"""FABulous GDS Generator - NLP Optimization Step using pymoo."""

import traceback
from pathlib import Path
from typing import TYPE_CHECKING

import numpy as np
import yaml
from librelane.config.variable import Variable
from librelane.logging.logger import err, info
from librelane.state.design_format import DesignFormat
from librelane.state.state import State
from librelane.steps.step import MetricsUpdate, Step, ViewsUpdate
from pymoo.algorithms.soo.nonconvex.de import DE
from pymoo.core.problem import Problem
from pymoo.optimize import minimize
from pymoo.termination import get_termination

from FABulous.fabric_definition.Fabric import Fabric
from FABulous.fabric_generator.gds_generator.helper import round_die_area
from FABulous.fabric_generator.gds_generator.steps.tile_macro_gen import TileMarcoGen
from FABulous.FABulous_settings import get_context

if TYPE_CHECKING:
    from FABulous.fabric_definition.Tile import Tile


class NLPTileProblem(Problem):
    """NLP problem class for tile size optimization using pymoo.

    This class defines the optimization problem with bilinear constraints
    for minimizing total fabric area subject to minimum area requirements.
    """

    def __init__(
        self,
        fabric: Fabric,
        tile_metrics,  # dict[tile_name, dict] OR dict[opt_mode, dict[tile_name, dict]]
        row_to_types,
        col_to_types,
        supertile_positions,
        num_rows,
        num_cols,
    ):
        self.fabric = fabric
        
        # Handle nested format {opt_mode: {tile_name: metrics}}
        # Flatten to {tile_name: metrics} by using first opt_mode
        if tile_metrics:
            first_key = next(iter(tile_metrics.keys()))
            first_value = tile_metrics[first_key]
            if isinstance(first_value, dict):
                # Check if nested format
                nested_first = next(iter(first_value.values()), None) if first_value else None
                if isinstance(nested_first, dict) and "design__die__bbox" in nested_first:
                    # Nested format detected
                    info(f"Detected nested metrics format, using opt_mode: '{first_key}'")
                    tile_metrics = first_value
        
        self.tile_metrics = tile_metrics  # dict[tile_name -> metric_dict]
        self.row_to_types = row_to_types
        self.col_to_types = col_to_types
        self.supertile_positions = supertile_positions
        self.num_rows = num_rows
        self.num_cols = num_cols

        # Extract per-tile metrics and compute aggregates
        tile_min_areas = {}
        tile_mode_options = {}
        min_tile_widths = {}
        min_tile_heights = {}

        # Get unique tile names to process
        unique_tiles = set()
        for r in range(num_rows):
            for c in range(num_cols):
                if fabric.tile[r][c] is not None:
                    unique_tiles.add(fabric.tile[r][c].name)

        for tile_name in unique_tiles:
            # For supertile components (e.g., DSP_top, DSP_bot), use parent supertile metrics
            metrics_key = tile_name
            tile_obj = fabric.tileDic.get(tile_name)
            if tile_obj and tile_obj.partOfSuperTile:
                # Find parent supertile name
                for super_name, super_tile in fabric.superTileDic.items():
                    if tile_name in [t.name for t in super_tile.tiles]:
                        metrics_key = super_name
                        break
            
            if metrics_key in tile_metrics:
                tile_metric_data = tile_metrics[metrics_key]

                # Extract die area (quad tuple) - x1,y1,x2,y2
                die_area_tuple = tile_metric_data.get("design__die__bbox", (0, 0, 1, 1))
                if isinstance(die_area_tuple, str):
                    # Parse string format like "0.0 0.0 200.16 250.32"
                    bbox_vals = [float(x) for x in die_area_tuple.split()]
                    width = bbox_vals[2] - bbox_vals[0]
                    height = bbox_vals[3] - bbox_vals[1]
                else:
                    # Already a tuple
                    _, _, width, height = die_area_tuple

                # Area from stdcell - ensure it's numeric
                area = tile_metric_data.get(
                    "design__instance__area__stdcell", width * height
                )
                if isinstance(area, str):
                    area = float(area)

                tile_min_areas[tile_name] = float(area)
                min_tile_widths[tile_name] = int(width)
                min_tile_heights[tile_name] = int(height)

                # For now, set basic mode options based on current dimensions
                # This could be extended to get from metrics if available
                tile_mode_options[tile_name] = [(width, height, "default")]

        self.tile_min_areas = tile_min_areas
        self.tile_mode_options = tile_mode_options
        self.min_tile_widths = min_tile_widths
        self.min_tile_heights = min_tile_heights

        # Build variable names and bounds
        self.var_names = []
        var_bounds = {}

        # Row heights
        for r in sorted(row_to_types.keys()):
            types_in_row = row_to_types[r]
            min_h = max(min_tile_heights.get(t, 1) for t in types_in_row)
            max_h = (
                max(
                    max(
                        (
                            h
                            for w, h, _ in tile_mode_options.get(
                                t, [(min_h, min_h, "")]
                            )
                        )
                    )
                    for t in types_in_row
                    if tile_mode_options.get(t)
                )
                if any(t in tile_mode_options for t in types_in_row)
                else min_h * 2
            )
            max_h = max(max_h, min_h + 10)  # Ensure upper bound
            var_bounds[f"row_h_{r}"] = (min_h, max_h)
            self.var_names.append(f"row_h_{r}")

        # Col widths
        for c in sorted(col_to_types.keys()):
            types_in_col = col_to_types[c]
            min_w = max(min_tile_widths.get(t, 1) for t in types_in_col)
            max_w = (
                max(
                    max((w for w, h, _ in tile_mode_options.get(t, [(min_w, 1, "")])))
                    for t in types_in_col
                    if tile_mode_options.get(t)
                )
                if any(t in tile_mode_options for t in types_in_col)
                else min_w * 2
            )
            max_w = max(max_w, min_w + 10)
            var_bounds[f"col_w_{c}"] = (min_w, max_w)
            self.var_names.append(f"col_w_{c}")

        # Supertile dimensions
        super_var_map = {}
        for type_name, r_start, c_start in supertile_positions:
            supertile = fabric.superTileDic[type_name]
            h_span = supertile.max_height
            w_span = supertile.max_width
            min_h = h_span  # At least 1 per row
            min_w = w_span  # At least 1 per col
            max_h = min_h * 2 if h_span == 1 else min_h + 10
            max_w = min_w * 2 if w_span == 1 else min_w + 10
            var_bounds[f"super_h_{type_name}_{r_start}_{c_start}"] = (min_h, max_h)
            var_bounds[f"super_w_{type_name}_{r_start}_{c_start}"] = (min_w, max_w)
            self.var_names.extend(
                [
                    f"super_h_{type_name}_{r_start}_{c_start}",
                    f"super_w_{type_name}_{r_start}_{c_start}",
                ]
            )
            h_idx = self.var_names.index(f"super_h_{type_name}_{r_start}_{c_start}")
            w_idx = self.var_names.index(f"super_w_{type_name}_{r_start}_{c_start}")
            super_var_map[(type_name, r_start, c_start)] = (h_idx, w_idx)

        # Build constraints
        regular_constraints = []  # (row, col, A_min)
        super_constraints = []  # (type, r_start, c_start, A_min, h_span, w_span)
        type_to_positions = {}  # temp for constraint building

        for r in range(num_rows):
            for c in range(num_cols):
                tile = fabric.tile[r][c]
                if tile is None:
                    continue
                tname = tile.name
                if tname in fabric.superTileDic:
                    supertile = fabric.superTileDic[tname]
                    h_span = supertile.max_height
                    w_span = supertile.max_width
                    super_constraints.append(
                        (tname, r, c, tile_min_areas[tname], h_span, w_span)
                    )
                else:
                    regular_constraints.append((r, c, tile_min_areas[tname]))

        self.regular_constraints = regular_constraints
        self.super_constraints = super_constraints
        self.super_var_map = super_var_map

        # Pre-compute variable index mappings for efficient access
        self.row_height_indices = {}  # row_idx -> x array position
        self.col_width_indices = {}  # col_idx -> x array position

        for i, name in enumerate(self.var_names):
            if name.startswith("row_h_"):
                row_idx = int(name.split("_")[2])
                self.row_height_indices[row_idx] = i
            elif name.startswith("col_w_"):
                col_idx = int(name.split("_")[2])
                self.col_width_indices[col_idx] = i

        # Bounds arrays
        xl = np.array([var_bounds[name][0] for name in self.var_names])
        xu = np.array([var_bounds[name][1] for name in self.var_names])

        n_constr = len(regular_constraints) + len(super_constraints)
        super().__init__(
            n_var=len(self.var_names), n_obj=1, n_constr=n_constr, xl=xl, xu=xu
        )

    def _evaluate(self, X, out):
        # X shape: (pop_size, n_var)
        if X.ndim == 1:
            X = X.reshape(1, -1)
        pop_size = X.shape[0]
        F = np.zeros(pop_size)
        G = np.zeros((pop_size, self.n_constr))

        for p in range(pop_size):
            x = X[p]

            # Objective: total area
            F[p] = self._compute_objective(x)
            # Constraints: both regular and super
            self._add_regular_tile_constraints(x, G, p)
            self._add_super_tile_constraints(x, G, p)

        out["F"] = F
        if self.n_constr > 0:
            out["G"] = G

    def _compute_objective(self, x):
        """Compute the total area objective for a single solution."""
        total_area = 0.0
        for r in range(self.num_rows):
            for c in range(self.num_cols):
                if r in self.row_height_indices and c in self.col_width_indices:
                    row_h = x[self.row_height_indices[r]]
                    col_w = x[self.col_width_indices[c]]
                    total_area += row_h * col_w
        return total_area

    def _add_regular_tile_constraints(self, x, G, p):
        """Add regular tile constraints for a single solution."""
        g_idx = 0  # Start from beginning for regular constraints
        for r, c, a_min in self.regular_constraints:
            if r in self.row_height_indices and c in self.col_width_indices:
                row_h = x[self.row_height_indices[r]]
                col_w = x[self.col_width_indices[c]]
                G[p, g_idx] = a_min - row_h * col_w  # <=0 means >= a_min
            g_idx += 1

    def _add_super_tile_constraints(self, x, G, p):
        """Add supertile constraints for a single solution."""
        g_idx = len(self.regular_constraints)  # Start after regular constraints
        for (
            type_name,
            r_start,
            c_start,
            a_min,
            h_span,
            w_span,
        ) in self.super_constraints:
            if (type_name, r_start, c_start) in self.super_var_map:
                h_idx, w_idx = self.super_var_map[(type_name, r_start, c_start)]
                super_h = x[h_idx]
                super_w = x[w_idx]
                G[p, g_idx] = a_min - super_h * super_w  # <=0 means >= a_min
            g_idx += 1


@Step.factory.register()
class GlobalTileSizeOptimization(Step):
    """LibreLane step for solving NLP optimization to find optimal tile dimensions.

    This step formulates and solves a Non-Linear Program using pymoo to minimize total
    fabric area subject to minimum area constraints (bilinear w*h >= A_min),
    row/column grid constraints, and SuperTile boundary constraints.

    After optimization, it automatically recompiles all tiles with the optimal dimensions
    and stores the recompiled states in metrics for downstream processing.
    """

    id = "FABulous.GlobalTileSizeOptimization"
    name = "FABulous Global Tile Size Optimization"

    config_vars = [
        Variable(
            "FABULOUS_FABRIC",
            Fabric,
            description="Fabric configuration object",
        ),
        Variable(
            "FABULOUS_PROJ_DIR",
            Path,
            description="Path to the FABulous project directory",
        ),
        Variable(
            "FABULOUS_ILP_SOLVER_TIME_LIMIT",
            int,
            description="Time limit in seconds for ILP solver",
            default=300,
        ),
    ]

    inputs = []
    outputs = [
        DesignFormat.GDS,
        DesignFormat.LEF,
        DesignFormat.LIB,
        DesignFormat.DEF,
    ]

    def run(self, state_in: State, **kwargs: str) -> tuple[ViewsUpdate, MetricsUpdate]:  # noqa: ARG002
        """Solve NLP problem and recompile tiles with optimal dimensions.

        The NLP formulation minimizes total fabric area sum(w_i*h_i) for all tiles,
        subject to minimum area constraints w_i*h_i >= A_min,i (bilinear terms),
        row/column grid consistency, and supertile spanning constraints.

        Variables: row_heights[r], col_widths[c] for each row/col with tiles
        Objective: Minimize sum over all positions: row_height[r] * col_width[c]
        Constraints:
        - Regular tiles: row_height[r] * col_width[c] >= A_min,i
        - Supertiles: sum_spanned_row_h * sum_spanned_col_w >= A_min,i
        - Bounds: from min tile dimensions to max available modes

        After solving, recompiles all tiles with optimal dimensions.

        Parameters
        ----------
        state_in : State
            Input state with fabric structure and tile dimension options

        Returns
        -------
        tuple[ViewsUpdate, MetricsUpdate]
            Updated views (design files) and metrics with optimal dimensions and recompiled states
        """
        info("Formulating NLP problem using pymoo...")

        # Get fabric configuration
        fabric: Fabric = self.config["FABULOUS_FABRIC"]
        time_limit = self.config.get("FABULOUS_ILP_SOLVER_TIME_LIMIT", 300)
        proj_dir = Path(self.config.get("FABULOUS_PROJ_DIR", "."))

        # Build fabric structure
        num_rows = len(fabric.tile)
        num_cols = len(fabric.tile[0]) if num_rows > 0 else 0

        row_to_types: dict[int, set[str]] = {}
        col_to_types: dict[int, set[str]] = {}
        type_to_positions: dict[str, list[tuple[int, int]]] = {}
        supertile_positions: list[tuple[str, int, int]] = []  # (type, row, col)

        for r in range(num_rows):
            for c in range(num_cols):
                tile = fabric.tile[r][c]
                if tile is None:
                    continue
                tname = tile.name
                row_to_types.setdefault(r, set()).add(tname)
                col_to_types.setdefault(c, set()).add(tname)
                type_to_positions.setdefault(tname, []).append((r, c))
                if tname in fabric.superTileDic:
                    supertile_positions.append((tname, r, c))

        info(
            f"Fabric: {num_rows}x{num_cols}, {len(type_to_positions)} tile types, {len(supertile_positions)} supertile instances"
        )

        # Get tile metrics
        min_tile_widths = state_in.metrics.get("tile_min_widths", {})
        min_tile_heights = state_in.metrics.get("tile_min_heights", {})
        tile_mode_options = state_in.metrics.get("tile_dimension_options", {})

        # Compute A_min,i for each tile type
        tile_min_areas: dict[str, int] = {}
        for tname in type_to_positions:
            if tile_mode_options and tname in tile_mode_options:
                # Min area from available modes
                min_area = min(w * h for w, h, _ in tile_mode_options[tname])
                tile_min_areas[tname] = min_area
            else:
                # Fallback to min dimensions
                tile_min_areas[tname] = min_tile_widths.get(
                    tname, 1
                ) * min_tile_heights.get(tname, 1)

        info(f"Tile minimum areas: {tile_min_areas}")

        # Create pymoo problem - constructor handles all the formatting
        problem = NLPTileProblem(
            fabric,
            state_in.metrics,  # Pass per-tile metrics dict
            row_to_types,
            col_to_types,
            supertile_positions,
            num_rows,
            num_cols,
        )

        # Solve with DE
        algorithm = DE(
            pop_size=len(problem.var_names) * 10
            if len(problem.var_names) < 50
            else 100,  # Adaptive pop size
            variant="DE/rand/1/bin",
            CR=0.9,
            F=0.8,
        )

        # Time limit via termination
        termination = get_termination("time", time_limit * 1000)  # in ms

        res = minimize(problem, algorithm, termination, verbose=True)

        if not res.success:
            raise RuntimeError(f"NLP optimization failed: {res}")

        # Extract results
        x_opt = res.X

        # Map back to dimensions
        optimal_row_h = {}
        optimal_col_w = {}

        for i, name in enumerate(problem.var_names):
            if name.startswith("row_h_"):
                r = int(name.split("_")[2])
                optimal_row_h[r] = x_opt[i]
            elif name.startswith("col_w_"):
                c = int(name.split("_")[2])
                optimal_col_w[c] = x_opt[i]

        # Tile dimensions from row/col
        optimal_widths_int = {}
        optimal_heights_int = {}

        for tname in type_to_positions:
            positions = type_to_positions[tname]
            if tname in fabric.superTileDic:
                # Supertile dimensions from specific instances
                for (tn, r, c), (h_idx, w_idx) in problem.super_var_map.items():
                    if tn == tname:
                        optimal_heights_int[tn] = int(x_opt[h_idx])
                        optimal_widths_int[tn] = int(x_opt[w_idx])
                        break
            else:
                # Regular tile: use row/col dimensions
                r, c = positions[0]  # Assume all same
                optimal_heights_int[tname] = int(
                    optimal_row_h.get(r, min_tile_heights.get(tname, 1))
                )
                optimal_widths_int[tname] = int(
                    optimal_col_w.get(c, min_tile_widths.get(tname, 1))
                )

        total_area = int(res.F[0])
        row_heights_list = [
            int(optimal_row_h.get(r, 1)) for r in sorted(row_to_types.keys())
        ]
        col_widths_list = [
            int(optimal_col_w.get(c, 1)) for c in sorted(col_to_types.keys())
        ]
        status = "Optimal" if res.success else "Feasible"


        # Report results
        info(f"NLP solver status: {status}")
        if res and res.success:
            info(f"  Converged in {res.algorithm.evaluator.n_eval} evaluations")

        info(f"  Total fabric area: {total_area}")
        info(f"  Optimal tile widths: {optimal_widths_int}")
        info(f"  Optimal tile heights: {optimal_heights_int}")
        info(f"  Row heights: {row_heights_list}")
        info(f"  Col widths: {col_widths_list}")

        # Step 4: Recompile tiles with optimal dimensions
        info("\n=== Recompiling tiles with optimal dimensions ===")

        views_updates = {}
        metrics_updates = {
            "nlp_optimal_widths": optimal_widths_int,
            "nlp_optimal_heights": optimal_heights_int,
            "nlp_total_area": total_area,
            "nlp_row_heights": row_heights_list,
            "nlp_col_widths": col_widths_list,
            "nlp_solver_status": status,
            "type_to_positions": type_to_positions,
        }

        return views_updates, metrics_updates

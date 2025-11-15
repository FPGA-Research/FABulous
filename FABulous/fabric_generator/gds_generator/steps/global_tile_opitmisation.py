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
        self.tile_metrics = tile_metrics  # Keep nested format: {opt_mode: {tile_name: {metrics}}}
        self.row_to_types = row_to_types
        self.col_to_types = col_to_types
        self.supertile_positions = supertile_positions
        self.num_rows = num_rows
        self.num_cols = num_cols

        # Extract per-tile metrics from all opt_modes
        # tile_metrics has format: {opt_mode: {tile_name: {metrics}}}
        tile_mode_constraints = {}  # {tile_name: [(min_w, min_h, area, mode_name)]}
        min_tile_widths = {}  # Absolute minimum width across all modes
        min_tile_heights = {}  # Absolute minimum height across all modes

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
            
            # Extract metrics from all opt_modes
            mode_constraints = []
            all_widths = []
            all_heights = []
            
            for opt_mode, tiles_data in tile_metrics.items():
                if metrics_key in tiles_data:
                    tile_metric_data = tiles_data[metrics_key]

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

                    mode_constraints.append((width, height, float(area), opt_mode))
                    all_widths.append(width)
                    all_heights.append(height)
            
            if mode_constraints:
                tile_mode_constraints[tile_name] = mode_constraints
                min_tile_widths[tile_name] = int(min(all_widths))
                min_tile_heights[tile_name] = int(min(all_heights))
        
        self.tile_mode_constraints = tile_mode_constraints
        self.min_tile_widths = min_tile_widths
        self.min_tile_heights = min_tile_heights
        self.min_tile_widths = min_tile_widths
        self.min_tile_heights = min_tile_heights

        # Build variable names and bounds
        self.var_names = []
        var_bounds = {}

        # Row heights
        for r in sorted(row_to_types.keys()):
            types_in_row = row_to_types[r]
            min_h = max(min_tile_heights.get(t, 1) for t in types_in_row)
            # Max height: maximum across all modes for all tiles in row
            max_h = min_h
            for t in types_in_row:
                if t in tile_mode_constraints:
                    max_h = max(max_h, max(h for w, h, a, mode in tile_mode_constraints[t]))
            max_h = max(max_h, min_h * 3)  # Allow some flexibility
            var_bounds[f"row_h_{r}"] = (min_h, max_h)
            self.var_names.append(f"row_h_{r}")

        # Col widths
        for c in sorted(col_to_types.keys()):
            types_in_col = col_to_types[c]
            min_w = max(min_tile_widths.get(t, 1) for t in types_in_col)
            # Max width: maximum across all modes for all tiles in column
            max_w = min_w
            for t in types_in_col:
                if t in tile_mode_constraints:
                    max_w = max(max_w, max(w for w, h, a, mode in tile_mode_constraints[t]))
            max_w = max(max_w, min_w * 3)  # Allow some flexibility
            var_bounds[f"col_w_{c}"] = (min_w, max_w)
            self.var_names.append(f"col_w_{c}")

        # Don't create separate supertile variables
        # Supertiles will use sum of row/col heights/widths they span

        # Build constraints - for each tile position, use minimum area across all modes
        # The tile must be able to accommodate at least its smallest feasible configuration
        regular_constraints = []  # (row, col, A_min)
        super_constraints = []  # (type, r_start, c_start, A_min, h_span, w_span)

        for r in range(num_rows):
            for c in range(num_cols):
                tile = fabric.tile[r][c]
                if tile is None:
                    continue
                tname = tile.name
                
                # Find metrics key (handle supertile components)
                metrics_key = tname
                tile_obj = fabric.tileDic.get(tname)
                if tile_obj and tile_obj.partOfSuperTile:
                    for super_name, super_tile in fabric.superTileDic.items():
                        if tname in [t.name for t in super_tile.tiles]:
                            metrics_key = super_name
                            break
                
                # Check if this is a supertile or component tile
                if tname in fabric.superTileDic:
                    # Direct supertile reference
                    supertile = fabric.superTileDic[tname]
                    h_span = supertile.max_height
                    w_span = supertile.max_width
                    # Use maximum die area across all modes (accounts for aspect ratio constraints)
                    # This ensures the tile has enough space for any feasible configuration
                    if metrics_key in tile_mode_constraints:
                        # Use max die area (w×h) across modes, not just stdcell area
                        # This captures the aspect ratio constraints from OpenROAD
                        max_die_area = max(w * h for w, h, a, mode in tile_mode_constraints[metrics_key])
                        constraint_area = max_die_area
                    else:
                        constraint_area = 1
                    super_constraints.append(
                        (tname, r, c, constraint_area, h_span, w_span)
                    )
                elif tile.partOfSuperTile:
                    # This is a component tile (e.g., DSP_top/DSP_bot)
                    # Skip it - the parent supertile constraint will handle it
                    pass
                else:
                    # Regular tile - use maximum die area to capture aspect ratio constraints
                    if metrics_key in tile_mode_constraints:
                        # Use max die area (w×h) across modes
                        # This ensures dimensions satisfy feasibility from at least one mode
                        max_die_area = max(w * h for w, h, a, mode in tile_mode_constraints[metrics_key])
                        constraint_area = max_die_area
                    else:
                        constraint_area = 1
                    regular_constraints.append((r, c, constraint_area))

        self.regular_constraints = regular_constraints
        self.super_constraints = super_constraints

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
        """Add supertile constraints for a single solution.
        
        Supertiles span multiple rows/columns, so we sum the heights/widths:
        For DSP spanning rows r, r+1 and column c:
        (row_h[r] + row_h[r+1]) * col_w[c] >= DSP_min_area
        """
        g_idx = len(self.regular_constraints)  # Start after regular constraints
        for (
            type_name,
            r_start,
            c_start,
            a_min,
            h_span,
            w_span,
        ) in self.super_constraints:
            # Sum row heights for rows spanned by supertile
            total_h = 0.0
            for r in range(r_start, r_start + h_span):
                if r in self.row_height_indices:
                    total_h += x[self.row_height_indices[r]]
            
            # Sum col widths for columns spanned by supertile
            total_w = 0.0
            for c in range(c_start, c_start + w_span):
                if c in self.col_width_indices:
                    total_w += x[self.col_width_indices[c]]
            
            # Constraint: total_h * total_w >= a_min
            G[p, g_idx] = a_min - total_h * total_w  # <=0 means >= a_min
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

        # Track supertile instances by detecting component tiles
        supertile_seen = set()  # Track (super_name, r_start, c_start) to avoid duplicates
        
        for r in range(num_rows):
            for c in range(num_cols):
                tile = fabric.tile[r][c]
                if tile is None:
                    continue
                tname = tile.name
                
                # Check if this tile is part of a supertile
                if tile.partOfSuperTile:
                    # This is a component of a supertile (e.g., DSP_top is part of DSP)
                    # Don't add component tiles to row_to_types/col_to_types individually
                    # Only record the parent supertile
                    for super_name, super_tile in fabric.superTileDic.items():
                        if any(t.name == tname for t in super_tile.tiles):
                            # Found parent supertile
                            # Only record once at first component position
                            if tname == super_tile.tiles[0].name:  # First component
                                key = (super_name, r, c)
                                if key not in supertile_seen:
                                    supertile_positions.append((super_name, r, c))
                                    supertile_seen.add(key)
                                    # Add parent supertile to row/col types (not components)
                                    for rr in range(r, r + super_tile.max_height):
                                        row_to_types.setdefault(rr, set()).add(super_name)
                                    for cc in range(c, c + super_tile.max_width):
                                        col_to_types.setdefault(cc, set()).add(super_name)
                                    type_to_positions.setdefault(super_name, []).append((r, c))
                            break
                elif tname in fabric.superTileDic:
                    # This is a supertile type appearing directly (shouldn't happen normally)
                    supertile_positions.append((tname, r, c))
                    row_to_types.setdefault(r, set()).add(tname)
                    col_to_types.setdefault(c, set()).add(tname)
                    type_to_positions.setdefault(tname, []).append((r, c))
                else:
                    # Regular tile
                    row_to_types.setdefault(r, set()).add(tname)
                    col_to_types.setdefault(c, set()).add(tname)
                    type_to_positions.setdefault(tname, []).append((r, c))

        info(
            f"Fabric: {num_rows}x{num_cols}, {len(type_to_positions)} tile types, {len(supertile_positions)} supertile instances"
        )

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
        
        # Log mode information
        mode_summary = {}
        for tname, modes in problem.tile_mode_constraints.items():
            mode_summary[tname] = {
                mode: f"{w:.0f}x{h:.0f} ({a:.0f})" 
                for w, h, a, mode in modes
            }
        info(f"Tile optimization modes: {mode_summary}")

        # Solve with DE
        algorithm = DE(
            pop_size=len(problem.var_names) * 10
            if len(problem.var_names) < 50
            else 100,  # Adaptive pop size
            variant="DE/rand/1/bin",
            CR=0.9,
            F=0.8,
        )

        # Time limit termination
        from pymoo.termination.max_time import TimeBasedTermination
        termination = TimeBasedTermination(max_time=time_limit)

        info(f"Running optimization with time limit: {time_limit}s")
        res = minimize(problem, algorithm, termination, verbose=True)

        # Check if we have a valid solution (X is not None)
        # res.success can be False when time limit is reached, but solution is still valid
        if res.X is None:
            raise RuntimeError(f"NLP optimization failed to find any solution")
        
        info(f"Optimization terminated. Success={res.success}, found solution with objective={res.F}")

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
                # Supertile: sum the row heights and col widths it spans
                supertile = fabric.superTileDic[tname]
                r_start, c_start = positions[0]
                
                # Sum heights for rows spanned
                total_h = sum(
                    optimal_row_h.get(r, 0)
                    for r in range(r_start, r_start + supertile.max_height)
                )
                # Sum widths for cols spanned
                total_w = sum(
                    optimal_col_w.get(c, 0)
                    for c in range(c_start, c_start + supertile.max_width)
                )
                
                optimal_heights_int[tname] = int(total_h)
                optimal_widths_int[tname] = int(total_w)
            else:
                # Regular tile: use row/col dimensions
                r, c = positions[0]  # Assume all same
                optimal_heights_int[tname] = int(
                    optimal_row_h.get(r, problem.min_tile_heights.get(tname, 1))
                )
                optimal_widths_int[tname] = int(
                    optimal_col_w.get(c, problem.min_tile_widths.get(tname, 1))
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

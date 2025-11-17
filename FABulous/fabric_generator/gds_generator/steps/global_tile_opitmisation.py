"""FABulous GDS Generator - NLP Optimization Step using pymoo."""

from typing import Optional
from librelane.flows.flow import FlowException
from collections import Counter
import math
from typing import NamedTuple
from collections import defaultdict
import json
from pathlib import Path

import numpy as np
from librelane.config.variable import Variable
from librelane.logging.logger import info
from librelane.state.design_format import DesignFormat
from librelane.state.state import State
from librelane.steps.step import MetricsUpdate, Step, ViewsUpdate
from pymoo.algorithms.soo.nonconvex.de import DE
from pymoo.core.problem import ElementwiseProblem, Problem
from pymoo.optimize import minimize

from FABulous.fabric_definition.Fabric import Fabric
from FABulous.fabric_definition.SuperTile import SuperTile
from FABulous.fabric_definition.Tile import Tile
from FABulous.fabric_generator.gds_generator.steps.tile_optimisation import OptMode


class NLPTileProblem(ElementwiseProblem):
    """NLP problem class for tile size optimization using pymoo.

    This class defines the optimization problem with bilinear constraints
    for minimizing total fabric area subject to minimum area requirements.
    """

    class PositionIndex(NamedTuple):
        width_idx: int
        height_idx: int

    def __init__(
        self,
        fabric: Fabric,
        tile_metrics: dict[
            OptMode, dict
        ],  # dict[tile_name, dict] OR dict[opt_mode, dict[tile_name, dict]]
    ):
        self.fabric = fabric
        self.tile_metrics = (
            tile_metrics  # Keep nested format: {opt_mode: {tile_name: {metrics}}}
        )

        self.tile_count = Counter(
            [t.name for (_, _), t in self.fabric if t is not None]
        )
        # Get unique tile names to process
        unique_tiles: list[Tile] = list(fabric.tileDic.values())
        self.tile_row_set: dict[str, set[int]] = defaultdict(set)
        self.tile_column_set: dict[str, set[int]] = defaultdict(set)

        for (x, y), tile in fabric:
            if tile is None:
                continue
            self.tile_row_set[tile.name].add(y)
            self.tile_column_set[tile.name].add(x)

        indices: int = 0
        self.tile_to_solution_index: dict[str, NLPTileProblem.PositionIndex] = {}
        for t in unique_tiles:
            self.tile_to_solution_index[t.name] = NLPTileProblem.PositionIndex(
                width_idx=indices, height_idx=indices + 1
            )
            indices += 2

        tile_min: dict[str, tuple[float, float]] = {}

        print(self.tile_metrics)
        for i in unique_tiles:
            if i.partOfSuperTile:
                # Skip component tiles of supertiles
                continue
            tmp_min_width: float = -math.inf
            tmp_min_height: float = -math.inf
            for j in self.tile_metrics.values():
                if i.name not in j:
                    continue
                _, _, w, h = j[i.name]["design__die__bbox"]
                tmp_min_width = max(tmp_min_width, w)
                tmp_min_height = max(tmp_min_height, h)
            tile_min[i.name] = (tmp_min_width, tmp_min_height)

        # For each supertile, compute min/max dimensions for its component tiles
        for supertile in fabric.superTileDic.values():
            row_min_heights: dict[str, float] = {}
            for row in supertile.tileMap:
                # Compute min_height for this row from max of component tile min_heights in that row
                for component_tile in row:
                    if component_tile is None:
                        continue
                    component_name = component_tile.name
                    on_rows = self.tile_row_set[component_tile.name]
                    target_tile: set[str] = set()
                    for t, s in self.tile_row_set.items():
                        if t == component_name:
                            continue
                        if len(on_rows & s) > 0:
                            target_tile.add(t)

                    row_min_heights[component_name] = max(
                        [tile_min[i][1] for i in target_tile if i in tile_min]
                    )

            # Compute min_width for each column
            col_min_widths: dict[str, float] = {}
            for col_idx in range(supertile.max_width):
                for row in supertile.tileMap:
                    if col_idx < len(row):
                        component_tile = row[col_idx]
                        if component_tile is None:
                            continue
                        component_name = component_tile.name
                        on_cols = self.tile_column_set[component_tile.name]
                        target_tile: set[str] = set()
                        for t, s in self.tile_column_set.items():
                            if t == component_name:
                                continue
                            if len(on_cols & s) > 0:
                                target_tile.add(t)

                        col_min_widths[component_name] = max(
                            [tile_min[i][0] for i in target_tile if i in tile_min]
                        )

            # Update tile_min with computed column widths
            for (_, _), sub_tile in supertile:
                tile_min[sub_tile.name] = (
                    col_min_widths[sub_tile.name],
                    row_min_heights[sub_tile.name],
                )

        xl = np.zeros(len(self.tile_to_solution_index) * 2)
        for t, indices in self.tile_to_solution_index.items():
            xl[indices.width_idx] = tile_min[t][0]
            xl[indices.height_idx] = tile_min[t][1]

        xu = np.full(len(self.tile_to_solution_index) * 2, np.inf)

        # Count constraints
        n_constr = (
            len(fabric.tileDic.values()) * 2 + len(fabric.superTileDic.values()) * 2
        )

        super().__init__(
            n_var=len(self.tile_to_solution_index) * 2,
            n_obj=1,
            n_constr=n_constr,
            xl=xl,
            xu=xu,
        )

    def _evaluate(self, X, out):
        # X shape: (pop_size, n_var)
        if X.ndim == 1:
            X = X.reshape(1, -1)
        pop_size = X.shape[0]
        F = np.zeros(pop_size)
        G = np.zeros((pop_size, self.n_constr))

        out["F"] = self._compute_objective(X)
        out["G"] = np.column_stack(
            [
                self._add_equality_constraints(X),
                self._add_mode_constraints(X),
            ]
        )

    def _compute_objective(self, x):
        """Compute the total area objective for a single solution."""
        total_area = 0.0
        for tile_name, indices in self.tile_to_solution_index.items():
            w = x[0][indices.width_idx]
            h = x[0][indices.height_idx]
            total_area += w * h * self.tile_count[tile_name]
        return total_area

    def _add_equality_constraints(self, x):
        """Add equality constraints: tiles on same row have same height, same column have same width.

        Uses abs(a - b) <= tolerance for equality.
        """
        result = []
        # Height equality: tiles on same row
        for tile_name in self.tile_row_set:
            tile = self.fabric.tileDic[tile_name]
            if tile.partOfSuperTile:
                continue
            on_rows = self.tile_row_set[tile_name]
            tile_idx = self.tile_to_solution_index[tile_name]
            tile_h = x[tile_idx.height_idx]

            for other_name in self.tile_row_set:
                if other_name == tile_name:  # Avoid duplicates
                    continue
                other_tile = self.fabric.tileDic[other_name]
                other_rows = self.tile_row_set[other_name]
                if len(on_rows & other_rows) > 0:
                    other_idx = self.tile_to_solution_index[other_name]
                    other_h = x[other_idx.height_idx]
                    result.append(abs(tile_h - other_h) - 0.1)

        # Width equality: tiles on same column
        for tile_name in self.tile_column_set:
            tile = self.fabric.tileDic[tile_name]
            if tile.partOfSuperTile:
                continue
            on_cols = self.tile_column_set[tile_name]
            tile_idx = self.tile_to_solution_index[tile_name]
            tile_w = x[tile_idx.width_idx]

            for other_name in self.tile_column_set:
                if other_name <= tile_name:  # Avoid duplicates
                    continue
                other_tile = self.fabric.tileDic[other_name]
                if other_tile.partOfSuperTile:
                    continue
                other_cols = self.tile_column_set[other_name]
                if len(on_cols & other_cols) > 0:
                    other_idx = self.tile_to_solution_index[other_name]
                    other_w = x[other_idx.width_idx]
                    result.append(abs(tile_w - other_w) - 0.1)

        return result

    def _add_mode_constraints(self, x):
        """Add mode constraints: at least one mode must be satisfied.

        For regular tiles: w * h >= mode_die_area for at least one mode
        For supertiles: sum(component_widths) * sum(component_heights) >= mode_die_area for at least one mode
        """
        result = []
        # Regular tiles
        for tile in self.fabric.tileDic.values():
            if tile.partOfSuperTile:
                continue

            tile_idx = self.tile_to_solution_index[tile.name]
            tile_w = x[tile_idx.width_idx]
            tile_h = x[tile_idx.height_idx]

            # Collect all modes for this tile
            mode_constraints = []
            for mode_metrics in self.tile_metrics.values():
                if tile.name in mode_metrics:
                    _, _, w, h = mode_metrics[tile.name]["DESIGN__DIE__BBOX"]
                    mode_die_area = w * h
                    # Constraint: mode_die_area - tile_w * tile_h <= 0
                    result.append(mode_die_area - tile_w * tile_h)

        # Supertiles
        for supertile in self.fabric.superTileDic.values():
            # Sum component tile dimensions
            total_w = 0.0
            total_h = 0.0

            for sub_tile in supertile.tiles:
                sub_idx = self.tile_to_solution_index[sub_tile.name]
                total_w += x[sub_idx.width_idx]
                total_h += x[sub_idx.height_idx]

            # Collect all modes for this supertile
            mode_constraints = []
            for mode_metrics in self.tile_metrics.values():
                if supertile.name in mode_metrics:
                    _, _, w, h = mode_metrics[supertile.name]["DESIGN__DIE__BBOX"]
                    mode_die_area = w * h
                    # Constraint: mode_die_area - total_w * total_h <= 0
                    result.append(mode_die_area - total_w * total_h)

        return result


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
            "TILE_OPT_INFO",
            Optional[Path],
            description="Tile optimization information dictionary or path to JSON file",
            default=None,
        ),
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

        if self.config["TILE_OPT_INFO"] is None:
            raise FlowException(
                "Values of TILE_OPT_INFO should have been set when calling this step."
            )
        # Get fabric configuration
        fabric: Fabric = self.config["FABULOUS_FABRIC"]
        time_limit = self.config.get("FABULOUS_ILP_SOLVER_TIME_LIMIT", 300)
        if isinstance(self.config["TILE_OPT_INFO"], Path):
            tile_data: dict[OptMode, dict] = {}
            tile_data_raw = json.load(self.config["TILE_OPT_INFO"].open())
            for mode, tile_info in tile_data_raw.items():
                tile_data[OptMode(mode)] = {}
                for tile_name, data in tile_info.items():
                    if "error" in data:
                        continue
                    tile_data[OptMode(mode)][tile_name] = {}
                    tile_data[OptMode(mode)][tile_name]["design__die__bbox"] = [
                        float(i) for i in data["design__die__bbox"].split()
                    ]
                    tile_data[OptMode(mode)][tile_name]["design__core__bbox"] = [
                        float(i) for i in data["design__core__bbox"].split()
                    ]
            tile_opt_data = tile_data
        else:
            tile_opt_data = self.config["TILE_OPT_INFO"]
        # Build fabric structure
        num_rows = len(fabric.tile)
        num_cols = len(fabric.tile[0]) if num_rows > 0 else 0

        row_to_types: dict[int, set[str]] = {}
        col_to_types: dict[int, set[str]] = {}
        type_to_positions: dict[str, list[tuple[int, int]]] = {}
        supertile_positions: list[tuple[str, int, int]] = []  # (type, row, col)

        # Track supertile instances by detecting component tiles
        supertile_seen = (
            set()
        )  # Track (super_name, r_start, c_start) to avoid duplicates

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
                                        row_to_types.setdefault(rr, set()).add(
                                            super_name
                                        )
                                    for cc in range(c, c + super_tile.max_width):
                                        col_to_types.setdefault(cc, set()).add(
                                            super_name
                                        )
                                    type_to_positions.setdefault(super_name, []).append(
                                        (r, c)
                                    )
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
            tile_opt_data,
        )

        # Solve with DE
        algorithm = DE(
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
            raise RuntimeError("NLP optimization failed to find any solution")

        info(
            f"Optimization terminated. Success={res.success}, found solution with objective={res.F}"
        )

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

"""FABulous GDS Generator - NLP Optimization Step using pymoo."""

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
from pymoo.core.problem import Problem
from pymoo.optimize import minimize

from FABulous.fabric_definition.Fabric import Fabric
from FABulous.fabric_definition.SuperTile import SuperTile
from FABulous.fabric_definition.Tile import Tile
from FABulous.fabric_generator.gds_generator.steps.tile_optimisation import OptMode


class NLPTileProblem(Problem):
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

        # Get unique tile names to process
        unique_tiles: list[Tile] = list(fabric.tileDic.values())
        self.tile_row_set: dict[str, set[int]] = defaultdict(set)
        self.tile_column_set: dict[str, set[int]] = defaultdict(set)

        for (x, y), tile in fabric:
            if tile is None:
                continue
            self.tile_row_set[tile.name].add(x)
            self.tile_column_set[tile.name].add(y)

        indices: int = 0
        self.tile_to_solution_index: dict[str, NLPTileProblem.PositionIndex] = {}
        for t in unique_tiles:
            self.tile_to_solution_index[t.name] = NLPTileProblem.PositionIndex(
                width_idx=indices, height_idx=indices + 1
            )
            indices += 2

        tile_min: dict[str, tuple[float, float]] = {}

        for i in unique_tiles:
            if i.partOfSuperTile:
                # Skip component tiles of supertiles
                continue
            tmp_min_width: float = -math.inf
            tmp_min_height: float = -math.inf
            tmp_max_width: float = math.inf
            tmp_max_height: float = math.inf
            for j in self.tile_metrics.values():
                _, _, w, h = j[i.name]["DESIGN__DIE__BBOX"]
                tmp_min_width = max(tmp_min_width, w)
                tmp_min_height = max(tmp_min_height, h)
                tmp_max_width = min(tmp_max_width, w)
                tmp_max_height = min(tmp_max_height, h)
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
                        [tile_min[i][1] for i in target_tile]
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
                            [tile_min[i][0] for i in target_tile]
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
        super().__init__(            n_var=len(self.tile_to_solution_index)*2, n_obj=1, n_constr=n_constr, xl=xl, xu=xu
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

            # Constraints
            g_idx = 0
            # 1. Regular tile mode constraints
            g_idx = self._add_regular_tile_mode_constraints(x, G[p], g_idx)
            # 2. Supertile mode constraints
            g_idx, supertile_dims = self._add_supertile_mode_constraints(x, G[p], g_idx)
            # 3. Supertile equality constraints
            g_idx = self._add_supertile_equality_constraints(
                G[p], g_idx, supertile_dims
            )

        out["F"] = F
        if self.n_constr > 0:
            out["G"] = G

    def _count_constraints(self):
        """Count total number of constraints needed."""
        n_constr = 0

        # Regular tile mode constraints
        for r, c, tile_name, modes_list in self.regular_constraints:
            n_constr += len(modes_list) if modes_list else 1

        # Supertile constraints
        for (
            tname,
            r,
            c,
            tile_name,
            modes_list,
            h_span,
            w_span,
        ) in self.super_constraints:
            # Mode area constraints: 2 per mode (lower and upper bound)
            n_constr += 2 * len(modes_list) if modes_list else 1
            # Row equality constraints
            if h_span > 1:
                n_constr += h_span - 1
            # Column equality constraints
            if w_span > 1:
                n_constr += w_span - 1

        return n_constr

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

    def _add_regular_tile_mode_constraints(self, x, G, g_idx):
        """Add mode area constraints for regular tiles.

        For each tile mode: row_h[r] × col_w[c] >= mode_die_area
        Returns updated constraint index.
        """
        for r, c, tile_name, modes_list in self.regular_constraints:
            if r in self.row_height_indices and c in self.col_width_indices:
                row_h = x[self.row_height_indices[r]]
                col_w = x[self.col_width_indices[c]]

                if modes_list:
                    for mode_w, mode_h, stdcell_area, mode_name in modes_list:
                        mode_die_area = mode_w * mode_h
                        G[g_idx] = mode_die_area - row_h * col_w
                        g_idx += 1
                else:
                    G[g_idx] = 1 - row_h * col_w
                    g_idx += 1
            else:
                if modes_list:
                    g_idx += len(modes_list)
                else:
                    g_idx += 1

        return g_idx

    def _add_supertile_mode_constraints(self, x, G, g_idx):
        """Add mode area constraints for supertiles.

        For each mode:
        - Lower bound: (Σrow_h) × (Σcol_w) >= mode_die_area
        - Upper bound: (Σrow_h) × (Σcol_w) <= mode_die_area * 1.15

        Returns updated constraint index and supertile dimensions for equality constraints.
        """
        supertile_dimensions = []  # Store for later equality constraints

        for (
            tname,
            r_start,
            c_start,
            tile_name,
            modes_list,
            h_span,
            w_span,
        ) in self.super_constraints:
            # Sum row heights
            total_h = 0.0
            row_heights = []
            for r in range(r_start, r_start + h_span):
                if r in self.row_height_indices:
                    h = x[self.row_height_indices[r]]
                    total_h += h
                    row_heights.append(h)

            # Sum col widths
            total_w = 0.0
            col_widths = []
            for c in range(c_start, c_start + w_span):
                if c in self.col_width_indices:
                    w = x[self.col_width_indices[c]]
                    total_w += w
                    col_widths.append(w)

            # Store dimensions for equality constraints
            supertile_dimensions.append((row_heights, col_widths, h_span, w_span))

            # Mode area constraints
            if modes_list:
                for mode_w, mode_h, stdcell_area, mode_name in modes_list:
                    mode_die_area = mode_w * mode_h
                    # Lower bound
                    G[g_idx] = mode_die_area - total_h * total_w
                    g_idx += 1
                    # Upper bound (prevent oversizing)
                    G[g_idx] = total_h * total_w - mode_die_area * 1.15
                    g_idx += 1
            else:
                G[g_idx] = 1 - total_h * total_w
                g_idx += 1

        return g_idx, supertile_dimensions

    def _add_supertile_equality_constraints(self, G, g_idx, supertile_dimensions):
        """Add equality constraints for supertile rows/columns.

        Rows spanned by a supertile should have equal heights.
        Columns spanned by a supertile should have equal widths.
        """
        for row_heights, col_widths, h_span, w_span in supertile_dimensions:
            # Row equality: row_h[i] ≈ row_h[i+1]
            if h_span > 1 and len(row_heights) > 1:
                for i in range(len(row_heights) - 1):
                    diff = abs(row_heights[i] - row_heights[i + 1])
                    G[g_idx] = diff - 0.1  # 0.1 DBU tolerance
                    g_idx += 1

            # Column equality: col_w[i] ≈ col_w[i+1]
            if w_span > 1 and len(col_widths) > 1:
                for i in range(len(col_widths) - 1):
                    diff = abs(col_widths[i] - col_widths[i + 1])
                    G[g_idx] = diff - 0.1  # 0.1 DBU tolerance
                    g_idx += 1

        return g_idx


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
            dict | Path,
            description="Tile optimization information dictionary or path to JSON file",
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

        # Get fabric configuration
        fabric: Fabric = self.config["FABULOUS_FABRIC"]
        time_limit = self.config.get("FABULOUS_ILP_SOLVER_TIME_LIMIT", 300)
        if isinstance(self.config["TILE_OPT_INFO"], Path):
            tile_data: dict[OptMode, dict] = {}
            tile_data_raw = json.load(self.config["TILE_OPT_INFO"].open())
            for mode, tile_info in tile_data_raw.items():
                tile_data[OptMode(mode)] = {}
                tile_data[OptMode(mode)]["design__core__bbox"] = [
                    float(i) for i in tile_info["design__die__bbox"].split()
                ]
                tile_data[OptMode(mode)]["design__core__bbox"] = [
                    float(i) for i in tile_info["design__core__bbox"].split()
                ]
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

        # Log mode information
        mode_summary = {}
        for tname, modes in problem.tile_mode_constraints.items():
            mode_summary[tname] = {
                mode: f"{w:.0f}x{h:.0f} ({a:.0f})" for w, h, a, mode in modes
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

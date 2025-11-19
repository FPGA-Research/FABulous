"""FABulous GDS Generator - NLP Optimization Step using pymoo."""

import json
from collections import Counter, defaultdict
from decimal import Decimal
from pathlib import Path
from typing import NamedTuple, Optional

import numpy as np
from librelane.config.variable import Variable
from librelane.flows.flow import FlowException
from librelane.logging.logger import info, warn
from librelane.state.design_format import DesignFormat
from librelane.state.state import State
from librelane.steps.step import MetricsUpdate, Step, ViewsUpdate
from pymoo.algorithms.soo.nonconvex.isres import ISRES
from pymoo.core.problem import ElementwiseProblem
from pymoo.core.repair import Repair
from pymoo.core.termination import TerminateIfAny
from pymoo.optimize import minimize
from pymoo.termination.ftol import SingleObjectiveSpaceTermination
from pymoo.termination.max_gen import MaximumGenerationTermination

from FABulous.fabric_definition.Fabric import Fabric
from FABulous.fabric_definition.Tile import Tile
from FABulous.fabric_generator.gds_generator.helper import round_up_decimal
from FABulous.fabric_generator.gds_generator.steps.tile_optimisation import OptMode


class NLPTileProblem(ElementwiseProblem):
    """NLP problem class for tile size optimization using pymoo.

    This class defines the optimization problem with bilinear constraints for minimizing
    total fabric area subject to minimum area requirements.

    Parameters
    ----------
    fabric : Fabric
        the fabric object that contains the tile layout and structure
    tile_metrics : dict[OptMode, dict]
        Dictionary of tile metrics per optimization mode, containing die bounding boxes
    """

    class PositionIndex(NamedTuple):
        """Helper class for named values."""

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

        for i in unique_tiles:
            if i.partOfSuperTile:
                # Skip component tiles of supertiles
                continue
            tmp_min_width: float = 1.0
            tmp_min_height: float = 1.0
            for j in self.tile_metrics.values():
                if i.name not in j:
                    continue
                x0, y0, x1, y1 = j[i.name]["design__die__bbox"]
                w = x1 - x0
                h = y1 - y0
                tmp_min_width = max(tmp_min_width, w)
                tmp_min_height = max(tmp_min_height, h)
            tile_min[i.name] = (tmp_min_width, tmp_min_height)

        # For each supertile, compute min/max dimensions for its component tiles
        for supertile in fabric.superTileDic.values():
            row_min_heights: dict[str, float] = {}
            for row in supertile.tileMap:
                # Compute min_height for this row from max of component tile
                # min_heights in that row
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
        xu = np.zeros(len(self.tile_to_solution_index) * 2)

        for k, v in tile_min.items():
            indices = self.tile_to_solution_index[k]
            xl[indices.width_idx] = v[0]
            xl[indices.height_idx] = v[1]

        xu = xl.copy() * 4  # Arbitrary upper bound: 4x min size

        # Count constraints by simulating what will be generated
        x = np.zeros(len(self.tile_to_solution_index) * 2)

        super().__init__(
            n_var=len(self.tile_to_solution_index) * 2,
            n_obj=1,
            n_ieq_constr=len(self._add_mode_constraints(x))
            + len(self._add_equality_constraints(x)),
            xl=xl,
            xu=xu,
        )

    def _evaluate(self, x: np.ndarray, out: dict) -> None:
        """Pymoo evaluation function for objective and constraints."""
        # x shape: (n_var,) - single solution vector for ElementwiseProblem
        out["F"] = self._compute_objective(x)

        eq_constraints = self._add_equality_constraints(x)
        mode_constraints = self._add_mode_constraints(x)

        # Concatenate all constraints
        all_constraints = eq_constraints + mode_constraints
        out["G"] = np.array(all_constraints)

    def _compute_objective(self, x: np.ndarray) -> float:
        """Compute the total area objective for a single solution."""
        total_area = 0.0
        for tile_name, indices in self.tile_to_solution_index.items():
            w = x[indices.width_idx]
            h = x[indices.height_idx]
            total_area += w * h * self.tile_count[tile_name]
        return total_area

    def _add_equality_constraints(self, x: np.ndarray) -> list:
        """Add equality constraints on tile dimensions.

        For pymoo: g(x) <= 0, so we use (h1 - h2)^2 - tolerance <= 0
        This is better than abs(h1-h2) for differentiability.
        """
        result = []
        tolerance = 0.5  # Allow tiles to differ by ~1 unit

        # Height equality: tiles on same row
        for tile_name in self.tile_row_set:
            on_rows = self.tile_row_set[tile_name]
            tile_idx = self.tile_to_solution_index[tile_name]
            tile_h = x[tile_idx.height_idx]

            for other_name in self.tile_row_set:
                if other_name == tile_name:  # Skip self-comparison only
                    continue
                other_tile = self.fabric.tileDic[other_name]
                other_rows = self.tile_row_set[other_name]
                if len(on_rows & other_rows) > 0:
                    other_idx = self.tile_to_solution_index[other_name]
                    other_h = x[other_idx.height_idx]
                    # Use squared difference for differentiability
                    result.append((tile_h - other_h) ** 2 - tolerance)

        # Width equality: tiles on same column
        for tile_name in self.tile_column_set:
            on_cols = self.tile_column_set[tile_name]
            tile_idx = self.tile_to_solution_index[tile_name]
            tile_w = x[tile_idx.width_idx]

            for other_name in self.tile_column_set:
                if other_name == tile_name:  # Skip self-comparison only
                    continue
                other_tile = self.fabric.tileDic[other_name]
                if other_tile.partOfSuperTile:
                    continue
                other_cols = self.tile_column_set[other_name]
                if len(on_cols & other_cols) > 0:
                    other_idx = self.tile_to_solution_index[other_name]
                    other_w = x[other_idx.width_idx]
                    result.append((tile_w - other_w) ** 2 - tolerance)

        return result

    def _add_mode_constraints(self, x: np.ndarray) -> list:
        """Add mode constraints on tile dimensions.

        For regular tiles: w * h >= mode_die_area for at least one mode
        For supertiles: sum(component_widths) * sum(component_heights) >= mode_die_area
                        for at least one mode
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
                    x0, y0, x1, y1 = mode_metrics[tile.name]["design__die__bbox"]
                    mode_die_area = (x1 - x0) * (y1 - y0)
                    # Constraint: mode_die_area - tile_w * tile_h <= 0  # noqa: ERA001
                    mode_constraints.append(mode_die_area - tile_w * tile_h)
            result.append(min(mode_constraints))

        # Supertiles
        for supertile in self.fabric.superTileDic.values():
            # Sum component tile dimensions from first row (width) and
            # first column (height)
            # Width is sum of widths in the first row
            total_w = 0.0
            if supertile.tileMap and len(supertile.tileMap) > 0:
                for tile in supertile.tileMap[0]:  # First row
                    if tile is not None:
                        sub_idx = self.tile_to_solution_index[tile.name]
                        total_w += x[sub_idx.width_idx]

            # Height is sum of heights in the first column
            total_h = 0.0
            for row in supertile.tileMap:
                if row and len(row) > 0 and row[0] is not None:  # First column
                    sub_idx = self.tile_to_solution_index[row[0].name]
                    total_h += x[sub_idx.height_idx]

            # Collect all modes for this supertile
            mode_constraints = []
            for mode_metrics in self.tile_metrics.values():
                if supertile.name in mode_metrics:
                    x0, y0, x1, y1 = mode_metrics[supertile.name]["design__die__bbox"]
                    mode_die_area = (x1 - x0) * (y1 - y0)
                    # Constraint: mode_die_area - total_w * total_h <= 0  # noqa: ERA001
                    mode_constraints.append(mode_die_area - total_w * total_h)
            result.append(min(mode_constraints))

        return result


@Step.factory.register()
class GlobalTileSizeOptimization(Step):
    """LibreLane step for solving NLP optimization to find optimal tile dimensions.

    This step formulates and solves a Non-Linear Program using pymoo to minimize total
    fabric area subject to minimum area constraints (bilinear w*h >= A_min), row/column
    grid constraints, and SuperTile boundary constraints.

    After optimization, it automatically recompiles all tiles with the optimal
    dimensions and stores the recompiled states in metrics for downstream processing.
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
            "FABULOUS_NLP_FTOL_TOLERANCE",
            float,
            description="Function tolerance for NLP optimizer - "
            "stops when objective change is below this value",
            default=1e-6,
        ),
    ]

    inputs = []
    outputs = [
        DesignFormat.GDS,
        DesignFormat.LEF,
        DesignFormat.LIB,
        DesignFormat.DEF,
    ]

    def run(self, state_in: State, **_kwargs: str) -> tuple[ViewsUpdate, MetricsUpdate]:
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
        print(self.config)

        if self.config["TILE_OPT_INFO"] is None:
            raise FlowException(
                "Values of TILE_OPT_INFO should have been set when calling this step."
            )
        # Get fabric configuration
        fabric: Fabric = self.config["FABULOUS_FABRIC"]
        tolerance = self.config.get("FABULOUS_NLP_FTOL_TOLERANCE", 10.0)
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
        # Create pymoo problem - constructor handles all the formatting
        problem = NLPTileProblem(
            fabric,
            tile_opt_data,
        )

        x_pitch = Decimal(state_in.metrics.get("pdk__site_width", 0.5))
        y_pitch = Decimal(state_in.metrics.get("pdk__site_height", 0.5))

        # Solve with ISRES - specifically designed for constrained optimization
        class RoundRepair(Repair):
            def _do(self, problem, X: np.ndarray, **kwargs) -> np.ndarray:
                """Solution repair to round to nearest grid pitch."""
                for j in range(X.shape[0]):
                    for i in range(X.shape[1]):
                        if i % 2 == 0:
                            X[j][i] = float(round_up_decimal(Decimal(X[j][i]), y_pitch))
                        else:
                            X[j][i] = float(round_up_decimal(Decimal(X[j][i]), x_pitch))
                return X

        algorithm = ISRES(repair=RoundRepair())

        info("Running optimization with function tolerance termination")

        # Combine: stop when objective stops changing (ftol) OR feasible solution found
        # OR max 50000 generations
        ftol_termination = SingleObjectiveSpaceTermination(tol=tolerance)
        max_gen_termination = MaximumGenerationTermination(50000)
        termination = TerminateIfAny(ftol_termination, max_gen_termination)

        res = minimize(problem, algorithm, termination, verbose=True)

        # Check if we have a valid solution
        # Try to get best solution even if infeasible
        if res.X is None:
            # Check if there's a population with solutions
            if hasattr(res, "pop") and res.pop is not None and len(res.pop) > 0:
                info("No single best solution found, using best from population")
                # Sort population by constraint violation, then by objective
                pop_sorted = sorted(
                    res.pop,
                    key=lambda ind: (
                        ind.CV[0]
                        if hasattr(ind, "CV") and ind.CV is not None
                        else float("inf"),
                        ind.F[0],
                    ),
                )
                best_ind = pop_sorted[0]
                res.X = best_ind.X
                res.F = best_ind.F
                res.CV = best_ind.CV if hasattr(best_ind, "CV") else None
            else:
                raise RuntimeError("NLP optimization failed to find any solution")

        # Check constraint violation
        if hasattr(res, "CV") and res.CV is not None:
            if res.CV[0] > 1e-6:
                warn(f"Solution has constraint violation of {res.CV[0]}")
            else:
                info(f"Found feasible solution with CV={res.CV[0]}")
        else:
            info("Found solution (constraint violation not available)")

        info(f"Optimization terminated with objective={res.F[0]}")

        # Extract results

        result_dict = {}
        for tile_name, indices in problem.tile_to_solution_index.items():
            w = res.X[indices.width_idx]
            h = res.X[indices.height_idx]
            if fabric.tileDic[tile_name].partOfSuperTile:
                # Skip component tiles of supertiles
                continue
            result_dict[tile_name] = (
                Decimal(0),
                Decimal(0),
                Decimal(w).quantize(Decimal(".01")),
                Decimal(h).quantize(Decimal(".01")),
            )

        for supertile in fabric.superTileDic.values():
            # Sum component tile dimensions from first row (width) and first column (height)
            # Width is sum of widths in the first row
            total_w = 0.0
            if supertile.tileMap and len(supertile.tileMap) > 0:
                for tile in supertile.tileMap[0]:  # First row
                    if tile is not None:
                        sub_idx = problem.tile_to_solution_index[tile.name]
                        total_w += res.X[sub_idx.width_idx]

            # Height is sum of heights in the first column
            total_h = 0.0
            for row in supertile.tileMap:
                if row and len(row) > 0 and row[0] is not None:  # First column
                    sub_idx = problem.tile_to_solution_index[row[0].name]
                    total_h += res.X[sub_idx.height_idx]

            result_dict[supertile.name] = (
                Decimal(0),
                Decimal(0),
                Decimal(total_w).quantize(Decimal(".01")),
                Decimal(total_h).quantize(Decimal(".01")),
            )

        # Calculate total area
        total_area = int(res.F[0])

        # Report results
        info(f"  Total fabric area: {total_area}")
        info(f"  Optimal tile dimensions: {result_dict}")

        metrics_updates = {
            "nlp__tile__area": result_dict,
            "nlp__total__area": total_area,
        }

        return {}, metrics_updates

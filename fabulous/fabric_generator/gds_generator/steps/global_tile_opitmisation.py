"""FABulous GDS Generator - NLP Optimization Step using pymoo."""

import json
from collections import defaultdict
from decimal import Decimal
from pathlib import Path
from typing import Any, Optional

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
from pymoo.optimize import minimize
from pymoo.termination.max_gen import MaximumGenerationTermination

from fabulous.fabric_definition.fabric import Fabric
from fabulous.fabric_generator.gds_generator.helper import round_up_decimal
from fabulous.fabric_generator.gds_generator.steps.tile_optimisation import OptMode


class NLPTileProblem(ElementwiseProblem):
    """NLP problem for tile size optimization using row/column variables.

    Variables are row heights h[r] and column widths w[c], so that uniformity within
    each row and column is inherent in the formulation rather than enforced through soft
    equality constraints.

    Rows that share a tile type are linked into equivalence classes so they get a single
    shared height variable. Columns are linked similarly.

    Parameters
    ----------
    fabric : Fabric
        The fabric whose tiles are being sized.
    tile_metrics : dict[OptMode, dict]
        Per-mode compilation metrics for tiles that compiled successfully.
    all_tile_metrics : dict[OptMode, dict] | None, optional
        Metrics including failed explorations, used for lower-bound
        estimates. Falls back to *tile_metrics* when ``None``.
    area_margin : float, optional
        Fractional margin added to standard-cell area constraints,
        by default 0.05 (5 %).

    Raises
    ------
    RuntimeError
        If any tile/supertile failed all exploration modes and has no successful
        compilation, since the NLP cannot determine feasible dimensions without at least
        one working compilation per tile.
    """

    def __init__(
        self,
        fabric: Fabric,
        tile_metrics: dict[OptMode, dict],
        all_tile_metrics: dict[OptMode, dict] | None = None,
        area_margin: float = 0.05,
    ) -> None:
        self.fabric = fabric
        self.tile_metrics = tile_metrics
        self.area_margin = area_margin
        # all_tile_metrics includes failed explorations for lower bounds
        self._all_tile_metrics = all_tile_metrics or tile_metrics

        self.tile_row_set: dict[str, set[int]] = defaultdict(set)
        self.tile_column_set: dict[str, set[int]] = defaultdict(set)
        self.position_map: dict[tuple[int, int], str] = {}

        for (x, y), tile in fabric:
            if tile is None:
                continue
            self.tile_row_set[tile.name].add(y)
            self.tile_column_set[tile.name].add(x)
            self.position_map[(x, y)] = tile.name

        # Rows sharing a tile type must have the same height, and likewise
        # for columns. Union-find groups enforce this.
        self.row_groups: dict[int, int] = {}
        self._compute_equivalence_classes(self.tile_row_set, self.row_groups)

        self.col_groups: dict[int, int] = {}
        self._compute_equivalence_classes(self.tile_column_set, self.col_groups)

        unique_row_groups = sorted(set(self.row_groups.values()))
        unique_col_groups = sorted(set(self.col_groups.values()))
        self.row_group_to_var: dict[int, int] = {
            g: i for i, g in enumerate(unique_row_groups)
        }
        n_row_vars = len(unique_row_groups)
        self.col_group_to_var: dict[int, int] = {
            g: n_row_vars + i for i, g in enumerate(unique_col_groups)
        }
        n_vars = n_row_vars + len(unique_col_groups)

        info(
            f"NLP variables: {n_row_vars} row groups, "
            f"{len(unique_col_groups)} column groups = {n_vars} total"
        )

        # Combine IO-pin floor with the smallest observed bbox across
        # successful exploration modes.
        def _combined_min(name: str) -> tuple[float, float]:
            """Return (w, h) floor combining IO-pin and observed bbox minima."""
            pin_w, pin_h = self._pin_min_from_metrics(name)
            obs_w, obs_h = self._min_dimensions_from_metrics(name)
            return (max(pin_w, obs_w), max(pin_h, obs_h))

        tile_min: dict[str, tuple[float, float]] = {}
        for tile in fabric.tileDic.values():
            if tile.partOfSuperTile:
                continue
            tile_min[tile.name] = _combined_min(tile.name)

        # SuperTile components derive bounds from the SuperTile minimum
        # and from row/column neighbors
        for supertile in fabric.superTileDic.values():
            st_min_w, st_min_h = _combined_min(supertile.name)
            first_row = supertile.tileMap[0] if supertile.tileMap else []
            n_cols = sum(1 for t in first_row if t is not None)
            n_rows = sum(
                1
                for row in supertile.tileMap
                if row and any(t is not None for t in row)
            )
            if n_cols == 0 or n_rows == 0:
                continue

            # Ensure all component tiles have an entry before updating
            for row in supertile.tileMap:
                for component_tile in row:
                    if component_tile is not None:
                        tile_min.setdefault(component_tile.name, (1.0, 1.0))

            # Update height bounds from row neighbors
            for row in supertile.tileMap:
                for component_tile in row:
                    if component_tile is None:
                        continue
                    name = component_tile.name
                    neighbors = self._find_sharing_tiles(name, self.tile_row_set)
                    neighbor_h = max(
                        (tile_min[n][1] for n in neighbors if n in tile_min),
                        default=1.0,
                    )
                    cur_w, _ = tile_min[name]
                    tile_min[name] = (cur_w, max(neighbor_h, st_min_h / n_rows))

            # Update width bounds from column neighbors
            for col_idx in range(supertile.max_width):
                for row in supertile.tileMap:
                    if col_idx >= len(row) or row[col_idx] is None:
                        continue
                    name = row[col_idx].name
                    neighbors = self._find_sharing_tiles(name, self.tile_column_set)
                    neighbor_w = max(
                        (tile_min[n][0] for n in neighbors if n in tile_min),
                        default=1.0,
                    )
                    _, cur_h = tile_min[name]
                    tile_min[name] = (max(neighbor_w, st_min_w / n_cols), cur_h)

        xl = np.zeros(n_vars)

        for tile_name, (min_w, min_h) in tile_min.items():
            for row_idx in self.tile_row_set[tile_name]:
                var_idx = self.row_group_to_var[self.row_groups[row_idx]]
                xl[var_idx] = max(xl[var_idx], min_h)
            for col_idx in self.tile_column_set[tile_name]:
                var_idx = self.col_group_to_var[self.col_groups[col_idx]]
                xl[var_idx] = max(xl[var_idx], min_w)

        # Aggregate per-tile min compilable area, stdcell area (for util
        # reporting), and DRC-clean (w, h) samples (for feasibility envelope).
        self.min_areas: dict[str, float] = {}
        self.stdcell_areas: dict[str, float] = {}
        self.tile_samples: dict[str, list[tuple[float, float]]] = {}
        for tile in fabric.get_all_unique_tiles():
            name = tile.name
            areas: list[float] = []
            raw_samples: list[tuple[float, float]] = []
            for mode_metrics in self.tile_metrics.values():
                m = mode_metrics.get(name)
                if m is None:
                    continue
                # Terminal bbox plus every mid-run DRC-clean sample
                bboxes = [m["design__die__bbox"], *m.get("fabulous__clean_probes", [])]
                for x0, y0, x1, y1 in bboxes:
                    w, h = x1 - x0, y1 - y0
                    areas.append(w * h)
                    raw_samples.append((w, h))

            self.min_areas[name] = min(areas) if areas else float("inf")
            self.tile_samples[name] = self._pareto_frontier(raw_samples)

            stdcell_vals = [
                a
                for mode_metrics in self._all_tile_metrics.values()
                if name in mode_metrics
                for a in [mode_metrics[name].get("design__instance__area__stdcell")]
                if a is not None
            ]
            self.stdcell_areas[name] = max(stdcell_vals) if stdcell_vals else 0.0

        for tile in fabric.get_all_unique_tiles():
            samples = self.tile_samples.get(tile.name, [])
            if not samples:
                continue

            is_supertile = tile.name in self.fabric.superTileDic
            if is_supertile:
                supertile = self.fabric.superTileDic[tile.name]
                first_row = supertile.tileMap[0] if supertile.tileMap else []
                n_cols = sum(1 for t in first_row if t is not None)
                n_rows = sum(
                    1
                    for row in supertile.tileMap
                    if row and any(t is not None for t in row)
                )
                if n_cols == 0 or n_rows == 0:
                    continue
            else:
                if len(samples) != 1:
                    continue
                n_cols, n_rows = 1, 1

            target_aspect = n_cols / n_rows  # w/h for square cells
            best = min(
                samples,
                key=lambda s: (
                    abs((s[0] / s[1]) - target_aspect) if s[1] > 0 else float("inf")
                ),
            )
            sample_w, sample_h = best

            if is_supertile:
                per_row_h = sample_h / n_rows
                per_col_w = sample_w / n_cols
                for row in supertile.tileMap:
                    for component in row:
                        if component is None:
                            continue
                        for row_idx in self.tile_row_set[component.name]:
                            vi = self.row_group_to_var[self.row_groups[row_idx]]
                            xl[vi] = max(xl[vi], per_row_h)
                        for col_idx in self.tile_column_set[component.name]:
                            vi = self.col_group_to_var[self.col_groups[col_idx]]
                            xl[vi] = max(xl[vi], per_col_w)
            else:
                for row_idx in self.tile_row_set[tile.name]:
                    var_idx = self.row_group_to_var[self.row_groups[row_idx]]
                    xl[var_idx] = max(xl[var_idx], sample_h)
                for col_idx in self.tile_column_set[tile.name]:
                    var_idx = self.col_group_to_var[self.col_groups[col_idx]]
                    xl[var_idx] = max(xl[var_idx], sample_w)

        # Fail fast if any tile/supertile failed every exploration mode.
        valid_names = {
            n for mode_metrics in self.tile_metrics.values() for n in mode_metrics
        }
        missing = [
            t.name
            for t in self.fabric.get_all_unique_tiles()
            if t.name not in valid_names
        ]
        if missing:
            raise RuntimeError(
                f"Tile(s) {missing} failed all exploration modes and have no "
                f"successful compilation. The NLP cannot determine feasible "
                f"dimensions without at least one working compilation per tile."
            )

        xu = xl * 3.0  # upper bound safety floor
        for tile in fabric.tileDic.values():
            if tile.partOfSuperTile:
                continue
            required = self.min_areas.get(tile.name, 0.0) * (1.0 + self.area_margin)
            if required <= 0:
                continue
            row_vars = {
                self.row_group_to_var[self.row_groups[r]]
                for r in self.tile_row_set[tile.name]
            }
            col_vars = {
                self.col_group_to_var[self.col_groups[c]]
                for c in self.tile_column_set[tile.name]
            }
            for rv in row_vars:
                for cv in col_vars:
                    if xl[cv] > 0:
                        xu[rv] = max(xu[rv], required / xl[cv])
                    if xl[rv] > 0:
                        xu[cv] = max(xu[cv], required / xl[rv])

        # Additional safety: allow each variable to reach at least 2x the
        # largest bbox observed during exploration for any tile it serves.
        for tile in fabric.get_all_unique_tiles():
            max_w = 0.0
            max_h = 0.0
            for mode_metrics in self._all_tile_metrics.values():
                if tile.name not in mode_metrics:
                    continue
                x0, y0, x1, y1 = mode_metrics[tile.name]["design__die__bbox"]
                max_w = max(max_w, x1 - x0)
                max_h = max(max_h, y1 - y0)
            if max_w == 0.0 and max_h == 0.0:
                continue
            for r in self.tile_row_set[tile.name]:
                var = self.row_group_to_var[self.row_groups[r]]
                xu[var] = max(xu[var], 2.0 * max_h)
            for c in self.tile_column_set[tile.name]:
                var = self.col_group_to_var[self.col_groups[c]]
                xu[var] = max(xu[var], 2.0 * max_w)

        # One representative (col, row) per tile type; all positions in the
        # same row/col group share identical dimensions.
        tile_constraints: list[tuple[str, int, int]] = []
        for tile in fabric.tileDic.values():
            if tile.partOfSuperTile:
                continue
            rows = self.tile_row_set[tile.name]
            cols = self.tile_column_set[tile.name]
            if rows and cols:
                tile_constraints.append((tile.name, min(cols), min(rows)))

        supertile_constraints: list[tuple[str, list[int], list[int]]] = []
        for supertile in fabric.superTileDic.values():
            st_cols = [
                min(self.tile_column_set[tile.name])
                for tile in (supertile.tileMap[0] if supertile.tileMap else [])
                if tile is not None
            ]
            st_rows: list[int] = []
            for row in supertile.tileMap:
                first_tile = (
                    next((t for t in row if t is not None), None) if row else None
                )
                if first_tile is not None:
                    st_rows.append(min(self.tile_row_set[first_tile.name]))
            supertile_constraints.append((supertile.name, st_cols, st_rows))

        # Precompute resolved variable indices and required areas for the hot
        # evaluation path.
        margin = 1.0 + self.area_margin
        self._tile_eval: list[tuple[int, int, float]] = [
            (
                self.col_group_to_var[self.col_groups[col]],
                self.row_group_to_var[self.row_groups[row]],
                self.min_areas.get(name, float("inf")) * margin,
            )
            for name, col, row in tile_constraints
        ]
        self._supertile_eval: list[tuple[list[int], list[int], float]] = [
            (
                [self.col_group_to_var[self.col_groups[c]] for c in st_cols],
                [self.row_group_to_var[self.row_groups[r]] for r in st_rows],
                self.min_areas.get(name, float("inf")) * margin,
            )
            for name, st_cols, st_rows in supertile_constraints
        ]
        # Envelope constraints need ≥2 DRC-clean samples to interpolate; with
        # one sample the existing per-axis xl already encodes the same floor.
        self._envelope_eval: list[tuple[int, int, list[tuple[float, float]]]] = [
            (
                self.col_group_to_var[self.col_groups[col]],
                self.row_group_to_var[self.row_groups[row]],
                self.tile_samples[name],
            )
            for name, col, row in tile_constraints
            if len(self.tile_samples.get(name, [])) >= 2
        ]
        self._position_var_pairs: list[tuple[int, int]] = [
            (
                self.col_group_to_var[self.col_groups[col]],
                self.row_group_to_var[self.row_groups[row]],
            )
            for col, row in self.position_map
        ]
        n_constr = (
            len(self._tile_eval) + len(self._supertile_eval) + len(self._envelope_eval)
        )

        info(
            f"NLP constraints: {len(self._tile_eval)} area + "
            f"{len(self._supertile_eval)} supertile area + "
            f"{len(self._envelope_eval)} envelope = {n_constr}"
        )

        super().__init__(
            n_var=n_vars,
            n_obj=1,
            n_ieq_constr=n_constr,
            xl=xl,
            xu=xu,
        )

    @staticmethod
    def _compute_equivalence_classes(
        tile_positions: dict[str, set[int]],
        groups: dict[int, int],
    ) -> None:
        """Compute equivalence classes for rows or columns.

        Two indices must be in the same group if any tile type appears in both. Uses
        union-find logic to compute transitive closure.
        """
        parent: dict[int, int] = {}

        def find(x: int) -> int:
            """Return the root representative of *x* with path compression."""
            while parent.get(x, x) != x:
                parent[x] = parent.get(parent[x], parent[x])
                x = parent[x]
            return x

        def union(a: int, b: int) -> None:
            """Merge the sets containing *a* and *b*."""
            ra, rb = find(a), find(b)
            if ra != rb:
                parent[ra] = rb

        all_indices: set[int] = set()
        for indices in tile_positions.values():
            all_indices |= indices

        for idx in all_indices:
            parent[idx] = idx

        for indices in tile_positions.values():
            idx_list = sorted(indices)
            for i in range(1, len(idx_list)):
                union(idx_list[0], idx_list[i])

        for idx in all_indices:
            groups[idx] = find(idx)

    def _min_dimensions_from_metrics(self, name: str) -> tuple[float, float]:
        """Return (min_width, min_height) across all compilation modes.

        The minimum width and height may come from different modes. Falls back to 1.0 if
        no metrics exist for the given tile.
        """
        widths: list[float] = []
        heights: list[float] = []
        for mode_metrics in self._all_tile_metrics.values():
            if name not in mode_metrics:
                continue
            x0, y0, x1, y1 = mode_metrics[name]["design__die__bbox"]
            widths.append(x1 - x0)
            heights.append(y1 - y0)
        return (
            min(widths) if widths else 1.0,
            min(heights) if heights else 1.0,
        )

    def _pin_min_from_metrics(self, name: str) -> tuple[float, float]:
        """Return (pin_min_width, pin_min_height) from any mode's metrics.

        Pin minimums are IO-density-based dimension floors and are identical across
        exploration modes. Falls back to exploration bbox minimums if pin_min fields are
        absent (pre-patch JSON).
        """
        for mode_metrics in self._all_tile_metrics.values():
            if name not in mode_metrics:
                continue
            m = mode_metrics[name]
            w = m.get("fabulous__pin_min_width")
            h = m.get("fabulous__pin_min_height")
            if w is not None and h is not None:
                return (w, h)
        return self._min_dimensions_from_metrics(name)

    @staticmethod
    def _pareto_frontier(
        samples: list[tuple[float, float]],
    ) -> list[tuple[float, float]]:
        """Return the (w, h) Pareto frontier where smaller is better on both axes.

        A sample is kept iff no other sample has both smaller-or-equal w AND smaller-or-
        equal h with at least one strictly smaller. The result is sorted by h ascending
        (and by construction, w descending).

        This preserves wider+shorter samples alongside narrower+taller ones so the
        supertile aspect-target selector and the piecewise envelope constraint see the
        full feasible front rather than a single extreme.
        """
        sorted_samples = sorted(samples, key=lambda wh: (wh[1], wh[0]))
        frontier: list[tuple[float, float]] = []
        min_w_so_far = float("inf")
        for w, h in sorted_samples:
            if w < min_w_so_far:
                frontier.append((w, h))
                min_w_so_far = w
        return frontier

    @staticmethod
    def _envelope_w_floor(h: float, samples: list[tuple[float, float]]) -> float:
        """Piecewise-linear lower bound on w given h, from samples sorted by h.

        Outside the sampled h range the envelope clamps to the nearest sample's w (i.e.,
        below the shortest sample, use its width; above the tallest, use its width).
        Inside the range, linearly interpolate between adjacent samples. The Pareto
        property (w decreases as h increases for feasible tiles) makes this a convex
        lower bound.
        """
        if not samples:
            return 0.0
        if h <= samples[0][1]:
            return samples[0][0]
        if h >= samples[-1][1]:
            return samples[-1][0]
        for i in range(len(samples) - 1):
            w1, h1 = samples[i]
            w2, h2 = samples[i + 1]
            if h1 <= h <= h2:
                if h2 == h1:
                    return max(w1, w2)
                return w1 + (w2 - w1) * (h - h1) / (h2 - h1)
        return samples[-1][0]

    @staticmethod
    def _find_sharing_tiles(
        tile_name: str,
        tile_positions: dict[str, set[int]],
    ) -> set[str]:
        """Find tiles sharing at least one row or column with the given tile."""
        positions = tile_positions[tile_name]
        return {
            other
            for other, other_pos in tile_positions.items()
            if other != tile_name and positions & other_pos
        }

    def get_row_height(self, x: np.ndarray, row_idx: int) -> float:
        """Get the height variable for a given row index."""
        return x[self.row_group_to_var[self.row_groups[row_idx]]]

    def get_col_width(self, x: np.ndarray, col_idx: int) -> float:
        """Get the width variable for a given column index."""
        return x[self.col_group_to_var[self.col_groups[col_idx]]]

    def _evaluate(self, x: np.ndarray, out: dict) -> None:
        """Pymoo evaluation: compute objective (total fabric area) and constraints.

        Constraints cover: per-tile and per-supertile minimum compilable area (with
        margin), and the piecewise-linear Pareto envelope for tiles with ≥2 DRC-clean
        samples, so the solver cannot pick an untested aspect ratio below the observed
        width floor at its chosen row height.
        """
        total_area = 0.0
        for cv, rv in self._position_var_pairs:
            total_area += x[cv] * x[rv]
        out["F"] = total_area

        result: list[float] = []
        for cv, rv, required in self._tile_eval:
            result.append(required - x[cv] * x[rv])
        for cvs, rvs, required in self._supertile_eval:
            total_w = sum(x[c] for c in cvs)
            total_h = sum(x[r] for r in rvs)
            result.append(required - total_w * total_h)
        for cv, rv, samples in self._envelope_eval:
            result.append(self._envelope_w_floor(x[rv], samples) - x[cv])
        out["G"] = np.array(result, dtype=float)


@Step.factory.register()
class GlobalTileSizeOptimization(Step):
    """LibreLane step for NLP optimization of tile dimensions.

    Formulates and solves a Non-Linear Program using pymoo to minimize total fabric
    area. Variables are row heights and column widths, ensuring uniformity within each
    row/column by construction.
    """

    id = "FABulous.GlobalTileSizeOptimization"
    name = "FABulous Global Tile Size Optimization"

    config_vars = [
        Variable(
            "TILE_OPT_INFO",
            Optional[Path],  # noqa: UP045 librelane issue
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
    ]

    inputs = []
    outputs = [
        DesignFormat.GDS,
        DesignFormat.LEF,
        DesignFormat.LIB,
        DesignFormat.DEF,
    ]

    @staticmethod
    def _parse_tile_fields(data: dict) -> dict[str, Any]:
        """Parse tile metric fields from JSON data.

        Parses bbox strings into float lists and extracts optional scalar
        fields (pin minimums) when present.

        Parameters
        ----------
        data : dict
            Raw metric fields for a tile from the JSON file, including required
            bbox fields and optional pin minimums.

        Return
        ------
        dict[str, Any]
             Parsed fields including:
             - "design__die__bbox": [x0, y0, x1, y1]
             - "design__core__bbox": [x0, y0, x1, y1]
             - Optional scalar fields like "fabulous__pin_min_width"

        Raises
        ------
        TypeError
            If a required bbox field is not a string.
        """
        for required in ("design__die__bbox", "design__core__bbox"):
            val = data.get(required)
            if val is None or not isinstance(val, str):
                raise TypeError(
                    f"Required metric '{required}' is missing or not "
                    f"a string (got {val!r}). The tile may have "
                    f"failed compilation."
                )

        result: dict[str, Any] = {
            "design__die__bbox": [float(v) for v in data["design__die__bbox"].split()],
            "design__core__bbox": [
                float(v) for v in data["design__core__bbox"].split()
            ],
        }
        for key in (
            "fabulous__pin_min_width",
            "fabulous__pin_min_height",
            "design__instance__area__stdcell",
        ):
            if data.get(key) is not None:
                result[key] = float(data[key])
        probes_raw = data.get("fabulous__clean_probes")
        if probes_raw:
            result["fabulous__clean_probes"] = [
                [float(v) for v in bbox] for bbox in probes_raw
            ]
        return result

    @classmethod
    def _load_tile_metrics_from_json(
        cls,
        path: Path,
    ) -> tuple[dict[OptMode, dict], dict[OptMode, dict]]:
        """Load tile metrics from a JSON file.

        Returns two dicts: (valid_metrics, all_metrics).
        valid_metrics excludes tiles whose exploration never found a
        working state (used for feasibility constraints).
        all_metrics includes everything with a bbox (used for lower bounds).
        """
        tile_data_raw = json.loads(path.resolve().read_text())
        valid_data: dict[OptMode, dict] = {}
        all_data: dict[OptMode, dict] = {}

        for mode, tile_info in tile_data_raw.items():
            valid_dict: dict[str, dict[str, Any]] = {}
            all_dict: dict[str, dict[str, Any]] = {}

            for tile_name, data in tile_info.items():
                if not data.get("design__die__bbox"):
                    if "error" in data:
                        warn(
                            f"Tile {tile_name} in mode {mode} has error "
                            f"and no bbox: {data['error']}"
                        )
                    continue

                parsed = cls._parse_tile_fields(data)
                all_dict[tile_name] = parsed

                if "No working state found" in data.get("error_traceback", ""):
                    warn(
                        f"Tile {tile_name} in mode {mode} never compiled "
                        f"successfully, excluding from constraints"
                    )
                else:
                    valid_dict[tile_name] = parsed

            valid_data[OptMode(mode)] = valid_dict
            all_data[OptMode(mode)] = all_dict

        return valid_data, all_data

    def run(self, state_in: State, **_kwargs: str) -> tuple[ViewsUpdate, MetricsUpdate]:
        """Solve NLP problem for optimal tile dimensions."""
        info("Formulating NLP problem using pymoo...")
        if self.config["TILE_OPT_INFO"] is None:
            raise FlowException(
                "Values of TILE_OPT_INFO should have been set when calling this step."
            )
        fabric: Fabric = self.config["FABULOUS_FABRIC"]

        if isinstance(self.config["TILE_OPT_INFO"], Path):
            valid_metrics, all_metrics = self._load_tile_metrics_from_json(
                self.config["TILE_OPT_INFO"]
            )
        else:
            valid_metrics = self.config["TILE_OPT_INFO"]
            all_metrics = valid_metrics

        area_margin = self.config.get("FABULOUS_NLP_AREA_MARGIN", 0.0)
        info(f"Using area margin: {area_margin:.1%}")
        problem = NLPTileProblem(
            fabric, valid_metrics, all_metrics, area_margin=area_margin
        )

        x_pitch = Decimal(state_in.metrics.get("pdk__site_width", 0.5))
        y_pitch = Decimal(state_in.metrics.get("pdk__site_height", 0.5))

        n_row_vars = len(set(problem.row_groups.values()))

        class RoundRepair(Repair):
            def _do(self, _problem: Any, X: np.ndarray, **_kwargs: Any) -> np.ndarray:  # noqa: ANN401
                """Round variables to nearest grid pitch."""
                for j in range(X.shape[0]):
                    for i in range(X.shape[1]):
                        if i < n_row_vars:  # row height variables
                            X[j][i] = float(round_up_decimal(Decimal(X[j][i]), y_pitch))
                        else:  # column width variables
                            X[j][i] = float(round_up_decimal(Decimal(X[j][i]), x_pitch))
                return X

        algorithm = ISRES(repair=RoundRepair())

        n_gen = 500
        info(f"Running optimization for {n_gen} generations")
        termination = MaximumGenerationTermination(n_gen)

        res = minimize(problem, algorithm, termination, verbose=True)

        if res.X is None:
            if hasattr(res, "pop") and res.pop is not None and len(res.pop) > 0:
                info("No single best solution found, using best from population")
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

        if hasattr(res, "CV") and res.CV is not None:
            if res.CV[0] > 1e-6:
                warn(f"Solution has constraint violation of {res.CV[0]}")
            else:
                info(f"Found feasible solution with CV={res.CV[0]}")
        else:
            info("Found solution (constraint violation not available)")

        info(f"Optimization terminated with objective={res.F[0]}")

        quant = Decimal(".01")
        zero = Decimal(0)
        result_dict: dict[str, tuple[Decimal, ...]] = {}

        def quantized_width(tile_name: str) -> Decimal:
            """Return the NLP-optimal width for *tile_name*, quantized to 0.01."""
            col = min(problem.tile_column_set[tile_name])
            return Decimal(problem.get_col_width(res.X, col)).quantize(quant)

        def quantized_height(tile_name: str) -> Decimal:
            """Return the NLP-optimal height for *tile_name*, quantized to 0.01."""
            row = min(problem.tile_row_set[tile_name])
            return Decimal(problem.get_row_height(res.X, row)).quantize(quant)

        for tile in fabric.tileDic.values():
            if tile.partOfSuperTile:
                continue
            result_dict[tile.name] = (
                zero,
                zero,
                quantized_width(tile.name),
                quantized_height(tile.name),
            )

        for supertile in fabric.superTileDic.values():
            total_w = zero
            if supertile.tileMap:
                for tile in supertile.tileMap[0]:
                    if tile is not None:
                        total_w += quantized_width(tile.name)

            total_h = zero
            for row_tiles in supertile.tileMap:
                first_tile = (
                    next((t for t in row_tiles if t is not None), None)
                    if row_tiles
                    else None
                )
                if first_tile is not None:
                    total_h += quantized_height(first_tile.name)

            result_dict[supertile.name] = (zero, zero, total_w, total_h)

        total_area = int(res.F[0])
        info(f"  Total fabric area: {total_area}")
        info(f"  Optimal tile dimensions: {result_dict}")

        return {}, {
            "nlp__tile__area": result_dict,
            "nlp__total__area": total_area,
            "nlp__tile__min_area": problem.min_areas,
            "nlp__tile__stdcell_area": problem.stdcell_areas,
        }

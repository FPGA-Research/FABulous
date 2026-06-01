"""Benchmark-driven inverse router implementation."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from fabulous.fabric_cad.fabxplore.modules.inverse_router.core.models import (
    BenchmarkSource,
    InverseRouterOptions,
    InverseRouterPruneStats,
    InverseRouterResult,
    InverseRouterRouteResult,
)
from fabulous.fabric_cad.fabxplore.modules.inverse_router.core.process_tracker import (  # noqa: E501
    InverseRouterProcessTracker,
)
from fabulous.fabric_cad.fabxplore.modules.inverse_router.core.report import (
    render_inverse_router_report,
)
from fabulous.fabric_cad.fabxplore.pnr.fab_graph.core.models import (
    RoutingPipKind,
    RoutingResourceKey,
    RoutingSwitchMatrix,
)

if TYPE_CHECKING:
    from fabulous.fabric_cad.fabxplore.pnr.pnr_bridge import PnRBridge
    from fabulous.fabric_cad.fabxplore.utils.fabulous_fasm import (
        FabulousFasmDocument,
    )

MatrixKey = tuple[str, str]
ExternalTrackKey = tuple[RoutingResourceKey, int]


class InverseRouter:
    """Derive routing-resource scores from nextpnr FASM output.

    Parameters
    ----------
    options : InverseRouterOptions
        Normalized inverse-router options.
    """

    def __init__(self, options: InverseRouterOptions) -> None:
        self.options = options

    def run(self, fpga_model: PnRBridge) -> InverseRouterResult:
        """Run inverse routing on the active PnR bridge.

        Parameters
        ----------
        fpga_model : PnRBridge
            Combined design, FABulous API, and editable routing graph.

        Returns
        -------
        InverseRouterResult
            Structured score, pruning, validation, and report data.
        """
        tracker = InverseRouterProcessTracker(
            enabled=self.options.track_progress,
            chunk_size=self.options.progress_chunk_size,
        )
        tracker.start(self.options.tile_name)

        training_routes, documents = self._collect_training_documents(
            fpga_model,
            tracker,
        )
        matrix_score, final_matrix, matrix_stats = self._score_switch_matrix(
            fpga_model,
            documents,
            prune_enabled=self.options.optimize_switch_matrix,
        )
        external_scores, final_external, removed_external, external_stats = (
            self._score_external_tracks(
                fpga_model,
                documents,
                prune_enabled=self.options.optimize_external_pips,
            )
        )
        tracker.scoring(
            _active_cell_count(matrix_score) if matrix_score is not None else 0,
            len([score for score in external_scores.values() if score > 0]),
        )

        if self.options.optimize_switch_matrix and final_matrix is not None:
            fpga_model.set_switch_matrix(
                self.options.tile_name,
                final_matrix.columns,
                final_matrix.rows,
                final_matrix.matrix,
            )

        if self.options.optimize_external_pips:
            _remove_external_tracks(fpga_model, removed_external)

        tracker.applied(
            matrix_stats.removed_unused + matrix_stats.removed_used,
            len(removed_external),
        )

        training_validation_routes = (
            self._run_route_batches(
                fpga_model,
                self.options.training_benchmarks,
                phase="training_validation",
                tracker=tracker,
            )
            if self.options.validate_training
            else []
        )
        test_validation_routes = (
            self._run_route_batches(
                fpga_model,
                self.options.test_benchmarks,
                phase="test_validation",
                tracker=tracker,
            )
            if self.options.validate_test
            else []
        )

        result = InverseRouterResult(
            options=self.options,
            tile_name=self.options.tile_name,
            training_routes=training_routes,
            training_validation_routes=training_validation_routes,
            test_validation_routes=test_validation_routes,
            switch_matrix_score=matrix_score,
            final_switch_matrix=final_matrix,
            switch_matrix_stats=matrix_stats,
            external_scores=external_scores,
            final_external_pips=final_external,
            removed_external_pips=removed_external,
            external_stats=external_stats,
        )
        result = result.model_copy(
            update={"report_summary": render_inverse_router_report(result)}
        )
        tracker.finish(self.options.tile_name)
        return result

    def _collect_training_documents(
        self,
        fpga_model: PnRBridge,
        tracker: InverseRouterProcessTracker,
    ) -> tuple[list[InverseRouterRouteResult], list[FabulousFasmDocument]]:
        """Route training benchmarks and evaluate successful FASM outputs.

        Parameters
        ----------
        fpga_model : PnRBridge
            PnR bridge used for routing and FASM evaluation.
        tracker : InverseRouterProcessTracker
            Progress tracker.

        Returns
        -------
        tuple[list[InverseRouterRouteResult], list[FabulousFasmDocument]]
            Route summaries and successfully evaluated FASM documents.
        """
        route_records: list[InverseRouterRouteResult] = []
        documents: list[FabulousFasmDocument] = []
        for seed in self._seeds():
            tracker.batch("training", seed, len(self.options.training_benchmarks))
            batch_results = self._route_batch(
                fpga_model,
                self.options.training_benchmarks,
                seed=seed,
            )
            for benchmark_name, route_result, error in batch_results:
                record = _route_record(
                    benchmark_name,
                    seed,
                    "training",
                    route_result,
                    error,
                )
                fasm_text = getattr(route_result, "fasm_text", None)
                if record.passed and fasm_text:
                    try:
                        documents.append(fpga_model.evaluate_fasm(fasm_text))
                    except Exception as exc:  # noqa: BLE001
                        record = record.model_copy(update={"error": str(exc)})
                route_records.append(record)
                tracker.route("training", benchmark_name, record.passed)
        return route_records, documents

    def _run_route_batches(
        self,
        fpga_model: PnRBridge,
        benchmarks: dict[str, BenchmarkSource],
        *,
        phase: str,
        tracker: InverseRouterProcessTracker,
    ) -> list[InverseRouterRouteResult]:
        """Run route batches without collecting FASM documents.

        Parameters
        ----------
        fpga_model : PnRBridge
            PnR bridge used for routing.
        benchmarks : dict[str, BenchmarkSource]
            Benchmarks to route.
        phase : str
            Phase label stored in route records.
        tracker : InverseRouterProcessTracker
            Progress tracker.

        Returns
        -------
        list[InverseRouterRouteResult]
            Route records.
        """
        records: list[InverseRouterRouteResult] = []
        for seed in self._seeds():
            tracker.batch(phase, seed, len(benchmarks))
            for benchmark_name, route_result, error in self._route_batch(
                fpga_model,
                benchmarks,
                seed=seed,
            ):
                record = _route_record(
                    benchmark_name,
                    seed,
                    phase,
                    route_result,
                    error,
                )
                records.append(record)
                tracker.route(phase, benchmark_name, record.passed)
        return records

    def _route_batch(
        self,
        fpga_model: PnRBridge,
        benchmarks: dict[str, BenchmarkSource],
        *,
        seed: int,
    ) -> list[tuple[str, object | None, str | None]]:
        """Run nextpnr batch tests for one IO assignment seed.

        Parameters
        ----------
        fpga_model : PnRBridge
            PnR bridge used for routing.
        benchmarks : dict[str, BenchmarkSource]
            Benchmarks to route.
        seed : int
            Auto-PCF assignment seed.

        Returns
        -------
        list[tuple[str, object | None, str | None]]
            Benchmark name, raw route result if available, and non-fatal error.
        """
        if not benchmarks:
            return []
        try:
            route_results = fpga_model.nextpnr_batch_test(
                benchmarks,
                nextpnr_exec=self.options.nextpnr_exec,
                extra_args=self.options.extra_args,
                pcf_assignment_seed=seed,
                check=False,
                live_output=self.options.live_output,
            )
        except Exception as exc:  # noqa: BLE001
            return [(name, None, str(exc)) for name in benchmarks]
        return [
            (benchmark_name, route_result, None)
            for benchmark_name, route_result in zip(
                benchmarks,
                route_results,
                strict=False,
            )
        ]

    def _score_switch_matrix(
        self,
        fpga_model: PnRBridge,
        documents: list[FabulousFasmDocument],
        *,
        prune_enabled: bool,
    ) -> tuple[RoutingSwitchMatrix, RoutingSwitchMatrix, InverseRouterPruneStats]:
        """Build switch-matrix scores and final pruned matrix.

        Parameters
        ----------
        fpga_model : PnRBridge
            Graph that provides the starting switch matrix.
        documents : list[FabulousFasmDocument]
            Evaluated FASM documents from successful training routes.
        prune_enabled : bool
            Whether pruning ratios should select PIPs for removal.

        Returns
        -------
        tuple[RoutingSwitchMatrix, RoutingSwitchMatrix, InverseRouterPruneStats]
            Score matrix, final matrix, and pruning statistics.
        """
        initial_matrix = fpga_model.switch_matrix(self.options.tile_name)
        scores, original_values, row_order, column_order = _initial_matrix_scores(
            initial_matrix
        )
        for document in documents:
            used_matrix = document.used_switch_matrix_for_tile_type(
                self.options.tile_name,
                active_pip_value=1,
            )
            _accumulate_matrix_scores(
                used_matrix,
                scores=scores,
                original_values=original_values,
                row_order=row_order,
                column_order=column_order,
            )

        if prune_enabled:
            removed_keys, stats = _select_removed_keys(
                scores,
                remove_unused_ratio=self.options.switch_matrix_remove_unused_ratio,
                remove_used_ratio=self.options.switch_matrix_remove_used_ratio,
            )
        else:
            removed_keys, stats = _select_removed_keys(
                scores,
                remove_unused_ratio=0.0,
                remove_used_ratio=0.0,
            )
        score_matrix = _matrix_from_values(
            self.options.tile_name,
            scores,
            row_order,
            column_order,
            include_zero=True,
        )
        final_matrix = (
            _final_matrix(
                self.options.tile_name,
                scores,
                original_values,
                removed_keys,
                row_order,
                column_order,
                active_pip_value=self.options.switch_matrix_active_pip_value,
            )
            if prune_enabled
            else initial_matrix
        )
        return (score_matrix, final_matrix, stats)

    def _score_external_tracks(
        self,
        fpga_model: PnRBridge,
        documents: list[FabulousFasmDocument],
        *,
        prune_enabled: bool,
    ) -> tuple[
        dict[ExternalTrackKey, int],
        list[ExternalTrackKey],
        list[ExternalTrackKey],
        InverseRouterPruneStats,
    ]:
        """Build external track scores and final kept/removed lists.

        Parameters
        ----------
        fpga_model : PnRBridge
            Graph that provides active external resources.
        documents : list[FabulousFasmDocument]
            Evaluated FASM documents from successful training routes.
        prune_enabled : bool
            Whether pruning ratios should select tracks for removal.

        Returns
        -------
        dict[ExternalTrackKey, int]
            External scores keyed by tile-local ``(resource_key, track_index)``.
        list[ExternalTrackKey]
            External tracks kept after pruning.
        list[ExternalTrackKey]
            External tracks removed by pruning.
        InverseRouterPruneStats
            External track pruning statistics.
        """
        candidates = _external_track_candidates(fpga_model, self.options.tile_name)
        scores = {track: 0 for track in candidates}
        for document in documents:
            for track, score in document.used_external_track_scores_for_tile_type(
                self.options.tile_name
            ).items():
                candidates.setdefault(track, track)
                scores[track] = scores.get(track, 0) + score

        if prune_enabled:
            removed_tracks, stats = _select_removed_keys(
                scores,
                remove_unused_ratio=self.options.external_remove_unused_ratio,
                remove_used_ratio=self.options.external_remove_used_ratio,
            )
        else:
            removed_tracks, stats = _select_removed_keys(
                scores,
                remove_unused_ratio=0.0,
                remove_used_ratio=0.0,
            )
        removed = [track for track in candidates.values() if track in removed_tracks]
        kept = [track for track in candidates.values() if track not in removed_tracks]
        return (scores, kept, removed, stats)

    def _seeds(self) -> range:
        """Return the configured auto-PCF seed range.

        Returns
        -------
        range
            Seed values.
        """
        return range(
            self.options.io_seed_start,
            self.options.io_seed_start + self.options.io_seed_count,
        )


def _route_record(
    benchmark_name: str,
    seed: int,
    phase: str,
    route_result: object | None,
    error: str | None,
) -> InverseRouterRouteResult:
    """Build one route record from a raw router result.

    Parameters
    ----------
    benchmark_name : str
        Benchmark name.
    seed : int
        Auto-PCF assignment seed.
    phase : str
        Route phase.
    route_result : object | None
        Raw route result object.
    error : str | None
        Non-fatal routing error.

    Returns
    -------
    InverseRouterRouteResult
        Normalized route record.
    """
    return InverseRouterRouteResult(
        benchmark_name=benchmark_name,
        seed=seed,
        phase=phase,
        passed=bool(getattr(route_result, "passed", False)),
        fasm_available=bool(getattr(route_result, "fasm_text", None)),
        error=error,
    )


def _initial_matrix_scores(
    matrix: RoutingSwitchMatrix,
) -> tuple[dict[MatrixKey, int], dict[MatrixKey, float], list[str], list[str]]:
    """Initialize score maps from a starting switch matrix.

    Parameters
    ----------
    matrix : RoutingSwitchMatrix
        Starting graph switch matrix.

    Returns
    -------
    tuple[dict[MatrixKey, int], dict[MatrixKey, float], list[str], list[str]]
        Score map, original active values, row order, and column order.
    """
    scores: dict[MatrixKey, int] = {}
    original_values: dict[MatrixKey, float] = {}
    for row_index, row in enumerate(matrix.rows):
        for column_index, column in enumerate(matrix.columns):
            value = matrix.matrix[row_index][column_index]
            if value == 0:
                continue
            key = (row, column)
            scores[key] = 0
            original_values[key] = float(value)
    return (scores, original_values, list(matrix.rows), list(matrix.columns))


def _accumulate_matrix_scores(
    matrix: RoutingSwitchMatrix,
    *,
    scores: dict[MatrixKey, int],
    original_values: dict[MatrixKey, float],
    row_order: list[str],
    column_order: list[str],
) -> None:
    """Add one used switch matrix into score maps.

    Parameters
    ----------
    matrix : RoutingSwitchMatrix
        Used matrix from one evaluated FASM route.
    scores : dict[MatrixKey, int]
        Mutable score map.
    original_values : dict[MatrixKey, float]
        Mutable original/fallback matrix values.
    row_order : list[str]
        Mutable row ordering.
    column_order : list[str]
        Mutable column ordering.
    """
    for row_index, row in enumerate(matrix.rows):
        if row not in row_order:
            row_order.append(row)
        for column_index, column in enumerate(matrix.columns):
            value = matrix.matrix[row_index][column_index]
            if value == 0:
                continue
            if column not in column_order:
                column_order.append(column)
            key = (row, column)
            scores[key] = scores.get(key, 0) + int(value)
            original_values.setdefault(key, float(value))


def _select_removed_keys(
    scores: dict[Any, int],
    *,
    remove_unused_ratio: float,
    remove_used_ratio: float,
) -> tuple[set[Any], InverseRouterPruneStats]:
    """Select low-score keys for removal.

    Parameters
    ----------
    scores : dict[Any, int]
        Candidate score map.
    remove_unused_ratio : float
        Ratio of score-zero candidates to remove.
    remove_used_ratio : float
        Ratio of score-positive candidates to remove.

    Returns
    -------
    tuple[set[Any], InverseRouterPruneStats]
        Removed keys and pruning statistics.
    """
    unused = sorted(
        (key for key, score in scores.items() if score == 0),
        key=str,
    )
    used = sorted(
        (key for key, score in scores.items() if score > 0),
        key=lambda key: (scores[key], str(key)),
    )
    unused_remove_count = _ratio_count(len(unused), remove_unused_ratio)
    used_remove_count = _ratio_count(len(used), remove_used_ratio)
    removed = set(unused[:unused_remove_count])
    removed.update(used[:used_remove_count])
    stats = InverseRouterPruneStats(
        candidates=len(scores),
        unused_candidates=len(unused),
        used_candidates=len(used),
        removed_unused=unused_remove_count,
        removed_used=used_remove_count,
        kept=len(scores) - len(removed),
    )
    return (removed, stats)


def _ratio_count(count: int, ratio: float) -> int:
    """Return how many items a ratio selects.

    Parameters
    ----------
    count : int
        Number of candidate items.
    ratio : float
        Ratio in ``0..1``.

    Returns
    -------
    int
        Selected item count.
    """
    if ratio >= 1.0:
        return count
    return int(count * ratio)


def _matrix_from_values(
    tile_name: str,
    values: dict[MatrixKey, int | float],
    row_order: list[str],
    column_order: list[str],
    *,
    include_zero: bool,
) -> RoutingSwitchMatrix:
    """Build a switch-matrix object from keyed values.

    Parameters
    ----------
    tile_name : str
        Tile type represented by the matrix.
    values : dict[MatrixKey, int | float]
        Matrix cell values keyed by ``(row, column)``.
    row_order : list[str]
        Preferred row order.
    column_order : list[str]
        Preferred column order.
    include_zero : bool
        Whether zero-valued keys should keep rows and columns present.

    Returns
    -------
    RoutingSwitchMatrix
        Matrix view.
    """
    active_keys = {
        key for key, value in values.items() if include_zero or float(value) != 0.0
    }
    rows = [row for row in row_order if any(key[0] == row for key in active_keys)]
    columns = [
        column
        for column in column_order
        if any(key[1] == column for key in active_keys)
    ]
    row_index = {row: index for index, row in enumerate(rows)}
    column_index = {column: index for index, column in enumerate(columns)}
    matrix = [[0.0 for _column in columns] for _row in rows]
    for (row, column), value in values.items():
        if (row, column) not in active_keys:
            continue
        matrix[row_index[row]][column_index[column]] = float(value)
    return RoutingSwitchMatrix(
        tile_type=tile_name,
        columns=columns,
        rows=rows,
        matrix=matrix,
    )


def _final_matrix(
    tile_name: str,
    scores: dict[MatrixKey, int],
    original_values: dict[MatrixKey, float],
    removed_keys: set[MatrixKey],
    row_order: list[str],
    column_order: list[str],
    *,
    active_pip_value: int | None,
) -> RoutingSwitchMatrix:
    """Build the final pruned matrix.

    Parameters
    ----------
    tile_name : str
        Tile type represented by the matrix.
    scores : dict[MatrixKey, int]
        Score map.
    original_values : dict[MatrixKey, float]
        Original matrix values.
    removed_keys : set[MatrixKey]
        Keys selected for removal.
    row_order : list[str]
        Preferred row order.
    column_order : list[str]
        Preferred column order.
    active_pip_value : int | None
        Value assigned to kept PIPs. ``None`` keeps original/fallback values.

    Returns
    -------
    RoutingSwitchMatrix
        Final pruned matrix.
    """
    final_values: dict[MatrixKey, float] = {}
    for key in scores:
        if key in removed_keys:
            continue
        final_values[key] = (
            float(active_pip_value)
            if active_pip_value is not None
            else original_values.get(key, 1.0)
        )
    return _matrix_from_values(
        tile_name,
        final_values,
        row_order,
        column_order,
        include_zero=False,
    )


def _external_track_candidates(
    fpga_model: PnRBridge,
    tile_name: str,
) -> dict[ExternalTrackKey, ExternalTrackKey]:
    """Return tile-type-level logical external track candidates.

    Parameters
    ----------
    fpga_model : PnRBridge
        Graph that provides active external resources.
    tile_name : str
        Tile type to inspect.

    Returns
    -------
    dict[ExternalTrackKey, ExternalTrackKey]
        Candidate tracks keyed by ``(resource_key, track_index)``.
    """
    candidates: dict[ExternalTrackKey, ExternalTrackKey] = {}
    for key in fpga_model.external_resources(
        tile_name,
        where=lambda candidate: candidate.kind is RoutingPipKind.EXTERNAL_WIRE
        and candidate.wire_count is not None
        and candidate.wire_count > 0,
    ):
        if key.wire_count is None:
            continue
        if key.wire_count > 1 and (
            key.source_name == "NULL" or key.destination_name == "NULL"
        ):
            continue
        for track_index in range(key.wire_count):
            track = (key, track_index)
            candidates[track] = track
    return candidates


def _remove_external_tracks(
    fpga_model: PnRBridge,
    tracks: list[ExternalTrackKey],
) -> None:
    """Apply external track removals to the graph.

    Parameters
    ----------
    fpga_model : PnRBridge
        Graph to mutate.
    tracks : list[ExternalTrackKey]
        Original resource keys and logical track indices selected for removal.
    """
    tracks_by_resource: dict[RoutingResourceKey, set[int]] = {}
    for resource_key, track_index in tracks:
        tracks_by_resource.setdefault(resource_key, set()).add(track_index)

    for resource_key, track_indices in tracks_by_resource.items():
        active_key = resource_key
        for track_index in sorted(track_indices, reverse=True):
            active_key = fpga_model.remove_external_resource_track(
                key=active_key,
                track_index=track_index,
            )


def _active_cell_count(matrix: RoutingSwitchMatrix) -> int:
    """Count nonzero matrix cells.

    Parameters
    ----------
    matrix : RoutingSwitchMatrix
        Matrix to inspect.

    Returns
    -------
    int
        Number of nonzero cells.
    """
    return sum(1 for row in matrix.matrix for value in row if value != 0)

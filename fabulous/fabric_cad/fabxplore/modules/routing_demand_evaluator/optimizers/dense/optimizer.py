"""Dense demand-guided switch-matrix optimizer."""

from __future__ import annotations

from dataclasses import dataclass
from math import ceil
from typing import TYPE_CHECKING

from fabulous.fabric_cad.fabxplore.modules.routing_demand_evaluator.optimizers.base import (  # noqa: E501
    OptimizerContext,
    RoutingDemandOptimizer,
)
from fabulous.fabric_cad.fabxplore.modules.routing_demand_evaluator.optimizers.common import (  # noqa: E501
    relax_congestion,
    repair_unreachable_demands,
    routing_pip_count,
)
from fabulous.fabric_cad.fabxplore.modules.routing_demand_evaluator.optimizers.greedy.optimizer import (  # noqa: E501
    Connections,
    Pip,
    _apply_to_tile_model,
    _build_graph,
    _copy_connections,
    _Counters,
    _failure_limits,
    _Limits,
    _pip_use_by_kind,
    _remove_pips,
    _with_optimizer_stats,
    _within_limits,
)

if TYPE_CHECKING:
    from fabulous.fabric_cad.fabxplore.modules.routing_demand_evaluator.core.models import (  # noqa: E501
        RoutingDemandEvaluatorResult,
    )

_MAX_BACKUP_SOURCES_PER_ROW = 4
_MIN_BACKUP_SOURCES_PER_ROW = 1


@dataclass(frozen=True)
class _DenseCandidate:
    """One removable dense optimizer candidate.

    Attributes
    ----------
    pip : Pip
        Candidate PIP.
    soft_use : int
        Number of soft routed paths using the PIP.
    row_fanin : int
        Current row fanin before pruning.
    """

    pip: Pip
    soft_use: int
    row_fanin: int


class DenseOptimizer(RoutingDemandOptimizer):
    """Demand-guided bulk optimizer for full or nearly full matrices."""

    def optimize(self, context: OptimizerContext) -> RoutingDemandEvaluatorResult:
        """Prune dense switch matrices with one bulk demand-guided pass.

        Parameters
        ----------
        context : OptimizerContext
            Optimizer context.

        Returns
        -------
        RoutingDemandEvaluatorResult
            Evaluation result after dense pruning.
        """
        context.tracker.evaluation_start("baseline demand oracle")
        baseline = context.evaluate(context.graph, [], track_router=True)
        limits = _failure_limits(context, baseline)
        if not _within_limits(baseline, limits):
            return _with_optimizer_stats(
                result=baseline,
                baseline=baseline,
                final_connections=context.matrix.connections,
                limits=limits,
                counters=_Counters(),
                stop_reason="baseline_exceeds_optimizer_limits",
                applied_to_tile_model=False,
            )

        target_remove = ceil(
            baseline.stats.original_routing_pips
            * context.options.opt_target_pip_reduction
        )
        counters = _Counters()
        context.tracker.optimizer_start(
            str(context.options.optimizer),
            target_remove,
            context.options.opt_max_iterations,
        )
        if target_remove == 0:
            return _finish(
                context=context,
                result=baseline,
                baseline=baseline,
                final_connections=context.matrix.connections,
                counters=counters,
                limits=limits,
                stop_reason="target_reached",
                applied_to_tile_model=False,
            )

        baseline_connections = _copy_connections(context.matrix.connections)
        removed = _dense_removal_plan(
            connections=baseline_connections,
            result=baseline,
            target_remove=target_remove,
        )
        if not removed:
            return _finish(
                context=context,
                result=baseline,
                baseline=baseline,
                final_connections=baseline_connections,
                counters=counters,
                limits=limits,
                stop_reason="no_removable_pips",
                applied_to_tile_model=False,
            )

        candidate_connections = _remove_pips(baseline_connections, removed)
        counters.iterations = 1
        counters.attempted_batches = 1
        counters.attempted_pips = len(removed)
        context.tracker.evaluation_start(f"dense bulk validation ({len(removed)} PIPs)")
        candidate = context.evaluate(
            _build_graph(context.matrix, candidate_connections),
            [],
            track_router=True,
        )
        if _within_limits(candidate, limits):
            repair = repair_unreachable_demands(
                context=context,
                baseline_connections=baseline_connections,
                optimized_connections=candidate_connections,
                result=candidate,
            )
            candidate_connections = repair.connections
            candidate = repair.result
            relax = relax_congestion(
                context=context,
                baseline_connections=baseline_connections,
                optimized_connections=candidate_connections,
                result=candidate,
            )
            candidate_connections = relax.connections
            candidate = relax.result
            counters.accepted_batches = 1
            counters.accepted_pips = max(
                baseline.stats.original_routing_pips
                - routing_pip_count(candidate_connections),
                0,
            )
            counters.rejected_pips = repair.restored_pips + relax.restored_pips
            stop_reason = (
                "target_reached"
                if counters.accepted_pips >= target_remove
                else "dense_candidate_exhausted"
            )
            should_apply = context.options.apply_to_tile_model
            if should_apply:
                _apply_to_tile_model(context, candidate_connections)
            return _finish(
                context=context,
                result=candidate,
                baseline=baseline,
                final_connections=candidate_connections,
                counters=counters,
                limits=limits,
                stop_reason=stop_reason,
                applied_to_tile_model=should_apply,
            )

        counters.rejected_batches = 1
        removed_by_row = _removed_by_row(removed)
        repaired = _repair_candidate(
            context=context,
            baseline_connections=baseline_connections,
            candidate=candidate,
            candidate_connections=candidate_connections,
            removed_by_row=removed_by_row,
            limits=limits,
            counters=counters,
        )
        if repaired is None:
            counters.rejected_pips = len(removed)
            return _finish(
                context=context,
                result=baseline,
                baseline=baseline,
                final_connections=baseline_connections,
                counters=counters,
                limits=limits,
                stop_reason="dense_repair_failed",
                applied_to_tile_model=False,
            )

        final_connections, final_result, stop_reason = repaired
        repair = repair_unreachable_demands(
            context=context,
            baseline_connections=baseline_connections,
            optimized_connections=final_connections,
            result=final_result,
        )
        final_connections = repair.connections
        final_result = repair.result
        relax = relax_congestion(
            context=context,
            baseline_connections=baseline_connections,
            optimized_connections=final_connections,
            result=final_result,
        )
        final_connections = relax.connections
        final_result = relax.result
        accepted_pips = _removed_pip_count(baseline_connections, final_connections)
        counters.accepted_batches = 1
        counters.accepted_pips = accepted_pips
        counters.rejected_pips = max(len(removed) - accepted_pips, 0)
        should_apply = context.options.apply_to_tile_model and accepted_pips > 0
        if should_apply:
            _apply_to_tile_model(context, final_connections)
        return _finish(
            context=context,
            result=final_result,
            baseline=baseline,
            final_connections=final_connections,
            counters=counters,
            limits=limits,
            stop_reason=stop_reason,
            applied_to_tile_model=should_apply,
        )


def _dense_removal_plan(
    connections: Connections,
    result: RoutingDemandEvaluatorResult,
    target_remove: int,
) -> list[Pip]:
    """Return demand-guided PIPs to remove from a dense matrix.

    Parameters
    ----------
    connections : Connections
        Baseline switch-matrix connections.
    result : RoutingDemandEvaluatorResult
        Baseline routed demand result.
    target_remove : int
        Target number of PIPs to remove.

    Returns
    -------
    list[Pip]
        Candidate removals, capped by ``target_remove``.
    """
    hard_use, soft_use = _pip_use_by_kind(result)
    remaining_by_row = {row: len(sources) for row, sources in connections.items()}
    min_keep_by_row = {
        row: _row_min_keep(
            fanin=len(sources),
            hard_used=sum(1 for source in sources if hard_use[(source, row)] > 0),
        )
        for row, sources in connections.items()
    }
    candidates: list[_DenseCandidate] = []
    for row, sources in connections.items():
        if len(sources) <= min_keep_by_row[row]:
            continue
        for source in sources:
            pip = (source, row)
            if hard_use[pip] > 0:
                continue
            candidates.append(
                _DenseCandidate(
                    pip=pip,
                    soft_use=soft_use[pip],
                    row_fanin=len(sources),
                )
            )

    removed: list[Pip] = []
    for candidate in sorted(
        candidates,
        key=lambda item: (
            item.soft_use,
            -item.row_fanin,
            item.pip[1],
            item.pip[0],
        ),
    ):
        if len(removed) >= target_remove:
            break
        source, row = candidate.pip
        if source not in connections.get(row, []):
            continue
        if remaining_by_row.get(row, 0) <= min_keep_by_row.get(row, 1):
            continue
        remaining_by_row[row] -= 1
        removed.append(candidate.pip)
    return removed


def _row_min_keep(fanin: int, hard_used: int) -> int:
    """Return derived minimum kept sources for one row.

    Parameters
    ----------
    fanin : int
        Original row fanin.
    hard_used : int
        Number of hard-demand-used PIPs in the row.

    Returns
    -------
    int
        Minimum fanin retained by dense pruning.
    """
    if fanin <= 1:
        return fanin
    backup = min(
        _MAX_BACKUP_SOURCES_PER_ROW,
        max(_MIN_BACKUP_SOURCES_PER_ROW, (fanin - 1).bit_length()),
    )
    return min(fanin, max(1, hard_used, backup))


def _repair_candidate(
    context: OptimizerContext,
    baseline_connections: Connections,
    candidate: RoutingDemandEvaluatorResult,
    candidate_connections: Connections,
    removed_by_row: dict[str, list[Pip]],
    limits: _Limits,
    counters: _Counters,
) -> tuple[Connections, RoutingDemandEvaluatorResult, str] | None:
    """Restore pruned rows until the dense candidate passes or rounds expire.

    Parameters
    ----------
    context : OptimizerContext
        Optimizer context.
    baseline_connections : Connections
        Original switch-matrix connections.
    candidate : RoutingDemandEvaluatorResult
        Current failing candidate result.
    candidate_connections : Connections
        Current candidate connections.
    removed_by_row : dict[str, list[Pip]]
        Removed PIPs keyed by destination row.
    limits : _Limits
        Optimizer limits.
    counters : _Counters
        Mutable optimizer counters.

    Returns
    -------
    tuple[Connections, RoutingDemandEvaluatorResult, str] | None
        Passing repaired connections, result, and stop reason, or ``None``.
    """
    current = _copy_connections(candidate_connections)
    result = candidate
    restored_rows: set[str] = set()
    while counters.iterations < context.options.opt_max_iterations:
        rows = _repair_rows(result, removed_by_row, restored_rows)
        if not rows:
            return None
        _restore_rows(current, baseline_connections, rows)
        restored_rows.update(rows)
        counters.iterations += 1
        counters.attempted_batches += 1
        context.tracker.evaluation_start(
            f"dense repair validation ({len(rows)} row(s) restored)"
        )
        result = context.evaluate(
            _build_graph(context.matrix, current),
            [],
            track_router=True,
        )
        if _within_limits(result, limits):
            return current, result, "dense_repaired"
        counters.rejected_batches += 1
    return None


def _repair_rows(
    result: RoutingDemandEvaluatorResult,
    removed_by_row: dict[str, list[Pip]],
    restored_rows: set[str],
) -> list[str]:
    """Return the next rows to restore after a failed dense validation.

    Parameters
    ----------
    result : RoutingDemandEvaluatorResult
        Failed candidate result.
    removed_by_row : dict[str, list[Pip]]
        Removed PIPs keyed by row.
    restored_rows : set[str]
        Rows already restored.

    Returns
    -------
    list[str]
        Rows selected for restoration.
    """
    failed_nodes = _failed_nodes(result)
    ranked: list[tuple[bool, int, str]] = []
    for row, pips in removed_by_row.items():
        if row in restored_rows:
            continue
        touches_failed = row in failed_nodes or any(
            source in failed_nodes for source, _sink in pips
        )
        ranked.append((not touches_failed, -len(pips), row))
    rows = [row for _not_failed, _removed_count, row in sorted(ranked)]
    return rows[: _restore_rows_per_round(len(removed_by_row))]


def _restore_rows_per_round(row_count: int) -> int:
    """Return derived repair chunk size.

    Parameters
    ----------
    row_count : int
        Number of rows with removed PIPs.

    Returns
    -------
    int
        Rows restored per validation round.
    """
    if row_count <= 0:
        return 0
    return max(1, min(32, ceil(row_count**0.5)))


def _failed_nodes(result: RoutingDemandEvaluatorResult) -> set[str]:
    """Return nodes from failed demands.

    Parameters
    ----------
    result : RoutingDemandEvaluatorResult
        Candidate routing result.

    Returns
    -------
    set[str]
        Failed demand sources and sinks.
    """
    nodes: set[str] = set()
    for demand_result in result.demand_results:
        if demand_result.routed:
            continue
        nodes.add(demand_result.demand.source)
        nodes.update(demand_result.failed_sinks or demand_result.demand.sinks)
    return nodes


def _removed_by_row(removed: list[Pip]) -> dict[str, list[Pip]]:
    """Group removed PIPs by destination row.

    Parameters
    ----------
    removed : list[Pip]
        Removed PIPs.

    Returns
    -------
    dict[str, list[Pip]]
        Removed PIPs keyed by row.
    """
    result: dict[str, list[Pip]] = {}
    for pip in removed:
        result.setdefault(pip[1], []).append(pip)
    return result


def _restore_rows(
    target: Connections,
    baseline: Connections,
    rows: list[str],
) -> None:
    """Restore rows in a candidate matrix from the baseline.

    Parameters
    ----------
    target : Connections
        Candidate connections to mutate.
    baseline : Connections
        Baseline connections.
    rows : list[str]
        Rows to restore.
    """
    for row in rows:
        target[row] = list(baseline.get(row, []))


def _removed_pip_count(
    baseline: Connections,
    final: Connections,
) -> int:
    """Return how many baseline PIPs are absent from ``final``.

    Parameters
    ----------
    baseline : Connections
        Original connections.
    final : Connections
        Final connections.

    Returns
    -------
    int
        Removed PIP count.
    """
    return sum(
        1
        for row, sources in baseline.items()
        for source in sources
        if source not in set(final.get(row, []))
    )


def _finish(
    context: OptimizerContext,
    result: RoutingDemandEvaluatorResult,
    baseline: RoutingDemandEvaluatorResult,
    final_connections: Connections,
    counters: _Counters,
    limits: _Limits,
    stop_reason: str,
    applied_to_tile_model: bool,
) -> RoutingDemandEvaluatorResult:
    """Attach optimizer stats, log finish, and return the final result.

    Parameters
    ----------
    context : OptimizerContext
        Optimizer context.
    result : RoutingDemandEvaluatorResult
        Final routing-demand result.
    baseline : RoutingDemandEvaluatorResult
        Baseline result.
    final_connections : Connections
        Final accepted connections.
    counters : _Counters
        Optimizer counters.
    limits : _Limits
        Optimizer limits.
    stop_reason : str
        Stop reason.
    applied_to_tile_model : bool
        Whether the matrix was applied to the in-memory tile model.

    Returns
    -------
    RoutingDemandEvaluatorResult
        Result with optimizer stats.
    """
    updated = _with_optimizer_stats(
        result=result,
        baseline=baseline,
        final_connections=final_connections,
        limits=limits,
        counters=counters,
        stop_reason=stop_reason,
        applied_to_tile_model=applied_to_tile_model,
    )
    context.tracker.optimizer_finish(
        removed_pips=updated.optimizer_stats.removed_pips
        if updated.optimizer_stats is not None
        else 0,
        final_pips=updated.stats.final_pips,
        stop_reason=stop_reason,
    )
    return updated

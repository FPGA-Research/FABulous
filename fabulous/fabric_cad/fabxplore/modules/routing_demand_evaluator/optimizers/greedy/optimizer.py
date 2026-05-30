"""Greedy routing-demand optimizer."""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from math import ceil

from fabulous.fabric_cad.fabxplore.modules.routing_demand_evaluator.core.models import (
    DemandKind,
    MatrixData,
    MuxBucketStats,
    MuxCleanupRowStats,
    MuxCleanupStats,
    OptimizerStats,
    RoutingDemandEvaluatorResult,
)
from fabulous.fabric_cad.fabxplore.modules.routing_demand_evaluator.core.report import (
    render_routing_demand_report,
)
from fabulous.fabric_cad.fabxplore.modules.routing_demand_evaluator.core.routing_graph import (  # noqa: E501
    RoutingGraph,
    RoutingGraphBuilder,
)
from fabulous.fabric_cad.fabxplore.modules.routing_demand_evaluator.optimizers.base import (  # noqa: E501
    OptimizerContext,
    RoutingDemandOptimizer,
)
from fabulous.fabric_cad.fabxplore.modules.routing_demand_evaluator.optimizers.common import (  # noqa: E501
    relax_congestion,
    repair_unreachable_demands,
    routing_pip_count,
)

Connections = dict[str, list[str]]
Pip = tuple[str, str]
_ZERO_USE_BATCH_LIMIT = 512


@dataclass(frozen=True)
class _Limits:
    """Failure-rate limits for one optimizer run.

    Attributes
    ----------
    hard : float
        Allowed hard-demand failure rate.
    soft : float
        Allowed soft-demand failure rate.
    """

    hard: float
    soft: float


@dataclass
class _Counters:
    """Mutable optimizer counters.

    Attributes
    ----------
    iterations : int
        Iterations used.
    attempted_batches : int
        Candidate batches evaluated.
    accepted_batches : int
        Candidate batches accepted.
    rejected_batches : int
        Candidate batches rejected.
    attempted_pips : int
        PIP removals attempted.
    accepted_pips : int
        PIP removals accepted.
    rejected_pips : int
        PIP removals rejected.
    """

    iterations: int = 0
    attempted_batches: int = 0
    accepted_batches: int = 0
    rejected_batches: int = 0
    attempted_pips: int = 0
    accepted_pips: int = 0
    rejected_pips: int = 0


@dataclass(frozen=True)
class _CandidateBatch:
    """Optimizer candidate batch.

    Attributes
    ----------
    pips : list[Pip]
        PIPs to try removing together.
    mux_cost_saved : int
        Estimated mux cost saved if the batch is accepted.
    config_bits_saved : int
        Estimated config bits saved if the batch is accepted.
    normalizes_power_of_two : bool
        Whether this batch normalizes a non-power-of-two mux fanin.
    """

    pips: list[Pip]
    mux_cost_saved: int
    config_bits_saved: int
    normalizes_power_of_two: bool


@dataclass(frozen=True)
class _CandidateSelection:
    """Selected candidate PIPs for one optimizer iteration.

    Attributes
    ----------
    pips : list[Pip]
        PIPs to try removing together.
    blocked_by_target_budget : bool
        Whether strict mux-cleanup candidates exist but all exceed the
        remaining pruning budget.
    """

    pips: list[Pip]
    blocked_by_target_budget: bool = False


class GreedyOptimizer(RoutingDemandOptimizer):
    """Greedy demand-oracle pruning optimizer."""

    def optimize(self, context: OptimizerContext) -> RoutingDemandEvaluatorResult:
        """Prune low-risk switch-matrix PIPs with demand-oracle checks.

        Parameters
        ----------
        context : OptimizerContext
            Optimizer context.

        Returns
        -------
        RoutingDemandEvaluatorResult
            Evaluation result after greedy pruning.
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

        connections = _copy_connections(context.matrix.connections)
        rejected: set[Pip] = set()
        current = baseline
        counters = _Counters()
        target_remove = ceil(
            baseline.stats.original_routing_pips
            * context.options.opt_target_pip_reduction
        )
        clean_mux = (
            context.options.opt_clean_mux or context.options.opt_power_of_two_muxes
        )
        stop_reason = "target_reached" if target_remove == 0 else "max_iterations"
        context.tracker.optimizer_start(
            str(context.options.optimizer),
            target_remove,
            context.options.opt_max_iterations,
        )

        while counters.iterations < context.options.opt_max_iterations:
            if _optimizer_target_reached(counters, target_remove):
                stop_reason = "target_reached"
                break
            # Normal pruning can cheaply validate PIPs that no current routed
            # demand uses.  Mux-cleanup modes keep their stricter row-local
            # batch semantics, so they intentionally skip this shortcut.
            zero_use_batch = (
                []
                if clean_mux
                else _zero_use_candidate_batch(
                    connections=connections,
                    result=current,
                    rejected=rejected,
                    target_remove=target_remove,
                    counters=counters,
                )
            )
            if zero_use_batch:
                selection = _CandidateSelection(pips=zero_use_batch)
            else:
                selection = _next_candidate_batch(
                    connections=connections,
                    result=current,
                    rejected=rejected,
                    target_remove=target_remove,
                    counters=counters,
                    clean_mux=clean_mux,
                    power_of_two_muxes=context.options.opt_power_of_two_muxes,
                )
            batch = selection.pips
            if not batch:
                if selection.blocked_by_target_budget:
                    stop_reason = "power_of_two_budget_exhausted"
                else:
                    stop_reason = (
                        "power_of_two_blocked"
                        if context.options.opt_power_of_two_muxes
                        and _has_non_power_of_two_muxes(connections)
                        else "no_removable_pips"
                    )
                break

            counters.iterations += 1
            accepted = (
                _try_zero_use_batch(
                    context=context,
                    connections=connections,
                    batch=batch,
                    limits=limits,
                    rejected=rejected,
                    counters=counters,
                )
                if zero_use_batch
                else _try_adaptive_batch(
                    context=context,
                    connections=connections,
                    current=current,
                    batch=batch,
                    limits=limits,
                    rejected=rejected,
                    counters=counters,
                    allow_split=not clean_mux,
                )
            )
            if accepted is None:
                context.tracker.optimizer_iteration(
                    iteration=counters.iterations,
                    max_iterations=context.options.opt_max_iterations,
                    current_pips=current.stats.final_pips,
                    accepted_pips=counters.accepted_pips,
                    accepted_batches=counters.accepted_batches,
                    rejected_batches=counters.rejected_batches,
                )
                continue
            connections, current = accepted
            context.tracker.optimizer_iteration(
                iteration=counters.iterations,
                max_iterations=context.options.opt_max_iterations,
                current_pips=current.stats.final_pips,
                accepted_pips=counters.accepted_pips,
                accepted_batches=counters.accepted_batches,
                rejected_batches=counters.rejected_batches,
            )

        repair = repair_unreachable_demands(
            context=context,
            baseline_connections=context.matrix.connections,
            optimized_connections=connections,
            result=current,
        )
        connections = repair.connections
        current = repair.result
        if repair.restored_pips:
            counters.accepted_pips = max(
                baseline.stats.original_routing_pips - routing_pip_count(connections),
                0,
            )
            counters.rejected_pips += repair.restored_pips
        relax = relax_congestion(
            context=context,
            baseline_connections=context.matrix.connections,
            optimized_connections=connections,
            result=current,
        )
        connections = relax.connections
        current = relax.result
        if relax.restored_pips:
            counters.accepted_pips = max(
                baseline.stats.original_routing_pips - routing_pip_count(connections),
                0,
            )
            counters.rejected_pips += relax.restored_pips

        remaining_non_power_rows = _non_power_of_two_mux_count(connections)
        should_apply = (
            context.options.apply_to_tile_model
            and counters.accepted_pips > 0
            and (
                not context.options.opt_power_of_two_muxes
                or remaining_non_power_rows == 0
            )
        )
        if context.options.opt_power_of_two_muxes and remaining_non_power_rows:
            current = current.model_copy(
                update={
                    "warnings": [
                        *current.warnings,
                        (
                            "Power-of-two mux cleanup incomplete; "
                            f"{remaining_non_power_rows} non-power-of-two "
                            "mux row(s) remain."
                        ),
                        "Tile-model apply skipped because strict power-of-two mux "
                        "cleanup did not finish.",
                    ]
                }
            )
        if should_apply:
            _apply_to_tile_model(context, connections)

        result = _with_optimizer_stats(
            result=current,
            baseline=baseline,
            final_connections=connections,
            limits=limits,
            counters=counters,
            stop_reason=stop_reason,
            applied_to_tile_model=should_apply,
        )
        context.tracker.optimizer_finish(
            removed_pips=counters.accepted_pips,
            final_pips=current.stats.final_pips,
            stop_reason=stop_reason,
        )
        return result


def _zero_use_candidate_batch(
    connections: Connections,
    result: RoutingDemandEvaluatorResult,
    rejected: set[Pip],
    target_remove: int,
    counters: _Counters,
) -> list[Pip]:
    """Return a large batch of PIPs unused by the current routes.

    Parameters
    ----------
    connections : Connections
        Current accepted switch-matrix connections.
    result : RoutingDemandEvaluatorResult
        Current accepted routed result.
    rejected : set[Pip]
        PIPs rejected by previous oracle calls.
    target_remove : int
        Target number of PIPs to remove.
    counters : _Counters
        Optimizer counters.

    Returns
    -------
    list[Pip]
        Unused PIPs that can be removed without emptying a matrix row.
    """
    remaining = target_remove - counters.accepted_pips
    if remaining <= 0:
        return []
    hard_use, soft_use = _pip_use_by_kind(result)
    candidates: list[Pip] = []
    for sink, sources in connections.items():
        if len(sources) <= 1:
            continue
        for source in sources:
            pip = (source, sink)
            if pip in rejected:
                continue
            if hard_use[pip] or soft_use[pip]:
                continue
            candidates.append(pip)

    removable = _remove_emptying_pips(
        connections,
        sorted(
            candidates,
            key=lambda pip: (
                -len(connections[pip[1]]),
                pip[1],
                pip[0],
            ),
        ),
    )
    batch_size = min(_zero_use_batch_size(len(removable)), remaining)
    return removable[:batch_size]


def _zero_use_batch_size(candidate_count: int) -> int:
    """Return validation chunk size for unused-PIP pruning.

    Parameters
    ----------
    candidate_count : int
        Number of currently removable unused PIPs.

    Returns
    -------
    int
        Batch size.
    """
    if candidate_count <= 0:
        return 0
    return max(1, min(_ZERO_USE_BATCH_LIMIT, candidate_count))


def _try_zero_use_batch(
    context: OptimizerContext,
    connections: Connections,
    batch: list[Pip],
    limits: _Limits,
    rejected: set[Pip],
    counters: _Counters,
) -> tuple[Connections, RoutingDemandEvaluatorResult] | None:
    """Try removing PIPs unused by the current routed solution.

    Parameters
    ----------
    context : OptimizerContext
        Optimizer context.
    connections : Connections
        Current accepted switch-matrix connections.
    batch : list[Pip]
        Unused candidate PIPs to remove.
    limits : _Limits
        Allowed failure-rate limits.
    rejected : set[Pip]
        PIPs rejected by previous oracle calls.
    counters : _Counters
        Mutable optimizer counters.

    Returns
    -------
    tuple[Connections, RoutingDemandEvaluatorResult] | None
        Accepted connections and validated result, or ``None``.
    """
    candidate_connections = _remove_pips(connections, batch)
    candidate_graph = _build_graph(context.matrix, candidate_connections)
    counters.attempted_batches += 1
    counters.attempted_pips += len(batch)
    context.tracker.evaluation_start(f"greedy zero-use validation ({len(batch)} PIPs)")
    candidate = context.evaluate(candidate_graph, [])
    if _within_limits(candidate, limits):
        counters.accepted_batches += 1
        counters.accepted_pips += len(batch)
        return candidate_connections, candidate

    counters.rejected_batches += 1
    counters.rejected_pips += len(batch)
    rejected.update(batch)
    return None


def _failure_limits(
    context: OptimizerContext,
    baseline: RoutingDemandEvaluatorResult,
) -> _Limits:
    """Return optimizer failure-rate limits.

    Parameters
    ----------
    context : OptimizerContext
        Optimizer context.
    baseline : RoutingDemandEvaluatorResult
        Baseline evaluation result.

    Returns
    -------
    _Limits
        Allowed failure-rate limits.
    """
    hard = context.options.opt_max_hard_failure_rate
    soft = context.options.opt_max_soft_failure_rate
    if context.options.opt_use_baseline_failure_rates:
        hard += baseline.stats.hard_failure_rate
        soft += baseline.stats.soft_failure_rate
    return _Limits(hard=min(hard, 1.0), soft=min(soft, 1.0))


def _within_limits(result: RoutingDemandEvaluatorResult, limits: _Limits) -> bool:
    """Return whether one result satisfies optimizer limits.

    Parameters
    ----------
    result : RoutingDemandEvaluatorResult
        Candidate result.
    limits : _Limits
        Allowed failure-rate limits.

    Returns
    -------
    bool
        Whether the candidate is acceptable.
    """
    return (
        result.stats.hard_failure_rate <= limits.hard
        and result.stats.soft_failure_rate <= limits.soft
    )


def _try_adaptive_batch(
    context: OptimizerContext,
    connections: Connections,
    current: RoutingDemandEvaluatorResult,
    batch: list[Pip],
    limits: _Limits,
    rejected: set[Pip],
    counters: _Counters,
    allow_split: bool,
) -> tuple[Connections, RoutingDemandEvaluatorResult] | None:
    """Try a batch and recursively shrink it when rejected.

    Parameters
    ----------
    context : OptimizerContext
        Optimizer context.
    connections : Connections
        Current accepted switch-matrix connections.
    current : RoutingDemandEvaluatorResult
        Current accepted evaluation result.
    batch : list[Pip]
        Candidate PIPs to remove.
    limits : _Limits
        Allowed failure-rate limits.
    rejected : set[Pip]
        PIPs rejected by previous oracle calls.
    counters : _Counters
        Mutable optimizer counters.
    allow_split : bool
        Whether the batch can be split when rejected.

    Returns
    -------
    tuple[Connections, RoutingDemandEvaluatorResult] | None
        Accepted connections and result, or ``None`` if no candidate was accepted.
    """
    if not batch:
        return None

    removable_batch = _remove_emptying_pips(connections, batch)
    if not removable_batch:
        counters.rejected_batches += 1
        counters.rejected_pips += len(batch)
        rejected.update(batch)
        return None

    candidate_connections = _remove_pips(connections, removable_batch)
    candidate_graph = _build_graph(context.matrix, candidate_connections)
    counters.attempted_batches += 1
    counters.attempted_pips += len(removable_batch)
    context.tracker.evaluation_start(
        f"greedy candidate validation ({len(removable_batch)} PIPs)"
    )
    candidate = context.evaluate(candidate_graph, [])
    if _within_limits(candidate, limits):
        counters.accepted_batches += 1
        counters.accepted_pips += len(removable_batch)
        return candidate_connections, candidate

    counters.rejected_batches += 1
    if not allow_split:
        rejected.update(removable_batch)
        counters.rejected_pips += len(removable_batch)
        return None
    if len(removable_batch) == 1:
        rejected.add(removable_batch[0])
        counters.rejected_pips += 1
        return None

    half = max(len(removable_batch) // 2, 1)
    accepted = _try_adaptive_batch(
        context=context,
        connections=connections,
        current=current,
        batch=removable_batch[:half],
        limits=limits,
        rejected=rejected,
        counters=counters,
        allow_split=allow_split,
    )
    if accepted is not None:
        return accepted
    return _try_adaptive_batch(
        context=context,
        connections=connections,
        current=current,
        batch=removable_batch[half:],
        limits=limits,
        rejected=rejected,
        counters=counters,
        allow_split=allow_split,
    )


def _next_candidate_batch(
    connections: Connections,
    result: RoutingDemandEvaluatorResult,
    rejected: set[Pip],
    target_remove: int,
    counters: _Counters,
    clean_mux: bool,
    power_of_two_muxes: bool,
) -> _CandidateSelection:
    """Return the next candidate batch.

    Parameters
    ----------
    connections : Connections
        Current accepted switch-matrix connections.
    result : RoutingDemandEvaluatorResult
        Current routed result.
    rejected : set[Pip]
        PIPs rejected by previous oracle calls.
    target_remove : int
        Target number of PIPs to remove.
    counters : _Counters
        Optimizer counters.
    clean_mux : bool
        Whether to use mux-aware batches.
    power_of_two_muxes : bool
        Whether to prioritize power-of-two fanin normalization.

    Returns
    -------
    _CandidateSelection
        Candidate batch and optional strict-budget block flag.
    """
    if clean_mux:
        batches = _rank_mux_candidate_batches(
            connections,
            result,
            rejected,
            power_of_two_muxes=power_of_two_muxes,
        )
        if not batches:
            return _CandidateSelection(pips=[])
        if not power_of_two_muxes:
            return _CandidateSelection(pips=batches[0].pips)
        remaining = max(target_remove - counters.accepted_pips, 1)
        for batch in batches:
            if len(batch.pips) <= remaining:
                return _CandidateSelection(pips=batch.pips)
        return _CandidateSelection(pips=[], blocked_by_target_budget=True)

    candidates = _rank_pip_candidates(connections, result, rejected)
    remaining = max(target_remove - counters.accepted_pips, 1)
    batch_size = min(_batch_size(len(candidates)), remaining)
    return _CandidateSelection(pips=candidates[:batch_size])


def _rank_pip_candidates(
    connections: Connections,
    result: RoutingDemandEvaluatorResult,
    rejected: set[Pip],
) -> list[Pip]:
    """Rank removable PIPs by estimated risk.

    Parameters
    ----------
    connections : Connections
        Current accepted switch-matrix connections.
    result : RoutingDemandEvaluatorResult
        Current routed result.
    rejected : set[Pip]
        PIPs rejected by previous oracle calls.

    Returns
    -------
    list[Pip]
        Candidate PIPs ordered from lowest to highest estimated risk.
    """
    hard_use, soft_use = _pip_use_by_kind(result)
    candidates: list[Pip] = []
    for sink, sources in connections.items():
        if len(sources) <= 1:
            continue
        for source in sources:
            pip = (source, sink)
            if pip not in rejected:
                candidates.append(pip)
    return sorted(
        candidates,
        key=lambda pip: (
            hard_use[pip],
            soft_use[pip],
            hard_use[pip] + soft_use[pip],
            -len(connections[pip[1]]),
            pip[1],
            pip[0],
        ),
    )


def _rank_mux_candidate_batches(
    connections: Connections,
    result: RoutingDemandEvaluatorResult,
    rejected: set[Pip],
    power_of_two_muxes: bool,
) -> list[_CandidateBatch]:
    """Rank mux-aware candidate batches.

    Parameters
    ----------
    connections : Connections
        Current accepted switch-matrix connections.
    result : RoutingDemandEvaluatorResult
        Current routed result.
    rejected : set[Pip]
        PIPs rejected by previous oracle calls.
    power_of_two_muxes : bool
        Whether non-power-of-two fanins should be normalized first.

    Returns
    -------
    list[_CandidateBatch]
        Candidate batches ordered from most useful to least useful.
    """
    hard_use, soft_use = _pip_use_by_kind(result)
    batches: list[_CandidateBatch] = []
    for sink, sources in connections.items():
        fanin = len(sources)
        if fanin <= 1:
            continue
        target_fanin = _target_mux_fanin(fanin)
        remove_count = fanin - target_fanin
        if remove_count <= 0:
            continue

        row_pips = [
            (source, sink) for source in sources if (source, sink) not in rejected
        ]
        if len(row_pips) < remove_count:
            continue
        row_pips = sorted(
            row_pips,
            key=lambda pip: (
                hard_use[pip],
                soft_use[pip],
                hard_use[pip] + soft_use[pip],
                pip[0],
            ),
        )
        selected = row_pips[:remove_count]
        batches.append(
            _CandidateBatch(
                pips=selected,
                mux_cost_saved=max(
                    _mux_cost(fanin) - _mux_cost(target_fanin),
                    0,
                ),
                config_bits_saved=max(
                    _mux_config_bits(fanin) - _mux_config_bits(target_fanin),
                    0,
                ),
                normalizes_power_of_two=(
                    power_of_two_muxes and not _is_allowed_mux_fanin(fanin)
                ),
            )
        )

    return sorted(
        batches,
        key=lambda batch: (
            not batch.normalizes_power_of_two,
            -batch.mux_cost_saved,
            -batch.config_bits_saved,
            sum(hard_use[pip] for pip in batch.pips),
            sum(soft_use[pip] for pip in batch.pips),
            len(batch.pips),
            batch.pips[0][1],
        ),
    )


def _pip_use_by_kind(
    result: RoutingDemandEvaluatorResult,
) -> tuple[Counter[Pip], Counter[Pip]]:
    """Return routed PIP usage split by demand kind.

    Parameters
    ----------
    result : RoutingDemandEvaluatorResult
        Routed result.

    Returns
    -------
    tuple[Counter[Pip], Counter[Pip]]
        Hard and soft PIP usage.
    """
    hard: Counter[Pip] = Counter()
    soft: Counter[Pip] = Counter()
    for demand_result in result.demand_results:
        counter = hard if demand_result.demand.kind == DemandKind.HARD else soft
        for path in demand_result.paths:
            for source, sink in zip(path.nodes, path.nodes[1:], strict=False):
                counter[(source, sink)] += 1
    return hard, soft


def _batch_size(candidate_count: int) -> int:
    """Return a conservative batch size for one greedy iteration.

    Parameters
    ----------
    candidate_count : int
        Number of currently removable candidate PIPs.

    Returns
    -------
    int
        Candidate batch size.
    """
    return max(1, min(16, ceil(candidate_count * 0.02)))


def _optimizer_target_reached(
    counters: _Counters,
    target_remove: int,
) -> bool:
    """Return whether the optimizer can stop.

    Parameters
    ----------
    counters : _Counters
        Optimizer counters.
    target_remove : int
        Target number of PIPs to remove.

    Returns
    -------
    bool
        Whether the optimizer target is satisfied.
    """
    return counters.accepted_pips >= target_remove


def _has_non_power_of_two_muxes(connections: Connections) -> bool:
    """Return whether any mux row has a non-power-of-two fanin.

    Parameters
    ----------
    connections : Connections
        Switch-matrix connections.

    Returns
    -------
    bool
        Whether a mux row has a non-power-of-two fanin.
    """
    return _non_power_of_two_mux_count(connections) > 0


def _non_power_of_two_mux_count(connections: Connections) -> int:
    """Return the number of non-power-of-two mux rows.

    Parameters
    ----------
    connections : Connections
        Switch-matrix connections.

    Returns
    -------
    int
        Non-power-of-two mux row count.
    """
    return sum(
        1
        for sources in connections.values()
        if len(sources) > 1 and not _is_allowed_mux_fanin(len(sources))
    )


def _target_mux_fanin(fanin: int) -> int:
    """Return the next lower mux-cleanup target fanin.

    Parameters
    ----------
    fanin : int
        Current row fanin.

    Returns
    -------
    int
        Target fanin for one mux cleanup batch.
    """
    if fanin <= 1:
        return fanin
    return 2 ** ((fanin - 1).bit_length() - 1)


def _is_allowed_mux_fanin(fanin: int) -> bool:
    """Return whether a fanin is direct or power-of-two mux sized.

    Parameters
    ----------
    fanin : int
        Row fanin.

    Returns
    -------
    bool
        Whether the fanin is allowed by power-of-two cleanup.
    """
    return fanin <= 1 or fanin.bit_count() == 1


def _copy_connections(connections: Connections) -> Connections:
    """Return a deep copy of matrix connections.

    Parameters
    ----------
    connections : Connections
        Matrix connections.

    Returns
    -------
    Connections
        Copied connections.
    """
    return {sink: list(sources) for sink, sources in connections.items()}


def _remove_pips(connections: Connections, pips: list[Pip]) -> Connections:
    """Return connections with selected PIPs removed.

    Parameters
    ----------
    connections : Connections
        Current connections.
    pips : list[Pip]
        PIPs to remove.

    Returns
    -------
    Connections
        Updated connections.
    """
    remove_by_sink: dict[str, set[str]] = {}
    for source, sink in pips:
        remove_by_sink.setdefault(sink, set()).add(source)
    return {
        sink: [
            source
            for source in sources
            if source not in remove_by_sink.get(sink, set())
        ]
        for sink, sources in connections.items()
    }


def _remove_emptying_pips(connections: Connections, pips: list[Pip]) -> list[Pip]:
    """Return removals that leave at least one PIP in every matrix row.

    Parameters
    ----------
    connections : Connections
        Current switch-matrix connections.
    pips : list[Pip]
        Candidate PIPs to remove.

    Returns
    -------
    list[Pip]
        Candidate PIPs with row-emptying removals filtered out.
    """
    remaining_by_row = {row: len(sources) for row, sources in connections.items()}
    removable: list[Pip] = []
    for source, row in pips:
        if remaining_by_row.get(row, 0) <= 1:
            continue
        remaining_by_row[row] -= 1
        removable.append((source, row))
    return removable


def _build_graph(matrix: MatrixData, connections: Connections) -> RoutingGraph:
    """Build a graph from candidate connections.

    Parameters
    ----------
    matrix : MatrixData
        Loaded matrix data.
    connections : Connections
        Candidate switch-matrix connections.

    Returns
    -------
    RoutingGraph
        Candidate routing graph.
    """
    builder = RoutingGraphBuilder()
    builder.add_connection_rows(connections)
    builder.add_jump_edges(matrix.jump_edges)
    return builder.build()


def _with_optimizer_stats(
    result: RoutingDemandEvaluatorResult,
    baseline: RoutingDemandEvaluatorResult,
    final_connections: Connections,
    limits: _Limits,
    counters: _Counters,
    stop_reason: str,
    applied_to_tile_model: bool,
) -> RoutingDemandEvaluatorResult:
    """Attach optimizer statistics and rerender the report.

    Parameters
    ----------
    result : RoutingDemandEvaluatorResult
        Final optimizer result.
    baseline : RoutingDemandEvaluatorResult
        Baseline result.
    final_connections : Connections
        Final accepted switch-matrix connections.
    limits : _Limits
        Allowed failure-rate limits.
    counters : _Counters
        Optimizer counters.
    stop_reason : str
        Stop reason.
    applied_to_tile_model : bool
        Whether the accepted matrix was applied to the in-memory tile model.

    Returns
    -------
    RoutingDemandEvaluatorResult
        Result with optimizer statistics and report.
    """
    baseline_pips = baseline.stats.original_routing_pips
    removed_pips = max(baseline_pips - result.stats.final_routing_pips, 0)
    final_matrix_bits = _estimate_config_bits(final_connections)
    baseline_non_matrix_bits = (
        baseline.stats.total_config_bits - baseline.stats.matrix_config_bits
    )
    mux_cleanup = _mux_cleanup_stats(
        baseline_connections=baseline.matrix.connections,
        final_connections=final_connections,
        baseline_config_bits=baseline.stats.matrix_config_bits,
        final_config_bits=final_matrix_bits,
    )
    stats = OptimizerStats(
        enabled=True,
        optimizer=str(result.options.optimizer),
        applied_to_tile_model=applied_to_tile_model,
        baseline_pips=baseline_pips,
        final_pips=result.stats.final_routing_pips,
        removed_pips=removed_pips,
        baseline_matrix_config_bits=baseline.stats.matrix_config_bits,
        final_matrix_config_bits_estimate=final_matrix_bits,
        baseline_total_config_bits=baseline.stats.total_config_bits,
        final_total_config_bits_estimate=baseline_non_matrix_bits + final_matrix_bits,
        pip_reduction=(removed_pips / baseline_pips if baseline_pips else 0.0),
        target_pip_reduction=result.options.opt_target_pip_reduction,
        baseline_hard_failure_rate=baseline.stats.hard_failure_rate,
        baseline_soft_failure_rate=baseline.stats.soft_failure_rate,
        allowed_hard_failure_rate=limits.hard,
        allowed_soft_failure_rate=limits.soft,
        final_hard_failure_rate=result.stats.hard_failure_rate,
        final_soft_failure_rate=result.stats.soft_failure_rate,
        attempted_iterations=counters.iterations,
        attempted_batches=counters.attempted_batches,
        accepted_batches=counters.accepted_batches,
        rejected_batches=counters.rejected_batches,
        attempted_pips=counters.attempted_pips,
        accepted_pips=counters.accepted_pips,
        rejected_pips=counters.rejected_pips,
        stop_reason=stop_reason,
        mux_cleanup=mux_cleanup,
    )
    updated = result.model_copy(update={"optimizer_stats": stats})
    return updated.model_copy(
        update={"report_summary": render_routing_demand_report(updated)}
    )


def _estimate_config_bits(connections: Connections) -> int:
    """Estimate FABulous switch-matrix configuration bits.

    Parameters
    ----------
    connections : Connections
        Switch-matrix connections.

    Returns
    -------
    int
        Estimated config bits.
    """
    return sum(
        (len(sources) - 1).bit_length()
        for sources in connections.values()
        if len(sources) >= 2
    )


def _mux_cleanup_stats(
    baseline_connections: Connections,
    final_connections: Connections,
    baseline_config_bits: int,
    final_config_bits: int,
) -> MuxCleanupStats:
    """Return mux implementation bucket statistics.

    Parameters
    ----------
    baseline_connections : Connections
        Connections before optimization.
    final_connections : Connections
        Accepted connections after optimization.
    baseline_config_bits : int
        Matrix config bits before optimization.
    final_config_bits : int
        Estimated matrix config bits after optimization.

    Returns
    -------
    MuxCleanupStats
        Mux-cost and bucket statistics.
    """
    baseline_hist = _mux_bucket_histogram(baseline_connections)
    final_hist = _mux_bucket_histogram(final_connections)
    bucket_order = ["direct", "mux2", "mux4", "mux8", "mux16", "mux32+"]
    buckets = [
        MuxBucketStats(
            bucket=bucket,
            before_rows=baseline_hist.get(bucket, 0),
            after_rows=final_hist.get(bucket, 0),
        )
        for bucket in bucket_order
        if baseline_hist.get(bucket, 0) or final_hist.get(bucket, 0)
    ]

    changed_rows: list[MuxCleanupRowStats] = []
    for row in sorted(set(baseline_connections) | set(final_connections)):
        before = len(baseline_connections.get(row, []))
        after = len(final_connections.get(row, []))
        before_bucket = _mux_bucket_label(before)
        after_bucket = _mux_bucket_label(after)
        if before_bucket == after_bucket:
            continue
        changed_rows.append(
            MuxCleanupRowStats(
                row=row,
                fanin_before=before,
                fanin_after=after,
                bucket_before=before_bucket,
                bucket_after=after_bucket,
                removed_pips=max(before - after, 0),
                config_bits_saved=max(
                    _mux_config_bits(before) - _mux_config_bits(after),
                    0,
                ),
                mux_cost_saved=max(_mux_cost(before) - _mux_cost(after), 0),
            )
        )

    baseline_cost = _total_mux_cost(baseline_connections)
    final_cost = _total_mux_cost(final_connections)
    return MuxCleanupStats(
        baseline_mux_cost=baseline_cost,
        final_mux_cost=final_cost,
        mux_cost_reduction=(
            (baseline_cost - final_cost) / baseline_cost if baseline_cost else 0.0
        ),
        rows_crossing_thresholds=len(changed_rows),
        direct_wire_conversions=sum(
            1 for row in changed_rows if row.bucket_after == "direct"
        ),
        config_bit_reduction=max(baseline_config_bits - final_config_bits, 0),
        non_power_of_two_mux_rows_before=_non_power_of_two_mux_count(
            baseline_connections
        ),
        non_power_of_two_mux_rows_after=_non_power_of_two_mux_count(final_connections),
        buckets=buckets,
        changed_rows=sorted(
            changed_rows,
            key=lambda row: (
                -row.mux_cost_saved,
                -row.config_bits_saved,
                -row.removed_pips,
                row.row,
            ),
        ),
    )


def _mux_bucket_histogram(connections: Connections) -> dict[str, int]:
    """Return row counts by mux implementation bucket.

    Parameters
    ----------
    connections : Connections
        Switch-matrix connections.

    Returns
    -------
    dict[str, int]
        Row counts keyed by bucket label.
    """
    histogram: dict[str, int] = {}
    for sources in connections.values():
        bucket = _mux_bucket_label(len(sources))
        histogram[bucket] = histogram.get(bucket, 0) + 1
    return histogram


def _total_mux_cost(connections: Connections) -> int:
    """Return estimated mux implementation cost for all rows.

    Parameters
    ----------
    connections : Connections
        Switch-matrix connections.

    Returns
    -------
    int
        Sum of padded mux input counts, with direct wires counted as zero.
    """
    return sum(_mux_cost(len(sources)) for sources in connections.values())


def _mux_bucket_label(fanin: int) -> str:
    """Return the implementation bucket label for one row fanin.

    Parameters
    ----------
    fanin : int
        Number of real row inputs.

    Returns
    -------
    str
        Mux bucket label.
    """
    cost = _mux_cost(fanin)
    if cost == 0:
        return "direct"
    if cost > 32:
        return "mux32+"
    return f"mux{cost}"


def _mux_cost(fanin: int) -> int:
    """Return padded mux input count for one row fanin.

    Parameters
    ----------
    fanin : int
        Number of real row inputs.

    Returns
    -------
    int
        Padded mux input count, or zero for direct/unused rows.
    """
    if fanin <= 1:
        return 0
    return 2 ** (fanin - 1).bit_length()


def _mux_config_bits(fanin: int) -> int:
    """Return selector bits needed for one row fanin.

    Parameters
    ----------
    fanin : int
        Number of real row inputs.

    Returns
    -------
    int
        Selector bit count.
    """
    if fanin <= 1:
        return 0
    return (fanin - 1).bit_length()


def _apply_to_tile_model(context: OptimizerContext, connections: Connections) -> None:
    """Apply optimized connections to the active in-memory tile model.

    Parameters
    ----------
    context : OptimizerContext
        Optimizer context.
    connections : Connections
        Accepted optimized connections.
    """
    matrix = _connections_to_delay_matrix(context.matrix, connections)
    context.fpga_model.set_switch_matrix(
        context.matrix.tile_name,
        list(context.matrix.columns),
        list(context.matrix.rows),
        matrix,
    )


def _connections_to_delay_matrix(
    matrix: MatrixData,
    connections: Connections,
) -> list[list[float]]:
    """Return a FabGraph delay matrix from local optimized connections.

    Parameters
    ----------
    matrix : MatrixData
        Baseline matrix metadata.
    connections : Connections
        Optimized connections.

    Returns
    -------
    list[list[float]]
        Delay matrix suitable for ``set_switch_matrix``.
    """
    column_index = {column: index for index, column in enumerate(matrix.columns)}
    result = [[0.0 for _column in matrix.columns] for _row in matrix.rows]
    for row_index, row in enumerate(matrix.rows):
        for source in connections.get(row, []):
            source_index = column_index.get(source)
            if source_index is None:
                continue
            result[row_index][source_index] = matrix.delay_by_row.get(row, {}).get(
                source,
                1.0,
            )
    return result


def _render_list(tile_name: str, connections: Connections) -> str:
    """Render FABulous list text for diagnostics and tests.

    Parameters
    ----------
    tile_name : str
        Tile name.
    connections : Connections
        Switch-matrix connections.

    Returns
    -------
    str
        List-file contents.
    """
    lines = [f"# Tile: {tile_name}", ""]
    for row, sources in connections.items():
        unique_sources = list(dict.fromkeys(sources))
        if not unique_sources:
            continue
        if len(unique_sources) == 1:
            lines.append(f"{row},{unique_sources[0]}")
        else:
            lines.append(f"{{{len(unique_sources)}}}{row},[{'|'.join(unique_sources)}]")
    return "\n".join(lines) + "\n"

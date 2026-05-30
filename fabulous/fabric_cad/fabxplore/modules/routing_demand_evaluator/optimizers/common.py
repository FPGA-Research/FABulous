"""Common helpers shared by routing-demand optimizers."""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from math import sqrt
from typing import TYPE_CHECKING

from fabulous.fabric_cad.fabxplore.modules.routing_demand_evaluator.core.routing_graph import (  # noqa: E501
    RoutingGraph,
    RoutingGraphBuilder,
)

if TYPE_CHECKING:
    from fabulous.fabric_cad.fabxplore.modules.routing_demand_evaluator.core.models import (  # noqa: E501
        MatrixData,
        RoutingDemandEvaluatorResult,
    )
    from fabulous.fabric_cad.fabxplore.modules.routing_demand_evaluator.optimizers.base import (  # noqa: E501
        OptimizerContext,
    )

Connections = dict[str, list[str]]
Pip = tuple[str, str]


@dataclass(frozen=True)
class UnreachableRepairResult:
    """Result from post-optimizer unreachable-demand repair.

    Attributes
    ----------
    result : RoutingDemandEvaluatorResult
        Evaluation result after repair.
    connections : Connections
        Switch-matrix connections after repair.
    restored_pips : int
        Number of baseline PIPs restored.
    rounds : int
        Repair rounds executed.
    """

    result: RoutingDemandEvaluatorResult
    connections: Connections
    restored_pips: int
    rounds: int


@dataclass(frozen=True)
class CongestionRelaxResult:
    """Result from post-optimizer congestion relaxation.

    Attributes
    ----------
    result : RoutingDemandEvaluatorResult
        Evaluation result after relaxation.
    connections : Connections
        Switch-matrix connections after relaxation.
    restored_pips : int
        Number of baseline PIPs restored.
    rounds : int
        Relaxation rounds executed.
    """

    result: RoutingDemandEvaluatorResult
    connections: Connections
    restored_pips: int
    rounds: int


def repair_unreachable_demands(
    context: OptimizerContext,
    baseline_connections: Connections,
    optimized_connections: Connections,
    result: RoutingDemandEvaluatorResult,
) -> UnreachableRepairResult:
    """Restore baseline PIPs needed by unreachable failed demands.

    Parameters
    ----------
    context : OptimizerContext
        Optimizer context.
    baseline_connections : Connections
        Baseline switch-matrix connections before optimization.
    optimized_connections : Connections
        Optimized switch-matrix connections to repair.
    result : RoutingDemandEvaluatorResult
        Evaluation result for ``optimized_connections``.

    Returns
    -------
    UnreachableRepairResult
        Repaired result, repaired connections, and repair counters.
    """
    if not context.options.repair_unreachable_demands:
        return UnreachableRepairResult(
            result=result,
            connections=optimized_connections,
            restored_pips=0,
            rounds=0,
        )

    connections = copy_connections(optimized_connections)
    baseline_graph = build_graph(context.matrix, baseline_connections)
    current = result
    rounds = 0
    restored_total = 0
    max_rounds = context.options.repair_max_rounds
    repair_name = "unreachable"
    context.tracker.repair_start(
        repair_name,
        max_rounds,
        len(_failed_sink_pairs(current)),
    )

    while failed_pairs := _failed_sink_pairs(current):
        if max_rounds is not None and rounds >= max_rounds:
            break
        rounds += 1
        restored = _restore_failed_pairs(
            baseline_graph=baseline_graph,
            baseline_connections=baseline_connections,
            connections=connections,
            pairs=failed_pairs,
        )
        if restored == 0:
            break

        restored_total += restored
        context.tracker.evaluation_start(
            f"unreachable-demand repair round {rounds} ({restored} PIPs)"
        )
        current = context.evaluate(
            build_graph(context.matrix, connections),
            [],
            track_router=True,
        )
        context.tracker.repair_round(
            repair_name,
            rounds,
            restored,
            current.stats.failed_sinks,
            current.router_stats.congested_resources,
            current.router_stats.max_resource_usage,
        )

    if restored_total:
        current = _with_note(
            current,
            (
                "Unreachable-demand repair restored "
                f"{restored_total} baseline PIP(s) in {rounds} round(s)."
            ),
        )
    context.tracker.repair_done(
        repair_name,
        rounds,
        restored_total,
        current.stats.failed_sinks,
        current.router_stats.congested_resources,
        current.router_stats.max_resource_usage,
    )
    return UnreachableRepairResult(
        result=current,
        connections=connections,
        restored_pips=restored_total,
        rounds=rounds,
    )


def relax_congestion(
    context: OptimizerContext,
    baseline_connections: Connections,
    optimized_connections: Connections,
    result: RoutingDemandEvaluatorResult,
) -> CongestionRelaxResult:
    """Restore baseline PIPs that offer alternatives around congested resources.

    Parameters
    ----------
    context : OptimizerContext
        Optimizer context.
    baseline_connections : Connections
        Baseline switch-matrix connections before optimization.
    optimized_connections : Connections
        Optimized switch-matrix connections to relax.
    result : RoutingDemandEvaluatorResult
        Evaluation result for ``optimized_connections``.

    Returns
    -------
    CongestionRelaxResult
        Relaxed result, relaxed connections, and relaxation counters.
    """
    if not context.options.relax_congestion:
        return CongestionRelaxResult(
            result=result,
            connections=optimized_connections,
            restored_pips=0,
            rounds=0,
        )

    connections = copy_connections(optimized_connections)
    baseline_graph = build_graph(context.matrix, baseline_connections)
    current = result
    rounds = 0
    restored_total = 0
    max_rounds = context.options.relax_congestion_max_rounds
    capacity = context.options.router_base_resource_capacity
    initial_congestion = _congested_intermediate_resources(current, capacity)
    initial_congested_count = len(initial_congestion)
    initial_max_usage = _max_usage(initial_congestion)
    repair_name = "congestion"
    context.tracker.repair_start(
        repair_name,
        max_rounds,
        initial_congested_count,
    )

    current_score = _congestion_score(current, capacity)
    while congestion := _congested_intermediate_resources(current, capacity):
        if max_rounds is not None and rounds >= max_rounds:
            break
        candidate_connections = copy_connections(connections)
        congested_nodes = _selected_congested_nodes(congestion)
        pairs = _path_pairs_through_resources(current, set(congested_nodes))
        restored = _restore_congestion_alternates(
            baseline_graph=baseline_graph,
            baseline_connections=baseline_connections,
            connections=candidate_connections,
            congested_nodes=congested_nodes,
            pairs=pairs,
        )
        if restored == 0:
            break

        candidate_round = rounds + 1
        context.tracker.evaluation_start(
            f"congestion relaxation round {candidate_round} ({restored} PIPs)"
        )
        candidate = context.evaluate(
            build_graph(context.matrix, candidate_connections),
            [],
            track_router=True,
        )
        candidate_score = _congestion_score(candidate, capacity)
        if candidate_score >= current_score:
            break

        rounds = candidate_round
        restored_total += restored
        connections = candidate_connections
        current = candidate
        current_score = candidate_score
        context.tracker.repair_round(
            repair_name,
            rounds,
            restored,
            current.stats.failed_sinks,
            current.router_stats.congested_resources,
            current.router_stats.max_resource_usage,
        )

    if restored_total:
        final_congestion = _congested_intermediate_resources(current, capacity)
        current = _with_note(
            current,
            (
                "Congestion relaxation restored "
                f"{restored_total} baseline PIP(s) in {rounds} round(s); "
                f"congested resources {initial_congested_count} -> "
                f"{len(final_congestion)}, max usage {initial_max_usage} -> "
                f"{_max_usage(final_congestion)}."
            ),
        )
    context.tracker.repair_done(
        repair_name,
        rounds,
        restored_total,
        current.stats.failed_sinks,
        current.router_stats.congested_resources,
        current.router_stats.max_resource_usage,
    )
    return CongestionRelaxResult(
        result=current,
        connections=connections,
        restored_pips=restored_total,
        rounds=rounds,
    )


def copy_connections(connections: Connections) -> Connections:
    """Return a deep copy of switch-matrix connections.

    Parameters
    ----------
    connections : Connections
        Switch-matrix connections.

    Returns
    -------
    Connections
        Copied connections.
    """
    return {row: list(sources) for row, sources in connections.items()}


def build_graph(matrix: MatrixData, connections: Connections) -> RoutingGraph:
    """Build a routing graph from switch-matrix connections.

    Parameters
    ----------
    matrix : MatrixData
        Matrix metadata.
    connections : Connections
        Switch-matrix connections.

    Returns
    -------
    RoutingGraph
        Routing graph with matrix PIPs and fixed JUMP edges.
    """
    builder = RoutingGraphBuilder()
    builder.add_connection_rows(connections)
    builder.add_jump_edges(matrix.jump_edges)
    return builder.build()


def routing_pip_count(connections: Connections) -> int:
    """Return the number of switch-matrix PIPs.

    Parameters
    ----------
    connections : Connections
        Switch-matrix connections.

    Returns
    -------
    int
        PIP count.
    """
    return sum(len(sources) for sources in connections.values())


def _failed_sink_pairs(
    result: RoutingDemandEvaluatorResult,
) -> list[tuple[str, str]]:
    """Return unique source/sink pairs that failed as unreachable.

    Parameters
    ----------
    result : RoutingDemandEvaluatorResult
        Evaluation result.

    Returns
    -------
    list[tuple[str, str]]
        Failed source/sink pairs.
    """
    pairs: list[tuple[str, str]] = []
    seen: set[tuple[str, str]] = set()
    for demand_result in result.demand_results:
        if demand_result.routed:
            continue
        for sink in demand_result.failed_sinks:
            pair = (demand_result.demand.source, sink)
            if pair in seen:
                continue
            seen.add(pair)
            pairs.append(pair)
    return pairs


def _restore_failed_pairs(
    baseline_graph: RoutingGraph,
    baseline_connections: Connections,
    connections: Connections,
    pairs: list[tuple[str, str]],
) -> int:
    """Restore baseline path PIPs for failed source/sink pairs.

    Parameters
    ----------
    baseline_graph : RoutingGraph
        Graph built from baseline connections.
    baseline_connections : Connections
        Baseline switch-matrix connections.
    connections : Connections
        Mutable optimized connections.
    pairs : list[tuple[str, str]]
        Failed source/sink pairs to repair.

    Returns
    -------
    int
        Number of restored PIPs.
    """
    restored = 0
    for source, sink in pairs:
        path = baseline_graph.shortest_path(source, sink)
        if path is None:
            continue
        nodes, _cost = path
        for pip_source, pip_sink in zip(nodes, nodes[1:], strict=False):
            restored += _restore_pip(
                baseline_connections,
                connections,
                (pip_source, pip_sink),
            )
    return restored


def _restore_congestion_alternates(
    baseline_graph: RoutingGraph,
    baseline_connections: Connections,
    connections: Connections,
    congested_nodes: list[str],
    pairs: list[tuple[str, str]],
) -> int:
    """Restore alternate baseline paths around congested resources.

    Parameters
    ----------
    baseline_graph : RoutingGraph
        Graph built from baseline connections.
    baseline_connections : Connections
        Baseline switch-matrix connections.
    connections : Connections
        Mutable optimized connections.
    congested_nodes : list[str]
        Congested resource names to penalize.
    pairs : list[tuple[str, str]]
        Source/sink pairs whose current paths cross congested resources.

    Returns
    -------
    int
        Number of restored PIPs.
    """
    node_costs = _node_penalties(baseline_graph, congested_nodes)
    restored = 0
    for source, sink in pairs:
        path = baseline_graph.shortest_path(source, sink, node_costs)
        if path is None:
            continue
        nodes, _cost = path
        for pip_source, pip_sink in zip(nodes, nodes[1:], strict=False):
            restored += _restore_pip(
                baseline_connections,
                connections,
                (pip_source, pip_sink),
            )
    return restored


def _restore_pip(
    baseline_connections: Connections,
    connections: Connections,
    pip: Pip,
) -> int:
    """Restore one PIP if it is present in the baseline matrix.

    Parameters
    ----------
    baseline_connections : Connections
        Baseline switch-matrix connections.
    connections : Connections
        Mutable optimized connections.
    pip : Pip
        Candidate ``source, sink`` PIP.

    Returns
    -------
    int
        ``1`` if the PIP was restored, otherwise ``0``.
    """
    source, row = pip
    baseline_sources = baseline_connections.get(row)
    if baseline_sources is None or source not in baseline_sources:
        return 0
    sources = connections.setdefault(row, [])
    if source in sources:
        return 0
    sources.append(source)
    _sort_like_baseline(sources, baseline_sources)
    return 1


def _congested_intermediate_resources(
    result: RoutingDemandEvaluatorResult,
    capacity: int,
) -> list[tuple[str, int]]:
    """Return over-capacity intermediate routing resources.

    Parameters
    ----------
    result : RoutingDemandEvaluatorResult
        Evaluation result.
    capacity : int
        Resource capacity.

    Returns
    -------
    list[tuple[str, int]]
        Congested resource names and usage counts, sorted by decreasing usage.
    """
    usage: Counter[str] = Counter()
    for demand_result in result.demand_results:
        for path in demand_result.paths:
            usage.update(path.nodes[1:-1])
    return sorted(
        ((resource, count) for resource, count in usage.items() if count > capacity),
        key=lambda item: (-item[1], item[0]),
    )


def _selected_congested_nodes(
    congestion: list[tuple[str, int]],
) -> list[str]:
    """Return a bounded set of high-pressure congested resources.

    Parameters
    ----------
    congestion : list[tuple[str, int]]
        Congested resources and usage counts.

    Returns
    -------
    list[str]
        Selected resource names.
    """
    limit = min(32, max(4, round(sqrt(len(congestion)))))
    return [resource for resource, _count in congestion[:limit]]


def _path_pairs_through_resources(
    result: RoutingDemandEvaluatorResult,
    resources: set[str],
) -> list[tuple[str, str]]:
    """Return routed source/sink pairs whose paths cross selected resources.

    Parameters
    ----------
    result : RoutingDemandEvaluatorResult
        Evaluation result.
    resources : set[str]
        Congested resource names.

    Returns
    -------
    list[tuple[str, str]]
        Unique source/sink pairs.
    """
    max_pairs = max(16, min(128, len(resources) * 8))
    pairs: list[tuple[str, str]] = []
    seen: set[tuple[str, str]] = set()
    for demand_result in result.demand_results:
        for path in demand_result.paths:
            nodes = path.nodes
            if not set(nodes[1:-1]) & resources:
                continue
            pair = (nodes[0], nodes[-1])
            if pair in seen:
                continue
            seen.add(pair)
            pairs.append(pair)
            if len(pairs) >= max_pairs:
                return pairs
    return pairs


def _node_penalties(
    graph: RoutingGraph,
    congested_nodes: list[str],
) -> dict[int, float]:
    """Return Dijkstra node penalties for congested resources.

    Parameters
    ----------
    graph : RoutingGraph
        Baseline routing graph.
    congested_nodes : list[str]
        Resource names to avoid when possible.

    Returns
    -------
    dict[int, float]
        Penalties keyed by node id.
    """
    return {
        graph.node_to_id[node]: 1000.0
        for node in congested_nodes
        if node in graph.node_to_id
    }


def _congestion_score(
    result: RoutingDemandEvaluatorResult,
    capacity: int,
) -> tuple[int, int]:
    """Return the congestion objective minimized by relaxation.

    Parameters
    ----------
    result : RoutingDemandEvaluatorResult
        Evaluation result.
    capacity : int
        Resource capacity.

    Returns
    -------
    tuple[int, int]
        Score tuple ``(max_usage, congested_resource_count)``.
    """
    congestion = _congested_intermediate_resources(result, capacity)
    return (_max_usage(congestion), len(congestion))


def _max_usage(congestion: list[tuple[str, int]]) -> int:
    """Return maximum usage from a congestion list.

    Parameters
    ----------
    congestion : list[tuple[str, int]]
        Congested resources and usage counts.

    Returns
    -------
    int
        Maximum usage count.
    """
    return max((count for _resource, count in congestion), default=0)


def _sort_like_baseline(sources: list[str], baseline_sources: list[str]) -> None:
    """Sort restored sources in their baseline row order.

    Parameters
    ----------
    sources : list[str]
        Mutable source list.
    baseline_sources : list[str]
        Baseline source order for the row.
    """
    order = {source: index for index, source in enumerate(baseline_sources)}
    sources.sort(key=lambda source: order.get(source, len(order)))


def _with_note(
    result: RoutingDemandEvaluatorResult,
    note: str,
) -> RoutingDemandEvaluatorResult:
    """Attach a summary note to an evaluation result.

    Parameters
    ----------
    result : RoutingDemandEvaluatorResult
        Evaluation result.
    note : str
        Note text.

    Returns
    -------
    RoutingDemandEvaluatorResult
        Result with note appended to warnings.
    """
    return result.model_copy(
        update={
            "warnings": [
                *result.warnings,
                note,
            ]
        }
    )

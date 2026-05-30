"""Routing-demand evaluator orchestration."""

from __future__ import annotations

from collections import defaultdict
from typing import TYPE_CHECKING

from fabulous.fabric_cad.fabxplore.modules.routing_demand_evaluator.core.matrix_loader import (  # noqa: E501
    load_matrix_data,
)
from fabulous.fabric_cad.fabxplore.modules.routing_demand_evaluator.core.models import (
    DemandClassName,
    DemandClassStats,
    DemandKind,
    DemandProfileResult,
    DemandRouteResult,
    MatrixData,
    RandomDemandBucketStats,
    RoutingDemandEvaluationStats,
    RoutingDemandEvaluatorOptions,
    RoutingDemandEvaluatorResult,
)
from fabulous.fabric_cad.fabxplore.modules.routing_demand_evaluator.core.process_tracker import (  # noqa: E501
    RoutingDemandProcessTracker,
)
from fabulous.fabric_cad.fabxplore.modules.routing_demand_evaluator.core.report import (
    render_routing_demand_report,
)
from fabulous.fabric_cad.fabxplore.modules.routing_demand_evaluator.core.routing_graph import (  # noqa: E501
    RoutingGraph,
    RoutingGraphBuilder,
)
from fabulous.fabric_cad.fabxplore.modules.routing_demand_evaluator.demand_classes import (  # noqa: E501
    random as random_demands,
)
from fabulous.fabric_cad.fabxplore.modules.routing_demand_evaluator.demand_profiles import (  # noqa: E501
    generate_demand_profile,
)
from fabulous.fabric_cad.fabxplore.modules.routing_demand_evaluator.optimizers import (
    OptimizerContext,
    create_optimizer,
)
from fabulous.fabric_cad.fabxplore.modules.routing_demand_evaluator.routers import (
    create_router,
)

if TYPE_CHECKING:
    from fabulous.fabric_cad.fabxplore.modules.routing_demand_evaluator.routers.base import (  # noqa: E501
        RoutingDemandRouter,
    )
    from fabulous.fabric_cad.fabxplore.pnr.pnr_bridge import PnRBridge


class RoutingDemandEvaluator:
    """Evaluate synthetic routing demands against a FABulous switch matrix.

    Parameters
    ----------
    options : RoutingDemandEvaluatorOptions
        Normalized evaluator options.
    """

    def __init__(self, options: RoutingDemandEvaluatorOptions) -> None:
        self.options = options

    def run(self, fpga_model: PnRBridge) -> RoutingDemandEvaluatorResult:
        """Run demand evaluation.

        Parameters
        ----------
        fpga_model : PnRBridge
            Combined packed design, FABulous project API, and routing graph.

        Returns
        -------
        RoutingDemandEvaluatorResult
            Structured result and report.
        """
        tracker = RoutingDemandProcessTracker(
            enabled=self.options.track_progress,
            chunk_size=self.options.progress_chunk_size,
        )
        tracker.start(self.options.tile_name)

        matrix = load_matrix_data(self.options, fpga_model)
        graph = build_graph(matrix)
        tracker.loaded_matrix(matrix.matrix_source, _routing_pip_count(matrix))

        profile = generate_demand_profile(self.options, matrix, graph, tracker)
        tracker.generated_demands(len(profile.demands))
        router = create_router(self.options)

        def evaluate(
            candidate_graph: RoutingGraph,
            warnings: list[str],
            *,
            track_router: bool = False,
        ) -> RoutingDemandEvaluatorResult:
            return evaluate_graph(
                options=self.options,
                matrix=matrix,
                graph=candidate_graph,
                demand_profile=profile,
                router=router,
                warnings=profile.warnings + warnings,
                tracker=tracker if track_router else None,
            )

        optimizer = create_optimizer(self.options)
        result = optimizer.optimize(
            OptimizerContext(
                options=self.options,
                matrix=matrix,
                graph=graph,
                demand_profile=profile,
                router=router,
                fpga_model=fpga_model,
                tracker=tracker,
                warnings=profile.warnings,
                evaluate=evaluate,
            )
        )
        tracker.done(result.stats.hard_failed, result.stats.soft_failed)
        return result


def build_graph(matrix: MatrixData) -> RoutingGraph:
    """Build a routing graph from matrix data.

    Parameters
    ----------
    matrix : MatrixData
        Loaded matrix data.

    Returns
    -------
    RoutingGraph
        Routing graph.
    """
    builder = RoutingGraphBuilder()
    builder.add_connection_rows(matrix.connections)
    builder.add_jump_edges(matrix.jump_edges)
    return builder.build()


def evaluate_graph(
    options: RoutingDemandEvaluatorOptions,
    matrix: MatrixData,
    graph: RoutingGraph,
    demand_profile: DemandProfileResult,
    router: RoutingDemandRouter,
    warnings: list[str],
    tracker: RoutingDemandProcessTracker | None = None,
) -> RoutingDemandEvaluatorResult:
    """Evaluate a graph against generated demands.

    Parameters
    ----------
    options : RoutingDemandEvaluatorOptions
        Evaluator options.
    matrix : MatrixData
        Loaded matrix metadata.
    graph : RoutingGraph
        Routing graph to evaluate.
    demand_profile : DemandProfileResult
        Generated demand profile.
    router : RoutingDemandRouter
        Router implementation.
    warnings : list[str]
        Warnings to include in the result.
    tracker : RoutingDemandProcessTracker | None
        Optional progress tracker for top-level routing.

    Returns
    -------
    RoutingDemandEvaluatorResult
        Evaluation result.
    """
    router_result = router.route(graph, demand_profile.demands, tracker=tracker)
    result = RoutingDemandEvaluatorResult(
        options=options,
        matrix=matrix,
        demand_profile=demand_profile,
        demand_results=router_result.demand_results,
        stats=_evaluation_stats(
            matrix=matrix,
            graph=graph,
            demand_results=router_result.demand_results,
        ),
        class_stats=_class_stats(router_result.demand_results),
        router_stats=router_result.router_stats,
        resource_usage=router_result.resource_usage,
        pip_usage=router_result.pip_usage,
        warnings=list(warnings),
        random_bucket_stats=_random_bucket_stats(
            matrix=matrix,
            graph=graph,
            demand_results=router_result.demand_results,
        ),
    )
    return result.model_copy(
        update={"report_summary": render_routing_demand_report(result)}
    )


def _evaluation_stats(
    matrix: MatrixData,
    graph: RoutingGraph,
    demand_results: list[DemandRouteResult],
) -> RoutingDemandEvaluationStats:
    """Build top-level evaluation statistics.

    Parameters
    ----------
    matrix : MatrixData
        Matrix metadata.
    graph : RoutingGraph
        Evaluated routing graph.
    demand_results : list[DemandRouteResult]
        Demand route results.

    Returns
    -------
    RoutingDemandEvaluationStats
        Top-level statistics.
    """
    hard_results = [
        result for result in demand_results if result.demand.kind == DemandKind.HARD
    ]
    soft_results = [
        result for result in demand_results if result.demand.kind == DemandKind.SOFT
    ]
    path_lengths = [
        max(len(path.nodes) - 1, 0)
        for result in demand_results
        for path in result.paths
    ]
    original_routing_pips = _routing_pip_count(matrix)
    jump_wires = len(matrix.jump_edges)
    final_graph_edges = len(graph.edges())
    final_routing_pips = max(final_graph_edges - jump_wires, 0)
    original_graph_edges = original_routing_pips + jump_wires
    return RoutingDemandEvaluationStats(
        total_demands=len(demand_results),
        hard_demands=len(hard_results),
        soft_demands=len(soft_results),
        hard_failed=sum(1 for result in hard_results if not result.routed),
        soft_failed=sum(1 for result in soft_results if not result.routed),
        failed_sinks=sum(len(result.failed_sinks) for result in demand_results),
        original_pips=original_graph_edges,
        final_pips=final_graph_edges,
        original_routing_pips=original_routing_pips,
        final_routing_pips=final_routing_pips,
        jump_wires=jump_wires,
        original_graph_edges=original_graph_edges,
        final_graph_edges=final_graph_edges,
        matrix_config_bits=matrix.matrix_config_bits,
        total_config_bits=matrix.total_config_bits,
        config_capacity=matrix.config_capacity,
        average_path_length=(
            sum(path_lengths) / len(path_lengths) if path_lengths else 0.0
        ),
    )


def _class_stats(demand_results: list[DemandRouteResult]) -> list[DemandClassStats]:
    """Build demand-class statistics.

    Parameters
    ----------
    demand_results : list[DemandRouteResult]
        Demand route results.

    Returns
    -------
    list[DemandClassStats]
        Per-class statistics.
    """
    grouped: dict[tuple[str, DemandKind], list[DemandRouteResult]] = defaultdict(list)
    for result in demand_results:
        grouped[(result.demand.demand_class, result.demand.kind)].append(result)

    stats: list[DemandClassStats] = []
    for (demand_class, kind), results in sorted(grouped.items()):
        path_lengths = [
            max(len(path.nodes) - 1, 0) for result in results for path in result.paths
        ]
        stats.append(
            DemandClassStats(
                demand_class=demand_class,
                kind=kind,
                total=len(results),
                passed=sum(1 for result in results if result.routed),
                failed=sum(1 for result in results if not result.routed),
                average_path_length=(
                    sum(path_lengths) / len(path_lengths) if path_lengths else 0.0
                ),
            )
        )
    return stats


def _random_bucket_stats(
    matrix: MatrixData,
    graph: RoutingGraph,
    demand_results: list[DemandRouteResult],
) -> list[RandomDemandBucketStats]:
    """Build candidate statistics for random demand buckets.

    Parameters
    ----------
    matrix : MatrixData
        Matrix metadata.
    graph : RoutingGraph
        Evaluated routing graph.
    demand_results : list[DemandRouteResult]
        Demand route results.

    Returns
    -------
    list[RandomDemandBucketStats]
        Random bucket statistics.
    """
    generated_counts = defaultdict(int)
    for result in demand_results:
        generated_counts[result.demand.demand_class] += 1
    buckets = [
        (DemandClassName.RANDOM_LOCAL, "local"),
        (DemandClassName.RANDOM_MEDIUM, "medium"),
        (DemandClassName.RANDOM_LONG, "long"),
    ]
    stats: list[RandomDemandBucketStats] = []
    for demand_class, distance in buckets:
        candidate_count, reachable_count = (
            random_demands.random_bucket_candidate_counts(
                matrix,
                graph,
                distance,
            )
        )
        stats.append(
            RandomDemandBucketStats(
                demand_class=demand_class,
                candidate_pairs=candidate_count,
                reachable_pairs=reachable_count,
                generated_demands=generated_counts[demand_class],
            )
        )
    return stats


def _routing_pip_count(matrix: MatrixData) -> int:
    """Count selectable switch-matrix routing PIPs.

    Parameters
    ----------
    matrix : MatrixData
        Matrix metadata.

    Returns
    -------
    int
        Routing PIP count.
    """
    return sum(len(sources) for sources in matrix.connections.values())

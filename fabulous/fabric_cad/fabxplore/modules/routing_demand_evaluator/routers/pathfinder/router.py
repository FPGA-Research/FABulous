"""PathFinder-style negotiated congestion router."""

from __future__ import annotations

from collections import Counter
from time import perf_counter
from typing import TYPE_CHECKING

from fabulous.fabric_cad.fabxplore.modules.routing_demand_evaluator.core.models import (
    DemandRouteResult,
    RoutedPath,
    RouterRunStats,
    RoutingDemand,
)
from fabulous.fabric_cad.fabxplore.modules.routing_demand_evaluator.routers.base import (  # noqa: E501
    RouterResult,
    RoutingDemandRouter,
)

if TYPE_CHECKING:
    from fabulous.fabric_cad.fabxplore.modules.routing_demand_evaluator.core.process_tracker import (  # noqa: E501
        RoutingDemandProcessTracker,
    )
    from fabulous.fabric_cad.fabxplore.modules.routing_demand_evaluator.core.routing_graph import (  # noqa: E501
        RoutingGraph,
    )


class PathFinderRouter(RoutingDemandRouter):
    """Route demands with PathFinder-style negotiated congestion.

    Parameters
    ----------
    max_iterations : int
        Maximum negotiation iterations.
    present_cost_multiplier : float
        Multiplier for present congestion costs.
    history_cost_increment : float
        Historical cost increment for overused resources.
    resource_capacity : int
        Default node capacity before congestion is reported.
    """

    def __init__(
        self,
        max_iterations: int,
        present_cost_multiplier: float,
        history_cost_increment: float,
        resource_capacity: int = 1,
    ) -> None:
        self.max_iterations = max_iterations
        self.present_cost_multiplier = present_cost_multiplier
        self.history_cost_increment = history_cost_increment
        self.resource_capacity = resource_capacity

    def route(
        self,
        graph: RoutingGraph,
        demands: list[RoutingDemand],
        tracker: RoutingDemandProcessTracker | None = None,
    ) -> RouterResult:
        """Route demands on a graph.

        Parameters
        ----------
        graph : RoutingGraph
            Routing-resource graph.
        demands : list[RoutingDemand]
            Demands to route.
        tracker : RoutingDemandProcessTracker | None
            Optional progress tracker.

        Returns
        -------
        RouterResult
            Router result bundle.
        """
        history: Counter[int] = Counter()
        previous_usage: Counter[int] = Counter()
        final_results: list[DemandRouteResult] = []
        final_usage: Counter[str] = Counter()
        final_pip_usage: Counter[str] = Counter()
        congested_resources = 0
        max_resource_usage = 0
        iterations_used = 0
        failed_sinks = 0

        if tracker is not None:
            tracker.routing_start(len(demands), self.max_iterations)
        for iteration in range(1, self.max_iterations + 1):
            iterations_used = iteration
            if tracker is not None:
                tracker.routing_iteration_start(
                    iteration,
                    self.max_iterations,
                    len(demands),
                )
            started_at = perf_counter()
            node_costs = self._node_costs(history, previous_usage, iteration)
            final_results = [
                self._route_one_net(graph, demand, node_costs) for demand in demands
            ]
            previous_usage = self._usage_by_id(graph, final_results)
            congested = [
                node
                for node, count in previous_usage.items()
                if count > self.resource_capacity
            ]
            congested_resources = len(congested)
            max_resource_usage = max(previous_usage.values(), default=0)
            failed_sinks = sum(len(result.failed_sinks) for result in final_results)
            if tracker is not None:
                tracker.routing_iteration_done(
                    iteration,
                    self.max_iterations,
                    failed_sinks,
                    congested_resources,
                    max_resource_usage,
                    perf_counter() - started_at,
                )
            if not congested and failed_sinks == 0:
                break
            for node in congested:
                history[node] += 1

        final_usage = self._usage_by_name(final_results)
        final_pip_usage = self._pip_usage(final_results)
        if tracker is not None:
            tracker.routing_done(
                iterations_used,
                failed_sinks,
                congested_resources,
                max_resource_usage,
            )
        return RouterResult(
            demand_results=final_results,
            router_stats=RouterRunStats(
                iterations_used=iterations_used,
                congested_resources=congested_resources,
                max_resource_usage=max_resource_usage,
                failed_sinks=failed_sinks,
            ),
            resource_usage=dict(final_usage),
            pip_usage=dict(final_pip_usage),
        )

    def _node_costs(
        self,
        history: Counter[int],
        previous_usage: Counter[int],
        iteration: int,
    ) -> dict[int, float]:
        """Return node costs for one iteration.

        Parameters
        ----------
        history : Counter[int]
            Historical overuse counts.
        previous_usage : Counter[int]
            Usage from the previous routing iteration.
        iteration : int
            Current iteration number.

        Returns
        -------
        dict[int, float]
            Extra node costs.
        """
        present_factor = self.present_cost_multiplier ** max(iteration - 1, 0)
        nodes = set(history) | set(previous_usage)
        return {
            node: (history[node] * self.history_cost_increment)
            + (max(previous_usage[node] - 1, 0) * present_factor)
            for node in nodes
        }

    def _route_one_net(
        self,
        graph: RoutingGraph,
        demand: RoutingDemand,
        node_costs: dict[int, float],
    ) -> DemandRouteResult:
        """Route one net demand.

        Parameters
        ----------
        graph : RoutingGraph
            Routing-resource graph.
        demand : RoutingDemand
            Demand to route.
        node_costs : dict[int, float]
            Extra node costs.

        Returns
        -------
        DemandRouteResult
            Demand route result.
        """
        paths: list[RoutedPath] = []
        failed_sinks: list[str] = []
        route_tree = [demand.source]
        for sink in demand.sinks:
            path = graph.shortest_path_to_any(route_tree, sink, node_costs)
            if path is None:
                failed_sinks.append(sink)
                continue
            nodes, cost = path
            routed_path = RoutedPath(
                demand_id=demand.demand_id,
                nodes=nodes,
                cost=cost,
            )
            paths.append(routed_path)
            route_tree.extend(nodes)

        if failed_sinks:
            return DemandRouteResult(
                demand=demand,
                routed=False,
                paths=paths,
                path=paths[0] if paths else None,
                failed_sinks=failed_sinks,
                failure_reason="unreachable",
            )
        return DemandRouteResult(
            demand=demand,
            routed=True,
            path=paths[0] if paths else None,
            paths=paths,
        )

    def _usage_by_id(
        self,
        graph: RoutingGraph,
        results: list[DemandRouteResult],
    ) -> Counter[int]:
        """Count intermediate resource usage by node id.

        Parameters
        ----------
        graph : RoutingGraph
            Routing-resource graph.
        results : list[DemandRouteResult]
            Demand route results.

        Returns
        -------
        Counter[int]
            Usage counts.
        """
        usage: Counter[int] = Counter()
        for result in results:
            if not result.path:
                continue
            for path in result.paths:
                for node in path.nodes[1:-1]:
                    usage[graph.node_to_id[node]] += 1
        return usage

    def _usage_by_name(self, results: list[DemandRouteResult]) -> Counter[str]:
        """Count routed resource usage by node name.

        Parameters
        ----------
        results : list[DemandRouteResult]
            Demand route results.

        Returns
        -------
        Counter[str]
            Usage counts.
        """
        usage: Counter[str] = Counter()
        for result in results:
            for path in result.paths:
                usage.update(path.nodes)
        return usage

    def _pip_usage(self, results: list[DemandRouteResult]) -> Counter[str]:
        """Count routed PIP usage.

        Parameters
        ----------
        results : list[DemandRouteResult]
            Demand route results.

        Returns
        -------
        Counter[str]
            PIP usage keyed by ``source->sink``.
        """
        usage: Counter[str] = Counter()
        for result in results:
            for path in result.paths:
                nodes = path.nodes
                for source, sink in zip(nodes, nodes[1:], strict=False):
                    usage[f"{source}->{sink}"] += 1
        return usage

"""Base router interface for routing-demand evaluation."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from fabulous.fabric_cad.fabxplore.modules.routing_demand_evaluator.core.models import (  # noqa: E501
        DemandRouteResult,
        RouterRunStats,
        RoutingDemand,
    )
    from fabulous.fabric_cad.fabxplore.modules.routing_demand_evaluator.core.process_tracker import (  # noqa: E501
        RoutingDemandProcessTracker,
    )
    from fabulous.fabric_cad.fabxplore.modules.routing_demand_evaluator.core.routing_graph import (  # noqa: E501
        RoutingGraph,
    )


class RouterResult:
    """Router result bundle.

    Parameters
    ----------
    demand_results : list[DemandRouteResult]
        Per-demand route results.
    router_stats : RouterRunStats
        Router statistics.
    resource_usage : dict[str, int]
        Resource usage by node name.
    pip_usage : dict[str, int]
        PIP usage by ``source->sink`` string.
    """

    def __init__(
        self,
        demand_results: list[DemandRouteResult],
        router_stats: RouterRunStats,
        resource_usage: dict[str, int],
        pip_usage: dict[str, int],
    ) -> None:
        self.demand_results = demand_results
        self.router_stats = router_stats
        self.resource_usage = resource_usage
        self.pip_usage = pip_usage


class RoutingDemandRouter(ABC):
    """Abstract routing-demand router."""

    @abstractmethod
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

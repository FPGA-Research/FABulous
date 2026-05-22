"""Router registry for routing-demand evaluation."""

from __future__ import annotations

from typing import TYPE_CHECKING

from fabulous.fabric_cad.fabxplore.modules.routing_demand_evaluator.core.models import (
    RouterName,
    RoutingDemandEvaluatorOptions,
)
from fabulous.fabric_cad.fabxplore.modules.routing_demand_evaluator.routers.pathfinder.router import (  # noqa: E501
    PathFinderRouter,
)

if TYPE_CHECKING:
    from fabulous.fabric_cad.fabxplore.modules.routing_demand_evaluator.routers.base import (  # noqa: E501
        RoutingDemandRouter,
    )


def create_router(options: RoutingDemandEvaluatorOptions) -> RoutingDemandRouter:
    """Create a router from evaluator options.

    Parameters
    ----------
    options : RoutingDemandEvaluatorOptions
        Evaluator options.

    Returns
    -------
    RoutingDemandRouter
        Router implementation.

    Raises
    ------
    ValueError
        If the router is unknown.
    """
    match options.router:
        case RouterName.PATHFINDER:
            return PathFinderRouter(
                max_iterations=options.router_max_iterations,
                present_cost_multiplier=options.router_present_cost_multiplier,
                history_cost_increment=options.router_history_cost_increment,
                resource_capacity=options.router_base_resource_capacity,
            )
        case _:
            raise ValueError(f"Unknown router: {options.router}")

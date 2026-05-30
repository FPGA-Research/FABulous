"""Demand-profile registry."""

from __future__ import annotations

from random import Random
from typing import TYPE_CHECKING

from fabulous.fabric_cad.fabxplore.modules.routing_demand_evaluator.core.models import (
    DemandProfileName,
    DemandProfileResult,
    RoutingDemandEvaluatorOptions,
)
from fabulous.fabric_cad.fabxplore.modules.routing_demand_evaluator.demand_profiles.control_stress.profile import (  # noqa: E501
    generate_control_stress_profile,
)
from fabulous.fabric_cad.fabxplore.modules.routing_demand_evaluator.demand_profiles.default.profile import (  # noqa: E501
    generate_default_profile,
)
from fabulous.fabric_cad.fabxplore.modules.routing_demand_evaluator.demand_profiles.full.profile import (  # noqa: E501
    generate_full_profile,
)
from fabulous.fabric_cad.fabxplore.modules.routing_demand_evaluator.demand_profiles.minimal.profile import (  # noqa: E501
    generate_minimal_profile,
)
from fabulous.fabric_cad.fabxplore.modules.routing_demand_evaluator.demand_profiles.routing_stress.profile import (  # noqa: E501
    generate_routing_stress_profile,
)

if TYPE_CHECKING:
    from fabulous.fabric_cad.fabxplore.modules.routing_demand_evaluator.core.models import (  # noqa: E501
        MatrixData,
    )
    from fabulous.fabric_cad.fabxplore.modules.routing_demand_evaluator.core.process_tracker import (  # noqa: E501
        RoutingDemandProcessTracker,
    )
    from fabulous.fabric_cad.fabxplore.modules.routing_demand_evaluator.core.routing_graph import (  # noqa: E501
        RoutingGraph,
    )


def generate_demand_profile(
    options: RoutingDemandEvaluatorOptions,
    matrix: MatrixData,
    graph: RoutingGraph,
    tracker: RoutingDemandProcessTracker | None = None,
) -> DemandProfileResult:
    """Generate demands for a named profile.

    Parameters
    ----------
    options : RoutingDemandEvaluatorOptions
        Evaluator options.
    matrix : MatrixData
        Loaded matrix data.
    graph : RoutingGraph
        Routing graph.
    tracker : RoutingDemandProcessTracker | None
        Optional progress tracker.

    Returns
    -------
    DemandProfileResult
        Generated demand profile.

    Raises
    ------
    ValueError
        If the profile is unknown.
    """
    rng = Random(options.seed)
    match options.demand_profile:
        case DemandProfileName.DEFAULT:
            return generate_default_profile(options, matrix, graph, rng, tracker)
        case DemandProfileName.MINIMAL:
            return generate_minimal_profile(options, matrix, graph, rng, tracker)
        case DemandProfileName.ROUTING_STRESS:
            return generate_routing_stress_profile(
                options,
                matrix,
                graph,
                rng,
                tracker,
            )
        case DemandProfileName.CONTROL_STRESS:
            return generate_control_stress_profile(
                options,
                matrix,
                graph,
                rng,
                tracker,
            )
        case DemandProfileName.FULL:
            return generate_full_profile(options, matrix, graph, rng, tracker)
        case _:
            raise ValueError(f"Unknown demand profile: {options.demand_profile}")

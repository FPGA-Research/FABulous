"""Default routing-demand profile."""

from __future__ import annotations

from typing import TYPE_CHECKING

from fabulous.fabric_cad.fabxplore.modules.routing_demand_evaluator.core.models import (
    DemandClassName,
    DemandProfileResult,
    RoutingDemandEvaluatorOptions,
)
from fabulous.fabric_cad.fabxplore.modules.routing_demand_evaluator.demand_profiles.common import (  # noqa: E501
    compose_profile,
)

if TYPE_CHECKING:
    from random import Random

    from fabulous.fabric_cad.fabxplore.modules.routing_demand_evaluator.core.models import (  # noqa: E501
        MatrixData,
    )
    from fabulous.fabric_cad.fabxplore.modules.routing_demand_evaluator.core.process_tracker import (  # noqa: E501
        RoutingDemandProcessTracker,
    )
    from fabulous.fabric_cad.fabxplore.modules.routing_demand_evaluator.core.routing_graph import (  # noqa: E501
        RoutingGraph,
    )


def generate_default_profile(
    options: RoutingDemandEvaluatorOptions,
    matrix: MatrixData,
    graph: RoutingGraph,
    rng: Random,
    tracker: RoutingDemandProcessTracker | None = None,
) -> DemandProfileResult:
    """Generate the default meaningful routing-demand profile.

    Parameters
    ----------
    options : RoutingDemandEvaluatorOptions
        Evaluator options.
    matrix : MatrixData
        Loaded matrix data.
    graph : RoutingGraph
        Routing graph.
    rng : Random
        Random generator.
    tracker : RoutingDemandProcessTracker | None
        Optional progress tracker.

    Returns
    -------
    DemandProfileResult
        Generated demand profile.
    """
    return compose_profile(
        profile_name="default",
        classes=[
            DemandClassName.MATRIX_ROW_COVERAGE,
            DemandClassName.BEL_INPUT_REACHABILITY,
            DemandClassName.BEL_OUTPUT_ESCAPE,
            DemandClassName.HIERARCHY_INTEGRITY,
            DemandClassName.BEL_INPUT_SOURCE_COVERAGE,
            DemandClassName.MATRIX_SOURCE_USEFULNESS,
            DemandClassName.FANIN_DIVERSITY,
            DemandClassName.SOURCE_FANOUT_DIVERSITY,
            DemandClassName.SIDE_PAIR_BALANCE,
            DemandClassName.LOCAL_FEEDBACK,
            DemandClassName.STRAIGHT_ROUTING,
            DemandClassName.TURN_ROUTING,
            DemandClassName.BEL_INPUT_FANOUT,
            DemandClassName.RANDOM_LOCAL,
            DemandClassName.RANDOM_MEDIUM,
        ],
        options=options,
        matrix=matrix,
        graph=graph,
        rng=rng,
        tracker=tracker,
    )

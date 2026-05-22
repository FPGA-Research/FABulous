"""Minimal routing-demand profile."""

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
    from fabulous.fabric_cad.fabxplore.modules.routing_demand_evaluator.core.routing_graph import (  # noqa: E501
        RoutingGraph,
    )


def generate_minimal_profile(
    options: RoutingDemandEvaluatorOptions,
    matrix: MatrixData,
    graph: RoutingGraph,
    rng: Random,
) -> DemandProfileResult:
    """Generate a small smoke-test demand profile.

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

    Returns
    -------
    DemandProfileResult
        Generated demand profile.
    """
    return compose_profile(
        profile_name="minimal",
        classes=[
            DemandClassName.MATRIX_ROW_COVERAGE,
            DemandClassName.BEL_INPUT_REACHABILITY,
            DemandClassName.BEL_OUTPUT_ESCAPE,
        ],
        options=options,
        matrix=matrix,
        graph=graph,
        rng=rng,
    )

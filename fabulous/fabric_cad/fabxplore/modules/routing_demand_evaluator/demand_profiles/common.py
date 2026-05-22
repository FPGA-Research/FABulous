"""Shared helpers for demand-profile composition."""

from __future__ import annotations

from typing import TYPE_CHECKING

from fabulous.fabric_cad.fabxplore.modules.routing_demand_evaluator.core.models import (
    DemandClassName,
    DemandProfileResult,
)
from fabulous.fabric_cad.fabxplore.modules.routing_demand_evaluator.demand_classes import (  # noqa: E501
    generate_demand_class,
)

if TYPE_CHECKING:
    from random import Random

    from fabulous.fabric_cad.fabxplore.modules.routing_demand_evaluator.core.models import (  # noqa: E501
        MatrixData,
        RoutingDemand,
        RoutingDemandEvaluatorOptions,
    )
    from fabulous.fabric_cad.fabxplore.modules.routing_demand_evaluator.core.routing_graph import (  # noqa: E501
        RoutingGraph,
    )

_RANDOM_CLASSES = {
    DemandClassName.RANDOM_LOCAL,
    DemandClassName.RANDOM_MEDIUM,
    DemandClassName.RANDOM_LONG,
}


def compose_profile(
    profile_name: str,
    classes: list[DemandClassName],
    options: RoutingDemandEvaluatorOptions,
    matrix: MatrixData,
    graph: RoutingGraph,
    rng: Random,
) -> DemandProfileResult:
    """Compose one demand profile from internal demand classes.

    Parameters
    ----------
    profile_name : str
        Profile name.
    classes : list[DemandClassName]
        Internal demand classes included by the profile.
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
    hard_budget = max(
        1,
        int(options.demand_iterations * (1.0 - options.random_demand_ratio)),
    )
    random_budget = max(0, options.demand_iterations - hard_budget)
    deterministic = [item for item in classes if item not in _RANDOM_CLASSES]
    random_classes = [item for item in classes if item in _RANDOM_CLASSES]
    demands: list[RoutingDemand] = []
    warnings: list[str] = []
    demands.extend(
        _generate_class_group(
            deterministic,
            hard_budget,
            options,
            matrix,
            graph,
            rng,
        )
    )
    demands.extend(
        _generate_class_group(
            random_classes,
            random_budget,
            options,
            matrix,
            graph,
            rng,
        )
    )
    present_classes = {demand.demand_class for demand in demands}
    for demand_class in classes:
        if demand_class not in present_classes:
            warnings.append(f"Demand class generated no demands: {demand_class}")
    return DemandProfileResult(
        profile_name=profile_name,
        demands=demands[: options.demand_iterations],
        warnings=warnings,
    )


def _generate_class_group(
    classes: list[DemandClassName],
    budget: int,
    options: RoutingDemandEvaluatorOptions,
    matrix: MatrixData,
    graph: RoutingGraph,
    rng: Random,
) -> list[RoutingDemand]:
    """Generate demands for a class group.

    Parameters
    ----------
    classes : list[DemandClassName]
        Classes to generate.
    budget : int
        Demand budget for the group.
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
    list[RoutingDemand]
        Generated demands.
    """
    if budget <= 0 or not classes:
        return []
    per_class = max(1, budget // len(classes))
    demands: list[RoutingDemand] = []
    for demand_class in classes:
        remaining = budget - len(demands)
        if remaining <= 0:
            break
        demands.extend(
            generate_demand_class(
                demand_class=demand_class,
                options=options,
                matrix=matrix,
                graph=graph,
                rng=rng,
                limit=min(per_class, remaining),
                offset=len(demands),
            )
        )
    return demands[:budget]

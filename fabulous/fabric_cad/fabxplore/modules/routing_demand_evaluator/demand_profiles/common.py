"""Shared helpers for demand-profile composition."""

from __future__ import annotations

from time import perf_counter
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
    from fabulous.fabric_cad.fabxplore.modules.routing_demand_evaluator.core.process_tracker import (  # noqa: E501
        RoutingDemandProcessTracker,
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
    tracker: RoutingDemandProcessTracker | None = None,
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
    tracker : RoutingDemandProcessTracker | None
        Optional progress tracker.

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
    if tracker is not None:
        tracker.demand_profile_start(
            profile_name,
            len(classes),
            hard_budget,
            random_budget,
        )
    demands.extend(
        _generate_class_group(
            deterministic,
            hard_budget,
            options,
            matrix,
            graph,
            rng,
            tracker,
            class_offset=0,
            total_classes=len(classes),
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
            tracker,
            class_offset=len(deterministic),
            total_classes=len(classes),
        )
    )
    present_classes = {demand.demand_class for demand in demands}
    for demand_class in classes:
        if demand_class not in present_classes:
            warnings.append(f"Demand class generated no demands: {demand_class}")
    result = DemandProfileResult(
        profile_name=profile_name,
        demands=demands[: options.demand_iterations],
        warnings=warnings,
    )
    if tracker is not None:
        tracker.demand_profile_done(profile_name, len(result.demands))
    return result


def _generate_class_group(
    classes: list[DemandClassName],
    budget: int,
    options: RoutingDemandEvaluatorOptions,
    matrix: MatrixData,
    graph: RoutingGraph,
    rng: Random,
    tracker: RoutingDemandProcessTracker | None,
    *,
    class_offset: int,
    total_classes: int,
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
    tracker : RoutingDemandProcessTracker | None
        Optional progress tracker.
    class_offset : int
        Number of profile classes before this group.
    total_classes : int
        Total number of classes in the profile.

    Returns
    -------
    list[RoutingDemand]
        Generated demands.
    """
    if budget <= 0 or not classes:
        return []
    per_class = max(1, budget // len(classes))
    demands: list[RoutingDemand] = []
    for group_index, demand_class in enumerate(classes, start=1):
        remaining = budget - len(demands)
        if remaining <= 0:
            break
        class_budget = min(per_class, remaining)
        class_index = class_offset + group_index
        if tracker is not None:
            tracker.demand_class_start(
                str(demand_class),
                class_index,
                total_classes,
                class_budget,
            )
        started_at = perf_counter()
        generated = generate_demand_class(
            demand_class=demand_class,
            options=options,
            matrix=matrix,
            graph=graph,
            rng=rng,
            limit=class_budget,
            offset=len(demands),
        )
        if tracker is not None:
            tracker.demand_class_done(
                str(demand_class),
                len(generated),
                perf_counter() - started_at,
            )
        demands.extend(generated)
    return demands[:budget]

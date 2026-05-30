"""Random routing-demand class generators."""

from __future__ import annotations

from typing import TYPE_CHECKING, Literal

from fabulous.fabric_cad.fabxplore.modules.routing_demand_evaluator.core.models import (
    DemandClassName,
    DemandKind,
    RoutingDemand,
)
from fabulous.fabric_cad.fabxplore.modules.routing_demand_evaluator.demand_classes.common import (  # noqa: E501
    _distance_matches,
    _reachable_random_candidates,
    _terminal_sinks,
    _terminal_sources,
)

if TYPE_CHECKING:
    from random import Random

    from fabulous.fabric_cad.fabxplore.modules.routing_demand_evaluator.core.models import (  # noqa: E501
        MatrixData,
    )
    from fabulous.fabric_cad.fabxplore.modules.routing_demand_evaluator.core.routing_graph import (  # noqa: E501
        RoutingGraph,
    )


def random_terminal_pairs(
    demand_class: DemandClassName,
    matrix: MatrixData,
    graph: RoutingGraph,
    rng: Random,
    limit: int,
    offset: int,
    distance: Literal["local", "medium", "long"],
) -> list[RoutingDemand]:
    """Generate random terminal-to-terminal demands.

    Parameters
    ----------
    demand_class : DemandClassName
        Demand class name.
    matrix : MatrixData
        Loaded matrix data.
    graph : RoutingGraph
        Routing graph.
    rng : Random
        Random generator.
    limit : int
        Maximum generated demands.
    offset : int
        Stable ID offset.
    distance : Literal["local", "medium", "long"]
        Distance bucket.

    Returns
    -------
    list[RoutingDemand]
        Generated demands.
    """
    if limit <= 0:
        return []
    sources = _terminal_sources(matrix, graph)
    sinks = _terminal_sinks(matrix, graph)
    if not sources or not sinks:
        return []
    candidates = _reachable_random_candidates(sources, sinks, graph, distance)
    rng.shuffle(candidates)
    return [
        RoutingDemand(
            demand_id=f"{demand_class}_{offset + index}",
            demand_class=demand_class,
            kind=DemandKind.SOFT,
            source=source.name,
            sink=sink.name,
        )
        for index, (source, sink) in enumerate(candidates[:limit])
    ]


def random_bucket_candidate_counts(
    matrix: MatrixData,
    graph: RoutingGraph,
    distance: Literal["local", "medium", "long"],
) -> tuple[int, int]:
    """Return candidate and reachable counts for one random bucket.

    Parameters
    ----------
    matrix : MatrixData
        Loaded matrix data.
    graph : RoutingGraph
        Routing graph.
    distance : Literal["local", "medium", "long"]
        Distance bucket.

    Returns
    -------
    tuple[int, int]
        Distance-matching pair count and reachable pair count.
    """
    sources = _terminal_sources(matrix, graph)
    sinks = _terminal_sinks(matrix, graph)
    candidate_count = 0
    reachable_count = 0
    for source in sources:
        for sink in sinks:
            if source.name == sink.name:
                continue
            if not _distance_matches(source, sink, distance):
                continue
            candidate_count += 1
            if graph.is_reachable(source.name, sink.name):
                reachable_count += 1
    return candidate_count, reachable_count

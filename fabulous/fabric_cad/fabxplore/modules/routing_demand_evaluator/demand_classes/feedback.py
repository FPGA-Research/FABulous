"""Feedback-oriented routing-demand class generators."""

from __future__ import annotations

from typing import TYPE_CHECKING

from fabulous.fabric_cad.fabxplore.modules.routing_demand_evaluator.core.models import (
    DemandClassName,
    DemandKind,
)
from fabulous.fabric_cad.fabxplore.modules.routing_demand_evaluator.demand_classes.common import (  # noqa: E501
    _coverage_by_source,
    _generic_bel_input_terminals,
    _generic_bel_output_terminals,
)

if TYPE_CHECKING:
    from fabulous.fabric_cad.fabxplore.modules.routing_demand_evaluator.core.models import (  # noqa: E501
        MatrixData,
        RoutingDemand,
    )
    from fabulous.fabric_cad.fabxplore.modules.routing_demand_evaluator.core.routing_graph import (  # noqa: E501
        RoutingGraph,
    )


def local_feedback(
    matrix: MatrixData,
    graph: RoutingGraph,
    limit: int,
    offset: int,
) -> list[RoutingDemand]:
    """Generate same-tile BEL output to BEL input demands.

    Parameters
    ----------
    matrix : MatrixData
        Loaded matrix data.
    graph : RoutingGraph
        Routing graph.
    limit : int
        Maximum generated demands.
    offset : int
        Stable ID offset.

    Returns
    -------
    list[RoutingDemand]
        Generated demands.
    """
    return _coverage_by_source(
        DemandClassName.LOCAL_FEEDBACK,
        DemandKind.HARD,
        _generic_bel_output_terminals(matrix, graph),
        _generic_bel_input_terminals(matrix, graph),
        limit,
        offset,
        graph,
    )


def neighbor_feedback(
    matrix: MatrixData,
    graph: RoutingGraph,
    limit: int,
    offset: int,
) -> list[RoutingDemand]:
    """Generate neighbor-style feedback demands through routing terminals.

    Parameters
    ----------
    matrix : MatrixData
        Loaded matrix data.
    graph : RoutingGraph
        Routing graph.
    limit : int
        Maximum generated demands.
    offset : int
        Stable ID offset.

    Returns
    -------
    list[RoutingDemand]
        Generated demands.
    """
    return _coverage_by_source(
        DemandClassName.NEIGHBOR_FEEDBACK,
        DemandKind.SOFT,
        _generic_bel_output_terminals(matrix, graph),
        _generic_bel_input_terminals(matrix, graph),
        limit,
        offset,
        graph,
    )

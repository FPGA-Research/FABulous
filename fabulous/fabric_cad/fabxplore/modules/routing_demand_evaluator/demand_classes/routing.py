"""Routing-resource demand class generators."""

from __future__ import annotations

from typing import TYPE_CHECKING

from fabulous.fabric_cad.fabxplore.modules.routing_demand_evaluator.core.models import (
    DemandClassName,
    DemandKind,
    RoutingDemand,
)
from fabulous.fabric_cad.fabxplore.modules.routing_demand_evaluator.demand_classes.common import (  # noqa: E501
    _coverage_by_sink,
    _coverage_by_source,
    _coverage_from_pairs,
    _matrix_row_routing_terminals,
    _matrix_row_terminals,
    _matrix_source_routing_terminals,
    _matrix_source_terminals,
    _routing_pairs_by_direction,
    _terminal_sinks,
    _terminal_span,
)

if TYPE_CHECKING:
    from fabulous.fabric_cad.fabxplore.modules.routing_demand_evaluator.core.models import (  # noqa: E501
        MatrixData,
        RoutingTerminal,
    )
    from fabulous.fabric_cad.fabxplore.modules.routing_demand_evaluator.core.routing_graph import (  # noqa: E501
        RoutingGraph,
    )


def matrix_row_coverage(
    matrix: MatrixData,
    graph: RoutingGraph,
    limit: int,
    offset: int,
) -> list[RoutingDemand]:
    """Generate demands proving matrix destination rows are reachable.

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
    return _coverage_by_sink(
        DemandClassName.MATRIX_ROW_COVERAGE,
        DemandKind.HARD,
        _matrix_source_terminals(matrix, graph),
        _matrix_row_terminals(matrix, graph),
        limit,
        offset,
        graph,
    )


def matrix_source_usefulness(
    matrix: MatrixData,
    graph: RoutingGraph,
    limit: int,
    offset: int,
) -> list[RoutingDemand]:
    """Generate demands proving matrix sources reach meaningful sinks.

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
        DemandClassName.MATRIX_SOURCE_USEFULNESS,
        DemandKind.SOFT,
        _matrix_source_terminals(matrix, graph),
        _terminal_sinks(matrix, graph),
        limit,
        offset,
        graph,
    )


def hierarchy_integrity(
    matrix: MatrixData,
    graph: RoutingGraph,
    limit: int,
    offset: int,
) -> list[RoutingDemand]:
    """Generate demands checking JUMP hierarchy continuity.

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
    pairs = [
        (source, sink)
        for source, sink in matrix.jump_edges
        if source != sink and graph.has_node(source) and graph.has_node(sink)
    ]
    demands: list[RoutingDemand] = []
    for source, sink in pairs[:limit]:
        demands.append(
            RoutingDemand(
                demand_id=(
                    f"{DemandClassName.HIERARCHY_INTEGRITY}_{offset + len(demands)}"
                ),
                demand_class=DemandClassName.HIERARCHY_INTEGRITY,
                kind=DemandKind.HARD,
                source=source,
                sink=sink,
            )
        )
    return demands


def straight_routing(
    matrix: MatrixData,
    graph: RoutingGraph,
    limit: int,
    offset: int,
) -> list[RoutingDemand]:
    """Generate same-direction routing continuation demands.

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
    return _routing_pairs_by_direction(
        DemandClassName.STRAIGHT_ROUTING,
        DemandKind.HARD,
        matrix,
        graph,
        limit,
        offset,
        same_direction=True,
    )


def turn_routing(
    matrix: MatrixData,
    graph: RoutingGraph,
    limit: int,
    offset: int,
) -> list[RoutingDemand]:
    """Generate cross-direction routing turn demands.

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
    return _routing_pairs_by_direction(
        DemandClassName.TURN_ROUTING,
        DemandKind.HARD,
        matrix,
        graph,
        limit,
        offset,
        same_direction=False,
    )


def short_to_long(
    matrix: MatrixData,
    graph: RoutingGraph,
    limit: int,
    offset: int,
) -> list[RoutingDemand]:
    """Generate short-wire to long-wire access demands.

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
    pairs = [
        (source, sink)
        for source in _matrix_routing_terminals_by_distance(
            matrix, graph, long=False, source=True
        )
        for sink in _matrix_routing_terminals_by_distance(
            matrix, graph, long=True, source=False
        )
        if source.name != sink.name
    ]
    return _coverage_from_pairs(
        DemandClassName.SHORT_TO_LONG,
        DemandKind.SOFT,
        pairs,
        limit,
        offset,
        graph,
    )


def long_to_short(
    matrix: MatrixData,
    graph: RoutingGraph,
    limit: int,
    offset: int,
) -> list[RoutingDemand]:
    """Generate long-wire to short-wire exit demands.

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
    pairs = [
        (source, sink)
        for source in _matrix_routing_terminals_by_distance(
            matrix, graph, long=True, source=True
        )
        for sink in _matrix_routing_terminals_by_distance(
            matrix, graph, long=False, source=False
        )
        if source.name != sink.name
    ]
    return _coverage_from_pairs(
        DemandClassName.LONG_TO_SHORT,
        DemandKind.SOFT,
        pairs,
        limit,
        offset,
        graph,
    )


def multi_hop(
    matrix: MatrixData,
    graph: RoutingGraph,
    limit: int,
    offset: int,
) -> list[RoutingDemand]:
    """Generate long/medium route stress demands.

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
    pairs = []
    for source in _matrix_source_routing_terminals(matrix, graph):
        for sink in _matrix_row_routing_terminals(matrix, graph):
            if source.name == sink.name:
                continue
            path = graph.shortest_path(source.name, sink.name)
            if path is not None and len(path[0]) >= 4:
                pairs.append((source, sink))
    return _coverage_from_pairs(
        DemandClassName.MULTI_HOP,
        DemandKind.SOFT,
        pairs,
        limit,
        offset,
        graph,
    )


def routing_redundancy(
    matrix: MatrixData,
    graph: RoutingGraph,
    limit: int,
    offset: int,
) -> list[RoutingDemand]:
    """Generate demands for source/sink pairs with alternate route potential.

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
    sources = _matrix_source_terminals(matrix, graph)
    sinks = _terminal_sinks(matrix, graph)
    demands: list[RoutingDemand] = []
    for sink in sinks:
        reachable = [
            source
            for source in sources
            if source.name != sink.name
            and graph.shortest_path(source.name, sink.name) is not None
        ]
        if len(reachable) < 2:
            continue
        demands.append(
            RoutingDemand(
                demand_id=(
                    f"{DemandClassName.ROUTING_REDUNDANCY}_{offset + len(demands)}"
                ),
                demand_class=DemandClassName.ROUTING_REDUNDANCY,
                kind=DemandKind.SOFT,
                source=reachable[1].name,
                sink=sink.name,
            )
        )
        if len(demands) >= limit:
            break
    return demands


def _matrix_routing_terminals_by_distance(
    matrix: MatrixData,
    graph: RoutingGraph,
    long: bool,
    source: bool,
) -> list[RoutingTerminal]:
    """Return matrix-side routing terminals by FABulous port span.

    Parameters
    ----------
    matrix : MatrixData
        Loaded matrix data.
    graph : RoutingGraph
        Routing graph.
    long : bool
        Select long-distance terminals if ``True``.
    source : bool
        Select matrix source-side terminals if ``True``.

    Returns
    -------
    list[RoutingTerminal]
        Matching terminals.
    """
    terminals = (
        _matrix_source_routing_terminals(matrix, graph)
        if source
        else _matrix_row_routing_terminals(matrix, graph)
    )
    return [
        terminal for terminal in terminals if (_terminal_span(terminal) > 1) == long
    ]

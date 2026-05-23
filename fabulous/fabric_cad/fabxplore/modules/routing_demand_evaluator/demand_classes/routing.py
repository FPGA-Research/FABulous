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

_CARDINAL_DIRECTIONS = ("NORTH", "EAST", "SOUTH", "WEST")


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


def fanin_diversity(
    matrix: MatrixData,
    graph: RoutingGraph,
    limit: int,
    offset: int,
) -> list[RoutingDemand]:
    """Generate soft demands for alternative sources into muxed rows.

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
    source_by_name = {
        terminal.name: terminal for terminal in _matrix_source_terminals(matrix, graph)
    }
    row_by_name = {
        terminal.name: terminal for terminal in _matrix_row_terminals(matrix, graph)
    }
    pairs = []
    for row in sorted(matrix.connections):
        sink = row_by_name.get(row)
        if sink is None:
            continue
        sources = sorted(
            {
                source
                for source in matrix.connections[row]
                if source != row and source in source_by_name
            }
        )
        if len(sources) < 2:
            continue
        pairs.extend((source_by_name[source], sink) for source in sources)
    return _direct_pair_demands(
        DemandClassName.FANIN_DIVERSITY,
        pairs,
        limit,
        offset,
        graph,
    )


def source_fanout_diversity(
    matrix: MatrixData,
    graph: RoutingGraph,
    limit: int,
    offset: int,
) -> list[RoutingDemand]:
    """Generate soft demands for sources that feed multiple rows.

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
    source_by_name = {
        terminal.name: terminal for terminal in _matrix_source_terminals(matrix, graph)
    }
    row_by_name = {
        terminal.name: terminal for terminal in _matrix_row_terminals(matrix, graph)
    }
    rows_by_source: dict[str, list[RoutingTerminal]] = {}
    for row in sorted(matrix.connections):
        sink = row_by_name.get(row)
        if sink is None:
            continue
        for source in sorted(set(matrix.connections[row])):
            if source == row or source not in source_by_name:
                continue
            rows_by_source.setdefault(source, []).append(sink)

    pairs = []
    for source in sorted(rows_by_source):
        sinks = _dedupe_terminals_by_name(rows_by_source[source])
        if len(sinks) < 2:
            continue
        pairs.extend((source_by_name[source], sink) for sink in sinks)
    return _direct_pair_demands(
        DemandClassName.SOURCE_FANOUT_DIVERSITY,
        pairs,
        limit,
        offset,
        graph,
    )


def side_pair_balance(
    matrix: MatrixData,
    graph: RoutingGraph,
    limit: int,
    offset: int,
) -> list[RoutingDemand]:
    """Generate soft demands for ordered side-to-side routing balance.

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
    sources_by_direction = _terminals_by_direction(
        _matrix_source_routing_terminals(matrix, graph)
    )
    sinks_by_direction = _terminals_by_direction(
        _matrix_row_routing_terminals(matrix, graph)
    )
    demands: list[RoutingDemand] = []
    for source_direction in _CARDINAL_DIRECTIONS:
        for sink_direction in _CARDINAL_DIRECTIONS:
            if source_direction == sink_direction:
                continue
            pair = _first_reachable_or_first_pair(
                sources=sources_by_direction.get(source_direction, []),
                sinks=sinks_by_direction.get(sink_direction, []),
                graph=graph,
            )
            if pair is None:
                continue
            source, sink = pair
            demands.append(
                RoutingDemand(
                    demand_id=(
                        f"{DemandClassName.SIDE_PAIR_BALANCE}_{offset + len(demands)}"
                    ),
                    demand_class=DemandClassName.SIDE_PAIR_BALANCE,
                    kind=DemandKind.SOFT,
                    source=source.name,
                    sink=sink.name,
                )
            )
            if len(demands) >= limit:
                return demands
    return demands


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


def _direct_pair_demands(
    demand_class: DemandClassName,
    pairs: list[tuple[RoutingTerminal, RoutingTerminal]],
    limit: int,
    offset: int,
    graph: RoutingGraph,
) -> list[RoutingDemand]:
    """Generate bounded one-to-one demands from explicit direct pairs.

    Parameters
    ----------
    demand_class : DemandClassName
        Demand class.
    pairs : list[tuple[RoutingTerminal, RoutingTerminal]]
        Candidate source/sink terminal pairs.
    limit : int
        Maximum generated demands.
    offset : int
        Stable ID offset.
    graph : RoutingGraph
        Routing graph.

    Returns
    -------
    list[RoutingDemand]
        Generated demands.
    """
    demands: list[RoutingDemand] = []
    seen: set[tuple[str, str]] = set()
    for source, sink in pairs:
        key = (source.name, sink.name)
        if source.name == sink.name or key in seen:
            continue
        seen.add(key)
        if graph.shortest_path(source.name, sink.name) is None:
            continue
        demands.append(
            RoutingDemand(
                demand_id=f"{demand_class}_{offset + len(demands)}",
                demand_class=demand_class,
                kind=DemandKind.SOFT,
                source=source.name,
                sink=sink.name,
            )
        )
        if len(demands) >= limit:
            break
    return demands


def _dedupe_terminals_by_name(
    terminals: list[RoutingTerminal],
) -> list[RoutingTerminal]:
    """Return terminals with duplicate names removed.

    Parameters
    ----------
    terminals : list[RoutingTerminal]
        Candidate terminals.

    Returns
    -------
    list[RoutingTerminal]
        Deduplicated terminals.
    """
    result: list[RoutingTerminal] = []
    seen: set[str] = set()
    for terminal in terminals:
        if terminal.name in seen:
            continue
        seen.add(terminal.name)
        result.append(terminal)
    return result


def _terminals_by_direction(
    terminals: list[RoutingTerminal],
) -> dict[str, list[RoutingTerminal]]:
    """Group terminals by cardinal FABulous direction.

    Parameters
    ----------
    terminals : list[RoutingTerminal]
        Terminals to group.

    Returns
    -------
    dict[str, list[RoutingTerminal]]
        Terminals keyed by direction.
    """
    by_direction: dict[str, list[RoutingTerminal]] = {}
    for terminal in sorted(terminals, key=lambda item: item.name):
        if terminal.direction not in _CARDINAL_DIRECTIONS:
            continue
        by_direction.setdefault(terminal.direction, []).append(terminal)
    return by_direction


def _first_reachable_or_first_pair(
    sources: list[RoutingTerminal],
    sinks: list[RoutingTerminal],
    graph: RoutingGraph,
) -> tuple[RoutingTerminal, RoutingTerminal] | None:
    """Return a representative source/sink pair for one side pair.

    Parameters
    ----------
    sources : list[RoutingTerminal]
        Candidate source terminals for one side.
    sinks : list[RoutingTerminal]
        Candidate sink terminals for one side.
    graph : RoutingGraph
        Routing graph.

    Returns
    -------
    tuple[RoutingTerminal, RoutingTerminal] | None
        A reachable pair if one exists, otherwise a deterministic fallback pair.
    """
    fallback: tuple[RoutingTerminal, RoutingTerminal] | None = None
    for source in sources:
        for sink in sinks:
            if source.name == sink.name:
                continue
            fallback = fallback or (source, sink)
            if graph.shortest_path(source.name, sink.name) is not None:
                return source, sink
    return fallback

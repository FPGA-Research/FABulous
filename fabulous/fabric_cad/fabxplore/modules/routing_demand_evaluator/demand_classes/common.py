"""Shared helpers for routing-demand class generators."""

from __future__ import annotations

from typing import TYPE_CHECKING, Literal

from fabulous.fabric_cad.fabxplore.modules.routing_demand_evaluator.core.models import (
    DemandClassName,
    DemandKind,
    RoutingDemand,
    RoutingDemandEvaluatorOptions,
    RoutingTerminal,
    RoutingTerminalRole,
    RoutingTerminalSource,
)

if TYPE_CHECKING:
    from collections.abc import Iterable

    from fabulous.fabric_cad.fabxplore.modules.routing_demand_evaluator.core.models import (  # noqa: E501
        MatrixData,
    )
    from fabulous.fabric_cad.fabxplore.modules.routing_demand_evaluator.core.routing_graph import (  # noqa: E501
        RoutingGraph,
    )


def _reachable_random_candidates(
    sources: list[RoutingTerminal],
    sinks: list[RoutingTerminal],
    graph: RoutingGraph,
    distance: Literal["local", "medium", "long"],
) -> list[tuple[RoutingTerminal, RoutingTerminal]]:
    """Return reachable random-demand candidates for one distance bucket.

    Parameters
    ----------
    sources : list[RoutingTerminal]
        Candidate sources.
    sinks : list[RoutingTerminal]
        Candidate sinks.
    graph : RoutingGraph
        Routing graph.
    distance : Literal["local", "medium", "long"]
        Distance bucket.

    Returns
    -------
    list[tuple[RoutingTerminal, RoutingTerminal]]
        Reachable source/sink candidates.
    """
    candidates: list[tuple[RoutingTerminal, RoutingTerminal]] = []
    for source in sources:
        for sink in sinks:
            if source.name == sink.name:
                continue
            if not _distance_matches(source, sink, distance):
                continue
            if not graph.is_reachable(source.name, sink.name):
                continue
            candidates.append((source, sink))
    return candidates


def _routing_pairs_by_direction(
    demand_class: DemandClassName,
    kind: DemandKind,
    matrix: MatrixData,
    graph: RoutingGraph,
    limit: int,
    offset: int,
    same_direction: bool,
) -> list[RoutingDemand]:
    """Generate routing terminal pairs filtered by direction relation.

    Parameters
    ----------
    demand_class : DemandClassName
        Demand class.
    kind : DemandKind
        Demand kind.
    matrix : MatrixData
        Loaded matrix data.
    graph : RoutingGraph
        Routing graph.
    limit : int
        Maximum generated demands.
    offset : int
        Stable ID offset.
    same_direction : bool
        Whether directions must match.

    Returns
    -------
    list[RoutingDemand]
        Generated demands.
    """
    sources = _matrix_source_routing_terminals(matrix, graph)
    sinks = _matrix_row_routing_terminals(matrix, graph)
    pairs = [
        (source, sink)
        for source in sources
        for sink in sinks
        if source.name != sink.name
        and source.direction is not None
        and sink.direction is not None
        and (source.direction == sink.direction) == same_direction
    ]
    return _coverage_from_pairs(demand_class, kind, pairs, limit, offset, graph)


def _coverage_by_sink(
    demand_class: DemandClassName,
    kind: DemandKind,
    sources: list[RoutingTerminal],
    sinks: list[RoutingTerminal],
    limit: int,
    offset: int,
    graph: RoutingGraph,
) -> list[RoutingDemand]:
    """Generate one representative demand for each sink.

    Parameters
    ----------
    demand_class : DemandClassName
        Demand class.
    kind : DemandKind
        Demand kind.
    sources : list[RoutingTerminal]
        Source terminals.
    sinks : list[RoutingTerminal]
        Sink terminals.
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
    if not sources or not sinks:
        return []
    demands: list[RoutingDemand] = []
    for sink in sinks:
        source = _first_reachable_source(sources, sink, graph) or sources[0]
        if source.name == sink.name:
            continue
        demands.append(
            RoutingDemand(
                demand_id=f"{demand_class}_{offset + len(demands)}",
                demand_class=demand_class,
                kind=kind,
                source=source.name,
                sink=sink.name,
            )
        )
        if len(demands) >= limit:
            break
    return demands


def _coverage_by_source(
    demand_class: DemandClassName,
    kind: DemandKind,
    sources: list[RoutingTerminal],
    sinks: list[RoutingTerminal],
    limit: int,
    offset: int,
    graph: RoutingGraph,
) -> list[RoutingDemand]:
    """Generate one representative demand for each source.

    Parameters
    ----------
    demand_class : DemandClassName
        Demand class.
    kind : DemandKind
        Demand kind.
    sources : list[RoutingTerminal]
        Source terminals.
    sinks : list[RoutingTerminal]
        Sink terminals.
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
    if not sources or not sinks:
        return []
    demands: list[RoutingDemand] = []
    for source in sources:
        sink = _first_reachable_sink(source, sinks, graph) or sinks[0]
        if source.name == sink.name:
            continue
        demands.append(
            RoutingDemand(
                demand_id=f"{demand_class}_{offset + len(demands)}",
                demand_class=demand_class,
                kind=kind,
                source=source.name,
                sink=sink.name,
            )
        )
        if len(demands) >= limit:
            break
    return demands


def _coverage_from_pairs(
    demand_class: DemandClassName,
    kind: DemandKind,
    pairs: list[tuple[RoutingTerminal, RoutingTerminal]],
    limit: int,
    offset: int,
    graph: RoutingGraph,
) -> list[RoutingDemand]:
    """Generate bounded reachable coverage demands from candidate pairs.

    Parameters
    ----------
    demand_class : DemandClassName
        Demand class.
    kind : DemandKind
        Demand kind.
    pairs : list[tuple[RoutingTerminal, RoutingTerminal]]
        Candidate terminal pairs.
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
    reachable_by_source: dict[str, tuple[RoutingTerminal, RoutingTerminal]] = {}
    fallback_by_source: dict[str, tuple[RoutingTerminal, RoutingTerminal]] = {}
    for source, sink in pairs:
        if source.name == sink.name:
            continue
        if graph.is_reachable(source.name, sink.name):
            reachable_by_source.setdefault(source.name, (source, sink))
            continue
        fallback_by_source.setdefault(source.name, (source, sink))

    result: list[RoutingDemand] = []
    seen_sources: set[str] = set()
    for source, sink in reachable_by_source.values():
        seen_sources.add(source.name)
        result.append(
            RoutingDemand(
                demand_id=f"{demand_class}_{offset + len(result)}",
                demand_class=demand_class,
                kind=kind,
                source=source.name,
                sink=sink.name,
            )
        )
        if len(result) >= limit:
            return result
    for source, sink in fallback_by_source.values():
        if source.name in seen_sources:
            continue
        seen_sources.add(source.name)
        result.append(
            RoutingDemand(
                demand_id=f"{demand_class}_{offset + len(result)}",
                demand_class=demand_class,
                kind=kind,
                source=source.name,
                sink=sink.name,
            )
        )
        if len(result) >= limit:
            break
    return result


def _fanout_demands(
    demand_class: DemandClassName,
    kind: DemandKind,
    options: RoutingDemandEvaluatorOptions,
    sources: list[RoutingTerminal],
    sinks: list[RoutingTerminal],
    limit: int,
    offset: int,
    graph: RoutingGraph,
) -> list[RoutingDemand]:
    """Generate multi-sink demands.

    Parameters
    ----------
    demand_class : DemandClassName
        Demand class.
    kind : DemandKind
        Demand kind.
    options : RoutingDemandEvaluatorOptions
        Evaluator options.
    sources : list[RoutingTerminal]
        Source terminals.
    sinks : list[RoutingTerminal]
        Sink terminals.
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
    if not sources or len(sinks) < 2:
        return []
    demands: list[RoutingDemand] = []
    source_candidates = []
    for source in sources:
        reachable = [
            sink for sink in sinks if graph.is_reachable(source.name, sink.name)
        ]
        unreachable = [
            sink for sink in sinks if sink.name != source.name and sink not in reachable
        ]
        source_candidates.append((source, reachable, unreachable))
    source_candidates.sort(key=lambda item: (-len(item[1]), item[0].name))
    for source, reachable, unreachable in source_candidates:
        for target in options.fanout_targets:
            target_count = min(target, options.max_net_sinks, len(sinks))
            sink_names = _fanout_sink_names(
                source.name,
                reachable,
                unreachable,
                target_count,
            )
            if not sink_names:
                continue
            demands.append(
                RoutingDemand(
                    demand_id=f"{demand_class}_{offset + len(demands)}",
                    demand_class=demand_class,
                    kind=kind,
                    source=source.name,
                    sink=sink_names[0],
                    sinks=sink_names,
                )
            )
            if len(demands) >= limit:
                return demands
    return demands


def _fanout_sink_names(
    source_name: str,
    reachable: list[RoutingTerminal],
    unreachable: list[RoutingTerminal],
    count: int,
) -> list[str]:
    """Return sink names for a fanout demand.

    Parameters
    ----------
    source_name : str
        Source name to avoid.
    reachable : list[RoutingTerminal]
        Reachable sink candidates.
    unreachable : list[RoutingTerminal]
        Unreachable sink candidates used to expose under-fanout.
    count : int
        Desired sink count.

    Returns
    -------
    list[str]
        Unique sink names.
    """
    names: list[str] = []
    for sink in [*reachable, *unreachable]:
        name = sink.name
        if name == source_name or name in names:
            continue
        names.append(name)
        if len(names) >= count:
            break
    return names


def _matrix_rows_driven_by_terminals(
    matrix: MatrixData,
    terminals: list[RoutingTerminal],
    graph: RoutingGraph,
) -> list[RoutingTerminal]:
    """Return matrix destination rows driven by selected terminals.

    Parameters
    ----------
    matrix : MatrixData
        Loaded matrix data.
    terminals : list[RoutingTerminal]
        Source terminals to search for in matrix source lists.
    graph : RoutingGraph
        Routing graph.

    Returns
    -------
    list[RoutingTerminal]
        Matrix row endpoints driven by matching sources.
    """
    source_names = {terminal.name for terminal in terminals}
    if not source_names:
        return []
    rows = [
        row
        for row, sources in matrix.connections.items()
        if graph.has_node(row) and any(source in source_names for source in sources)
    ]
    return _matrix_terminals(matrix, rows, graph)


def _matrix_source_routing_terminals(
    matrix: MatrixData,
    graph: RoutingGraph,
) -> list[RoutingTerminal]:
    """Return routing-resource terminals used on the matrix source side.

    Parameters
    ----------
    matrix : MatrixData
        Loaded matrix data.
    graph : RoutingGraph
        Routing graph.

    Returns
    -------
    list[RoutingTerminal]
        Matrix source-side routing terminals.
    """
    source_names = sorted(
        {
            source
            for sources in matrix.connections.values()
            for source in sources
            if graph.has_node(source)
        }
    )
    return [
        terminal
        for terminal in _matrix_terminals(matrix, source_names, graph)
        if _is_routing_terminal(terminal)
    ]


def _matrix_source_terminals(
    matrix: MatrixData,
    graph: RoutingGraph,
) -> list[RoutingTerminal]:
    """Return graph-present matrix source terminals.

    Parameters
    ----------
    matrix : MatrixData
        Loaded matrix data.
    graph : RoutingGraph
        Routing graph.

    Returns
    -------
    list[RoutingTerminal]
        Matrix source terminals.
    """
    source_names = sorted(
        {
            source
            for sources in matrix.connections.values()
            for source in sources
            if graph.has_node(source)
        }
    )
    return _matrix_terminals(matrix, source_names, graph)


def _matrix_row_routing_terminals(
    matrix: MatrixData,
    graph: RoutingGraph,
) -> list[RoutingTerminal]:
    """Return routing-resource terminals used as matrix destination rows.

    Parameters
    ----------
    matrix : MatrixData
        Loaded matrix data.
    graph : RoutingGraph
        Routing graph.

    Returns
    -------
    list[RoutingTerminal]
        Matrix row-side routing terminals.
    """
    return [
        terminal
        for terminal in _matrix_terminals(matrix, matrix.connections.keys(), graph)
        if _is_routing_terminal(terminal)
    ]


def _matrix_row_terminals(
    matrix: MatrixData,
    graph: RoutingGraph,
) -> list[RoutingTerminal]:
    """Return graph-present matrix destination row terminals.

    Parameters
    ----------
    matrix : MatrixData
        Loaded matrix data.
    graph : RoutingGraph
        Routing graph.

    Returns
    -------
    list[RoutingTerminal]
        Matrix row terminals.
    """
    return _matrix_terminals(matrix, matrix.connections.keys(), graph)


def _matrix_terminals(
    matrix: MatrixData,
    names: Iterable[str],
    graph: RoutingGraph,
) -> list[RoutingTerminal]:
    """Return terminals for matrix node names.

    Parameters
    ----------
    matrix : MatrixData
        Loaded matrix data.
    names : Iterable[str]
        Iterable matrix node names.
    graph : RoutingGraph
        Routing graph.

    Returns
    -------
    list[RoutingTerminal]
        Existing classified terminals or generated matrix terminals.
    """
    terminal_by_name = {terminal.name: terminal for terminal in matrix.terminals}
    generated_jump_roles = _generated_jump_roles(matrix)
    result: list[RoutingTerminal] = []
    seen: set[str] = set()
    for name in names:
        if not isinstance(name, str) or name in seen or not graph.has_node(name):
            continue
        seen.add(name)
        result.append(
            terminal_by_name.get(name)
            or RoutingTerminal(
                name=name,
                role=generated_jump_roles.get(name) or RoutingTerminalRole.TILE_OUTPUT,
                source=RoutingTerminalSource.GENERATED,
            )
        )
    return result


def _generated_jump_roles(
    matrix: MatrixData,
) -> dict[str, RoutingTerminalRole]:
    """Return metadata-derived JUMP roles for generated matrix nodes.

    Parameters
    ----------
    matrix : MatrixData
        Loaded matrix data.

    Returns
    -------
    dict[str, RoutingTerminalRole]
        Generated node names mapped to roles inferred from FabGraph JUMP metadata.
    """
    roles: dict[str, RoutingTerminalRole] = {}
    for jump_begin, jump_end in matrix.jump_edges:
        roles[jump_begin] = RoutingTerminalRole.JUMP_BEGIN
        roles[jump_end] = RoutingTerminalRole.JUMP_END
    return roles


def _generic_bel_input_terminals(
    matrix: MatrixData,
    graph: RoutingGraph,
) -> list[RoutingTerminal]:
    """Return generic BEL inputs, excluding special direct/control terminals.

    Parameters
    ----------
    matrix : MatrixData
        Loaded matrix data.
    graph : RoutingGraph
        Routing graph.

    Returns
    -------
    list[RoutingTerminal]
        Generic BEL-input terminals.
    """
    return [
        terminal
        for terminal in _terminals(matrix, [RoutingTerminalRole.BEL_INPUT], graph)
        if _is_generic_bel_input(terminal, matrix)
    ]


def _generic_bel_output_terminals(
    matrix: MatrixData,
    graph: RoutingGraph,
) -> list[RoutingTerminal]:
    """Return BEL outputs that escape into general routing rows.

    Parameters
    ----------
    matrix : MatrixData
        Loaded matrix data.
    graph : RoutingGraph
        Routing graph.

    Returns
    -------
    list[RoutingTerminal]
        Generic BEL-output terminals.
    """
    outputs = _terminals(matrix, [RoutingTerminalRole.BEL_OUTPUT], graph)
    return [
        output
        for output in outputs
        if any(
            _is_routing_terminal(row)
            and not _is_single_source_tile_output_row(matrix, row)
            for row in _matrix_rows_driven_by_terminals(matrix, [output], graph)
        )
    ]


def _generic_bel_input_sources(
    matrix: MatrixData,
    graph: RoutingGraph,
) -> list[RoutingTerminal]:
    """Return source terminals for generic BEL-input reachability.

    Parameters
    ----------
    matrix : MatrixData
        Loaded matrix data.
    graph : RoutingGraph
        Routing graph.

    Returns
    -------
    list[RoutingTerminal]
        Source terminals for generic BEL-input demands.
    """
    sources = [
        terminal
        for terminal in _matrix_source_routing_terminals(matrix, graph)
        if terminal.role
        not in {RoutingTerminalRole.JUMP_BEGIN, RoutingTerminalRole.JUMP_END}
    ]
    sources.extend(_terminals(matrix, [RoutingTerminalRole.CONSTANT], graph))
    sources.extend(_generic_bel_output_terminals(matrix, graph))
    return _dedupe_by_name(sources)


def _dedupe_by_name(terminals: list[RoutingTerminal]) -> list[RoutingTerminal]:
    """Remove duplicate terminals by node name.

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


def _is_single_source_tile_output_row(
    matrix: MatrixData,
    terminal: RoutingTerminal,
) -> bool:
    """Return whether a row is a direct one-source tile output.

    Parameters
    ----------
    matrix : MatrixData
        Loaded matrix data.
    terminal : RoutingTerminal
        Matrix row terminal.

    Returns
    -------
    bool
        Whether the row is a direct tile output with one selectable source.
    """
    return (
        terminal.role == RoutingTerminalRole.TILE_OUTPUT
        and terminal.source == RoutingTerminalSource.TILE_PORT
        and len(matrix.connections.get(terminal.name, [])) == 1
    )


def _is_generic_bel_input(
    terminal: RoutingTerminal,
    matrix: MatrixData,
) -> bool:
    """Return whether a BEL input belongs to general routing access.

    Parameters
    ----------
    terminal : RoutingTerminal
        BEL input terminal.
    matrix : MatrixData
        Loaded matrix data.

    Returns
    -------
    bool
        Whether the BEL input is driven directly or through JUMP hierarchy.
    """
    sources = matrix.connections.get(terminal.name, [])
    if len(sources) > 1:
        return True
    return any(_is_hierarchy_jump_source(source, matrix, set()) for source in sources)


def _is_hierarchy_jump_source(
    node: str,
    matrix: MatrixData,
    visited: set[str],
) -> bool:
    """Return whether a node traces through JUMP hierarchy.

    Parameters
    ----------
    node : str
        Matrix node name to inspect.
    matrix : MatrixData
        Loaded matrix data.
    visited : set[str]
        Nodes already visited during recursion.

    Returns
    -------
    bool
        Whether the node is fed by an upstream JUMP begin row.
    """
    if node in visited:
        return False
    visited.add(node)
    jump_begins = [
        jump_begin for jump_begin, jump_end in matrix.jump_edges if jump_end == node
    ]
    for jump_begin in jump_begins:
        sources = matrix.connections.get(jump_begin, [])
        if sources:
            return True
        if any(
            _is_hierarchy_jump_source(source, matrix, visited) for source in sources
        ):
            return True
    return False


def _is_routing_terminal(terminal: RoutingTerminal) -> bool:
    """Return whether a terminal should be treated as a routing resource.

    Parameters
    ----------
    terminal : RoutingTerminal
        Candidate terminal.

    Returns
    -------
    bool
        Whether the terminal belongs to the general routing fabric.
    """
    return terminal.role in {
        RoutingTerminalRole.TILE_INPUT,
        RoutingTerminalRole.TILE_OUTPUT,
        RoutingTerminalRole.JUMP_BEGIN,
        RoutingTerminalRole.JUMP_END,
    }


def _terminals(
    matrix: MatrixData,
    roles: list[RoutingTerminalRole],
    graph: RoutingGraph,
) -> list[RoutingTerminal]:
    """Return graph-present terminals with selected roles.

    Parameters
    ----------
    matrix : MatrixData
        Loaded matrix data.
    roles : list[RoutingTerminalRole]
        Roles to include.
    graph : RoutingGraph
        Routing graph.

    Returns
    -------
    list[RoutingTerminal]
        Matching terminals.
    """
    role_set = set(roles)
    return [
        terminal
        for terminal in matrix.terminals
        if terminal.role in role_set and graph.has_node(terminal.name)
    ]


def _first_reachable_source(
    sources: list[RoutingTerminal],
    sink: RoutingTerminal,
    graph: RoutingGraph,
) -> RoutingTerminal | None:
    """Return the first source that can reach a sink.

    Parameters
    ----------
    sources : list[RoutingTerminal]
        Candidate source terminals.
    sink : RoutingTerminal
        Sink terminal.
    graph : RoutingGraph
        Routing graph.

    Returns
    -------
    RoutingTerminal | None
        Reachable source, or ``None`` if no candidate can reach the sink.
    """
    for source in sources:
        if source.name == sink.name:
            continue
        if graph.is_reachable(source.name, sink.name):
            return source
    return None


def _first_reachable_sink(
    source: RoutingTerminal,
    sinks: list[RoutingTerminal],
    graph: RoutingGraph,
) -> RoutingTerminal | None:
    """Return the first sink reachable from a source.

    Parameters
    ----------
    source : RoutingTerminal
        Source terminal.
    sinks : list[RoutingTerminal]
        Candidate sink terminals.
    graph : RoutingGraph
        Routing graph.

    Returns
    -------
    RoutingTerminal | None
        Reachable sink, or ``None`` if no candidate is reachable.
    """
    for sink in sinks:
        if source.name == sink.name:
            continue
        if graph.is_reachable(source.name, sink.name):
            return sink
    return None


def _terminal_sources(matrix: MatrixData, graph: RoutingGraph) -> list[RoutingTerminal]:
    """Return meaningful source terminals.

    Parameters
    ----------
    matrix : MatrixData
        Loaded matrix data.
    graph : RoutingGraph
        Routing graph.

    Returns
    -------
    list[RoutingTerminal]
        Source-capable terminals.
    """
    return _terminals(
        matrix,
        [
            RoutingTerminalRole.BEL_OUTPUT,
            RoutingTerminalRole.TILE_OUTPUT,
            RoutingTerminalRole.EXTERNAL_INPUT,
            RoutingTerminalRole.EXTERNAL_OUTPUT,
            RoutingTerminalRole.CONSTANT,
        ],
        graph,
    )


def _terminal_sinks(matrix: MatrixData, graph: RoutingGraph) -> list[RoutingTerminal]:
    """Return meaningful sink terminals.

    Parameters
    ----------
    matrix : MatrixData
        Loaded matrix data.
    graph : RoutingGraph
        Routing graph.

    Returns
    -------
    list[RoutingTerminal]
        Sink-capable terminals.
    """
    return _terminals(
        matrix,
        [
            RoutingTerminalRole.BEL_INPUT,
            RoutingTerminalRole.TILE_INPUT,
            RoutingTerminalRole.EXTERNAL_INPUT,
            RoutingTerminalRole.EXTERNAL_OUTPUT,
            RoutingTerminalRole.LOCAL_RESET,
            RoutingTerminalRole.LOCAL_ENABLE,
            RoutingTerminalRole.SHARED_RESET,
            RoutingTerminalRole.SHARED_ENABLE,
        ],
        graph,
    )


def _routing_terminals_by_distance(
    matrix: MatrixData,
    graph: RoutingGraph,
    long: bool,
    source: bool,
) -> list[RoutingTerminal]:
    """Return routing terminals by port span.

    Parameters
    ----------
    matrix : MatrixData
        Loaded matrix data.
    graph : RoutingGraph
        Routing graph.
    long : bool
        Select long-distance terminals if ``True``.
    source : bool
        Select source-capable terminals if ``True``.

    Returns
    -------
    list[RoutingTerminal]
        Matching terminals.
    """
    role = RoutingTerminalRole.TILE_OUTPUT if source else RoutingTerminalRole.TILE_INPUT
    return [
        terminal
        for terminal in _terminals(matrix, [role], graph)
        if (_terminal_span(terminal) > 1) == long
    ]


def _terminal_span(terminal: RoutingTerminal) -> int:
    """Return the Manhattan span of one terminal.

    Parameters
    ----------
    terminal : RoutingTerminal
        Terminal.

    Returns
    -------
    int
        Manhattan span.
    """
    return abs(terminal.x_offset) + abs(terminal.y_offset)


def _distance_matches(
    source: RoutingTerminal,
    sink: RoutingTerminal,
    distance: Literal["local", "medium", "long"],
) -> bool:
    """Return whether a terminal pair matches a distance bucket.

    Parameters
    ----------
    source : RoutingTerminal
        Source terminal.
    sink : RoutingTerminal
        Sink terminal.
    distance : Literal["local", "medium", "long"]
        Distance bucket.

    Returns
    -------
    bool
        Whether the pair belongs to the bucket.
    """
    span = max(_terminal_span(source), _terminal_span(sink))
    if distance == "local":
        return span <= 1
    if distance == "medium":
        return span == 2
    return span >= 3

"""Access-oriented routing-demand class generators."""

from __future__ import annotations

from typing import TYPE_CHECKING

from fabulous.fabric_cad.fabxplore.modules.routing_demand_evaluator.core.models import (
    DemandClassName,
    DemandKind,
    RoutingDemand,
    RoutingTerminalRole,
)
from fabulous.fabric_cad.fabxplore.modules.routing_demand_evaluator.demand_classes.common import (  # noqa: E501
    _coverage_by_sink,
    _coverage_by_source,
    _generic_bel_input_sources,
    _generic_bel_input_terminals,
    _generic_bel_output_terminals,
    _matrix_rows_driven_by_terminals,
    _terminals,
)

if TYPE_CHECKING:
    from fabulous.fabric_cad.fabxplore.modules.routing_demand_evaluator.core.models import (  # noqa: E501
        MatrixData,
    )
    from fabulous.fabric_cad.fabxplore.modules.routing_demand_evaluator.core.routing_graph import (  # noqa: E501
        RoutingGraph,
    )


def bel_output_escape(
    matrix: MatrixData,
    graph: RoutingGraph,
    limit: int,
    offset: int,
) -> list[RoutingDemand]:
    """Generate BEL-output-to-routing escape demands.

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
        DemandClassName.BEL_OUTPUT_ESCAPE,
        DemandKind.HARD,
        _generic_bel_output_terminals(matrix, graph),
        _matrix_rows_driven_by_terminals(
            matrix,
            _generic_bel_output_terminals(matrix, graph),
            graph,
        ),
        limit,
        offset,
        graph,
    )


def bel_input_reachability(
    matrix: MatrixData,
    graph: RoutingGraph,
    limit: int,
    offset: int,
) -> list[RoutingDemand]:
    """Generate routing-to-BEL-input reachability demands.

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
        DemandClassName.BEL_INPUT_REACHABILITY,
        DemandKind.HARD,
        _generic_bel_input_sources(matrix, graph),
        _generic_bel_input_terminals(matrix, graph),
        limit,
        offset,
        graph,
    )


def bel_input_source_coverage(
    matrix: MatrixData,
    graph: RoutingGraph,
    limit: int,
    offset: int,
) -> list[RoutingDemand]:
    """Generate individual source-to-BEL-input coverage demands.

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
    demands: list[RoutingDemand] = []
    sources = _generic_bel_input_sources(matrix, graph)
    sinks = _generic_bel_input_terminals(matrix, graph)
    reachable_by_source: list[list[tuple[str, str]]] = []
    unreachable_by_source: list[list[tuple[str, str]]] = []
    for source in sources:
        reachable: list[tuple[str, str]] = []
        unreachable: list[tuple[str, str]] = []
        for sink in sinks:
            if source.name == sink.name:
                continue
            if not graph.is_reachable(source.name, sink.name):
                unreachable.append((source.name, sink.name))
            else:
                reachable.append((source.name, sink.name))
        if reachable:
            reachable_by_source.append(reachable)
        if unreachable:
            unreachable_by_source.append(unreachable)

    for source, sink in _interleave_pairs(
        _round_robin_pairs(reachable_by_source),
        _round_robin_pairs(unreachable_by_source),
    ):
        demands.append(
            RoutingDemand(
                demand_id=(
                    f"{DemandClassName.BEL_INPUT_SOURCE_COVERAGE}_"
                    f"{offset + len(demands)}"
                ),
                demand_class=DemandClassName.BEL_INPUT_SOURCE_COVERAGE,
                kind=DemandKind.SOFT,
                source=source,
                sink=sink,
            )
        )
        if len(demands) >= limit:
            return demands
    return demands


def _round_robin_pairs(
    grouped_pairs: list[list[tuple[str, str]]],
) -> list[tuple[str, str]]:
    """Flatten source-grouped pairs by depth first.

    Parameters
    ----------
    grouped_pairs : list[list[tuple[str, str]]]
        Pair lists grouped by source terminal.

    Returns
    -------
    list[tuple[str, str]]
        Flattened pairs spread across source terminals.
    """
    result: list[tuple[str, str]] = []
    max_depth = max((len(pairs) for pairs in grouped_pairs), default=0)
    for depth in range(max_depth):
        for pairs in grouped_pairs:
            if depth < len(pairs):
                result.append(pairs[depth])
    return result


def _interleave_pairs(
    first: list[tuple[str, str]],
    second: list[tuple[str, str]],
) -> list[tuple[str, str]]:
    """Return pair lists interleaved by index.

    Parameters
    ----------
    first : list[tuple[str, str]]
        First pair list.
    second : list[tuple[str, str]]
        Second pair list.

    Returns
    -------
    list[tuple[str, str]]
        Interleaved pairs.
    """
    result: list[tuple[str, str]] = []
    for index in range(max(len(first), len(second))):
        if index < len(first):
            result.append(first[index])
        if index < len(second):
            result.append(second[index])
    return result


def dsp_ram_access(
    matrix: MatrixData,
    graph: RoutingGraph,
    limit: int,
    offset: int,
) -> list[RoutingDemand]:
    """Generate external-BEL style DSP/RAM access demands.

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
        DemandClassName.DSP_RAM_ACCESS,
        DemandKind.SOFT,
        _terminals(matrix, [RoutingTerminalRole.TILE_OUTPUT], graph),
        _terminals(matrix, [RoutingTerminalRole.EXTERNAL_INPUT], graph),
        limit,
        offset,
        graph,
    ) + _coverage_by_source(
        DemandClassName.DSP_RAM_ACCESS,
        DemandKind.SOFT,
        _terminals(matrix, [RoutingTerminalRole.EXTERNAL_OUTPUT], graph),
        _terminals(matrix, [RoutingTerminalRole.TILE_INPUT], graph),
        max(0, limit // 2),
        offset + limit,
        graph,
    )


def io_access(
    matrix: MatrixData,
    graph: RoutingGraph,
    limit: int,
    offset: int,
) -> list[RoutingDemand]:
    """Generate IO-style access demands.

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
        DemandClassName.IO_ACCESS,
        DemandKind.SOFT,
        _terminals(matrix, [RoutingTerminalRole.EXTERNAL_INPUT], graph),
        _generic_bel_input_terminals(matrix, graph),
        limit,
        offset,
        graph,
    ) + _coverage_by_source(
        DemandClassName.IO_ACCESS,
        DemandKind.SOFT,
        _generic_bel_output_terminals(matrix, graph),
        _terminals(matrix, [RoutingTerminalRole.EXTERNAL_OUTPUT], graph),
        max(0, limit // 2),
        offset + limit,
        graph,
    )

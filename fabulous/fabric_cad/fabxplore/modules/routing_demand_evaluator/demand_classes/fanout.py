"""Fanout-oriented routing-demand class generators."""

from __future__ import annotations

from typing import TYPE_CHECKING

from fabulous.fabric_cad.fabxplore.modules.routing_demand_evaluator.core.models import (
    DemandClassName,
    DemandKind,
    RoutingTerminalRole,
)
from fabulous.fabric_cad.fabxplore.modules.routing_demand_evaluator.demand_classes.common import (  # noqa: E501
    _coverage_by_sink,
    _fanout_demands,
    _generic_bel_input_terminals,
    _generic_bel_output_terminals,
    _terminal_sources,
    _terminals,
)

if TYPE_CHECKING:
    from fabulous.fabric_cad.fabxplore.modules.routing_demand_evaluator.core.models import (  # noqa: E501
        MatrixData,
        RoutingDemand,
        RoutingDemandEvaluatorOptions,
    )
    from fabulous.fabric_cad.fabxplore.modules.routing_demand_evaluator.core.routing_graph import (  # noqa: E501
        RoutingGraph,
    )


def bel_input_fanout(
    options: RoutingDemandEvaluatorOptions,
    matrix: MatrixData,
    graph: RoutingGraph,
    limit: int,
    offset: int,
) -> list[RoutingDemand]:
    """Generate same-tile one-net-to-many-BEL-input demands.

    Parameters
    ----------
    options : RoutingDemandEvaluatorOptions
        Evaluator options.
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
    return _fanout_demands(
        DemandClassName.BEL_INPUT_FANOUT,
        DemandKind.SOFT,
        options,
        _generic_bel_output_terminals(matrix, graph),
        _generic_bel_input_terminals(matrix, graph),
        limit,
        offset,
        graph,
    )


def control_reachability(
    matrix: MatrixData,
    graph: RoutingGraph,
    limit: int,
    offset: int,
) -> list[RoutingDemand]:
    """Generate source-to-control-terminal reachability demands.

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
    sinks = _terminals(
        matrix,
        [
            RoutingTerminalRole.LOCAL_RESET,
            RoutingTerminalRole.LOCAL_ENABLE,
            RoutingTerminalRole.SHARED_RESET,
            RoutingTerminalRole.SHARED_ENABLE,
        ],
        graph,
    )
    return _coverage_by_sink(
        DemandClassName.CONTROL_REACHABILITY,
        DemandKind.HARD,
        _terminal_sources(matrix, graph),
        sinks,
        limit,
        offset,
        graph,
    )


def control_net(
    options: RoutingDemandEvaluatorOptions,
    matrix: MatrixData,
    graph: RoutingGraph,
    limit: int,
    offset: int,
) -> list[RoutingDemand]:
    """Generate control-like high-fanout demands.

    Parameters
    ----------
    options : RoutingDemandEvaluatorOptions
        Evaluator options.
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
    sinks = _terminals(
        matrix,
        [
            RoutingTerminalRole.LOCAL_RESET,
            RoutingTerminalRole.LOCAL_ENABLE,
            RoutingTerminalRole.SHARED_RESET,
            RoutingTerminalRole.SHARED_ENABLE,
        ],
        graph,
    )

    return _fanout_demands(
        DemandClassName.CONTROL_NET,
        DemandKind.SOFT,
        options,
        _terminal_sources(matrix, graph),
        sinks,
        limit,
        offset,
        graph,
    )

"""Carry-chain routing-demand class generators."""

from __future__ import annotations

from typing import TYPE_CHECKING

from fabulous.fabric_cad.fabxplore.modules.routing_demand_evaluator.core.models import (
    DemandClassName,
    DemandKind,
    RoutingDemand,
    RoutingTerminalRole,
)
from fabulous.fabric_cad.fabxplore.modules.routing_demand_evaluator.demand_classes.common import (  # noqa: E501
    _terminals,
)

if TYPE_CHECKING:
    from fabulous.fabric_cad.fabxplore.modules.routing_demand_evaluator.core.models import (  # noqa: E501
        MatrixData,
    )
    from fabulous.fabric_cad.fabxplore.modules.routing_demand_evaluator.core.routing_graph import (  # noqa: E501
        RoutingGraph,
    )


def carry_chain(
    matrix: MatrixData,
    graph: RoutingGraph,
    limit: int,
    offset: int,
) -> list[RoutingDemand]:
    """Generate carry-chain demands from carry outputs to carry inputs.

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
    carry_names = {
        terminal.name
        for terminal in _terminals(
            matrix,
            [RoutingTerminalRole.CARRY_INPUT, RoutingTerminalRole.CARRY_OUTPUT],
            graph,
        )
    }
    demands: list[RoutingDemand] = []
    for sink, sources in matrix.connections.items():
        if sink not in carry_names or not graph.has_node(sink):
            continue
        for source in sources:
            if source not in carry_names or not graph.has_node(source):
                continue
            demands.append(
                RoutingDemand(
                    demand_id=f"{DemandClassName.CARRY_CHAIN}_{offset + len(demands)}",
                    demand_class=DemandClassName.CARRY_CHAIN,
                    kind=DemandKind.HARD,
                    source=source,
                    sink=sink,
                )
            )
            if len(demands) >= limit:
                return demands
    return demands

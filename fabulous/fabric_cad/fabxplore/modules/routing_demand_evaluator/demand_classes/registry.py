"""Registry for internal routing-demand classes."""

from __future__ import annotations

from typing import TYPE_CHECKING

from fabulous.fabric_cad.fabxplore.modules.routing_demand_evaluator.core.models import (
    DemandClassName,
    RoutingDemand,
)
from fabulous.fabric_cad.fabxplore.modules.routing_demand_evaluator.demand_classes import (  # noqa: E501
    access,
    carry,
    fanout,
    feedback,
    random,
    routing,
)

if TYPE_CHECKING:
    from random import Random

    from fabulous.fabric_cad.fabxplore.modules.routing_demand_evaluator.core.models import (  # noqa: E501
        MatrixData,
        RoutingDemandEvaluatorOptions,
    )
    from fabulous.fabric_cad.fabxplore.modules.routing_demand_evaluator.core.routing_graph import (  # noqa: E501
        RoutingGraph,
    )


def generate_demand_class(
    demand_class: DemandClassName,
    options: RoutingDemandEvaluatorOptions,
    matrix: MatrixData,
    graph: RoutingGraph,
    rng: Random,
    limit: int,
    offset: int,
) -> list[RoutingDemand]:
    """Generate demands for one internal demand class.

    Parameters
    ----------
    demand_class : DemandClassName
        Demand class to generate.
    options : RoutingDemandEvaluatorOptions
        Evaluator options.
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

    Returns
    -------
    list[RoutingDemand]
        Generated demands.

    Raises
    ------
    ValueError
        If the demand class is unknown.
    """
    match demand_class:
        case DemandClassName.BEL_OUTPUT_ESCAPE:
            return access.bel_output_escape(matrix, graph, limit, offset)
        case DemandClassName.BEL_INPUT_REACHABILITY:
            return access.bel_input_reachability(matrix, graph, limit, offset)
        case DemandClassName.BEL_INPUT_SOURCE_COVERAGE:
            return access.bel_input_source_coverage(matrix, graph, limit, offset)
        case DemandClassName.MATRIX_ROW_COVERAGE:
            return routing.matrix_row_coverage(matrix, graph, limit, offset)
        case DemandClassName.MATRIX_SOURCE_USEFULNESS:
            return routing.matrix_source_usefulness(matrix, graph, limit, offset)
        case DemandClassName.FANIN_DIVERSITY:
            return routing.fanin_diversity(matrix, graph, limit, offset)
        case DemandClassName.SOURCE_FANOUT_DIVERSITY:
            return routing.source_fanout_diversity(matrix, graph, limit, offset)
        case DemandClassName.SIDE_PAIR_BALANCE:
            return routing.side_pair_balance(matrix, graph, limit, offset)
        case DemandClassName.HIERARCHY_INTEGRITY:
            return routing.hierarchy_integrity(matrix, graph, limit, offset)
        case DemandClassName.LOCAL_FEEDBACK:
            return feedback.local_feedback(matrix, graph, limit, offset)
        case DemandClassName.NEIGHBOR_FEEDBACK:
            return feedback.neighbor_feedback(matrix, graph, limit, offset)
        case DemandClassName.STRAIGHT_ROUTING:
            return routing.straight_routing(matrix, graph, limit, offset)
        case DemandClassName.TURN_ROUTING:
            return routing.turn_routing(matrix, graph, limit, offset)
        case DemandClassName.SHORT_TO_LONG:
            return routing.short_to_long(matrix, graph, limit, offset)
        case DemandClassName.LONG_TO_SHORT:
            return routing.long_to_short(matrix, graph, limit, offset)
        case DemandClassName.MULTI_HOP:
            return routing.multi_hop(matrix, graph, limit, offset)
        case DemandClassName.ROUTING_REDUNDANCY:
            return routing.routing_redundancy(matrix, graph, limit, offset)
        case DemandClassName.BEL_INPUT_FANOUT:
            return fanout.bel_input_fanout(options, matrix, graph, limit, offset)
        case DemandClassName.CONTROL_REACHABILITY:
            return fanout.control_reachability(matrix, graph, limit, offset)
        case DemandClassName.CONTROL_NET:
            return fanout.control_net(options, matrix, graph, limit, offset)
        case DemandClassName.CARRY_CHAIN:
            return carry.carry_chain(matrix, graph, limit, offset)
        case DemandClassName.DSP_RAM_ACCESS:
            return access.dsp_ram_access(matrix, graph, limit, offset)
        case DemandClassName.IO_ACCESS:
            return access.io_access(matrix, graph, limit, offset)
        case DemandClassName.RANDOM_LOCAL:
            return random.random_terminal_pairs(
                demand_class,
                matrix,
                graph,
                rng,
                limit,
                offset,
                distance="local",
            )
        case DemandClassName.RANDOM_MEDIUM:
            return random.random_terminal_pairs(
                demand_class,
                matrix,
                graph,
                rng,
                limit,
                offset,
                distance="medium",
            )
        case DemandClassName.RANDOM_LONG:
            return random.random_terminal_pairs(
                demand_class,
                matrix,
                graph,
                rng,
                limit,
                offset,
                distance="long",
            )
        case _:
            raise ValueError(f"Unknown demand class: {demand_class}")

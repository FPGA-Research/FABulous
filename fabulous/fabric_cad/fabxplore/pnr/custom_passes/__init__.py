"""Custom placement and routing (PnR) passes for FABulous."""

from fabulous.fabric_cad.fabxplore.pnr.custom_passes import (
    routing_demand_evaluator_pass,
    switch_block_factorizer_pass,
)
from fabulous.fabric_cad.fabxplore.pnr.custom_passes.tile_builder_pass import (
    TileBuilderPass,
)

RoutingDemandEvaluatorPass = routing_demand_evaluator_pass.RoutingDemandEvaluatorPass
SwitchBlockFactorizerPass = switch_block_factorizer_pass.SwitchBlockFactorizerPass

__all__ = [
    "RoutingDemandEvaluatorPass",
    "SwitchBlockFactorizerPass",
    "TileBuilderPass",
]

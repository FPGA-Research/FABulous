"""Custom placement and routing (PnR) passes for FABulous."""

from fabulous.fabric_cad.fabxplore.pnr.custom_passes import (
    fabric_router_pass,
    routing_demand_evaluator_pass,
    switch_block_factorizer_pass,
)
from fabulous.fabric_cad.fabxplore.pnr.custom_passes.tile_builder_pass import (
    TileBuilderPass,
)

FabricRouterPass = fabric_router_pass.FabricRouterPass
RoutingDemandEvaluatorPass = routing_demand_evaluator_pass.RoutingDemandEvaluatorPass
SwitchBlockFactorizerPass = switch_block_factorizer_pass.SwitchBlockFactorizerPass

__all__ = [
    "FabricRouterPass",
    "RoutingDemandEvaluatorPass",
    "SwitchBlockFactorizerPass",
    "TileBuilderPass",
]

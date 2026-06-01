"""Custom placement and routing (PnR) passes for FABulous."""

from fabulous.fabric_cad.fabxplore.pnr.custom_passes import (
    inverse_router_pass,
    routing_demand_evaluator_pass,
    switch_block_factorizer_pass,
    switch_matrix_pattern_pass,
)
from fabulous.fabric_cad.fabxplore.pnr.custom_passes.tile_builder_pass import (
    TileBuilderPass,
)

InverseRouterPass = inverse_router_pass.InverseRouterPass
RoutingDemandEvaluatorPass = routing_demand_evaluator_pass.RoutingDemandEvaluatorPass
SwitchBlockFactorizerPass = switch_block_factorizer_pass.SwitchBlockFactorizerPass
SwitchMatrixPatternPass = switch_matrix_pattern_pass.SwitchMatrixPatternPass

__all__ = [
    "InverseRouterPass",
    "RoutingDemandEvaluatorPass",
    "SwitchBlockFactorizerPass",
    "SwitchMatrixPatternPass",
    "TileBuilderPass",
]

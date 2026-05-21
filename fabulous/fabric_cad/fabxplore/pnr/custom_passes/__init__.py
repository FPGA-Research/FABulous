"""Custom placement and routing (PnR) passes for FABulous."""

from fabulous.fabric_cad.fabxplore.pnr.custom_passes import (
    switch_block_factorizer_pass,
)
from fabulous.fabric_cad.fabxplore.pnr.custom_passes.tile_builder_pass import (
    TileBuilderPass,
)

SwitchBlockFactorizerPass = switch_block_factorizer_pass.SwitchBlockFactorizerPass

__all__ = [
    "SwitchBlockFactorizerPass",
    "TileBuilderPass",
]

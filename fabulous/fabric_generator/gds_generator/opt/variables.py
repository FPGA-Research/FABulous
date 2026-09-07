"""LibreLane variables shared by the placement-driven optimisation steps.

Two switches select the optimisations. `FABULOUS_OPT_CONFIG_MAPPING` reassigns
configuration bits to the frame crosspoints nearest their latches and
`FABULOUS_OPT_TILE_INTERFACE` orders the border pins by the logic they feed.
Either one makes `TileAreaOptimisation` carry proposals from one iteration into
the next. The remaining variables are how the loop hands an iteration its
inputs; a flow sets them once, the loop rewrites them per iteration.
"""

from librelane.common.types import Path as LibrelanePath
from librelane.config.variable import Variable

from fabulous.fabric_definition.define import ConfigBitMode

CONFIG_BIT_MODE_VARIABLE = Variable(
    "FABULOUS_CONFIG_BIT_MODE",
    ConfigBitMode,
    "Config-bit storage mode of the fabric the tile belongs to, which the "
    "generated switch matrix and configuration memory follow. The "
    "configuration mapping needs the frame grid, so it runs under "
    "FRAME_BASED only.",
    default=ConfigBitMode.FRAME_BASED,
)

CONFIG_MAPPING_VARIABLE = Variable(
    "FABULOUS_OPT_CONFIG_MAPPING",
    bool,
    "Reassign the configuration bits to the frame crosspoints nearest their "
    "placed latches, inside the tile area optimisation, applying each "
    "iteration's proposal to the next. Off, the tile implements its "
    "`ConfigMem.csv` as written.",
    default=False,
)

TILE_INTERFACE_VARIABLE = Variable(
    "FABULOUS_OPT_TILE_INTERFACE",
    bool,
    "Order the border pins by the placed logic they feed, inside the tile area "
    "optimisation, applying each iteration's proposal to the next. Pairs "
    "already listed in `FABULOUS_TILE_INTERFACE_ORDER` keep their rank, so a "
    "border shared with an already hardened tile keeps abutting it.",
    default=False,
)

PLACEMENT_ITERATIONS_VARIABLE = Variable(
    "FABULOUS_OPT_PLACEMENT_ITERATIONS",
    int,
    "Iterations of the placement-driven optimisations. Under no_opt this many "
    "iterations run at the fixed die. Under balance and large the die grows to "
    "its first clean iteration under the usual cap, then this many more "
    "iterations shrink it after each clean one and hold it after a failed one.",
    default=10,
)

ROUTE_EVERY_ITERATION_VARIABLE = Variable(
    "FABULOUS_OPT_ROUTE_EVERY_ITERATION",
    bool,
    "Under no_opt, route every iteration and pick the winner by routed "
    "wirelength. Off, only the final iteration is routed and the earlier ones "
    "stop after their proposals.",
    default=False,
)

CONFIG_MEM_CSV_VARIABLE = Variable(
    "FABULOUS_CONFIG_MEM_CSV",
    LibrelanePath | None,
    "The current `<tile>_ConfigMem.csv` of the tile being hardened. Left unset "
    "for supertiles, whose configuration memories are not mapped on their own.",
    default=None,
)

CONFIG_MAPPING_TARGET_VARIABLE = Variable(
    "FABULOUS_CONFIG_MAPPING_TARGET",
    LibrelanePath | None,
    "The mapping the placed netlist implements when it differs from "
    "`FABULOUS_CONFIG_MEM_CSV`, which the loop sets per iteration.",
    default=None,
)

CONFIG_MAPPING_RECONNECT_VARIABLE = Variable(
    "FABULOUS_CONFIG_MAPPING_RECONNECT",
    LibrelanePath | None,
    "Reconnection list a previous iteration proposed; each listed latch pin is "
    "moved to the named frame port net. Unset, the netlist is implemented as "
    "synthesised.",
    default=None,
)

TILE_INTERFACE_ORDER_VARIABLE = Variable(
    "FABULOUS_TILE_INTERFACE_ORDER",
    LibrelanePath | None,
    "A tile interface order, a single-tile pin YAML naming pins exactly, that "
    "the border pins follow. Listed pins lead each border in the listed order "
    "and unlisted pins keep the default layout. Every tile sharing a border "
    "must be hardened with the same order.",
    default=None,
)

TILE_INTERFACE_FIXED_ORDER_VARIABLE = Variable(
    "FABULOUS_TILE_INTERFACE_FIXED_ORDER",
    LibrelanePath | None,
    "The interface order whose pairs the proposals keep in place, which the "
    "loop sets from `FABULOUS_TILE_INTERFACE_ORDER` before it rewrites that "
    "variable per iteration.",
    default=None,
)

TILE_INTERFACE_PAIRS_VARIABLE = Variable(
    "FABULOUS_TILE_INTERFACE_PAIRS",
    LibrelanePath | None,
    "YAML listing the bus pairs of the tile, one entry per fabric wire and "
    "per frame or clock chain with `axis`, `first`, `second`, `kind` and "
    "`scalar`. Left unset for supertiles, whose borders are not reordered.",
    default=None,
)

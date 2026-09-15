"""LibreLane variables of the placement-driven optimisations.

Two switches select them. `FABULOUS_OPT_CONFIG_MAPPING` reassigns configuration
bits to the frame crosspoints nearest their latches and
`FABULOUS_OPT_TILE_INTERFACE` orders the border pins by the logic they feed.
Either one makes the flow read the placement back, which is why the dump reads
both.
"""

from librelane.config.variable import Variable

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

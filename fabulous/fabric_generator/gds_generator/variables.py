"""LibreLane variables shared across the FABulous GDS flow.

A variable is declared here rather than at its step when more than one flow or
step reads it, so the name, the type and the default cannot drift apart.
"""

from librelane.common.types import Path as LibrelanePath
from librelane.config.variable import Variable

from fabulous.fabric_definition.define import ConfigBitMode

CONFIG_MAPPING_VARIABLE = Variable(
    "FABULOUS_OPT_CONFIG_MAPPING",
    bool,
    "Reassign the configuration bits to the frame crosspoints nearest their "
    "placed latches, inside the tile area optimisation, applying each "
    "iteration's proposal to the next. Off, the tile implements its "
    "`ConfigMem.csv` as written.",
    default=False,
)


IGNORE_ANTENNA_VIOLATIONS_VARIABLE = Variable(
    "IGNORE_ANTENNA_VIOLATIONS",
    bool,
    "Let an iteration finish with antenna violations rather than breaking off, "
    "which a search that only reads its numbers wants and a search that sizes "
    "the die does not.",
    default=False,
)

CONFIG_BIT_MODE_VARIABLE = Variable(
    "FABULOUS_CONFIG_BIT_MODE",
    ConfigBitMode,
    "Config-bit storage mode of the fabric the tile belongs to, which the "
    "generated switch matrix and configuration memory follow. The "
    "configuration mapping needs the frame grid, so it runs under "
    "FRAME_BASED only.",
    default=ConfigBitMode.FRAME_BASED,
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

PLACEMENT_ITERATIONS_VARIABLE = Variable(
    "FABULOUS_OPT_PLACEMENT_ITERATIONS",
    int,
    "How many placements the search may make before it gives up on the "
    "proposals settling. It stops earlier when an iteration proposes the "
    "inputs it was given, and exports the best-scoring iteration either way.",
    default=10,
)

ROUTE_EVERY_ITERATION_VARIABLE = Variable(
    "FABULOUS_OPT_ROUTE_EVERY_ITERATION",
    bool,
    "Route every iteration, which reports routed numbers for the search to be "
    "read by rather than steering it. Off, each iteration stops at its "
    "proposals, which are read before routing and so cannot depend on it.",
    default=False,
)

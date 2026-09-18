"""LibreLane variables shared across the FABulous GDS flow.

A variable named here is one more than one flow or step reads, so the name, the
type and the default are declared once rather than repeated wherever they are
consumed. `FABULOUS_OPT_CONFIG_MAPPING` reassigns configuration bits to the
frame crosspoints nearest their latches, and switching it on is what makes the
flow read the placement back. The rest are how the search hands an iteration its
inputs; a flow sets them once, the loop rewrites them per iteration.
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


IGNORE_ANTENNA_VIOLATIONS_VARIABLE = Variable(
    "IGNORE_ANTENNA_VIOLATIONS",
    bool,
    "Let an iteration finish with antenna violations rather than breaking off, "
    "which a search that only reads its numbers wants and a search that sizes "
    "the die does not.",
    default=False,
)

"""Config variables shared by several FABulous GDS steps.

A step lists these in its `config_vars` to receive them, since LibreLane filters
each step's config down to the variables the step declares.
"""

from librelane.config.variable import Variable

tile_logical_width_variable = Variable(
    "FABULOUS_TILE_LOGICAL_WIDTH",
    int,
    "Logical column count of the tile: 1 for a regular tile, the column count for "
    "a supertile.",
    default=1,
)

tile_logical_height_variable = Variable(
    "FABULOUS_TILE_LOGICAL_HEIGHT",
    int,
    "Logical row count of the tile: 1 for a regular tile, the row count for a "
    "supertile.",
    default=1,
)

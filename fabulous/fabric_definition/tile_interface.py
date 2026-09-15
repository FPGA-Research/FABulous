"""The pairs a tile's border pins form, and the chains every tile carries.

A tile border pin is half of a pair. A fabric wire leaves one tile through a
source pin and enters the neighbour through a destination pin, and inside one
tile the two are the same wire one hop apart, so `N1BEG[k]` on the north border
pairs with `N1END[k]` on the south border. The frame and clock chains pair the
same way: `FrameStrobe[j]` enters on the south border and leaves as
`FrameStrobe_O[j]` on the north, `FrameData[i]` enters on the west and leaves
as `FrameData_O[i]` on the east, and `UserCLK` enters on the south and leaves
as `UserCLKo`. Keeping the two members of a pair at the same rank on their two
borders is what keeps a tile's north border aligned with its own south border,
and therefore with the tile above it, so the pair is the unit any border
layout works in.

The vocabulary lives here rather than on `Tile`, since the GDS flow reads and
writes pairs with no tile to hand; a tile's own are `Tile.pairs`. The chain
names are fixed here and in the HDL generators alike, until the port model
carries them as objects.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from fabulous.fabric_definition.define import Direction, Side

FRAME_DATA = "FrameData"
FRAME_DATA_OUT = "FrameData_O"
FRAME_STROBE = "FrameStrobe"
FRAME_STROBE_OUT = "FrameStrobe_O"
USER_CLK = "UserCLK"
USER_CLK_OUT = "UserCLKo"


class Axis(StrEnum):
    """The two border pairs a pin can belong to."""

    VERTICAL = "vertical"
    HORIZONTAL = "horizontal"

    @property
    def sides(self) -> tuple[Side, Side]:
        """The first and second border of a pair on this axis."""
        if self is Axis.VERTICAL:
            return Side.NORTH, Side.SOUTH
        return Side.EAST, Side.WEST


class BusKind(StrEnum):
    """What a bus pair carries, which decides how its pins are laid out."""

    ROUTING = "routing"
    FRAME_DATA = "frame_data"
    FRAME_STROBE = "frame_strobe"
    CLOCK = "clock"


@dataclass(frozen=True)
class BusPair:
    """Two buses on opposite borders that carry the same wires, bit for bit.

    `first` sits on the first border of `axis` and `second` on the other. A
    chain bus enters through `second` and leaves through `first`. A scalar pair
    has one pin per border, named exactly; any other is indexed `bus[k]`.
    """

    axis: Axis
    first: str
    second: str
    kind: BusKind = BusKind.ROUTING
    scalar: bool = False

    def on(self, side: Side) -> str | None:
        """Return the member on `side`, or None when the pair does not touch it."""
        first_side, second_side = self.axis.sides
        if side is first_side:
            return self.first
        if side is second_side:
            return self.second
        return None


@dataclass(frozen=True)
class PinPair:
    """Two pins on opposite borders that carry the same wire."""

    axis: Axis
    first: str
    second: str
    kind: BusKind = BusKind.ROUTING


FRAME_CHAIN_PAIRS = (
    BusPair(Axis.VERTICAL, USER_CLK_OUT, USER_CLK, BusKind.CLOCK, scalar=True),
    BusPair(Axis.VERTICAL, FRAME_STROBE_OUT, FRAME_STROBE, BusKind.FRAME_STROBE),
    BusPair(Axis.HORIZONTAL, FRAME_DATA_OUT, FRAME_DATA, BusKind.FRAME_DATA),
)
"""The chains every tile carries across its borders, in the order they are laid out."""

SIDE_INPUT_CONNECTIONS = (
    (Direction.NORTH, 0, -1),  # north input <- south neighbour
    (Direction.EAST, -1, 0),  # east input  <- west neighbour
    (Direction.SOUTH, 0, 1),  # south input <- north neighbour
    (Direction.WEST, 1, 0),  # west input  <- east neighbour
)
"""Where a tile's inputs of each wire direction come from, as a grid offset.

A tile's INPUT ports along one direction are the far ends of the neighbour's
OUTPUT ports along that same direction, paired off in declaration order, so
this table is what says which pin of one tile meets which pin of the next.
The correspondence is not a name rule: a wire that lands mid-span leaves
`E2BEG` on one tile and arrives as `E2MID` on the other. Offsets are on the
bottom-left origin grid, where `dy` grows north.
"""

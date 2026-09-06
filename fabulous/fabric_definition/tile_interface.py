"""Border pins of a tile as pairs.

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

The chain names are fixed here and in the HDL generators alike, until the port
model carries them as objects; `TileInterface` is the one place the GDS flow
reads them from.
"""

from dataclasses import dataclass
from enum import StrEnum
from typing import TYPE_CHECKING

from fabulous.fabric_definition.define import IO, Side
from fabulous.fabric_definition.port import NULL_PORT_NAME

if TYPE_CHECKING:
    from fabulous.fabric_definition.tile import Tile

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


class TileInterface:
    """The border pairs of a tile, routing pairs first, then the chains.

    Every wire row of the tile CSV yields a source port on the row's side and a
    destination port on the opposite side with the same width, so each row is
    one bus pair. Rows whose source or destination is NULL have only one border
    and form no pair.

    Parameters
    ----------
    tile : Tile
        The tile whose ports the pairs are read from.
    """

    def __init__(self, tile: "Tile") -> None:
        self._tile = tile

    @property
    def routing_pairs(self) -> list[BusPair]:
        """The pairs the tile's wires form, in port order."""
        pairs: list[BusPair] = []
        for port in self._tile.portsInfo:
            if port.io_direction is not IO.OUTPUT or port.side_of_tile is Side.ANY:
                continue
            if NULL_PORT_NAME in (port.source_name, port.destination_name):
                continue
            match port.side_of_tile:
                case Side.NORTH:
                    pairs.append(
                        BusPair(Axis.VERTICAL, port.source_name, port.destination_name)
                    )
                case Side.SOUTH:
                    pairs.append(
                        BusPair(Axis.VERTICAL, port.destination_name, port.source_name)
                    )
                case Side.EAST:
                    pairs.append(
                        BusPair(
                            Axis.HORIZONTAL, port.source_name, port.destination_name
                        )
                    )
                case Side.WEST:
                    pairs.append(
                        BusPair(
                            Axis.HORIZONTAL, port.destination_name, port.source_name
                        )
                    )
        return pairs

    @property
    def pairs(self) -> list[BusPair]:
        """Every pair of the tile, the routing pairs first, then the chains."""
        return self.routing_pairs + list(FRAME_CHAIN_PAIRS)

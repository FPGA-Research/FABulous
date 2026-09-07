"""How a tile meets its neighbours, read on either of its two axes.

A pin carries both a border and a wire direction, and the parser derives the
first from the second: the output end of a wire row sits on the border its wire
travels towards and the input end on the opposite border, so `ports_on` and
`ports_along` read the same ports two ways. They are not interchangeable. A
border belongs to one tile and is what a layout works in, since a placer fits
pins along one edge. A direction belongs to the wire and is what joins two
tiles, since a tile's inputs of one direction meet its neighbour's outputs of
that same direction on the facing border.
"""

from typing import TYPE_CHECKING

from fabulous.fabric_definition.define import IO, Direction, Side

if TYPE_CHECKING:
    from fabulous.fabric_definition.port import TilePort
    from fabulous.fabric_definition.tile import Tile


class TileInterface:
    """The border pins of a tile, and the only place they are read from.

    Parameters
    ----------
    tile : Tile
        The tile whose ports are read.
    """

    def __init__(self, tile: "Tile") -> None:
        self._tile = tile

    def ports_on(self, side: Side, io: IO | None = None) -> list["TilePort"]:
        """Return the pins the tile presents on one border.

        Parameters
        ----------
        side : Side
            The border. `Side.ANY` holds the pins of no border, the jumps.
        io : IO | None
            Keep only inputs or only outputs. Defaults to both.

        Returns
        -------
        list["TilePort"]
            The ports in the order the tile declares them, NULL names dropped.
        """
        return [
            port
            for port in self._tile.portsInfo
            if port.side_of_tile is side
            and not port.name_is_null
            and (io is None or port.io_direction is io)
        ]

    def ports_along(
        self, direction: Direction, io: IO | None = None
    ) -> list["TilePort"]:
        """Return the pins of the wires that travel one way.

        The two ends of a wire sit on opposite borders, so this is the accessor
        a fabric stitch works in: the tile's inputs of a direction meet the
        outputs of the same direction on the neighbour that direction points
        away from.

        Parameters
        ----------
        direction : Direction
            The direction the wires travel. JUMP and SJUMP stay inside the tile.
        io : IO | None
            Keep only inputs or only outputs. Defaults to both.

        Returns
        -------
        list["TilePort"]
            The ports in the order the tile declares them, NULL names dropped.
        """
        return [
            port
            for port in self._tile.portsInfo
            if port.wire_direction is direction
            and not port.name_is_null
            and (io is None or port.io_direction is io)
        ]

    def pin_count(self, side: Side) -> int:
        """Count the physical pins on a border, buses expanded.

        Parameters
        ----------
        side : Side
            The border to count.

        Returns
        -------
        int
            The pins the placer has to fit along that border.
        """
        total = 0
        for port in self._tile.portsInfo:
            if port.side_of_tile is not side or port.name_is_null:
                continue
            inputs, outputs = port.expand_port_info("all")
            if port.name == port.source_name:
                total += len(inputs)
            elif port.name == port.destination_name:
                total += len(outputs)
        return total

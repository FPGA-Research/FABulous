"""Supertile definition for FPGA fabric.

This module contains the `SuperTile` class, which represents a composite tile made
up of multiple smaller, individual tiles. Supertiles allow for the creation of more
larger, complex and hierarchical structures within the FPGA fabric, combining different
functionalities into a single, reusable block.
"""

from collections.abc import Generator
from dataclasses import dataclass, field
from decimal import Decimal
from pathlib import Path

from FABulous.fabric_definition.Bel import Bel
from FABulous.fabric_definition.define import Side
from FABulous.fabric_definition.Port import Port
from FABulous.fabric_definition.Tile import Tile


@dataclass
class SuperTile:
    """Store the information about a super tile.

    Attributes
    ----------
    name : str
        The name of the super tile.
    tileDir : Path
        Path to the tile directory.
    tiles : list[Tile]
        The list of tiles that make up the super tile.
    tileMap : list[list[Tile]]
        The map of the tiles that make up the super tile
    bels : list[Bel]
        The list of bels of that the super tile contains
    withUserCLK : bool
        Whether the super tile has a userCLK port. Default is False.
    """

    name: str
    tileDir: Path
    tiles: list[Tile]
    tileMap: list[list[Tile]]
    bels: list[Bel] = field(default_factory=list)
    withUserCLK: bool = False

    def getPortsAroundTile(self) -> dict[str, list[list[Port]]]:
        """Return all the ports that are around the supertile.

        The dictionary key is the location of where the tile is located in the
        supertile map with the format of "X{x}Y{y}",
        where x is the x coordinate of the tile and y is the y coordinate of the tile.
        The top left tile will have key "00".

        Returns
        -------
        dict[str, list[list[Port]]]
            The dictionary of the ports around the super tile.
        """
        ports = {}
        for y, row in enumerate(self.tileMap):
            for x, tile in enumerate(row):
                if self.tileMap[y][x] is None:
                    continue
                ports[f"{x},{y}"] = []
                if y - 1 < 0 or self.tileMap[y - 1][x] is None:
                    ports[f"{x},{y}"].append(tile.getNorthSidePorts())
                if x + 1 >= len(self.tileMap[y]) or self.tileMap[y][x + 1] is None:
                    ports[f"{x},{y}"].append(tile.getEastSidePorts())
                if y + 1 >= len(self.tileMap) or self.tileMap[y + 1][x] is None:
                    ports[f"{x},{y}"].append(tile.getSouthSidePorts())
                if x - 1 < 0 or self.tileMap[y][x - 1] is None:
                    ports[f"{x},{y}"].append(tile.getWestSidePorts())
        return ports

    def __iter__(self) -> Generator[tuple[tuple[int, int], Tile], None, None]:
        """Iterate over all sub-tiles in the supertile."""
        for x, row in enumerate(self.tileMap):
            for y, tile in enumerate(row):
                if tile is not None:
                    yield (x, y), tile

    def getInternalConnections(self) -> list[tuple[list[Port], int, int]]:
        """Return all the internal connections of the supertile.

        Returns
        -------
        list[tuple[list[Port], int, int]]
            A list of tuples which contains the internal connected port
            and the x and y coordinate of the tile.
        """
        internalConnections = []
        for y, row in enumerate(self.tileMap):
            for x, tile in enumerate(row):
                if (
                    0 <= y - 1 < len(self.tileMap)
                    and self.tileMap[y - 1][x] is not None
                ):
                    internalConnections.append((tile.getNorthSidePorts(), x, y))
                if (
                    0 <= x + 1 < len(self.tileMap[0])
                    and self.tileMap[y][x + 1] is not None
                ):
                    internalConnections.append((tile.getEastSidePorts(), x, y))
                if (
                    0 <= y + 1 < len(self.tileMap)
                    and self.tileMap[y + 1][x] is not None
                ):
                    internalConnections.append((tile.getSouthSidePorts(), x, y))
                if (
                    0 <= x - 1 < len(self.tileMap[0])
                    and self.tileMap[y][x - 1] is not None
                ):
                    internalConnections.append((tile.getWestSidePorts(), x, y))
        return internalConnections

    @property
    def max_width(self) -> int:
        """Return the maximum width of the supertile."""
        return max(len(i) for i in self.tileMap)

    @property
    def max_height(self) -> int:
        """Return the maximum height of the supertile."""
        return len(self.tileMap)

    def get_min_die_area(
        self,
        x_pitch: Decimal,
        y_pitch: Decimal,
        x_pin_thickness_mult: Decimal,
        y_pin_thickness_mult: Decimal,
        x_spacing: Decimal,
        y_spacing: Decimal,
    ) -> tuple[Decimal, Decimal]:
        """Calculate minimum SuperTile dimensions based on IO pin density.

        For this supertile, aggregates IO pins from all constituent tiles
        that appear on the outer edges and calculates the minimum physical
        width and height required.

        Parameters
        ----------
        x_pitch : Decimal
            Horizontal pitch between tracks (DBU).
        y_pitch : Decimal
            Vertical pitch between tracks (DBU).
        x_pin_thickness_mult : Decimal
            Pin thickness multiplier in the horizontal direction.
        y_pin_thickness_mult : Decimal
            Pin thickness multiplier in the vertical direction.
        x_spacing : Decimal
            Pin spacing in the horizontal direction (DBU).
        y_spacing : Decimal
            Pin spacing in the vertical direction (DBU).

        Returns
        -------
        tuple[Decimal, Decimal]
            (min_width, min_height) where:
            - min_width: minimum width needed for north/south edge IO pins
            - min_height: minimum height needed for west/east edge IO pins

        Notes
        -----
        For supertiles, we aggregate IO pins from all constituent tiles
        that appear on the outer edges of the supertile to get conservative
        estimates for minimum dimensions.
        """
        max_north = 0
        max_south = 0
        max_west = 0
        max_east = 0

        for subtile in self.tiles:
            north_ports = subtile.get_port_count(Side.NORTH)
            south_ports = subtile.get_port_count(Side.SOUTH)
            west_ports = subtile.get_port_count(Side.WEST)
            east_ports = subtile.get_port_count(Side.EAST)

            max_north = max(max_north, north_ports)
            max_south = max(max_south, south_ports)
            max_west = max(max_west, west_ports)
            max_east = max(max_east, east_ports)

        min_width_io = Decimal(max(max_north, max_south)) * (
            x_pitch * x_pin_thickness_mult + x_spacing
        )
        min_height_io = Decimal(max(max_west, max_east)) * (
            y_pitch * y_pin_thickness_mult + y_spacing
        )

        return min_width_io, min_height_io

"""Supertile definition for FPGA fabric.

This module contains the `SuperTile` class, which represents a composite tile made
up of multiple smaller, individual tiles. Supertiles allow for the creation of more
larger, complex and hierarchical structures within the FPGA fabric, combining different
functionalities into a single, reusable block.
"""

from dataclasses import dataclass, field

from FABulous.fabric_definition.Bel import Bel
from FABulous.fabric_definition.Port import Port
from FABulous.fabric_definition.Tile import Tile


@dataclass
class SuperTile:
    """Store the information about a super tile.

    Attributes
    ----------
    name : str
        The name of the super tile
    tiles : list[Tile]
        The list of tiles that make up the super tile
    tileMap : list[list[Tile]]
        The map of the tiles that make up the super tile
    bels : list[Bel]
        The list of bels of that the super tile contains
    withUserCLK : bool
        Whether the super tile has a userCLK port. Default is False.
    """

    name: str
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

    def getExternalTileIONames(self) -> tuple[dict, list[bool]]:
        ports = {}
        userCLK = []

        for index, tile in enumerate(self.tiles):
            ports[f"0,{index}"] = []
            for port in tile.portsInfo:
                if port.name != "NULL" and port.name != "VDD" and port.name != "GND":
                    ports[f"0,{index}"].append(port)
            index += 1
            userCLK.append(tile.withUserCLK)
        return ports, userCLK

    def maxWidth(self) -> int:
        """Return the maximum width of the supertile."""
        return max(len(i) for i in self.tileMap)

    def maxHeight(self) -> int:
        """Return the maximum height of the supertile."""
        return len(self.tileMap)

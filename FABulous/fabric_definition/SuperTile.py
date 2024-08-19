from dataclasses import dataclass, field
from FABulous.fabric_definition.Tile import Tile
from FABulous.fabric_definition.Port import Port
from FABulous.fabric_definition.Bel import Bel


@dataclass
class SuperTile:
    """This class is for storing the information about a super tile.

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
        """Return all the ports that are around the super tile.
        The dictionary key is the location of where the tile is located in the super tile map with the format of "X{x}Y{y}",
        where x is the x coordinate of the tile and y is the y coordinate of the tile.
        The top left tile will have key "00".

        Returns
        -------
        dict : [str, list[list[Port]]]
            The dictionary of the ports around the super tile.
        """
        ports = {}
        for y, row in enumerate(self.tileMap):
            for x, tile in enumerate(row):
                if self.tileMap[y][x] == None:
                    continue
                ports[f"{x},{y}"] = []
                if y - 1 < 0 or self.tileMap[y - 1][x] == None:
                    ports[f"{x},{y}"].append(tile.getNorthSidePorts())
                if x + 1 >= len(self.tileMap[y]) or self.tileMap[y][x + 1] == None:
                    ports[f"{x},{y}"].append(tile.getEastSidePorts())
                if y + 1 >= len(self.tileMap) or self.tileMap[y + 1][x] == None:
                    ports[f"{x},{y}"].append(tile.getSouthSidePorts())
                if x - 1 < 0 or self.tileMap[y][x - 1] == None:
                    ports[f"{x},{y}"].append(tile.getWestSidePorts())
        return ports

    def getInternalConnections(self) -> list[tuple[list[Port], int, int]]:
        """Return all the internal connections of the super tile.

        Returns
        -------
        list : [tuple[list[Port], int, int]]
            A list of tuples which contains the internal connected port
            and the x and y coordinate of the tile.
        """
        internalConnections = []
        for y, row in enumerate(self.tileMap):
            for x, tile in enumerate(row):
                if 0 <= y - 1 < len(self.tileMap) and self.tileMap[y - 1][x] != None:
                    internalConnections.append((tile.getNorthSidePorts(), x, y))
                if 0 <= x + 1 < len(self.tileMap[0]) and self.tileMap[y][x + 1] != None:
                    internalConnections.append((tile.getEastSidePorts(), x, y))
                if 0 <= y + 1 < len(self.tileMap) and self.tileMap[y + 1][x] != None:
                    internalConnections.append((tile.getSouthSidePorts(), x, y))
                if 0 <= x - 1 < len(self.tileMap[0]) and self.tileMap[y][x - 1] != None:
                    internalConnections.append((tile.getWestSidePorts(), x, y))
        return internalConnections

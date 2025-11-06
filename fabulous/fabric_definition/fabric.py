"""FPGA fabric definition module.

This module contains the Fabric class which represents the complete FPGA fabric
including tile layout, configuration parameters, and connectivity information. The
fabric is the top-level container for all tiles, BELs, and routing resources.
"""

from collections.abc import Generator
from dataclasses import dataclass, field

from FABulous.fabric_definition.Bel import Bel
from FABulous.fabric_definition.define import (
    ConfigBitMode,
    Direction,
    MultiplexerStyle,
    Side,
)
from FABulous.fabric_definition.SuperTile import SuperTile
from FABulous.fabric_definition.Tile import Tile
from FABulous.fabric_definition.Wire import Wire


@dataclass
class Fabric:
    """Store the configuration of a fabric.

    All the information is parsed from the CSV file.

    Attributes
    ----------
    tile : list[list[Tile]]
        The tile map of the fabric
    name : str
        The name of the fabric
    numberOfRows : int
        The number of rows of the fabric
    numberOfColumns : int
        The number of columns of the fabric
    configBitMode : ConfigBitMode
        The configuration bit mode of the fabric.
        Currently supports frame based or ff chain
    frameBitsPerRow : int
        The number of frame bits per row of the fabric
    maxFramesPerCol : int
        The maximum number of frames per column of the fabric
    package : str
        The extra package used by the fabric. Only useful for VHDL output.
    generateDelayInSwitchMatrix : int
        The amount of delay in a switch matrix.
    multiplexerStyle : MultiplexerStyle
        The style of the multiplexer used in the fabric.
        Currently supports custom or generic
    frameSelectWidth : int
        The width of the frame select signal.
    rowSelectWidth : int
        The width of the row select signal.
    desync_flag : int
        The flag indicating desynchronization status,
        used to manage timing issues within the fabric.
    numberOfBRAMs : int
        The number of BRAMs in the fabric.
    superTileEnable : bool
        Whether the fabric has super tile.
    tileDic : dict[str, Tile]
        A dictionary of tiles used in the fabric. The key is the name of the tile and
        the value is the tile.
    superTileDic : dict[str, SuperTile]
        A dictionary of super tiles used in the fabric. The key is the name of the
        supertile and the value is the supertile.
    unusedTileDic: dict[str, Tile]
        A dictionary of tiles that are not used in the fabric,
        but defined in the fabric.csv.
        The key is the name of the tile and the value is the tile.
    unusedSuperTileDic : dict[str, SuperTile]
        A dictionary of super tiles that are not used in the fabric,
        but defined in the fabric.csv.
        The key is the name of the tile and the value is the tile.
    commonWirePair : list[tuple[str, str]]
        A list of common wire pairs in the fabric.
    """

    tile: list[list[Tile]] = field(default_factory=list)

    name: str = "eFPGA"
    numberOfRows: int = 15
    numberOfColumns: int = 15
    configBitMode: ConfigBitMode = ConfigBitMode.FRAME_BASED
    frameBitsPerRow: int = 32
    maxFramesPerCol: int = 20
    package: str = "use work.my_package.all"
    generateDelayInSwitchMatrix: int = 80
    multiplexerStyle: MultiplexerStyle = MultiplexerStyle.CUSTOM
    frameSelectWidth: int = 5
    rowSelectWidth: int = 5
    desync_flag: int = 20
    numberOfBRAMs: int = 10
    superTileEnable: bool = True

    tileDic: dict[str, Tile] = field(default_factory=dict)
    superTileDic: dict[str, SuperTile] = field(default_factory=dict)
    unusedTileDic: dict[str, Tile] = field(default_factory=dict)
    unusedSuperTileDic: dict[str, SuperTile] = field(default_factory=dict)
    commonWirePair: list[tuple[str, str]] = field(default_factory=list)

    def __post_init__(self) -> None:
        """Generate and get all the wire pairs in the fabric.

        The wire pair are used during model generation when some of the signals have
        source or destination of "NULL".

        The wires are used during model generation to work with wire that going cross
        tile.
        """
        for row in self.tile:
            for tile in row:
                if tile is None:
                    continue
                for port in tile.portsInfo:
                    self.commonWirePair.append((port.sourceName, port.destinationName))

        self.commonWirePair = list(dict.fromkeys(self.commonWirePair))
        self.commonWirePair = [
            (i, j) for i, j in self.commonWirePair if i != "NULL" and j != "NULL"
        ]

        for y, row in enumerate(self.tile):
            for x, tile in enumerate(row):
                if tile is None:
                    continue
                for port in tile.portsInfo:
                    if (
                        abs(port.xOffset) <= 1
                        and abs(port.yOffset) <= 1
                        and port.sourceName != "NULL"
                        and port.destinationName != "NULL"
                    ):
                        for i in range(port.wireCount):
                            tile.wireList.append(
                                Wire(
                                    direction=port.wireDirection,
                                    source=f"{port.sourceName}{i}",
                                    xOffset=port.xOffset,
                                    yOffset=port.yOffset,
                                    destination=f"{port.destinationName}{i}",
                                    sourceTile="",
                                    destinationTile="",
                                )
                            )
                    elif port.sourceName != "NULL" and port.destinationName != "NULL":
                        # clamp the xOffset to 1 or -1
                        value = min(max(port.xOffset, -1), 1)
                        cascadedI = 0
                        for i in range(port.wireCount * abs(port.xOffset)):
                            if i < port.wireCount:
                                cascadedI = i + port.wireCount * (abs(port.xOffset) - 1)
                            else:
                                cascadedI = i - port.wireCount
                                tile.wireList.append(
                                    Wire(
                                        direction=Direction.JUMP,
                                        source=f"{port.destinationName}{i}",
                                        xOffset=0,
                                        yOffset=0,
                                        destination=f"{port.sourceName}{i}",
                                        sourceTile=f"X{x}Y{y}",
                                        destinationTile=f"X{x}Y{y}",
                                    )
                                )
                            tile.wireList.append(
                                Wire(
                                    direction=port.wireDirection,
                                    source=f"{port.sourceName}{i}",
                                    xOffset=value,
                                    yOffset=port.yOffset,
                                    destination=f"{port.destinationName}{cascadedI}",
                                    sourceTile=f"X{x}Y{y}",
                                    destinationTile=f"X{x + value}Y{y + port.yOffset}",
                                )
                            )

                        # clamp the yOffset to 1 or -1
                        value = min(max(port.yOffset, -1), 1)
                        cascadedI = 0
                        for i in range(port.wireCount * abs(port.yOffset)):
                            if i < port.wireCount:
                                cascadedI = i + port.wireCount * (abs(port.yOffset) - 1)
                            else:
                                cascadedI = i - port.wireCount
                                tile.wireList.append(
                                    Wire(
                                        direction=Direction.JUMP,
                                        source=f"{port.destinationName}{i}",
                                        xOffset=0,
                                        yOffset=0,
                                        destination=f"{port.sourceName}{i}",
                                        sourceTile=f"X{x}Y{y}",
                                        destinationTile=f"X{x}Y{y}",
                                    )
                                )
                            tile.wireList.append(
                                Wire(
                                    direction=port.wireDirection,
                                    source=f"{port.sourceName}{i}",
                                    xOffset=port.xOffset,
                                    yOffset=value,
                                    destination=f"{port.destinationName}{cascadedI}",
                                    sourceTile=f"X{x}Y{y}",
                                    destinationTile=f"X{x + port.xOffset}Y{y + value}",
                                )
                            )
                    elif port.sourceName != "NULL" and port.destinationName == "NULL":
                        sourceName = port.sourceName
                        destName = port.sourceName
                        # if sourcename is not in a common pair wire we assume
                        # the source name is the same as destination name
                        wire_pair = dict(self.commonWirePair)
                        if sourceName in wire_pair:
                            destName = wire_pair[sourceName]

                        value = min(max(port.xOffset, -1), 1)
                        for i in range(port.wireCount * abs(port.xOffset)):
                            tile.wireList.append(
                                Wire(
                                    direction=port.wireDirection,
                                    source=f"{sourceName}{i}",
                                    xOffset=value,
                                    yOffset=port.yOffset,
                                    destination=f"{destName}{i}",
                                    sourceTile=f"X{x}Y{y}",
                                    destinationTile=f"X{x + value}Y{y + port.yOffset}",
                                )
                            )

                        value = min(max(port.yOffset, -1), 1)
                        for i in range(port.wireCount * abs(port.yOffset)):
                            tile.wireList.append(
                                Wire(
                                    direction=port.wireDirection,
                                    source=f"{sourceName}{i}",
                                    xOffset=port.xOffset,
                                    yOffset=value,
                                    destination=f"{destName}{i}",
                                    sourceTile=f"X{x}Y{y}",
                                    destinationTile=f"X{x + port.xOffset}Y{y + value}",
                                )
                            )
                tile.wireList = list(dict.fromkeys(tile.wireList))

    def __repr__(self) -> str:
        """Return the string representation of the fabric.

        Returns
        -------
        str
            A formatted string showing the fabric layout and key parameters.
        """
        fabric = ""
        for i in range(self.numberOfRows):
            for j in range(self.numberOfColumns):
                if self.tile[i][j] is None:
                    fabric += "Null".ljust(15) + "\t"
                else:
                    fabric += f"{str(self.tile[i][j].name).ljust(15)}\t"
            fabric += "\n"

        fabric += "\n"
        fabric += f"numberOfColumns: {self.numberOfColumns}\n"
        fabric += f"numberOfRows: {self.numberOfRows}\n"
        fabric += f"configBitMode: {self.configBitMode}\n"
        fabric += f"frameBitsPerRow: {self.frameBitsPerRow}\n"
        fabric += f"maxFramesPerCol: {self.maxFramesPerCol}\n"
        fabric += f"package: {self.package}\n"
        fabric += f"generateDelayInSwitchMatrix: {self.generateDelayInSwitchMatrix}\n"
        fabric += f"multiplexerStyle: {self.multiplexerStyle}\n"
        fabric += f"superTileEnable: {self.superTileEnable}\n"
        fabric += f"tileDic: {list(self.tileDic.keys())}\n"
        return fabric

    def __iter__(self) -> Generator[tuple[tuple[int, int], Tile | None]]:
        """Iterate over all tiles in the fabric in row-major order.

        Yields
        ------
        Generator[tuple[tuple[int, int], Tile | None]]
            Generator yielding a tuple where the first element is the (x, y)
            coordinates and the second is the Tile at that position or None
            if the position is empty.
        """
        for y, row in enumerate(self.tile):
            for x, tile in enumerate(row):
                yield (x, y), tile

    def getTileByName(self, name: str) -> Tile | SuperTile:
        """Get a tile by its name from the fabric.

        Search for the tile first in the used tiles dictionary, then in the unused tiles
        dictionary then in the supertiles if not found.

        Parameters
        ----------
        name : str
            The name of the tile to retrieve.

        Returns
        -------
        Tile | SuperTile
            The tile or supertile object if found.

        Raises
        ------
        KeyError
            If the tile name is not found in either used or unused tiles.
        """
        ret = self.tileDic.get(name)
        if ret is None:
            ret = self.unusedTileDic.get(name)
        if ret is None:
            ret = self.getSuperTileByName(name)  # Check if it's a supertile
        if ret is None:
            raise KeyError(f"Tile {name} not found in fabric.")
        return ret

    def getSuperTileByName(self, name: str) -> SuperTile:
        """Get a supertile by its name from the fabric.

        Searches for the supertile first in the used supertiles dictionary, then in the
        unused supertiles dictionary if not found.

        Parameters
        ----------
        name : str
            The name of the supertile to retrieve.

        Returns
        -------
        SuperTile
            The super tile object if found.

        Raises
        ------
        KeyError
            If the super tile name is not found in either used or unused super tiles.
        """
        ret = self.superTileDic.get(name)
        if ret is None:
            ret = self.unusedSuperTileDic.get(name)
        if ret is None:
            raise KeyError(f"SuperTile {name} not found in fabric.")

        return ret

    def getAllUniqueBels(self) -> list[Bel]:
        """Get all unique BELs from all tiles in the fabric.

        Returns
        -------
        list[Bel]
            A list of all unique BELs across all tiles.
        """
        bels = list()
        for tile in self.tileDic.values():
            bels.extend(tile.bels)
        return bels

    def getBelsByTileXY(self, x: int, y: int) -> list[Bel]:
        """Get all the Bels of a tile.

        Parameters
        ----------
        x : int
            The x coordinate of / column the tile.
        y : int
            The y coordinate / row of the tile.

        Returns
        -------
        list[Bel]
            A list of Bels in the tile.

        Raises
        ------
        ValueError
            Tile coordinates are out of range.
        """
        if x < 0 or x >= self.numberOfColumns or y < 0 or y >= self.numberOfRows:
            raise ValueError(
                f"Invalid tile coordinates: ({x},{y}) max (0,0) - ({self.numberOfRows},"
                f"{self.numberOfColumns})"
            )
        if self.tile[y][x] is None:
            return []

        return self.tile[y][x].bels

    def find_tile_positions(
        self, tile: Tile | SuperTile
    ) -> list[tuple[int, int]] | None:
        """Find all positions where a tile or supertile appears in the fabric grid.

        Parameters
        ----------
        tile : Tile | SuperTile
            The tile or supertile to search for

        Returns
        -------
        list[tuple[int, int]] | None
            List of (x, y) positions where the tile/supertile appears,
            or None if not found
        """
        positions = []
        if isinstance(tile, SuperTile):
            # For SuperTiles, find where they appear
            for y, row in enumerate(self.tile):
                for x, fabric_tile in enumerate(row):
                    if fabric_tile is None:
                        continue
                    # Check if this fabric tile belongs to the supertile
                    for st in self.superTileDic.values():
                        if st == tile:
                            # Check if fabric_tile is part of this supertile
                            for st_row in st.tileMap:
                                for st_tile in st_row:
                                    if st_tile and st_tile.name == fabric_tile.name:
                                        positions.append((x, y))
        else:
            # For regular Tiles, find where they appear
            for y, row in enumerate(self.tile):
                for x, fabric_tile in enumerate(row):
                    if fabric_tile and fabric_tile.name == tile.name:
                        positions.append((x, y))

        return positions if positions else None

    def determine_border_side(self, x: int, y: int) -> Side | None:
        """Determine which border side a tile position is on, if any.

        Parameters
        ----------
        x : int
            X coordinate in the fabric grid
        y : int
            Y coordinate in the fabric grid

        Returns
        -------
        Side | None
            The border side (NORTH, SOUTH, EAST, or WEST) if the position is on
            a border, None otherwise. If on a corner, returns the vertical side
            (NORTH or SOUTH) as priority.
        """
        is_north = y == 0
        is_south = y == self.numberOfRows - 1
        is_east = x == self.numberOfColumns - 1
        is_west = x == 0

        # Priority: corners get vertical sides (NORTH/SOUTH)
        if is_north:
            return Side.NORTH
        if is_south:
            return Side.SOUTH
        if is_east:
            return Side.EAST
        if is_west:
            return Side.WEST

        return None

    def get_unique_tile_types(self) -> list[Tile]:
        """Get list of unique tile types used in the fabric.

        Returns
        -------
        list[Tile]
            List of unique tile types (one instance per type name)
        """
        unique_tiles: dict[str, Tile] = {}

        for row in self.tile:
            for tile in row:
                if tile is not None and tile.name not in unique_tiles:
                    unique_tiles[tile.name] = tile

        return list(unique_tiles.values())

    def get_tile_row_column_indices(self, tile_name: str) -> tuple[set[int], set[int]]:
        """Get all row and column indices where a tile type appears.

        Parameters
        ----------
        tile_name : str
            Name of the tile type to search for

        Returns
        -------
        tuple[set[int], set[int]]
            (row_indices, column_indices) where the tile type appears
        """
        rows: set[int] = set()
        cols: set[int] = set()

        for row_idx, row in enumerate(self.tile):
            for col_idx, tile in enumerate(row):
                if tile is not None and tile.name == tile_name:
                    rows.add(row_idx)
                    cols.add(col_idx)

        return rows, cols

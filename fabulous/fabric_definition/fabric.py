"""FPGA fabric definition module.

This module contains the Fabric class which represents the complete FPGA fabric
including tile layout, configuration parameters, and connectivity information. The
fabric is the top-level container for all tiles, BELs, and routing resources.
"""

from collections.abc import Generator
from dataclasses import dataclass, field
from pathlib import Path

from fabulous.fabric_definition.bel import Bel
from fabulous.fabric_definition.define import (
    IO,
    ConfigBitMode,
    Direction,
    MultiplexerStyle,
    Side,
)
from fabulous.fabric_definition.supertile import SuperTile
from fabulous.fabric_definition.tile import Tile
from fabulous.fabric_definition.wire import Wire


@dataclass
class Fabric:
    """Store the configuration of a fabric.

    All the information is parsed from the CSV file.

    Attributes
    ----------
    fabric_dir : Path
        The path to the fabric config file
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
    disableUserCLK : bool
        Whether to disable UserCLK generation in the fabric.
    syncHeaderHex : str
        Hex string of the 20-byte sync header written at the start of every
        binary bitstream.
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

    fabric_dir: Path
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
    disableUserCLK: bool = False
    syncHeaderHex: str = "00AAFF01000000010000000000000000FAB0FAB1"

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
        if self.numberOfRows > 32:
            raise ValueError(
                "Due to bitstream limitations, "
                "numberOfRows must be less than or equal to 32."
            )

        if self.numberOfColumns > 32:
            raise ValueError(
                "Due to bitstream limitations, "
                "numberOfColumns must be less than or equal to 32."
            )

        if self.frameBitsPerRow != 32:
            raise ValueError(
                "Due to bitstream limitations, frameBitsPerRow must be 32."
            )

        if self.maxFramesPerCol != 20:
            raise ValueError(
                "Due to bitstream limitations, maxFramesPerCol must be 20."
            )

        if self.frameSelectWidth != 5:
            raise ValueError(
                "Due to bitstream limitations, frameSelectWidth must be 5."
            )

        if self.rowSelectWidth != 5:
            raise ValueError("Due to bitstream limitations, rowSelectWidth must be 5.")

        if self.desync_flag != 20:
            raise ValueError("Due to bitstream limitations, desync_flag must be 20.")

        for tile in self.tileDic.values():
            if len(tile.bels) > 26:
                raise ValueError(
                    "Due to naming limitations, "
                    f"tile {tile.name} cannot have more than 26 BELs."
                )

        # A supertile's BELs are emitted at its master tile, sharing the BEL
        # letter space (A, B, ...) with the master tile's own BELs, so the two
        # together must fit in 26 letters.
        for superTile in self.superTileDic.values():
            mx, my = superTile.get_master_tile_coords()
            master_tile = superTile.tileMap[my][mx]
            if (
                master_tile is not None
                and len(master_tile.bels) + len(superTile.bels) > 26
            ):
                raise ValueError(
                    "Due to naming limitations, supertile "
                    f"{superTile.name} and its master tile {master_tile.name} "
                    "together cannot have more than 26 BELs."
                )

        # SJUMP wires route a basic tile to a BEL hosted in its supertile's
        # master tile; they are only meaningful inside a supertile. A tile that
        # belongs to a supertile carries partOfSuperTile (set by the parser), so
        # reject any SJUMP-declaring tile that is not flagged as such.
        for row in self.tile:
            for tile in row:
                if tile is None:
                    continue
                if tile.get_sjump_ports() and not tile.partOfSuperTile:
                    raise ValueError(
                        f"Tile '{tile.name}' declares SJUMP wires but is not part "
                        "of any supertile. SJUMP wires route to a supertile-hosted "
                        "BEL and are only valid inside a supertile's tiles."
                    )

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

        # SJUMP wire pass: for every supertile placement, add SJUMP wires from the
        # child tiles to the master tile (forward) and back (reverse).
        touched: set[tuple[int, int]] = set()
        for base_fx, base_fy, superTile in self.iter_super_tile_placements():
            tx_local, ty_local = superTile.get_master_tile_coords()
            ftx = base_fx + tx_local
            fty = base_fy + ty_local
            master_tile = self.tile[fty][ftx]
            if master_tile is None:
                continue

            for ly, st_row in enumerate(superTile.tileMap):
                for lx, st_tile in enumerate(st_row):
                    if st_tile is None:
                        continue
                    fy = base_fy + ly
                    fx = base_fx + lx
                    grid_tile = self.tile[fy][fx]

                    for p in grid_tile.get_sjump_ports():
                        if p.inOut != IO.OUTPUT:
                            continue
                        for i in range(p.wireCount):
                            grid_tile.wireList.append(
                                Wire(
                                    direction=Direction.SJUMP,
                                    source=f"{p.name}{i}",
                                    xOffset=ftx - fx,
                                    yOffset=fty - fy,
                                    destination=f"{st_tile.name}_{p.name}{i}",
                                    sourceTile=f"X{fx}Y{fy}",
                                    destinationTile=f"X{ftx}Y{fty}",
                                )
                            )

                    # Reverse: supertile SM output ({child_name}_{port}) back down to
                    # the child tile's INPUT port. The source lives in the wrapper at
                    # the master tile, so the wire is owned by the master.
                    for p in grid_tile.get_sjump_ports():
                        if p.inOut != IO.INPUT:
                            continue
                        for i in range(p.wireCount):
                            master_tile.wireList.append(
                                Wire(
                                    direction=Direction.SJUMP,
                                    source=f"{st_tile.name}_{p.name}{i}",
                                    xOffset=fx - ftx,
                                    yOffset=fy - fty,
                                    destination=f"{p.name}{i}",
                                    sourceTile=f"X{ftx}Y{fty}",
                                    destinationTile=f"X{fx}Y{fy}",
                                )
                            )
                    touched.add((fx, fy))
                    touched.add((ftx, fty))

        for fx, fy in touched:
            tile = self.tile[fy][fx]
            tile.wireList = list(dict.fromkeys(tile.wireList))

    def iter_super_tile_placements(
        self, superTile: SuperTile | None = None
    ) -> Generator[tuple[int, int, SuperTile], None, None]:
        """Yield `(base_fx, base_fy, superTile)` for every supertile placement.

        Each supertile type's `tileMap` pattern is matched against the fabric
        grid; `(base_fx, base_fy)` is the top-left corner of a match. Shared by
        the SJUMP wire pass, the nextpnr model, and the bitstream spec so they all
        locate supertile instances identically.

        Parameters
        ----------
        superTile : SuperTile | None, optional
            If given, only placements of this supertile are yielded; otherwise
            every supertile type in the fabric is scanned.

        Yields
        ------
        tuple[int, int, SuperTile]
            The placement's top-left grid coordinates and the supertile there.
        """
        candidates = (
            [superTile] if superTile is not None else list(self.superTileDic.values())
        )
        for st in candidates:
            for base_fy in range(len(self.tile) - st.max_height + 1):
                for base_fx in range(len(self.tile[base_fy]) - st.max_width + 1):
                    if self._matches_super_tile(st, base_fx, base_fy):
                        yield base_fx, base_fy, st

    def _matches_super_tile(
        self, superTile: SuperTile, base_fx: int, base_fy: int
    ) -> bool:
        """Return whether `superTile`'s tileMap matches the grid at the base."""
        for ly, st_row in enumerate(superTile.tileMap):
            for lx, st_tile in enumerate(st_row):
                fy = base_fy + ly
                fx = base_fx + lx
                grid_tile = self.tile[fy][fx]
                if st_tile is None:
                    if grid_tile is not None:
                        return False
                elif grid_tile is None or grid_tile.name != st_tile.name:
                    return False
        return True

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
        fabric += f"disableUserCLK: {self.disableUserCLK}\n"
        fabric += f"tileDic: {list(self.tileDic.keys())}\n"
        return fabric

    def __iter__(self) -> Generator[tuple[tuple[int, int], Tile | None]]:
        """Iterate over all tiles in the fabric in row-major order.

        Yields
        ------
        tuple[tuple[int, int], Tile | None]
            A tuple where the first element is the (x, y) coordinates and the
            second is the Tile at that position or None if the position is
            empty.
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
        """Get all unique BELs from all tiles and supertiles in the fabric.

        Returns
        -------
        list[Bel]
            A list of all unique BELs across all tiles and supertiles.
        """
        bels = list()
        for tile in self.tileDic.values():
            bels.extend(tile.bels)
        for superTile in self.superTileDic.values():
            bels.extend(superTile.bels)
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

        return positions or None

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

    def get_all_unique_tiles(self) -> list[Tile | SuperTile]:
        """Get list of unique tile types used in the fabric.

        Returns
        -------
        list[Tile | SuperTile]
            List of unique tile types (one instance per type name)
        """
        result: list[Tile | SuperTile] = []

        # Add all regular tiles from tileDic
        result.extend([i for i in self.tileDic.values() if not i.partOfSuperTile])

        # Add all SuperTiles from superTileDic
        result.extend(self.superTileDic.values())

        return result

    def get_super_tile_containing(self, tile_name: str) -> SuperTile | None:
        """Return the SuperTile that contains the named tile, if any.

        Parameters
        ----------
        tile_name : str
            Name of the (sub-)tile to look up.

        Returns
        -------
        SuperTile | None
            The SuperTile whose constituent tiles include ``tile_name``, or None
            if the tile is not part of any SuperTile.
        """
        for super_tile in self.superTileDic.values():
            if any(tile.name == tile_name for tile in super_tile.tiles):
                return super_tile
        return None

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

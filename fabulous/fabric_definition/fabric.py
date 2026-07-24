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
    ConfigBitMode,
    Direction,
    MultiplexerStyle,
    Side,
)
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
    multiClkDomains : bool
        Whether the fabric uses multiple clock domains. When True, CLK features
        are kept in the bitstream instead of being filtered out.
    syncHeaderHex : str
        Hex string of the 20-byte sync header written at the start of every
        binary bitstream.
    tileDic : dict[str, Tile]
        A dictionary of tiles used in the fabric. The key is the name of the tile and
        the value is the tile. A former supertile is stored here as a composite
        ``Tile`` keyed by its name.
    unusedTileDic: dict[str, Tile]
        A dictionary of tiles (leaf or composite) that are defined in the
        fabric.csv but not used in the fabric. The key is the name of the tile and
        the value is the tile.
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
    multiClkDomains: bool = False
    syncHeaderHex: str = "00AAFF01000000010000000000000000FAB0FAB1"

    tileDic: dict[str, Tile] = field(default_factory=dict)
    unusedTileDic: dict[str, Tile] = field(default_factory=dict)
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
            if tile.is_composite:
                # A composite tile's wrapper BELs are emitted at its master
                # sub-tile, sharing the BEL letter space (A, B, ...) with the
                # master sub-tile's own BELs, so the two together must fit in
                # 26 letters.
                mx, my = tile.get_master_offset()
                master_tile = tile.tile_map[my][mx]
                if (
                    master_tile is not None
                    and len(master_tile.bels) + len(tile.bels) > 26
                ):
                    raise ValueError(
                        "Due to naming limitations, composite tile "
                        f"{tile.name} and its master sub-tile {master_tile.name} "
                        "together cannot have more than 26 BELs."
                    )
            elif len(tile.bels) > 26:
                raise ValueError(
                    "Due to naming limitations, "
                    f"tile {tile.name} cannot have more than 26 BELs."
                )

        for row in self.tile:
            for tile in row:
                if tile is None:
                    continue
                for port in tile.ports_info:
                    self.commonWirePair.append(
                        (port.source_name, port.destination_name)
                    )

        self.commonWirePair = list(dict.fromkeys(self.commonWirePair))
        self.commonWirePair = [
            (i, j) for i, j in self.commonWirePair if i != "NULL" and j != "NULL"
        ]

        for y, row in enumerate(self.tile):
            for x, tile in enumerate(row):
                if tile is None:
                    continue
                for port in tile.ports_info:
                    if (
                        abs(port.x_offset) <= 1
                        and abs(port.y_offset) <= 1
                        and port.source_name != "NULL"
                        and port.destination_name != "NULL"
                    ):
                        for i in range(port.wire_count):
                            tile.wire_list.append(
                                Wire(
                                    direction=port.wire_direction,
                                    source=f"{port.source_name}{i}",
                                    x_offset=port.x_offset,
                                    y_offset=port.y_offset,
                                    destination=f"{port.destination_name}{i}",
                                    sourceTile="",
                                    destinationTile="",
                                )
                            )
                    elif port.source_name != "NULL" and port.destination_name != "NULL":
                        # clamp the x_offset to 1 or -1
                        value = min(max(port.x_offset, -1), 1)
                        cascadedI = 0
                        for i in range(port.wire_count * abs(port.x_offset)):
                            if i < port.wire_count:
                                cascadedI = i + port.wire_count * (
                                    abs(port.x_offset) - 1
                                )
                            else:
                                cascadedI = i - port.wire_count
                                tile.wire_list.append(
                                    Wire(
                                        direction=Direction.JUMP,
                                        source=f"{port.destination_name}{i}",
                                        x_offset=0,
                                        y_offset=0,
                                        destination=f"{port.source_name}{i}",
                                        sourceTile=f"X{x}Y{y}",
                                        destinationTile=f"X{x}Y{y}",
                                    )
                                )
                            tile.wire_list.append(
                                Wire(
                                    direction=port.wire_direction,
                                    source=f"{port.source_name}{i}",
                                    x_offset=value,
                                    y_offset=port.y_offset,
                                    destination=f"{port.destination_name}{cascadedI}",
                                    sourceTile=f"X{x}Y{y}",
                                    destinationTile=f"X{x + value}Y{y + port.y_offset}",
                                )
                            )

                        # clamp the y_offset to 1 or -1
                        value = min(max(port.y_offset, -1), 1)
                        cascadedI = 0
                        for i in range(port.wire_count * abs(port.y_offset)):
                            if i < port.wire_count:
                                cascadedI = i + port.wire_count * (
                                    abs(port.y_offset) - 1
                                )
                            else:
                                cascadedI = i - port.wire_count
                                tile.wire_list.append(
                                    Wire(
                                        direction=Direction.JUMP,
                                        source=f"{port.destination_name}{i}",
                                        x_offset=0,
                                        y_offset=0,
                                        destination=f"{port.source_name}{i}",
                                        sourceTile=f"X{x}Y{y}",
                                        destinationTile=f"X{x}Y{y}",
                                    )
                                )
                            tile.wire_list.append(
                                Wire(
                                    direction=port.wire_direction,
                                    source=f"{port.source_name}{i}",
                                    x_offset=port.x_offset,
                                    y_offset=value,
                                    destination=f"{port.destination_name}{cascadedI}",
                                    sourceTile=f"X{x}Y{y}",
                                    destinationTile=f"X{x + port.x_offset}Y{y + value}",
                                )
                            )
                    elif port.source_name != "NULL" and port.destination_name == "NULL":
                        source_name = port.source_name
                        destName = port.source_name
                        # if sourcename is not in a common pair wire we assume
                        # the source name is the same as destination name
                        wire_pair = dict(self.commonWirePair)
                        if source_name in wire_pair:
                            destName = wire_pair[source_name]

                        value = min(max(port.x_offset, -1), 1)
                        for i in range(port.wire_count * abs(port.x_offset)):
                            tile.wire_list.append(
                                Wire(
                                    direction=port.wire_direction,
                                    source=f"{source_name}{i}",
                                    x_offset=value,
                                    y_offset=port.y_offset,
                                    destination=f"{destName}{i}",
                                    sourceTile=f"X{x}Y{y}",
                                    destinationTile=f"X{x + value}Y{y + port.y_offset}",
                                )
                            )

                        value = min(max(port.y_offset, -1), 1)
                        for i in range(port.wire_count * abs(port.y_offset)):
                            tile.wire_list.append(
                                Wire(
                                    direction=port.wire_direction,
                                    source=f"{source_name}{i}",
                                    x_offset=port.x_offset,
                                    y_offset=value,
                                    destination=f"{destName}{i}",
                                    sourceTile=f"X{x}Y{y}",
                                    destinationTile=f"X{x + port.x_offset}Y{y + value}",
                                )
                            )
                tile.wire_list = list(dict.fromkeys(tile.wire_list))

    def _composite_matches_grid(
        self, composite: Tile, base_fx: int, base_fy: int
    ) -> bool:
        """Return whether a composite's ``tile_map`` matches the grid at the base.

        The composite ``tile_map`` is stored top row first while the fabric grid
        ``self.tile`` is stored bottom row first, so the composite rows are walked
        from the bottom up. ``(base_fx, base_fy)`` is the bottom-left corner of the
        candidate placement in the fabric grid.

        Parameters
        ----------
        composite : Tile
            The composite tile whose ``tile_map`` pattern is matched.
        base_fx : int
            The column of the placement's bottom-left corner in the fabric grid.
        base_fy : int
            The row of the placement's bottom-left corner in the fabric grid.

        Returns
        -------
        bool
            ``True`` if every composite cell matches the corresponding grid cell.
        """
        rows = composite.tile_map
        if rows is None:
            return False
        height = len(rows)
        for ly, st_row in enumerate(rows):
            # tile_map is top-first; the bottom row (ly == height - 1) lands on
            # base_fy in the bottom-first fabric grid.
            fy = base_fy + (height - 1 - ly)
            for lx, st_tile in enumerate(st_row):
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
        fabric += f"multiClkDomains: {self.multiClkDomains}\n"
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

    def getTileByName(self, name: str) -> Tile:
        """Get a tile by its name from the fabric.

        Search for the tile first in the used tiles dictionary, then in the unused
        tiles dictionary. Composite tiles (former supertiles) live in the same
        dictionaries keyed by their name.

        Parameters
        ----------
        name : str
            The name of the tile to retrieve.

        Returns
        -------
        Tile
            The (leaf or composite) tile object if found.

        Raises
        ------
        KeyError
            If the tile name is not found in either used or unused tiles.
        """
        ret = self.tileDic.get(name)
        if ret is None:
            ret = self.unusedTileDic.get(name)
        if ret is None:
            raise KeyError(f"Tile {name} not found in fabric.")
        return ret

    def getAllUniqueBels(self) -> list[Bel]:
        """Get all unique BELs from all tiles in the fabric.

        Includes wrapper BELs of composite tiles, which are stored on the
        composite ``Tile.bels``.

        Returns
        -------
        list[Bel]
            A list of all BELs across all tiles.
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

    def find_tile_positions(self, tile: Tile) -> list[tuple[int, int]] | None:
        """Find all positions where a tile appears in the fabric grid.

        For a composite tile the ``tile_map`` pattern is matched against the grid,
        and every grid cell covered by a matching placement is reported. For a
        leaf tile every grid cell with the same name is reported.

        Parameters
        ----------
        tile : Tile
            The (leaf or composite) tile to search for.

        Returns
        -------
        list[tuple[int, int]] | None
            List of (x, y) positions where the tile appears, or None if not found.
        """
        positions = []
        if tile.is_composite:
            rows = tile.tile_map
            if rows is None:
                return None
            height = len(rows)
            for base_fy in range(len(self.tile) - height + 1):
                for base_fx in range(len(self.tile[base_fy]) - tile.max_width + 1):
                    if not self._composite_matches_grid(tile, base_fx, base_fy):
                        continue
                    # Report every covered grid cell (every non-None sub-tile).
                    for ly, st_row in enumerate(rows):
                        fy = base_fy + (height - 1 - ly)
                        for lx, st_tile in enumerate(st_row):
                            if st_tile is not None:
                                positions.append((base_fx + lx, fy))
        else:
            for y, row in enumerate(self.tile):
                for x, fabric_tile in enumerate(row):
                    if fabric_tile and fabric_tile.name == tile.name:
                        positions.append((x, y))

        return positions or None

    def find_composite_placement_origins(
        self, composite: Tile
    ) -> list[tuple[int, int]]:
        """Find the bottom-left origin of each placement of a composite tile.

        The composite ``tile_map`` pattern is matched against the grid via the same
        scan as :meth:`find_tile_positions`, but instead of every covered cell only
        the bottom-left corner ``(base_fx, base_fy)`` of each matching placement is
        reported. This yields one origin per real placement, which is correct even
        when the same composite is repeated contiguously (reconstructing origins
        from the flattened covered-cell set would merge such placements).

        Parameters
        ----------
        composite : Tile
            The composite tile to locate.

        Returns
        -------
        list[tuple[int, int]]
            One ``(base_fx, base_fy)`` bottom-left origin per placement. Empty when
            the composite has no ``tile_map`` or does not appear in the grid.
        """
        rows = composite.tile_map
        if rows is None:
            return []
        height = len(rows)
        origins: list[tuple[int, int]] = []
        for base_fy in range(len(self.tile) - height + 1):
            for base_fx in range(len(self.tile[base_fy]) - composite.max_width + 1):
                if self._composite_matches_grid(composite, base_fx, base_fy):
                    origins.append((base_fx, base_fy))
        return origins

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

        Note
        ----
        Uses bottom-left origin: y=0 is bottom (SOUTH), y=max is top (NORTH).
        """
        # Bottom-left origin: y=0 is bottom (SOUTH), y=max is top (NORTH)
        is_south = y == 0
        is_north = y == self.numberOfRows - 1
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

    def get_all_unique_tiles(self) -> list[Tile]:
        """Get list of unique tile types used in the fabric.

        Returns the leaf tiles that are not part of any composite, plus the
        composite tiles themselves. Both kinds live in ``tileDic``; a composite
        is identified by ``is_composite`` and a leaf belonging to a composite
        carries ``part_of_super_tile``.

        Returns
        -------
        list[Tile]
            List of unique tile types (one instance per type name).
        """
        return [
            tile
            for tile in self.tileDic.values()
            if tile.is_composite or not tile.part_of_super_tile
        ]

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

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

from fabulous.fabric_definition.bel import Bel
from fabulous.fabric_definition.define import IO, Side
from fabulous.fabric_definition.port import Port
from fabulous.fabric_definition.switch_matrix import SwitchMatrix
from fabulous.fabric_definition.tile import Tile


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
    switch_matrix : SwitchMatrix | None
        The supertile switch matrix (source file, connectivity, config bits), or
        None if the supertile has no switch matrix.
    master_tile_coords : tuple[int, int] | None
        Local (x, y) of the master tile. Explicitly set via the `MASTER` token
        in the supertile CSV, or computed as the last non-None tile in row-major
        order if no MASTER is present.  All supertile config bits and BELs are
        anchored to this tile.
    """

    name: str
    tileDir: Path
    tiles: list[Tile]
    tileMap: list[list[Tile]]
    bels: list[Bel] = field(default_factory=list)
    withUserCLK: bool = False
    switch_matrix: SwitchMatrix | None = None
    master_tile_coords: tuple[int, int] | None = None

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
                if tile is None:
                    continue
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

    def get_master_tile_coords(self) -> tuple[int, int]:
        """Return the (x, y) coordinates of the master tile in local space.

        The master tile is either:
        - The tile explicitly marked with `MASTER` in the supertile CSV
          (stored in `master_tile_coords`), or
        - The last non-None tile in row-major order if no MASTER was specified.

        Config bits for the supertile switch matrix and BELs are chained
        through this tile's frame path, and the BEL placement (nextpnr model,
        bitstream spec) is anchored here. This is distinct from the supertile's
        structural *anchor* tile (the top-left tile, where `gen_fabric` places
        the wrapper instance); the master and the anchor are usually different
        tiles (e.g. DSP master = `DSP_bot`, anchor = `DSP_top`).

        Returns
        -------
        tuple[int, int]
            `(x, y)` in local supertile coordinates.

        Raises
        ------
        ValueError
            If the supertile contains no tiles.
        """
        if self.master_tile_coords is not None:
            return self.master_tile_coords
        mx, my = 0, 0
        found = False
        for y, row in enumerate(self.tileMap):
            for x, tile in enumerate(row):
                if tile is not None:
                    mx, my = x, y
                    found = True
        if not found:
            raise ValueError(
                f"SuperTile '{self.name}' has no tiles; cannot determine master tile"
            )
        return mx, my

    def get_all_sjump_ports(self) -> list[tuple[int, int, Port]]:
        """Return all SJUMP OUTPUT ports across every child tile.

        Returns
        -------
        list[tuple[int, int, Port]]
            Each entry is `(local_x, local_y, port)` for every OUTPUT port
            with `wireDirection == Direction.SJUMP` in any child tile.
        """
        result = []
        for y, row in enumerate(self.tileMap):
            for x, tile in enumerate(row):
                if tile is None:
                    continue
                for p in tile.get_sjump_ports():
                    if p.inOut == IO.OUTPUT:
                        result.append((x, y, p))
        return result

    def get_all_input_sjump_ports(self) -> list[tuple[int, int, Port]]:
        """Return all SJUMP INPUT ports across every child tile.

        Returns
        -------
        list[tuple[int, int, Port]]
            Each entry is `(local_x, local_y, port)` for every INPUT port
            with `wireDirection == Direction.SJUMP` in any child tile.
        """
        result = []
        for y, row in enumerate(self.tileMap):
            for x, tile in enumerate(row):
                if tile is None:
                    continue
                for p in tile.get_sjump_ports():
                    if p.inOut == IO.INPUT:
                        result.append((x, y, p))
        return result

    def get_matrix_port_names(self) -> tuple[set[str], set[str]]:
        """Return the valid source and sink names for the supertile switch matrix.

        The names mirror what `gen_super_tile_switch_matrix` declares as matrix
        ports, so they form the authoritative set against which a
        `supertile_matrix` file is validated. Constant sources (`GND0` etc.)
        are not included here; callers add them separately.

        Returns
        -------
        tuple[set[str], set[str]]
            `(valid_sources, valid_sinks)` where sources drive the matrix muxes
            (child OUTPUT SJUMP wires and BEL outputs) and sinks are the mux
            outputs (BEL inputs and child INPUT SJUMP wires).
        """
        valid_sources: set[str] = set()
        valid_sinks: set[str] = set()

        for row in self.tileMap:
            for tile in row:
                if tile is None:
                    continue
                for p in tile.get_sjump_ports():
                    names = {f"{tile.name}_{p.name}{k}" for k in range(p.wireCount)}
                    if p.inOut == IO.OUTPUT:
                        valid_sources |= names
                    else:
                        valid_sinks |= names

        for bel in self.bels:
            valid_sinks.update(bel.inputs)
            valid_sources.update(bel.outputs)

        return valid_sources, valid_sinks

    @property
    def total_config_bits(self) -> int:
        """Return the supertile's config bits: switch matrix bits plus BEL bits."""
        return self.supertile_matrix_config_bits + sum(b.configBit for b in self.bels)

    @property
    def supertile_matrix_dir(self) -> Path | None:
        """Return the supertile switch matrix file, or None if there is none."""
        return None if self.switch_matrix is None else self.switch_matrix.matrix_file

    @property
    def supertile_matrix_config_bits(self) -> int:
        """Return the supertile switch matrix config-bit count (0 if no matrix)."""
        return 0 if self.switch_matrix is None else self.switch_matrix.no_config_bits

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
        x_pin_thickness_mult: Decimal = Decimal(1),
        y_pin_thickness_mult: Decimal = Decimal(1),
        edge_offset: int = 2,
    ) -> tuple[Decimal, Decimal]:
        """Calculate minimum SuperTile dimensions based on IO pin track requirements.

        Takes the maximum per-side IO pin count across all constituent subtiles
        as a conservative upper bound, then derives the minimum physical width
        and height required.

        See `Tile.get_min_die_area` for the track-based derivation.

        Parameters
        ----------
        x_pitch : Decimal
            Vertical-layer track pitch (for north/south pins).
        y_pitch : Decimal
            Horizontal-layer track pitch (for east/west pins).
        x_pin_thickness_mult : Decimal
            Number of tracks each north/south pin spans, by default 1.
        y_pin_thickness_mult : Decimal
            Number of tracks each east/west pin spans, by default 1.
        edge_offset : int, optional
            Reserved tracks at tile edge, by default 2.

        Returns
        -------
        tuple[Decimal, Decimal]
            (min_width, min_height)
        """
        max_north = 0
        max_south = 0
        max_west = 0
        max_east = 0

        for subtile in self.tiles:
            max_north = max(max_north, subtile.get_port_count(Side.NORTH))
            max_south = max(max_south, subtile.get_port_count(Side.SOUTH))
            max_west = max(max_west, subtile.get_port_count(Side.WEST))
            max_east = max(max_east, subtile.get_port_count(Side.EAST))

        x_io_count = Decimal(max(max_north, max_south))
        min_width_io = (x_io_count * x_pin_thickness_mult + edge_offset) * x_pitch

        y_io_count = Decimal(max(max_west, max_east))
        min_height_io = (y_io_count * y_pin_thickness_mult + edge_offset) * y_pitch

        return min_width_io, min_height_io

"""Tile class definition for FPGA fabric representation."""

from collections.abc import Iterator
from dataclasses import dataclass, field
from decimal import Decimal
from pathlib import Path
from typing import TYPE_CHECKING

from loguru import logger

from fabulous.fabric_definition.bel import Bel
from fabulous.fabric_definition.configmem import EMPTY_CONFIG_MEM, ConfigMem
from fabulous.fabric_definition.define import (
    IO,
    Direction,
    PinSortMode,
    Side,
)
from fabulous.fabric_definition.gen_io import Gen_IO
from fabulous.fabric_definition.port import (
    TilePort,
)
from fabulous.fabric_definition.switch_matrix import SwitchMatrix

if TYPE_CHECKING:
    from fabulous.fabric_generator.gds_generator.gen_io_pin_config_yaml import (
        PinOrderConfig,
    )


@dataclass
class Tile:
    """Store information about a tile.

    A tile is composite-capable: a leaf tile is a 1x1 composite of itself, while
    a former supertile is a `Tile` whose `tile_map` holds a grid of sub-tile
    objects. The grid is stored top row first, so `tile_map[0]` is the TOP row
    (physically north) and `tile_map[-1]` is the bottom row (physically south).
    Cell coordinates are `(x=column, y=row)` indices in that top-first space.

    Parameters
    ----------
    name : str
        The name of the tile
    ports : list[TilePort]
        List of ports for the tile
    bels : list[Bel]
        List of Basic Elements of Logic (BELs) in the tile
    tile_dir : Path
        Directory path for the tile
    matrix_dir : Path | None
        Path to the tile's switch-matrix source (file or directory). `None`
        when the tile has no wrapper switch matrix (a composite with no
        `MATRIX` line). A leaf tile always has a real path; parsing raises
        if a leaf tile has no `MATRIX` line.
    gen_ios : list[Gen_IO]
        List of general I/O components
    switch_matrix : SwitchMatrix
        Switch matrix of the tile, holding its source file, connectivity, and
        config-bit count.
    userCLK : bool
        True if the tile uses a clk signal
    pin_order_config : dict[Side, PinOrderConfig] | None
        Configuration for pin ordering on each side of the tile. If None, defaults to
        BUS_MAJOR sorting on all sides.
    tile_map : list[list[Tile | None]] | None
        The 2D grid of sub-tile objects for a composite tile, stored top row
        first. `None` for a leaf tile. Defaults to None.
    sub_tiles : list[Tile] | None
        The flat list of constituent sub-tiles of a composite tile. Defaults to
        an empty list for a leaf tile.
    master_offset : tuple[int, int] | None
        Explicit `(x, y)` cell of the master sub-tile (where the wrapper BELs
        and config bits live). When None, the master defaults to the last
        non-None cell in row-major order. Defaults to None.
    config_mem : ConfigMem
        The tile's configuration memory. Defaults to the empty grid, which a
        tile carries until the parser knows the fabric's frame parameters.

    Attributes
    ----------
    name : str
        The name of the tile
    ports_info : list[TilePort]
        The list of ports of the tile
    bels: list[Bel]
        The list of BELs of the tile
    switch_matrix : SwitchMatrix
        The switch matrix of the tile
    gen_ios : list[Gen_IO]
        The list of GEN_IOs of the tile
    withUserCLK : bool
        Whether the tile has a userCLK port. Default is False.
    tile_dir : Path
        The path to the tile folder
    part_of_composite : bool
        Whether the tile is part of a super tile. Default is False.
    pin_order_config : dict
        Configuration for pin ordering on each side of the tile.
    tile_map : list[list[Tile | None]] | None
        The 2D grid of sub-tile objects for a composite tile, stored top row
        first. `None` for a leaf tile. Defaults to None.
    sub_tiles : list[Tile]
        The flat list of constituent sub-tiles of a composite tile. Empty for a
        leaf tile.
    master_offset : tuple[int, int] | None
        Explicit `(x, y)` cell of the master sub-tile, or None to use the
        row-major default.
    config_mem : ConfigMem
        The tile's configuration memory. Empty until the parser reads the
        fabric's frame parameters and hands it one.
    """

    name: str
    ports_info: list[TilePort]
    bels: list[Bel]
    switch_matrix: SwitchMatrix
    gen_ios: list[Gen_IO]
    withUserCLK: bool = False
    tile_dir: Path = Path()
    part_of_composite: bool = False
    pin_order_config: dict = field(default_factory=dict)
    tile_map: list[list["Tile | None"]] | None = None  # 2D sub-tile layout
    sub_tiles: list["Tile"] = field(default_factory=list)  # flat list of sub-tiles
    master_offset: tuple[int, int] | None = None  # explicit master cell (x, y)
    config_mem: ConfigMem = EMPTY_CONFIG_MEM

    def __init__(
        self,
        name: str,
        ports: list[TilePort],
        bels: list[Bel],
        tile_dir: Path,
        matrix_dir: Path | None,
        gen_ios: list[Gen_IO],
        switch_matrix: SwitchMatrix,
        userCLK: bool,
        pin_order_config: dict[Side, "PinOrderConfig"] | None = None,
        tile_map: list[list["Tile | None"]] | None = None,
        sub_tiles: list["Tile"] | None = None,
        master_offset: tuple[int, int] | None = None,
        config_mem: ConfigMem = EMPTY_CONFIG_MEM,
    ) -> None:
        self.name = name
        self.ports_info = ports
        self.bels = bels
        self.gen_ios = gen_ios
        self.matrix_dir = matrix_dir
        self.switch_matrix = switch_matrix
        self.withUserCLK = userCLK
        self.tile_dir = tile_dir
        self.tile_map = tile_map
        self.sub_tiles = sub_tiles if sub_tiles is not None else []
        self.master_offset = master_offset
        self.config_mem = config_mem

        if pin_order_config is None:
            from fabulous.fabric_generator.gds_generator.gen_io_pin_config_yaml import (
                PinOrderConfig,
            )

            self.pin_order_config = {
                Side.NORTH: PinOrderConfig(sort_mode=PinSortMode.BUS_MAJOR),
                Side.EAST: PinOrderConfig(sort_mode=PinSortMode.BUS_MAJOR),
                Side.SOUTH: PinOrderConfig(sort_mode=PinSortMode.BUS_MAJOR),
                Side.WEST: PinOrderConfig(sort_mode=PinSortMode.BUS_MAJOR),
            }
        else:
            self.pin_order_config = pin_order_config

    def __eq__(self, __o: object, /) -> bool:
        """Check equality between tiles based on their name.

        Parameters
        ----------
        __o : object
            The object to compare with.

        Returns
        -------
        bool
            True if both tiles have the same name, False otherwise.
        """
        if __o is None or not isinstance(__o, Tile):
            return False
        return self.name == __o.name

    def ports_on(self, side: Side, io: IO | None = None) -> list[TilePort]:
        """Return the pins the tile presents on one border.

        Parameters
        ----------
        side : Side
            The border. `Side.ANY` holds the pins of no border, the jumps.
        io : IO | None
            Keep only inputs or only outputs. Defaults to both.

        Returns
        -------
        list[TilePort]
            The ports in the order the tile declares them, NULL names dropped.
        """
        return [
            port
            for port in self.ports_info
            if port.side_of_tile is side
            and not port.name_is_null
            and (io is None or port.io_direction is io)
        ]

    def ports_along(self, direction: Direction, io: IO | None = None) -> list[TilePort]:
        """Return the pins of the wires that travel one way.

        The two ends of a wire sit on opposite borders, so this is the accessor
        a fabric stitch works in: the tile's inputs of a direction meet the
        outputs of the same direction on the neighbour that direction points
        away from.

        Parameters
        ----------
        direction : Direction
            The direction the wires travel. JUMP stays inside the tile.
        io : IO | None
            Keep only inputs or only outputs. Defaults to both.

        Returns
        -------
        list[TilePort]
            The ports in the order the tile declares them, NULL names dropped.
        """
        return [
            port
            for port in self.ports_info
            if port.wire_direction is direction
            and not port.name_is_null
            and (io is None or port.io_direction is io)
        ]

    def get_tile_output_names(self) -> list[str]:
        """Get all output port source names for the tile.

        Returns
        -------
        list[str]
            List of source names for output ports, excluding NULL and JUMP
            direction ports.
        """
        return [
            p.source_name
            for p in self.ports_info
            if p.source_name != "NULL"
            and p.wire_direction != Direction.JUMP
            and p.is_output
        ]

    @property
    def total_config_bits(self) -> int:
        """Get the total number of global configuration bits.

        Calculates the sum of switch matrix configuration bits
        and all BEL configuration bits.

        Returns
        -------
        int
            Total number of global configuration bits for the tile.
        """
        ret = self.switch_matrix.no_config_bits

        for b in self.bels:
            ret += b.configBit

        return ret

    def port_count(self, side: Side) -> int:
        """Count total number of expanded physical pins on a given side of the tile.

        Parameters
        ----------
        side : Side
            The side of the tile to count ports for.

        Returns
        -------
        int
            Total number of expanded ports on the given side.
        """
        total = 0
        for p in self.ports_info:
            if p.side_of_tile != side or p.name_is_null:
                continue
            inputs, outputs = p.expand_port_info("all")
            if p.name == p.source_name:
                total += len(inputs)
            elif p.name == p.destination_name:
                total += len(outputs)

        return total

    def get_min_die_area(
        self,
        x_pitch: Decimal,
        y_pitch: Decimal,
        x_pin_thickness_mult: Decimal = Decimal(1),
        y_pin_thickness_mult: Decimal = Decimal(1),
        frame_data_width: int = 32,
        frame_strobe_width: int = 20,
        edge_offset: int = 2,
    ) -> tuple[Decimal, Decimal]:
        """Calculate minimum tile dimensions based on IO pin track requirements.

        The IO pin placer distributes pins across available tracks on each
        tile edge. Each pin occupies `thickness_mult` consecutive tracks,
        and `edge_offset` tracks are reserved at the start of the tile
        (see `tile_io_place.allocate_tracks`).

        The minimum number of tracks on a side is therefore::

            required_tracks = port_count * thickness_mult + edge_offset

        And the minimum physical dimension is::

            min_dim = required_tracks * pitch

        For a composite tile the per-side pin count is the maximum across all
        constituent sub-tiles (a conservative upper bound). A leaf tile's
        `get_sub_tiles` returns `[self]`, so the same code path naturally
        uses the leaf's own per-side pin counts.

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
        frame_data_width : int, optional
            Frame data width, by default 32.
        frame_strobe_width : int, optional
            Frame strobe width, by default 20.
        edge_offset : int, optional
            Reserved tracks at tile edge, by default 2.

        Returns
        -------
        tuple[Decimal, Decimal]
            (min_width, min_height)
        """
        sub_tiles = self.get_sub_tiles()
        north_ports = max(sub.port_count(Side.NORTH) for sub in sub_tiles)
        south_ports = max(sub.port_count(Side.SOUTH) for sub in sub_tiles)
        west_ports = max(sub.port_count(Side.WEST) for sub in sub_tiles)
        east_ports = max(sub.port_count(Side.EAST) for sub in sub_tiles)

        x_io_count = Decimal(max(north_ports, south_ports) + frame_strobe_width)
        min_width_io = (x_io_count * x_pin_thickness_mult + edge_offset) * x_pitch

        y_io_count = Decimal(max(west_ports, east_ports) + frame_data_width)
        min_height_io = (y_io_count * y_pin_thickness_mult + edge_offset) * y_pitch

        return min_width_io, min_height_io

    @property
    def is_composite(self) -> bool:
        """Whether this tile is a composite tile holding sub-tiles.

        Returns
        -------
        bool
            `True` if the tile carries a `tile_map` (and therefore contains
            sub-tiles), `False` for a leaf tile.
        """
        return self.tile_map is not None

    @property
    def max_width(self) -> int:
        """Maximum number of columns across the tile map.

        Returns
        -------
        int
            The widest row in `tile_map` for a composite tile, or `1` for a
            leaf tile.
        """
        if self.tile_map is None:
            return 1
        return max(len(row) for row in self.tile_map)

    @property
    def max_height(self) -> int:
        """Number of rows in the tile map.

        Returns
        -------
        int
            The number of rows in `tile_map` for a composite tile, or `1` for
            a leaf tile.
        """
        if self.tile_map is None:
            return 1
        return len(self.tile_map)

    def __iter__(self) -> Iterator[tuple[tuple[int, int], "Tile"]]:
        """Iterate over the sub-tiles and their grid coordinates.

        For a leaf tile a single `((0, 0), self)` pair is yielded. For a
        composite tile each non-`None` cell is yielded as `((x, y), tile)`
        where `x` is the column index and `y` is the row index.

        Yields
        ------
        tuple[tuple[int, int], Tile]
            The `(x, y)` grid coordinate and the sub-tile at that cell.
        """
        if self.tile_map is None:
            yield (0, 0), self
            return
        for y, row in enumerate(self.tile_map):
            for x, tile in enumerate(row):
                if tile is not None:
                    yield (x, y), tile

    def fabric_dy(self, row_index: int) -> int:
        """Convert a top-first `tile_map` row index to a bottom-first fabric offset.

        `tile_map` is stored top row first (row 0 = north), while the fabric
        grid (`Fabric.tile`) is stored bottom row first (row 0 = south). This
        flips the row axis only; column indices are identical between the two
        orientations.

        Parameters
        ----------
        row_index : int
            A row index into `tile_map`, top-first.

        Returns
        -------
        int
            The corresponding row offset in the bottom-first fabric grid.
        """
        return self.max_height - 1 - row_index

    def iter_cells_fabric(self) -> Iterator[tuple[int, int, "Tile"]]:
        """Iterate over populated sub-tile cells using fabric-oriented offsets.

        Like `__iter__`, but the row component of each coordinate is converted
        from `tile_map`'s top-first storage into the fabric grid's
        bottom-first orientation via `fabric_dy`. For a leaf tile a single
        `(0, 0, self)` triple is yielded.

        Yields
        ------
        tuple[int, int, Tile]
            The `(dx, fabric_dy, sub_tile)` triple for each populated cell,
            where `dx` is the column offset and `fabric_dy` is the row offset
            in the bottom-first fabric grid.
        """
        for (x, y), tile in self:
            yield x, self.fabric_dy(y), tile

    def get_ports_around_tile(self) -> dict[str, list[list[TilePort]]]:
        """Return the perimeter side ports of each composite sub-tile cell.

        The dictionary key is the sub-tile cell location in `"x,y"` format,
        matching the `(x, y)` grid indexing of `__iter__` (`x` is the
        column, `y` is the row). For each present cell, the side-port list of a
        given side is appended only when that side faces the composite boundary
        (its neighbour in the grid is missing or `None`). `tile_map` is stored
        top row first, so a smaller row index is physically north.

        Returns
        -------
        dict[str, list[list[TilePort]]]
            Mapping from cell coordinate to the perimeter side-port lists. An
            empty dict for a leaf tile.
        """
        if self.tile_map is None:
            return {}

        ports: dict[str, list[list[TilePort]]] = {}
        for y, row in enumerate(self.tile_map):
            for x, tile in enumerate(row):
                if tile is None:
                    continue
                key = f"{x},{y}"
                ports[key] = []
                # Top-first storage: y-1 is physically north, y+1 is south.
                # Order is N,E,S,W to match the emitted HDL port order.
                if y - 1 < 0 or self.tile_map[y - 1][x] is None:
                    ports[key].append(tile.ports_on(Side.NORTH))
                if x + 1 >= len(row) or row[x + 1] is None:
                    ports[key].append(tile.ports_on(Side.EAST))
                if y + 1 >= len(self.tile_map) or self.tile_map[y + 1][x] is None:
                    ports[key].append(tile.ports_on(Side.SOUTH))
                if x - 1 < 0 or row[x - 1] is None:
                    ports[key].append(tile.ports_on(Side.WEST))
        return ports

    def get_internal_connections(self) -> list[tuple[list[TilePort], int, int]]:
        """Return the internal edge side ports between adjacent sub-tile cells.

        For each present cell, the side-port list of a given side is reported
        when that side faces another present sub-tile (an internal edge). Each
        entry carries the side ports and the `(x, y)` cell coordinate, using
        the same grid indexing as `__iter__`. `tile_map` is stored top row
        first, so a smaller row index is physically north.

        Returns
        -------
        list[tuple[list[TilePort], int, int]]
            One entry per internal edge as `(side_ports, x, y)`. An empty list
            for a leaf tile.
        """
        if self.tile_map is None:
            return []

        internal_connections: list[tuple[list[TilePort], int, int]] = []
        for y, row in enumerate(self.tile_map):
            for x, tile in enumerate(row):
                if tile is None:
                    continue
                # Top-first storage: y-1 is physically north, y+1 is south.
                # Order is N,E,S,W to match the emitted HDL port order.
                if y - 1 >= 0 and self.tile_map[y - 1][x] is not None:
                    internal_connections.append((tile.ports_on(Side.NORTH), x, y))
                if x + 1 < len(row) and row[x + 1] is not None:
                    internal_connections.append((tile.ports_on(Side.EAST), x, y))
                if y + 1 < len(self.tile_map) and self.tile_map[y + 1][x] is not None:
                    internal_connections.append((tile.ports_on(Side.SOUTH), x, y))
                if x - 1 >= 0 and row[x - 1] is not None:
                    internal_connections.append((tile.ports_on(Side.WEST), x, y))
        return internal_connections

    def get_anchor_offset(self) -> tuple[int, int]:
        """Return the `(x, y)` cell of the composite anchor sub-tile.

        The anchor is where the composite is structurally placed and where its
        external ports are named: the first non-None cell in row-major order,
        which under top-first storage is the top-left cell. A leaf tile anchors
        at the origin.

        Returns
        -------
        tuple[int, int]
            The `(x, y)` anchor cell, `(0, 0)` for a leaf tile.

        Raises
        ------
        ValueError
            If a composite tile has an all-None `tile_map`.
        """
        if self.tile_map is None:
            return (0, 0)
        for y, row in enumerate(self.tile_map):
            for x, tile in enumerate(row):
                if tile is not None:
                    return (x, y)
        message = (
            f"Composite tile '{self.name}' has no sub-tiles; cannot determine anchor"
        )
        logger.error(message)
        raise ValueError(message)

    def get_master_offset(self) -> tuple[int, int]:
        """Return the `(x, y)` cell of the composite master sub-tile.

        The master is where the wrapper's BELs and config bits physically live.
        When `master_offset` is set it is returned directly; otherwise the
        master defaults to the last non-None cell in row-major order. A leaf tile
        masters at the origin.

        Returns
        -------
        tuple[int, int]
            The `(x, y)` master cell, `(0, 0)` for a leaf tile.

        Raises
        ------
        ValueError
            If a composite tile has an all-None `tile_map` and no explicit
            `master_offset`.
        """
        if self.tile_map is None:
            return (0, 0)
        if self.master_offset is not None:
            return self.master_offset

        master: tuple[int, int] | None = None
        for y, row in enumerate(self.tile_map):
            for x, tile in enumerate(row):
                if tile is not None:
                    master = (x, y)
        if master is None:
            message = (
                f"Composite tile '{self.name}' has no sub-tiles; "
                "cannot determine master"
            )
            logger.error(message)
            raise ValueError(message)
        return master

    def get_master_tile(self) -> "Tile":
        """Return the sub-tile at the composite's master cell.

        Returns
        -------
        Tile
            The master sub-tile, or `self` for a leaf tile.

        Raises
        ------
        ValueError
            If an explicit `master_offset` points at an empty cell.
        """
        if self.tile_map is None:
            return self
        x, y = self.get_master_offset()
        master = self.tile_map[y][x]
        if master is None:
            raise ValueError(
                f"Composite tile '{self.name}' masters at ({x}, {y}), which is empty."
            )
        return master

    def get_sub_tiles(self) -> list["Tile"]:
        """Get the list of all sub-tiles.

        Returns
        -------
        list[Tile]
            The non-`None` sub-tile objects of a composite tile, or `[self]`
            for a leaf tile.
        """
        if self.tile_map is None:
            return [self]
        return [tile for row in self.tile_map for tile in row if tile is not None]

    def get_sub_tile_offset(self, sub_tile: "Tile | str") -> tuple[int, int]:
        """Get the (x, y) offset for a sub-tile in the tile map.

        Parameters
        ----------
        sub_tile : Tile | str
            The sub-tile object or its name to locate.

        Returns
        -------
        tuple[int, int]
            The `(x, y)` position in the tile map, with `y=0` at the top row,
            matching `get_anchor_offset` and `get_master_offset`.

        Raises
        ------
        ValueError
            If the sub-tile is not found.
        """
        if self.tile_map is None:
            if self._matches_tile(self, sub_tile):
                return (0, 0)
            raise ValueError(f"Sub-tile '{sub_tile}' not found in tile '{self.name}'")

        for y, row in enumerate(self.tile_map):
            for x, tile in enumerate(row):
                if tile is not None and self._matches_tile(tile, sub_tile):
                    return (x, y)
        raise ValueError(f"Sub-tile '{sub_tile}' not found in tile_map")

    def part_of_tile(self, sub_tile: "Tile | str") -> bool:
        """Check whether a sub-tile is part of this tile.

        Parameters
        ----------
        sub_tile : Tile | str
            The sub-tile object or its name to check.

        Returns
        -------
        bool
            `True` if the given sub-tile is a sub-tile of this tile.
        """
        return any(self._matches_tile(tile, sub_tile) for tile in self.get_sub_tiles())

    def is_root_tile(self, sub_tile: "Tile | str") -> bool:
        """Check whether a sub-tile is the root sub-tile (bottom-left).

        Parameters
        ----------
        sub_tile : Tile | str
            The sub-tile object or its name to check.

        Returns
        -------
        bool
            `True` if the given sub-tile is the bottom-left sub-tile.
        """
        if self.tile_map is None:
            return self._matches_tile(self, sub_tile)
        root_tile = self.tile_map[-1][0]
        if root_tile is None:
            return False
        return self._matches_tile(root_tile, sub_tile)

    @staticmethod
    def _matches_tile(tile: "Tile", reference: "Tile | str") -> bool:
        """Check whether a tile matches a reference object or name.

        Parameters
        ----------
        tile : Tile
            The candidate sub-tile.
        reference : Tile | str
            The sub-tile object or name to match against.

        Returns
        -------
        bool
            `True` if `tile` matches `reference` by name (when a string is
            given) or by equality (when a tile object is given).
        """
        if isinstance(reference, str):
            return tile.name == reference
        return tile == reference

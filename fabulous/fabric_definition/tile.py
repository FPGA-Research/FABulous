"""Tile class definition for FPGA fabric representation."""

from collections.abc import Iterator
from dataclasses import dataclass, field
from decimal import Decimal
from pathlib import Path
from typing import TYPE_CHECKING

from loguru import logger

from fabulous.fabric_definition.bel import Bel
from fabulous.fabric_definition.define import IO, Direction, PinSortMode, Side
from fabulous.fabric_definition.gen_io import Gen_IO
from fabulous.fabric_definition.port import (
    BelPort,
    GenericPort,
    SharedPort,
    TilePort,
)
from fabulous.fabric_definition.switch_matrix import SwitchMatrix
from fabulous.fabric_definition.wire import Wire

if TYPE_CHECKING:
    from fabulous.fabric_generator.gds_generator.gen_io_pin_config_yaml import (
        PinOrderConfig,
    )


@dataclass
class Tile:
    """Store information about a tile.

    A tile is composite-capable: a leaf tile is a 1x1 composite of itself, while
    a former supertile is a ``Tile`` whose ``tile_map`` holds a grid of sub-tile
    objects. The grid is stored top row first, so ``tile_map[0]`` is the TOP row
    (physically north) and ``tile_map[-1]`` is the bottom row (physically south).
    All ``(x, y)`` cell coordinates produced by :meth:`__iter__`,
    :meth:`get_ports_around_tile`, :meth:`get_sub_tile_offset`,
    :meth:`get_anchor_offset` and :meth:`get_master_offset` use ``x`` as the
    column index and ``y`` as the row index in this top-first space.

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
    matrix_dir : Path
        Path to the tile's switch-matrix source (file or directory). ``Path()``
        when the tile has no wrapper switch matrix.
    gen_ios : list[Gen_IO]
        List of general I/O components
    user_clk : bool
        True if the tile uses a clk signal
    switch_matrix : SwitchMatrix
        Switch matrix of the tile, holding its source file, connectivity, and
        config-bit count.
    pin_order_config : dict[Side, PinOrderConfig] | None, optional
        Configuration for pin ordering on each side of the tile. If None, defaults to
        BUS_MAJOR sorting on all sides.
    tile_map : list[list[Tile | None]] | None, optional
        The 2D grid of sub-tile objects for a composite tile, stored top row
        first. ``None`` for a leaf tile. Default is None.
    sub_tiles : list[Tile] | None, optional
        The flat list of constituent sub-tiles of a composite tile. Defaults to
        an empty list for a leaf tile.
    master_offset : tuple[int, int] | None, optional
        Explicit ``(x, y)`` cell of the master sub-tile (where the wrapper BELs
        and config bits live). When None, the master defaults to the last
        non-None cell in row-major order. Default is None.

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
    with_user_clk : bool
        Whether the tile has a user_clk port. Default is False.
    wire_list : list[Wire]
        The list of wires of the tile
    tile_dir : Path
        The path to the tile folder
    part_of_super_tile : bool, optional
        Whether the tile is part of a super tile. Default is False.
    pin_order_config : dict, optional
        Configuration for pin ordering on each side of the tile.
    tile_map : list[list[Tile | None]] | None, optional
        The 2D grid of sub-tile objects for a composite tile, stored top row
        first. ``None`` for a leaf tile. Default is None.
    sub_tiles : list[Tile], optional
        The flat list of constituent sub-tiles of a composite tile. Empty for a
        leaf tile.
    master_offset : tuple[int, int] | None, optional
        Explicit ``(x, y)`` cell of the master sub-tile, or None to use the
        row-major default.
    """

    name: str
    ports_info: list[TilePort]
    bels: list[Bel]
    switch_matrix: SwitchMatrix
    gen_ios: list[Gen_IO]
    with_user_clk: bool = False
    wire_list: list[Wire] = field(default_factory=list)
    tile_dir: Path = Path()
    part_of_super_tile: bool = False
    pin_order_config: dict = field(default_factory=dict)
    tile_map: list[list["Tile | None"]] | None = None  # 2D sub-tile layout
    sub_tiles: list["Tile"] = field(default_factory=list)  # flat list of sub-tiles
    master_offset: tuple[int, int] | None = None  # explicit master cell (x, y)

    def __init__(
        self,
        name: str,
        ports: list[TilePort],
        bels: list[Bel],
        tile_dir: Path,
        matrix_dir: Path,
        gen_ios: list[Gen_IO],
        user_clk: bool,
        switch_matrix: SwitchMatrix,
        pin_order_config: dict[Side, "PinOrderConfig"] | None = None,
        tile_map: list[list["Tile | None"]] | None = None,
        sub_tiles: list["Tile"] | None = None,
        master_offset: tuple[int, int] | None = None,
    ) -> None:
        self.name = name
        self.ports_info = ports
        self.bels = bels
        self.gen_ios = gen_ios
        self.matrix_dir = matrix_dir
        self.with_user_clk = user_clk
        self.switch_matrix = switch_matrix
        self.wire_list = []
        self.tile_dir = tile_dir
        self.tile_map = tile_map
        self.sub_tiles = sub_tiles if sub_tiles is not None else []
        self.master_offset = master_offset

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

    def get_port_on_side(self, side: Side, io: IO | None = None) -> list[TilePort]:
        """Get the ports physically located on a given side of the tile.

        Parameters
        ----------
        side : Side
            The physical side of the tile to collect ports from.
        io : IO | None
            Restrict the result to this I/O direction. Defaults to None, which
            keeps both directions.

        Returns
        -------
        list[TilePort]
            The matching ports, excluding NULL ports.
        """
        ports = [
            p for p in self.ports_info if p.side_of_tile == side and not p.name_is_null
        ]
        if io is not None:
            ports = [p for p in ports if p.io_direction == io]
        return ports

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
    def switch_matrix_config_bits(self) -> int:
        """Get the number of config bits for the switch matrix.

        This is a backward-compatibility property that returns
        the config_bits from the switch_matrix.

        Returns
        -------
        int
            Number of configuration bits for the switch matrix.
        """
        return self.switch_matrix.total_config_bits

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
        ret = self.switch_matrix.total_config_bits

        for b in self.bels:
            ret += b.config_bit

        return ret

    def get_port_count(self, side: Side) -> int:
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

            required_tracks = pin_count * thickness_mult + edge_offset

        And the minimum physical dimension is::

            min_dim = required_tracks * pitch

        For a composite tile the per-side pin count is the maximum across all
        constituent sub-tiles (a conservative upper bound). A leaf tile's
        :meth:`get_sub_tiles` returns ``[self]``, so the same code path naturally
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
        north_ports = max(sub.get_port_count(Side.NORTH) for sub in sub_tiles)
        south_ports = max(sub.get_port_count(Side.SOUTH) for sub in sub_tiles)
        west_ports = max(sub.get_port_count(Side.WEST) for sub in sub_tiles)
        east_ports = max(sub.get_port_count(Side.EAST) for sub in sub_tiles)

        x_io_count = Decimal(max(north_ports, south_ports) + frame_strobe_width)
        min_width_io = (x_io_count * x_pin_thickness_mult + edge_offset) * x_pitch

        y_io_count = Decimal(max(west_ports, east_ports) + frame_data_width)
        min_height_io = (y_io_count * y_pin_thickness_mult + edge_offset) * y_pitch

        return min_width_io, min_height_io

    @property
    def ports(self) -> dict[str, list[TilePort]]:
        """Provide a hierarchical view of ports grouped by sub-tile name.

        Sub-tile ownership is structural: each sub-tile object owns its own
        ``ports_info``. A leaf tile's :meth:`get_sub_tiles` returns ``[self]``, so
        its ports are grouped under the tile's own name. A composite tile groups
        each sub-tile's ports under that sub-tile's name; sub-tiles that share a
        name have their ports merged.

        Returns
        -------
        dict[str, list[TilePort]]
            Dictionary mapping sub-tile names to their associated ports.
        """
        result: dict[str, list[TilePort]] = {}
        for sub_tile in self.get_sub_tiles():
            result.setdefault(sub_tile.name, []).extend(sub_tile.ports_info)
        return result

    @property
    def bel_groups(self) -> dict[str, list[Bel]]:
        """Provide a hierarchical view of BELs grouped by sub-tile name.

        Sub-tile ownership is structural: each sub-tile object owns its own
        ``bels``. A leaf tile's :meth:`get_sub_tiles` returns ``[self]``, so its
        BELs are grouped under the tile's own name. A composite tile groups each
        sub-tile's BELs under that sub-tile's name; sub-tiles that share a name
        have their BELs merged. A composite's own wrapper BELs (``self.bels``)
        are not sub-tile BELs and are surfaced separately via :attr:`bels`.

        Returns
        -------
        dict[str, list[Bel]]
            Dictionary mapping sub-tile names to their associated BELs.
        """
        result: dict[str, list[Bel]] = {}
        for sub_tile in self.get_sub_tiles():
            result.setdefault(sub_tile.name, []).extend(sub_tile.bels)
        return result

    @property
    def config_bits(self) -> int:
        """Get the total number of configuration bits.

        This is an alias for total_config_bits for API compatibility.

        Returns
        -------
        int
            Total number of configuration bits for the tile.
        """
        return self.total_config_bits

    @property
    def is_composite(self) -> bool:
        """Whether this tile is a composite tile holding sub-tiles.

        Returns
        -------
        bool
            ``True`` if the tile carries a ``tile_map`` (and therefore contains
            sub-tiles), ``False`` for a leaf tile.
        """
        return self.tile_map is not None

    @property
    def max_width(self) -> int:
        """Maximum number of columns across the tile map.

        Returns
        -------
        int
            The widest row in ``tile_map`` for a composite tile, or ``1`` for a
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
            The number of rows in ``tile_map`` for a composite tile, or ``1`` for
            a leaf tile.
        """
        if self.tile_map is None:
            return 1
        return len(self.tile_map)

    def __iter__(self) -> Iterator[tuple[tuple[int, int], "Tile"]]:
        """Iterate over the sub-tiles and their grid coordinates.

        For a leaf tile a single ``((0, 0), self)`` pair is yielded. For a
        composite tile each non-``None`` cell is yielded as ``((x, y), tile)``
        where ``x`` is the column index and ``y`` is the row index.

        Yields
        ------
        tuple[tuple[int, int], Tile]
            The ``(x, y)`` grid coordinate and the sub-tile at that cell.
        """
        if self.tile_map is None:
            yield (0, 0), self
            return
        for y, row in enumerate(self.tile_map):
            for x, tile in enumerate(row):
                if tile is not None:
                    yield (x, y), tile

    def get_ports_around_tile(self) -> dict[str, list[list[TilePort]]]:
        """Return the perimeter side ports of each composite sub-tile cell.

        The dictionary key is the sub-tile cell location in ``"x,y"`` format,
        matching the ``(x, y)`` grid indexing of :meth:`__iter__` (``x`` is the
        column, ``y`` is the row). For each present cell, the side-port list of a
        given side is appended only when that side faces the composite boundary
        (its neighbour in the grid is missing or ``None``). ``tile_map`` is stored
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
                if y - 1 < 0 or self.tile_map[y - 1][x] is None:
                    ports[key].append(tile.get_port_on_side(Side.NORTH))
                if y + 1 >= len(self.tile_map) or self.tile_map[y + 1][x] is None:
                    ports[key].append(tile.get_port_on_side(Side.SOUTH))
                if x + 1 >= len(row) or row[x + 1] is None:
                    ports[key].append(tile.get_port_on_side(Side.EAST))
                if x - 1 < 0 or row[x - 1] is None:
                    ports[key].append(tile.get_port_on_side(Side.WEST))
        return ports

    def get_internal_connections(self) -> list[tuple[list[TilePort], int, int]]:
        """Return the internal edge side ports between adjacent sub-tile cells.

        For each present cell, the side-port list of a given side is reported
        when that side faces another present sub-tile (an internal edge). Each
        entry carries the side ports and the ``(x, y)`` cell coordinate, using
        the same grid indexing as :meth:`__iter__`. ``tile_map`` is stored top row
        first, so a smaller row index is physically north.

        Returns
        -------
        list[tuple[list[TilePort], int, int]]
            One entry per internal edge as ``(side_ports, x, y)``. An empty list
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
                if y - 1 >= 0 and self.tile_map[y - 1][x] is not None:
                    internal_connections.append(
                        (tile.get_port_on_side(Side.NORTH), x, y)
                    )
                if y + 1 < len(self.tile_map) and self.tile_map[y + 1][x] is not None:
                    internal_connections.append(
                        (tile.get_port_on_side(Side.SOUTH), x, y)
                    )
                if x + 1 < len(row) and row[x + 1] is not None:
                    internal_connections.append(
                        (tile.get_port_on_side(Side.EAST), x, y)
                    )
                if x - 1 >= 0 and row[x - 1] is not None:
                    internal_connections.append(
                        (tile.get_port_on_side(Side.WEST), x, y)
                    )
        return internal_connections

    def get_anchor_offset(self) -> tuple[int, int]:
        """Return the ``(x, y)`` cell of the composite anchor sub-tile.

        The anchor is where the composite is structurally placed and where its
        external ports are named: the first non-None cell in row-major order,
        which under top-first storage is the top-left cell. A leaf tile anchors
        at the origin.

        Returns
        -------
        tuple[int, int]
            The ``(x, y)`` anchor cell, ``(0, 0)`` for a leaf tile.

        Raises
        ------
        ValueError
            If a composite tile has an all-None ``tile_map``.
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
        """Return the ``(x, y)`` cell of the composite master sub-tile.

        The master is where the wrapper's BELs and config bits physically live.
        When ``master_offset`` is set it is returned directly; otherwise the
        master defaults to the last non-None cell in row-major order. A leaf tile
        masters at the origin.

        Returns
        -------
        tuple[int, int]
            The ``(x, y)`` master cell, ``(0, 0)`` for a leaf tile.

        Raises
        ------
        ValueError
            If a composite tile has an all-None ``tile_map`` and no explicit
            ``master_offset``.
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

    def get_sub_tiles(self) -> list["Tile"]:
        """Get the list of all sub-tiles.

        Returns
        -------
        list[Tile]
            The non-``None`` sub-tile objects of a composite tile, or ``[self]``
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
            The ``(x, y)`` position in the tile map, with ``y=0`` at the top row,
            matching :meth:`get_anchor_offset` and :meth:`get_master_offset`.

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
            ``True`` if the given sub-tile is a sub-tile of this tile.
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
            ``True`` if the given sub-tile is the bottom-left sub-tile.
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
            ``True`` if ``tile`` matches ``reference`` by name (when a string is
            given) or by equality (when a tile object is given).
        """
        if isinstance(reference, str):
            return tile.name == reference
        return tile == reference

    def find_port_by_name(self, port_name: str) -> GenericPort | None:
        """Find a port by name in tile ports or BEL ports.

        Searches first in tile ports, then in all BEL ports (inputs, outputs,
        external inputs, external outputs).

        Parameters
        ----------
        port_name : str
            Name of the port to find.

        Returns
        -------
        GenericPort | None
            The port if found, None otherwise.
        """
        # Search tile ports
        for port in self.ports_info:
            if port.name == port_name:
                return port

        # Search BEL ports
        for bel in self.bels:
            for p in bel.inputs + bel.outputs:
                if p.name == port_name:
                    return p
            for p in bel.external_inputs + bel.external_outputs:
                if p.name == port_name:
                    return p

        return None

    def is_port_in_tile(self, port: GenericPort) -> bool:
        """Check if a port exists in this tile.

        Searches in both tile ports and BEL ports.

        Parameters
        ----------
        port : GenericPort
            Port to check.

        Returns
        -------
        bool
            True if the port exists in this tile.
        """
        # Check tile ports
        for p in self.ports_info:
            if p.name == port.name:
                return True

        # Check BEL ports
        for bel in self.bels:
            for p in bel.inputs + bel.outputs:
                if p.name == port.name:
                    return True
            for p in bel.external_inputs + bel.external_outputs:
                if p.name == port.name:
                    return True

        return False

    def get_tile_input_ports(self, sub_tile: str = "") -> list[TilePort]:
        """Get all input ports, optionally filtered by sub-tile.

        Parameters
        ----------
        sub_tile : str, optional
            Sub-tile name to filter by. If empty, returns all input ports.

        Returns
        -------
        list[TilePort]
            List of input ports, sorted by name.
        """
        ports = self.ports.get(sub_tile, []) if sub_tile else self.ports_info
        return sorted([p for p in ports if p.is_input], key=lambda p: p.name)

    def get_tile_output_ports(self, sub_tile: str = "") -> list[TilePort]:
        """Get all output ports, optionally filtered by sub-tile.

        Parameters
        ----------
        sub_tile : str, optional
            Sub-tile name to filter by. If empty, returns all output ports.

        Returns
        -------
        list[TilePort]
            List of output ports, sorted by name.
        """
        ports = self.ports.get(sub_tile, []) if sub_tile else self.ports_info
        return sorted([p for p in ports if p.is_output], key=lambda p: p.name)

    def get_tile_port_grouped(self, io: IO | None = None) -> dict[Side, list[TilePort]]:
        """Get ports grouped by side of tile.

        Parameters
        ----------
        io : IO | None, optional
            I/O direction to filter by. If None, includes all ports.

        Returns
        -------
        dict[Side, list[TilePort]]
            Dictionary mapping Side enum to list of ports on that side.
        """
        result = {
            Side.NORTH: self.get_port_on_side(Side.NORTH),
            Side.EAST: self.get_port_on_side(Side.EAST),
            Side.SOUTH: self.get_port_on_side(Side.SOUTH),
            Side.WEST: self.get_port_on_side(Side.WEST),
        }
        if io is not None:
            for side in result:
                result[side] = [p for p in result[side] if p.io_direction == io]
        return result

    def get_unique_bel_type(self) -> list[Bel]:
        """Get unique BELs by name (deduplicated).

        Returns
        -------
        list[Bel]
            List of unique BELs, with duplicates (same name) removed.
        """
        seen: set[str] = set()
        result: list[Bel] = []
        for bel in self.bels:
            if bel.name not in seen:
                seen.add(bel.name)
                result.append(bel)
        return result

    def get_bel_by_bel_port(self, bel_port: BelPort) -> Bel | None:
        """Find the BEL containing a specific port.

        Parameters
        ----------
        bel_port : BelPort
            The BEL port to search for.

        Returns
        -------
        Bel | None
            The BEL containing the port, or None if not found.
        """
        for bel in self.bels:
            for p in bel.inputs + bel.outputs:
                if p.name == bel_port.name:
                    return bel
            for p in bel.external_inputs + bel.external_outputs:
                if p.name == bel_port.name:
                    return bel
        return None

    def get_bel_shared_port(self) -> list[SharedPort]:
        """Get all unique shared ports from BELs.

        Returns
        -------
        list[SharedPort]
            List of unique SharedPort objects from all BELs.
        """
        seen: set[str] = set()
        result: list[SharedPort] = []
        for bel in self.bels:
            for port in bel.shared_port:
                if port.name not in seen:
                    seen.add(port.name)
                    result.append(port)
        return result

    def serialize(self) -> dict:
        """Serialize tile to dictionary for JSON export.

        Returns
        -------
        dict
            Dictionary representation of the tile.
        """
        return {
            "name": self.name,
            "ports": {k: [p.serialize() for p in v] for k, v in self.ports.items()},
            "bels": [b.serialize() for b in self.bels],
            "switch_matrix": self.switch_matrix.serialize(),
            "config_bits": self.total_config_bits,
            "with_user_clk": self.with_user_clk,
            "tile_map": (
                [
                    [tile.name if tile is not None else None for tile in row]
                    for row in self.tile_map
                ]
                if self.tile_map is not None
                else None
            ),
            "part_of_super_tile": self.part_of_super_tile,
            "is_composite": self.is_composite,
        }

    def __str__(self) -> str:
        """Return a formatted string representation of the tile.

        Returns
        -------
        str
            Multi-line string describing the tile.
        """
        lines = [f"Tile: {self.name}"]
        lines.append(f"  Config bits: {self.total_config_bits}")
        lines.append(f"  Switch matrix bits: {self.switch_matrix_config_bits}")
        lines.append(f"  BELs: {len(self.bels)}")
        lines.append(f"  Ports: {len(self.ports_info)}")
        lines.append(f"  User CLK: {self.with_user_clk}")

        if self.tile_map:
            lines.append(f"  Sub-tiles: {self.get_sub_tiles()}")

        # Port summary by side
        lines.append("  Ports by side:")
        for side in [Side.NORTH, Side.EAST, Side.SOUTH, Side.WEST]:
            ports = self.get_tile_port_grouped().get(side, [])
            lines.append(f"    {side.name}: {len(ports)} ports")

        return "\n".join(lines)

"""Tile class definition for FPGA fabric representation."""

from dataclasses import dataclass, field
from decimal import Decimal
from pathlib import Path
from typing import TYPE_CHECKING

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
    userCLK : bool
        True if the tile uses a clk signal
    switch_matrix : SwitchMatrix
        Switch matrix of the tile, holding its source file, connectivity, and
        config-bit count.
    pin_order_config : dict[Side, PinOrderConfig] | None, optional
        Configuration for pin ordering on each side of the tile. If None, defaults to
        BUS_MAJOR sorting on all sides.
    tileMap : list[list[str | None]] | None, optional
        2D sub-tile layout for composite tiles, or None for simple tiles.

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
    wire_list : list[Wire]
        The list of wires of the tile
    tile_dir : Path
        The path to the tile folder
    partOfSuperTile : bool, optional
        Whether the tile is part of a super tile. Default is False.
    pin_order_config : dict, optional
        Configuration for pin ordering on each side of the tile.
    tileMap : list[list[str | None]] | None, optional
        2D sub-tile layout for composite tiles, or None for simple tiles.
    """

    name: str
    ports_info: list[TilePort]
    bels: list[Bel]
    switch_matrix: SwitchMatrix
    gen_ios: list[Gen_IO]
    withUserCLK: bool = False
    wire_list: list[Wire] = field(default_factory=list)
    tile_dir: Path = Path()
    partOfSuperTile: bool = False
    pin_order_config: dict = field(default_factory=dict)
    tileMap: list[list[str | None]] | None = None  # 2D sub-tile layout

    def __init__(
        self,
        name: str,
        ports: list[TilePort],
        bels: list[Bel],
        tile_dir: Path,
        matrix_dir: Path,
        gen_ios: list[Gen_IO],
        userCLK: bool,
        switch_matrix: SwitchMatrix,
        pin_order_config: dict[Side, "PinOrderConfig"] | None = None,
        tileMap: list[list[str | None]] | None = None,
    ) -> None:
        self.name = name
        self.ports_info = ports
        self.bels = bels
        self.gen_ios = gen_ios
        self.matrix_dir = matrix_dir
        self.withUserCLK = userCLK
        self.switch_matrix = switch_matrix
        self.wire_list = []
        self.tile_dir = tile_dir
        self.tileMap = tileMap

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

    def getWestSidePorts(self) -> list[TilePort]:
        """Get all ports physically located on the west side of the tile.

        Returns
        -------
        list[TilePort]
            List of ports on the west side, excluding NULL ports.
        """
        return [
            p
            for p in self.ports_info
            if p.side_of_tile == Side.WEST and p.name != "NULL"
        ]

    def getEastSidePorts(self) -> list[TilePort]:
        """Get all ports physically located on the east side of the tile.

        Returns
        -------
        list[TilePort]
            List of ports on the east side, excluding NULL ports.
        """
        return [
            p
            for p in self.ports_info
            if p.side_of_tile == Side.EAST and p.name != "NULL"
        ]

    def getNorthSidePorts(self) -> list[TilePort]:
        """Get all ports physically located on the north side of the tile.

        Returns
        -------
        list[TilePort]
            List of ports on the north side, excluding NULL ports.
        """
        return [
            p
            for p in self.ports_info
            if p.side_of_tile == Side.NORTH and p.name != "NULL"
        ]

    def getSouthSidePorts(self) -> list[TilePort]:
        """Get all ports physically located on the south side of the tile.

        Returns
        -------
        list[TilePort]
            List of ports on the south side, excluding NULL ports.
        """
        return [
            p
            for p in self.ports_info
            if p.side_of_tile == Side.SOUTH and p.name != "NULL"
        ]

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
            p for p in self.ports_info if p.side_of_tile == side and p.name != "NULL"
        ]
        if io is not None:
            ports = [p for p in ports if p.io_direction == io]
        return ports

    def get_sjump_ports(self) -> list[TilePort]:
        """Get all ports with SJUMP wire direction.

        SJUMP ports are one-way connections between the tile and a supertile
        BEL: OUTPUT ports exit toward the supertile switch matrix, INPUT ports
        receive results back. Both directions are returned; callers filter by
        ``in_out`` as needed.

        Returns
        -------
        list[TilePort]
            List of SJUMP-direction ports, excluding NULL ports.
        """
        return [
            p
            for p in self.ports_info
            if p.wire_direction == Direction.SJUMP and p.name != "NULL"
        ]

    def get_tile_output_names(self) -> list[str]:
        """Get all output port source names for the tile.

        Returns
        -------
        list[str]
            List of source names for output ports, excluding NULL, JUMP, and
            SJUMP direction ports.
        """
        return [
            p.source_name
            for p in self.ports_info
            if p.source_name != "NULL"
            and p.wire_direction not in (Direction.JUMP, Direction.SJUMP)
            and p.io_direction == IO.OUTPUT
        ]

    @property
    def globalConfigBits(self) -> int:
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
            if p.side_of_tile != side or p.name == "NULL":
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
        north_ports = self.get_port_count(Side.NORTH)
        south_ports = self.get_port_count(Side.SOUTH)
        west_ports = self.get_port_count(Side.WEST)
        east_ports = self.get_port_count(Side.EAST)

        x_io_count = Decimal(max(north_ports, south_ports) + frame_strobe_width)
        min_width_io = (x_io_count * x_pin_thickness_mult + edge_offset) * x_pitch

        y_io_count = Decimal(max(west_ports, east_ports) + frame_data_width)
        min_height_io = (y_io_count * y_pin_thickness_mult + edge_offset) * y_pitch

        return min_width_io, min_height_io

    @property
    def ports(self) -> dict[str, list[TilePort]]:
        """Provide hierarchical view of ports grouped by sub-tile name.

        For simple tiles (no tileMap), all ports are grouped under the tile name.
        For composite tiles, ports are grouped by their sub-tile attribute if
        available, otherwise by the tile name.

        Returns
        -------
        dict[str, list[TilePort]]
            Dictionary mapping sub-tile names to their associated ports.
        """
        if self.tileMap is None:
            return {self.name: self.ports_info}

        result: dict[str, list[TilePort]] = {}
        for port in self.ports_info:
            subtile = getattr(port, "subTile", self.name)
            if subtile not in result:
                result[subtile] = []
            result[subtile].append(port)
        return result

    @property
    def bel_groups(self) -> dict[str, list[Bel]]:
        """Provide hierarchical view of BELs grouped by sub-tile name.

        For simple tiles (no tileMap), all BELs are grouped under the tile name.
        For composite tiles, BELs are grouped by their sub-tile attribute if
        available, otherwise by the tile name.

        Returns
        -------
        dict[str, list[Bel]]
            Dictionary mapping sub-tile names to their associated BELs.
        """
        if self.tileMap is None:
            return {self.name: self.bels}

        result: dict[str, list[Bel]] = {}
        for bel in self.bels:
            subtile = getattr(bel, "subTile", self.name)
            if subtile not in result:
                result[subtile] = []
            result[subtile].append(bel)
        return result

    @property
    def config_bits(self) -> int:
        """Get the total number of configuration bits.

        This is an alias for globalConfigBits for API compatibility.

        Returns
        -------
        int
            Total number of configuration bits for the tile.
        """
        return self.globalConfigBits

    def get_sub_tiles(self) -> list[str]:
        """Get list of all sub-tile names.

        Returns
        -------
        list[str]
            List of sub-tile names. For simple tiles, returns [tile.name].
        """
        if self.tileMap is None:
            return [self.name]
        return [name for row in self.tileMap for name in row if name is not None]

    def get_sub_tile_offset(self, subTile: str) -> tuple[int, int]:
        """Get (x, y) offset for a sub-tile in the tile map.

        Parameters
        ----------
        subTile : str
            Name of the sub-tile to find.

        Returns
        -------
        tuple[int, int]
            (x, y) position in the tile map, with y=0 at the top row.

        Raises
        ------
        ValueError
            If the sub-tile is not found.
        """
        if self.tileMap is None:
            if subTile == self.name:
                return (0, 0)
            raise ValueError(f"Sub-tile '{subTile}' not found in tile '{self.name}'")

        for y, row in enumerate(self.tileMap):
            for x, name in enumerate(row):
                if name == subTile:
                    return (x, y)
        raise ValueError(f"Sub-tile '{subTile}' not found in tileMap")

    def part_of_tile(self, name: str) -> bool:
        """Check if name is part of this tile.

        Parameters
        ----------
        name : str
            Name to check.

        Returns
        -------
        bool
            True if name is a sub-tile of this tile.
        """
        return name in self.get_sub_tiles()

    def is_root_tile(self, name: str) -> bool:
        """Check if name is the root sub-tile (bottom-left).

        Parameters
        ----------
        name : str
            Name to check.

        Returns
        -------
        bool
            True if name is the root sub-tile.
        """
        if self.tileMap is None:
            return name == self.name
        return self.tileMap[-1][0] == name

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

    def get_tile_input_ports(self, subTile: str = "") -> list[TilePort]:
        """Get all input ports, optionally filtered by sub-tile.

        Parameters
        ----------
        subTile : str, optional
            Sub-tile name to filter by. If empty, returns all input ports.

        Returns
        -------
        list[TilePort]
            List of input ports, sorted by name.
        """
        ports = self.ports.get(subTile, []) if subTile else self.ports_info
        return sorted(
            [p for p in ports if p.io_direction == IO.INPUT], key=lambda p: p.name
        )

    def get_tile_output_ports(self, subTile: str = "") -> list[TilePort]:
        """Get all output ports, optionally filtered by sub-tile.

        Parameters
        ----------
        subTile : str, optional
            Sub-tile name to filter by. If empty, returns all output ports.

        Returns
        -------
        list[TilePort]
            List of output ports, sorted by name.
        """
        ports = self.ports.get(subTile, []) if subTile else self.ports_info
        return sorted(
            [p for p in ports if p.io_direction == IO.OUTPUT], key=lambda p: p.name
        )

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
            Side.NORTH: self.getNorthSidePorts(),
            Side.EAST: self.getEastSidePorts(),
            Side.SOUTH: self.getSouthSidePorts(),
            Side.WEST: self.getWestSidePorts(),
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
            "switch_matrix": (
                self.switch_matrix.serialize()
                if hasattr(self.switch_matrix, "serialize")
                else {"config_bits": self.switch_matrix.total_config_bits}
            ),
            "config_bits": self.globalConfigBits,
            "withUserCLK": self.withUserCLK,
            "tileMap": self.tileMap,
            "partOfSuperTile": self.partOfSuperTile,
        }

    def __str__(self) -> str:
        """Return a formatted string representation of the tile.

        Returns
        -------
        str
            Multi-line string describing the tile.
        """
        lines = [f"Tile: {self.name}"]
        lines.append(f"  Config bits: {self.globalConfigBits}")
        lines.append(f"  Switch matrix bits: {self.switch_matrix_config_bits}")
        lines.append(f"  BELs: {len(self.bels)}")
        lines.append(f"  Ports: {len(self.ports_info)}")
        lines.append(f"  User CLK: {self.withUserCLK}")

        if self.tileMap:
            lines.append(f"  Sub-tiles: {self.get_sub_tiles()}")

        # Port summary by side
        lines.append("  Ports by side:")
        for side in [Side.NORTH, Side.EAST, Side.SOUTH, Side.WEST]:
            ports = self.get_tile_port_grouped().get(side, [])
            lines.append(f"    {side.name}: {len(ports)} ports")

        return "\n".join(lines)

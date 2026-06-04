"""Tile class definition for FPGA fabric representation."""

from dataclasses import dataclass, field
from decimal import Decimal
from pathlib import Path
from typing import TYPE_CHECKING

from fabulous.fabric_definition.bel import Bel
from fabulous.fabric_definition.define import IO, Direction, PinSortMode, Side
from fabulous.fabric_definition.gen_io import Gen_IO
from fabulous.fabric_definition.port import TilePort
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
    tileDir : Path
        Directory path for the tile
    switch_matrix : SwitchMatrix
        Switch matrix of the tile, holding its source file, connectivity, and
        config-bit count.
    gen_ios : list[Gen_IO]
        List of general I/O components
    userCLK : bool
        True if the tile uses a clk signal
    pinOrderConfig : dict[Side, PinOrderConfig] | None, optional
        Configuration for pin ordering on each side of the tile. If None, defaults to
        BUS_MAJOR sorting on all sides.

    Attributes
    ----------
    name : str
        The name of the tile
    portsInfo : list[TilePort]
        The list of ports of the tile
    bels: list[Bel]
        The list of BELs of the tile
    switch_matrix : SwitchMatrix
        The switch matrix of the tile
    gen_ios : list[Gen_IO]
        The list of GEN_IOs of the tile
    withUserCLK : bool
        Whether the tile has a userCLK port. Default is False.
    wireList : list[Wire]
        The list of wires of the tile
    tileDir : Path
        The path to the tile folder
    partOfSuperTile : bool, optional
        Whether the tile is part of a super tile. Default is False.
    pinOrderConfig : dict, optional
        Configuration for pin ordering on each side of the tile.
    """

    name: str
    portsInfo: list[TilePort]
    bels: list[Bel]
    switch_matrix: SwitchMatrix
    gen_ios: list[Gen_IO]
    withUserCLK: bool = False
    wireList: list[Wire] = field(default_factory=list)
    tileDir: Path = Path()
    partOfSuperTile: bool = False
    pinOrderConfig: dict = field(default_factory=dict)

    def __init__(
        self,
        name: str,
        ports: list[TilePort],
        bels: list[Bel],
        tileDir: Path,
        switch_matrix: SwitchMatrix,
        gen_ios: list[Gen_IO],
        userCLK: bool,
        pinOrderConfig: dict[Side, "PinOrderConfig"] | None = None,
    ) -> None:
        self.name = name
        self.portsInfo = ports
        self.bels = bels
        self.gen_ios = gen_ios
        self.switch_matrix = switch_matrix
        self.withUserCLK = userCLK
        self.wireList = []
        self.tileDir = tileDir

        if pinOrderConfig is None:
            from fabulous.fabric_generator.gds_generator.gen_io_pin_config_yaml import (
                PinOrderConfig,
            )

            self.pinOrderConfig = {
                Side.NORTH: PinOrderConfig(sort_mode=PinSortMode.BUS_MAJOR),
                Side.EAST: PinOrderConfig(sort_mode=PinSortMode.BUS_MAJOR),
                Side.SOUTH: PinOrderConfig(sort_mode=PinSortMode.BUS_MAJOR),
                Side.WEST: PinOrderConfig(sort_mode=PinSortMode.BUS_MAJOR),
            }
        else:
            self.pinOrderConfig = pinOrderConfig

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
            for p in self.portsInfo
            if p.side_of_tile == Side.WEST and not p.name_is_null
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
            for p in self.portsInfo
            if p.side_of_tile == Side.EAST and not p.name_is_null
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
            for p in self.portsInfo
            if p.side_of_tile == Side.NORTH and not p.name_is_null
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
            for p in self.portsInfo
            if p.side_of_tile == Side.SOUTH and not p.name_is_null
        ]

    def getNorthPorts(self, io: IO) -> list[TilePort]:
        """Get all ports with north wire direction filtered by I/O type.

        Parameters
        ----------
        io : IO
            The I/O direction to filter by (INPUT or OUTPUT).

        Returns
        -------
        list[TilePort]
            List of north-direction ports with specified I/O type, excluding NULL ports.
        """
        return [
            p
            for p in self.portsInfo
            if p.wire_direction == Direction.NORTH
            and not p.name_is_null
            and p.io_direction == io
        ]

    def getSouthPorts(self, io: IO) -> list[TilePort]:
        """Get all ports with south wire direction filtered by I/O type.

        Parameters
        ----------
        io : IO
            The I/O direction to filter by (INPUT or OUTPUT).

        Returns
        -------
        list[TilePort]
            List of south-direction ports with specified I/O type, excluding NULL ports.
        """
        return [
            p
            for p in self.portsInfo
            if p.wire_direction == Direction.SOUTH
            and not p.name_is_null
            and p.io_direction == io
        ]

    def getEastPorts(self, io: IO) -> list[TilePort]:
        """Get all ports with east wire direction filtered by I/O type.

        Parameters
        ----------
        io : IO
            The I/O direction to filter by (INPUT or OUTPUT).

        Returns
        -------
        list[TilePort]
            List of east-direction ports with specified I/O type, excluding NULL ports.
        """
        return [
            p
            for p in self.portsInfo
            if p.wire_direction == Direction.EAST
            and not p.name_is_null
            and p.io_direction == io
        ]

    def getWestPorts(self, io: IO) -> list[TilePort]:
        """Get all ports with west wire direction filtered by I/O type.

        Parameters
        ----------
        io : IO
            The I/O direction to filter by (INPUT or OUTPUT).

        Returns
        -------
        list[TilePort]
            List of west-direction ports with specified I/O type, excluding NULL ports.
        """
        return [
            p
            for p in self.portsInfo
            if p.wire_direction == Direction.WEST
            and not p.name_is_null
            and p.io_direction == io
        ]

    def get_sjump_ports(self) -> list[TilePort]:
        """Get all ports with SJUMP wire direction.

        SJUMP ports are one-way connections between the tile and a supertile
        BEL: OUTPUT ports exit toward the supertile switch matrix, INPUT ports
        receive results back. Both directions are returned; callers filter by
        `in_out` as needed.

        Returns
        -------
        list[TilePort]
            List of SJUMP-direction ports, excluding NULL ports.
        """
        return [
            p
            for p in self.portsInfo
            if p.wire_direction == Direction.SJUMP and not p.name_is_null
        ]

    def getTileInputNames(self) -> list[str]:
        """Get all input port destination names for the tile.

        Returns
        -------
        list[str]
            List of destination names for input ports, excluding NULL, JUMP,
            and SJUMP direction ports.
        """
        return [
            p.destination_name
            for p in self.portsInfo
            if p.destination_name != "NULL"
            and p.wire_direction not in (Direction.JUMP, Direction.SJUMP)
            and p.is_input
        ]

    def getTileOutputNames(self) -> list[str]:
        """Get all output port source names for the tile.

        Returns
        -------
        list[str]
            List of source names for output ports, excluding NULL, JUMP, and
            SJUMP direction ports.
        """
        return [
            p.source_name
            for p in self.portsInfo
            if p.source_name != "NULL"
            and p.wire_direction not in (Direction.JUMP, Direction.SJUMP)
            and p.is_output
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
        for p in self.portsInfo:
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

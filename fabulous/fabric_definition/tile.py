"""Tile class definition for FPGA fabric representation."""

import itertools
from dataclasses import dataclass, field
from decimal import Decimal
from pathlib import Path
from typing import TYPE_CHECKING

from fabulous.fabric_definition.bel import Bel
from fabulous.fabric_definition.define import IO, Direction, PinSortMode, Side
from fabulous.fabric_definition.gen_io import Gen_IO
from fabulous.fabric_definition.port import Port
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
    ports : list[Port]
        List of ports for the tile
    bels : list[Bel]
        List of Basic Elements of Logic (BELs) in the tile
    tileDir : Path
        Directory path for the tile
    matrixDir : Path
        Directory path for the tile matrix
    gen_ios : list[Gen_IO]
        List of general I/O components
    userCLK : bool
        True if the tile uses a clk signal
    configBit : int, optional
        Number of configuration bits for the switch matrix. Default is 0.
    pinOrderConfig : dict[Side, PinOrderConfig] | None, optional
        Configuration for pin ordering on each side of the tile. If None, defaults to
        BUS_MAJOR sorting on all sides.

    Attributes
    ----------
    name : str
        The name of the tile
    portsInfo : list[Port]
        The list of ports of the tile
    bels: list[Bel]
        The list of BELs of the tile
    matrixDir : Path
        The directory of the tile matrix
    matrixConfigBits : int
        The number of config bits the tile switch matrix has
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
    portsInfo: list[Port]
    bels: list[Bel]
    matrixDir: Path
    matrixConfigBits: int
    gen_ios: list[Gen_IO]
    withUserCLK: bool = False
    wireList: list[Wire] = field(default_factory=list)
    tileDir: Path = Path()
    partOfSuperTile: bool = False
    pinOrderConfig: dict = field(default_factory=dict)

    def __init__(
        self,
        name: str,
        ports: list[Port],
        bels: list[Bel],
        tileDir: Path,
        matrixDir: Path,
        gen_ios: list[Gen_IO],
        userCLK: bool,
        configBit: int = 0,
        pinOrderConfig: dict[Side, "PinOrderConfig"] | None = None,
    ) -> None:
        self.name = name
        self.portsInfo = ports
        self.bels = bels
        self.gen_ios = gen_ios
        self.matrixDir = matrixDir
        self.withUserCLK = userCLK
        self.matrixConfigBits = configBit
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

    def getWestSidePorts(self) -> list[Port]:
        """Get all ports physically located on the west side of the tile.

        Returns
        -------
        list[Port]
            List of ports on the west side, excluding NULL ports.
        """
        return [
            p for p in self.portsInfo if p.sideOfTile == Side.WEST and p.name != "NULL"
        ]

    def getEastSidePorts(self) -> list[Port]:
        """Get all ports physically located on the east side of the tile.

        Returns
        -------
        list[Port]
            List of ports on the east side, excluding NULL ports.
        """
        return [
            p for p in self.portsInfo if p.sideOfTile == Side.EAST and p.name != "NULL"
        ]

    def getNorthSidePorts(self) -> list[Port]:
        """Get all ports physically located on the north side of the tile.

        Returns
        -------
        list[Port]
            List of ports on the north side, excluding NULL ports.
        """
        return [
            p for p in self.portsInfo if p.sideOfTile == Side.NORTH and p.name != "NULL"
        ]

    def getSouthSidePorts(self) -> list[Port]:
        """Get all ports physically located on the south side of the tile.

        Returns
        -------
        list[Port]
            List of ports on the south side, excluding NULL ports.
        """
        return [
            p for p in self.portsInfo if p.sideOfTile == Side.SOUTH and p.name != "NULL"
        ]

    def getNorthPorts(self, io: IO) -> list[Port]:
        """Get all ports with north wire direction filtered by I/O type.

        Parameters
        ----------
        io : IO
            The I/O direction to filter by (INPUT or OUTPUT).

        Returns
        -------
        list[Port]
            List of north-direction ports with specified I/O type, excluding NULL ports.
        """
        return [
            p
            for p in self.portsInfo
            if p.wireDirection == Direction.NORTH and p.name != "NULL" and p.inOut == io
        ]

    def getSouthPorts(self, io: IO) -> list[Port]:
        """Get all ports with south wire direction filtered by I/O type.

        Parameters
        ----------
        io : IO
            The I/O direction to filter by (INPUT or OUTPUT).

        Returns
        -------
        list[Port]
            List of south-direction ports with specified I/O type, excluding NULL ports.
        """
        return [
            p
            for p in self.portsInfo
            if p.wireDirection == Direction.SOUTH and p.name != "NULL" and p.inOut == io
        ]

    def getEastPorts(self, io: IO) -> list[Port]:
        """Get all ports with east wire direction filtered by I/O type.

        Parameters
        ----------
        io : IO
            The I/O direction to filter by (INPUT or OUTPUT).

        Returns
        -------
        list[Port]
            List of east-direction ports with specified I/O type, excluding NULL ports.
        """
        return [
            p
            for p in self.portsInfo
            if p.wireDirection == Direction.EAST and p.name != "NULL" and p.inOut == io
        ]

    def getWestPorts(self, io: IO) -> list[Port]:
        """Get all ports with west wire direction filtered by I/O type.

        Parameters
        ----------
        io : IO
            The I/O direction to filter by (INPUT or OUTPUT).

        Returns
        -------
        list[Port]
            List of west-direction ports with specified I/O type, excluding NULL ports.
        """
        return [
            p
            for p in self.portsInfo
            if p.wireDirection == Direction.WEST and p.name != "NULL" and p.inOut == io
        ]

    def getTileInputNames(self) -> list[str]:
        """Get all input port destination names for the tile.

        Returns
        -------
        list[str]
            List of destination names for input ports, excluding NULL and
            JUMP direction ports.
        """
        return [
            p.destinationName
            for p in self.portsInfo
            if p.destinationName != "NULL"
            and p.wireDirection != Direction.JUMP
            and p.inOut == IO.INPUT
        ]

    def getTileOutputNames(self) -> list[str]:
        """Get all output port source names for the tile.

        Returns
        -------
        list[str]
            List of source names for output ports, excluding NULL and
            JUMP direction ports.
        """
        return [
            p.sourceName
            for p in self.portsInfo
            if p.sourceName != "NULL"
            and p.wireDirection != Direction.JUMP
            and p.inOut == IO.OUTPUT
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
        ret = self.matrixConfigBits

        for b in self.bels:
            ret += b.configBit

        return ret

    def get_port_count(self, side: Side) -> int:
        """Count total number of expanded ports on a given side of the tile.

        Parameters
        ----------
        side : Side
            The side of the tile to count ports for.

        Returns
        -------
        int
            Total number of expanded ports on the given side.
        """
        ports = [p for p in self.portsInfo if p.sideOfTile == side and p.name != "NULL"]
        return len(
            list(
                itertools.chain.from_iterable(
                    [
                        list(itertools.chain.from_iterable(p.expandPortInfo("all")))
                        for p in ports
                    ]
                )
            )
        )

    def get_min_die_area(
        self,
        x_pitch: Decimal,
        y_pitch: Decimal,
        x_pin_thickness_mult: Decimal,
        y_pin_thickness_mult: Decimal,
        x_spacing: Decimal,
        y_spacing: Decimal,
        frame_data_width: int = 32,
        frame_strobe_width: int = 20,
    ) -> tuple[Decimal, Decimal]:
        """Calculate minimum tile dimensions based on IO pin density.

        For this tile, calculates the minimum physical width and height
        required to accommodate all IO pins at the PDK's track pitch.

        Parameters
        ----------
        x_pitch : Decimal
            Horizontal pitch between tracks (DBU).
        y_pitch : Decimal
            Vertical pitch between tracks (DBU).
        x_pin_thickness_mult : Decimal
            Pin thickness multiplier in the horizontal direction.
        y_pin_thickness_mult : Decimal
            Pin thickness multiplier in the vertical direction.
        x_spacing : Decimal
            Pin spacing in the horizontal direction (DBU).
        y_spacing : Decimal
            Pin spacing in the vertical direction (DBU).
        frame_data_width : int, optional
            Frame data width, by default 32.
        frame_strobe_width : int, optional
            Frame strobe width, by default 20.

        Returns
        -------
        tuple[Decimal, Decimal]
            (min_width, min_height) where:
            - min_width: minimum width needed for north/south edge IO pins
            - min_height: minimum height needed for west/east edge IO pins

        Notes
        -----
        The minimum dimensions are calculated as:
        - min_width = max(north_pins, south_pins) * x_pitch
        - min_height = max(west_pins, east_pins) * y_pitch

        These constraints prevent the NLP solver from suggesting dimensions
        that are physically impossible due to IO pin spacing requirements.
        """
        # Count ports on each physical side
        north_ports = self.get_port_count(Side.NORTH)
        south_ports = self.get_port_count(Side.SOUTH)
        west_ports = self.get_port_count(Side.WEST)
        east_ports = self.get_port_count(Side.EAST)

        # Min width constrained by north/south edges
        x_io_count = Decimal(max(north_ports, south_ports) + frame_strobe_width)
        min_width_io = (
            x_io_count * (x_pitch * x_pin_thickness_mult)
            + x_spacing * x_io_count
            + 2 * x_spacing
        )
        # Min height constrained by west/east edges
        y_io_count = Decimal(max(west_ports, east_ports) + frame_data_width)
        min_height_io = (
            y_io_count * (y_pitch * y_pin_thickness_mult)
            + y_spacing * y_io_count
            + 2 * y_spacing
        )
        return min_width_io, min_height_io

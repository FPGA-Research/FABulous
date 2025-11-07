"""Fabric definition enumerations and constants.

This module defines various enumerations used throughout FABulous for fabric definition,
including I/O types, directions, sides, and configuration modes.
"""

from decimal import Decimal
from enum import Enum, StrEnum
from typing import NamedTuple


class IO(Enum):
    """Enumeration for I/O port directions.

    Defines the direction of ports in fabric components:
    - INPUT: Input port
    - OUTPUT: Output port
    - INOUT: Bidirectional port
    - NULL: No connection/unused port
    """

    INPUT = "INPUT"
    OUTPUT = "OUTPUT"
    INOUT = "INOUT"
    NULL = "NULL"


class Direction(Enum):
    """Enumeration for wire and port directions in the fabric.

    Defines the directional flow of wires and ports:
    - NORTH: Northward direction
    - SOUTH: Southward direction
    - EAST: Eastward direction
    - WEST: Westward direction
    - JUMP: Local connections within a tile
    """

    NORTH = "NORTH"
    SOUTH = "SOUTH"
    EAST = "EAST"
    WEST = "WEST"
    JUMP = "JUMP"


class Side(StrEnum):
    """Enumeration for tile sides and placement.

    Defines the physical sides of tiles in the fabric:
    - NORTH: North side of tile
    - SOUTH: South side of tile
    - EAST: East side of tile
    - WEST: West side of tile
    - ANY: Any side (no specific placement)
    """

    NORTH = "N"
    SOUTH = "S"
    EAST = "E"
    WEST = "W"
    ANY = "ANY"


class MultiplexerStyle(Enum):
    """Enumeration for multiplexer implementation styles.

    Defines how multiplexers are implemented in the fabric:
    - CUSTOM:  Custom multiplexer implementations which instantiate a
               custom multiplexer layout.
    - GENERIC: Generic/standard multiplexer implementations which uses behavioral
               modeling and will use standard cells in the physical implementation.
    """

    CUSTOM = "CUSTOM"
    GENERIC = "GENERIC"


class ConfigBitMode(Enum):
    """Enumeration for configuration bit access modes.

    Defines how configuration bits are accessed and programmed:
    - FRAME_BASED: Frame-based configuration
    - FLIPFLOP_CHAIN: Flip-flop chain configuration
    """

    FRAME_BASED = "FRAME_BASED"
    FLIPFLOP_CHAIN = "FLIPFLOP_CHAIN"


class HDLType(StrEnum):
    """Enumeration for HDLs supported by FABulous.

    This enumeration includes the following values:
    - VERILOG: Verilog HDL
    - VHDL: VHDL HDL
    - SYSTEM_VERILOG: SystemVerilog HDL
    """

    VERILOG = "verilog"
    VHDL = "vhdl"
    SYSTEM_VERILOG = "system_verilog"


class FABulousAttribute(StrEnum):
    """Enumeration for FABulous attributes in the HDL.

    This enumeration includes the following values:
    - EXTERNAL: External attribute
    - SHARED_PORT: Shared port attribute
    - GLOBAL: Global attribute
    - USER_CLK: User clock attribute
    - CONFIG_BIT: Configuration bit attribute
    """

    EXTERNAL = "EXTERNAL"
    SHARED_PORT = "SHARED_PORT"
    GLOBAL = "GLOBAL"
    USER_CLK = "USER_CLK"
    CONFIG_BIT = "CONFIG_BIT"


class PinSortMode(StrEnum):
    """Enumeration for pin sorting modes."""

    BUS_MAJOR = "bus_major"
    BIT_MINOR = "bit_minor"
    CUSTOM = "custom"


class TileSize(NamedTuple):
    """Named tuple representing the size of a tile."""

    width: Decimal
    height: Decimal

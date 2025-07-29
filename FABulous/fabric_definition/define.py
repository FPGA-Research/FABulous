from enum import Enum, StrEnum


class IO(Enum):
    INPUT = "INPUT"
    OUTPUT = "OUTPUT"
    INOUT = "INOUT"
    NULL = "NULL"


class Direction(Enum):
    NORTH = "NORTH"
    SOUTH = "SOUTH"
    EAST = "EAST"
    WEST = "WEST"
    JUMP = "JUMP"


class Side(Enum):
    NORTH = "NORTH"
    SOUTH = "SOUTH"
    EAST = "EAST"
    WEST = "WEST"
    ANY = "ANY"


class MultiplexerStyle(Enum):
    CUSTOM = "CUSTOM"
    GENERIC = "GENERIC"


class ConfigBitMode(Enum):
    FRAME_BASED = "FRAME_BASED"
    FLIPFLOP_CHAIN = "FLIPFLOP_CHAIN"


class HDLType(StrEnum):
    VERILOG = "verilog"
    VHDL = "vhdl"
    SYSTEM_VERILOG = "system_verilog"


class FABulousAttribute(StrEnum):
    EXTERNAL = "EXTERNAL"
    SHARED_PORT = "SHARED_PORT"
    GLOBAL = "GLOBAL"
    USER_CLK = "USER_CLK"
    CONFIG_BIT = "CONFIG_BIT"

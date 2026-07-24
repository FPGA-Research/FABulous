"""Port class hierarchy for FPGA fabric.

This module contains the port class hierarchy for representing different types of ports
in the FPGA fabric:
- Port: Base class for all port types
- TilePort: Port on a tile with side and termination information
- BelPort: Port on a BEL (Basic Element of Logic)
- SlicedPort: A sliced portion of another port
- SharedPort: A port shared between multiple BELs
- ConfigPort: A configuration port with features
"""

from __future__ import annotations

from functools import total_ordering
from typing import TYPE_CHECKING

from fabulous.fabric_definition.define import (
    IO,
    Direction,
    FeatureType,
    FeatureValue,
    Side,
)

if TYPE_CHECKING:
    from fabulous.fabric_definition.tile import Tile

NULL_PORT_NAME = "NULL"


class Port:
    """Base class for all port types.

    Parameters
    ----------
    name : str
        The name of the port.
    io_direction : IO
        The I/O direction (INPUT, OUTPUT, INOUT).
    width : int
        The bit width of the port.
    is_clock : bool
        Whether the port carries a clock. Defaults to False.
    is_global : bool
        Whether the port is driven by a fabric-wide signal, such as the global
        user clock, rather than a locally generated one. Defaults to False.
    net : str
        The net the port belongs to. Defaults to "", the global net.

    Raises
    ------
    ValueError
        If `width` is not greater than 0.
    TypeError
        If `io_direction` is not an `IO`, `name` is not a `str`, or
        `is_clock` or `is_global` is not a `bool`.
    """

    _name: str
    _io_direction: IO
    _width: int
    _is_clock: bool
    _is_global: bool
    _net: str

    def __init__(
        self,
        name: str,
        io_direction: IO,
        width: int,
        is_clock: bool = False,
        is_global: bool = False,
        net: str = "",
    ) -> None:
        self._name = name
        self._io_direction = io_direction
        self._width = width
        self._is_clock = is_clock
        self._is_global = is_global
        self._net = net

        if self.width <= 0:
            raise ValueError(f"Width must be greater than 0, got {self.width}")
        if not isinstance(self.io_direction, IO):
            raise TypeError(
                f"io_direction must be an instance of IO, got {type(self.io_direction)}"
            )
        if not isinstance(self._name, str):
            raise TypeError(f"name must be a string, got {type(self._name)}")
        if not isinstance(self._is_clock, bool):
            raise TypeError(f"is_clock must be a bool, got {type(self._is_clock)}")
        if not isinstance(self._is_global, bool):
            raise TypeError(f"is_global must be a bool, got {type(self._is_global)}")

    def __repr__(self) -> str:
        """Return a string representation of the port."""
        return f"Port({self.io_direction.value} {self.name}[{self.width - 1}:0])"

    @property
    def name(self) -> str:
        """Return the port name."""
        return self._name

    @property
    def io_direction(self) -> IO:
        """Return the I/O direction."""
        return self._io_direction

    @property
    def width(self) -> int:
        """Return the bit width."""
        return self._width

    @property
    def is_input(self) -> bool:
        """Whether the port is an input. An INOUT port is not an input."""
        return self._io_direction == IO.INPUT

    @property
    def is_output(self) -> bool:
        """Whether the port is an output. An INOUT port is not an output."""
        return self._io_direction == IO.OUTPUT

    @property
    def is_inout(self) -> bool:
        """Whether the port is bidirectional."""
        return self._io_direction == IO.INOUT

    @property
    def name_is_null(self) -> bool:
        """Whether the port name is the NULL placeholder.

        Only the port's own name is considered. A wire's `source_name` and
        `destination_name` are NULL independently of it and of each other.
        """
        return self._name == NULL_PORT_NAME

    @property
    def is_clock(self) -> bool:
        """Whether the port carries a clock."""
        return self._is_clock

    @property
    def is_global(self) -> bool:
        """Whether the port is driven by a fabric-wide signal."""
        return self._is_global

    @property
    def net(self) -> str:
        """The net the port belongs to; "" is the global net."""
        return self._net

    def expand(self) -> list[str]:
        """Expand the port name into a list of strings based on the width.

        Returns
        -------
        list[str]
            A list of expanded port names.
        """
        if self.width == 1:
            return [f"{self.name}"]
        return [f"{self.name}[{i}]" for i in range(self.width)]

    def __eq__(self, other: object, /) -> bool:
        """Check equality with another object."""
        if other is None or not isinstance(other, Port):
            return False
        return self is other

    def __hash__(self) -> int:
        """Return the hash value."""
        return id(self)

    def serialize(self) -> dict:
        """Serialize the port to a dictionary."""
        return {
            "name": self.name,
            "io_direction": self.io_direction.value,
            "width": self.width,
            "is_clock": self.is_clock,
            "is_global": self.is_global,
            "net": self.net,
        }


@total_ordering
class TilePort(Port):
    """TilePort represents a port on a tile with a side and termination status.

    It is an immutable and comparable class. When sorting a list of TilePort instances,
    the order is determined first by the side of the tile in order of
    [north, east, south, west] then by the IO type in the order of
    [output, input, inout].

    Parameters
    ----------
    name : str
        The name of the port.
    io_direction : IO
        The I/O direction (INPUT, OUTPUT, INOUT).
    width : int
        The bit width of the port.
    side_of_tile : Side
        The side of the tile where the port is located.
    term : bool
        Whether the port is a termination port. Defaults to False.
    tile : Tile | None
        The tile this port belongs to. Set once at construction and read-only
        thereafter. Defaults to None, leaving the port unattached.
    wire_direction : Direction | None
        The wire direction; defaults to `Direction.JUMP` when None.
    source_name : str
        The source name of the wire connection.
    x_offset : int
        The X-offset for wire routing.
    y_offset : int
        The Y-offset for wire routing.
    destination_name : str
        The destination name of the wire connection.
    wire_count : int
        The number of wires.
    """

    _side_of_tile: Side
    _term: bool
    _tile: Tile | None
    # Backward compatibility fields for wire routing
    _wire_direction: Direction
    _source_name: str
    _x_offset: int
    _y_offset: int
    _destination_name: str
    _wire_count: int

    def __init__(
        self,
        name: str,
        io_direction: IO,
        width: int,
        side_of_tile: Side,
        term: bool = False,
        tile: Tile | None = None,
        # Backward compatibility parameters
        wire_direction: Direction | None = None,
        source_name: str = "",
        x_offset: int = 0,
        y_offset: int = 0,
        destination_name: str = "",
        wire_count: int = 1,
    ) -> None:
        super().__init__(name, io_direction, width)
        self._side_of_tile = side_of_tile
        self._term = term
        self._tile = tile
        # Backward compatibility
        self._wire_direction = (
            wire_direction if wire_direction is not None else Direction.JUMP
        )
        self._source_name = source_name
        self._x_offset = x_offset
        self._y_offset = y_offset
        self._destination_name = destination_name
        self._wire_count = wire_count

    __order = {Side.NORTH: 0, Side.EAST: 1, Side.SOUTH: 2, Side.WEST: 3, Side.ANY: 4}
    __io = {IO.OUTPUT: 0, IO.INPUT: 1, IO.INOUT: 2}

    @property
    def side_of_tile(self) -> Side:
        """The side of the tile where the port is located."""
        return self._side_of_tile

    @property
    def term(self) -> bool:
        """Whether the port is a termination port."""
        return self._term

    @property
    def tile(self) -> Tile | None:
        """The tile this port belongs to, or None while the port is unattached."""
        return self._tile

    # Backward compatibility properties
    @property
    def wire_direction(self) -> Direction:
        """Wire direction (backward compatibility)."""
        return self._wire_direction

    @property
    def source_name(self) -> str:
        """Source name (backward compatibility)."""
        return self._source_name

    @property
    def x_offset(self) -> int:
        """X-offset (backward compatibility)."""
        return self._x_offset

    @property
    def y_offset(self) -> int:
        """Y-offset (backward compatibility)."""
        return self._y_offset

    @property
    def destination_name(self) -> str:
        """Destination name (backward compatibility)."""
        return self._destination_name

    @property
    def wire_count(self) -> int:
        """Wire count (backward compatibility)."""
        return self._wire_count

    def __repr__(self) -> str:
        """Return a string representation of the TilePort."""
        name = f"{self.side_of_tile}"
        return (
            f"TilePort({{{name}}} {self.io_direction.value} "
            f"{self.name}[{self.width - 1}:0])"
        )

    @property
    def _sort_key(self) -> tuple[int, int]:
        """The [north, east, south, west] then [output, input, inout] sort key."""
        return (self.__order[self.side_of_tile], self.__io[self.io_direction])

    def __lt__(self, other: object, /) -> bool:
        """Less than comparison.

        `total_ordering` derives the remaining comparisons from this and the
        identity-based `__eq__` inherited from `Port`, so two distinct ports of
        equal rank compare as neither less than nor equal to each other.
        """
        if not isinstance(other, TilePort):
            raise TypeError(f"Cannot compare {self} with {other}")
        return self._sort_key < other._sort_key

    def serialize(self) -> dict:
        """Serialize the tile port to a dictionary."""
        return super().serialize() | {
            "side_of_tile": self.side_of_tile.value,
            "term": self.term,
            "tile": self.tile.name if self.tile is not None else None,
            "wire_direction": self.wire_direction.value,
            "source_name": self.source_name,
            "x_offset": self.x_offset,
            "y_offset": self.y_offset,
            "destination_name": self.destination_name,
            "wire_count": self.wire_count,
        }

    # Backward compatibility methods from old Port class
    def get_port_regex(self, indexed: bool = False, prefix: str = "") -> str:
        """Expand port information to individual wire names.

        Generates a regex expression for this port, accounting for wire count and
        offset calculations.

        Parameters
        ----------
        indexed : bool, optional
            If True, wire names use bracket notation (e.g., `port[0]`).
            If False, wire names use simple concatenation (e.g., `port0`).
            Defaults to False.
        prefix : str, optional
            A prefix to prepend to the port name, by default "".

        Returns
        -------
        str
            A regex expression matching the port's wire names.
        """
        total_wires = (abs(self.x_offset) + abs(self.y_offset)) * self.wire_count

        if total_wires == 1 and not self.name_is_null:
            return f"{prefix}{self.name}"
        if indexed:
            return rf"{prefix}{self.name}\[\d+\]"
        return rf"{prefix}{self.name}\d+"

    def expand_port_info_by_name(
        self, indexed: bool = False, prefix: str = "", escape: bool = False
    ) -> list[str]:
        """Expand port information to individual wire names.

        Generates a list of individual wire names for this port, accounting for
        wire count and offset calculations. For termination ports (NULL), the
        wire count is multiplied by the Manhattan distance.

        Parameters
        ----------
        indexed : bool, optional
            If True, wire names use bracket notation (e.g., `port[0]`).
            If False, wire names use simple concatenation (e.g., `port0`).
            Defaults to False.
        prefix : str, optional
            A prefix to prepend to the port name, by default "".
        escape : bool, optional
            If True, escape special characters in the port names (e.g., for regex),
            by default False.

        Returns
        -------
        list[str]
            List of individual wire names for this port.
        """
        if self.source_name == "NULL" or self.destination_name == "NULL":
            count = (abs(self.x_offset) + abs(self.y_offset)) * self.wire_count
        else:
            count = self.wire_count

        if not indexed:
            return [
                f"{prefix}{self.name}{i}" for i in range(count) if not self.name_is_null
            ]

        if escape:
            return [
                rf"{prefix}{self.name}\[{i}\]"
                for i in range(count)
                if not self.name_is_null
            ]
        return [
            f"{prefix}{self.name}[{i}]" for i in range(count) if not self.name_is_null
        ]

    def expand_port_info_by_name_top(
        self, indexed: bool = False, prefix: str = "", escape: bool = False
    ) -> list[str]:
        """Expand port information for top-level connections.

        Similar to expand_port_info_by_name but specifically for top-level tile
        connections. The start index is calculated differently to handle
        the top slice of wires for routing fabric connections.

        Parameters
        ----------
        indexed : bool, optional
            If True, wire names use bracket notation (e.g., `port[0]`).
            If False, wire names use simple concatenation (e.g., `port0`).
            Defaults to False.
        prefix : str, optional
            A prefix to prepend to the port name, by default "".
        escape : bool, optional
            If True, escape special characters in the port names (e.g., for regex),
            by default False.

        Returns
        -------
        list[str]
            List of individual wire names for top-level connections.
        """
        if self.source_name == "NULL" or self.destination_name == "NULL":
            startIndex = 0
            total_wires = (abs(self.x_offset) + abs(self.y_offset)) * self.wire_count
        else:
            startIndex = (
                (abs(self.x_offset) + abs(self.y_offset)) - 1
            ) * self.wire_count
            total_wires = (abs(self.x_offset) + abs(self.y_offset)) * self.wire_count

        if not indexed:
            return [
                f"{prefix}{self.name}{i}"
                for i in range(startIndex, total_wires)
                if not self.name_is_null
            ]

        if escape:
            return [
                rf"{prefix}{self.name}\[{i}\]"
                for i in range(startIndex, total_wires)
                if not self.name_is_null
            ]
        return [
            f"{prefix}{self.name}[{i}]"
            for i in range(startIndex, total_wires)
            if not self.name_is_null
        ]

    def expand_port_info(
        self, mode: str = "SwitchMatrix"
    ) -> tuple[list[str], list[str]]:
        """Expand the port information to the individual bit signal.

        If 'Indexed' is in the mode, then brackets are added to the signal name.

        Parameters
        ----------
        mode : str, optional
            Mode for expansion. Defaults to "SwitchMatrix".
            Possible modes are 'all', 'allIndexed', 'Top', 'TopIndexed', 'AutoTop',
            'AutoTopIndexed', 'SwitchMatrix', 'SwitchMatrixIndexed', 'AutoSwitchMatrix',
            'AutoSwitchMatrixIndexed'

        Returns
        -------
        tuple[list[str], list[str]]
            A tuple of two lists. The first list contains the source names of the ports
            and the second list contains the destination names of the ports.
        """
        inputs, outputs = [], []
        thisRange = 0
        openIndex = ""
        closeIndex = ""

        if "Indexed" in mode:
            openIndex = "("
            closeIndex = ")"

        # range (wires-1 downto 0) as connected to the switch matrix
        if mode == "SwitchMatrix" or mode == "SwitchMatrixIndexed":
            thisRange = self.wire_count
        elif mode == "AutoSwitchMatrix" or mode == "AutoSwitchMatrixIndexed":
            if self.source_name == "NULL" or self.destination_name == "NULL":
                # the following line connects all wires to the switch matrix in the case
                # one port is NULL (typically termination)
                thisRange = (abs(self.x_offset) + abs(self.y_offset)) * self.wire_count
            else:
                # the following line connects all bottom wires to the switch matrix in
                # the case begin and end ports are used
                thisRange = self.wire_count
        # range ((wires*distance)-1 downto 0) as connected to the tile top
        elif mode in [
            "all",
            "allIndexed",
            "Top",
            "TopIndexed",
            "AutoTop",
            "AutoTopIndexed",
        ]:
            thisRange = (abs(self.x_offset) + abs(self.y_offset)) * self.wire_count

        # the following three lines are needed to get the top line[wires] that
        # are actually the connection from a switch matrix to the routing fabric
        startIndex = 0
        if mode in ["Top", "TopIndexed"]:
            startIndex = (
                (abs(self.x_offset) + abs(self.y_offset)) - 1
            ) * self.wire_count

        elif mode in ["AutoTop", "AutoTopIndexed"]:
            if self.source_name == "NULL" or self.destination_name == "NULL":
                # in case one port is NULL, then the all the other port wires get
                # connected to the switch matrix.
                startIndex = 0
            else:
                # "normal" case as for the CLBs
                startIndex = (
                    (abs(self.x_offset) + abs(self.y_offset)) - 1
                ) * self.wire_count
        if startIndex == thisRange:
            thisRange = 1

        for i in range(startIndex, thisRange):
            if self.source_name != "NULL":
                inputs.append(f"{self.source_name}{openIndex}{str(i)}{closeIndex}")

            if self.destination_name != "NULL":
                outputs.append(
                    f"{self.destination_name}{openIndex}{str(i)}{closeIndex}"
                )
        return inputs, outputs


class SlicedPort(Port):
    """A port that represents a slice of another port.

    The range is written `high downto low`, following VHDL: both endpoints are
    inclusive 0-based indices into the original port's own expansion, and `high`
    selects the most significant bit. `expand()` still lists bits least
    significant first, matching `Port.expand()`.

    Parameters
    ----------
    original_port : Port
        The original port being sliced.
    high : int
        The most significant bit index of the slice, inclusive.
    low : int
        The least significant bit index of the slice, inclusive.

    Raises
    ------
    ValueError
        If `low` is negative, if `high` is below `low`, or if `high` falls
        outside the original port's width.
    """

    _high: int
    _low: int
    _original_port: Port

    def __init__(
        self,
        original_port: Port,
        high: int,
        low: int,
    ) -> None:
        if low < 0:
            raise ValueError(f"Slice low index must not be negative, got {low}")
        if high < low:
            raise ValueError(
                f"Slice must be written high downto low, got high={high} low={low}"
            )
        if high >= original_port.width:
            raise ValueError(
                f"Slice high index {high} is outside the width of "
                f"{original_port.name} ({original_port.width} bits)"
            )
        super().__init__(
            original_port.name,
            original_port.io_direction,
            high - low + 1,
        )
        self._original_port = original_port
        self._high = high
        self._low = low

    @property
    def original_port(self) -> Port:
        """The original port being sliced."""
        return self._original_port

    @property
    def high(self) -> int:
        """The most significant bit index of the slice, inclusive."""
        return self._high

    @property
    def low(self) -> int:
        """The least significant bit index of the slice, inclusive."""
        return self._low

    def expand(self) -> list[str]:
        """Expand the slice into indexed wire names, least significant bit first."""
        low, high = self.low, self.high
        if isinstance(self.original_port, (BelPort, TilePort)):
            return [f"{self.original_port.name}[{i}]" for i in range(low, high + 1)]
        if isinstance(self.original_port, SlicedPort):
            # Index the parent's expansion relatively: the parent already carries
            # its own bit offset, so low..high select into that sub-list.
            parent_bits = self.original_port.expand()
            return [parent_bits[i] for i in range(low, high + 1)]
        raise ValueError(f"type {type(self.original_port)} not supported for slicing")

    def __repr__(self) -> str:
        """Return a string representation of the SlicedPort."""
        return (
            f"SlicedPort({self.io_direction.value} "
            f"{self.name}[{self.high}:{self.low}] "
            f"from {self.original_port.name})"
        )

    def serialize(self) -> dict:
        """Serialize the sliced port to a dictionary."""
        return super().serialize() | {
            "high": self.high,
            "low": self.low,
            "original_port": self.original_port.name,
        }


class BelPort(Port):
    """A port on a BEL (Basic Element of Logic).

    Parameters
    ----------
    name : str
        The name of the port.
    io_direction : IO
        The I/O direction (INPUT, OUTPUT, INOUT).
    width : int
        The bit width of the port.
    prefix : str
        Prefix added to the port name.
    external : bool
        Whether the port is exposed externally.
    control : bool
        Whether the port is a control signal.
    is_clock : bool
        Whether the port carries a clock.
    is_global : bool
        Whether the port is driven by a fabric-wide signal.
    net : str
        The net the port belongs to; "" is the global net.
    """

    _prefix: str
    _external: bool
    _control: bool

    def __init__(
        self,
        name: str,
        io_direction: IO,
        width: int,
        prefix: str = "",
        external: bool = False,
        control: bool = False,
        is_clock: bool = False,
        is_global: bool = False,
        net: str = "",
    ) -> None:
        super().__init__(name, io_direction, width, is_clock, is_global, net)
        self._prefix = prefix
        self._external = external
        self._control = control

    @property
    def prefix(self) -> str:
        """The prefix added to the port name."""
        return self._prefix

    @property
    def external(self) -> bool:
        """Whether the port is exposed externally."""
        return self._external

    @property
    def control(self) -> bool:
        """Whether the port is a control signal."""
        return self._control

    def __repr__(self) -> str:
        """Return a string representation of the BelPort."""
        return f"BelPort({self.io_direction.value} {self.name}[{self.width - 1}:0])"

    @property
    def name(self) -> str:
        """The port name including its prefix."""
        return f"{self.prefix}{self._name}"

    def expand(self) -> list[str]:
        """Expand the port name into a list of strings based on the width.

        Returns
        -------
        list[str]
            A list of expanded port names.
        """
        if self.width == 1:
            return [f"{self.name}"]
        return [f"{self.name}[{i}]" for i in range(self.width)]

    def serialize(self) -> dict:
        """Serialize the BEL port to a dictionary."""
        return super().serialize() | {
            "prefix": self.prefix,
            "external": self.external,
            "control": self.control,
        }


class ConfigPort(Port):
    """A configuration port with features.

    Parameters
    ----------
    name : str
        The name of the port.
    io_direction : IO
        The I/O direction (INPUT, OUTPUT, INOUT).
    width : int
        The bit width of the port.
    features : list[FeatureValue] | None
        Features associated with this port; defaults to an empty list.
    feature_type : FeatureType
        The type of feature encoding.
    """

    _features: list[FeatureValue]
    _feature_type: FeatureType

    def __init__(
        self,
        name: str,
        io_direction: IO,
        width: int,
        features: list[FeatureValue] | None = None,
        feature_type: FeatureType = FeatureType.ENUMERATE,
    ) -> None:
        super().__init__(name, io_direction, width)
        self._features = features if features is not None else []
        self._feature_type = feature_type

    @property
    def features(self) -> list[FeatureValue]:
        """The list of features associated with this port."""
        return self._features

    @property
    def feature_type(self) -> FeatureType:
        """The type of feature encoding."""
        return self._feature_type

    def __repr__(self) -> str:
        """Return a string representation of the ConfigPort."""
        return (
            f"ConfigPort({self.io_direction.value} "
            f"{self.name}[{self.width - 1}:0], features={self.features})"
        )

    def serialize(self) -> dict:
        """Serialize the config port to a dictionary."""
        return super().serialize() | {
            "features": self.features,
            "feature_type": self.feature_type.value,
        }


class SharedPort(Port):
    """A port shared between multiple BELs.

    Parameters
    ----------
    name : str
        The name of the port.
    io_direction : IO
        The I/O direction (INPUT, OUTPUT, INOUT).
    width : int
        The bit width of the port.
    shared_with : str
        Name of the entity this port is shared with.
    """

    _shared_with: str

    def __init__(
        self,
        name: str,
        io_direction: IO,
        width: int,
        shared_with: str = "",
    ) -> None:
        super().__init__(name, io_direction, width)
        self._shared_with = shared_with

    @property
    def shared_with(self) -> str:
        """Name of the entity this port is shared with."""
        return self._shared_with

    def share_expand(self) -> list[str]:
        """Expand the port name into a list of strings based on the width.

        Returns
        -------
        list[str]
            A list of expanded port names using the shared_with name.
        """
        expand = []
        if self.width == 1:
            expand.append(f"{self.shared_with}")
        else:
            for i in range(self.width):
                expand.append(f"{self.shared_with}[{i}]")

        return expand

    def serialize(self) -> dict:
        """Serialize the shared port to a dictionary."""
        return super().serialize() | {"shared_with": self.shared_with}


# Type alias for any port type
GenericPort = Port | TilePort | SlicedPort | BelPort | ConfigPort | SharedPort

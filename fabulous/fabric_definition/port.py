"""Port class hierarchy for FPGA fabric.

This module contains the port class hierarchy for representing different types of ports
in the FPGA fabric:
- Port: Base class for all port types
- TilePort: Port on a tile with side and terminal information
- BelPort: Port on a BEL (Basic Element of Logic)
- SlicedPort: A sliced portion of another port
- SharedPort: A port shared between multiple BELs
- ConfigPort: A configuration port with features
"""

from fabulous.fabric_definition.define import (
    IO,
    ClockEdge,
    Direction,
    FeatureType,
    FeatureValue,
    Side,
)


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

    Raises
    ------
    ValueError
        If ``width`` is not greater than 0.
    TypeError
        If ``io_direction`` is not an ``IO`` or ``name`` is not a ``str``.
    """

    _name: str
    _io_direction: IO
    _width: int

    __slots__ = ("_name", "_io_direction", "_width")

    def __init__(self, name: str, io_direction: IO, width: int) -> None:
        self._name = name
        self._io_direction = io_direction
        self._width = width

        if self.width <= 0:
            raise ValueError(f"Width must be greater than 0, got {self.width}")
        if not isinstance(self.io_direction, IO):
            raise TypeError(
                f"io_direction must be an instance of IO, got {type(self.io_direction)}"
            )
        if not isinstance(self._name, str):
            raise TypeError(f"name must be a string, got {type(self._name)}")

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
        }


class TilePort(Port):
    """TilePort represents a port on a tile with a specific side and terminal status.

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
    terminal : bool
        Whether the port is a terminal port. Defaults to False.
    tile_type : str
        The type of tile this port belongs to.
    wire_direction : Direction | None
        The wire direction; defaults to ``Direction.JUMP`` when None.
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
    _terminal: bool
    _tile_type: str
    # Backward compatibility fields for wire routing
    _wire_direction: Direction
    _source_name: str
    _x_offset: int
    _y_offset: int
    _destination_name: str
    _wire_count: int

    __slots__ = (
        "_side_of_tile",
        "_terminal",
        "_tile_type",
        "_wire_direction",
        "_source_name",
        "_x_offset",
        "_y_offset",
        "_destination_name",
        "_wire_count",
    )

    def __init__(
        self,
        name: str,
        io_direction: IO,
        width: int,
        side_of_tile: Side,
        terminal: bool = False,
        tile_type: str = "",
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
        self._terminal = terminal
        self._tile_type = tile_type
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
    def terminal(self) -> bool:
        """Whether the port is a terminal port."""
        return self._terminal

    @property
    def tile_type(self) -> str:
        """The type of tile this port belongs to."""
        return self._tile_type

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

    def __hash__(self) -> int:
        """Return the hash value."""
        return super().__hash__()

    def __lt__(self, other: object, /) -> bool:
        """Less than comparison."""
        if not isinstance(other, TilePort):
            raise TypeError(f"Cannot compare {self} with {other}")
        return (self.__order[self.side_of_tile], self.__io[self.io_direction]) < (
            self.__order[other.side_of_tile],
            self.__io[other.io_direction],
        )

    def __le__(self, other: object, /) -> bool:
        """Less than or equal comparison."""
        if not isinstance(other, TilePort):
            raise TypeError(f"Cannot compare {self} with {other}")
        return (self.__order[self.side_of_tile], self.__io[self.io_direction]) <= (
            self.__order[other.side_of_tile],
            self.__io[other.io_direction],
        )

    def __gt__(self, other: object, /) -> bool:
        """Greater than comparison."""
        if not isinstance(other, TilePort):
            raise TypeError(f"Cannot compare {self} with {other}")
        return (self.__order[self.side_of_tile], self.__io[self.io_direction]) > (
            self.__order[other.side_of_tile],
            self.__io[other.io_direction],
        )

    def __ge__(self, other: object, /) -> bool:
        """Greater than or equal comparison."""
        if not isinstance(other, TilePort):
            raise TypeError(f"Cannot compare {self} with {other}")
        return (self.__order[self.side_of_tile], self.__io[self.io_direction]) >= (
            self.__order[other.side_of_tile],
            self.__io[other.io_direction],
        )

    def serialize(self) -> dict:
        """Serialize the tile port to a dictionary."""
        return super().serialize() | {
            "side_of_tile": self.side_of_tile.value,
            "terminal": self.terminal,
            "tile_type": self.tile_type,
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

        if total_wires == 1 and self.name != "NULL":
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
                f"{prefix}{self.name}{i}" for i in range(count) if self.name != "NULL"
            ]

        if escape:
            return [
                rf"{prefix}{self.name}\[{i}\]"
                for i in range(count)
                if self.name != "NULL"
            ]
        return [
            f"{prefix}{self.name}[{i}]" for i in range(count) if self.name != "NULL"
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
                if self.name != "NULL"
            ]

        if escape:
            return [
                rf"{prefix}{self.name}\[{i}\]"
                for i in range(startIndex, total_wires)
                if self.name != "NULL"
            ]
        return [
            f"{prefix}{self.name}[{i}]"
            for i in range(startIndex, total_wires)
            if self.name != "NULL"
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

    Parameters
    ----------
    original_port : Port
        The original port being sliced.
    slice_range : tuple[int, int]
        The inclusive range of bits to slice (start, end).
    """

    _slice_range: tuple[int, int]
    _original_port: Port

    __slots__ = ("_sliced_width", "_slice_range", "_original_port")

    def __init__(
        self,
        original_port: Port,
        slice_range: tuple[int, int] = (-1, -1),
    ) -> None:
        # Convention: slice_range is an inclusive, ascending (low, high) pair of
        # 0-based indices into the original port's own expansion. Both this width
        # and expand() follow it.
        super().__init__(
            original_port.name,
            original_port.io_direction,
            slice_range[1] - slice_range[0] + 1,
        )
        self._original_port = original_port
        self._slice_range = slice_range

    @property
    def original_port(self) -> Port:
        """The original port being sliced."""
        return self._original_port

    @property
    def slice_range(self) -> tuple[int, int]:
        """The inclusive range of bits to slice (start, end)."""
        return self._slice_range

    def expand(self) -> list[str]:
        """Expand the slice into a list of indexed wire names."""
        # slice_range is (low, high), inclusive, 0-based into the original port's
        # own expansion (see __init__).
        low, high = self.slice_range
        if isinstance(self.original_port, (BelPort, TilePort)):
            return [f"{self.original_port.name}[{i}]" for i in range(low, high + 1)]
        if isinstance(self.original_port, SlicedPort):
            # Index the parent's expansion relatively: the parent already carries
            # its own bit offset, so low..high select into that sub-list.
            parent_bits = self.original_port.expand()
            return [parent_bits[i] for i in range(low, high + 1)]
        raise ValueError(f"type {type(self.original_port)} not supported for slicing")

    def __hash__(self) -> int:
        """Return the hash value."""
        return super().__hash__()

    def __repr__(self) -> str:
        """Return a string representation of the SlicedPort."""
        return (
            f"SlicedPort({self.io_direction.value} "
            f"{self.name}[{self.slice_range[0]}:{self.slice_range[1]}] "
            f"from {self.original_port.name})"
        )

    def serialize(self) -> dict:
        """Serialize the sliced port to a dictionary."""
        return super().serialize() | {
            "slice_range": self.slice_range,
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
    """

    _prefix: str
    _external: bool
    _control: bool

    __slots__ = ("_prefix", "_external", "_control")

    def __init__(
        self,
        name: str,
        io_direction: IO,
        width: int,
        prefix: str = "",
        external: bool = False,
        control: bool = False,
    ) -> None:
        super().__init__(name, io_direction, width)
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

    def __hash__(self) -> int:
        """Return the hash value."""
        return super().__hash__()

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

    __slots__ = ("_features", "_feature_type")

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

    def __hash__(self) -> int:
        """Return the hash value."""
        return super().__hash__()

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

    __slots__ = ("_shared_with",)

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

    def __hash__(self) -> int:
        """Return the hash value."""
        return super().__hash__()

    def serialize(self) -> dict:
        """Serialize the shared port to a dictionary."""
        return super().serialize() | {"shared_with": self.shared_with}


class ClockPort(Port):
    """Clock port carrying clock-domain metadata.

    A ClockPort is a Port that additionally records the active clock edge, the
    clock domain it belongs to, and whether it is the global user clock
    (`UserCLK`) or a locally generated clock. By default it describes the fabric
    user clock: a 1-bit input named `UserCLK` on the global (unnamed) domain
    triggered on the rising edge.

    Parameters
    ----------
    name : str
        The name of the port. Defaults to "UserCLK".
    io_direction : IO
        The I/O direction. Defaults to IO.INPUT.
    width : int
        The bit width of the port. Defaults to 1.
    edge : ClockEdge
        The active clock edge. Defaults to ClockEdge.RISING.
    domain : str
        The clock domain this port belongs to. Defaults to "" (the global domain).
    is_global : bool
        Whether this is the global user clock rather than a locally generated
        clock. Defaults to True.

    Raises
    ------
    TypeError
        If edge is not a ClockEdge instance, or is_global is not a bool.
    """

    _edge: ClockEdge
    _domain: str
    _is_global: bool

    __slots__ = ("_edge", "_domain", "_is_global")

    def __init__(
        self,
        name: str = "UserCLK",
        io_direction: IO = IO.INPUT,
        width: int = 1,
        edge: ClockEdge = ClockEdge.RISING,
        domain: str = "",
        is_global: bool = True,
    ) -> None:
        super().__init__(name, io_direction, width)
        if not isinstance(edge, ClockEdge):
            raise TypeError(f"edge must be a ClockEdge, got {type(edge)}")
        if not isinstance(is_global, bool):
            raise TypeError(f"is_global must be a bool, got {type(is_global)}")
        self._edge = edge
        self._domain = domain
        self._is_global = is_global

    @property
    def edge(self) -> ClockEdge:
        """The active clock edge."""
        return self._edge

    @property
    def domain(self) -> str:
        """The clock domain this port belongs to."""
        return self._domain

    @property
    def is_global(self) -> bool:
        """Whether this is the global user clock."""
        return self._is_global

    def __repr__(self) -> str:
        """Return a string representation of the clock port."""
        scope = "global" if self.is_global else "local"
        return (
            f"ClockPort({scope} {self.edge.value} {self.io_direction.value} "
            f"{self.name}[{self.width - 1}:0])"
        )

    def __hash__(self) -> int:
        """Return the hash value."""
        return super().__hash__()

    def serialize(self) -> dict:
        """Serialize the clock port to a dictionary."""
        return super().serialize() | {
            "edge": self.edge.value,
            "domain": self.domain,
            "is_global": self.is_global,
        }

    @classmethod
    def from_serialized(cls, data: dict) -> "ClockPort":
        """Reconstruct a ClockPort from its serialized dictionary.

        Parameters
        ----------
        data : dict
            A dictionary produced by `serialize`.

        Returns
        -------
        ClockPort
            The reconstructed clock port.
        """
        return cls(
            name=data["name"],
            io_direction=IO(data["io_direction"]),
            width=data["width"],
            edge=ClockEdge(data["edge"]),
            domain=data["domain"],
            is_global=data["is_global"],
        )


# Type alias for any port type
GenericPort = (
    Port | TilePort | SlicedPort | BelPort | ConfigPort | SharedPort | ClockPort
)

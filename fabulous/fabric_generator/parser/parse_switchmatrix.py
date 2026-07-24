"""Parser functions for switch matrix and list file configurations.

This module provides utilities for parsing switch matrix CSV files and list files used
in fabric definition. It handles expansion of port definitions, connection mappings, and
validation of port configurations.
"""

import re
from collections import defaultdict
from pathlib import Path
from typing import TYPE_CHECKING, Literal, overload

from loguru import logger

from fabulous.custom_exception import (
    InvalidListFileDefinition,
    InvalidPortType,
    InvalidSwitchMatrixDefinition,
)
from fabulous.fabric_definition.define import IO, Direction, Side
from fabulous.fabric_definition.port import NULL_PORT_NAME, TilePort

if TYPE_CHECKING:
    from fabulous.fabric_definition.switch_matrix import SwitchMatrix

oppositeDic = {"NORTH": "SOUTH", "SOUTH": "NORTH", "EAST": "WEST", "WEST": "EAST"}


def parseMatrix(
    fileName: Path, preserve_list_order: bool = False
) -> dict[str, list[str]]:
    """Parse the matrix CSV into a dictionary from destination to source.

    A non-zero cell denotes a configurable connection. When
    `preserve_list_order` is set, the cell's integer encodes the mux input
    position (higher = earlier, MSB-first) and that order is kept; when unset,
    every connection is treated as a plain `1` so the inputs fall back to
    CSV-column order (legacy behaviour). Both sort by `(-value, column)`.

    The top-left header cell is a label only (conventionally the tile name)
    and is not validated: the mux-input columns are `header[1:]`.

    Parameters
    ----------
    fileName : Path
        Directory of the matrix CSV file.
    preserve_list_order : bool, optional
        Keep the cell-encoded mux-input order when True; otherwise treat every
        connection as `1` and use CSV-column order. Defaults to False.

    Raises
    ------
    InvalidSwitchMatrixDefinition
        A non-integer cell value in a row.

    Returns
    -------
    dict[str, list[str]]
        Dictionary from destination to a list of sources.
    """
    path = fileName.absolute()
    with path.open() as f:
        lines = re.sub(r"#.*", "", f.read()).split("\n")

    header = lines[0].split(",")
    dest_list = header[1:]

    connections: dict[str, list[str]] = {}
    for line in lines[1:]:
        fields = line.split(",")
        port_name, row = fields[0], fields[1:]
        if not port_name:
            continue
        items: list[tuple[int, int, str]] = []
        for k, v in enumerate(row):
            stripped = v.strip()
            if stripped == "":
                continue
            if k >= len(dest_list):
                raise InvalidSwitchMatrixDefinition(
                    f"{path}: row {port_name!r} has a non-empty cell {stripped!r} "
                    f"in column {k}, beyond the {len(dest_list)} destination "
                    "columns declared in the header. The row is wider than the "
                    "header, so this connection cannot be mapped to a destination."
                )
            try:
                value = int(stripped)
            except ValueError as exc:
                raise InvalidSwitchMatrixDefinition(
                    f"{path}: row {port_name!r} column {k} has non-integer "
                    f"cell value {stripped!r}"
                ) from exc
            if value != 0 and k < len(dest_list):
                sort_value = value if preserve_list_order else 1
                items.append((sort_value, k, dest_list[k]))
        items.sort(key=lambda x: (-x[0], x[1]))
        connections[port_name] = [d for _, _, d in items]
    return connections


def expandListPorts(port: str) -> list[str]:
    """Expand the .list file entry into a list of port strings.

    Parameters
    ----------
    port : str
        The port entry to expand. If it contains "[", it's split
        into multiple entries based on "|".

    Raises
    ------
    ValueError
        If the port entry contains "[" or "{" without matching closing
        bracket "]"/"}", or if a "{...}" multiplier is not a positive
        integer.

    Returns
    -------
    list[str]
        The expanded list of port strings.
    """
    if port.count("[") != port.count("]") or port.count("{") != port.count("}"):
        raise ValueError(f"Invalid port entry: {port}, mismatched brackets")

    # "[...]" splits the port into alternatives separated by "|",
    # expanding each recursively
    if "[" in port:
        left_index = port.find("[")
        right_index = port.find("]")
        before = port[:left_index]
        after = port[right_index + 1 :]
        result = []
        for entry in port[left_index + 1 : right_index].split("|"):
            result.extend(expandListPorts(before + entry + after))
        return result

    # "{N}" is a multiplier: repeat the port N times and strip the
    # multiplier from the name. N must be a positive integer; "{0}" and
    # non-numeric "{x}" are malformed and must not leak literal braces
    # into the returned port name.
    port = port.replace(" ", "")
    brace_contents = re.findall(r"\{([^{}]*)\}", port)
    if not brace_contents:
        return [port]

    port_multiplier = 0
    for content in brace_contents:
        if not content.isdigit() or int(content) == 0:
            raise ValueError(
                f"Invalid port entry: {port}, multiplier '{{{content}}}' must be "
                "a positive integer"
            )
        port_multiplier += int(content)
    port = re.sub(r"\{[^{}]*\}", "", port)
    return [port] * port_multiplier


@overload
def parseList(
    filePath: Path, collect: Literal["pair"] = "pair"
) -> list[tuple[str, str]]:
    pass


@overload
def parseList(
    filePath: Path, collect: Literal["source", "sink"]
) -> dict[str, list[str]]:
    pass


def parseList(
    filePath: Path,
    collect: Literal["pair", "source", "sink"] = "pair",
) -> list[tuple[str, str]] | dict[str, list[str]]:
    """Parse a list file and expand the list file information into a list of tuples.

    Parameters
    ----------
    filePath : Path
        The path to the list file to parse.
    collect : Literal["pair", "source", "sink"], optional
        Collect value by source, sink or just as (source, sink) pair.
        Defaults to "pair".

    Raises
    ------
    FileNotFoundError
        The file does not exist.
    InvalidListFileDefinition
        Invalid format in the list file.

    Returns
    -------
    list[tuple[str, str]] | dict[str, list[str]]
        Return either a list of connection pairs or a dictionary of lists which is
        collected by the specified option, source or sink.
    """
    path = filePath.absolute()
    if not path.exists():
        raise FileNotFoundError(f"The file {path} does not exist.")

    pairs: list[tuple[str, str]] = []
    with path.open() as f:
        content = re.sub(r"#.*", "", f.read())
    for line_num, raw_line in enumerate(content.split("\n")):
        fields = [
            f for f in raw_line.replace(" ", "").replace("\t", "").split(",") if f
        ]
        if not fields:
            continue
        if len(fields) != 2:
            raise InvalidListFileDefinition(
                f"Invalid list formatting in file: {path} at line {line_num}: {fields}"
            )
        source_entry, sink_entry = fields[0], fields[1]

        if source_entry == "INCLUDE":
            pairs.extend(parseList(path.parent / sink_entry, "pair"))
            continue

        expanded_sources = expandListPorts(source_entry)
        expanded_sinks = expandListPorts(sink_entry)
        if len(expanded_sources) != len(expanded_sinks):
            raise InvalidListFileDefinition(
                f"List file {path} does not have the same number of source and "
                f"sink ports at line {line_num}: {fields}"
            )
        pairs.extend(zip(expanded_sources, expanded_sinks, strict=True))

    unique_pairs = list(dict.fromkeys(pairs))
    if len(unique_pairs) != len(pairs):
        logger.warning(
            f"{path.name}: ignoring {len(pairs) - len(unique_pairs)} duplicate "
            "connection(s)"
        )

    if collect == "source":
        grouped: defaultdict[str, list[str]] = defaultdict(list)
        for source, sink in unique_pairs:
            grouped[source].append(sink)
        return dict(grouped)

    if collect == "sink":
        grouped = defaultdict(list)
        for source, sink in unique_pairs:
            grouped[sink].append(source)
        return dict(grouped)

    return unique_pairs


def _canonical_offset(
    direction: Direction, raw_x: int, raw_y: int, line: str
) -> tuple[int, int]:
    """Derive a wire's canonical bottom-left offset from its direction and reach.

    A cardinal wire's orientation is fixed by its direction token, so only the
    reach magnitude of the authored offsets is meaningful; the sign is derived
    here. The reach lies on the direction's own axis, and the orthogonal offset
    must be zero.

    Parameters
    ----------
    direction : Direction
        The wire's cardinal direction (NORTH, SOUTH, EAST or WEST).
    raw_x : int
        The authored x offset.
    raw_y : int
        The authored y offset.
    line : str
        The originating CSV line, used in the error message.

    Raises
    ------
    InvalidSwitchMatrixDefinition
        If the offset orthogonal to the direction is non-zero, i.e. the wire is
        diagonal and has no unambiguous cardinal reach.

    Returns
    -------
    tuple[int, int]
        The canonical ``(x_offset, y_offset)`` under the bottom-left origin.
    """
    match direction:
        case Direction.NORTH:
            off_axis, x, y = raw_x, 0, abs(raw_y)
        case Direction.SOUTH:
            off_axis, x, y = raw_x, 0, -abs(raw_y)
        case Direction.EAST:
            off_axis, x, y = raw_y, abs(raw_x), 0
        case Direction.WEST:
            off_axis, x, y = raw_y, -abs(raw_x), 0
    if off_axis != 0:
        raise InvalidSwitchMatrixDefinition(
            f"Invalid port definition line {line!r}: a {direction.value} wire "
            f"must have a zero offset on the orthogonal axis, got ({raw_x}, "
            f"{raw_y})."
        )
    return x, y


def parse_port_line(line: str) -> tuple[list[TilePort], tuple[str, str] | None]:
    """Parse a single line of the port configuration from the CSV file.

    Parameters
    ----------
    line : str
        CSV line containing port configuration data.

    Raises
    ------
    InvalidPortType
        If the port definition is invalid.

    Returns
    -------
    tuple[list[TilePort], tuple[str, str] | None]
        A tuple containing a list of parsed ports and an optional common wire pair.
    """
    fields: list[str] = line.split(",")
    port_type = fields[0]

    try:
        wire_direction = Direction[port_type]
    except KeyError:
        raise InvalidPortType(f"Unknown port type: {port_type}") from None

    if len(fields) < 6:
        raise InvalidPortType(
            f"Invalid port definition line {line!r}: port type {port_type!r} "
            "requires 6 comma-separated fields (DIRECTION, source_name, "
            "x_offset, y_offset, destination_name, wire_count), "
            f"got {len(fields)}."
        )
    source_name = fields[1]
    x_offset = int(fields[2])
    y_offset = int(fields[3])
    destination_name = fields[4]
    wire_count = int(fields[5])

    # The trailing digits are read back as that index. A name that ends in a
    # digit is ambiguous once expanded.
    for wire_name in (source_name, destination_name):
        if wire_name != NULL_PORT_NAME and wire_name[-1:].isdigit():
            raise InvalidPortType(
                f"Wire name '{wire_name}' ends in a digit, which is ambiguous: "
                "wire expansion appends the index as a trailing digit, so a name "
                "ending in a digit cannot be distinguished from an indexed wire. "
                "Rename the wire so it does not end in a digit."
            )

    ports: list[TilePort] = []
    commonWirePair: tuple[str, str] | None

    if wire_direction in (
        Direction.NORTH,
        Direction.EAST,
        Direction.SOUTH,
        Direction.WEST,
    ):
        # The direction token is authoritative for the wire's orientation and
        # sign; the offsets contribute only reach (magnitude). Deriving the sign
        # here rather than trusting the authored one lets both the top-first
        # (pre-bottom-left origin) and the current bottom-left CSV conventions
        # parse to the same model, so existing fabric definitions keep working.
        x_offset, y_offset = _canonical_offset(wire_direction, x_offset, y_offset, line)

        # Output port (source side)
        ports.append(
            TilePort(
                name=source_name,
                io_direction=IO.OUTPUT,
                width=wire_count,
                side_of_tile=Side[port_type],
                wire_direction=wire_direction,
                source_name=source_name,
                x_offset=x_offset,
                y_offset=y_offset,
                destination_name=destination_name,
                wire_count=wire_count,
            )
        )

        # Input port (destination side)
        ports.append(
            TilePort(
                name=destination_name,
                io_direction=IO.INPUT,
                width=wire_count,
                side_of_tile=Side[port_type].opposite,
                wire_direction=wire_direction,
                source_name=source_name,
                x_offset=x_offset,
                y_offset=y_offset,
                destination_name=destination_name,
                wire_count=wire_count,
            )
        )
        commonWirePair = (f"{source_name}", f"{destination_name}")

    elif wire_direction is Direction.JUMP:
        # Output port
        ports.append(
            TilePort(
                name=source_name,
                io_direction=IO.OUTPUT,
                width=wire_count,
                side_of_tile=Side.ANY,
                wire_direction=Direction.JUMP,
                source_name=source_name,
                x_offset=x_offset,
                y_offset=y_offset,
                destination_name=destination_name,
                wire_count=wire_count,
            )
        )
        # Input port
        ports.append(
            TilePort(
                name=destination_name,
                io_direction=IO.INPUT,
                width=wire_count,
                side_of_tile=Side.ANY,
                wire_direction=Direction.JUMP,
                source_name=source_name,
                x_offset=x_offset,
                y_offset=y_offset,
                destination_name=destination_name,
                wire_count=wire_count,
            )
        )
        commonWirePair = None

    else:
        raise InvalidPortType(f"Unknown port type: {port_type}")
    return (ports, commonWirePair)


def create_switch_matrix(matrix_dir: Path, tileName: str = "") -> "SwitchMatrix":
    """Build a `SwitchMatrix` from a switch matrix file.

    Thin wrapper over `SwitchMatrix.from_file` for the composite-tile parse
    path, whose wrapper matrix has no tile ports to canonicalise against.

    Parameters
    ----------
    matrix_dir : Path
        Path to the switch matrix file (`.list`, `.csv`, or hand-written HDL).
    tileName : str, optional
        Tile name, used in HDL warnings and CSV validation. Defaults to "".

    Returns
    -------
    SwitchMatrix
        The parsed switch matrix.
    """
    from fabulous.fabric_definition.switch_matrix import SwitchMatrix

    return SwitchMatrix.from_file(matrix_dir, tileName)

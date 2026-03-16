"""Parser functions for switch matrix and list file configurations.

This module provides utilities for parsing switch matrix CSV files and list files used
in fabric definition. It handles expansion of port definitions, connection mappings, and
validation of port configurations.
"""

import re
from pathlib import Path
from typing import Literal, overload

from fabulous.custom_exception import (
    InvalidListFileDefinition,
    InvalidPortType,
    InvalidSwitchMatrixDefinition,
)
from fabulous.fabric_definition.define import IO, Direction, Side
from fabulous.fabric_definition.port import Port

oppositeDic = {"NORTH": "SOUTH", "SOUTH": "NORTH", "EAST": "WEST", "WEST": "EAST"}


def parseMatrix(fileName: Path, tileName: str) -> dict[str, list[str]]:
    """Parse the matrix CSV into a dictionary from destination to source.

    Parameters
    ----------
    fileName : Path
        Directory of the matrix CSV file.
    tileName : str
        Name of the tile needed to be parsed.

    Raises
    ------
    InvalidSwitchMatrixDefinition
        Non matching matrix file content and tile name

    Returns
    -------
    dict[str, list[str]]
        Dictionary from destination to a list of sources.
    """
    path = fileName.absolute()
    with path.open() as f:
        lines = re.sub(r"#.*", "", f.read()).split("\n")

    header = lines[0].split(",")
    if header[0] != tileName:
        raise InvalidSwitchMatrixDefinition(
            f"{path} {header} {tileName}\n"
            "Tile name (top left element) in csv file does not match tile name "
            "in tile object"
        )
    dest_list = header[1:]

    connections: dict[str, list[str]] = {}
    for line in lines[1:]:
        fields = line.split(",")
        port_name, row = fields[0], fields[1:]
        if not port_name:
            continue
        # collect destinations where the connection bit is set
        connections[port_name] = [dest_list[k] for k, v in enumerate(row) if v == "1"]
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
        bracket "]"/"}".

    Returns
    -------
    list[str]
        The expanded list of port strings.
    """
    if port.count("[") != port.count("]") and port.count("{") != port.count("}"):
        raise ValueError(f"Invalid port entry: {port}, mismatched brackets")

    # "[...]" splits the port into alternatives separated by "|", expanding each recursively
    if "[" in port:
        left_index = port.find("[")
        right_index = port.find("]")
        before = port[:left_index]
        after = port[right_index + 1 :]
        result = []
        for entry in re.split(r"\|", port[left_index + 1 : right_index]):
            result.extend(expandListPorts(before + entry + after))
        return result

    # "{N}" is a multiplier: repeat the port N times and strip the multiplier from the name
    port = port.replace(" ", "")
    multipliers = re.findall(r"\{(\d+)\}", port)
    portMultiplier = sum(int(m) for m in multipliers)
    if portMultiplier != 0:
        port = re.sub(r"\{(\d+)\}", "", port)
        return [port] * portMultiplier
    return [port]


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
    filePath = filePath.absolute()
    if not filePath.exists():
        raise FileNotFoundError(f"The file {filePath} does not exist.")

    pairs: list[tuple[str, str]] = []
    with filePath.open() as f:
        content = re.sub(r"#.*", "", f.read())
    for line_num, raw_line in enumerate(content.split("\n")):
        fields = [
            f for f in raw_line.replace(" ", "").replace("\t", "").split(",") if f
        ]
        if not fields:
            continue
        if len(fields) != 2:
            raise InvalidListFileDefinition(
                f"Invalid list formatting in file: {filePath} at line {line_num}: {fields}"
            )
        source_entry, sink_entry = fields[0], fields[1]

        if source_entry == "INCLUDE":
            pairs.extend(parseList(filePath.parent / sink_entry, "pair"))
            continue

        expanded_sources = expandListPorts(source_entry)
        expanded_sinks = expandListPorts(sink_entry)
        if len(expanded_sources) != len(expanded_sinks):
            raise InvalidListFileDefinition(
                f"List file {filePath} does not have the same number of source and "
                f"sink ports at line {line_num}: {fields}"
            )
        pairs.extend(zip(expanded_sources, expanded_sinks, strict=False))

    unique_pairs = list(dict.fromkeys(pairs))

    if collect == "source":
        grouped: dict[str, list[str]] = {}
        for source, sink in unique_pairs:
            grouped.setdefault(source, []).append(sink)
        return grouped

    if collect == "sink":
        grouped = {}
        for source, sink in unique_pairs:
            grouped.setdefault(sink, []).append(source)
        return grouped

    return unique_pairs


def parsePortLine(line: str) -> tuple[list[Port], tuple[str, str] | None]:
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
    tuple[list[Port], tuple[str, str] | None]
        A tuple containing a list of parsed ports and an optional common wire pair.
    """
    kind, start, x, y, end, count = line.split(",")[:6]
    x, y, count = int(x), int(y), int(count)

    if kind in ("NORTH", "SOUTH", "EAST", "WEST"):
        # Directional wire: OUTPUT port at start side, INPUT port at opposite side
        direction = Direction[kind]
        ports = [
            Port(direction, start, x, y, end, count, start, IO.OUTPUT, Side[kind]),
            Port(
                direction,
                start,
                x,
                y,
                end,
                count,
                end,
                IO.INPUT,
                Side[oppositeDic[kind].upper()],
            ),
        ]
        return ports, (start, end)

    if kind == "JUMP":
        # Jump wire: connects within the same tile, no directional side
        ports = [
            Port(Direction.JUMP, start, x, y, end, count, start, IO.OUTPUT, Side.ANY),
            Port(Direction.JUMP, start, x, y, end, count, end, IO.INPUT, Side.ANY),
        ]
        return ports, None

    raise InvalidPortType(f"Unknown port type: {kind}")

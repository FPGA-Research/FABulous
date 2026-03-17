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
    InvalidSwitchMatrixDefinition,
)

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
    if port.count("[") != port.count("]") or port.count("{") != port.count("}"):
        raise ValueError(f"Invalid port entry: {port}, mismatched brackets")

    # "[...]" splits the port into alternatives separated by "|", expanding each recursively
    if "[" in port:
        left_index = port.find("[")
        right_index = port.find("]")
        before = port[:left_index]
        after = port[right_index + 1 :]
        result = []
        for entry in port[left_index + 1 : right_index].split("|"):
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

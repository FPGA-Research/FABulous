"""Helper functions for FPGA fabric generation.

This module provides utility functions that assist in various aspects of FPGA fabric
generation, including switch matrix bootstrapping, signal ordering, and file generation
utilities. These functions support the main fabric generation workflow by providing
common operations needed across multiple generation stages.
"""

import csv
import re
from pathlib import Path

from loguru import logger

from fabulous.fabric_definition.define import Direction
from fabulous.fabric_definition.tile import Tile
from fabulous.fabric_generator.parser.parse_switchmatrix import parseList


def bootstrap_switch_matrix(tile: Tile, outputDir: Path) -> None:
    """Generate a blank switch matrix CSV file for the given tile.

    The top left corner will contain the name of the tile.
    Columns are the source signals and rows are the destination signals.

    The order of the signal will be:
    - standard wire
    - BEL signal with prefix
    - GEN_IO signals with prefix
    - jump wire

    The order is important as this order will be used during switch matrix generation.

    Parameters
    ----------
    tile : Tile
        The tile to generate the switch matrix for
    outputDir : Path
        The output directory to write the switch matrix to
    """
    logger.info(f"Generate matrix csv for {tile.name} # filename: {outputDir}")
    with outputDir.open("w") as f:
        writer = csv.writer(f)
        sourceName, destName = [], []
        # normal wire
        for i in tile.portsInfo:
            if i.wireDirection != Direction.JUMP:
                portInput, portOutput = i.expandPortInfo("AutoSwitchMatrix")
                sourceName += portInput
                destName += portOutput
        # bel wire
        for b in tile.bels:
            for p in b.inputs:
                sourceName.append(f"{p}")
            for p in b.outputs + b.externalOutput:
                destName.append(f"{p}")

        # jump wire
        for i in tile.portsInfo:
            if i.wireDirection == Direction.JUMP:
                portInput, portOutput = i.expandPortInfo("AutoSwitchMatrix")
                sourceName += portInput
                destName += portOutput
        sourceName = list(dict.fromkeys(sourceName))
        destName = list(dict.fromkeys(destName))
        writer.writerow([tile.name] + destName)
        for p in sourceName:
            writer.writerow([p] + [0] * len(destName))


def bootstrap_matrix_from_list(list_file: Path, output: Path, tile_name: str) -> None:
    """Generate a blank switch matrix CSV whose ports come from a .list file.

    Unlike `bootstrap_switch_matrix`, this does not need a `Tile` object: the
    source and destination port sets are derived directly from the
    connections in `list_file`. Only ports that take part in at least one
    connection appear in the grid, in first-appearance order. The result is
    an all-zero grid ready for `list_to_csv` to populate.

    Parameters
    ----------
    list_file : Path
        The input .list file to derive the ports from.
    output : Path
        The path of the blank switch matrix CSV to write.
    tile_name : str
        The name written into the top-left cell of the matrix.
    """
    connection_pairs = parseList(list_file)
    sources = list(dict.fromkeys(s for s, _ in connection_pairs))
    destinations = list(dict.fromkeys(d for _, d in connection_pairs))
    with output.open("w") as f:
        writer = csv.writer(f)
        writer.writerow([tile_name] + destinations)
        for s in sources:
            writer.writerow([s] + [0] * len(destinations))


def list_to_csv(
    InFileName: Path, OutFileName: Path, preserveListOrder: bool = False
) -> None:
    """Export a list file into its equivalent CSV switch matrix representation.

    A comment will be appended to the end of the column and
    row of the matrix, which will indicate the number of signals in a given row.

    When `preserveListOrder` is on, give each new connection a unique 1-based
    per-row index so the order can be recovered later. Otherwise all
    connections are marked with `1`. The per-row counter starts past any
    existing non-zero values that the bootstrap CSV may already contain.

    Parameters
    ----------
    InFileName : Path
        The input file name of the list file
    OutFileName : Path
        The directory of the CSV file to be written
    preserveListOrder : bool, optional
        By default, every connection is written as `1`, and order is
        determined by CSV-column position when read back. When it is set to
        `True`, every connection is written as its 1-based position in the
        .list file for that row (1, 2, 3, ...), so `parseMatrix` can recover
        the user-specified mux input order.
    """
    logger.info(f"Adding {InFileName} to {OutFileName}")

    connectionPair = parseList(InFileName)

    with Path(OutFileName).open() as f:
        file = f.read()
        file = re.sub(r"#.*", "", file)
        file = file.split("\n")

    col = len(file[0].split(","))
    rows = len(file)

    # create a 0 zero matrix as initialization
    matrix = [[0 for _ in range(col)] for _ in range(rows)]

    # load the data from the original csv into the matrix
    for i in range(1, len(file)):
        for j in range(1, len(file[i].split(","))):
            value = file[i].split(",")[j]
            if value == "":
                continue
            matrix[i - 1][j - 1] = int(value)

    # get source and destination list in the csv
    destination = file[0].strip("\n").split(",")[1:]
    source = [file[i].split(",")[0] for i in range(1, len(file))]

    row_seq = [max((v for v in matrix[i]), default=0) for i in range(len(source))]
    for s, d in connectionPair:
        try:
            s_index = source.index(s)
        except ValueError:
            logger.critical(f"{s} is not in the source column of the matrix csv file")
            exit(-1)

        try:
            d_index = destination.index(d)
        except ValueError:
            logger.critical(f"{d} is not in the destination row of the matrix csv file")
            exit(-1)

        if matrix[s_index][d_index] != 0:
            logger.warning(
                f"Connection ({s}, {d}) already exists in the original matrix"
            )
            continue
        if preserveListOrder:
            row_seq[s_index] += 1
            matrix[s_index][d_index] = row_seq[s_index]
        else:
            matrix[s_index][d_index] = 1

    # writing the matrix back to the given out file
    with Path(OutFileName).open("w") as f:
        f.write(file[0] + "\n")
        for i in range(len(source)):
            f.write(f"{source[i]},")
            row_nonzero = sum(1 for v in matrix[i] if v != 0)
            for j in range(len(destination)):
                f.write(str(matrix[i][j]))
                if j != len(destination) - 1:
                    f.write(",")
                else:
                    f.write(f",#,{row_nonzero}")
            f.write("\n")
        colCount = []
        for j in range(col):
            count = 0
            for i in range(rows):
                if matrix[i][j] != 0:
                    count += 1
            colCount.append(str(count))
        f.write(f"#,{','.join(colCount)}")


def csv_to_list(InFileName: Path, OutFileName: Path) -> None:
    """Export a CSV switch matrix description into its equivalent list representation.

    Every non-zero cell becomes a `source,destination` line. The `#` metadata
    that `list_to_csv` appends (per-row connection counts and the trailing
    column-count row) is stripped the same way `parseMatrix` does, so a CSV
    produced by `list_to_csv` round-trips back to a valid .list file.

    Parameters
    ----------
    InFileName : Path
        The input file name of the CSV file
    OutFileName : Path
        The directory of the list file to be written
    """
    with Path(InFileName).open() as f:
        lines = re.sub(r"#.*", "", f.read()).split("\n")

    header = lines[0].split(",")
    tile_name = header[0]
    destinations = header[1:]

    with Path(OutFileName).open("w") as f:
        f.write(f"# {tile_name}\n")
        for line in lines[1:]:
            fields = line.split(",")
            source = fields[0]
            if not source:
                continue
            for k, value in enumerate(fields[1:]):
                if (
                    k < len(destinations)
                    and destinations[k]
                    and value.strip() not in ("", "0")
                ):
                    f.write(f"{source},{destinations[k]}\n")

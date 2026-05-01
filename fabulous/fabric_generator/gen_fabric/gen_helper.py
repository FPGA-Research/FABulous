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


def bootstrapSwitchMatrix(tile: Tile, outputDir: Path) -> None:
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


def list2CSV(
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


def CSV2list(InFileName: str, OutFileName: str) -> None:
    """Export a CSV switch matrix description into its equivalent list representation.

    Parameters
    ----------
    InFileName : str
        The input file name of the CSV file
    OutFileName : str
        The directory of the list file to be written
    """
    with Path(InFileName).open() as f:
        inFile = f.readlines()
    InFile = [i.strip("\n").split(",") for i in inFile]
    with Path(OutFileName).open("w") as f:
        # get the number of tiles in horizontal direction
        cols = len(InFile[0])
        # top-left should be the name
        _ = f.write(f"# {InFile[0][0]}\n")
        # switch matrix inputs
        inputs = []
        for item in InFile[0][1:]:
            inputs.append(item)
        # beginning from the second line, write out the list
        for line in InFile[1:]:
            for i in range(1, cols):
                if line[i] != "0":
                    # it is [i-1] because the beginning of the line is the
                    # destination port
                    _ = f.write(f"{line[0]},{inputs[i - 1]}")

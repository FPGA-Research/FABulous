import csv
import re
from pathlib import Path

from loguru import logger

from FABulous.fabric_definition.define import Direction
from FABulous.fabric_definition.Tile import Tile
from FABulous.fabric_generator.parser.parse_switchmatrix import parseList


def bootstrapSwitchMatrix(tile: Tile, outputDir: Path) -> None:
    """Generates a blank switch matrix CSV file for the given tile. The top left corner
    will contain the name of the tile. Columns are the source signals and rows are the
    destination signals.

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
    outputDir : str
        The output directory to write the switch matrix to
    """
    logger.info(f"Generate matrix csv for {tile.name} # filename: {outputDir}")
    with open(outputDir, "w") as f:
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


def list2CSV(InFileName: Path, OutFileName: Path) -> None:
    """This function is used to export a given list description into its equivalent CSV
    switch matrix description. A comment will be appended to the end of the column and
    row of the matrix, which will indicate the number of signals in a given row.

    Parameters
    ----------
    InFileName : str
        The input file name of the list file
    OutFileName : str
        The directory of the CSV file to be written

    Raises
    ------
    ValueError
        If the list file contains signals that are not in the matrix file
    """

    logger.info(f"Adding {InFileName} to {OutFileName}")

    connectionPair = parseList(InFileName)

    with open(OutFileName) as f:
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

    # set the matrix value with the provided connection pair
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
        matrix[s_index][d_index] = 1

    # writing the matrix back to the given out file
    with open(OutFileName, "w") as f:
        f.write(file[0] + "\n")
        for i in range(len(source)):
            f.write(f"{source[i]},")
            for j in range(len(destination)):
                f.write(str(matrix[i][j]))
                if j != len(destination) - 1:
                    f.write(",")
                else:
                    f.write(f",#,{matrix[i].count(1)}")
            f.write("\n")
        colCount = []
        for j in range(col):
            count = 0
            for i in range(rows):
                if matrix[i][j] == 1:
                    count += 1
            colCount.append(str(count))
        f.write(f"#,{','.join(colCount)}")


def CSV2list(InFileName: str, OutFileName: str):
    """This function is used to export a given CSV switch matrix description into its
    equivalent list description.

    Parameters
    ----------
    InFileName : str
        The input file name of the CSV file
    OutFileName : str
        The directory of the list file to be written
    """
    InFile = [i.strip("\n").split(",") for i in open(InFileName)]
    with open(OutFileName, "w") as f:
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
                    # it is [i-1] because the beginning of the line is the destination port
                    _ = f.write(f"{line[0]},{inputs[i - 1]}")

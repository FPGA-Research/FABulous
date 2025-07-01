import csv
import json
import os
import re
import subprocess
from copy import deepcopy
from pathlib import Path
from typing import Literal, overload

from loguru import logger

from FABulous.custom_exception import FabricParsingError
from FABulous.fabric_definition.Bel import Bel
from FABulous.fabric_definition.ConfigMem import ConfigMem
from FABulous.fabric_definition.define import (
    IO,
    ConfigBitMode,
    Direction,
    MultiplexerStyle,
    Side,
)
from FABulous.fabric_definition.Fabric import Fabric
from FABulous.fabric_definition.Gen_IO import Gen_IO
from FABulous.fabric_definition.Port import Port
from FABulous.fabric_definition.SuperTile import SuperTile
from FABulous.fabric_definition.Tile import Tile
from FABulous.fabric_generator.utilities import expandListPorts

oppositeDic = {"NORTH": "SOUTH", "SOUTH": "NORTH", "EAST": "WEST", "WEST": "EAST"}


def parseFabricCSV(fileName: str) -> Fabric:
    """Parses a CSV file and returns a fabric object.

    Parameters
    ----------
    fileName : str
        Directory of the CSV file.

    Raises
    ------
    ValueError
        - File provided is not a CSV file.
        - CSV file does not exist.
        - FabricBegin and FabricEnd regions cannot be found.
        - ParametersBegin and ParametersEnd regions cannot be found.
        - Bel entry extension is not ".v" or ".vhdl".
        - Matrix entry extension is not ".list", ".csv", ".v", or ".vhdl".
        - Unknown tile description entry is found in the CSV file.
        - Unknown tile is found in the fabric entry in the CSV file.
        - Unknown super tile is found in the super tile entry in the CSV file.
        - Invalid ConfigBitMode is found in the parameter entry in the CSV file.
        - Invalid MultiplexerStyle is found in the parameter entry in the CSV file.
        - Invalid parameter entry is found in the CSV file.

    Returns
    -------
    Fabric
        The fabric object.
    """

    fName = Path(fileName)
    if fName.suffix != ".csv":
        logger.error("File must be a csv file")
        raise ValueError

    if not fName.exists():
        logger.error(f"File {fName} does not exist.")
        raise ValueError

    filePath = fName.parent

    with open(fName) as f:
        file = f.read()
        file = re.sub(r"#.*", "", file)

    # read in the csv file and part them
    if fabricDescription := re.search(
        r"FabricBegin(.*?)FabricEnd", file, re.MULTILINE | re.DOTALL
    ):
        fabricDescription = fabricDescription.group(1)
    else:
        logger.error("Cannot find FabricBegin and FabricEnd in csv file.")
        raise ValueError

    if parameters := re.search(
        r"ParametersBegin(.*?)ParametersEnd", file, re.MULTILINE | re.DOTALL
    ):
        parameters = parameters.group(1)
    else:
        logger.error("Cannot find ParametersBegin and ParametersEnd in csv file.")
        raise ValueError

    fabricDescription = fabricDescription.split("\n")
    parameters = parameters.split("\n")

    # Lists for tiles
    tileTypes = []
    tileDefs = []
    commonWirePair: list[tuple[str, str]] = []
    fabricTiles = []
    tileDic = {}
    unusedTileDic = {}

    # list for supertiles
    superTileDic = {}
    unusedSuperTileDic = {}

    # For backwards compatibility parse tiles in fabric config
    new_tiles, new_commonWirePair = parseTiles(fName)
    tileTypes += [new_tile.name for new_tile in new_tiles]
    tileDefs += new_tiles
    commonWirePair += new_commonWirePair
    tileDic = dict(zip(tileTypes, tileDefs, strict=False))

    new_supertiles = parseSupertiles(fName, tileDic)
    for new_supertile in new_supertiles:
        superTileDic[new_supertile.name] = new_supertile

    if new_tiles or new_supertiles:
        logger.warning(
            f"Deprecation warning: {fName} should not contain tile descriptions."
        )

    # parse the parameters
    height = 0
    width = 0
    configBitMode = ConfigBitMode.FRAME_BASED
    frameBitsPerRow = 32
    maxFramesPerCol = 20
    package = "use work.my_package.all;"
    generateDelayInSwitchMatrix = 80
    multiplexerStyle = MultiplexerStyle.CUSTOM
    superTileEnable = True

    for i in parameters:
        i = i.split(",")
        i = [j for j in i if j != ""]
        if not i:
            continue
        if i[0].startswith("Tile"):
            if "GENERATE" in i:
                # import here to avoid circular import
                from FABulous.fabric_generator.fabric_automation import (
                    generate_custom_tile_config,
                )

                # we generate the tile right before we parse everything
                i[1] = str(generate_custom_tile_config(filePath.joinpath(i[1])))

            new_tiles, new_commonWirePair = parseTiles(filePath.joinpath(i[1]))
            tileTypes += [new_tile.name for new_tile in new_tiles]
            tileDefs += new_tiles
            commonWirePair += new_commonWirePair
            tileDic = dict(zip(tileTypes, tileDefs, strict=False))
        elif i[0].startswith("Supertile"):
            new_supertiles = parseSupertiles(filePath.joinpath(i[1]), tileDic)
            for new_supertile in new_supertiles:
                superTileDic[new_supertile.name] = new_supertile
        elif i[0].startswith("ConfigBitMode"):
            if i[1] == "frame_based":
                configBitMode = ConfigBitMode.FRAME_BASED
            elif i[1] == "FlipFlopChain":
                configBitMode = ConfigBitMode.FLIPFLOP_CHAIN
            else:
                logger.error(
                    f"Invalid config bit mode {i[1]} in parameters. Valid options are frame_based and FlipFlopChain."
                )
                raise ValueError
        elif i[0].startswith("FrameBitsPerRow"):
            frameBitsPerRow = int(i[1])
        elif i[0].startswith("MaxFramesPerCol"):
            maxFramesPerCol = int(i[1])
        elif i[0].startswith("Package"):
            package = i[1]
        elif i[0].startswith("GenerateDelayInSwitchMatrix"):
            generateDelayInSwitchMatrix = int(i[1])
        elif i[0].startswith("MultiplexerStyle"):
            if i[1] == "custom":
                multiplexerStyle = MultiplexerStyle.CUSTOM
            elif i[1] == "generic":
                multiplexerStyle = MultiplexerStyle.GENERIC
            else:
                logger.error(
                    f"Invalid multiplexer style {i[1]} in parameters. Valid options are custom and generic."
                )
                raise ValueError
        elif i[0].startswith("SuperTileEnable"):
            superTileEnable = i[1] == "TRUE"
        else:
            logger.error(f"The following parameter is not valid: {i}")
            raise ValueError

    # form the fabric data structure
    usedTile = set()
    for f in fabricDescription:
        fabricLineTmp = f.split(",")
        fabricLineTmp = [i for i in fabricLineTmp if i != ""]
        if not fabricLineTmp:
            continue
        fabricLine = []
        for i in fabricLineTmp:
            if i in tileDic:
                fabricLine.append(deepcopy(tileDic[i]))
                usedTile.add(i)
            elif i == "Null" or i == "NULL" or i == "None":
                fabricLine.append(None)
            else:
                logger.error(f"Unknown tile {i}.")
                raise ValueError
        fabricTiles.append(fabricLine)

    for i in list(tileDic.keys()):
        if i not in usedTile:
            logger.info(
                f"Tile {i} is not used in the fabric. Removing from tile dictionary."
            )
            unusedTileDic[i] = tileDic[i]
            del tileDic[i]
    for i in list(superTileDic.keys()):
        if any(j.name not in usedTile for j in superTileDic[i].tiles):
            logger.info(
                f"Supertile {i} is not used in the fabric. Removing from tile dictionary."
            )
            unusedSuperTileDic[i] = superTileDic[i]
            del superTileDic[i]

    height = len(fabricTiles)
    width = len(fabricTiles[0])

    commonWirePair = list(dict.fromkeys(commonWirePair))
    commonWirePair = [
        (i, j) for (i, j) in commonWirePair if "NULL" not in i and "NULL" not in j
    ]

    return Fabric(
        tile=fabricTiles,
        numberOfColumns=width,
        numberOfRows=height,
        configBitMode=configBitMode,
        frameBitsPerRow=frameBitsPerRow,
        maxFramesPerCol=maxFramesPerCol,
        package=package,
        generateDelayInSwitchMatrix=generateDelayInSwitchMatrix,
        multiplexerStyle=multiplexerStyle,
        numberOfBRAMs=int(height / 2),
        superTileEnable=superTileEnable,
        tileDic=tileDic,
        superTileDic=superTileDic,
        unusedTileDic=unusedTileDic,
        unusedSuperTileDic=unusedSuperTileDic,
        commonWirePair=commonWirePair,
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
    ValueError
        Non matching matrix file content and tile name

    Returns
    -------
    dict : [str, list[str]]
        Dictionary from destination to a list of sources.
    """

    connectionsDic = {}
    with open(fileName) as f:
        file = f.read()
        file = re.sub(r"#.*", "", file)
        file = file.split("\n")

    if file[0].split(",")[0] != tileName:
        logger.error(f"{fileName} {file[0].split(',')} {tileName}")
        logger.error(
            "Tile name (top left element) in csv file does not match tile name in tile object"
        )
        raise ValueError
    destList = file[0].split(",")[1:]

    for i in file[1:]:
        i = i.split(",")
        portName, connections = i[0], i[1:]
        if portName == "":
            continue
        indices = [k for k, v in enumerate(connections) if v == "1"]
        connectionsDic[portName] = [destList[j] for j in indices]
    return connectionsDic


@overload
def parseList(
    filePath: Path, collect: Literal["pair"] = "pair", prefix: str = ""
) -> list[tuple[str, str]]:
    pass


@overload
def parseList(
    filePath: Path, collect: Literal["source", "sink"], prefix: str = ""
) -> dict[str, list[str]]:
    pass


def parseList(
    filePath: Path,
    collect: Literal["pair", "source", "sink"] = "pair",
    prefix: str = "",
) -> list[tuple[str, str]] | dict[str, list[str]]:
    """Parse a list file and expand the list file information into a list of tuples.

    Parameters
    ----------
    fileName : Path
        ""
    collect : (Literal["", "source", "sink"], optional)
        Collect value by source, sink or just as pair. Defaults to "pair".

    Raises
    ------
    ValueError
        The file does not exist.
    ValueError
        Invalid format in the list file.

    Returns
    -------
    Union : [list[tuple[str, str]], dict[str, list[str]]]
        Return either a list of connection pairs or a dictionary of lists which is collected by the specified option, source or sink.
    """
    if not filePath.exists():
        logger.error(f"The file {filePath} does not exist.")
        raise ValueError

    resultList = []
    with open(filePath) as f:
        file = f.read()
        file = re.sub(r"#.*", "", file)
    file = file.split("\n")
    for i, line in enumerate(file):
        line = line.replace(" ", "").replace("\t", "").split(",")
        line = [i for i in line if i != ""]
        if not line:
            continue
        if len(line) != 2:
            logger.error(f"Invalid list formatting in file: {filePath} at line {i}")
            logger.error(f"Line: {line}")
            raise ValueError
        left, right = line[0], line[1]

        if left == "INCLUDE":
            resultList.extend(parseList(filePath.parent.joinpath(right), "pair"))
            continue

        leftList = []
        rightList = []
        expandListPorts(left, leftList)
        expandListPorts(right, rightList)
        if len(leftList) != len(rightList):
            raise ValueError(
                f"List file {filePath} does not have the same number of source and sink ports."
            )
        resultList += list(zip(leftList, rightList, strict=False))

    result = list(dict.fromkeys(resultList))
    resultDic = {}
    if collect == "source":
        for k, v in result:
            if k not in resultDic:
                resultDic[k] = []
            resultDic[k].append(v)
        return resultDic

    if collect == "sink":
        for k, v in result:
            for i in v:
                if i not in resultDic:
                    resultDic[i] = []
                resultDic[i].append(k)
        return resultDic

    return result


def parsePortLine(line: str) -> tuple[list[Port], tuple[str, str] | None]:
    ports = []
    commonWirePair: tuple[str, str] | None
    temp: list[str] = line.split(",")
    if temp[0] in ["NORTH", "SOUTH", "EAST", "WEST"]:
        ports.append(
            Port(
                Direction[temp[0]],
                temp[1],
                int(temp[2]),
                int(temp[3]),
                temp[4],
                int(temp[5]),
                temp[1],
                IO.OUTPUT,
                Side[temp[0]],
            )
        )

        ports.append(
            Port(
                Direction[temp[0]],
                temp[1],
                int(temp[2]),
                int(temp[3]),
                temp[4],
                int(temp[5]),
                temp[4],
                IO.INPUT,
                Side[oppositeDic[temp[0]].upper()],
            )
        )
        commonWirePair = (f"{temp[1]}", f"{temp[4]}")

    elif temp[0] == "JUMP":
        ports.append(
            Port(
                Direction.JUMP,
                temp[1],
                int(temp[2]),
                int(temp[3]),
                temp[4],
                int(temp[5]),
                temp[1],
                IO.OUTPUT,
                Side.ANY,
            )
        )
        ports.append(
            Port(
                Direction.JUMP,
                temp[1],
                int(temp[2]),
                int(temp[3]),
                temp[4],
                int(temp[5]),
                temp[4],
                IO.INPUT,
                Side.ANY,
            )
        )
        commonWirePair = None
    else:
        logger.error(f"Unknown port type: {temp[0]}")
        raise ValueError("Unknown port type.")
    return (ports, commonWirePair)


def parseTiles(fileName: Path) -> tuple[list[Tile], list[tuple[str, str]]]:
    """Parses a CSV tile configuration file and returns all tile objects.

    Parameters
    ----------
    fileName : str
        The path to the CSV file.

    Returns
    -------
    Tuple[List[Tile], List[Tuple[str, str]]]
        A tuple containing a list of Tile objects and a list of common wire pairs.

    Raises
    ------
    ValueError : If the input csv file is not a CSV file.
    ValueError : If the input csv file does not exist.
    ValueError : If the BEL file is not a VHDL or Verilog file.
    ValueError : If GEN_IO pins are lower than 1
    ValueError : If a GEN_IO is a CONFIGACCESS and not an OUTPUT.
    ValueError : If a GEN_IO with the same prefix already exists in the tile.
    ValueError : If a GEN_IO is CLOCKED and CLOCKED_COMB at the same time.
    ValueError : If the MATRIX file is not a .list, .csv, .v, or .vhdl file.
    """
    logger.info(f"Reading tile configuration: {fileName}")

    if fileName.suffix != ".csv":
        logger.error("File must be a CSV file.")
        raise ValueError

    if not fileName.exists():
        logger.error(f"File {fileName} does not exist.")
        raise ValueError

    filePathParent = fileName.parent

    with open(fileName) as f:
        file = f.read()
        file = re.sub(r"#.*", "", file)

    tilesData = re.findall(r"TILE(.*?)EndTILE", file, re.MULTILINE | re.DOTALL)

    new_tiles = []
    commonWirePairs = []
    proj_dir = Path(os.getenv("FAB_PROJ_DIR"))

    # Parse each tile config
    for t in tilesData:
        t = t.split("\n")
        tileName = t[0].split(",")[1]
        ports: list[Port] = []
        bels: list[Bel] = []
        matrixDir: Path | None = None
        gen_ios: list[Gen_IO] = []
        withUserCLK = False
        configBit = 0
        genMatrixList = False
        tileCarry: dict[str, dict[IO, str]] = {}
        localSharedPorts: dict[str, list[Port]] = {}

        for item in t:
            temp: list[str] = item.split(",")
            if not temp or temp[0] == "":
                continue
            if temp[0] in ["NORTH", "SOUTH", "EAST", "WEST", "JUMP"]:
                port, commonWirePair = parsePortLine(item)
                if "CARRY" in temp[6]:
                    # For prefix after carry
                    carryPrefix = re.search(r'CARRY="([^"]+)"', temp[6])
                    if not carryPrefix:
                        carryPrefix = "FABulous_default"
                    else:
                        carryPrefix = carryPrefix.group(1)

                    if carryPrefix not in tileCarry:
                        tileCarry[carryPrefix] = {}
                        tileCarry[carryPrefix][IO.OUTPUT] = f"{temp[1]}0"
                        tileCarry[carryPrefix][IO.INPUT] = f"{temp[4]}0"
                    else:
                        raise ValueError(
                            f"There is already a carrychain with the prefix {carryPrefix}"
                        )
                if "SHARED_" in temp[6]:
                    if "JUMP" not in temp[0]:
                        logger.error(
                            "LOCAL SHARED_ Ports can only be used with JUMP ports."
                        )
                        raise ValueError
                    localShared = temp[6].split("_")[1]
                    if localShared is None or localShared == "":
                        logger.error("SHARED_ cannot be empty.")
                        raise ValueError
                    if localShared not in ["RESET", "ENABLE"]:
                        logger.error(
                            f"LOCAL SHARED_ port {localShared} is not supported. Only SHARED_RESET and SHARED_ENABLE are supported."
                        )
                        raise ValueError
                    if localShared not in localSharedPorts:
                        localSharedPorts[localShared] = port
                    else:
                        logger.error(
                            f"LOCAL SHARED_ port {localShared} already exists."
                        )
                        raise ValueError

                ports.extend(port)
                if commonWirePair:
                    commonWirePairs.append(commonWirePair)

            elif temp[0] == "BEL":
                belFilePath = filePathParent.joinpath(temp[1])
                if len(temp) > 2:  # bel prefix is provided
                    bel_prefix = temp[2]
                else:
                    bel_prefix = ""
                if temp[1].endswith(".vhdl"):
                    bels.append(parseBelFile(belFilePath, bel_prefix, "vhdl"))
                elif temp[1].endswith(".v") or temp[1].endswith(".sv"):
                    bels.append(parseBelFile(belFilePath, bel_prefix, "verilog"))
                    if "ADD_AS_CUSTOM_PRIM" in temp[4:]:
                        primsFile = proj_dir.joinpath("user_design/custom_prims.v")
                        logger.info(f"Adding bels to custom prims file: {primsFile}")
                        addBelsToPrim(primsFile, [bels[-1]])
                else:
                    logger.error(
                        f"Invalid file type in {belFilePath} only .vhdl and .v are supported."
                    )
                    raise ValueError
            elif temp[0] == "GEN_IO":
                configBit = 0
                configAccess = False
                inverted = False
                clocked = False
                clockedComb = False
                clockedMux = False
                pins = int(temp[1])
                if pins <= 0:
                    logger.error(f"GEN_IO pins must be greater than 0, but is {pins}")
                    raise ValueError
                # Additional params can be added
                for param in temp[4:]:
                    param = param.strip()
                    param = param.upper()

                    if param == "CONFIGACCESS":
                        if temp[2] != "OUTPUT":
                            logger.error(
                                "CONFIGACCESS GEN_IO can only be used with OUTPUT"
                            )
                            raise ValueError
                        configAccess = True
                        configBit = int(temp[1])
                    elif param == "INVERTED":
                        inverted = True
                    elif param == "CLOCKED":
                        clocked = True
                    elif param == "CLOCKED_COMB":
                        clockedComb = True
                    elif param == "CLOCKED_MUX":
                        clockedMux = True
                        configBit = int(temp[1])
                    elif param is None or param == "":
                        continue
                    else:
                        logger.error(f"Unknown parameter {param} in GEN_IO")
                        raise ValueError

                    if configAccess and (clocked or clockedComb or clockedMux):
                        logger.error("CONFIGACCESS GEN_IO can not be clocked")
                        raise ValueError
                    if sum([clocked, clockedComb, clockedMux]) > 1:
                        logger.error(
                            "CLOCKED, CLOCKED_COMB or CLOCKED_MUX can not be combined for one GEN_IO"
                        )
                        raise ValueError

                if temp[3] not in (gio.prefix for gio in gen_ios):
                    gen_ios.append(
                        Gen_IO(
                            temp[3],
                            int(temp[1]),
                            IO[temp[2]],
                            configBit,
                            configAccess,
                            inverted,
                            clocked,
                            clockedComb,
                            clockedMux,
                        )
                    )
                else:
                    logger.error(
                        f"GEN_IO with prefix {temp[3]} already exists in tile {tileName}."
                    )
                    raise ValueError
            elif temp[0] == "MATRIX":
                configBit = 0

                if "GENERATE" in temp:
                    # import here to avoid circular import
                    from FABulous.fabric_generator.fabric_automation import (
                        generateSwitchmatrixList,
                    )

                    logger.info(f"Generating switch matrix list for tile {tileName}")
                    genMatrixList = True
                    if len(temp) <= 2:
                        # only MATRIX, GENERATE in csv
                        matrixDir = fileName.parent
                    else:
                        matrixDir = fileName.parent.joinpath(temp[2])
                    if matrixDir.is_file() and matrixDir.suffix == ".list":
                        logger.warning(
                            f"Matrix file {matrixDir} already exists and will be overwritten."
                        )
                    elif matrixDir.parent == proj_dir.joinpath("Tile"):
                        matrixDir = matrixDir.joinpath(
                            f"{tileName}_generated_switch_matrix.list"
                        )
                        logger.info(f"Generating matrix file {matrixDir}")
                    else:
                        matrixDir = proj_dir.joinpath(
                            f"./Tile/{tileName}/{tileName}_generated_switch_matrix.list"
                        )
                        logger.warning(
                            f"No destination directory for matrix file sepicified, using default path {matrixDir}."
                        )
                        if not matrixDir.parent.exists():
                            matrixDir.parent.mkdir(parents=True)
                            logger.warning(f"Creating directory {matrixDir.parent}.")

                else:
                    matrixDir = fileName.parent.joinpath(temp[1])
                    match matrixDir.suffix:
                        case ".list":
                            for _, v in parseList(matrixDir, "source").items():
                                muxSize = len(v)
                                if muxSize >= 2:
                                    configBit += (muxSize - 1).bit_length()
                        case "_matrix.csv":
                            for _, v in parseMatrix(matrixDir, tileName).items():
                                muxSize = len(v)
                                if muxSize >= 2:
                                    configBit += (muxSize - 1).bit_length()
                        case ".vhdl" | ".v":
                            with open(matrixDir) as f:
                                f = f.read()
                                if configBit := re.search(
                                    r"NumberOfConfigBits: (\d+)", f
                                ):
                                    configBit = int(configBit.group(1))
                                else:
                                    configBit = 0
                                    logger.warning(
                                        f"Cannot find NumberOfConfigBits in {matrixDir} assume 0 config bits."
                                    )
                        case _:
                            logger.error("Unknown file extension for matrix.")
                            raise ValueError("Unknown file extension for matrix.")

            elif temp[0] == "INCLUDE":
                p = fileName.parent.joinpath(temp[1])
                if not p.exists():
                    logger.error(f"Cannot find {str(p)} in tile {tileName}")
                    raise ValueError
                with open(p) as f:
                    iFile = f.read()
                    iFile = re.sub(r"#.*", "", iFile)
                for line in iFile.split("\n"):
                    lineItem = line.split(",")
                    if not lineItem[0]:
                        continue

                    port, commonWirePair = parsePortLine(line)
                    ports.extend(port)
                    if commonWirePair:
                        commonWirePairs.append(commonWirePair)

            else:
                logger.error(f"Unknown tile description {temp[0]} in tile {t}.")
                raise ValueError

            withUserCLK = any(bel.withUserCLK for bel in bels)

            if genMatrixList:
                generateSwitchmatrixList(
                    tileName, bels, matrixDir, tileCarry, localSharedPorts
                )
                for _, v in parseList(matrixDir, "source").items():
                    muxSize = len(v)
                    if muxSize >= 2:
                        configBit += (muxSize - 1).bit_length()

            new_tiles.append(
                Tile(
                    name=tileName,
                    ports=ports,
                    bels=bels,
                    tileDir=fileName,
                    matrixDir=matrixDir,
                    gen_ios=gen_ios,
                    userCLK=withUserCLK,
                    configBit=configBit,
                )
            )

    return (new_tiles, commonWirePairs)


def parseSupertiles(fileName: Path, tileDic: dict[str, Tile]) -> list[SuperTile]:
    """Parses a CSV supertile configuration file and returns all SuperTile objects.

    Parameters
    ----------
    fileName : str
        The path to the CSV file.
    tileDic : Dict[str, Tile]
        Dict of tiles.

    Returns
    -------
    List[SuperTile]
        List of SuperTile objects.
    """
    logger.info(f"Reading supertile configuration: {fileName}")

    if not fileName.suffix == ".csv":
        logger.error("File must be a csv file.")
        raise ValueError

    if not fileName.exists():
        logger.error(f"File {fileName} does not exist.")
        raise ValueError

    filePath = fileName.parent

    with open(fileName) as f:
        file = f.read()
        file = re.sub(r"#.*", "", file)

    superTilesData = re.findall(
        r"SuperTILE(.*?)EndSuperTILE", file, re.MULTILINE | re.DOTALL
    )

    new_supertiles = []

    # Parse each supertile config
    for t in superTilesData:
        description = t.split("\n")
        name = description[0].split(",")[1]
        tileMap = []
        tiles = []
        bels = []
        withUserCLK = False
        for i in description[1:-1]:
            line = i.split(",")
            line = [i for i in line if i != "" and i != " "]
            row = []

            if line[0] == "BEL":
                belFilePath = filePath.joinpath(line[1])
                if line[1].endswith(".vhdl"):
                    bels.append(parseBelFile(belFilePath, line[2], "vhdl"))
                elif line[1].endswith(".v") or line[1].endswith(".sv"):
                    bels.append(parseBelFile(belFilePath, line[2], "verilog"))
                else:
                    raise ValueError(
                        f"Invalid file type in {belFilePath} only .vhdl and .v are supported."
                    )
                continue

            for j in line:
                if j in tileDic:
                    # mark the tile as part of super tile
                    tileDic[j].partOfSuperTile = True
                    t = deepcopy(tileDic[j])
                    row.append(t)
                    if t not in tiles:
                        tiles.append(t)
                elif j == "Null" or j == "NULL" or j == "None":
                    row.append(None)
                else:
                    logger.error(
                        f"The super tile {name} contains definitions that are not tiles or Null."
                    )
                    raise ValueError
            tileMap.append(row)

        withUserCLK = any(bel.withUserCLK for bel in bels)
        new_supertiles.append(SuperTile(name, tiles, tileMap, bels, withUserCLK))

    return new_supertiles


def parseBelFile(
    filename: Path,
    belPrefix: str = "",
    filetype: Literal["verilog", "vhdl"] = "",
) -> Bel:
    """Parse a Verilog or VHDL bel file and return all the related information of the
    bel. The tuple returned for relating to ports will be a list of (belName, IO) pair.

    The function will also parse and record all the FABulous attribute which all starts with ::

        (* FABulous, <type>, ... *)

    The <type> can be one the following:

    * **BelMap**
    * **EXTERNAL**
    * **SHARED_PORT**
    * **GLOBAL**
    * **CONFIG_PORT**
    * **SHARED_ENABLE**
    * **SHARED_RESET**

    The **BelMap** attribute will specify the bel mapping for the bel. This attribute should be placed before the start of
    the module The bel mapping is then used for generating the bitstream specification. Each of the entry in the attribute will have the following format::

    <name> = <value>

    ``<name>`` is the name of the feature and ``<value>`` will be the bit position of the feature. ie. ``INIT=0`` will specify that the feature ``INIT`` is located at bit 0.
    Since a single feature can be mapped to multiple bits, this is currently done by specifying multiple entries for the same feature. This will be changed in the future.
    The bit specification is done in the following way::

        INIT_a_1=1, INIT_a_2=2, ...

    The name of the feature will be converted to ``INIT_a[1]``, ``INIT_a[2]`` for the above example. This is necessary
    because  Verilog does not allow square brackets as part of the attribute name.

    **EXTERNAL** attribute will notify FABulous to put the pin in the top module during the fabric generation.

    **SHARED_PORT** attribute will notify FABulous this the pin is shared between multiple bels. Attribute need to go with
    the **EXTERNAL** attribute.

    **GLOBAL** attribute will notify FABulous to stop parsing any pin after this attribute.

    **CONFIG_PORT** attribute will notify FABulous the port is for configuration.

    Example
    -------
    Verilog
    ::

        (* FABulous, BelMap,
        single_bit_feature=0, //single bit feature, single_bit_feature=0
        multiple_bits_0=1, //multiple bit feature bit0, multiple_bits[0]=1
        multiple_bits_1=2 //multiple bit feature bit1, multiple_bits[1]=2
        *)
        module exampleModule (externalPin, normalPin1, normalPin2, sharedPin, globalPin);
            (* FABulous, EXTERNAL *) input externalPin;
            input normalPin;
            (* FABulous, EXTERNAL, SHARED_PORT *) input sharedPin;
            (* FABulous, GLOBAL) input globalPin;
            output normalPin2; //do not get parsed
            ...

    Parameters
    ----------
        filename : str
            The filename of the bel file.
        belPrefix : str, optional)
            The bel prefix provided by the CSV file. Defaults to "".

    Returns
    -------
    Tuple containing
        - List of Bel Internal ports (belName, IO).
        - List of Bel External ports (belName, IO).
        - List of Bel Config ports (belName, IO).
        - List of Bel Shared ports (belName, IO).
        - Number of configuration bits in the bel.
        - Whether the bel has UserCLK.
        - Bel config bit mapping as a dict {port_name: bit_number}.

    Raises
    ------
    ValueError
        File not found
    ValueError
        No permission to access the file
    ValueError
        Bel file contains no or more than one module
    """
    internal: list[tuple[str, IO]] = []
    external: list[tuple[str, IO]] = []
    config: list[tuple[str, IO]] = []
    shared: list[tuple[str, IO]] = []
    localSharedPorts: dict[str, tuple[str, IO]] = {}
    belMapDic = {}
    carry: dict[str, dict[IO, str]] = {}
    carryPrefix: str = ""
    isExternal = False
    isConfig = False
    isShared = False
    userClk = False
    individually_declared = False
    noConfigBits = 0
    belMapDic = {}
    ports_vectors: dict[str, dict[str, tuple[IO, int]]] = (
        {}
    )  # {<porttype>:{porname:(IO, size)}}
    # define port types
    ports_vectors["internal"] = {}
    ports_vectors["external"] = {}
    ports_vectors["config"] = {}
    ports_vectors["shared"] = {}
    module_name = ""

    if filetype not in ["verilog", "vhdl"]:
        raise ValueError(f"Invalid filetype {filetype} for bel file {filename}")

    try:
        with open(filename) as f:
            file = f.read()
    except FileNotFoundError:
        logger.critical(f"File {filename} not found.")
        exit(-1)
    except PermissionError:
        logger.critical(f"Permission denied to file {filename}.")
        exit(-1)

    if filetype == "vhdl":
        module_name = (
            filename.stem
        )  # FIXME: Temporary, till we have GHDL-Yosys integration
        belMapDic = vhdl_belMapProcessing(file, filename)
        if result := re.search(r"NoConfigBits.*?=.*?(\d+)", file, re.IGNORECASE):
            noConfigBits = int(result.group(1))
        else:
            logger.warning(f"Cannot find NoConfigBits in {filename}")
            logger.warning("Assume the number of configBits is 0")
            noConfigBits = 0
        if len(belMapDic) != noConfigBits:
            logger.error(
                f"NoConfigBits does not match with the BEL map in file {filename}, length of BelMap is {len(belMapDic)}, but with {noConfigBits} config bits"
            )
            raise ValueError

        # FIXME: This is a temporary fix for the issue, that our vhdl parser can't handle vectors
        portmatch = file.split("-- GLOBAL")[0].lower()
        portmatch = portmatch[portmatch.find("port") :]  # trim everything before port
        if any(
            s in portmatch
            for s in ["std_logic_vector", "bit_vector", "integer", "signed", "unsigned"]
        ):
            raise ValueError(
                f"Unsupported port type in {filename}. \
                 Currtently only std_logic ports are supported for VHDL bels."
            )

        if result := re.search(
            r"port.*?\((.*?)\);", file, re.MULTILINE | re.DOTALL | re.IGNORECASE
        ):
            file, _ = result.group(1).split("-- GLOBAL")
        else:
            raise ValueError(f"Could not find port section in file {filename}")

        for line in file.split("\n"):
            result = line
            result = re.sub(r"STD_LOGIC.*|;.*|--*", "", result, flags=re.IGNORECASE)
            result = result.replace(" ", "").replace("\t", "").replace(";", "")
            portName = ""
            direction = None
            if "IMPORTANT" in line:
                continue
            if result := re.search(r"(.*):(.*)", result):
                portName = f"{belPrefix}{result.group(1)}"
                if result.group(2).upper() == "IN":
                    direction = IO["INPUT"]
                elif result.group(2).upper() == "OUT":
                    direction = IO["OUTPUT"]
                elif result.group(2).upper() == "INOUT":
                    direction = IO["INOUT"]
                else:
                    logger.error(
                        f"Invalid or Unknown port direction {result.group(2).upper()} in line {line}."
                    )
                    raise ValueError
            else:
                continue
            if line:
                if "EXTERNAL" in line:
                    isExternal = True
                if "CONFIG" in line:
                    isConfig = True
                if "SHARED_PORT" in line:
                    isShared = True
                if "CARRY" in line:
                    # For prefix after carry
                    carryPrefix = re.search(r'CARRY="([^"]+)"', line)
                    if not carryPrefix:
                        carryPrefix = "FABulous_default"
                    else:
                        carryPrefix = carryPrefix.group(1)
                if "SHARED_ENABLE" in line or "SHARED_RESET" in line:
                    if direction is not IO["INPUT"]:
                        logger.error(
                            "SHARED_ENABLE or SHARED_RESET can only be used with INPUT ports."
                        )
                        raise ValueError
                    if "SHARED_ENABLE" in line:
                        localSharedPorts["ENABLE"] = (portName, direction)
                    elif "SHARED_RESET" in line:
                        localSharedPorts["RESET"] = (portName, direction)

                if "GLOBAL" in line:
                    break

            if portName == "" or direction is None:
                logger.warning(f"Invalid port definition in line {line}.")
                continue
            if isExternal and not isShared:
                external.append((portName, direction))
            elif isConfig:
                config.append((portName, direction))
            elif isShared:
                # shared port do not have a prefix
                shared.append((portName.removeprefix(belPrefix), direction))
            else:
                internal.append((portName, direction))

            # FIXME: This is a temporary fix for the issue, that our vhdl parser can't handle vectors
            if portName[-1].isdigit():
                individually_declared = True

            if "UserCLK" in portName:
                userClk = True

            if carryPrefix:
                if direction is IO["INOUT"]:
                    raise ValueError(
                        f"CARRY can't be used with INOUT ports for port {portName}!"
                    )
                if carryPrefix not in carry:
                    carry[carryPrefix] = {}
                if direction not in carry[carryPrefix]:
                    carry[carryPrefix][direction] = portName
                else:
                    raise ValueError(
                        f"Port {portName} with prefix {carryPrefix} can't be a carry {direction}, \
                        since port {carry[carryPrefix][direction]} already is!"
                    )

            isExternal = False
            isConfig = False
            isShared = False
            carryPrefix = ""

    if filetype == "verilog":
        # Runs yosys on verilog file, creates netlist, saves to json in same directory.
        json_file = filename.with_suffix(".json")
        runCmd = [
            "yosys",
            f"-qpread_verilog -sv {filename}; proc -noopt; write_json -compat-int {json_file}",
        ]

        result = subprocess.run(runCmd, check=True)
        if result.returncode != 0:
            logger.opt(exception=FabricParsingError()).error(
                "Failed to run yosys command: {e}"
            )

        with open(f"{json_file}") as f:
            data_dict = json.load(f)

        modules = data_dict.get("modules", {})
        filtered_ports: dict[str, tuple[IO, list]] = {}

        if len(modules) == 0:
            logger.opt(exception=FabricParsingError()).error(
                f"File {filename} does not contain any modules."
            )
        elif len(modules) > 1:
            logger.opt(exception=FabricParsingError()).error(
                f"File {filename} contains more than one module."
            )

        # Gathers port name and direction, filters out configbits as they show in ports.
        for module_name, module_info in modules.items():
            ports = module_info["ports"]
            for port_name, details in ports.items():
                if "ConfigBits" in port_name:
                    continue
                if "UserCLK" in port_name:
                    userClk = True
                if port_name[-1].isdigit():
                    # FIXME:  This is a temporary fix for the issue where the ports are individually declared
                    #         Check for the last charcter in portname is not really reliable and sould be handeled more rubust in the future.
                    individually_declared = True
                direction = IO[details["direction"].upper()]
                bits = details.get("bits", [])
                filtered_ports[port_name] = (direction, bits)

        param_defaults = module_info.get("parameter_default_values")
        if param_defaults and "NoConfigBits" in param_defaults:
            noConfigBits = param_defaults["NoConfigBits"]
        # Passed attributes dont show in port list, checks for attributes in netnames.
        # (If passed attributes missing, may need to expand to check other lists e.g "memories".)
        netnames = module_info.get("netnames", {})
        for portName, (direction, bits) in filtered_ports.items():
            netDetails = netnames.get(portName, {})
            attributes = netDetails.get("attributes", {})
            # Unrolled Ports
            for index in range(len(bits)):
                new_port_name = (
                    f"{portName}{index}" if len(bits) > 1 else portName
                )  # Multi-bit ports get index
                if "EXTERNAL" in attributes and "SHARED_PORT" not in attributes:
                    external.append((f"{belPrefix}{new_port_name}", direction))
                elif "CONFIG" in attributes:
                    config.append((f"{belPrefix}{new_port_name}", direction))
                elif "SHARED_PORT" in attributes:
                    shared.append((new_port_name, direction))
                else:
                    internal.append((f"{belPrefix}{new_port_name}", direction))

                if "SHARED_ENABLE" in attributes or "SHARED_RESET" in attributes:
                    if direction is not IO["INPUT"]:
                        logger.error(
                            "SHARED_ENABLE or SHARED_RESET can only be used with INPUT ports."
                        )
                        raise ValueError
                    if "SHARED_ENABLE" in attributes:
                        localSharedPorts["ENABLE"] = (
                            f"{belPrefix}{new_port_name}",
                            direction,
                        )
                    elif "SHARED_RESET" in attributes:
                        localSharedPorts["RESET"] = (
                            f"{belPrefix}{new_port_name}",
                            direction,
                        )

                if "CARRY" in attributes:
                    # For prefix after carry
                    carryPrefix = attributes.get("CARRY")
                    if carryPrefix == 1:
                        # Default carry prefix, yosys uses 1 if no value is specified
                        carryPrefix = "FABulous_default"
                    if direction is IO["INOUT"]:
                        raise ValueError(
                            f"CARRY can't be used with INOUT ports for port {new_port_name}!"
                        )
                    if carryPrefix not in carry:
                        carry[carryPrefix] = {}
                    if direction not in carry[carryPrefix]:
                        carry[carryPrefix][direction] = f"{belPrefix}{new_port_name}"
                    else:
                        raise ValueError(
                            f"Port {portName} with prefix {carryPrefix} can't be a carry {direction}, \
                            since port {carry[carryPrefix][direction]} already is!"
                        )

            # Port vectors:
            if "EXTERNAL" in attributes and "SHARED_PORT" not in attributes:
                ports_vectors["external"][portName] = (direction, len(bits))
            elif "CONFIG" in attributes:
                ports_vectors["config"][portName] = (direction, len(bits))
            elif "SHARED_PORT" in attributes:
                ports_vectors["shared"][portName] = (direction, len(bits))
            else:
                ports_vectors["internal"][portName] = (direction, len(bits))

        belMapDic = verilog_belMapProcessing(module_info)
        if len(belMapDic) != noConfigBits:
            raise ValueError(
                f"NoConfigBits does not match with the BEL map in file {filename}, length of BelMap is {len(belMapDic)}, but with {noConfigBits} config bits"
            )

    if individually_declared and filetype == "verilog":
        logger.warning(
            f"Ports in {filename} have been individually declared rather than as a vector."
        )
        logger.warning("Ports will not be concatenated during fabric generation.")
    return Bel(
        src=filename,
        filetype=filetype,
        prefix=belPrefix,
        module_name=module_name,
        internal=internal,
        external=external,
        configPort=config,
        sharedPort=shared,
        configBit=noConfigBits,
        belMap=belMapDic,
        userCLK=userClk,
        individually_declared=individually_declared,
        ports_vectors=ports_vectors,
        carry=carry,
        localShared=localSharedPorts,
    )


def verilog_belMapProcessing(module_info):
    """Extracts and transforms BEL mapping attributes in the JSON created from a Verilog
    module.

    Parameters
    ----------
    module_info : dict
        A dictionary containing the module's attributes, including
        potential BEL mapping information.

    Returns
    -------
    dic
        Dictionary containing the parsed bel mapping information.
    """
    belMapDic = {}
    attributes = module_info.get("attributes", {})
    # if BelMap not present defaults belMapDic to {}
    if "BelMap" not in attributes:
        return belMapDic
    # Passed attributes that dont need appending. (May need refining.)
    exclude_attributes = {
        "BelMap",
        "FABulous",
        "dynports",
        "cells_not_processed",
        "src",
    }
    # match case for INIT. (may need modifying for other naming conventions.)
    for key, value in attributes.items():
        if key in exclude_attributes:
            continue
        match key:
            case key if key.startswith("INIT_") and key[5:].isdigit():
                index = key[5:]
                new_key = f"INIT[{index}]"
            case "INIT":
                new_key = "INIT"
            case key if key.isupper() and "_" not in key:
                new_key = key
            case _:
                new_key = key

        belMapDic[new_key] = {0: {0: "1"}}

    # yosys reverses belmap, reverse back to keep original belmap.
    belMapDic = dict(reversed(list(belMapDic.items())))

    return belMapDic


def vhdl_belMapProcessing(file: str, filename: str) -> dict:
    """Processes bel mapping information from file contents.

    Parameters
    ----------
    file : str
        Conent of the file as a string
    filename : str
        Name of the file being processed
    syntax : Literal['vhdl']
        Syntax type of the file.

    Returns
    -------
    dict
        Dictionary containing the parsed bel mapping information.

    Raises
    ------
    ValueError
        If invalid enum is encounted in the file.
    """
    pre = "--.*?"

    belEnumsDic = {}
    if belEnums := re.findall(
        pre + r"\(\*.*?FABulous,.*?BelEnum,(.*?)\*\)", file, re.DOTALL | re.MULTILINE
    ):
        for enums in belEnums:
            enums = enums.replace("\n", "").replace(" ", "").replace("\t", "")
            enums = enums.split(",")
            enums = [i for i in enums if i != "" and i != " "]
            if enumParse := re.search(r"(.*?)\[(\d+):(\d+)\]", enums[0]):
                name = enumParse.group(1)
                start = int(enumParse.group(2))
                end = int(enumParse.group(3))
            else:
                logger.error(f"Invalid enum {enums[0]} in file {filename}")
                raise ValueError
            belEnumsDic[name] = {}
            for i in enums[1:]:
                key, value = i.split("=")
                belEnumsDic[name][key] = {}
                bitValue = list(value)
                if start > end:
                    for j in range(start, end - 1, -1):
                        belEnumsDic[name][key][j] = bitValue.pop(0)
                else:
                    for j in range(start, end + 1):
                        belEnumsDic[name][key][j] = bitValue.pop(0)

    belMapDic = {}
    if belMap := re.search(
        pre + r"\(\*.*FABulous,.*?BelMap,(.*?)\*\)", file, re.DOTALL | re.MULTILINE
    ):
        belMap = belMap.group(1)
        belMap = belMap.replace("\n", "").replace(" ", "").replace("\t", "")
        belMap = belMap.split(",")
        belMap = [i for i in belMap if i != "" and i != " "]
        for bel in belMap:
            bel = bel.split("=")
            belNameTemp = bel[0].rsplit("_", 1)
            # process scalar
            if len(belNameTemp) > 1 and belNameTemp[1].isnumeric():
                bel[0] = f"{belNameTemp[0]}[{belNameTemp[1]}]"
            belMapDic[bel[0]] = {}
            if bel == [""]:
                continue
            # process enum data type
            if bel[0] in list(belEnumsDic.keys()):
                belMapDic[bel[0]] = belEnumsDic[bel[0]]
            # process vector input
            elif ":" in bel[1]:
                start, end = bel[1].split(":")
                start, end = int(start), int(end)
                if start > end:
                    length = start - end + 1
                    for i in range(2**length - 1, -1, -1):
                        belMapDic[bel[0]][i] = {}
                        bitMap = list(f"{i:0{length.bit_length()}b}")
                        for v in range(len(bitMap) - 1, -1, -1):
                            belMapDic[bel[0]][i][v] = bitMap.pop(0)
                else:
                    length = end - start + 1
                    for i in range(2**length):
                        belMapDic[bel[0]][i] = {}
                        bitMap = list(f"{2**length - i - 1:0{length.bit_length()}b}")
                        for v in range(len(bitMap) - 1, -1, -1):
                            belMapDic[bel[0]][i][v] = bitMap.pop(0)
            else:
                belMapDic[bel[0]][0] = {0: "1"}
    return belMapDic


def parseConfigMem(
    fileName: Path,
    maxFramePerCol: int,
    frameBitPerRow: int,
    globalConfigBits: int,
) -> list[ConfigMem]:
    """Parse the config memory CSV file into a list of ConfigMem objects.

    Parameters
    ----------
    fileName : str
        Directory of the config memory CSV file
    maxFramePerCol : int
        Maximum number of frames per colum
    frameBitPerRow : int
        Number of bits per row
    globalConfigBits : int
        Number of global config bits for the config memory

    Raises
    ------
    ValueError
        - Invalid amount of frame entries in the config memory CSV file
        - Too many values in bit mask
        - Length of bit mask does not match the number of frame bits per row
        - Bit mask does not have enough values matching the number of the given config bits
        - Repeated config bit entry in ':' separated format in config bit range
        - Repeated config bit entry in list format in config bit range
        - Invalid range entry in config bit range

    Returns
    -------
    list[ConfigMem]
        List of ConfigMem objects parsed from the config memory CSV file.
    """
    with open(fileName) as f:
        mappingFile = list(csv.DictReader(f))

        # remove the pretty print from used_bits_mask
        for i, _ in enumerate(mappingFile):
            mappingFile[i]["used_bits_mask"] = mappingFile[i]["used_bits_mask"].replace(
                "_", ""
            )

        # we should have as many lines as we have frames (=framePerCol)
        if len(mappingFile) != maxFramePerCol:
            logger.error(
                f"The bitstream mapping file has only {len(mappingFile)} entries but MaxFramesPerCol is {maxFramePerCol}."
            )
            raise ValueError

        # we also check used_bits_mask (is a vector that is as long as a frame and contains a '1' for a bit used and a '0' if not used (padded)
        usedBitsCounter = 0
        for entry in mappingFile:
            if entry["used_bits_mask"].count("1") > frameBitPerRow:
                logger.error(
                    f"bitstream mapping file {fileName} has to many 1-elements in bitmask for frame : {entry['frame_name']}"
                )
                raise ValueError
            if len(entry["used_bits_mask"]) != frameBitPerRow:
                logger.error(
                    f"bitstream mapping file {fileName} has has a too long or short bitmask for frame : {entry['frame_name']}"
                )
                raise ValueError
            usedBitsCounter += entry["used_bits_mask"].count("1")

        if usedBitsCounter != globalConfigBits:
            logger.error(
                f"bitstream mapping file {fileName} has a bitmask mismatch; bitmask has in total {usedBitsCounter} 1-values for {globalConfigBits} bits."
            )
            raise ValueError

        allConfigBitsOrder = []
        configMemEntry = []
        for entry in mappingFile:
            configBitsOrder = []
            entry["ConfigBits_ranges"] = (
                entry["ConfigBits_ranges"].replace(" ", "").replace("\t", "")
            )

            if ":" in entry["ConfigBits_ranges"]:
                left, right = re.split(":", entry["ConfigBits_ranges"])
                # check the order of the number, if right is smaller than left, then we swap them
                left, right = int(left), int(right)
                if right < left:
                    left, right = right, left
                    numList = list(reversed(range(left, right + 1)))
                else:
                    numList = list(range(left, right + 1))

                for i in numList:
                    if i in allConfigBitsOrder:
                        logger.error(
                            f"Configuration bit index {i} already allocated in {fileName}, {entry['frame_name']}."
                        )
                        raise ValueError
                    configBitsOrder.append(i)

            elif ";" in entry["ConfigBits_ranges"]:
                for item in entry["ConfigBits_ranges"].split(";"):
                    if int(item) in allConfigBitsOrder:
                        logger.error(
                            f"Configuration bit index {item} already allocated in {fileName}, {entry['frame_name']}."
                        )
                        raise ValueError
                    configBitsOrder.append(int(item))

            elif "NULL" in entry["ConfigBits_ranges"]:
                continue

            else:
                logger.error(
                    f"Range {entry['ConfigBits_ranges']} is not a valid format. It should be in the form [int]:[int] or [int]. If there are multiple ranges it should be separated by ';'."
                )
                raise ValueError

            allConfigBitsOrder += configBitsOrder

            if entry["used_bits_mask"].count("1") > 0:
                configMemEntry.append(
                    ConfigMem(
                        frameName=entry["frame_name"],
                        frameIndex=int(entry["frame_index"]),
                        bitsUsedInFrame=entry["used_bits_mask"].count("1"),
                        usedBitMask=entry["used_bits_mask"],
                        configBitRanges=configBitsOrder,
                    )
                )

    return configMemEntry

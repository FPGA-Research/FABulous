import csv
import os
import pathlib
import re
import subprocess
import json
from sys import prefix
from loguru import logger
from copy import deepcopy

from typing import Literal, overload
from FABulous.fabric_generator.utilities import expandListPorts
from FABulous.fabric_definition.Bel import Bel
from FABulous.fabric_definition.Port import Port
from FABulous.fabric_definition.Wire import Wire
from FABulous.fabric_definition.Tile import Tile
from FABulous.fabric_definition.SuperTile import SuperTile
from FABulous.fabric_definition.Fabric import Fabric
from FABulous.fabric_definition.ConfigMem import ConfigMem
from FABulous.fabric_definition.define import (
    IO,
    Direction,
    Side,
    ConfigBitMode,
    MultiplexerStyle,
)


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

    fName = pathlib.Path(fileName)
    if fName.suffix != ".csv":
        logger.error("File must be a csv file")
        raise ValueError

    if not fName.exists():
        logger.error(f"File {fName} does not exist.")
        raise ValueError

    filePath = fName.parent

    with open(fName, "r") as f:
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

    # list for supertiles
    superTileDic = {}

    # For backwards compatibility parse tiles in fabric config
    new_tiles, new_commonWirePair = parseTiles(fName)
    tileTypes += [new_tile.name for new_tile in new_tiles]
    tileDefs += new_tiles
    commonWirePair += new_commonWirePair
    tileDic = dict(zip(tileTypes, tileDefs))

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
            new_tiles, new_commonWirePair = parseTiles(filePath.joinpath(i[1]))
            tileTypes += [new_tile.name for new_tile in new_tiles]
            tileDefs += new_tiles
            commonWirePair += new_commonWirePair
            tileDic = dict(zip(tileTypes, tileDefs))
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
            del tileDic[i]
    for i in list(superTileDic.keys()):
        if any(j.name not in usedTile for j in superTileDic[i].tiles):
            logger.info(
                f"Supertile {i} is not used in the fabric. Removing from tile dictionary."
            )
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
        commonWirePair=commonWirePair,
    )


def parseMatrix(fileName: pathlib.Path, tileName: str) -> dict[str, list[str]]:
    """Parse the matrix CSV into a dictionary from destination to source.

    Parameters
    ----------
    fileName : pathlib.Path
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
    with open(fileName, "r") as f:
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
    filePath: pathlib.Path, collect: Literal["pair"] = "pair", prefix: str = ""
) -> list[tuple[str, str]]:
    pass


@overload
def parseList(
    filePath: pathlib.Path, collect: Literal["source", "sink"], prefix: str = ""
) -> dict[str, list[str]]:
    pass


def parseList(
    filePath: pathlib.Path,
    collect: Literal["pair", "source", "sink"] = "pair",
    prefix: str = "",
) -> list[tuple[str, str]] | dict[str, list[str]]:
    """Parse a list file and expand the list file information into a list of tuples.

    Parameters
    ----------
    fileName : pathlib.Path
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
    with open(filePath, "r") as f:
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
        resultList += list(zip(leftList, rightList))

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


def parseTiles(fileName: pathlib.Path) -> tuple[list[Tile], list[tuple[str, str]]]:
    """Parses a CSV tile configuration file and returns all tile objects.

    Parameters
    ----------
    fileName : str
        The path to the CSV file.

    Returns
    -------
    Tuple[List[Tile], List[Tuple[str, str]]]
        A tuple containing a list of Tile objects and a list of common wire pairs.
    """

    logger.info(f"Reading tile configuration: {fileName}")

    if fileName.suffix != ".csv":
        logger.error("File must be a CSV file.")
        raise ValueError

    if not fileName.exists():
        logger.error(f"File {fileName} does not exist.")
        raise ValueError

    filePathParent = fileName.parent

    with open(fileName, "r") as f:
        file = f.read()
        file = re.sub(r"#.*", "", file)

    tilesData = re.findall(r"TILE(.*?)EndTILE", file, re.MULTILINE | re.DOTALL)

    new_tiles = []
    commonWirePairs = []

    # Parse each tile config
    for t in tilesData:
        t = t.split("\n")
        tileName = t[0].split(",")[1]
        ports: list[Port] = []
        bels: list[Bel] = []
        matrixDir: pathlib.Path | None = None
        withUserCLK = False
        configBit = 0
        for item in t:
            temp: list[str] = item.split(",")
            if not temp or temp[0] == "":
                continue
            if temp[0] in ["NORTH", "SOUTH", "EAST", "WEST", "JUMP"]:
                port, commonWirePair = parsePortLine(item)
                ports.extend(port)
                if commonWirePair:
                    commonWirePairs.append(commonWirePair)
            elif temp[0] == "BEL":
                belFilePath = filePathParent.joinpath(temp[1])
                if temp[1].endswith(".vhdl"):
                    bels.append(parseBelFile(belFilePath, temp[2], "vhdl"))
                elif temp[1].endswith(".v"):
                    bels.append(parseBelFile(belFilePath, temp[2], "verilog"))
                else:
                    raise ValueError(
                        f"Invalid file type in {belFilePath} only .vhdl and .v are supported."
                    )
            elif temp[0] == "MATRIX":
                matrixDir = fileName.parent.joinpath(temp[1])
                configBit = 0

                match matrixDir.suffix:
                    case ".list":
                        for _, v in parseList(matrixDir, "source").items():
                            muxSize = len(v)
                            if muxSize >= 2:
                                configBit += muxSize.bit_length() - 1
                    case "_matrix.csv":
                        for _, v in parseMatrix(matrixDir, tileName).items():
                            muxSize = len(v)
                            if muxSize >= 2:
                                configBit += muxSize.bit_length() - 1
                    case ".vhdl" | ".v":
                        with open(matrixDir, "r") as f:
                            f = f.read()
                            if configBit := re.search(r"NumberOfConfigBits: (\d+)", f):
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
            new_tiles.append(
                Tile(
                    name=tileName,
                    ports=ports,
                    bels=bels,
                    tileDir=fileName,
                    matrixDir=matrixDir,
                    userCLK=withUserCLK,
                    configBit=configBit,
                )
            )

    return (new_tiles, commonWirePairs)


def parseSupertiles(
    fileName: pathlib.Path, tileDic: dict[str, Tile]
) -> list[SuperTile]:
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

    with open(fileName, "r") as f:
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
                elif line[1].endswith(".v"):
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
    filename: pathlib.Path,
    belPrefix: str = "",
    filetype: Literal["verilog", "vhdl"] = "",
) -> Bel:
    """
    Parse a Verilog or VHDL bel file and return all the related information of the bel.
    The tuple returned for relating to ports will be a list of (belName, IO) pair.

    The function will also parse and record all the FABulous attribute which all starts with ::

        (* FABulous, <type>, ... *)

    The <type> can be one the following:

    * **BelMap**
    * **EXTERNAL**
    * **SHARED_PORT**
    * **GLOBAL**
    * **CONFIG_PORT**

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
    """
    internal: list[tuple[str, IO]] = []
    external: list[tuple[str, IO]] = []
    config: list[tuple[str, IO]] = []
    shared: list[tuple[str, IO]] = []
    isExternal = False
    isConfig = False
    isShared = False
    userClk = False
    individually_declared = False
    noConfigBits = 0

    try:
        with open(filename, "r") as f:
            file = f.read()
    except FileNotFoundError:
        logger.critical(f"File {filename} not found.")
        exit(-1)
    except PermissionError:
        logger.critical(f"Permission denied to file {filename}.")
        exit(-1)

    if filetype == "vhdl":
        belMapDic = vhdl_belMapProcessing(file, filename, filetype)
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
                if "GLOBAL" in line:
                    break

        if isExternal and not isShared:
            external.append((portName, direction))
        elif isConfig:
            config.append((portName, direction))
        elif isShared:
            # shared port do not have a prefix
            shared.append((portName.removeprefix(belPrefix), direction))
        else:
            internal.append((portName, direction))

        if "UserCLK" in portName:
            userClk = True

        isExternal = False
        isConfig = False
        isShared = False

    if filetype == "verilog":
        # Runs yosys on verilog file, creates netlist, saves to json in same directory.
        json_file = filename.with_suffix(".json")
        runCmd = [
            "yosys",
            "-qp"
            f"read_verilog {filename}; proc -noopt; write_json -compat-int {json_file}",
        ]
        try:
            subprocess.run(runCmd, check=True)
        except subprocess.CalledProcessError as e:
            logger.error(f"Failed to run yosys command: {e}")
            raise ValueError

        with open(f"{json_file}", "r") as f:
            data_dict = json.load(f)

        modules = data_dict.get("modules", {})
        filtered_ports: dict[str, IO] = {}
        # Gathers port name and direction, filters out configbits as they show in ports.
        for module_name, module_info in modules.items():
            ports = module_info["ports"]
            for port_name, details in ports.items():
                if "ConfigBits" in port_name:
                    continue
                if "UserCLK" in port_name:
                    userClk = True
                if port_name[-1].isdigit():
                    individually_declared = True
                direction = IO[details["direction"].upper()]
                bits = details.get("bits", [])
                filtered_ports[port_name] = (direction, bits)

        if individually_declared:
            logger.warning(
                f"Ports in {filename} have been individually declared rather than as a vector."
            )
            logger.warning("Ports will not be concatenated during fabric generation.")

        param_defaults = module_info.get("parameter_default_values")
        if param_defaults and "NoConfigBits" in param_defaults:
            noConfigBits = param_defaults["NoConfigBits"]
        # Passed attributes dont show in port list, checks for attributes in netnames.
        # (If passed attributes missing, may need to expand to check other lists e.g "memories".)
        netnames = module_info.get("netnames", {})
        for item, details in netnames.items():
            if item in filtered_ports:
                direction, bits = filtered_ports[item]
                attributes = details.get("attributes", {})
                for index in range(len(bits)):
                    new_port_name = (
                        f"{item}{index}" if len(bits) > 1 else item
                    )  # Multi-bit ports get index
                    if "EXTERNAL" in attributes and "SHARED_PORT" not in attributes:
                        external.append((f"{belPrefix}{new_port_name}", direction))
                    elif "CONFIG" in attributes:
                        config.append((f"{belPrefix}{new_port_name}", direction))
                    elif "SHARED_PORT" in attributes:
                        shared.append((new_port_name, direction))
                    else:
                        internal.append((f"{belPrefix}{new_port_name}", direction))
        belMapDic = verilog_belMapProcessing(module_info)
        if len(belMapDic) != noConfigBits:
            raise ValueError(
                f"NoConfigBits does not match with the BEL map in file {filename}, length of BelMap is {len(belMapDic)}, but with {noConfigBits} config bits"
            )

    return Bel(
        src=filename,
        prefix=belPrefix,
        internal=internal,
        external=external,
        configPort=config,
        sharedPort=shared,
        configBit=noConfigBits,
        belMap=belMapDic,
        userCLK=userClk,
        individually_declared=individually_declared,
    )


def verilog_belMapProcessing(module_info):
    """Extracts and transforms BEL mapping attributes in the JSON created from a Verilog module.

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
                    for i in range(0, 2**length):
                        belMapDic[bel[0]][i] = {}
                        bitMap = list(f"{2**length-i-1:0{length.bit_length()}b}")
                        for v in range(len(bitMap) - 1, -1, -1):
                            belMapDic[bel[0]][i][v] = bitMap.pop(0)
            else:
                belMapDic[bel[0]][0] = {0: "1"}
    return belMapDic


def parseConfigMem(
    fileName: pathlib.Path,
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

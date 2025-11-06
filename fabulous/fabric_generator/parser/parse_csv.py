"""Contains functions for parsing CSV files related to the fabric definition."""

import re
from copy import deepcopy
from pathlib import Path
from typing import TYPE_CHECKING

from loguru import logger

from FABulous.custom_exception import (
    InvalidFabricDefinition,
    InvalidFabricParameter,
    InvalidFileType,
    InvalidPortType,
    InvalidSupertileDefinition,
    InvalidTileDefinition,
)
from FABulous.fabric_definition.define import IO, ConfigBitMode, MultiplexerStyle
from FABulous.fabric_definition.Fabric import Fabric
from FABulous.fabric_definition.Gen_IO import Gen_IO
from FABulous.fabric_definition.SuperTile import SuperTile
from FABulous.fabric_definition.Tile import Tile
from FABulous.fabric_generator.gen_fabric.fabric_automation import (
    addBelsToPrim,
    generateCustomTileConfig,
    generateSwitchmatrixList,
)
from FABulous.fabric_generator.parser.parse_hdl import parseBelFile
from FABulous.fabric_generator.parser.parse_switchmatrix import (
    parseList,
    parseMatrix,
    parsePortLine,
)
from FABulous.FABulous_settings import get_context

if TYPE_CHECKING:
    from FABulous.fabric_definition.Bel import Bel
    from FABulous.fabric_definition.Port import Port


def parseTilesCSV(fileName: Path) -> tuple[list[Tile], list[tuple[str, str]]]:
    """Parse a CSV tile configuration file and returns all tile objects.

    Parameters
    ----------
    fileName : Path
        The path to the CSV file.

    Returns
    -------
    tuple[list[Tile], list[tuple[str, str]]]
        A tuple containing a list of Tile objects and a list of common wire pairs.

    Raises
    ------
    FileExistsError
        If the input does not exist.
    InvalidFileType
        If the input file is not a CSV file.
    InvalidTileDefinition
        If the tile definition is invalid.
    InvalidPortType
        If port type is invalid.
    """
    logger.info(f"Reading tile configuration: {fileName}")

    if fileName.suffix != ".csv":
        raise InvalidFileType("File must be a CSV file.")

    if not fileName.exists():
        raise FileExistsError(f"File {fileName} does not exist.")

    filePathParent = fileName.parent

    with fileName.open() as f:
        file = f.read()
        file = re.sub(r"#.*", "", file)

    tilesData = re.findall(r"TILE(.*?)EndTILE", file, re.MULTILINE | re.DOTALL)

    new_tiles = []
    commonWirePairs = []
    proj_dir = get_context().proj_dir

    # Parse each tile config
    for t in tilesData:
        t = t.split("\n")
        tileName = t[0].split(",")[1].strip()
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
            temp = [i.strip() for i in temp]
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
                        raise InvalidPortType(
                            "There is already a carrychain "
                            f"with the prefix {carryPrefix}"
                        )
                if "SHARED_" in temp[6]:
                    if "JUMP" not in temp[0]:
                        raise InvalidTileDefinition(
                            "LOCAL SHARED_ Ports can only be used with JUMP ports."
                        )
                    localShared = temp[6].split("_")[1]
                    if localShared is None or localShared == "":
                        raise InvalidTileDefinition("SHARED_ cannot be empty.")
                    if localShared not in ["RESET", "ENABLE"]:
                        raise InvalidTileDefinition(
                            f"LOCAL SHARED_ port {localShared} is not supported. "
                            "Only SHARED_RESET and SHARED_ENABLE are supported."
                        )
                    if localShared not in localSharedPorts:
                        localSharedPorts[localShared] = port
                    else:
                        raise InvalidTileDefinition(
                            f"LOCAL SHARED_ port {localShared} already exists."
                        )

                ports.extend(port)
                if commonWirePair:
                    commonWirePairs.append(commonWirePair)

            elif temp[0] == "BEL":
                belFilePath = filePathParent.joinpath(temp[1])
                bel_prefix = temp[2] if len(temp) > 2 else ""
                if (
                    temp[1].endswith(".vhdl")
                    or temp[1].endswith(".v")
                    or temp[1].endswith(".sv")
                ):
                    bels.append(parseBelFile(belFilePath, bel_prefix))
                else:
                    raise InvalidFileType(
                        f"File {belFilePath} is not a .vhdl or .v file. "
                        "Please check the BEL file."
                    )

                if "ADD_AS_CUSTOM_PRIM" in temp[3:]:
                    primsFile = proj_dir.joinpath("user_design/custom_prims.v")
                    logger.info(f"Adding bels to custom prims file: {primsFile}")
                    addBelsToPrim(primsFile, [bels[-1]])

            elif temp[0] == "GEN_IO":
                configBit = 0
                configAccess = False
                inverted = False
                clocked = False
                clockedComb = False
                clockedMux = False
                pins = int(temp[1])
                if pins <= 0:
                    raise InvalidTileDefinition(
                        f"GEN_IO pins must be greater than 0, but is {pins}"
                    )  # Additional params can be added
                for param in temp[4:]:
                    param = param.strip()
                    param = param.upper()

                    if param == "CONFIGACCESS":
                        if temp[2] != "OUTPUT":
                            raise InvalidTileDefinition(
                                "CONFIGACCESS GEN_IO can only be used with OUTPUT, "
                                f"but is {temp[2]}"
                            )
                        if not configAccess and temp[2] != "OUTPUT":
                            raise InvalidTileDefinition(
                                "CONFIGACCESS GEN_IO can only be used with OUTPUT, "
                                f"but is {temp[2]}"
                            )
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
                        raise InvalidTileDefinition(
                            f"Unknown parameter {param} in GEN_IO. "
                            "Valid parameters are CONFIGACCESS, INVERTED, CLOCKED, "
                            "CLOCKED_COMB, CLOCKED_MUX."
                        )

                    if configAccess and (clocked or clockedComb or clockedMux):
                        raise InvalidTileDefinition(
                            "CONFIGACCESS GEN_IO can not be clocked"
                        )
                    if sum([clocked, clockedComb, clockedMux]) > 1:
                        raise InvalidTileDefinition(
                            "CLOCKED, CLOCKED_COMB or CLOCKED_MUX can not be combined "
                            "for one GEN_IO"
                        )

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
                    raise InvalidTileDefinition(
                        f"GEN_IO with prefix {temp[3]} already exists in tile "
                        f"{tileName}."
                    )
            elif temp[0] == "MATRIX":
                configBit = 0

                if "GENERATE" in temp:
                    logger.info(f"Generating switch matrix list for tile {tileName}")
                    genMatrixList = True
                    if len(temp) <= 2:
                        # only MATRIX, GENERATE in csv
                        matrixDir = fileName.parent
                    else:
                        matrixDir = fileName.parent.joinpath(temp[2])
                    if matrixDir.is_file() and matrixDir.suffix == ".list":
                        logger.warning(
                            f"Matrix file {matrixDir} already exists and will be "
                            "overwritten."
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
                            "No destination directory for matrix file sepicified, "
                            f"using default path {matrixDir}."
                        )
                        if not matrixDir.parent.exists():
                            matrixDir.parent.mkdir(parents=True)
                            logger.warning(f"Creating directory {matrixDir.parent}.")

                else:
                    matrixDir = fileName.parent.joinpath(temp[1]).absolute()
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
                            with matrixDir.open() as f:
                                f = f.read()
                                if configBit := re.search(
                                    r"NumberOfConfigBits: (\d+)", f
                                ):
                                    configBit = int(configBit.group(1))
                                else:
                                    configBit = 0
                                    logger.warning(
                                        "Cannot find NumberOfConfigBits in "
                                        f"{matrixDir} assume 0 config bits."
                                    )
                        case _:
                            raise InvalidFileType("Unknown file extension for matrix.")

            elif temp[0] == "INCLUDE":
                p = fileName.parent.joinpath(temp[1])
                if not p.exists():
                    raise InvalidTileDefinition(
                        f"Cannot find {str(p)} in tile {tileName}"
                    )
                with p.open() as f:
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
                raise InvalidTileDefinition(
                    f"Unknown tile description {temp[0]} in tile {tileName}. "
                    "Valid descriptions are NORTH, SOUTH, EAST, WEST, JUMP, BEL, "
                    "GEN_IO, MATRIX, and INCLUDE."
                )

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


def parseSupertilesCSV(fileName: Path, tileDic: dict[str, Tile]) -> list[SuperTile]:
    """Parse a CSV supertile configuration file and returns all SuperTile objects.

    Parameters
    ----------
    fileName : Path
        The path to the CSV file.
    tileDic : dict[str, Tile]
        Dict of tiles.

    Raises
    ------
    InvalidFileType
        If the input file is not a CSV file.
    FileNotFoundError
        If the input does not exist.
    InvalidSupertileDefinition
        If the supertile definition is invalid.

    Returns
    -------
    list[SuperTile]
        List of SuperTile objects.
    """
    logger.info(f"Reading supertile configuration: {fileName}")

    if not fileName.suffix == ".csv":
        raise InvalidFileType("File must be a csv file.")

    if not fileName.exists():
        raise FileNotFoundError(f"File {fileName} does not exist.")

    filePath = fileName.parent

    with fileName.open() as f:
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
                bels.append(parseBelFile(belFilePath, line[2]))
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
                    raise InvalidSupertileDefinition(
                        f"The super tile {name} contains definitions that are not "
                        "tiles or Null."
                    )
            tileMap.append(row)

        withUserCLK = any(bel.withUserCLK for bel in bels)
        new_supertiles.append(SuperTile(name, tiles, tileMap, bels, withUserCLK))

    return new_supertiles


def parseFabricCSV(fileName: str) -> Fabric:
    """Parse a CSV file and returns a fabric object.

    Parameters
    ----------
    fileName : str
        Directory of the CSV file.

    Raises
    ------
    FileNotFoundError
        If the input does not exist.
    InvalidFabricDefinition
        If the fabric definition is invalid.
    InvalidFabricParameter
        If the fabric parameter is invalid.
    InvalidFileType
        If the input file is not a CSV file.

    Returns
    -------
    Fabric
        The fabric object.
    """
    fName = Path(fileName).absolute()
    if fName.suffix != ".csv":
        raise InvalidFileType("File must be a csv file")

    if not fName.exists():
        raise FileNotFoundError(f"File {fName} does not exist.")

    filePath = fName.parent

    with fName.open() as f:
        file = f.read()
        file = re.sub(r"#.*", "", file)

    # read in the csv file and part them
    if fabricDescription := re.search(
        r"FabricBegin(.*?)FabricEnd", file, re.MULTILINE | re.DOTALL
    ):
        fabricDescription = fabricDescription.group(1)
    else:
        raise InvalidFabricDefinition(
            "Cannot find FabricBegin and FabricEnd in csv file."
        )

    if parameters := re.search(
        r"ParametersBegin(.*?)ParametersEnd", file, re.MULTILINE | re.DOTALL
    ):
        parameters = parameters.group(1)
    else:
        raise InvalidFabricDefinition(
            "Cannot find ParametersBegin and ParametersEnd in csv file."
        )

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
    new_tiles, new_commonWirePair = parseTilesCSV(fName)
    tileTypes += [new_tile.name for new_tile in new_tiles]
    tileDefs += new_tiles
    commonWirePair += new_commonWirePair
    tileDic = dict(zip(tileTypes, tileDefs, strict=False))

    new_supertiles = parseSupertilesCSV(fName, tileDic)
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
        i = [i.strip() for i in i]
        if not i:
            continue
        if i[0].startswith("Tile"):
            if "GENERATE" in i:
                # we generate the tile right before we parse everything
                i[1] = str(generateCustomTileConfig(filePath.joinpath(i[1])))

            new_tiles, new_commonWirePair = parseTilesCSV(filePath.joinpath(i[1]))
            tileTypes += [new_tile.name for new_tile in new_tiles]
            tileDefs += new_tiles
            commonWirePair += new_commonWirePair
            tileDic = dict(zip(tileTypes, tileDefs, strict=False))
        elif i[0].startswith("Supertile"):
            new_supertiles = parseSupertilesCSV(filePath.joinpath(i[1]), tileDic)
            for new_supertile in new_supertiles:
                superTileDic[new_supertile.name] = new_supertile
        elif i[0].startswith("ConfigBitMode"):
            if i[1] == "frame_based":
                configBitMode = ConfigBitMode.FRAME_BASED
            elif i[1] == "FlipFlopChain":
                configBitMode = ConfigBitMode.FLIPFLOP_CHAIN
            else:
                raise InvalidFabricParameter(
                    f"Invalid config bit mode {i[1]} in parameters. "
                    "Valid options are frame_based and FlipFlopChain."
                )
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
                raise InvalidFabricParameter(
                    f"Invalid multiplexer style {i[1]} in parameters. "
                    "Valid options are custom and generic."
                )
        elif i[0].startswith("SuperTileEnable"):
            superTileEnable = i[1] == "TRUE"
        else:
            raise InvalidFabricParameter(f"The following parameter is not valid: {i}")

    # form the fabric data structure
    usedTile = set()
    for f in fabricDescription:
        fabricLineTmp = f.split(",")
        fabricLineTmp = [i for i in fabricLineTmp if i != ""]
        fabricLineTmp = [i.strip() for i in fabricLineTmp]
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
                raise InvalidFabricDefinition(
                    f"Unknown tile {i} in fabric description. "
                    "Please check the tile definitions."
                )
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
                f"Supertile {i} is not used in the fabric. "
                "Removing from tile dictionary."
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

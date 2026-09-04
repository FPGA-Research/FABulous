"""Contains functions for parsing CSV files related to the fabric definition."""

import re
from copy import deepcopy
from pathlib import Path
from typing import TYPE_CHECKING

from loguru import logger

from fabulous.custom_exception import (
    InvalidFabricDefinition,
    InvalidFabricParameter,
    InvalidFileType,
    InvalidPortType,
    InvalidSupertileDefinition,
    InvalidSwitchMatrixDefinition,
    InvalidTileDefinition,
)
from fabulous.fabric_definition.define import (
    IO,
    SWITCH_MATRIX_CONSTANTS,
    ConfigBitMode,
    Direction,
    MultiplexerStyle,
    Side,
)
from fabulous.fabric_definition.fabric import Fabric
from fabulous.fabric_definition.gen_io import Gen_IO
from fabulous.fabric_definition.port import NULL_PORT_NAME, TilePort
from fabulous.fabric_definition.supertile import SuperTile
from fabulous.fabric_definition.switch_matrix import SwitchMatrix
from fabulous.fabric_definition.tile import Tile
from fabulous.fabric_generator.gen_fabric.fabric_automation import (
    addBelsToPrim,
    generateCustomTileConfig,
    generateSwitchmatrixList,
)
from fabulous.fabric_generator.parser.parse_hdl import parseBelFile
from fabulous.fabulous_settings import get_context

if TYPE_CHECKING:
    from fabulous.fabric_definition.bel import Bel


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
    common_wire_pair: tuple[str, str] | None

    if wire_direction in (
        Direction.NORTH,
        Direction.EAST,
        Direction.SOUTH,
        Direction.WEST,
    ):
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
        common_wire_pair = (f"{source_name}", f"{destination_name}")

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
        common_wire_pair = None

    elif wire_direction is Direction.SJUMP:
        # SJUMP,source,0,0,NULL,n  -> OUTPUT: signal exits tile toward supertile SM
        # SJUMP,NULL,0,0,dest,n    -> INPUT: signal enters tile from supertile SM
        # An SJUMP line is one-way: exactly one of source/destination must be NULL.
        if (source_name == NULL_PORT_NAME) == (destination_name == NULL_PORT_NAME):
            raise InvalidPortType(
                f"Invalid SJUMP line '{line.strip()}': exactly one of source and "
                "destination must be NULL (use 'SJUMP,src,0,0,NULL,n' for an output "
                "or 'SJUMP,NULL,0,0,dst,n' for an input)."
            )
        # SJUMP wires terminate at the supertile switch matrix and carry no
        # spatial offset; a nonzero offset is a definition error, not silently 0.
        if x_offset != 0 or y_offset != 0:
            raise InvalidPortType(
                f"Invalid SJUMP line '{line.strip()}': X/Y offset must be 0,0 "
                f"(got {x_offset},{y_offset})."
            )

        if source_name != NULL_PORT_NAME:
            ports.append(
                TilePort(
                    name=source_name,
                    io_direction=IO.OUTPUT,
                    width=wire_count,
                    side_of_tile=Side.ANY,
                    wire_direction=Direction.SJUMP,
                    source_name=source_name,
                    x_offset=0,
                    y_offset=0,
                    destination_name=NULL_PORT_NAME,
                    wire_count=wire_count,
                )
            )
        if destination_name != NULL_PORT_NAME:
            ports.append(
                TilePort(
                    name=destination_name,
                    io_direction=IO.INPUT,
                    width=wire_count,
                    side_of_tile=Side.ANY,
                    wire_direction=Direction.SJUMP,
                    source_name=NULL_PORT_NAME,
                    x_offset=0,
                    y_offset=0,
                    destination_name=destination_name,
                    wire_count=wire_count,
                )
            )
        common_wire_pair = None

    else:
        raise InvalidPortType(f"Unknown port type: {port_type}")
    return (ports, common_wire_pair)


def parseTilesCSV(
    file_name: Path, preserve_list_order: bool = False
) -> tuple[list[Tile], list[tuple[str, str]]]:
    """Parse a CSV tile configuration file and returns all tile objects.

    Parameters
    ----------
    file_name : Path
        The path to the CSV file.
    preserve_list_order : bool, optional
        Passed to each tile's switch matrix so a `.list` keeps its file order
        (MSB-first) instead of the canonical dest-column order. Defaults to False.

    Returns
    -------
    tuple[list[Tile], list[tuple[str, str]]]
        A tuple containing a list of Tile objects and a list of common wire pairs.

    Raises
    ------
    ValueError
        If CARRY port prefix is not a string
    FileExistsError
        If the input does not exist.
    InvalidFileType
        If the input file is not a CSV file.
    InvalidTileDefinition
        If the tile definition is invalid.
    InvalidPortType
        If port type is invalid.
    """
    logger.info(f"Reading tile configuration: {file_name}")

    if file_name.suffix != ".csv":
        raise InvalidFileType("File must be a CSV file.")

    if not file_name.exists():
        raise FileExistsError(f"File {file_name} does not exist.")

    filePathParent = file_name.parent

    with file_name.open() as f:
        file = f.read()
        file = re.sub(r"#.*", "", file)

    tilesData = re.findall(r"TILE(.*?)EndTILE", file, re.MULTILINE | re.DOTALL)

    new_tiles = []
    common_wire_pairs = []
    proj_dir = get_context().proj_dir

    # Parse each tile config
    for t in tilesData:
        t = t.split("\n")
        tileName = t[0].split(",")[1].strip()
        if filePathParent.name != tileName:
            logger.warning(
                f"Tile name '{tileName}' does not match folder name "
                f"'{filePathParent.name}' in {file_name}."
            )
        ports: list[TilePort] = []
        bels: list[Bel] = []
        matrixDir: Path | None = None
        gen_ios: list[Gen_IO] = []
        withUserCLK = False
        genMatrixList = False
        tileCarry: dict[str, dict[IO, str]] = {}
        localSharedPorts: dict[str, list[TilePort]] = {}

        for item in t:
            temp: list[str] = item.split(",")
            temp = [i.strip() for i in temp]
            if not temp or temp[0] == "":
                continue
            if temp[0] in Direction:
                port, common_wire_pair = parse_port_line(item)
                if "CARRY" in temp[6]:
                    # For prefix after carry
                    carryPrefix = re.search(r'CARRY="([^"]+)"', temp[6])
                    if not carryPrefix:
                        if "=" in temp[6] and '"' not in temp[6]:
                            # Crude check if its defined as string string notation
                            logger.error(
                                "CARRY port prefix has to be a string for ",
                                f"{temp[6]}.",
                            )
                            raise ValueError
                        logger.info(
                            "CARRY port without prefix,"
                            "using default prefix FABulous_default"
                        )
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
                if common_wire_pair:
                    common_wire_pairs.append(common_wire_pair)

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
                        f"File {belFilePath} is not a .vhdl, .v, or .sv file. "
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
                if "GENERATE" in temp:
                    logger.info(f"Generating switch matrix list for tile {tileName}")
                    genMatrixList = True
                    if len(temp) <= 2:
                        # only MATRIX, GENERATE in csv
                        matrixDir = file_name.parent
                    else:
                        matrixDir = file_name.parent.joinpath(temp[2])
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
                    matrixDir = file_name.parent.joinpath(temp[1]).absolute()

            elif temp[0] == "INCLUDE":
                p = file_name.parent.joinpath(temp[1])
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

                    port, common_wire_pair = parse_port_line(line)
                    ports.extend(port)
                    if common_wire_pair:
                        common_wire_pairs.append(common_wire_pair)

            else:
                raise InvalidTileDefinition(
                    f"Unknown tile description {temp[0]} in tile {tileName}. "
                    f"Valid descriptions are {', '.join(d.value for d in Direction)}, "
                    "BEL, GEN_IO, MATRIX, and INCLUDE."
                )

        withUserCLK = any(bel.withUserCLK for bel in bels)

        if matrixDir is None:
            raise InvalidTileDefinition(
                f"Tile {tileName!r} has no MATRIX line; a switch matrix "
                "(.csv/.list) or hand-written HDL file is required."
            )

        if genMatrixList:
            generateSwitchmatrixList(
                tileName, bels, matrixDir, tileCarry, localSharedPorts
            )

        new_tiles.append(
            Tile(
                name=tileName,
                ports=ports,
                bels=bels,
                tileDir=file_name,
                switch_matrix=SwitchMatrix.from_file(
                    matrixDir,
                    tileName,
                    ports=ports,
                    bels=bels,
                    preserve_list_order=preserve_list_order,
                ),
                gen_ios=gen_ios,
                userCLK=withUserCLK,
            )
        )

    return (new_tiles, common_wire_pairs)


def validate_super_tile_matrix(
    super_tile: SuperTile,
    connections: dict[str, list[str]],
    matrix_path: Path,
) -> None:
    """Check that a supertile switch matrix only references known names.

    Every mux output (sink) must be a BEL input or a child-tile INPUT SJUMP wire,
    and every mux input (source) must be a BEL output, a child-tile OUTPUT SJUMP
    wire, or a switch-matrix constant. An unknown name is almost always a typo and
    would otherwise emit RTL referencing an undeclared signal.

    Parameters
    ----------
    super_tile : SuperTile
        The supertile whose ports and BELs define the legal names.
    connections : dict[str, list[str]]
        Parsed matrix, mapping each sink (destination) to its sources.
    matrix_path : Path
        Path to the matrix file, used in the error message.

    Raises
    ------
    InvalidSwitchMatrixDefinition
        If any sink or source is not a known port, BEL pin, or constant.
    """
    valid_sources, valid_sinks = super_tile.get_matrix_port_names()
    valid_sources |= set(SWITCH_MATRIX_CONSTANTS)

    unknown_sinks = sorted(s for s in connections if s not in valid_sinks)
    unknown_sources = sorted(
        {src for sources in connections.values() for src in sources} - valid_sources
    )

    if unknown_sinks or unknown_sources:
        raise InvalidSwitchMatrixDefinition(
            f"Supertile '{super_tile.name}' switch matrix {matrix_path} references "
            f"undefined names: sinks={unknown_sinks}, sources={unknown_sources}.\n"
            "Sinks must be BEL inputs or child-tile INPUT SJUMP wires; sources "
            "must be BEL outputs, child-tile OUTPUT SJUMP wires, or a constant.\n"
            f"Available sinks: {sorted(valid_sinks)}\n"
            f"Available sources: {sorted(valid_sources)}"
        )


def parseSupertilesCSV(file_name: Path, tileDic: dict[str, Tile]) -> list[SuperTile]:
    """Parse a CSV supertile configuration file and returns all SuperTile objects.

    Parameters
    ----------
    file_name : Path
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
    logger.info(f"Reading supertile configuration: {file_name}")

    if not file_name.suffix == ".csv":
        raise InvalidFileType("File must be a csv file.")

    if not file_name.exists():
        raise FileNotFoundError(f"File {file_name} does not exist.")

    filePath = file_name.parent

    with file_name.open() as f:
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
        master_set = False
        master_coords: tuple[int, int] | None = None
        matrix_line_path: Path | None = None
        for i in description[1:-1]:
            line = i.split(",")
            line = [i for i in line if i != "" and i != " "]
            row = []

            if line[0] == "BEL":
                belFilePath = filePath.joinpath(line[1])
                bels.append(parseBelFile(belFilePath, line[2] if len(line) > 2 else ""))
                continue
            if line[0] == "MATRIX":
                # The supertile switch matrix is given by this line's path,
                # resolved relative to the supertile CSV.
                if len(line) > 1:
                    matrix_line_path = filePath / line[1]
                continue

            row_master = False
            for j in line:
                if j == "MASTER":
                    if len(row) == 0 or row[-1] is None:
                        raise InvalidSupertileDefinition(
                            f"Supertile '{name}': MASTER must follow a valid tile name."
                        )
                    row_master = True
                    continue
                if j in tileDic:
                    tileDic[j].partOfSuperTile = True
                    t = deepcopy(tileDic[j])
                    row.append(t)
                    if t not in tiles:
                        tiles.append(t)
                elif j in ("Null", "NULL", "None"):
                    row.append(None)
                else:
                    raise InvalidSupertileDefinition(
                        f"The super tile {name} contains definitions that are not "
                        "tiles or Null."
                    )
            if row_master:
                if len(row) > 1:
                    raise InvalidSupertileDefinition(
                        f"Supertile '{name}': MASTER cannot be used on a row "
                        "with multiple tiles."
                    )
                row_index = len(tileMap)
                col_index = len(row) - 1
                if master_set:
                    raise InvalidSupertileDefinition(
                        f"Supertile '{name}': multiple MASTER tokens found."
                    )
                master_coords = (col_index, row_index)
                master_set = True
            tileMap.append(row)

        withUserCLK = any(bel.withUserCLK for bel in bels)
        # tileDir is the supertile CSV file path (matching Tile.tileDir), so
        # consumers use `tileDir.parent` for the supertile's directory.
        super_tile = SuperTile(
            name, file_name.absolute(), tiles, tileMap, bels, withUserCLK
        )
        super_tile.master_tile_coords = master_coords

        # The supertile switch matrix is taken from the MATRIX line (resolved
        # relative to the CSV). There is no auto-discovery: a supertile without a
        # MATRIX line simply has no switch matrix.
        st_matrix_dir: Path | None = matrix_line_path
        if st_matrix_dir is not None:
            if not st_matrix_dir.exists():
                raise InvalidSupertileDefinition(
                    f"Supertile '{name}': MATRIX file {st_matrix_dir} does not exist."
                )
            switch_matrix = SwitchMatrix.from_file(st_matrix_dir, name)
            validate_super_tile_matrix(
                super_tile, switch_matrix.connections, st_matrix_dir
            )
            super_tile.switch_matrix = switch_matrix

        new_supertiles.append(super_tile)

    return new_supertiles


def parse_tile_from_dir(
    tile_dir: Path, tile_name: str, is_supertile: bool
) -> Tile | SuperTile:
    """Parse a single tile or supertile from its own directory.

    Reads `<tile_dir>/<tile_name>.csv` in isolation, without constructing a
    surrounding `Fabric`. For a supertile, the subtile CSVs are read first (each
    from `<tile_dir>/<subtile>/<subtile>.csv`) to build the tile dictionary the
    supertile definition references.

    Parameters
    ----------
    tile_dir : Path
        Directory containing the tile CSV and, for supertiles, the subtile
        subdirectories.
    tile_name : str
        Name of the tile or supertile to return. Also the CSV file stem.
    is_supertile : bool
        Whether the target is a supertile.

    Raises
    ------
    FileNotFoundError
        If `<tile_dir>/<tile_name>.csv` does not exist.
    InvalidTileDefinition
        If a non-supertile named `tile_name` is not present in the CSV.
    InvalidSupertileDefinition
        If a supertile named `tile_name` is not present in the CSV.

    Returns
    -------
    Tile | SuperTile
        The parsed tile or supertile.
    """
    tile_csv = tile_dir / f"{tile_name}.csv"
    if not tile_csv.exists():
        raise FileNotFoundError(f"Tile CSV {tile_csv} does not exist")

    if not is_supertile:
        tiles, _ = parseTilesCSV(tile_csv)
        for tile in tiles:
            if tile.name == tile_name:
                return tile
        raise InvalidTileDefinition(f"Tile {tile_name!r} not found in {tile_csv}")

    # Collect the subtile names the supertile references. The block is scanned
    # with the same regex, comment stripping, and token filtering
    # `parseSupertilesCSV` uses, so the two agree on which cells are subtile
    # names: the `BEL`/`MATRIX` control lines and the `MASTER`/`Null` placement
    # tokens are skipped, leaving only the subtile names.
    text = re.sub(r"#.*", "", tile_csv.read_text(encoding="utf-8"))
    subtile_names: list[str] = []
    seen: set[str] = set()
    for block in re.findall(
        r"SuperTILE(.*?)EndSuperTILE", text, re.MULTILINE | re.DOTALL
    ):
        # block[0] is the `SuperTILE,<name>` header remainder and the last line
        # is the empty line before `EndSuperTILE`; the tile map is between.
        for raw_line in block.split("\n")[1:-1]:
            line = [cell for cell in raw_line.split(",") if cell not in ("", " ")]
            if not line or line[0] in ("BEL", "MATRIX"):
                continue
            for cell in line:
                if cell in ("MASTER", "Null", "NULL", "None") or cell in seen:
                    continue
                seen.add(cell)
                subtile_names.append(cell)

    tile_dic: dict[str, Tile] = {}
    for subtile_name in subtile_names:
        subtile_csv = tile_dir / subtile_name / f"{subtile_name}.csv"
        tiles, _ = parseTilesCSV(subtile_csv)
        tile_dic.update({tile.name: tile for tile in tiles})

    supertiles = parseSupertilesCSV(tile_csv, tile_dic)
    for supertile in supertiles:
        if supertile.name == tile_name:
            return supertile
    raise InvalidSupertileDefinition(f"SuperTile {tile_name!r} not found in {tile_csv}")


def parseFabricCSV(file_name: Path) -> Fabric:
    """Parse a CSV file and returns a fabric object.

    Parameters
    ----------
    file_name : Path
        Path of the CSV file.

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
    csv_file = file_name.absolute()
    if csv_file.suffix != ".csv":
        raise InvalidFileType("File must be a csv file")

    if not csv_file.exists():
        raise FileNotFoundError(f"File {csv_file} does not exist.")

    filePath = csv_file.parent

    with csv_file.open() as f:
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
    common_wire_pair: list[tuple[str, str]] = []
    fabricTiles = []
    tileDic = {}
    unusedTileDic = {}

    # list for supertiles
    superTileDic = {}
    unusedSuperTileDic = {}

    # PreserveListOrder controls the canonical .list mux-input ordering, so it
    # must be known before any tile is parsed (a tile may precede it in the CSV).
    preserveListOrder = False
    for line in parameters:
        fields = [f.strip() for f in line.split(",") if f.strip()]
        if fields and fields[0].startswith("PreserveListOrder"):
            if len(fields) < 2 or fields[1] not in ("TRUE", "FALSE"):
                raise InvalidFabricParameter(
                    "PreserveListOrder requires a value of TRUE or FALSE"
                )
            preserveListOrder = fields[1] == "TRUE"

    # For backwards compatibility parse tiles in fabric config
    new_tiles, new_common_wire_pair = parseTilesCSV(csv_file, preserveListOrder)
    tileTypes += [new_tile.name for new_tile in new_tiles]
    tileDefs += new_tiles
    common_wire_pair += new_common_wire_pair
    tileDic = dict(zip(tileTypes, tileDefs, strict=False))

    new_supertiles = parseSupertilesCSV(csv_file, tileDic)
    for new_supertile in new_supertiles:
        superTileDic[new_supertile.name] = new_supertile

    if new_tiles or new_supertiles:
        logger.warning(
            f"Deprecation warning: {csv_file} should not contain tile descriptions."
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
    disableUserCLK = False
    multiClkDomains = False

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

            new_tiles, new_common_wire_pair = parseTilesCSV(
                filePath.joinpath(i[1]), preserveListOrder
            )
            tileTypes += [new_tile.name for new_tile in new_tiles]
            tileDefs += new_tiles
            common_wire_pair += new_common_wire_pair
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
        elif i[0].startswith("DisableUserCLK"):
            disableUserCLK = i[1] == "TRUE"
        elif i[0].startswith("MultiClkDomains"):
            multiClkDomains = i[1] == "TRUE"
        elif i[0].startswith("PreserveListOrder"):
            # Consumed and validated by the pre-scan above (it must be known
            # before any tile is parsed); accepted here so it is not rejected.
            pass
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

    common_wire_pair = list(dict.fromkeys(common_wire_pair))
    common_wire_pair = [
        (i, j) for (i, j) in common_wire_pair if "NULL" not in i and "NULL" not in j
    ]

    return Fabric(
        fabric_dir=csv_file,
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
        disableUserCLK=disableUserCLK,
        multiClkDomains=multiClkDomains,
        tileDic=tileDic,
        superTileDic=superTileDic,
        unusedTileDic=unusedTileDic,
        unusedSuperTileDic=unusedSuperTileDic,
        commonWirePair=common_wire_pair,
    )

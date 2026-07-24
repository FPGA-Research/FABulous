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
from fabulous.fabric_definition.bel import Bel
from fabulous.fabric_definition.define import (
    IO,
    SWITCH_MATRIX_CONSTANTS,
    ConfigBitMode,
    Direction,
    MultiplexerStyle,
)
from fabulous.fabric_definition.fabric import Fabric
from fabulous.fabric_definition.gen_io import Gen_IO
from fabulous.fabric_definition.switch_matrix import SwitchMatrix
from fabulous.fabric_definition.tile import Tile
from fabulous.fabric_generator.gen_fabric.fabric_automation import (
    addBelsToPrim,
    generateCustomTileConfig,
    generateSwitchmatrixList,
)
from fabulous.fabric_generator.parser.parse_switchmatrix import (
    create_switch_matrix,
    parse_port_line,
    parseList,
    parseMatrix,
)
from fabulous.fabulous_settings import get_context

if TYPE_CHECKING:
    from fabulous.fabric_definition.port import TilePort


def parseTilesCSV(
    fileName: Path, preserve_list_order: bool = False
) -> tuple[list[Tile], list[tuple[str, str]]]:
    """Parse a CSV tile configuration file and returns all tile objects.

    Parameters
    ----------
    fileName : Path
        The path to the CSV file.
    preserve_list_order : bool
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
    common_wire_pairs = []
    proj_dir = get_context().proj_dir

    # Parse each tile config
    for t in tilesData:
        t = t.split("\n")
        tileName = t[0].split(",")[1].strip()
        if filePathParent.name != tileName:
            logger.warning(
                f"Tile name '{tileName}' does not match folder name "
                f"'{filePathParent.name}' in {fileName}."
            )
        ports: list[TilePort] = []
        bels: list[Bel] = []
        matrix_dir: Path | None = None
        gen_ios: list[Gen_IO] = []
        with_user_clk = False
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
                    local_shared = temp[6].split("_")[1]
                    if local_shared is None or local_shared == "":
                        raise InvalidTileDefinition("SHARED_ cannot be empty.")
                    if local_shared not in ["RESET", "ENABLE"]:
                        raise InvalidTileDefinition(
                            f"LOCAL SHARED_ port {local_shared} is not supported. "
                            "Only SHARED_RESET and SHARED_ENABLE are supported."
                        )
                    if local_shared not in localSharedPorts:
                        localSharedPorts[local_shared] = port
                    else:
                        raise InvalidTileDefinition(
                            f"LOCAL SHARED_ port {local_shared} already exists."
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
                    bels.append(Bel.from_hdl(belFilePath, bel_prefix))
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
                config_bit = 0
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
                        config_bit = int(temp[1])
                    elif param == "INVERTED":
                        inverted = True
                    elif param == "CLOCKED":
                        clocked = True
                    elif param == "CLOCKED_COMB":
                        clockedComb = True
                    elif param == "CLOCKED_MUX":
                        clockedMux = True
                        config_bit = int(temp[1])
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
                            config_bit,
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
                        matrix_dir = fileName.parent
                    else:
                        matrix_dir = fileName.parent.joinpath(temp[2])
                    if matrix_dir.is_file() and matrix_dir.suffix == ".list":
                        logger.warning(
                            f"Matrix file {matrix_dir} already exists and will be "
                            "overwritten."
                        )
                    elif matrix_dir.parent == proj_dir.joinpath("Tile"):
                        matrix_dir = matrix_dir.joinpath(
                            f"{tileName}_generated_switch_matrix.list"
                        )
                        logger.info(f"Generating matrix file {matrix_dir}")
                    else:
                        matrix_dir = proj_dir.joinpath(
                            f"./Tile/{tileName}/{tileName}_generated_switch_matrix.list"
                        )
                        logger.warning(
                            "No destination directory for matrix file sepicified, "
                            f"using default path {matrix_dir}."
                        )
                        if not matrix_dir.parent.exists():
                            matrix_dir.parent.mkdir(parents=True)
                            logger.warning(f"Creating directory {matrix_dir.parent}.")

                else:
                    matrix_dir = fileName.parent.joinpath(temp[1]).absolute()

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

        with_user_clk = any(bel.with_user_clock for bel in bels)

        if matrix_dir is None:
            raise InvalidTileDefinition(
                f"Tile {tileName!r} has no MATRIX line; a switch matrix "
                "(.csv/.list) or hand-written HDL file is required."
            )

        if genMatrixList:
            generateSwitchmatrixList(
                tileName, bels, matrix_dir, tileCarry, localSharedPorts
            )

        # Built here, not at the MATRIX line: a `.list` is canonicalised against
        # the tile's ports and BELs, which are only complete once the whole tile
        # block has been read.
        new_tiles.append(
            Tile(
                name=tileName,
                ports=ports,
                bels=bels,
                tile_dir=fileName,
                matrix_dir=matrix_dir,
                gen_ios=gen_ios,
                user_clk=with_user_clk,
                switch_matrix=SwitchMatrix.from_file(
                    matrix_dir,
                    tileName,
                    ports=ports,
                    bels=bels,
                    preserve_list_order=preserve_list_order,
                ),
            )
        )

    return (new_tiles, common_wire_pairs)


def _composite_matrix_port_names(
    sub_tiles: list[Tile], bels: list["Bel"]
) -> tuple[set[str], set[str]]:
    """Return the valid source and sink names for a composite tile's matrix.

    The composite tile's wrapper switch matrix binds to its sub-tile instance
    ports by sub-tile-qualified name (``{subtile}_{port}{k}``) and to its wrapper
    BEL pins by BEL pin name. A sub-tile OUTPUT port can drive a mux (a source);
    a sub-tile INPUT port can be a mux output (a sink). A wrapper-BEL output is a
    source; a wrapper-BEL input is a sink.

    Parameters
    ----------
    sub_tiles : list[Tile]
        The composite tile's constituent sub-tiles, whose ports define the legal
        sub-tile-qualified matrix names.
    bels : list[Bel]
        The composite tile's wrapper BELs, whose pins define the legal BEL-pin
        matrix names.

    Returns
    -------
    tuple[set[str], set[str]]
        ``(valid_sources, valid_sinks)``.
    """
    valid_sources: set[str] = set()
    valid_sinks: set[str] = set()

    for sub_tile in sub_tiles:
        for port in sub_tile.ports_info:
            if port.name == "NULL":
                continue
            names = {f"{sub_tile.name}_{port.name}{k}" for k in range(port.wire_count)}
            if port.io_direction == IO.OUTPUT:
                valid_sources |= names
            elif port.io_direction == IO.INPUT:
                valid_sinks |= names

    for bel in bels:
        valid_sinks.update(p.name for p in bel.inputs)
        valid_sources.update(p.name for p in bel.outputs)

    return valid_sources, valid_sinks


def validate_composite_tile_matrix(
    name: str,
    sub_tiles: list[Tile],
    bels: list["Bel"],
    connections: dict[str, list[str]],
    matrix_path: Path,
) -> None:
    """Check that a composite tile's switch matrix only references known names.

    Every mux output (sink) must be a sub-tile INPUT port (qualified
    ``{subtile}_{port}``) or a wrapper-BEL input, and every mux input (source)
    must be a sub-tile OUTPUT port, a wrapper-BEL output, or a switch-matrix
    constant. An unknown name is almost always a typo and would otherwise emit
    RTL referencing an undeclared signal.

    Parameters
    ----------
    name : str
        The composite tile name, used in the error message.
    sub_tiles : list[Tile]
        The composite tile's constituent sub-tiles, whose ports define the legal
        names.
    bels : list[Bel]
        The composite tile's wrapper BELs, whose pins define the legal names.
    connections : dict[str, list[str]]
        Parsed matrix, mapping each sink (destination) to its sources.
    matrix_path : Path
        Path to the matrix file, used in the error message.

    Raises
    ------
    InvalidSwitchMatrixDefinition
        If any sink or source is not a known port, BEL pin, or constant.
    """
    valid_sources, valid_sinks = _composite_matrix_port_names(sub_tiles, bels)
    valid_sources |= set(SWITCH_MATRIX_CONSTANTS)

    unknown_sinks = sorted(s for s in connections if s not in valid_sinks)
    unknown_sources = sorted(
        {src for sources in connections.values() for src in sources} - valid_sources
    )

    if unknown_sinks or unknown_sources:
        raise InvalidSwitchMatrixDefinition(
            f"Composite tile '{name}' switch matrix {matrix_path} "
            f"references undefined names: sinks={unknown_sinks}, "
            f"sources={unknown_sources}.\n"
            "Sinks must be sub-tile INPUT ports or wrapper-BEL inputs; sources "
            "must be sub-tile OUTPUT ports, wrapper-BEL outputs, or a constant.\n"
            f"Available sinks: {sorted(valid_sinks)}\n"
            f"Available sources: {sorted(valid_sources)}"
        )


def parseSupertilesCSV(fileName: Path, tileDic: dict[str, Tile]) -> list[Tile]:
    """Parse a CSV supertile configuration file and return composite tiles.

    Each ``SuperTILE`` block becomes a single composite :class:`Tile` whose
    ``tile_map`` holds the grid of sub-tile objects (stored top row first, matching
    the CSV order). Its wrapper switch matrix is its own ``switch_matrix`` and its
    wrapper BELs are its own ``bels``.

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
    list[Tile]
        List of composite Tile objects.
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

    new_composites: list[Tile] = []

    # Parse each supertile config into a composite tile
    for t in superTilesData:
        description = t.split("\n")
        name = description[0].split(",")[1]
        tile_map: list[list[Tile | None]] = []
        sub_tiles: list[Tile] = []
        bels: list[Bel] = []
        master_set = False
        master_offset: tuple[int, int] | None = None
        matrix_line_path: Path | None = None
        for i in description[1:-1]:
            line = i.split(",")
            line = [i for i in line if i != "" and i != " "]
            if not line:
                continue
            row: list[Tile | None] = []

            if line[0] == "BEL":
                belFilePath = filePath.joinpath(line[1])
                bels.append(Bel.from_hdl(belFilePath, line[2] if len(line) > 2 else ""))
                continue
            if line[0] == "MATRIX":
                # The wrapper switch matrix is given by this line's path,
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
                    tileDic[j].part_of_super_tile = True
                    sub_tile = deepcopy(tileDic[j])
                    row.append(sub_tile)
                    if sub_tile not in sub_tiles:
                        sub_tiles.append(sub_tile)
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
                # tile_map is built top row first (CSV order), so the row index is
                # simply the current number of rows already appended.
                row_index = len(tile_map)
                col_index = len(row) - 1
                if master_set:
                    raise InvalidSupertileDefinition(
                        f"Supertile '{name}': multiple MASTER tokens found."
                    )
                master_offset = (col_index, row_index)
                master_set = True
            tile_map.append(row)

        with_user_clk = any(bel.with_user_clock for bel in bels)

        # The wrapper switch matrix is taken from the MATRIX line (resolved
        # relative to the CSV). There is no auto-discovery: a supertile without a
        # MATRIX line simply has an empty wrapper matrix; its sub-tiles keep
        # their own matrices.
        switch_matrix = SwitchMatrix(matrix_file=Path())
        if matrix_line_path is not None:
            if not matrix_line_path.exists():
                raise InvalidSupertileDefinition(
                    f"Supertile '{name}': MATRIX file {matrix_line_path} "
                    "does not exist."
                )
            if matrix_line_path.suffix == ".list":
                connections = parseList(matrix_line_path, "source")
            else:
                connections = parseMatrix(matrix_line_path, name)
            validate_composite_tile_matrix(
                name, sub_tiles, bels, connections, matrix_line_path
            )
            switch_matrix = create_switch_matrix(matrix_line_path, name)

        # tile_dir is the supertile CSV file path (matching Tile.tile_dir), so
        # consumers use ``tile_dir.parent`` for the supertile's directory.
        compositeTile = Tile(
            name=name,
            ports=[],
            bels=bels,
            tile_dir=fileName.absolute(),
            matrix_dir=matrix_line_path if matrix_line_path is not None else Path(),
            gen_ios=[],
            user_clk=with_user_clk,
            switch_matrix=switch_matrix,
            tile_map=tile_map,
            sub_tiles=sub_tiles,
            master_offset=master_offset,
        )
        new_composites.append(compositeTile)

    return new_composites


def parse_tile_from_dir(tile_dir: Path, tile_name: str, is_supertile: bool) -> Tile:
    """Parse a single leaf or composite tile from its own directory.

    Reads `<tile_dir>/<tile_name>.csv` in isolation, without constructing a
    surrounding `Fabric`. For a composite, the sub-tile CSVs are read first (each
    from `<tile_dir>/<subtile>/<subtile>.csv`) to build the tile dictionary the
    composite definition references.

    Parameters
    ----------
    tile_dir : Path
        Directory containing the tile CSV and, for composites, the sub-tile
        subdirectories.
    tile_name : str
        Name of the tile or composite to return. Also the CSV file stem.
    is_supertile : bool
        Whether the target is a composite tile.

    Raises
    ------
    FileNotFoundError
        If `<tile_dir>/<tile_name>.csv` does not exist.
    InvalidTileDefinition
        If a leaf tile named `tile_name` is not present in the CSV.
    InvalidSupertileDefinition
        If a composite named `tile_name` is not present in the CSV.

    Returns
    -------
    Tile
        The parsed leaf or composite tile.
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

    # Collect the sub-tile names the composite references. The block is scanned
    # with the same regex, comment stripping, and token filtering
    # `parseSupertilesCSV` uses, so the two agree on which cells are sub-tile
    # names: the `BEL`/`MATRIX` control lines and the `MASTER`/`Null` placement
    # tokens are skipped, leaving only the sub-tile names.
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

    composites = parseSupertilesCSV(tile_csv, tile_dic)
    for composite in composites:
        if composite.name == tile_name:
            return composite
    raise InvalidSupertileDefinition(f"SuperTile {tile_name!r} not found in {tile_csv}")


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
    common_wire_pair: list[tuple[str, str]] = []
    fabricTiles = []
    tileDic: dict[str, Tile] = {}
    unusedTileDic: dict[str, Tile] = {}

    # Composite (former supertile) tiles, keyed by name and kept separate from
    # the leaf tileDic until both are merged below.
    compositeTileDic: dict[str, Tile] = {}

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
    new_tiles, new_common_wire_pair = parseTilesCSV(fName, preserveListOrder)
    tileTypes += [new_tile.name for new_tile in new_tiles]
    tileDefs += new_tiles
    common_wire_pair += new_common_wire_pair
    tileDic = dict(zip(tileTypes, tileDefs, strict=False))

    new_composites = parseSupertilesCSV(fName, tileDic)
    for new_composite in new_composites:
        compositeTileDic[new_composite.name] = new_composite

    if new_tiles or new_composites:
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
            new_composites = parseSupertilesCSV(filePath.joinpath(i[1]), tileDic)
            for new_composite in new_composites:
                compositeTileDic[new_composite.name] = new_composite
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

    # Merge composite tiles into the (un)used tile dictionaries. A composite is
    # used only if every one of its sub-tiles is used in the fabric grid.
    for name, composite in compositeTileDic.items():
        if any(sub.name not in usedTile for sub in composite.get_sub_tiles()):
            logger.info(
                f"Composite tile {name} is not used in the fabric. "
                "Removing from tile dictionary."
            )
            unusedTileDic[name] = composite
        else:
            tileDic[name] = composite

    # Reverse rows to use bottom-left origin coordinate system
    # After this: fabricTiles[0] = bottom row (y=0), fabricTiles[-1] = top row
    fabricTiles.reverse()

    height = len(fabricTiles)
    width = len(fabricTiles[0])

    common_wire_pair = list(dict.fromkeys(common_wire_pair))
    common_wire_pair = [
        (i, j) for (i, j) in common_wire_pair if "NULL" not in i and "NULL" not in j
    ]

    return Fabric(
        fabric_dir=fName,
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
        unusedTileDic=unusedTileDic,
        commonWirePair=common_wire_pair,
    )

"""Functions for fabric automation, such as generating tile configurations and IOs."""

import json
import math
import re
import shutil
import tempfile
from importlib import resources
from pathlib import Path

from loguru import logger

from fabulous.custom_exception import InvalidFileType, InvalidPortType, SpecMissMatch
from fabulous.fabric_definition.bel import Bel
from fabulous.fabric_definition.define import IO, HDLType, MultiplexerStyle
from fabulous.fabric_definition.gen_io import Gen_IO
from fabulous.fabric_definition.port import TilePort
from fabulous.fabric_generator.code_generator.code_generator import CodeGenerator
from fabulous.fabric_generator.code_generator.code_generator_Verilog import (
    VerilogCodeGenerator,
)
from fabulous.fabric_generator.code_generator.code_generator_VHDL import (
    VHDLCodeGenerator,
)
from fabulous.fabric_generator.parser.parse_hdl import parseBelFile
from fabulous.fabric_generator.parser.parse_switchmatrix import parseList
from fabulous.fabulous_settings import get_context


def generateCustomTileConfig(
    tile_path: Path, switch_matrix: bool = True, overwrite: bool = False
) -> Path:
    """Generate a custom tile configuration.

    A tile .csv file and a switch matrix .list file will be generated based on
    the given tile folder or the path to the BEL folder.

    The provided path may contain BEL files, which will be included
    in the generated tile .csv file as well as the generated
    switch matrix .list file.

    The tile CSV references the list file by path, so it is written only here,
    or on request with `parseTilesCSV(..., generate_matrix_list=True)`. Loading
    the fabric never regenerates it. A `.list` file in the tile folder, other
    than `<name>_switch_matrix.list` or the `<name>_generated_switch_matrix.list`
    that `MATRIX,GENERATE` used to write, is referenced instead of generating one.

    Files of an earlier generation, as listed by `existing_tile_outputs`, are
    only replaced with `overwrite`, and only once the BELs are known to be
    valid. If generating then fails, they are put back. After a successful
    regeneration, the BEL stubs already in `custom_prims.v` are refreshed.

    Parameters
    ----------
    tile_path : Path
        The path to the tile folder. If the path is a file, the parent
        directory will be used as the tile folder.
    switch_matrix : bool
        Whether to generate the switch matrix list. Default True. With False the
        tile CSV still references `<name>_switch_matrix.list`, which the user
        provides, and a BEL over the single-tile budget is rejected, since a
        supertile always needs its generated switch matrices.
    overwrite : bool
        Replace the output of an earlier generation. Default False.

    Returns
    -------
    Path
        Path to the generated tile .csv file.

    Raises
    ------
    FileExistsError
        If an earlier generation left output in the tile folder and `overwrite`
        is False.
    ValueError
        If the tile path is not a valid tile path, if the tile folder does not
        exist, or if the tile needs a supertile but `switch_matrix` is False.
    NotImplementedError
        If the tile is over the single-tile budget but has more than one BEL, which
        is not yet supported for supertile generation.
    """
    tile_name: str = ""
    project_tile_dir: Path = get_context().proj_dir / "Tile"

    tile_files = {}
    tile_csv: Path
    tile_bels: list[Path] = []
    tile_carrys = []
    tile_switchmatrix: Path
    csv_out: list[str] = []

    tile_path = Path(tile_path).absolute()

    logger.info(f"Generating custom tile config {tile_path}")

    if tile_path.is_file():
        tile_path = tile_path.parent

    tile_name = tile_path.stem
    tile_csv = tile_path / f"{tile_name}.csv"
    tile_switchmatrix = tile_path / f"{tile_name}_switch_matrix.list"

    if not tile_path.is_relative_to(project_tile_dir.absolute()):
        raise ValueError(f"Path {tile_path} is not a valid tile path")

    if not tile_path.exists():
        tile_path.mkdir()
    else:
        tile_files = tile_path.rglob("*")

    earlier = existing_tile_outputs(tile_path, switch_matrix)

    generated_lists = (
        f"{tile_name}_switch_matrix.list",
        f"{tile_name}_generated_switch_matrix.list",
    )
    for file in tile_files:
        if not file.is_file():
            logger.debug(f"Skipping file {file} since it is not a file.")
            continue
        # A list of another name is the user's switch matrix for this tile;
        # lists in subfolders belong to other tiles.
        if file.suffix.lower() == ".list":
            if file.parent == tile_path and file.name not in generated_lists:
                tile_switchmatrix = file
                logger.warning(
                    f"Found switch matrix list {file} for custom tile {tile_name}, "
                    "no switch matrix list will be generated."
                )
            continue
        # ConfigMem and switch matrix files, the `.v` BEL parsing writes next
        # to a VHDL BEL, and an earlier generation's output are not BELs.
        name = file.name.lower()
        if (
            any(
                m in name
                for m in ("configmem", "config_mem", "switchmatrix", "switch_matrix")
            )
            or (
                file.suffix == ".v"
                and any(file.with_suffix(e).is_file() for e in (".vhd", ".vhdl"))
            )
            or any(file.is_relative_to(p) for p in earlier)
        ):
            logger.debug(
                f"File {file} is most likely a generated file and will be ignored."
            )
            continue

        if file.suffix.lower() in [".vhdl", ".vhd", ".v", ".sv"]:
            logger.info(f"Found BEL file {file} for custom tile {tile_name}")
            tile_bels.append(file)

        else:
            logger.warning(
                f"File {file} in custom tile {tile_name} is not a valid config or "
                "bel file."
            )

    has_reset = False
    has_enable = False
    parsed_bels: list[Bel] = []
    for file in tile_bels:
        bel = parseBelFile(file, "")
        parsed_bels.append(bel)
        if "RESET" in bel.localShared:
            has_reset = True
        if "ENABLE" in bel.localShared:
            has_enable = True
        for carry in bel.carry:
            if carry not in tile_carrys:
                tile_carrys.append(carry)

    # If the BEL ports exceed the single-tile switch-matrix budget (32 inputs /
    # 8 outputs), emit a supertile instead of a single tile.
    # Summed per BEL: generated tile CSVs give BELs no prefix, so two BELs may
    # share port names, and the switch matrix still needs a pin for each.
    total_inputs = 0
    total_outputs = 0
    for b in parsed_bels:
        dedicated = set(_dedicated_ports(b))
        total_inputs += len({p.name for p in b.input_ports} - dedicated)
        total_outputs += len({p.name for p in b.output_ports} - dedicated)
    wide = total_inputs > 32 or total_outputs > 8
    if wide:
        if not switch_matrix:
            raise ValueError(
                f"The BELs of {tile_name} have {total_inputs} inputs / "
                f"{total_outputs} outputs, more than a single tile can route, and "
                "need a supertile, which always generates its switch matrices. "
                "Run generate_custom_tile_config without --no-switch-matrix."
            )
        if len(parsed_bels) != 1:
            raise NotImplementedError(
                "Supertile generation currently supports exactly one wide BEL per "
                f"tile, but {tile_name} has {len(parsed_bels)}."
            )
        _check_supertile_bel(tile_path, parsed_bels[0])

    # Everything that can be checked without writing is checked, so a caller
    # only gets to confirm a regeneration that would go ahead.
    if earlier and not overwrite:
        raise FileExistsError(
            f"Tile {tile_name} already has generated output: "
            f"{', '.join(map(str, earlier))}. Pass overwrite=True (CLI: --overwrite) "
            "to replace it."
        )

    # The earlier output is moved aside rather than deleted, so a generation
    # that fails halfway leaves the tile as it was.
    with tempfile.TemporaryDirectory() as backup_dir:
        backup = Path(backup_dir)
        for path in earlier:
            logger.warning(f"Replacing earlier tile output {path}")
            shutil.move(path, backup / path.name)
        done = False
        try:
            if wide:
                tile_csv = generate_custom_supertile_config(tile_path, parsed_bels[0])
            else:
                logger.info(f"Creating tile config CSV file {tile_csv}")
                csv_out.append(f"TILE,{tile_name}")
                csv_out.append("INCLUDE,./../include/Base.csv")
                for i, carry in enumerate(tile_carrys):
                    csv_out.append(f'NORTH,Co{i},0,-1,Ci{i},1,CARRY="{carry}"')
                if has_reset:
                    csv_out.append("JUMP,J_SRST_BEG,0,0,J_SRST_END,1,SHARED_RESET")
                if has_enable:
                    csv_out.append("JUMP,J_SEN_BEG,0,0,J_SEN_END,1,SHARED_ENABLE")
                for bel in tile_bels:
                    csv_out.append(f"BEL,./{bel.relative_to(tile_path)}")
                matrix = tile_switchmatrix.relative_to(tile_path).as_posix()
                csv_out.append(f"MATRIX,./{matrix}")
                csv_out.append("EndTILE")
                tile_csv.write_text("\n".join(csv_out), encoding="utf-8")
                if not tile_switchmatrix.exists() and switch_matrix:
                    # Imported here because parse_csv imports this module.
                    from fabulous.fabric_generator.parser.parse_csv import (
                        parseTilesCSV,
                    )

                    parseTilesCSV(tile_csv, generate_matrix_list=True)
                elif not tile_switchmatrix.exists():
                    logger.info(
                        f"Write the switch matrix {tile_switchmatrix} for tile "
                        f"{tile_name}, or generate it with "
                        "generate_switch_matrix_list."
                    )
            done = True
        finally:
            if not done:
                for path in existing_tile_outputs(tile_path, switch_matrix):
                    if path.is_dir():
                        shutil.rmtree(path)
                    else:
                        path.unlink()
                for path in earlier:
                    shutil.move(backup / path.name, path)

    # A BEL interface may have changed since its stub was written. Only existing
    # stubs are refreshed, so a regeneration adds none that a first generation
    # would not (there are none without a generated switch matrix).
    if earlier:
        prims_file = get_context().proj_dir / "user_design" / "custom_prims.v"
        prims = prims_file.read_text() if prims_file.is_file() else ""
        stubbed = []
        for b in parsed_bels:
            module = rf"^\s*module\s+{re.escape(b.module_name)}\b"
            if re.search(module, prims, re.MULTILINE):
                stubbed.append(b)
        if stubbed:
            addBelsToPrim(prims_file, stubbed, overwrite=True)
    return tile_csv


def is_supertile_csv(csv_path: Path) -> bool:
    """Tell whether a tile config CSV defines a supertile.

    Comments are stripped first, as `parseSupertilesCSV` does.

    Parameters
    ----------
    csv_path : Path
        The tile config CSV.

    Returns
    -------
    bool
        True if the first definition in the file is a `SuperTILE`.
    """
    text = re.sub(r"#.*", "", csv_path.read_text(encoding="utf-8"))
    return text.lstrip().startswith("SuperTILE")


def existing_tile_outputs(tile_path: Path, switch_matrix: bool = True) -> list[Path]:
    """List what an earlier tile config generation left in `tile_path`.

    That is the tile CSV, the `<name>_sub<N>` subtile folders, the switch matrix
    and ConfigMem files, the tile RTL `gen_tile` wrote, and the
    `<name>_generated_switch_matrix.list` of the removed `MATRIX,GENERATE`
    flow. Files are matched by name only, so a user file of such a name is
    listed as well. Without `switch_matrix`, the user provides
    `<name>_switch_matrix.list`, so it is not listed.

    Parameters
    ----------
    tile_path : Path
        The tile folder.
    switch_matrix : bool
        Whether generation writes the switch matrix list. Default True.

    Returns
    -------
    list[Path]
        Subtile folders first, then files.
    """
    name = tile_path.name
    sub_dirs = [
        d
        for d in tile_path.iterdir()
        if d.is_dir() and re.fullmatch(rf"{re.escape(name)}_sub\d+", d.name)
    ]
    files = [
        tile_path / f"{name}.csv",
        tile_path / f"{name}_generated_switch_matrix.list",
    ]
    files.extend(tile_path.glob(f"{name}_ConfigMem.*"))
    files.extend(
        f
        for f in tile_path.glob(f"{name}_switch_matrix.*")
        if switch_matrix or f.suffix != ".list"
    )
    # `<name>.v` could also be a user's BEL; it is only the tile RTL when
    # gen_tile wrote the switch matrix RTL next to it.
    for ext in ("v", "vhdl"):
        if (tile_path / f"{name}_switch_matrix.{ext}").is_file():
            files.append(tile_path / f"{name}.{ext}")
    return sorted(sub_dirs) + sorted({f for f in files if f.is_file()})


def _dedicated_ports(bel: Bel) -> list[str]:
    """Collect the BEL ports that never go through the switch matrix.

    Carry chain and local shared reset/enable ports get their own dedicated
    wiring, so they do not count against the 32-input / 8-output switch-matrix
    budget (see `generate_switch_matrix_list`).

    Parameters
    ----------
    bel : Bel
        The BEL to inspect.

    Returns
    -------
    list[str]
        Names of the carry and local shared ports.
    """
    ports = [port for directions in bel.carry.values() for port in directions.values()]
    ports.extend(port for port, _ in bel.localShared.values())
    return ports


def _slice_evenly(count: int, parts: int) -> list[int]:
    """Split `count` items into `parts` group sizes, as even as possible.

    Parameters
    ----------
    count : int
        Total number of items to distribute.
    parts : int
        Number of groups.

    Returns
    -------
    list[int]
        Group sizes; the first `count % parts` groups get one extra item.
    """
    base, extra = divmod(count, parts)
    return [base + (1 if i < extra else 0) for i in range(parts)]


def _check_supertile_bel(tile_path: Path, bel: Bel) -> None:
    """Reject a wide BEL that supertile generation cannot handle yet.

    Parameters
    ----------
    tile_path : Path
        The supertile folder.
    bel : Bel
        The wide BEL.

    Raises
    ------
    ValueError
        If the BEL file has the tile's name, which `gen_tile` would overwrite
        with the supertile RTL.
    NotImplementedError
        If the BEL has carry chains or local shared reset/enable ports.
    """
    name = tile_path.name
    if bel.src.stem == name:
        raise ValueError(
            f"BEL file {bel.src.name} has the name of tile {name}; gen_tile "
            f"writes the supertile RTL to {name}.v and would overwrite it. "
            "Rename the BEL file."
        )
    # Carry chains and local shared reset/enable are not split across subtiles
    # yet; anchoring them on the master subtile would lift this.
    dedicated = _dedicated_ports(bel)
    if dedicated:
        raise NotImplementedError(
            f"BEL {bel.name} uses CARRY or SHARED_RESET/SHARED_ENABLE ports "
            f"({', '.join(dedicated)}), which are not yet supported for supertile "
            "generation."
        )


def generate_custom_supertile_config(tile_path: Path, bel: Bel) -> Path:
    """Generate a supertile for a single BEL that exceeds the single-tile budget.

    The BEL ports are sliced evenly across a vertical stack of subtiles (one
    `SI` SJUMP port carrying a slice of the BEL inputs, one `SO` SJUMP port
    carrying a slice of the BEL outputs per subtile). Each subtile gets a full
    Base-derived switch matrix via `_switch_matrix_lines`; the supertile
    switch matrix is a 1:1 concatenation stitching the subtile SJUMP slices back
    onto the BEL's flat buses.

    CARRY and SHARED_RESET/SHARED_ENABLE ports are not yet distributed across
    subtiles, so a wide BEL using them is rejected.

    Parameters
    ----------
    tile_path : Path
        The supertile folder (under the project `Tile` directory); the BEL HDL
        already lives here and the subtile folders are created inside it. Files
        of an earlier generation there are overwritten.
    bel : Bel
        The wide BEL to distribute across the supertile.

    Returns
    -------
    Path
        Path to the generated supertile `.csv` file.
    """
    name = tile_path.name

    routed_inputs = [p.name for p in bel.input_ports]
    routed_outputs = [p.name for p in bel.output_ports]
    n_sub = max(math.ceil(len(routed_inputs) / 32), math.ceil(len(routed_outputs) / 8))
    in_widths = _slice_evenly(len(routed_inputs), n_sub)
    out_widths = _slice_evenly(len(routed_outputs), n_sub)

    logger.info(
        f"BEL {bel.name} has {len(bel.input_ports)} inputs / "
        f"{len(bel.output_ports)} outputs, "
        f"exceeding the single-tile budget; generating supertile {name} with "
        f"{n_sub} subtiles"
    )

    sub_names = [f"{name}_sub{i}" for i in range(n_sub)]
    base_csv = (get_context().proj_dir / "Tile" / "include" / "Base.csv").absolute()
    st_matrix_lines: list[str] = []
    in_cursor = 0
    out_cursor = 0
    for i, sub_name in enumerate(sub_names):
        si_w, so_w = in_widths[i], out_widths[i]
        sub_dir = tile_path / sub_name
        sub_dir.mkdir(parents=True, exist_ok=True)

        sm_lines = _switch_matrix_lines(
            sub_name,
            [f"SI{k}" for k in range(si_w)],
            [f"SO{k}" for k in range(so_w)],
        )
        (sub_dir / f"{sub_name}_switch_matrix.list").write_text("\n".join(sm_lines))

        include = base_csv.relative_to(sub_dir, walk_up=True).as_posix()
        sub_csv = [f"TILE,{sub_name}", f"INCLUDE,{include}"]
        # Trailing comma gives the port parser its expected 7th (attribute) column.
        if si_w:
            sub_csv.append(f"SJUMP,SI,0,0,NULL,{si_w},")
        if so_w:
            sub_csv.append(f"SJUMP,NULL,0,0,SO,{so_w},")
        sub_csv.append(f"MATRIX,./{sub_name}_switch_matrix.list")
        sub_csv.append("EndTILE")
        (sub_dir / f"{sub_name}.csv").write_text("\n".join(sub_csv))

        # Supertile matrix: sink,source. BEL input <- subtile SI (OUTPUT SJUMP);
        # subtile SO (INPUT SJUMP) <- BEL output.
        for k in range(si_w):
            st_matrix_lines.append(f"{routed_inputs[in_cursor + k]},{sub_name}_SI{k}")
        for k in range(so_w):
            st_matrix_lines.append(f"{sub_name}_SO{k},{routed_outputs[out_cursor + k]}")
        in_cursor += si_w
        out_cursor += so_w

    (tile_path / f"{name}_switch_matrix.list").write_text("\n".join(st_matrix_lines))

    st_csv = [f"SuperTILE,{name}"]
    st_csv.extend(sub_names)  # one subtile per row -> 1-wide x N-tall stack
    st_csv.append(f"BEL,./{bel.src.relative_to(tile_path).as_posix()}")
    st_csv.append(f"MATRIX,./{name}_switch_matrix.list")
    st_csv.append("EndSuperTILE")
    st_csv_path = tile_path / f"{name}.csv"
    st_csv_path.write_text("\n".join(st_csv))

    addBelsToPrim(get_context().proj_dir / "user_design" / "custom_prims.v", [bel])

    return st_csv_path


def _switch_matrix_lines(
    tile_name: str, inputs: list[str], outputs: list[str]
) -> list[str]:
    """Build switch matrix list lines that route the given ports into the fabric.

    The ports are substituted into a dummy list file derived from the LUT4AB
    switch matrix; unused multiplexers are dropped and the freed connections are
    spread over the least connected sinks.

    Parameters
    ----------
    tile_name : str
        Name of the tile, used in error messages.
    inputs : list[str]
        Ports the switch matrix drives, at most 32.
    outputs : list[str]
        Ports the switch matrix reads, at most 8.

    Returns
    -------
    list[str]
        The list file lines, starting with a "generated file" header.

    Raises
    ------
    ValueError
        If there are more than 32 inputs or more than 8 outputs.
    """
    with resources.path(
        "fabulous.fabric_files.dummy_files", "DUMMY_switch_matrix.list"
    ) as dummy_file_path:
        portPairs = parseList(dummy_file_path)

    if len(inputs) > 32:
        raise ValueError(
            f"Tile {tile_name} has {len(inputs)} Bel inputs, switchmatrix gen can "
            "only handle 32 inputs"
        )

    if len(outputs) > 8:
        raise ValueError(
            f"Tile {tile_name} has {len(outputs)} Bel outputs, switchmatrix gen can "
            "only handle 8 outputs"
        )

    # build a dict, with the old names from the list file and
    # the replacement from the bels
    replaceDic = {}
    for i, port in enumerate(inputs):
        replaceDic[f"CLB{math.floor(i / 4)}_I{i % 4}"] = f"{port}"
    for i, port in enumerate(outputs):
        replaceDic[f"CLB{i % 8}_O"] = f"{port}"

    # generate a list of sinks, with their connection count,
    # if they have at least 5 connections
    sinks_num = [sink for _, sink in portPairs]
    sinks_num = {i: sinks_num.count(i) for i in sinks_num if sinks_num.count(i) > 4}

    connections = {}
    for source, sink in portPairs:
        # replace the old names with the new ones
        if source in replaceDic:
            source = replaceDic[source]
        if sink in replaceDic:
            sink = replaceDic[sink]
        if "CLB" in source:
            # drop the whole multiplexer, if its not connected
            continue

        if source not in connections:
            connections[source] = []
        connections[source].append(sink)

    for source in connections:
        # copy the dict, since we need only want to update the connection count,
        # if we found a sink
        for i, sink in enumerate(connections[source]):
            if "CLB" in sink:
                sinks_num_run = sinks_num.copy()
                # replace sink with the sink with the lowest connection count and
                # check if it's already connected
                while True:
                    sink = min(sinks_num_run, key=lambda s: sinks_num_run[s])
                    sinks_num_run[sink] = sinks_num_run[sink] + 1
                    if sink not in connections[source]:
                        # update the real connection count, if we found a sink
                        sinks_num[sink] = sinks_num[sink] + 1
                        break
                # update dict
                connections[source][i] = sink

    # generate listfile strings
    listfile = []
    listfile.append("# --------------WARNING-----------------")
    listfile.append("# This is a generated list file!")
    listfile.append("# FABulous does not regenerate it on its own, so you can edit it.")
    listfile.append("# Running generate_switch_matrix_list overwrites your changes.")
    listfile.append("# --------------WARNING-----------------")

    for source, sinks in connections.items():
        muxsize = len(sinks)
        if muxsize % 2 != 0 and muxsize > 1:
            logger.warning(
                f"For source {source} mux size is {len(sinks)} with sinks: {sinks}"
            )
            listfile.append(f"# WARNING: Muxsize {muxsize} for source {source}")

        if muxsize == 1:
            listfile.append(f"{source},{sinks[0]}")
        else:  # generate a line for listfile
            rtmp = f"[{sinks[0]}"
            for sink in sinks[1:]:
                rtmp += f"|{sink}"
            rtmp += "]"
            ltmp = f"{{{len(sinks)}}}{source}"
            listfile.append(f"{ltmp},{rtmp}")

    return listfile


def generate_switch_matrix_list(
    tileName: str,
    bels: list[Bel],
    outFile: Path,
    carryportsTile: dict[str, dict[IO, str]],
    localSharedPortsTile: dict[str, list[TilePort]],
) -> None:
    """Generate a switch matrix list file for a given tile and its BELs.

    The list file is based on a dummy list file, derived from the LUT4AB switch matrix
    list file. It is also possible to automatically generate connections for carry
    chains between the BELs.

    Parameters
    ----------
    tileName :str
        Name of the tile
    bels : list[Bel]
        List of bels in the tile
    outFile : Path
        Path to the switchmatrix list file output
    carryportsTile : dict[str, dict[IO, str]]
        Dictionary of carry ports for the tile
    localSharedPortsTile : dict[str, list[TilePort]]
        List of local shared ports for the tile, based on JUMP wire definitions

    Raises
    ------
    ValueError
        - Carry port prefixes in tile config and bels do not match.
        - Bels have more than 32 Bel inputs.
        - Bels have more than 8 Bel outputs.
        - Invalid list formatting in file.
        - Number of carry ins and carry outs do not match.
    """
    projdir = get_context().proj_dir

    belIns = [p.name for bel in bels for p in bel.input_ports]
    belOuts = [p.name for bel in bels for p in bel.output_ports]
    belCarrys = [bel.carry for bel in bels]
    belLocalSharedPorts = [bel.localShared for bel in bels]

    # build carryports datastructure and
    # remove carrys from bel ports for further processing
    carryports: dict[str, dict[IO, list[str]]] = {}
    for carrys in belCarrys:
        for prefix in carrys:
            if prefix not in carryports:
                carryports[prefix] = {}
                carryports[prefix][IO.INPUT] = []
                carryports[prefix][IO.OUTPUT] = []
            carryports[prefix][IO.INPUT].append(carrys[prefix][IO.INPUT])
            belIns.remove(carrys[prefix][IO.INPUT])
            carryports[prefix][IO.OUTPUT].append(carrys[prefix][IO.OUTPUT])
            belOuts.remove(carrys[prefix][IO.OUTPUT])

    # check if carry prefixes match
    if set(carryportsTile.keys()) != set(carryports.keys()):
        logger.error(
            "Carry port prefixes in tile config and bels do not match! ",
            f"Carry prefixes in tile config: {set(carryportsTile.keys())}, ",
            f"carry prefixes in bels: {set(carryports.keys())}",
        )
        raise ValueError

    # Remove local shared ports from bel ports for further processing
    for bel in belLocalSharedPorts:
        for belType in bel:
            if bel[belType][0] in belIns:
                belIns.remove(bel[belType][0])
            if bel[belType][0] in belOuts:
                belOuts.remove(bel[belType][0])

    listfile = _switch_matrix_lines(tileName, belIns, belOuts)

    if carryports and carryportsTile:
        for prefix in carryportsTile:
            # append Tile carry in to beginning of output list,
            # since it should be connected to the first bel carry input
            carryports[prefix][IO.OUTPUT].insert(0, carryportsTile[prefix][IO.INPUT])
            # append Tile carry out to the end of output list,
            # since it should be connected to the last bel carry out
            carryports[prefix][IO.INPUT].append(carryportsTile[prefix][IO.OUTPUT])

            if len(carryports[prefix][IO.INPUT]) is not len(
                carryports[prefix][IO.OUTPUT]
            ):
                raise ValueError(
                    f"Carryports mismatch! There are "
                    f"{len(carryports[prefix][IO.INPUT])} "
                    f"INPUTS and {len(carryports[prefix][IO.OUTPUT])} outputs!"
                )

            listfile.append(f"# Connect carry chain {prefix}")
            for cin, cout in zip(
                carryports[prefix][IO.INPUT],
                carryports[prefix][IO.OUTPUT],
                strict=False,
            ):
                listfile.append(f"{cin},{cout}")

    # connecting SHARED_ENABLE and SHARED_RESET
    if "RESET" in localSharedPortsTile:
        sharedResetTile = localSharedPortsTile["RESET"]
        listfile.append("# Connect shared reset")
        # values taken from LUT4AB switchmatrix list, added VDD and GND0
        listfile.append(
            f"{{8}}{sharedResetTile[0].name}0,[J2MID_ABb_END0|J2MID_CDb_END0|J2MID_EFb_END0|J2MID_GHa_END0|JN2END1|JE2END1|JS2END1|JW2END1]"
        )
        for belport in belLocalSharedPorts:
            if bel_reset := belport["RESET"]:
                listfile.append(
                    f"{{2}}{bel_reset[0]},[{sharedResetTile[1].name}0|GND0]"
                )
    if "ENABLE" in localSharedPortsTile:
        sharedResetTile = localSharedPortsTile["ENABLE"]
        listfile.append("# Connect shared enable")
        # values taken from LUT4AB switchmatrix list, added VDD and GND0
        listfile.append(
            f"{{8}}{sharedResetTile[0].name}0,[J2MID_ABb_END3|J2MID_CDb_END3|J2MID_EFb_END3|J2MID_GHa_END3|JN2END2|JE2END2|JS2END2|JW2END2]"
        )
        for belport in belLocalSharedPorts:
            if bel_enable := belport["ENABLE"]:
                listfile.append(
                    f"{{2}}{bel_enable[0]},[{sharedResetTile[1].name}0|VCC0]"
                )

    with outFile.open("w") as f:
        f.write("\n".join(str(line) for line in listfile))

    primsFile = projdir.joinpath("user_design/custom_prims.v")
    if not primsFile.is_file():
        logger.info(f"Creating prims file {primsFile}")
        primsFile.touch()

    addBelsToPrim(primsFile, bels)


def addBelsToPrim(
    primsFile: Path,
    bels: list[Bel],
    support_vectors: bool = False,
    overwrite: bool = False,
) -> None:
    """Add a list of Bels as blackbox primitives to yosys prims file.

    Parameters
    ----------
    primsFile : Path
        Path to yosys prims file
    bels : list[Bel]
        List of bels to add
    support_vectors : bool
        Boolean to support vectors for ports in the prims file
        Default False,
        since the FABulous nextpn integration does not support vectors
    overwrite : bool
        Replace primitives that are already present in the prims file,
        instead of keeping the existing definition.
        Default False
    """
    prims: str = ""  # prims.v
    primsAdd: list[str] = []  # append to prims.v

    if primsFile.is_file():
        with primsFile.open() as f:
            prims = f.read()
    else:
        logger.warning(f"Prims file {primsFile} does not exist, creating a new one.")
        primsFile.touch()

    # remove all duplicate bels in list.
    bels = list({bel.src: bel for bel in bels}.values())

    if overwrite:
        for bel in bels:
            prims, removed = re.subn(
                rf"(^//Warning: The primitive {re.escape(bel.module_name)} [^\n]*\n)?"
                rf"(^[ \t]*\(\* blackbox[^\n]*\n)?"
                rf"^[ \t]*module\s+{re.escape(bel.module_name)}\s*\("
                rf".*?^[ \t]*endmodule[^\n]*\n?",
                "",
                prims,
                flags=re.MULTILINE | re.DOTALL,
            )
            if removed:
                logger.info(
                    f"Removing existing {bel.module_name} from yosys primitives file "
                    f"{primsFile}."
                )

    logger.info(
        f"Adding bels {', '.join(bel.name for bel in bels)} to yosys primitives file "
        f"{primsFile}."
    )

    for bel in bels:
        if bel.filetype != HDLType.VERILOG:
            logger.warning(
                f"Bel {bel.src} is not a Verilog file, "
                f"a generalized verilog description will be added to {primsFile}.",
                "This is experimental and may not work as expected!",
            )

        # check if belis already in prims file or already added to primsAdd
        if bel.module_name not in prims and bel.module_name not in " ".join(primsAdd):
            primsAdd.append(
                f"\n//Warning: The primitive {bel.module_name} was added by FABulous "
                f"automatically."
            )
            primsAdd.append("(* blackbox, keep *)")

            # build module sting for prim file
            modline = f"module {bel.module_name} (\n"

            # check if its first port, to not set a comma before
            first = True

            # ports contain the bel prefix, but this is not needed in the prims file
            inputs = [p.name.removeprefix(bel.prefix) for p in bel.input_ports]
            outputs = [p.name.removeprefix(bel.prefix) for p in bel.output_ports]
            shared_ports = [p.removeprefix(bel.prefix) for p, _ in bel.sharedPort]
            external_inputs: list[str] = []
            external_outputs: list[str] = []
            for external_port in bel.external_input_ports:
                external_inputs.append(external_port.name.removeprefix(bel.prefix))
            for external_port in bel.external_output_ports:
                external_outputs.append(external_port.name.removeprefix(bel.prefix))
            external_ports = external_inputs + external_outputs

            if support_vectors:
                # Find all ports with their directions
                # need to parse the json file again, since port width
                # is not known in BEL object
                with bel.src.with_suffix(".json").open() as f:
                    bel_dict = json.load(f)
                module_ports = bel_dict["modules"][bel.module_name]["ports"]

                # UserCLK needs to be renamed, otherwise yosys can't map the CLK
                if module_ports["UserCLK"]:
                    module_ports["CLK"] = module_ports["UserCLK"]
                    del module_ports["UserCLK"]
                # ConfigBits are not needed in the prims file
                if "ConfigBits" in module_ports:
                    del module_ports["ConfigBits"]

                ports_dict = {}
                for port_name, details in module_ports.items():
                    if details["direction"] not in ports_dict:
                        ports_dict[details["direction"]] = []
                    if len(details["bits"]) > 1:
                        ports_dict[details["direction"]].append(
                            f"[{len(details['bits']) - 1}:0] {port_name}"
                        )
                    else:
                        ports_dict[details["direction"]].append(port_name)

                # build portlist
                for direction, ports in ports_dict.items():
                    if not first:
                        modline += ",\n"
                    else:
                        first = False
                    for port in ports:
                        if port in external_ports:
                            # add pad attribute to external ports
                            modline += "    (* iopad_external_pin *)\n"
                        if port in shared_ports and port == "UserCLK":
                            port = "CLK"

                        modline += f"    {direction} {port}"
            else:  # No vector support
                ports = inputs + outputs + external_ports + shared_ports

                # we iterate through all ports to make the handling of the commas easier
                for port in ports:
                    if not first:
                        modline += ",\n"
                    else:
                        first = False
                    if port in inputs:
                        modline += f"    input {port}"
                    if port in outputs:
                        modline += f"    output {port}"
                    if port in external_ports:
                        modline += "    (* iopad_external_pin *)\n"
                        if port in external_inputs:
                            modline += f"    input {port}"
                        else:
                            modline += f"    output {port}"

                    if port in shared_ports:
                        direction = dict(bel.sharedPort)[port]
                        if port == "UserCLK":
                            # Rename UserCLK to CLK
                            # Otherwise Yosys can't map the CLK
                            port = "CLK"
                        modline += f"    {str(direction.value).lower()} {port}"

            modline += "\n);"

            belparams: dict[str, int] = {}
            for parameter in bel.belFeatureMap:
                parameter = parameter.split("[")[0]
                if parameter not in belparams:
                    belparams[parameter] = 0
                else:
                    belparams[parameter] += 1
            for param in belparams:
                if belparams[param] > 1:
                    modline += f"\n    parameter [{belparams[param]}:0] {param} = 0;"
                else:
                    modline += f"\n    parameter {param} = 0;"

            modline += "\nendmodule\n"
            primsAdd.append(modline)

            logger.info(
                f"{bel.module_name} added to yosys primitives file {primsFile}."
            )
        elif bel.module_name in prims:
            logger.info(
                f"{bel.module_name} already in yosys primitives file {primsFile}."
            )
        else:
            # Module already in list
            continue

    # write to prims file, line by line
    if overwrite:
        primsFile.write_text(prims + "\n".join(primsAdd))
    else:
        with primsFile.open("a") as f:
            f.write("\n".join(str(i) for i in primsAdd))


def genIOBel(
    gen_ios: list[Gen_IO],
    bel_path: Path,
    overwrite: bool = True,
    multiplexerStyle: MultiplexerStyle = MultiplexerStyle.CUSTOM,
) -> Bel | None:
    """Generate the IO BELs for a list of generative IOs.

    Parameters
    ----------
    gen_ios : list[Gen_IO]
        List of Generative IOs to generate the IO BEL.
    bel_path : Path
        Name of the BEL to be generated.
    overwrite : bool
        Default is True
        Overwrite the existing BEL file if it exists, by default True.
        If False, it will read the existing BEL file and return the Bel object,
        without generating a new one.
    multiplexerStyle : MultiplexerStyle
        Default is MultiplexerStyle.CUSTOM
        Use generic or custom multiplexers.

    Returns
    -------
    Bel | None
        The generated Bel object or None if no generative IOs are present.

    Raises
    ------
    InvalidFileType
        If a wrong bel file suffix is specified.
    InvalidPortType
        If an invalid IO type is specified for generative IOs.
    SpecMissMatch
        If the multiplexer style is not supported for generative IOs.
    ValueError
        If the number of config access ports does not match the number of config bits.
    """
    if len(gen_ios) == 0:
        logger.info(f"No generative IOs for {bel_path}, skipping genIOBel generation")
        return None

    bel_name = bel_path.stem
    language = bel_path.suffix.lower().replace(".", "")

    if language in ["v", "sv"]:
        language = "verilog"
    elif language in ["vhdl", "vhd"]:
        language = "vhdl"
    else:
        raise InvalidFileType(
            f"File suffix {language} of file {bel_path} is not supported for "
            f"genIOBel generation"
        )

    writer: CodeGenerator = (
        VHDLCodeGenerator() if language == "vhdl" else VerilogCodeGenerator()
    )
    writer.outFileName = bel_path

    logger.info(f"Generating Gen_IO BEL {bel_name} in {bel_path}")
    if bel_path.exists():
        if overwrite:
            logger.info(f"Overwriting existing Gen_IO BEL file: {bel_path}")
            bel_path.unlink()
        else:
            logger.info(f"Return existing Gen_IO BEL file: {bel_path}")
            return parseBelFile(bel_path, "")

    configBits = 0
    for gio in gen_ios:
        configBits += gio.configBit

    belMap: list[tuple[str, int]] = [("INIT", configBits)]

    writer.addComment(f"Generative IO BEL for {bel_name}", onNewLine=True)
    writer.addComment("This is a generated file, please don't edit!", onNewLine=True)
    writer.addNewLine()

    if configBits > 0:
        writer.addBelMapAttribute(belMap)

    writer.addHeader(f"{bel_name}")
    writer.addParameterStart(indentLevel=1)
    writer.addParameter("NoConfigBits", "integer", configBits, indentLevel=2)
    writer.addParameterEnd(indentLevel=1)
    writer.addPortStart(indentLevel=1)

    # Append generative IO ports as gel ports and also as external ports
    # Since one port goes to the fabric and one to the top level,
    # we need to generate both
    # Only the top-level ports are added to the externalPorts list

    externalPorts: list[tuple[str, IO, bool]] = []  # [(name, IO, reg)]
    internalPorts: list[tuple[str, IO, bool]] = []  # [(name, IO, reg)]
    configAccessPorts: list[tuple[str, bool]] = []  # [(name, inverted)]
    clocked = False

    for gio in gen_ios:
        if gio.clocked or gio.clockedComb or gio.clockedMux:
            clocked = True
        if gio.pins <= 0:
            logger.warning(f"Generative IO {gio.prefix} has no pins, skipping")
            continue
        for i in range(gio.pins):
            # for single pins we kick out the index
            j = "" if gio.pins == 1 else f"{i}"
            if gio.IO == IO.INPUT:
                if gio.configAccess:
                    raise ValueError(
                        "Generative IO cannot be an INPUT with config access!"
                    )
                internalPorts.append((f"{gio.prefix}{j}", IO.INPUT, False))
                if gio.clockedComb:  # clocked combinatorial also has a Q signal
                    # But only inputs produce a Q signal to the fabric top
                    externalPorts.append((f"{gio.prefix}_Q_top{j}", IO.OUTPUT, True))
                    externalPorts.append((f"{gio.prefix}_top{j}", IO.OUTPUT, False))
                elif gio.clocked:
                    externalPorts.append((f"{gio.prefix}_top{j}", IO.OUTPUT, True))
                else:  # combinatorial
                    externalPorts.append((f"{gio.prefix}_top{j}", IO.OUTPUT, False))
            elif gio.IO == IO.OUTPUT:
                if not gio.configAccess:
                    externalPorts.append((f"{gio.prefix}_top{j}", IO.INPUT, False))
                    if gio.clockedComb:
                        # clocked combinatorial also has a Q signal
                        internalPorts.append((f"{gio.prefix}_Q{j}", IO.OUTPUT, True))
                        internalPorts.append((f"{gio.prefix}{j}", IO.OUTPUT, False))
                    elif gio.clocked:
                        internalPorts.append((f"{gio.prefix}{j}", IO.OUTPUT, True))
                    else:  # combinatorial
                        internalPorts.append((f"{gio.prefix}{j}", IO.OUTPUT, False))

                else:
                    # if the GIO is a config access port,
                    # we need to add it to the external ports
                    externalPorts.append((f"{gio.prefix}{j}", IO.OUTPUT, False))
                    configAccessPorts.append((f"{gio.prefix}{j}", gio.inverted))
            else:
                raise InvalidPortType("Invalid IO type for generative IO")

    for port, direction, reg in internalPorts:
        writer.addPortScalar(port, direction, reg, indentLevel=2)

    for port, direction, reg in externalPorts:
        writer.addPortScalar(port, direction, reg, "EXTERNAL", indentLevel=2)

    if clocked:
        writer.addPortScalar(
            "UserCLK", IO.INPUT, False, "EXTERNAL, SHARED_PORT", indentLevel=2
        )

    if configBits > 0:
        if language == "vhdl":
            writer.addComment("GLOBAL", True, indentLevel=2)
            writer.addPortVector(
                "ConfigBits", IO.INPUT, "NoConfigBits-1", indentLevel=2
            )
        else:  #  Verilog
            writer.addPortVector(
                "ConfigBits",
                IO.INPUT,
                "NoConfigBits -1",
                attribute="GLOBAL",
                indentLevel=2,
            )

    writer.addPortEnd(indentLevel=1)
    writer.addHeaderEnd(f"{bel_name}")
    writer.addNewLine()
    # declare architecture
    writer.addDesignDescriptionStart(f"{bel_name}")
    writer.addLogicStart()

    # gen_io config bit access
    if any(gio.configAccess for gio in gen_ios):
        writer.addNewLine()
        writer.addComment("gen_io config access", onNewLine=True)
        if len(configAccessPorts) != configBits:
            raise SpecMissMatch(
                f"Config access ports ({len(configAccessPorts)}) do not match the "
                f"number of config bits ({configBits})"
            )
        for i in range(configBits):
            port, inverted = configAccessPorts[i]
            writer.addAssignScalar(
                f"{port}",
                f"ConfigBits[{i}]",
                inverted=inverted,
            )

    # gen_io assignments
    writer.addNewLine()
    # Each CLOCKED_MUX declaration uses the config bits after the previous ones.
    config_bit_offset = 0
    for gio in gen_ios:
        if gio.pins <= 0:
            logger.warning(f"Generative IO {gio.prefix} has no pins, skipping")
            continue
        if gio.configAccess:
            continue

        if gio.clocked:
            for i in range(gio.pins):
                # for single pins we kick out the index
                j = "" if gio.pins == 1 else f"{i}"
                if gio.IO == IO.INPUT:
                    writer.addRegister(
                        f"{gio.prefix}_top{j}",
                        f"{gio.prefix}{j}",
                        inverted=gio.inverted,
                    )
                elif gio.IO == IO.OUTPUT:
                    writer.addRegister(
                        f"{gio.prefix}{j}",
                        f"{gio.prefix}_top{j}",
                        inverted=gio.inverted,
                    )
        elif gio.clockedComb:
            # clocked combinatorial also has a Q signal and the original signal
            for i in range(gio.pins):
                # for single pins we kick out the index
                j = "" if gio.pins == 1 else f"{i}"
                if gio.IO == IO.INPUT:
                    writer.addRegister(
                        f"{gio.prefix}_Q_top{j}",
                        f"{gio.prefix}{j}",
                        inverted=gio.inverted,
                    )
                    writer.addAssignScalar(
                        f"{gio.prefix}_top{j}",
                        f"{gio.prefix}{j}",
                        inverted=gio.inverted,
                    )

                elif gio.IO == IO.OUTPUT:
                    writer.addRegister(
                        f"{gio.prefix}_Q{j}",
                        f"{gio.prefix}_top{j}",
                        inverted=gio.inverted,
                    )
                    writer.addAssignScalar(
                        f"{gio.prefix}{j}",
                        f"{gio.prefix}_top{j}",
                        inverted=gio.inverted,
                    )
        else:
            if gio.clockedMux:
                for i in range(gio.pins):
                    # for single pins we kick out the index
                    j = "" if gio.pins == 1 else f"{i}"

                    if gio.IO == IO.INPUT:
                        sink = f"{gio.prefix}_top{j}"
                        source = f"{gio.prefix}{j}"
                    else:
                        sink = f"{gio.prefix}{j}"
                        source = f"{gio.prefix}_top{j}"

                    reg = f"{gio.prefix}_Q{j}"
                    select = f"ConfigBits[{config_bit_offset + i}]"

                    writer.addConnectionScalar(reg, True)
                    writer.addRegister(
                        reg,
                        source,
                        inverted=gio.inverted,
                    )

                    if multiplexerStyle == MultiplexerStyle.CUSTOM:
                        portsPairs = [
                            ("A0", source),
                            ("A1", reg),
                            ("S", select),
                            ("X", sink),
                        ]
                        writer.addInstantiation(
                            compName="cus_mux21",
                            compInsName=f"inst_cus_mux21_{gio.prefix}{j}",
                            portsPairs=portsPairs,
                        )
                    else:
                        # generic multiplexer
                        if language == "vhdl":
                            writer.addAssignScalar(
                                sink,
                                f"{source} when ({select} = '0') else {reg}",
                            )
                        else:  # Verilog
                            writer.addAssignScalar(sink, f"{select} ? {reg} : {source}")

                config_bit_offset += gio.configBit
            else:
                for i in range(gio.pins):
                    # for single pins we kick out the index
                    j = "" if gio.pins == 1 else f"{i}"
                    if gio.IO == IO.INPUT:
                        writer.addAssignScalar(
                            f"{gio.prefix}_top{j}",
                            f"{gio.prefix}{j}",
                            inverted=gio.inverted,
                        )
                    elif gio.IO == IO.OUTPUT:
                        writer.addAssignScalar(
                            f"{gio.prefix}{j}",
                            f"{gio.prefix}_top{j}",
                            inverted=gio.inverted,
                        )

    writer.addNewLine()
    writer.addDesignDescriptionEnd()
    writer.addNewLine()
    writer.writeToFile()

    bel: Bel = parseBelFile(writer.outFileName, "")

    prims_file = get_context().proj_dir / "user_design" / "custom_prims.v"
    if not prims_file.exists():
        logger.info(f"Creating {prims_file}")
        prims_file.touch()

    addBelsToPrim(prims_file, [bel], False)

    return bel

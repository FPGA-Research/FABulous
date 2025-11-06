"""Functions for fabric automation, such as generating tile configurations and IOs."""

import json
import math
from importlib import resources
from pathlib import Path
from typing import TYPE_CHECKING

from loguru import logger

from FABulous.custom_exception import InvalidFileType, InvalidPortType, SpecMissMatch
from FABulous.fabric_definition.Bel import Bel
from FABulous.fabric_definition.define import IO, HDLType, MultiplexerStyle
from FABulous.fabric_definition.Gen_IO import Gen_IO
from FABulous.fabric_definition.Port import Port
from FABulous.fabric_generator.code_generator.code_generator_Verilog import (
    VerilogCodeGenerator,
)
from FABulous.fabric_generator.code_generator.code_generator_VHDL import (
    VHDLCodeGenerator,
)
from FABulous.fabric_generator.parser.parse_hdl import parseBelFile
from FABulous.fabric_generator.parser.parse_switchmatrix import parseList
from FABulous.FABulous_settings import get_context

if TYPE_CHECKING:
    from FABulous.fabric_generator.code_generator.code_generator import CodeGenerator


def generateCustomTileConfig(tile_path: Path) -> Path:
    """Generate a custom tile configuration.

    A tile .csv file and a switch matrix .list file will be generated based on
    the given tile folder or the path to the BEL folder.

    The provided path may contain BEL files, which will be included
    in the generated tile .csv file as well as the generated
    switch matrix .list file.

    Parameters
    ----------
    tile_path : Path
        The path to the tile folder. If the path is a file, the parent
        directory will be used as the tile folder.

    Returns
    -------
    Path
        Path to the generated tile .csv file.

    Raises
    ------
    ValueError
        If the tile path is not a valid tile path or if the tile folder does not exist.
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

    for file in tile_files:
        if not file.is_file():
            logger.debug(f"Skipping file {file} since it is not a file.")
            continue
        if (
            "configmem" in file.name.lower()
            or "config_mem" in file.name.lower()
            or "switchmatrix" in file.name.lower()
            or "switch_matrix" in file.name.lower()
        ):
            logger.debug(
                f"File {file}is most likely a generated file and will be ignored."
            )
            continue

        if file.suffix.lower() in [".vhdl", ".vhd", ".v", ".sv"]:
            logger.info(f"Found BEL file {file} for custom tile {tile_name}")
            tile_bels.append(file)

        elif file.suffix.lower() == ".csv":
            logger.warning(
                f"Found tile config CSV file {file} for custom tile {tile_name}, "
                "nothing to do here."
            )
            return file
        elif file.suffix.lower() == ".list":
            tile_switchmatrix = file
            logger.warning(
                f"Found tile tile_switchmatrix list file {file} for custom tile "
                f"{tile_name}, no switchmatrix list file will be generated."
            )
        else:
            logger.warning(
                f"File {file} in custom tile {tile_name} is not a valid config or "
                "bel file."
            )

    has_reset = False
    has_enable = False
    for file in tile_bels:
        bel = parseBelFile(file, "")
        if "RESET" in bel.localShared:
            has_reset = True
        if "ENABLE" in bel.localShared:
            has_enable = True
        for carry in bel.carry:
            if carry not in tile_carrys:
                tile_carrys.append(carry)
    # Create tile config CSV file
    logger.info(f"Creating tile config CSV file {tile_csv}")
    tile_csv.touch()

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
    if tile_switchmatrix.exists():
        csv_out.append(f"MATRIX,{tile_switchmatrix.relative_to(tile_path)}")
    else:
        csv_out.append("MATRIX,GENERATE")
    csv_out.append("EndTILE")

    with tile_csv.open("w", encoding="utf-8") as file:
        file.write("\n".join(csv_out))

    return tile_csv


def generateSwitchmatrixList(
    tileName: str,
    bels: list[Bel],
    outFile: Path,
    carryportsTile: dict[str, dict[IO, str]],
    localSharedPortsTile: dict[str, list[Port]],
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
    localSharedPortsTile : dict[str, list[Port]]
        List of local shared ports for the tile, based on JUMP wire definitions

    Raises
    ------
    ValueError
        - Bels have more than 32 Bel inputs.
        - Bels have more than 8 Bel outputs.
        - Invalid list formatting in file.
        - Number of carry ins and carry outs do not match.
    """
    projdir = get_context().proj_dir

    with resources.path(
        "FABulous.fabric_files.dummy_files", "DUMMY_switch_matrix.list"
    ) as dummy_file_path:
        CLBDummyFile = dummy_file_path

    belIns = sum((bel.inputs for bel in bels), [])
    belOuts = sum((bel.outputs for bel in bels), [])
    belCarrys = [bel.carry for bel in bels]
    portPairs = parseList(CLBDummyFile)
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

    # Remove local shared ports from bel ports for further processing
    for bel in belLocalSharedPorts:
        for belType in bel:
            if bel[belType][0] in belIns:
                belIns.remove(bel[belType][0])
            if bel[belType][0] in belOuts:
                belOuts.remove(bel[belType][0])

    if len(belIns) > 32:
        raise ValueError(
            f"Tile {tileName} has {len(belIns)} Bel inputs, switchmatrix gen can "
            "only handle 32 inputs"
        )

    if len(belOuts) > 8:
        raise ValueError(
            f"Tile {tileName} has {len(belOuts)} Bel outputs, switchmatrix gen can "
            "only handle 8 outputs"
        )

    # build a dict, with the old names from the list file and
    # the replacement from the bels
    replaceDic = {}
    for i, port in enumerate(belIns):
        replaceDic[f"CLB{math.floor(i / 4)}_I{i % 4}"] = f"{port}"
    for i, port in enumerate(belOuts):
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
                    sink = min(sinks_num_run, key=sinks_num_run.get)
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
    listfile.append("# Your changes will be overwritten!")
    listfile.append("# If you want to keep your changes,")
    listfile.append("# please make a copy of this file and edit your tile csv.")
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
            inputs = [p.removeprefix(bel.prefix) for p in bel.inputs]
            outputs = [p.removeprefix(bel.prefix) for p in bel.outputs]
            shared_ports = [p.removeprefix(bel.prefix) for p, _ in bel.sharedPort]
            external_inputs: list[str] = []
            external_outputs: list[str] = []
            for external_port in bel.externalInput:
                external_inputs.append(external_port.removeprefix(bel.prefix))
            for external_port in bel.externalOutput:
                external_outputs.append(external_port.removeprefix(bel.prefix))
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
    overwrite : bool, optional
        Default is True
        Overwrite the existing BEL file if it exists, by default True.
        If False, it will read the existing BEL file and return the Bel object,
        without generating a new one.
    multiplexerStyle : MultiplexerStyle, optional
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
                            ("S", f"ConfigBits[{i}]"),
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
                                f"{source} when (ConfigBits[{i}] = '0') else {reg}",
                            )
                        else:  # Verilog
                            writer.addAssignScalar(
                                sink, f"ConfigBits[{i}] ? {reg} : {source}"
                            )

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

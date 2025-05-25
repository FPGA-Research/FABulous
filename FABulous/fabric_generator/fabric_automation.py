import json
import math
import os
from pathlib import Path

from loguru import logger

from FABulous.fabric_definition.Bel import Bel
from FABulous.fabric_definition.Port import Port
from FABulous.fabric_definition.define import IO
from FABulous.fabric_generator.file_parser import parseBelFile, parseList


def generateCustomTileConfig(tile_path: Path) -> Path:
    """
    Generates a custom tile configuration for a given tile folder
    or path to bel folder.
    A tile .csv file and a switch matrix .list file will be generated.

    The provided path may contain bel files, which will be included
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

    """
    tile_name: str = ""
    project_tile_dir: Path = Path(os.getenv("FAB_PROJ_DIR")).absolute() / "Tile"

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
                f"Found tile config CSV file {file} for custom tile {tile_name}, nothing to do here."
            )
            return file
        elif file.suffix.lower() == ".list":
            tile_switchmatrix = file
            logger.warning(
                f"Found tile tile_switchmatrix list file {file} for custom tile {tile_name}, no switchmatrix list file will be generated."
            )
        else:
            logger.warning(
                f"File {file} in custom tile {tile_name} is not a valid config or bel file."
            )

    has_reset = False
    has_enable = False
    for file in tile_bels:
        if file.suffix.lower() in [".v", ".sv"]:
            bel = parseBelFile(file, "", "verilog")
        else:
            bel = parseBelFile(file, "", "vhdl")
        if "RESET" in bel.localShared.keys():
            has_reset = True
        if "ENABLE" in bel.localShared.keys():
            has_enable = True
        for carry in bel.carry:
            if carry not in tile_carrys:
                tile_carrys.append(carry)
    # Create tile config CSV file
    logger.info(f"Creating tile config CSV file {tile_csv}")
    tile_csv.touch()

    csv_out.append(f"TILE,{tile_name}")
    csv_out.append(f"INCLUDE,./../include/Base.csv")
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
):
    """Generate a switchmatrix list file for a given tile ans its bels. This list File
    is based on a dummy list file from CLB_DUMMY and is based on the LUT4AB switchtmatix
    list file. It is also possible to automatically generate connections for carry
    chains between the bels.

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
         localSharedPortsTile : dicst[str, list[Port]]
            list of local shared ports for the tile, based on JUMP wire definitions

    Raises
    ------
         ValueError
             Bels have more than 32 Bel inputs.
         ValueError
             Bels have more than 8 Bel outputs.
         ValueError
             Invalid list formatting in file.
         ValueError
             Number of carry ins and carry outs do not match.
    """
    projdir = Path(os.getenv("FAB_PROJ_DIR"))
    fab_root = Path(os.getenv("FAB_ROOT"))
    CLBDummyFile = (
        fab_root / "fabric_files" / "dummy_files" / "DUMMY_switch_matrix.list"
    )

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
        for type in bel:
            if bel[type][0] in belIns:
                belIns.remove(bel[type][0])
            if bel[type][0] in belOuts:
                belOuts.remove(bel[type][0])

    if len(belIns) > 32:
        raise ValueError(
            f"Tile {tileName} has {len(belIns)} Bel inputs, switchmatrix gen can only handle 32 inputs"
        )

    if len(belOuts) > 8:
        raise ValueError(
            f"Tile {tileName} has {len(belOuts)} Bel outputs, switchmatrix gen can only handle 8 outputs"
        )

    # build a dict, with the old names from the list file and the replacement from the bels
    replaceDic = {}
    for i, port in enumerate(belIns):
        replaceDic[f"CLB{math.floor(i / 4)}_I{i % 4}"] = f"{port}"
    for i, port in enumerate(belOuts):
        replaceDic[f"CLB{i % 8}_O"] = f"{port}"

    # generate a list of sinks, with their connection count, if they have at least 5 connections
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
        # copy the dict, since we need only want to update the connection count, if we found a sink
        for i, sink in enumerate(connections[source]):
            if "CLB" in sink:
                sinks_num_run = sinks_num.copy()
                # replace sink with the sink with the lowest connection count and check if it's already connected
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
                logger.error(
                    f"Carryports mismatch! There are {len(carryports[prefix][IO.INPUT])} INPUTS and {len(carryports[prefix][IO.OUTPUT])} outputs!"
                )
                raise ValueError()

            listfile.append(f"# Connect carry chain {prefix}")
            for cin, cout in zip(
                carryports[prefix][IO.INPUT], carryports[prefix][IO.OUTPUT]
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

    f = open(outFile, "w")
    f.write("\n".join(str(line) for line in listfile))
    f.close()

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
    """Adds a list of Bels as blackbox primitives to yosys prims file.

    Parameters
    ----------
        primsFile : str
            Path to yosys prims file
        bels : list[Bel]
            List of bels to add
        support_vectors : bool
            Boolean to support vectors for ports in the prims file
            Default False, since the FABulous nextpn integration does not support vectors
    Raises
    ------
        FileNotFoundError :
            Prims file is not found
    """
    prims: str = ""  # prims.v
    primsAdd: list[str] = []  # append to prims.v

    if primsFile.is_file():
        with open(primsFile, "r") as f:
            prims = f.read()
    else:
        logger.error(f"Prims file {primsFile} not found.")
        raise FileNotFoundError(f"Prims file {primsFile} not found.")

    # remove all duplicate bels in list.
    bels = list({bel.src: bel for bel in bels}.values())
    logger.info(
        f"Adding bels {', '.join(bel.name for bel in bels)} to yosys primitives file {primsFile}."
    )

    for bel in bels:
        if bel.filetype != "verilog":
            logger.warning(
                f"Bel {bel.src} is not a Verilog file, a generalized verilog description will be added to {primsFile}.",
                "This is experimental and may not work as expected!",
            )

        # check if belis already in prims file or already added to primsAdd
        if bel.module_name not in prims and bel.module_name not in " ".join(primsAdd):
            primsAdd.append(
                f"\n//Warning: The primitive {bel.module_name} was added by FABulous automatically."
            )
            primsAdd.append("(* blackbox, keep *)")

            # build module sting for prim file
            modline = f"module {bel.module_name} (\n"

            # check if its first port, to not set a comma before
            first = True

            shared_ports = [p for p, _ in bel.sharedPort]

            # external ports contain the bel prefix, but this is not needed in the prims file
            external_inputs: list[str] = []
            external_outputs: list[str] = []
            for external_port in bel.externalInput:
                external_inputs.append(external_port.removeprefix(bel.prefix))
            for external_port in bel.externalOutput:
                external_outputs.append(external_port.removeprefix(bel.prefix))
            external_ports = external_inputs + external_outputs

            if support_vectors:
                # Find all ports with their directions
                # need to parse the json file again, since port width is not known in BEL object
                with open(bel.src.with_suffix(".json"), "r") as f:
                    bel_dict = json.load(f)
                module_ports = bel_dict["modules"][bel.module_name]["ports"]

                # UserCLK needs to be renamed, otherwise yosys can't map the CLK
                if module_ports["UserCLK"]:
                    module_ports["CLK"] = module_ports["UserCLK"]
                    del module_ports["UserCLK"]
                # ConfigBits are not needed in the prims file
                if "ConfigBits" in module_ports.keys():
                    del module_ports["ConfigBits"]

                ports_dict = {}
                for port_name, details in module_ports.items():
                    if not details["direction"] in ports_dict:
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
                        if port in shared_ports:
                            # Rename UserCLK to CLK
                            # Otherwise Yosys can't map the CLK
                            if port == "UserCLK":
                                port = "CLK"
                        modline += f"    {direction} {port}"
            else:  # No vector support
                ports = bel.inputs + bel.outputs + external_ports + shared_ports

                for port in ports:
                    if not first:
                        modline += ",\n"
                    else:
                        first = False
                    if port in bel.inputs:
                        modline += f"    input {port}"
                    if port in bel.outputs:
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
    with open(primsFile, "a") as f:
        f.write("\n".join(str(i) for i in primsAdd))

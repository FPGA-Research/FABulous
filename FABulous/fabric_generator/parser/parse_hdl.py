import json
import re
import subprocess
from pathlib import Path
from typing import Literal

from loguru import logger

from FABulous.custom_exception import (
    FabricParsingError,
    InvalidBelDefinition,
    InvalidPortType,
)
from FABulous.fabric_definition.Bel import Bel
from FABulous.fabric_definition.define import IO


def verilog_belMapProcessing(module_info: dict) -> dict:
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
    for key, _value in attributes.items():
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
    return dict(reversed(list(belMapDic.items())))


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
                raise InvalidBelDefinition(
                    f"Invalid enum {enums[0]} in file {filename}"
                )
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
    ports_vectors: dict[
        str, dict[str, tuple[IO, int]]
    ] = {}  # {<porttype>:{porname:(IO, size)}}
    # define port types
    ports_vectors["internal"] = {}
    ports_vectors["external"] = {}
    ports_vectors["config"] = {}
    ports_vectors["shared"] = {}
    module_name = ""

    if filetype not in ["verilog", "vhdl"]:
        raise ValueError(f"Invalid filetype {filetype} for bel file {filename}")

    try:
        with filename.open() as f:
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
            raise InvalidBelDefinition(
                f"NoConfigBits does not match with the BEL map in file {filename}, length of BelMap is {len(belMapDic)}, but with {noConfigBits} config bits"
            )

        # FIXME: This is a temporary fix for the issue, that our vhdl parser can't handle vectors
        portmatch = file.split("-- GLOBAL")[0].lower()
        portmatch = portmatch[portmatch.find("port") :]  # trim everything before port
        if any(
            s in portmatch
            for s in ["std_logic_vector", "bit_vector", "integer", "signed", "unsigned"]
        ):
            raise InvalidPortType(
                f"Unsupported port type in {filename}. Currently only std_logic ports are supported for VHDL bels."
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
                    raise InvalidPortType(
                        f"Invalid or Unknown port direction {result.group(2).upper()} in line {line}."
                    )
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
                        raise InvalidBelDefinition(
                            f"SHARED_ENABLE or SHARED_RESET can only be used with INPUT ports in line {line}."
                        )
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
                    raise InvalidBelDefinition(
                        f"CARRY can't be used with INOUT ports for port {portName}!"
                    )
                if carryPrefix not in carry:
                    carry[carryPrefix] = {}
                if direction not in carry[carryPrefix]:
                    carry[carryPrefix][direction] = portName
                else:
                    raise InvalidBelDefinition(
                        f"Port {portName} with prefix {carryPrefix} can't be a carry {direction},"
                        f" since port {carry[carryPrefix][direction]} already is!"
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

        with json_file.open() as f:
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
        # modules should only contain one module
        module_name = next(iter(modules))
        module_info = modules[module_name]
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
                        raise InvalidBelDefinition(
                            f"SHARED_ENABLE or SHARED_RESET can only be used with INPUT ports in line {line}."
                        )
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

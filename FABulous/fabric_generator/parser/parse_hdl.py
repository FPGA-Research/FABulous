from pathlib import Path

from loguru import logger

from FABulous.custom_exception import (
    FabricParsingError,
    InvalidBelDefinition,
)
from FABulous.fabric_definition.Bel import Bel
from FABulous.fabric_definition.define import IO, FABulousAttribute
from FABulous.fabric_definition.Yosys_obj import YosysJson, YosysModule


def belMapProcessing(module_info: YosysModule) -> dict:
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
    # if BelMap not present defaults belMapDic to {}
    if "BelMap" not in module_info.attributes:
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
    for key, _value in module_info.attributes.items():
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


def parseBelFile(
    filename: Path,
    belPrefix: str = "",
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

    yosys_json = YosysJson(filename)
    modules = yosys_json.modules
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
    for port_name, details in module_info.ports.items():
        if "ConfigBits" in port_name:
            continue
        if "UserCLK" in port_name:
            userClk = True
        if port_name[-1].isdigit():
            # FIXME:  This is a temporary fix for the issue where the ports are individually declared
            #         Check for the last charcter in portname is not really reliable and sould be handeled more rubust in the future.
            individually_declared = True
        direction = IO[details.direction.upper()]
        filtered_ports[port_name] = (direction, details.bits)

    configBitsPort = module_info.ports.get("ConfigBits")
    noConfigBits = 0
    if configBitsPort:
        noConfigBits = len(configBitsPort.bits)
    # Passed attributes dont show in port list, checks for attributes in netnames.
    # (If passed attributes missing, may need to expand to check other lists e.g "memories".)
    for portName, (direction, bits) in filtered_ports.items():
        attributes = module_info.netnames[portName].attributes
        # Unrolled Ports
        for index in range(len(bits)):
            new_port_name = (
                f"{portName}{index}" if len(bits) > 1 else portName
            )  # Multi-bit ports get index
            if (
                FABulousAttribute.EXTERNAL in attributes
                and FABulousAttribute.SHARED_PORT not in attributes
            ):
                external.append((f"{belPrefix}{new_port_name}", direction))
            elif FABulousAttribute.CONFIG_BIT in attributes:
                config.append((f"{belPrefix}{new_port_name}", direction))
            elif FABulousAttribute.SHARED_PORT in attributes:
                shared.append((new_port_name, direction))
            else:
                internal.append((f"{belPrefix}{new_port_name}", direction))

            if "SHARED_ENABLE" in attributes or "SHARED_RESET" in attributes:
                if direction is not IO["INPUT"]:
                    raise InvalidBelDefinition(
                        "SHARED_ENABLE or SHARED_RESET can only be used with INPUT ports."
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

    belMapDic = belMapProcessing(module_info)
    if len(belMapDic) != noConfigBits:
        raise ValueError(
            f"NoConfigBits does not match with the BEL map in file {filename}, length of BelMap is {len(belMapDic)}, but with {noConfigBits} config bits"
        )

    return Bel(
        src=filename,
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

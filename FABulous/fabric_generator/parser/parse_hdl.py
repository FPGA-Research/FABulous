"""Contains functions for processing BEL related information from HDL files."""

import re
from pathlib import Path

from FABulous.custom_exception import (
    FabricParsingError,
    InvalidBelDefinition,
)
from FABulous.fabric_definition.Bel import Bel
from FABulous.fabric_definition.define import IO, FABulousAttribute
from FABulous.fabric_definition.Yosys_obj import YosysJson, YosysModule


def belMapProcessing(module_info: YosysModule) -> dict:
    """Extract and transform BEL mapping attributes in `YosysModule`.

    Parameters
    ----------
    module_info : YosysModule
        A dictionary containing the module's attributes, including
        potential BEL mapping information.

    Returns
    -------
    dict
        Dictionary containing the parsed bel mapping information.

    Raises
    ------
    ValueError
        If any BEL mapping attribute has an invalid format or index.
    """
    belMapDic = {}

    # update attributes to remove the fab_attr_ prefix, ignoring case
    fab_attrs = [key for key in module_info.attributes if "fab_attr_" in key.casefold()]
    for key in fab_attrs:
        attr = module_info.attributes.pop(key)
        key = re.sub(r"fab_attr_", "", key, flags=re.IGNORECASE)
        module_info.attributes[key] = attr

    # if BelMap not present defaults belMapDic to {}
    if "belmap" not in (attr.casefold() for attr in module_info.attributes):
        return belMapDic
    # Passed attributes that dont need appending. (May need refining.)
    exclude_attributes = {
        "BelMap",
        "FABulous",
        "dynports",
        "cells_not_processed",
        "src",
        "top",
    }

    # Second pass: convert keys to appropriate format
    atters = {}
    for key, value in module_info.attributes.items():
        # skip excluded attributes
        if key.casefold() in (item.casefold() for item in exclude_attributes):
            continue

        # check if value is an integer or digit string,
        # since it specifies the bit position
        if (type(value) is str and not value.isdigit()) and type(value) is not int:
            raise ValueError(
                f"BelMap attribute {key} does not have int / digit value:{value}."
            )

        # Check if key contains underscore and last part after underscore is all digits
        parts = key.rsplit("_", 1)  # Split from the right, only once
        if len(parts) == 2 and parts[1].isdigit():
            # Convert to vector notation: SOME_KEY_NAME_123 -> SOME_KEY_NAME[123]
            base_name = parts[0]
            index = parts[1]
            new_key = f"{base_name}[{index}]"
        else:
            # Leave key unchanged
            new_key = key

        atters[new_key] = int(value)

    # sort attributes by their integer values
    atters = dict(sorted(atters.items(), key=lambda item: item[1]))

    for i, (key, value) in enumerate(atters.items()):
        # check if the index matches the expected sequence
        if i != value:
            raise ValueError(
                f"BelMap attribute {key} has incorrect index {value}."
                f" Expected value {i}."
            )

        belMapDic[key] = {0: {0: "1"}}

    return belMapDic


def parseBelFile(
    filename: Path,
    belPrefix: str = "",
) -> Bel:
    """Parse a Verilog or VHDL BEL file and return related information of the BEL.

    The function will also parse and record all the FABulous attributes
    which all start with:

        (* FABulous, <type>, ... *)

    The <type> can be one the following:

    * **BelMap**
    * **EXTERNAL**
    * **SHARED_PORT**
    * **GLOBAL**
    * **CONFIG_PORT**
    * **SHARED_ENABLE**
    * **SHARED_RESET**

    The **BelMap** attribute will specify the bel mapping for the bel.
    This attribute should be placed before the start of the module.
    The bel mapping is then used for generating the bitstream specification.
    Each of the entry in the attribute will have the following format::

    <name> = <value>

    ``<name>`` is the name of the feature and ``<value>`` will be the
    bit position of the feature. ie. ``INIT=0`` will specify that the feature
    ``INIT`` is located at bit 0.
    Since a single feature can be mapped to multiple bits, this is currently done by
    specifying multiple entries for the same feature.
    This will be changed in the future.
    The bit specification is done in the following way::

        INIT_a_1=1, INIT_a_2=2, ...

    The name of the feature will be converted to ``INIT_a[1]``, ``INIT_a[2]``
    for the above example. This is necessary
    because  Verilog does not allow square brackets as part of the attribute name.

    **EXTERNAL** attribute will notify FABulous to put the pin in the top module during
    the fabric generation.

    **SHARED_PORT** attribute will notify FABulous this the pin is shared between
    multiple bels. Attribute need to go with
    the **EXTERNAL** attribute.

    **GLOBAL** attribute will notify FABulous to stop parsing any pin after this
    attribute.

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
        module exampleModule (
            externalPin,
            normalPin1,
            normalPin2,
            sharedPin,
            globalPin);
            (* FABulous, EXTERNAL *) input externalPin;
            input normalPin;
            (* FABulous, EXTERNAL, SHARED_PORT *) input sharedPin;
            (* FABulous, GLOBAL) input globalPin;
            output normalPin2; //do not get parsed
            ...

    Parameters
    ----------
    filename : Path
        The filename of the bel file.
    belPrefix : str, optional
        The bel prefix provided by the CSV file. Defaults to "".

    Returns
    -------
    Bel
        A Bel object containing all the parsed information.

    Raises
    ------
    FabricParsingError
        Fabric cannot be parsed
    InvalidBelDefinition
        The BEL file contains invalid BEL definitions. Such as wrong attribute type on
        wrong port type. i.e SHARE_EN on output ports
    ValueError
        Port naming is reused
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
    noConfigBits = 0
    belMapDic = {}
    ports_vectors: dict[str, dict[str, tuple[IO, int]]] = {}
    # define port types
    ports_vectors["internal"] = {}
    ports_vectors["external"] = {}
    ports_vectors["config"] = {}
    ports_vectors["shared"] = {}

    yosys_json = YosysJson(filename)
    filtered_ports: dict[str, tuple[IO, list]] = {}

    if len(yosys_json.modules) == 0:
        raise FabricParsingError(f"File {filename} does not contain any modules.")

    # Gathers port name and direction, filters out configbits as they show in ports.
    # modules should only contain one module
    module_name, module_info = yosys_json.getTopModule()
    for port_name, details in module_info.ports.items():
        if "ConfigBits" in port_name:
            continue
        if "UserCLK" in port_name:
            userClk = True
        direction = IO[details.direction.upper()]
        filtered_ports[port_name] = (direction, details.bits)

    configBitsPort = module_info.ports.get("ConfigBits")
    noConfigBits = 0
    if configBitsPort:
        noConfigBits = len(configBitsPort.bits)
    # Passed attributes dont show in port list, checks for attributes in netnames.
    # (If passed attributes missing, may need to expand to check other lists
    # e.g "memories".)
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
                        "SHARED_ENABLE or SHARED_RESET can only be used with "
                        "INPUT ports."
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
                        f"CARRY can't be used with INOUT ports for port "
                        f"{new_port_name}!"
                    )
                if carryPrefix not in carry:
                    carry[carryPrefix] = {}
                if direction not in carry[carryPrefix]:
                    carry[carryPrefix][direction] = f"{belPrefix}{new_port_name}"
                else:
                    raise ValueError(
                        f"Port {portName} with prefix {carryPrefix} can't be a "
                        f"carry {direction}, since port "
                        f"{carry[carryPrefix][direction]} already is!"
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
            f"NoConfigBits does not match with the BEL map in file {filename}, "
            f"length of BelMap is {len(belMapDic)}, but with {noConfigBits} "
            "config bits"
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
        ports_vectors=ports_vectors,
        carry=carry,
        localShared=localSharedPorts,
    )

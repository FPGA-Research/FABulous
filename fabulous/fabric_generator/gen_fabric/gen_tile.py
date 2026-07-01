"""Tile generation module for FABulous FPGA architecture.

This module generates RTL code for individual tiles and super tiles within an FPGA
fabric. It handles the integration of Basic Elements of Logic (BELs), switch matrices,
and configuration infrastructure into complete tile implementations.

Key features:
- Individual tile RTL generation with BEL instantiation
- Switch matrix integration and port mapping
- Configuration data routing and management
- Supertile wrapper generation for hierarchical designs
- Support for both VHDL and Verilog code generation
- External I/O port handling and clock distribution
"""

from collections import defaultdict
from pathlib import Path

from fabulous.fabric_definition.define import IO, ConfigBitMode, Direction
from fabulous.fabric_definition.supertile import SuperTile
from fabulous.fabric_definition.tile import Tile
from fabulous.fabric_generator.code_generator.code_generator import CodeGenerator
from fabulous.fabric_generator.code_generator.code_generator_Verilog import (
    VerilogCodeGenerator,
)
from fabulous.fabric_generator.code_generator.code_generator_VHDL import (
    VHDLCodeGenerator,
)


def generateTile(
    writer: CodeGenerator,
    tile: Tile,
    frame_bits_per_row: int = 32,
    max_frame_per_col: int = 20,
    disable_user_clk: bool = False,
    config_bit_mode: ConfigBitMode = ConfigBitMode.FRAME_BASED,
) -> None:
    """Generate the RTL code for a tile given the tile object.

    This function creates the complete RTL implementation for a tile, including:
    - Port declarations for all tile connections
    - BEL instantiations with proper port mapping
    - Switch matrix instantiation and connections
    - Configuration infrastructure (frame-based or FlipFlop chain)
    - Clock and reset signal distribution
    - Jump wire handling for long-distance connections

    We first check if we need a configuration port. Currently we assume that each
    primitive needs a configuration port. However, a switch matrix can have no switch
    matrix multiplexers (e.g., when only bouncing back in border termination tiles)

    TODO: we don't do this and always create a configuration port for each tile.
    This dangle the CLK and MODE ports hanging in the air, which will throw a warning

    Each switch matrix entity is built up in a specific order:

    ```
    1.a) interconnect wire INPUTS (in the order defined by the fabric file)
    2.a) BEL primitive INPUTS (in the order the BEL-VHDLs are listed
         in the fabric CSV) within each BEL, the order from the entity is
         maintained. Note that INPUTS refers to the view of the switch
         matrix! Which corresponds to BEL outputs at the actual BEL
    3.a) JUMP wire INPUTS (in the order defined by the fabric file)
    1.b) interconnect wire OUTPUTS
    2.b) BEL primitive OUTPUTS
         Again: OUTPUTS refers to the view of the switch matrix which
         corresponds to BEL inputs at the actual BEL
    3.b) JUMP wire OUTPUTS
    ```

    The switch matrix uses single bit ports (std_logic and not std_logic_vector)!!!


    Parameters
    ----------
    writer : CodeGenerator
        The code generator instance for RTL output
    tile : Tile
        The tile object containing BELs and port information
    frame_bits_per_row : int
        Number of configuration bits per row for frame-based configuration
    max_frame_per_col : int
        Maximum number of frames per column for frame-based configuration
    disable_user_clk : bool
        If True, the UserCLK port will not be generated or connected
    config_bit_mode : ConfigBitMode
        The configuration bit mode to use (frame-based or FlipFlop chain)

    Raises
    ------
    FileNotFoundError
        Only raised for VHDL output. If required component files
        (e.g., switch matrix or config memory) are missing.
    """
    allJumpWireList = []

    writer.addHeader(f"{tile.name}")
    writer.addParameterStart(indentLevel=1)
    if isinstance(writer, VerilogCodeGenerator):  # emulation only in Verilog
        maxBits = frame_bits_per_row * max_frame_per_col
        writer.addPreprocIfDef("EMULATION")
        writer.addParameter(
            "Emulate_Bitstream",
            f"[{maxBits - 1}:0]",
            f"{maxBits}'b0",
            indentLevel=2,
        )
        writer.addPreprocEndif()
    writer.addParameter("MaxFramesPerCol", "integer", max_frame_per_col, indentLevel=2)
    writer.addParameter("FrameBitsPerRow", "integer", frame_bits_per_row, indentLevel=2)
    if tile.globalConfigBits > 0:
        writer.addParameter(
            "NoConfigBits", "integer", tile.globalConfigBits, indentLevel=2
        )

    writer.addParameterEnd(indentLevel=1)
    writer.addPortStart(indentLevel=1)

    # holder for each direction of port string
    portList = (
        tile.getNorthSidePorts()
        + tile.getEastSidePorts()
        + tile.getWestSidePorts()
        + tile.getSouthSidePorts()
    )

    side_of_port = None
    for port in portList:
        if side_of_port is not port.sideOfTile:
            side_of_port = port.sideOfTile
            writer.addComment(str(side_of_port), onNewLine=True)
        # destination port are input to the tile
        # source port are output of the tile
        wireSize = (abs(port.xOffset) + abs(port.yOffset)) * port.wireCount - 1
        writer.addPortVector(port.name, port.inOut, wireSize, indentLevel=2)
        writer.addComment(str(port), indentLevel=2, onNewLine=False)

    # SJUMP ports: OUTPUT exits toward supertile SM; INPUT enters from supertile SM
    sjump_ports = tile.get_sjump_ports()
    if sjump_ports:
        writer.addComment(
            "SJUMP ports (supertile BEL interface)", onNewLine=True, indentLevel=1
        )
        for p in sjump_ports:
            writer.addPortVector(p.name, p.inOut, f"{p.wireCount}-1", indentLevel=2)

    # now we have to scan all BELs if they use external pins,
    # because they have to be exported to the tile entity
    externalPorts = []
    for i in tile.bels:
        for p in i.externalInput:
            writer.addPortScalar(p, IO.INPUT, indentLevel=2)
        for p in i.externalOutput:
            writer.addPortScalar(p, IO.OUTPUT, indentLevel=2)
        externalPorts += i.externalInput
        externalPorts += i.externalOutput

    # if we found BELs with top-level IO ports, we just pass them through
    sharedExternalPorts = set()
    for i in tile.bels:
        sharedExternalPorts.update(i.sharedPort)

    writer.addComment("Tile IO ports from BELs", onNewLine=True, indentLevel=1)

    if not disable_user_clk:
        writer.addPortScalar("UserCLK", IO.INPUT, indentLevel=2)
        writer.addPortScalar("UserCLKo", IO.OUTPUT, indentLevel=2)

    if config_bit_mode == ConfigBitMode.FRAME_BASED:
        writer.addPortVector("FrameData", IO.INPUT, "FrameBitsPerRow-1", indentLevel=2)
        writer.addComment("CONFIG_PORT", onNewLine=False, end="")
        writer.addPortVector(
            "FrameData_O", IO.OUTPUT, "FrameBitsPerRow-1", indentLevel=2
        )
        writer.addPortVector(
            "FrameStrobe", IO.INPUT, "MaxFramesPerCol-1", indentLevel=2
        )
        writer.addComment("CONFIG_PORT", onNewLine=False, end="")
        writer.addPortVector(
            "FrameStrobe_O", IO.OUTPUT, "MaxFramesPerCol-1", indentLevel=2
        )

    elif config_bit_mode == ConfigBitMode.FLIPFLOP_CHAIN:
        writer.addPortScalar("MODE", IO.INPUT, indentLevel=2)
        writer.addPortScalar("CONFin", IO.INPUT, indentLevel=2)
        writer.addPortScalar("CONFout", IO.OUTPUT, indentLevel=2)
        writer.addPortScalar("CLK", IO.INPUT, indentLevel=2)

    writer.addComment("global", onNewLine=True, indentLevel=1)

    writer.addPortEnd()
    writer.addHeaderEnd(f"{tile.name}")
    writer.addDesignDescriptionStart(f"{tile.name}")

    # insert switch matrix and config_mem component declaration
    if isinstance(writer, VHDLCodeGenerator):
        # insert CLB, I/O (or whatever BEL) component declaration
        # specified in the fabric csv file after the 'BEL' key word
        # we use this list to check if we have seen a BEL description
        # before so we only insert one component declaration
        BEL_VHDL_riles_processed = []
        for i in tile.bels:
            if i.src not in BEL_VHDL_riles_processed:
                BEL_VHDL_riles_processed.append(i.src)
                writer.addComponentDeclarationForFile(i.src)

        basePath = Path(writer.outFileName).parent

        if (basePath / f"{tile.name}_switch_matrix.vhdl").exists():
            writer.addComponentDeclarationForFile(
                f"{basePath}/{tile.name}_switch_matrix.vhdl"
            )
        else:
            raise FileNotFoundError(
                f"Could not find {tile.name}_switch_matrix.vhdl in {basePath} "
                "Need to run matrix generation first"
            )

        if tile.globalConfigBits > 0:
            if (basePath / f"{tile.name}_ConfigMem.vhdl").exists():
                writer.addComponentDeclarationForFile(
                    f"{basePath}/{tile.name}_ConfigMem.vhdl"
                )
            else:
                raise FileNotFoundError(
                    f"Could not find {tile.name}_ConfigMem.vhdl in {basePath} "
                    "config_mem generation first"
                )

    # signal declarations
    writer.addComment("signal declarations", onNewLine=True)
    # BEL port wires
    writer.addComment("BEL ports (e.g., slices)", onNewLine=True)
    repeatDeclaration = set()
    for bel in tile.bels:
        for i in bel.inputs + bel.outputs:
            if f"{i}" not in repeatDeclaration:
                writer.addConnectionScalar(i)
                repeatDeclaration.add(f"{bel.prefix}{i}")

    # Jump wires
    writer.addComment("Jump wires", onNewLine=True)
    for p in tile.portsInfo:
        if p.wireDirection == Direction.JUMP:
            if (
                p.sourceName != "NULL"
                and p.destinationName != "NULL"
                and p.inOut == IO.OUTPUT
            ):
                writer.addConnectionVector(p.name, f"{p.wireCount}-1")

            for k in range(p.wireCount):
                allJumpWireList.append(f"{p.name}( {k} )")

    # SJUMP ports are module ports (declared above) and are wired to the switch
    # matrix directly in the instantiation below, so they need no internal wire.

    # internal configuration data signal to daisy-chain all BELs
    # (if any and in the order they are listed in the fabric.csv)
    writer.addComment(
        "internal configuration data signal to daisy-chain all BELs (if any and in "
        "the order they are listed in the fabric.csv)",
        onNewLine=True,
    )

    # the signal has to be number of BELs+2 bits wide (Bel_counter+1 downto 0)
    # we chain switch matrices only to the configuration port,
    # if they really contain configuration bits
    # i.e. switch matrices have a config port which is indicated by
    # `NumberOfConfigBits:0 is false`

    # The following conditional as intended to only generate the config_data signal if
    # really anything is actually configured
    # however, we leave it and just use this signal as conf_data(0 downto 0) for simply
    # touting through CONFin to CONFout
    # maybe even useful if we want to add a buffer here

    # all the signal wire need to declare first for compatibility with VHDL
    if tile.globalConfigBits > 0:
        writer.addConnectionVector("ConfigBits", "NoConfigBits-1", 0)
        writer.addConnectionVector("ConfigBits_N", "NoConfigBits-1", 0)

    writer.addNewLine()
    writer.addComment("Connection for outgoing wires", onNewLine=True)
    writer.addConnectionVector("FrameData_i", "FrameBitsPerRow-1", 0)
    writer.addConnectionVector("FrameData_O_i", "FrameBitsPerRow-1", 0)
    writer.addConnectionVector("FrameStrobe_i", "MaxFramesPerCol-1", 0)
    writer.addConnectionVector("FrameStrobe_O_i", "MaxFramesPerCol-1", 0)

    added = set()
    for port in tile.portsInfo:
        span = abs(port.xOffset) + abs(port.yOffset)
        if (port.sourceName, port.destinationName) in added:
            continue
        if span >= 2 and port.sourceName != "NULL" and port.destinationName != "NULL":
            highBoundIndex = span * port.wireCount - 1
            writer.addConnectionVector(f"{port.destinationName}_i", highBoundIndex)
            writer.addConnectionVector(
                f"{port.sourceName}_i", highBoundIndex - port.wireCount
            )
            added.add((port.sourceName, port.destinationName))

    writer.addNewLine()
    writer.addLogicStart()

    # buffer FrameData signals
    writer.addAssignScalar("FrameData_O_i", "FrameData_i")
    writer.addNewLine()
    for i in range(frame_bits_per_row):
        writer.addInstantiation(
            "my_buf",
            f"data_inbuf_{i}",
            portsPairs=[("A", f"FrameData[{i}]"), ("X", f"FrameData_i[{i}]")],
        )
    for i in range(frame_bits_per_row):
        writer.addInstantiation(
            "my_buf",
            f"data_outbuf_{i}",
            portsPairs=[
                ("A", f"FrameData_O_i[{i}]"),
                ("X", f"FrameData_O[{i}]"),
            ],
        )

    # strobe is always added even when config bits are 0
    writer.addAssignScalar("FrameStrobe_O_i", "FrameStrobe_i")
    writer.addNewLine()
    for i in range(max_frame_per_col):
        writer.addInstantiation(
            "my_buf",
            f"strobe_inbuf_{i}",
            portsPairs=[("A", f"FrameStrobe[{i}]"), ("X", f"FrameStrobe_i[{i}]")],
        )

    for i in range(max_frame_per_col):
        writer.addInstantiation(
            "my_buf",
            f"strobe_outbuf_{i}",
            portsPairs=[
                ("A", f"FrameStrobe_O_i[{i}]"),
                ("X", f"FrameStrobe_O[{i}]"),
            ],
        )

    added = set()
    for port in tile.portsInfo:
        span = abs(port.xOffset) + abs(port.yOffset)
        if (port.sourceName, port.destinationName) in added:
            continue
        if span >= 2 and port.sourceName != "NULL" and port.destinationName != "NULL":
            highBoundIndex = span * port.wireCount - 1
            # using scalar assignment to connect the two vectors
            # could replace with assign as vector,
            # but will lose the - wireCount readability
            writer.addAssignScalar(
                f"{port.sourceName}_i[{highBoundIndex}-{port.wireCount}:0]",
                f"{port.destinationName}_i[{highBoundIndex}:{port.wireCount}]",
            )
            writer.addNewLine()
            for i in range(highBoundIndex - port.wireCount + 1):
                writer.addInstantiation(
                    "my_buf",
                    f"{port.destinationName}_inbuf_{i}",
                    portsPairs=[
                        ("A", f"{port.destinationName}[{i + port.wireCount}]"),
                        ("X", f"{port.destinationName}_i[{i + port.wireCount}]"),
                    ],
                )
            for i in range(highBoundIndex - port.wireCount + 1):
                writer.addInstantiation(
                    "my_buf",
                    f"{port.sourceName}_outbuf_{i}",
                    portsPairs=[
                        ("A", f"{port.sourceName}_i[{i}]"),
                        ("X", f"{port.sourceName}[{i}]"),
                    ],
                )

            added.add((port.sourceName, port.destinationName))

    if not disable_user_clk:
        writer.addInstantiation(
            "clk_buf",
            "inst_clk_buf",
            portsPairs=[("A", "UserCLK"), ("X", "UserCLKo")],
        )

    writer.addNewLine()
    # top configuration data daisy chaining
    if config_bit_mode == ConfigBitMode.FLIPFLOP_CHAIN:
        writer.addComment("top configuration data daisy chaining", onNewLine=True)
        writer.addAssignScalar("conf_data(conf_data'low)", "CONFin")
        writer.addComment("conf_data'low=0 and CONFin is from tile entity")
        writer.addAssignScalar("conf_data(conf_data'high)", "CONFout")
        writer.addComment("CONFout is from tile entity")

    if config_bit_mode == ConfigBitMode.FRAME_BASED and tile.globalConfigBits > 0:
        writer.addComment("configuration storage latches", onNewLine=True)
        writer.addInstantiation(
            compName=f"{tile.name}_ConfigMem",
            compInsName=f"Inst_{tile.name}_ConfigMem",
            portsPairs=[
                ("FrameData", "FrameData"),
                ("FrameStrobe", "FrameStrobe"),
                ("ConfigBits", "ConfigBits"),
                ("ConfigBits_N", "ConfigBits_N"),
            ],
            emulateParamPairs=[("Emulate_Bitstream", "Emulate_Bitstream")],
        )

    # BEL component instantiations
    if tile.bels:
        writer.addNewLine()
        writer.addComment("BEL component instantiations", onNewLine=True)

    belCounter = 0
    belConfigBitsCounter = 0
    for bel in tile.bels:
        port_dict = defaultdict(list)
        portsPairs = []
        portList = []
        signal = []
        userclk_pair = None

        # build port list for internal and external ports
        for port_type, bel_ports in bel.ports_vectors.items():
            if port_type in ["external", "internal"]:
                for port_name, info in bel_ports.items():
                    _direction, width = info
                    if width > 1:
                        port_dict[port_name] = [
                            (f"{bel.prefix}{port_name}{i}", f"{i}")
                            for i in range(width)
                        ]
                    else:
                        port_dict[port_name] = [
                            (f"{bel.prefix}{port_name}", f"{i}") for i in range(width)
                        ]

        # Shared ports
        for port in bel.sharedPort:
            if port[0] == "UserCLK":
                if not disable_user_clk:
                    userclk_pair = (port[0], port[0])
            else:
                portsPairs.append((port[0], port[0]))

        for portname, ports in port_dict.items():
            if len(ports) > 1:
                # Sort ports based on bit significance.
                ports.sort(key=lambda x: int(x[1]) if x[1].isdigit() else -1)
                # Concatenate the ports in the correct order.
                concatenated_ports = ", ".join(port for port, _ in ports[::-1])
                portsPairs.append((portname, f"{{{concatenated_ports}}}"))
            else:
                # Single port, no need for concatenation.
                single_port = ports[0][0]
                portsPairs.append((portname, single_port))

        # Makes sure UserCLK is after ports.
        if userclk_pair is not None:
            portsPairs.append(userclk_pair)

        if config_bit_mode == ConfigBitMode.FRAME_BASED:
            if bel.configBit > 0:
                portsPairs.append(
                    (
                        "ConfigBits",
                        f"ConfigBits[{belConfigBitsCounter + bel.configBit}-1:"
                        f"{belConfigBitsCounter}]",
                    )
                )
        elif config_bit_mode == ConfigBitMode.FLIPFLOP_CHAIN:
            portsPairs.append(("MODE", "Mode"))
            portsPairs.append(("CONFin", f"conf_data({belCounter})"))
            portsPairs.append(("CONFout", f"conf_data({belCounter + 1})"))
            portsPairs.append(("CLK", "CLK"))

        writer.addInstantiation(
            compName=bel.name,
            compInsName=f"Inst_{bel.prefix}{bel.name}",
            portsPairs=portsPairs,
        )

        # FIXME: Why is the belCounter increased here by 2 and afterwards by 1?
        belCounter += 2
        belConfigBitsCounter += bel.configBit

        # for the next BEL (if any) for cascading configuration chain
        # (this information is also needed for chaining the switch matrix)
        belCounter += 1

    portsPairs = []
    # normal input wire (excludes JUMP and SJUMP, which are handled separately;
    # otherwise SJUMP inputs would be bound twice in the switch-matrix instance)
    for i in tile.portsInfo:
        if (
            i.wireDirection not in (Direction.JUMP, Direction.SJUMP)
            and i.inOut == IO.INPUT
        ):
            portsPairs += list(
                zip(
                    i.expandPortInfoByName(),
                    i.expandPortInfoByName(indexed=True),
                    strict=False,
                )
            )
    # bel input wire (bel output is input to switch matrix)
    for bel in tile.bels:
        for p in bel.outputs:
            portsPairs.append((p, p))

    # jump input wire
    port, signal = [], []
    for i in tile.portsInfo:
        if i.wireDirection == Direction.JUMP and i.inOut == IO.INPUT:
            port += i.expandPortInfoByName()
        if i.wireDirection == Direction.JUMP and i.inOut == IO.OUTPUT:
            signal += i.expandPortInfoByName(indexed=True)

    portsPairs += list(zip(port, signal, strict=False))

    # normal output wire (excludes JUMP and SJUMP which are handled separately)
    for i in tile.portsInfo:
        if (
            i.wireDirection not in (Direction.JUMP, Direction.SJUMP)
            and i.inOut == IO.OUTPUT
        ):
            portsPairs += list(
                zip(
                    i.expandPortInfoByName(),
                    i.expandPortInfoByNameTop(indexed=True),
                    strict=False,
                )
            )

    # bel output wire (bel input is input to switch matrix)
    for bel in tile.bels:
        for p in bel.inputs:
            portsPairs.append((p, p))

    # jump output wire
    port, signal = [], []
    for i in tile.portsInfo:
        if i.wireDirection == Direction.JUMP and i.inOut == IO.OUTPUT:
            port += i.expandPortInfoByName()
        if i.wireDirection == Direction.JUMP and i.inOut == IO.OUTPUT:
            signal += i.expandPortInfoByName(indexed=True)

    portsPairs += list(zip(port, signal, strict=True))

    # sjump output wire - SM drives SJUMP OUTPUT signals exiting to supertile SM
    port, signal = [], []
    for i in tile.portsInfo:
        if i.wireDirection == Direction.SJUMP and i.inOut == IO.OUTPUT:
            port += i.expandPortInfoByName()
            signal += i.expandPortInfoByName(indexed=True)

    portsPairs += list(zip(port, signal, strict=True))

    # sjump input wire - SJUMP INPUT signals enter SM as sources from supertile SM.
    # The tile port is a vector, so index into it (Q[0]) rather than using the
    # scalar SM-port name (Q0), which would be a floating implicit wire.
    port, signal = [], []
    for i in tile.portsInfo:
        if i.wireDirection == Direction.SJUMP and i.inOut == IO.INPUT:
            port += i.expandPortInfoByName()
            signal += i.expandPortInfoByName(indexed=True)

    portsPairs += list(zip(port, signal, strict=True))

    if config_bit_mode == ConfigBitMode.FLIPFLOP_CHAIN:
        portsPairs.append(("MODE", "Mode"))
        portsPairs.append(("CONFin", f"conf_data({belCounter})"))
        portsPairs.append(("CONFout", f"conf_data({belCounter + 1})"))
        portsPairs.append(("CLK", "CLK"))

    if config_bit_mode == ConfigBitMode.FRAME_BASED and tile.globalConfigBits > 0:
        portsPairs.append(
            (
                "ConfigBits",
                f"ConfigBits[{tile.globalConfigBits}-1:{belConfigBitsCounter}]",
            )
        )
        portsPairs.append(
            (
                "ConfigBits_N",
                f"ConfigBits_N[{tile.globalConfigBits}-1:{belConfigBitsCounter}]",
            )
        )

    writer.addInstantiation(
        compName=f"{tile.name}_switch_matrix",
        compInsName=f"Inst_{tile.name}_switch_matrix",
        portsPairs=portsPairs,
    )

    writer.addDesignDescriptionEnd()
    writer.writeToFile()


def generateSuperTile(
    writer: CodeGenerator,
    superTile: SuperTile,
    frame_bits_per_row: int = 32,
    max_frame_per_col: int = 20,
    disable_user_clk: bool = False,
    config_bit_mode: ConfigBitMode = ConfigBitMode.FRAME_BASED,
) -> None:
    """Generate a super tile wrapper for given super tile.

    Creates a hierarchical wrapper that instantiates multiple individual tiles
    and manages their interconnections. The supertile handles:
    - Internal tile-to-tile connections within the supertile
    - External port mapping to fabric-level connections
    - Configuration data distribution to sub-tiles
    - Clock signal routing and buffering
    - External I/O port aggregation

    Parameters
    ----------
    writer : CodeGenerator
        The code generator instance for RTL output
    superTile : SuperTile
        Super tile object containing tile map and configuration
    frame_bits_per_row : int
        Number of configuration bits per row for frame-based configuration
    max_frame_per_col : int
        Maximum number of frames per column for frame-based configuration
    disable_user_clk : bool
        If True, the UserCLK port will not be generated or connected
    config_bit_mode : ConfigBitMode
        The configuration bit mode to use (frame-based or FlipFlop chain)
    """
    writer.addHeader(f"{superTile.name}")
    writer.addParameterStart(indentLevel=1)
    if isinstance(writer, VerilogCodeGenerator):
        writer.addPreprocIfDef("EMULATION")
        maxBits = frame_bits_per_row * max_frame_per_col
        for y, row in enumerate(superTile.tileMap):
            for x, tile in enumerate(row):
                if not tile:
                    continue
                writer.addParameter(
                    f"Tile_X{x}Y{y}_Emulate_Bitstream",
                    f"[{maxBits - 1}:0]",
                    f"{maxBits}'b0",
                    indentLevel=2,
                )
        writer.addPreprocEndif()
    writer.addParameter("MaxFramesPerCol", "integer", max_frame_per_col, indentLevel=2)
    writer.addParameter("FrameBitsPerRow", "integer", frame_bits_per_row, indentLevel=2)

    writer.addParameterEnd(indentLevel=1)
    writer.addPortStart(indentLevel=1)

    portsAround = superTile.getPortsAroundTile()

    for k, v in portsAround.items():
        if not v:
            continue
        x, y = k.split(",")
        for pList in v:
            # Skip empty port lists
            if not pList:
                continue

            writer.addComment(
                f"Tile_X{x}Y{y}_{pList[0].wireDirection}",
                onNewLine=True,
                indentLevel=1,
            )
            for p in pList:
                wire = (abs(p.xOffset) + abs(p.yOffset)) * p.wireCount - 1
                writer.addPortVector(
                    f"Tile_X{x}Y{y}_{p.name}", p.inOut, wire, indentLevel=2
                )
                writer.addComment(str(p), onNewLine=False)

    # add tile external bel port
    writer.addComment("Tile IO ports from BELs", onNewLine=True, indentLevel=1)
    for i in superTile.tiles:
        for b in i.bels:
            for p in b.externalInput:
                writer.addPortScalar(p, IO.INPUT, indentLevel=2)
            for p in b.externalOutput:
                writer.addPortScalar(p, IO.OUTPUT, indentLevel=2)
            for p in b.sharedPort:
                if p[0] == "UserCLK":
                    continue
                writer.addPortScalar(p[0], p[1], indentLevel=2)

    # add supertile-level BEL external ports
    if superTile.bels:
        writer.addComment("SuperTile BEL IO ports", onNewLine=True, indentLevel=1)
        for b in superTile.bels:
            for p in b.externalInput:
                writer.addPortScalar(p, IO.INPUT, indentLevel=2)
            for p in b.externalOutput:
                writer.addPortScalar(p, IO.OUTPUT, indentLevel=2)

    st_config_bits = superTile.total_config_bits

    # add config port
    if config_bit_mode == ConfigBitMode.FRAME_BASED:
        for y, row in enumerate(superTile.tileMap):
            for x, tile in enumerate(row):
                if tile is None:
                    continue
                if y - 1 < 0 or superTile.tileMap[y - 1][x] is None:
                    writer.addPortVector(
                        f"Tile_X{x}Y{y}_FrameStrobe_O",
                        IO.OUTPUT,
                        "MaxFramesPerCol-1",
                        indentLevel=2,
                    )
                    writer.addComment("CONFIG_PORT", onNewLine=False)
                if x - 1 < 0 or superTile.tileMap[y][x - 1] is None:
                    writer.addPortVector(
                        f"Tile_X{x}Y{y}_FrameData",
                        IO.INPUT,
                        "FrameBitsPerRow-1",
                        indentLevel=2,
                    )
                    writer.addComment("CONFIG_PORT", onNewLine=False)
                if (
                    y + 1 >= len(superTile.tileMap)
                    or superTile.tileMap[y + 1][x] is None
                ):
                    writer.addPortVector(
                        f"Tile_X{x}Y{y}_FrameStrobe",
                        IO.INPUT,
                        "MaxFramesPerCol-1",
                        indentLevel=2,
                    )
                    writer.addComment("CONFIG_PORT", onNewLine=False)
                if (
                    x + 1 >= len(superTile.tileMap[y])
                    or superTile.tileMap[y][x + 1] is None
                ):
                    writer.addPortVector(
                        f"Tile_X{x}Y{y}_FrameData_O",
                        IO.OUTPUT,
                        "FrameBitsPerRow-1",
                        indentLevel=2,
                    )
                    writer.addComment("CONFIG_PORT", onNewLine=False)
    if not disable_user_clk:
        for y, row in enumerate(superTile.tileMap):
            for x, tile in enumerate(row):
                if tile is None:
                    continue
                if y - 1 < 0 or superTile.tileMap[y - 1][x] is None:
                    writer.addPortScalar(
                        f"Tile_X{x}Y{y}_UserCLKo", IO.OUTPUT, indentLevel=2
                    )
                if (
                    y + 1 >= len(superTile.tileMap)
                    or superTile.tileMap[y + 1][x] is None
                ):
                    writer.addPortScalar(
                        f"Tile_X{x}Y{y}_UserCLK", IO.INPUT, indentLevel=2
                    )
    writer.addPortEnd()
    writer.addHeaderEnd(f"{superTile.name}")
    writer.addDesignDescriptionStart(f"{superTile.name}")
    writer.addNewLine()

    if isinstance(writer, VHDLCodeGenerator):
        for t in superTile.tiles:
            # This is only relevant to VHDL code generation,
            # will not affect Verilog code generation
            writer.addComponentDeclarationForFile(
                f"{Path(writer.outFileName).parent}/{t.name}/{t.name}.vhdl"
            )

    # find all internal connections
    internalConnections = superTile.getInternalConnections()

    # declare internal connections
    writer.addComment("signal declarations", onNewLine=True)

    # SJUMP signals: one vector per (child tile, SJUMP port) pair
    sjump_ports = superTile.get_all_sjump_ports()
    if sjump_ports:
        writer.addComment("SJUMP signals (child tile -> supertile SM)", onNewLine=True)
        for lx, ly, p in sjump_ports:
            writer.addConnectionVector(
                f"{superTile.tileMap[ly][lx].name}_{p.name}",
                f"{p.wireCount}-1",
                indentLevel=1,
            )

    # Reverse SJUMP signals: supertile SM -> child tile inputs
    all_input_sjump = superTile.get_all_input_sjump_ports()
    if all_input_sjump:
        writer.addComment("SJUMP signals (supertile SM -> child tile)", onNewLine=True)
        for lx, ly, p in all_input_sjump:
            writer.addConnectionVector(
                f"{superTile.tileMap[ly][lx].name}_{p.name}",
                f"{p.wireCount}-1",
                indentLevel=1,
            )

    # BEL pin signals bridging the supertile BELs and the switch matrix
    bel_pin_signals = [
        pin for bel in superTile.bels for pin in (*bel.inputs, *bel.outputs)
    ]
    if bel_pin_signals:
        writer.addComment("BEL pin signals (BEL <-> supertile SM)", onNewLine=True)
        for pin in bel_pin_signals:
            writer.addConnectionScalar(pin, indentLevel=1)

    for i, x, y in internalConnections:
        if i:
            writer.addComment(f"Tile_X{x}Y{y}_{i[0].wireDirection}", onNewLine=True)
            for p in i:
                if p.inOut == IO.OUTPUT:
                    wire = (abs(p.xOffset) + abs(p.yOffset)) * p.wireCount - 1
                    writer.addConnectionVector(
                        f"Tile_X{x}Y{y}_{p.name}", wire, indentLevel=1
                    )
                    writer.addComment(str(p), onNewLine=False)

    # declare internal connections for frameData, frameStrobe, and UserCLK
    for y, row in enumerate(superTile.tileMap):
        for x, tile in enumerate(row):
            if tile is None:
                continue
            if (
                0 <= y - 1 < len(superTile.tileMap)
                and superTile.tileMap[y - 1][x] is not None
            ):
                writer.addConnectionVector(
                    f"Tile_X{x}Y{y}_FrameStrobe_O",
                    "MaxFramesPerCol-1",
                    indentLevel=1,
                )
                if not disable_user_clk:
                    writer.addConnectionScalar(f"Tile_X{x}Y{y}_UserCLKo", indentLevel=1)
            if (
                0 <= x + 1 < len(superTile.tileMap[y])
                and superTile.tileMap[y][x + 1] is not None
            ):
                writer.addConnectionVector(
                    f"Tile_X{x}Y{y}_FrameData_O", "FrameBitsPerRow-1", indentLevel=1
                )

    if st_config_bits > 0 and config_bit_mode == ConfigBitMode.FRAME_BASED:
        writer.addConnectionVector(
            "ST_ConfigBits", f"{st_config_bits}-1", indentLevel=1
        )
        writer.addConnectionVector(
            "ST_ConfigBits_N", f"{st_config_bits}-1", indentLevel=1
        )

    writer.addNewLine()

    writer.addLogicStart()

    # pair up the connection for tile instantiation
    for y, row in enumerate(superTile.tileMap):
        for x, tile in enumerate(row):
            northInput, southInput, eastInput, westInput = [], [], [], []
            portsPairs = []
            if tile is None:
                continue

            # north direction input connection
            northPort = [i.name for i in tile.getNorthPorts(IO.INPUT)]
            if (
                0 <= y + 1 < len(superTile.tileMap)
                and superTile.tileMap[y + 1][x] is not None
            ):
                for p in superTile.tileMap[y + 1][x].getNorthPorts(IO.OUTPUT):
                    northInput.append(f"Tile_X{x}Y{y + 1}_{p.name}")
            else:
                for p in tile.getNorthPorts(IO.INPUT):
                    northInput.append(f"Tile_X{x}Y{y}_{p.name}")

            portsPairs += list(zip(northPort, northInput, strict=False))
            # east direction input connection
            eastPort = [i.name for i in tile.getEastPorts(IO.INPUT)]
            if (
                0 <= x - 1 < len(superTile.tileMap[0])
                and superTile.tileMap[y][x - 1] is not None
            ):
                for p in superTile.tileMap[y][x - 1].getEastPorts(IO.OUTPUT):
                    eastInput.append(f"Tile_X{x - 1}Y{y}_{p.name}")
            else:
                for p in tile.getEastPorts(IO.INPUT):
                    eastInput.append(f"Tile_X{x}Y{y}_{p.name}")

            portsPairs += list(zip(eastPort, eastInput, strict=False))

            # south direction input connection
            southPort = [
                i.name for i in tile.getSouthPorts(IO.INPUT) if i.inOut == IO.INPUT
            ]
            if (
                0 <= y - 1 < len(superTile.tileMap)
                and superTile.tileMap[y - 1][x] is not None
            ):
                for p in superTile.tileMap[y - 1][x].getSouthPorts(IO.OUTPUT):
                    southInput.append(f"Tile_X{x}Y{y - 1}_{p.name}")
            else:
                for p in tile.getSouthPorts(IO.INPUT):
                    southInput.append(f"Tile_X{x}Y{y}_{p.name}")

            portsPairs += list(zip(southPort, southInput, strict=False))

            # west direction input connection
            westPort = [
                i.name for i in tile.getWestPorts(IO.INPUT) if i.inOut == IO.INPUT
            ]
            if (
                0 <= x + 1 < len(superTile.tileMap[0])
                and superTile.tileMap[y][x + 1] is not None
            ):
                for p in superTile.tileMap[y][x + 1].getWestPorts(IO.OUTPUT):
                    westInput.append(f"Tile_X{x + 1}Y{y}_{p.name}")
            else:
                for p in tile.getWestPorts(IO.INPUT):
                    westInput.append(f"Tile_X{x}Y{y}_{p.name}")

            portsPairs += list(zip(westPort, westInput, strict=False))

            for p in (
                tile.getNorthPorts(IO.OUTPUT)
                + tile.getEastPorts(IO.OUTPUT)
                + tile.getSouthPorts(IO.OUTPUT)
                + tile.getWestPorts(IO.OUTPUT)
            ):
                portsPairs.append((p.name, f"Tile_X{x}Y{y}_{p.name}"))

            for b in tile.bels:
                for p in b.externalInput:
                    portsPairs.append((p, p))

                for p in b.externalOutput:
                    portsPairs.append((p, p))

                if not disable_user_clk:
                    for p in b.sharedPort:
                        if "UserCLK" not in p[0]:
                            portsPairs.append(("UserCLK", p[0]))

            # connect SJUMP ports to supertile-level signals
            for p in tile.get_sjump_ports():
                portsPairs.append((p.name, f"{tile.name}_{p.name}"))

            # add clock to tile
            if not disable_user_clk:
                if (
                    0 <= y + 1 < len(superTile.tileMap)
                    and superTile.tileMap[y + 1][x] is not None
                ):
                    portsPairs.append(("UserCLK", f"Tile_X{x}Y{y + 1}_UserCLKo"))
                else:
                    portsPairs.append(("UserCLK", f"Tile_X{x}Y{y}_UserCLK"))
                portsPairs.append(("UserCLKo", f"Tile_X{x}Y{y}_UserCLKo"))
            if config_bit_mode == ConfigBitMode.FRAME_BASED:
                # add connection for frameData, frameStrobe
                if (
                    0 <= x - 1 < len(superTile.tileMap[0])
                    and superTile.tileMap[y][x - 1] is not None
                ):
                    portsPairs.append(("FrameData", f"Tile_X{x - 1}Y{y}_FrameData_O"))
                else:
                    portsPairs.append(("FrameData", f"Tile_X{x}Y{y}_FrameData"))

                portsPairs.append(("FrameData_O", f"Tile_X{x}Y{y}_FrameData_O"))

                if (
                    0 <= y + 1 < len(superTile.tileMap)
                    and superTile.tileMap[y + 1][x] is not None
                ):
                    portsPairs.append(
                        ("FrameStrobe", f"Tile_X{x}Y{y + 1}_FrameStrobe_O")
                    )
                else:
                    portsPairs.append(("FrameStrobe", f"Tile_X{x}Y{y}_FrameStrobe"))

                portsPairs.append(("FrameStrobe_O", f"Tile_X{x}Y{y}_FrameStrobe_O"))

            emulateParamPairs = [
                ("Emulate_Bitstream", f"Tile_X{x}Y{y}_Emulate_Bitstream")
            ]

            writer.addInstantiation(
                compName=tile.name,
                compInsName=f"Tile_X{x}Y{y}_{tile.name}",
                portsPairs=portsPairs,
                emulateParamPairs=emulateParamPairs,
            )

    # Instantiate supertile ConfigMem (shares free slots in master tile's frame space)
    if st_config_bits > 0 and config_bit_mode == ConfigBitMode.FRAME_BASED:
        mx, my = superTile.get_master_tile_coords()
        if (
            0 <= mx - 1 < len(superTile.tileMap[0])
            and superTile.tileMap[my][mx - 1] is not None
        ):
            cm_frame_data = f"Tile_X{mx - 1}Y{my}_FrameData_O"
        else:
            cm_frame_data = f"Tile_X{mx}Y{my}_FrameData"
        if (
            0 <= my + 1 < len(superTile.tileMap)
            and superTile.tileMap[my + 1][mx] is not None
        ):
            cm_frame_strobe = f"Tile_X{mx}Y{my + 1}_FrameStrobe_O"
        else:
            cm_frame_strobe = f"Tile_X{mx}Y{my}_FrameStrobe"
        writer.addInstantiation(
            compName=f"{superTile.name}_ConfigMem",
            compInsName=f"Inst_{superTile.name}_ConfigMem",
            portsPairs=[
                ("FrameData", cm_frame_data),
                ("FrameStrobe", cm_frame_strobe),
                ("ConfigBits", f"ST_ConfigBits[{st_config_bits}-1:0]"),
                ("ConfigBits_N", f"ST_ConfigBits_N[{st_config_bits}-1:0]"),
            ],
            # The supertile config bits live in free slots of the master tile's
            # frame space, so in emulation they are preloaded from the master
            # tile's bitstream parameter (not its own frame shift register).
            emulateParamPairs=[
                ("Emulate_Bitstream", f"Tile_X{mx}Y{my}_Emulate_Bitstream")
            ],
        )

    # Instantiate supertile switch matrix (if a matrix file was found)
    if superTile.supertile_matrix_dir is not None:
        sm_ports_pairs = []
        # Connect SJUMP vector signals to SM scalar input ports
        for lx, ly, p in superTile.get_all_sjump_ports():
            tileName = superTile.tileMap[ly][lx].name
            for k in range(p.wireCount):
                sm_ports_pairs.append(
                    (f"{tileName}_{p.name}{k}", f"{tileName}_{p.name}[{k}]")
                )
        # SM outputs drive BEL input signals (signals named after the BEL ports)
        for bel in superTile.bels:
            for ip in bel.inputs:
                sm_ports_pairs.append((ip, ip))
        # BEL output signals feed back into the SM (routed to reverse SJUMP wires)
        for bel in superTile.bels:
            for op in bel.outputs:
                sm_ports_pairs.append((op, op))
        # SM outputs also drive reverse SJUMP signals into child tiles
        for _ly, row in enumerate(superTile.tileMap):
            for _lx, st_tile in enumerate(row):
                if st_tile is None:
                    continue
                for p in st_tile.get_sjump_ports():
                    if p.inOut == IO.INPUT:
                        tileName = st_tile.name
                        for k in range(p.wireCount):
                            sm_ports_pairs.append(
                                (f"{tileName}_{p.name}{k}", f"{tileName}_{p.name}[{k}]")
                            )
        if (
            superTile.supertile_matrix_config_bits > 0
            and config_bit_mode == ConfigBitMode.FRAME_BASED
        ):
            sm_ports_pairs.append(
                (
                    "ConfigBits",
                    f"ST_ConfigBits[{superTile.supertile_matrix_config_bits}-1:0]",
                )
            )
            sm_ports_pairs.append(
                (
                    "ConfigBits_N",
                    f"ST_ConfigBits_N[{superTile.supertile_matrix_config_bits}-1:0]",
                )
            )
        writer.addInstantiation(
            compName=f"{superTile.name}_switch_matrix",
            compInsName=f"Inst_{superTile.name}_switch_matrix",
            portsPairs=sm_ports_pairs,
        )

    # Instantiate supertile BELs
    st_bel_config_offset = superTile.supertile_matrix_config_bits
    for bel in superTile.bels:
        bel_ports_pairs = []
        # Bus the individual switch-matrix signals into the BEL's vector ports,
        # mirroring the normal-tile BEL instantiation (e.g. .A({A7,...,A0})). The
        # signals {prefix}{port}{i} are the supertile SM outputs / BEL inputs.
        port_dict: defaultdict[str, list[tuple[str, str]]] = defaultdict(list)
        for port_type, bel_ports in bel.ports_vectors.items():
            if port_type in ("external", "internal"):
                for port_name, info in bel_ports.items():
                    _direction, width = info
                    if width > 1:
                        port_dict[port_name] = [
                            (f"{bel.prefix}{port_name}{i}", f"{i}")
                            for i in range(width)
                        ]
                    else:
                        port_dict[port_name] = [
                            (f"{bel.prefix}{port_name}", f"{i}") for i in range(width)
                        ]
        for portname, ports in port_dict.items():
            if len(ports) > 1:
                ports.sort(key=lambda x: int(x[1]) if x[1].isdigit() else -1)
                concatenated = ", ".join(p for p, _ in ports[::-1])
                bel_ports_pairs.append((portname, f"{{{concatenated}}}"))
            else:
                bel_ports_pairs.append((portname, ports[0][0]))
        if not disable_user_clk and bel.withUserCLK:
            # The supertile wrapper has no bare "UserCLK"; the BEL shares the
            # master tile's clock net (same selection the master tile uses: the
            # chained UserCLKo from the tile below, or its own UserCLK input).
            mx, my = superTile.get_master_tile_coords()
            if (
                0 <= my + 1 < len(superTile.tileMap)
                and superTile.tileMap[my + 1][mx] is not None
            ):
                bel_user_clk = f"Tile_X{mx}Y{my + 1}_UserCLKo"
            else:
                bel_user_clk = f"Tile_X{mx}Y{my}_UserCLK"
            bel_ports_pairs.append(("UserCLK", bel_user_clk))
        if bel.configBit > 0 and config_bit_mode == ConfigBitMode.FRAME_BASED:
            bel_ports_pairs.append(
                (
                    "ConfigBits",
                    f"ST_ConfigBits["
                    f"{st_bel_config_offset + bel.configBit}-1:{st_bel_config_offset}]",
                )
            )
        st_bel_config_offset += bel.configBit
        writer.addInstantiation(
            compName=bel.name,
            compInsName=f"Inst_ST_{bel.prefix}{bel.name}",
            portsPairs=bel_ports_pairs,
        )

    writer.addDesignDescriptionEnd()
    writer.writeToFile()

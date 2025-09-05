"""Switch matrix generation module for FABulous FPGA tiles.

This module generates RTL code for configurable switch matrices within FPGA tiles.
Switch matrices handle the routing of signals between tile ports, BEL inputs/outputs,
and jump wires. The module supports various configuration modes and multiplexer styles.

Key features:
- CSV and list file parsing for switch matrix configurations
- Support for custom and generic multiplexer implementations
- Configuration bit calculation and management
- Debug signal generation for switch matrix analysis
- Multiple configuration modes (FlipFlop chain, Frame-based)
"""

import math

from loguru import logger

from FABulous.custom_exception import InvalidFileType
from FABulous.fabric_definition.define import (
    IO,
    ConfigBitMode,
    Direction,
    MultiplexerStyle,
)
from FABulous.fabric_definition.Fabric import Fabric
from FABulous.fabric_definition.Tile import Tile
from FABulous.fabric_generator.code_generator.code_generator import CodeGenerator
from FABulous.fabric_generator.code_generator.code_generator_VHDL import (
    VHDLCodeGenerator,
)
from FABulous.fabric_generator.gen_fabric.gen_helper import (
    bootstrapSwitchMatrix,
    list2CSV,
)
from FABulous.fabric_generator.parser.parse_switchmatrix import parseMatrix


def genTileSwitchMatrix(
    writer: CodeGenerator, fabric: Fabric, tile: Tile, switch_matrix_debug_signal: bool
) -> None:
    """Generate the RTL code for the tile switch matrix.

    The switch matrix generated will be based on the `matrixDir` attribute of the tile.
    If the given file format is `.csv`, it will be parsed as a switch matrix
    `.csv` file.
    If the given file format is `.list`, the tool will convert the `.list` file
    into a switch matrix with specific ordering first before progressing. If the given
    file format is Verilog or VHDL, then the function will not generate anything.

    Parameters
    ----------
    writer : CodeGenerator
        The code generator instance for RTL output
    fabric : Fabric
        The fabric object containing global configuration
    tile : Tile
        The tile object containing BELs and port information
    switch_matrix_debug_signal : bool
        Whether to generate debug signals for the switch matrix.

    Raises
    ------
    InvalidFileType
        If `matrixDir` does not contain a valid file format.
    ValueError
        If any port in the switch matrix is not connected to anything.
    """
    # convert the matrix to a dictionary map and performs entry check
    connections: dict[str, list[str]] = {}
    if tile.matrixDir.suffix == ".csv":
        connections = parseMatrix(tile.matrixDir, tile.name)
    elif tile.matrixDir.suffix == ".list":
        logger.info(f"{tile.name} matrix is a list file")
        logger.info(
            f"Bootstrapping {tile.name} to matrix form and adding the list file to the "
            "matrix"
        )
        matrixDir = tile.matrixDir.with_suffix(".csv")
        bootstrapSwitchMatrix(tile, matrixDir)
        list2CSV(tile.matrixDir, matrixDir)
        logger.info(
            f"Update matrix directory to {matrixDir} for Fabric Tile Dictionary"
        )
        tile.matrixDir = matrixDir
        connections = parseMatrix(tile.matrixDir, tile.name)
    elif tile.matrixDir.suffix == ".v" or tile.matrixDir.suffix == ".vhdl":
        logger.info(
            f"A switch matrix file is provided in {tile.name}, "
            "will skip the matrix generation process"
        )
        return
    else:
        raise InvalidFileType("Invalid matrix file format.")

    noConfigBits = 0
    for port_name in connections:
        if not connections[port_name]:
            raise ValueError(f"{port_name} not connected to anything!")
        mux_size = len(connections[port_name])
        if mux_size >= 2:
            noConfigBits += (mux_size - 1).bit_length()

    # we pass the NumberOfConfigBits as a comment in the beginning of the file.
    # This simplifies it to generate the configuration port only if needed later when
    # building the fabric where we are only working with the VHDL files

    # Generate header
    writer.addComment(f"NumberOfConfigBits: {noConfigBits}")
    writer.addHeader(f"{tile.name}_switch_matrix")
    if noConfigBits > 0:
        writer.addParameterStart(indentLevel=1)
        writer.addParameter("NoConfigBits", "integer", noConfigBits, indentLevel=2)
        writer.addParameterEnd(indentLevel=1)
    writer.addPortStart(indentLevel=1)

    # normal wire input
    for i in tile.portsInfo:
        if i.wireDirection != Direction.JUMP and i.inOut == IO.INPUT:
            for p in i.expandPortInfoByName():
                writer.addPortScalar(p, IO.INPUT, indentLevel=2)

    # bel wire input
    for b in tile.bels:
        for p in b.outputs:
            writer.addPortScalar(p, IO.INPUT, indentLevel=2)

    # jump wire input
    for i in tile.portsInfo:
        if i.wireDirection == Direction.JUMP and i.inOut == IO.INPUT:
            for p in i.expandPortInfoByName():
                writer.addPortScalar(p, IO.INPUT, indentLevel=2)

    # normal wire output
    for i in tile.portsInfo:
        if i.wireDirection != Direction.JUMP and i.inOut == IO.OUTPUT:
            for p in i.expandPortInfoByName():
                writer.addPortScalar(p, IO.OUTPUT, indentLevel=2)

    # bel wire output
    for b in tile.bels:
        for p in b.inputs:
            writer.addPortScalar(p, IO.OUTPUT, indentLevel=2)

    # jump wire output
    for i in tile.portsInfo:
        if i.wireDirection == Direction.JUMP and i.inOut == IO.OUTPUT:
            for p in i.expandPortInfoByName():
                writer.addPortScalar(p, IO.OUTPUT, indentLevel=2)

    writer.addComment("global", onNewLine=True)
    if noConfigBits > 0:
        if fabric.configBitMode == ConfigBitMode.FLIPFLOP_CHAIN:
            writer.addPortScalar("MODE", IO.INPUT, indentLevel=2)
            writer.addComment("global signal 1: configuration, 0: operation")
            writer.addPortScalar("CONFin", IO.INPUT, indentLevel=2)
            writer.addPortScalar("CONFout", IO.OUTPUT, indentLevel=2)
            writer.addPortScalar("CLK", IO.INPUT, indentLevel=2)
        if fabric.configBitMode == ConfigBitMode.FRAME_BASED:
            writer.addPortVector(
                "ConfigBits", IO.INPUT, "NoConfigBits-1", indentLevel=2
            )
            writer.addPortVector(
                "ConfigBits_N", IO.INPUT, "NoConfigBits-1", indentLevel=2
            )
    writer.addPortEnd()
    writer.addHeaderEnd(f"{tile.name}_switch_matrix")
    writer.addDesignDescriptionStart(f"{tile.name}_switch_matrix")

    # constant declaration
    # we may use the following in the switch matrix for providing
    # '0' and '1' to a mux input:
    if isinstance(writer, VHDLCodeGenerator):
        writer.addConstant("GND0", "0")
        writer.addConstant("GND", "0")
        writer.addConstant("VCC0", "1")
        writer.addConstant("VCC", "1")
        writer.addConstant("VDD0", "1")
        writer.addConstant("VDD", "1")
    else:
        writer.addConstant("GND0", "1'b0")
        writer.addConstant("GND", "1'b0")
        writer.addConstant("VCC0", "1'b1")
        writer.addConstant("VCC", "1'b1")
        writer.addConstant("VDD0", "1'b1")
        writer.addConstant("VDD", "1'b1")
    writer.addNewLine()

    # signal declaration
    for portName in connections:
        # ports with single connections are directly assigned
        if len(connections[portName]) > 1:
            writer.addConnectionVector(
                f"{portName}_input", f"{len(connections[portName])}-1"
            )

    ### SwitchMatrixDebugSignals ### SwitchMatrixDebugSignals ###
    ### SwitchMatrixDebugSignals ### SwitchMatrixDebugSignals ###
    if switch_matrix_debug_signal:
        writer.addNewLine()
        for portName in connections:
            muxSize = len(connections[portName])
            if muxSize >= 2:
                paddedMuxSize = 2 ** (muxSize - 1).bit_length() - 1
                writer.addConnectionVector(
                    f"DEBUG_select_{portName}",
                    f"{paddedMuxSize.bit_length() - 1}",
                )
    ### SwitchMatrixDebugSignals ### SwitchMatrixDebugSignals ###
    ### SwitchMatrixDebugSignals ### SwitchMatrixDebugSignals ###
    writer.addComment(
        "The configuration bits (if any) are just a long shift register",
        onNewLine=True,
    )
    writer.addComment(
        "This shift register is padded to an even number of flops/latches",
        onNewLine=True,
    )

    # we are only generate configuration bits, if we really need configurations bits
    # for example in terminating switch matrices at the fabric borders,
    # we may just change direction without any switching
    if noConfigBits > 0:
        if fabric.configBitMode == "ff_chain":
            writer.addConnectionVector("ConfigBits", noConfigBits)
        if fabric.configBitMode == "FlipFlopChain":
            # we pad to an even number of bits: (int(math.ceil(ConfigBitCounter/2.0))*2)
            writer.addConnectionVector(
                "ConfigBits", int(math.ceil(noConfigBits / 2.0)) * 2
            )
            writer.addConnectionVector(
                "ConfigBitsInput", int(math.ceil(noConfigBits / 2.0)) * 2
            )

    # begin architecture
    writer.addLogicStart()

    # the configuration bits shift register
    # again, we add this only if needed
    # TODO Should ff_chain be the same as FlipFlopChain?
    if noConfigBits > 0:
        if fabric.configBitMode == "ff_chain":
            writer.addShiftRegister(noConfigBits)
        elif fabric.configBitMode == ConfigBitMode.FLIPFLOP_CHAIN:
            writer.addFlipFlopChain(noConfigBits)
        elif fabric.configBitMode == ConfigBitMode.FRAME_BASED:
            pass

    # the switch matrix implementation
    # we use the following variable to count the configuration bits of a
    # long shift register which actually holds the switch matrix configuration
    configBitstreamPosition = 0
    for portName in connections:
        muxSize = len(connections[portName])
        writer.addComment(
            f"switch matrix multiplexer {portName} MUX-{muxSize}", onNewLine=True
        )
        if muxSize == 0:
            logger.warning(
                f"Input port {portName} of switch matrix in Tile {tile.name} is unused"
            )
            writer.addComment(
                f"WARNING unused multiplexer MUX-{portName}", onNewLine=True
            )

        elif muxSize == 1:
            # just route through : can be used for auxiliary wires or diagonal routing
            # (Manhattan, just go to a switch matrix when turning
            # can also be used to tap a wire.
            # A double with a mid is nothing else as a single cascaded with another
            # single where the second single has only one '1' to cascade
            # from the first single
            if connections[portName][0] == "0":
                writer.addAssignScalar(portName, 0)
            elif connections[portName][0] == "1":
                writer.addAssignScalar(portName, 1)
            else:
                writer.addAssignScalar(
                    portName,
                    connections[portName][0],
                    delay=fabric.generateDelayInSwitchMatrix,
                )
            writer.addNewLine()
        elif muxSize >= 2:
            # this is the case for a configurable switch matrix multiplexer
            old_ConfigBitstreamPosition = configBitstreamPosition

            # Pad mux size to the next power of 2
            paddedMuxSize = 2 ** (muxSize - 1).bit_length()

            if paddedMuxSize == 2:
                muxComponentName = f"cus_mux{paddedMuxSize}1"
            else:
                muxComponentName = f"cus_mux{paddedMuxSize}1_buf"

            portsPairs = []
            start = 0
            for start in range(muxSize):
                portsPairs.append((f"A{start}", f"{portName}_input[{start}]"))

            for end in range(start + 1, paddedMuxSize):
                portsPairs.append((f"A{end}", "GND0"))

            if fabric.multiplexerStyle == MultiplexerStyle.CUSTOM:
                if paddedMuxSize == 2:
                    portsPairs.append(("S", f"ConfigBits[{configBitstreamPosition}+0]"))
                else:
                    for i in range(paddedMuxSize.bit_length() - 1):
                        portsPairs.append(
                            (f"S{i}", f"ConfigBits[{configBitstreamPosition}+{i}]")
                        )
                        portsPairs.append(
                            (
                                f"S{i}N",
                                f"ConfigBits_N[{configBitstreamPosition}+{i}]",
                            )
                        )

            portsPairs.append(("X", f"{portName}"))

            if fabric.multiplexerStyle == MultiplexerStyle.CUSTOM:
                # we add the input signal in reversed order
                # Changed it such that the left-most entry is located at the end of the
                # concatenated vector for the multiplexing
                # This was done such that the index from left-to-right in the adjacency
                # matrix corresponds with the multiplexer select input (index)
                writer.addAssignScalar(
                    f"{portName}_input",
                    connections[portName][::-1],
                    delay=fabric.generateDelayInSwitchMatrix,
                )
                writer.addInstantiation(
                    compName=muxComponentName,
                    compInsName=f"inst_{muxComponentName}_{portName}",
                    portsPairs=portsPairs,
                )
                if muxSize != 2 and muxSize != 4 and muxSize != 8 and muxSize != 16:
                    logger.warning(
                        f"creating a MUX-{muxSize} for port {portName} using "
                        f"MUX-{muxSize} in switch matrix for tile {tile.name}"
                    )
            else:
                # generic multiplexer
                writer.addAssignScalar(
                    portName,
                    f"{portName}_input[ConfigBits[{configBitstreamPosition - 1}:"
                    f"{configBitstreamPosition}]]",
                )

            # update the configuration bitstream position
            configBitstreamPosition += paddedMuxSize.bit_length() - 1

    ### SwitchMatrixDebugSignals ### SwitchMatrixDebugSignals ###
    ### SwitchMatrixDebugSignals ### SwitchMatrixDebugSignals ###
    if switch_matrix_debug_signal:
        logger.info(f"Generate debug signals for switch matrix in tile {tile.name}")
        writer.addNewLine()
        configBitstreamPosition = 0
        old_ConfigBitstreamPosition = 0
        for portName in connections:
            muxSize = len(connections[portName])
            if muxSize >= 2:
                paddedMuxSize = 2 ** (muxSize - 1).bit_length()
                configBitstreamPosition += paddedMuxSize.bit_length() - 1
                writer.addAssignVector(
                    f"DEBUG_select_{portName:<15}",
                    "ConfigBits",
                    f"{configBitstreamPosition - 1}",
                    old_ConfigBitstreamPosition,
                )
                old_ConfigBitstreamPosition = configBitstreamPosition

    ### SwitchMatrixDebugSignals ### SwitchMatrixDebugSignals ###
    ### SwitchMatrixDebugSignals ### SwitchMatrixDebugSignals ###

    # just the final end of architecture
    writer.addDesignDescriptionEnd()
    writer.writeToFile()

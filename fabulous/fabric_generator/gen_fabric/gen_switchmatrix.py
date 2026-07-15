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

from fabulous.fabric_definition.define import (
    IO,
    SWITCH_MATRIX_CONSTANTS,
    ConfigBitMode,
    Direction,
    MultiplexerStyle,
)
from fabulous.fabric_definition.port import Port
from fabulous.fabric_definition.supertile import SuperTile
from fabulous.fabric_definition.tile import Tile
from fabulous.fabric_generator.code_generator.code_generator import CodeGenerator
from fabulous.fabric_generator.code_generator.code_generator_VHDL import (
    VHDLCodeGenerator,
)


def _unconnected_port_diagnostic(ports: list[Port], port_name: str) -> str:
    """Explain an unconnected switch matrix port caused by NULL-wire expansion.

    A NULL-terminated spanning wire expands to `wires x distance` nested
    wires (see `Port.expandPortInfoByName`). When the switch matrix leaves some
    of those nested wires unconnected, the bare wire name is unhelpful, so this
    traces the wire back to its originating port and explains the expansion.

    Parameters
    ----------
    ports : list[Port]
        The ports of the tile whose switch matrix is being generated.
    port_name : str
        The expanded wire name that has no connections.

    Returns
    -------
    str
        A diagnostic message to append to the base error, or an empty string
        when `port_name` is not a nested wire of a NULL-terminated spanning
        wire.
    """
    for port in ports:
        expanded = port.expandPortInfoByName()
        if port_name not in expanded:
            continue
        distance = abs(port.xOffset) + abs(port.yOffset)
        isNullTerminated = port.sourceName == "NULL" or port.destinationName == "NULL"
        if not (isNullTerminated and distance > 1):
            return ""
        return (
            f"\n  '{port_name}' is one of {len(expanded)} nested wires expanded "
            f"from wire spec '{port.name}' (wires={port.wireCount}, "
            f"distance={distance}). A NULL-terminated wire connects all nested "
            f"wires: wires x distance = {port.wireCount} x {distance} = "
            f"{len(expanded)} ({expanded[0]}..{expanded[-1]}). The switch matrix "
            f"connects fewer than {len(expanded)} of them. Either connect all "
            f"{len(expanded)} nested wires, or name both ends of the wire "
            f"(instead of NULL) for a direct {port.wireCount}-wire "
            "point-to-point bus."
        )
    return ""


def genTileSwitchMatrix(
    writer: CodeGenerator,
    tile: Tile,
    switch_matrix_debug_signal: bool,
    config_bit_mode: ConfigBitMode = ConfigBitMode.FRAME_BASED,
    multiplexer_style: MultiplexerStyle = MultiplexerStyle.CUSTOM,
    default_pip_delay: int = 80,
) -> None:
    """Generate the RTL code for the tile switch matrix.

    The switch matrix is read straight from the tile's already-canonical
    `tile.switch_matrix.connections` (built once when the fabric was parsed);
    no CSV is written or re-read here. A tile whose matrix is hand-written HDL
    is skipped - it supplies its own switch matrix module.

    Parameters
    ----------
    writer : CodeGenerator
        The code generator instance for RTL output
    tile : Tile
        The tile object containing BELs and port information
    switch_matrix_debug_signal : bool
        Whether to generate debug signals for the switch matrix.
    config_bit_mode : ConfigBitMode
        The configuration-bit mode for the tile (frame-based or flip-flop chain).
    multiplexer_style : MultiplexerStyle
        The multiplexer style used to implement switch-matrix muxes.
    default_pip_delay : int
        Per-mux delay (ps) emitted on assign statements in the switch matrix.

    Raises
    ------
    ValueError
        If any port in the switch matrix is not connected to anything.
    """
    if tile.switch_matrix.matrix_file.suffix in (".v", ".sv", ".vhdl", ".vhd"):
        logger.info(
            f"{tile.name} provides a hand-written switch matrix HDL; "
            "skipping matrix generation."
        )
        return

    # Unconnected outputs are checked here (not at parse) because tile ports are
    # only final after fabric assembly; the switch matrix connections are read
    # once but the port set backing the diagnostic changes.
    connections = tile.switch_matrix.connections
    for port_name in connections:
        if not connections[port_name]:
            hint = _unconnected_port_diagnostic(tile.portsInfo, port_name)
            raise ValueError(f"{port_name} not connected to anything!{hint}")
    noConfigBits = tile.switch_matrix.no_config_bits

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

    # normal wire input (excludes JUMP and SJUMP which are handled separately)
    for i in tile.portsInfo:
        if (
            i.wireDirection not in (Direction.JUMP, Direction.SJUMP)
            and i.inOut == IO.INPUT
        ):
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

    # normal wire output (excludes JUMP and SJUMP which are handled separately)
    for i in tile.portsInfo:
        if (
            i.wireDirection not in (Direction.JUMP, Direction.SJUMP)
            and i.inOut == IO.OUTPUT
        ):
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

    # sjump wire output - SM drives OUTPUT signals exiting to supertile SM
    for i in tile.portsInfo:
        if i.wireDirection == Direction.SJUMP and i.inOut == IO.OUTPUT:
            for p in i.expandPortInfoByName():
                writer.addPortScalar(p, IO.OUTPUT, indentLevel=2)

    # sjump wire input - SM receives INPUT signals arriving from supertile SM
    for i in tile.portsInfo:
        if i.wireDirection == Direction.SJUMP and i.inOut == IO.INPUT:
            for p in i.expandPortInfoByName():
                writer.addPortScalar(p, IO.INPUT, indentLevel=2)

    writer.addComment("global", onNewLine=True)
    if noConfigBits > 0:
        if config_bit_mode == ConfigBitMode.FLIPFLOP_CHAIN:
            writer.addPortScalar("MODE", IO.INPUT, indentLevel=2)
            writer.addComment("global signal 1: configuration, 0: operation")
            writer.addPortScalar("CONFin", IO.INPUT, indentLevel=2)
            writer.addPortScalar("CONFout", IO.OUTPUT, indentLevel=2)
            writer.addPortScalar("CLK", IO.INPUT, indentLevel=2)
        if config_bit_mode == ConfigBitMode.FRAME_BASED:
            writer.addPortVector(
                "ConfigBits", IO.INPUT, "NoConfigBits-1", indentLevel=2
            )
            writer.addPortVector(
                "ConfigBits_N", IO.INPUT, "NoConfigBits-1", indentLevel=2
            )
    writer.addPortEnd()
    writer.addHeaderEnd(f"{tile.name}_switch_matrix")
    writer.addDesignDescriptionStart(f"{tile.name}_switch_matrix")
    _gen_switch_matrix_body(
        writer,
        tile.name,
        connections,
        noConfigBits,
        config_bit_mode,
        multiplexer_style,
        default_pip_delay,
        switch_matrix_debug_signal,
    )


def _gen_switch_matrix_body(
    writer: CodeGenerator,
    name: str,
    connections: dict[str, list[str]],
    noConfigBits: int,
    config_bit_mode: ConfigBitMode,
    multiplexer_style: MultiplexerStyle,
    default_pip_delay: int,
    switch_matrix_debug_signal: bool,
) -> None:
    """Emit the body of a switch matrix module (constants, signals, mux logic).

    Called after the port list has been written. Handles constant declarations,
    signal declarations, mux instantiation, optional debug signals, and the
    closing `addDesignDescriptionEnd` / `writeToFile` calls.

    Parameters
    ----------
    writer : CodeGenerator
        Code generator instance for RTL output.
    name : str
        Module/tile name used in log messages.
    connections : dict[str, list[str]]
        Mapping from sink port name to list of source port names.
    noConfigBits : int
        Total number of configuration bits for this matrix.
    config_bit_mode : ConfigBitMode
        Frame-based or flip-flop chain configuration.
    multiplexer_style : MultiplexerStyle
        Custom or generic multiplexer implementation.
    default_pip_delay : int
        Per-mux delay (ps) emitted on assign statements.
    switch_matrix_debug_signal : bool
        Whether to generate debug signals.
    """
    # constant declaration - provides '0'/'1' as padding inputs to muxes
    vhdl = isinstance(writer, VHDLCodeGenerator)
    for const in SWITCH_MATRIX_CONSTANTS:
        if const.startswith("GND"):
            writer.addConstant(const, "0" if vhdl else "1'b0")
        else:
            writer.addConstant(const, "1" if vhdl else "1'b1")
    writer.addNewLine()

    # signal declaration - one input-concat vector per multi-input mux
    for portName in connections:
        if len(connections[portName]) > 1:
            writer.addConnectionVector(
                f"{portName}_input", f"{len(connections[portName])}-1"
            )

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
    writer.addComment(
        "The configuration bits (if any) are just a long shift register",
        onNewLine=True,
    )
    writer.addComment(
        "This shift register is padded to an even number of flops/latches",
        onNewLine=True,
    )

    if noConfigBits > 0:
        if config_bit_mode == "ff_chain":
            writer.addConnectionVector("ConfigBits", noConfigBits)
        if config_bit_mode == "FlipFlopChain":
            writer.addConnectionVector(
                "ConfigBits", int(math.ceil(noConfigBits / 2.0)) * 2
            )
            writer.addConnectionVector(
                "ConfigBitsInput", int(math.ceil(noConfigBits / 2.0)) * 2
            )

    writer.addLogicStart()

    # TODO Should ff_chain be the same as FlipFlopChain?
    if noConfigBits > 0:
        if config_bit_mode == "ff_chain":
            writer.addShiftRegister(noConfigBits)
        elif config_bit_mode == ConfigBitMode.FLIPFLOP_CHAIN:
            writer.addFlipFlopChain(noConfigBits)
        elif config_bit_mode == ConfigBitMode.FRAME_BASED:
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
                f"Input port {portName} of switch matrix in {name} is unused"
            )
            writer.addComment(
                f"WARNING unused multiplexer MUX-{portName}", onNewLine=True
            )
        elif muxSize == 1:
            if connections[portName][0] == "0":
                writer.addAssignScalar(portName, 0)
            elif connections[portName][0] == "1":
                writer.addAssignScalar(portName, 1)
            else:
                writer.addAssignScalar(
                    portName,
                    connections[portName][0],
                    delay=default_pip_delay,
                )
            writer.addNewLine()
        elif muxSize >= 2:
            paddedMuxSize = 2 ** (muxSize - 1).bit_length()
            muxComponentName = f"cus_mux{paddedMuxSize}1"

            portsPairs = []
            start = 0
            for start in range(muxSize):
                portsPairs.append((f"A{start}", f"{portName}_input[{start}]"))
            for end in range(start + 1, paddedMuxSize):
                portsPairs.append((f"A{end}", "GND0"))

            if multiplexer_style == MultiplexerStyle.CUSTOM:
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

            # Drive the mux input vector for both mux styles.
            writer.addAssignScalar(
                f"{portName}_input",
                connections[portName][::-1],
                delay=default_pip_delay,
            )

            if multiplexer_style == MultiplexerStyle.CUSTOM:
                writer.addInstantiation(
                    compName=muxComponentName,
                    compInsName=f"inst_{muxComponentName}_{portName}",
                    portsPairs=portsPairs,
                )
                if muxSize not in (2, 4, 8, 16):
                    logger.warning(
                        f"creating a MUX-{muxSize} for port {portName} using "
                        f"MUX-{muxSize} in switch matrix for {name}"
                    )
            else:
                # generic multiplexer: select the input behaviorally so it
                # synthesises to standard cells. The writer emits the indexing
                # in language-correct syntax for Verilog and VHDL.
                select_width = paddedMuxSize.bit_length() - 1
                writer.addMuxAssign(
                    portName,
                    f"{portName}_input",
                    "ConfigBits",
                    configBitstreamPosition,
                    select_width,
                    delay=default_pip_delay,
                )

            configBitstreamPosition += paddedMuxSize.bit_length() - 1

    if switch_matrix_debug_signal:
        logger.info(f"Generate debug signals for switch matrix in {name}")
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

    writer.addDesignDescriptionEnd()
    writer.writeToFile()


def gen_super_tile_switch_matrix(
    writer: CodeGenerator,
    superTile: SuperTile,
    config_bit_mode: ConfigBitMode = ConfigBitMode.FRAME_BASED,
    multiplexer_style: MultiplexerStyle = MultiplexerStyle.CUSTOM,
    default_pip_delay: int = 80,
) -> None:
    """Generate the switch matrix RTL for a supertile.

    The supertile switch matrix routes SJUMP output signals from child tiles to
    the input ports of supertile-level BELs. Its connectivity is described by
    `superTile.supertile_matrix_dir` (a `.list` or `.csv` file using the same
    format as tile switch matrices).

    Parameters
    ----------
    writer : CodeGenerator
        Code generator instance for RTL output.
    superTile : SuperTile
        The supertile whose BELs and SJUMP ports drive this matrix.
    config_bit_mode : ConfigBitMode
        Frame-based or flipflop-chain configuration.
    multiplexer_style : MultiplexerStyle
        Custom or generic multiplexer implementation.
    default_pip_delay : int
        Default PIP delay value for timing annotation.
    """
    if superTile.switch_matrix is None:
        return

    noConfigBits = superTile.switch_matrix.no_config_bits
    module_name = f"{superTile.name}_switch_matrix"

    # Connectivity (destination -> [sources]) held on the supertile.
    connections = superTile.switch_matrix.connections

    writer.addComment(f"NumberOfConfigBits: {noConfigBits}")
    writer.addHeader(module_name)
    if noConfigBits > 0:
        writer.addParameterStart(indentLevel=1)
        writer.addParameter("NoConfigBits", "integer", noConfigBits, indentLevel=2)
        writer.addParameterEnd(indentLevel=1)
    writer.addPortStart(indentLevel=1)

    # Inputs: SJUMP OUTPUT signals from each child tile ({tileName}_{portName}{i})
    all_sjump_ports = superTile.get_all_sjump_ports()
    if all_sjump_ports:
        writer.addComment("SJUMP inputs from child tiles", onNewLine=True)
        for lx, ly, p in all_sjump_ports:
            tileName = superTile.tileMap[ly][lx].name
            for k in range(p.wireCount):
                writer.addPortScalar(f"{tileName}_{p.name}{k}", IO.INPUT, indentLevel=2)

    # Outputs: input ports of supertile BELs (SM drives BEL inputs)
    if superTile.bels:
        writer.addComment("BEL input ports (SM outputs)", onNewLine=True)
    for bel in superTile.bels:
        for p in bel.inputs:
            writer.addPortScalar(p, IO.OUTPUT, indentLevel=2)

    # Inputs: output ports of supertile BELs (SM routes them back to child tiles)
    if any(bel.outputs for bel in superTile.bels):
        writer.addComment("BEL output ports (SM inputs)", onNewLine=True)
    for bel in superTile.bels:
        for p in bel.outputs:
            writer.addPortScalar(p, IO.INPUT, indentLevel=2)

    # Outputs: reverse SJUMP signals driven back into child tiles
    all_input_sjump = superTile.get_all_input_sjump_ports()
    if all_input_sjump:
        writer.addComment("Reverse SJUMP outputs (SM -> child tile)", onNewLine=True)
        for lx, ly, p in all_input_sjump:
            tileName = superTile.tileMap[ly][lx].name
            for k in range(p.wireCount):
                writer.addPortScalar(
                    f"{tileName}_{p.name}{k}", IO.OUTPUT, indentLevel=2
                )

    writer.addComment("global", onNewLine=True)
    if noConfigBits > 0:
        if config_bit_mode == ConfigBitMode.FLIPFLOP_CHAIN:
            writer.addPortScalar("MODE", IO.INPUT, indentLevel=2)
            writer.addPortScalar("CONFin", IO.INPUT, indentLevel=2)
            writer.addPortScalar("CONFout", IO.OUTPUT, indentLevel=2)
            writer.addPortScalar("CLK", IO.INPUT, indentLevel=2)
        if config_bit_mode == ConfigBitMode.FRAME_BASED:
            writer.addPortVector(
                "ConfigBits", IO.INPUT, "NoConfigBits-1", indentLevel=2
            )
            writer.addPortVector(
                "ConfigBits_N", IO.INPUT, "NoConfigBits-1", indentLevel=2
            )
    writer.addPortEnd()
    writer.addHeaderEnd(module_name)
    writer.addDesignDescriptionStart(module_name)
    _gen_switch_matrix_body(
        writer,
        superTile.name,
        connections,
        noConfigBits,
        config_bit_mode,
        multiplexer_style,
        default_pip_delay,
        switch_matrix_debug_signal=False,
    )

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
from pathlib import Path

from loguru import logger

from fabulous.fabric_definition.define import (
    IO,
    SWITCH_MATRIX_CONSTANTS,
    ConfigBitMode,
    Direction,
    MultiplexerStyle,
)
from fabulous.fabric_definition.port import TilePort
from fabulous.fabric_definition.switch_matrix import Mux
from fabulous.fabric_definition.tile import Tile
from fabulous.fabric_generator.code_generator.code_generator import CodeGenerator
from fabulous.fabric_generator.code_generator.code_generator_VHDL import (
    VHDLCodeGenerator,
)


def _unconnected_port_diagnostic(ports: list[TilePort], port_name: str) -> str:
    """Explain an unconnected switch matrix port caused by NULL-wire expansion.

    A NULL-terminated spanning wire expands to `wires x distance` nested
    wires (see `TilePort.expand_port_info_by_name`). When the switch matrix
    leaves some of those nested wires unconnected, the bare wire name is
    unhelpful, so this traces the wire back to its originating port and explains
    the expansion.

    Parameters
    ----------
    ports : list[TilePort]
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
        expanded = port.expand_port_info_by_name()
        if port_name not in expanded:
            continue
        distance = abs(port.x_offset) + abs(port.y_offset)
        isNullTerminated = port.source_name == "NULL" or port.destination_name == "NULL"
        if not (isNullTerminated and distance > 1):
            return ""
        return (
            f"\n  '{port_name}' is one of {len(expanded)} nested wires expanded "
            f"from wire spec '{port.name}' (wires={port.wire_count}, "
            f"distance={distance}). A NULL-terminated wire connects all nested "
            f"wires: wires x distance = {port.wire_count} x {distance} = "
            f"{len(expanded)} ({expanded[0]}..{expanded[-1]}). The switch matrix "
            f"connects fewer than {len(expanded)} of them. Either connect all "
            f"{len(expanded)} nested wires, or name both ends of the wire "
            f"(instead of NULL) for a direct {port.wire_count}-wire "
            "point-to-point bus."
        )
    return ""


def _add_leaf_matrix_ports(writer: CodeGenerator, tile: Tile) -> None:
    """Declare the switch-matrix ports for a leaf tile.

    The port order mirrors the historical leaf-tile switch matrix: routing
    inputs, BEL outputs (matrix inputs), JUMP inputs, then routing outputs, BEL
    inputs (matrix outputs) and JUMP outputs.

    Parameters
    ----------
    writer : CodeGenerator
        The code generator instance for RTL output.
    tile : Tile
        The leaf tile whose ports and BELs define the matrix interface.
    """
    # normal wire input (excludes JUMP, which is handled separately)
    for i in tile.ports_info:
        if i.wire_direction != Direction.JUMP and i.io_direction == IO.INPUT:
            for p in i.expand_port_info_by_name():
                writer.addPortScalar(p, IO.INPUT, indentLevel=2)

    # bel wire input
    for b in tile.bels:
        for p in b.outputs:
            writer.addPortScalar(p.name, IO.INPUT, indentLevel=2)

    # jump wire input
    for i in tile.ports_info:
        if i.wire_direction == Direction.JUMP and i.io_direction == IO.INPUT:
            for p in i.expand_port_info_by_name():
                writer.addPortScalar(p, IO.INPUT, indentLevel=2)

    # normal wire output (excludes JUMP, which is handled separately)
    for i in tile.ports_info:
        if i.wire_direction != Direction.JUMP and i.io_direction == IO.OUTPUT:
            for p in i.expand_port_info_by_name():
                writer.addPortScalar(p, IO.OUTPUT, indentLevel=2)

    # bel wire output
    for b in tile.bels:
        for p in b.inputs:
            writer.addPortScalar(p.name, IO.OUTPUT, indentLevel=2)

    # jump wire output
    for i in tile.ports_info:
        if i.wire_direction == Direction.JUMP and i.io_direction == IO.OUTPUT:
            for p in i.expand_port_info_by_name():
                writer.addPortScalar(p, IO.OUTPUT, indentLevel=2)


def _add_composite_matrix_ports(writer: CodeGenerator, muxes: list[Mux]) -> None:
    """Declare the wrapper switch-matrix ports for a composite tile.

    A composite tile's wrapper matrix has no ``ports_info`` of its own; its ports
    are the sub-tile-qualified connection names (e.g. ``DSP_bot_A0``) and wrapper
    BEL pin names that the matrix references. Each mux output (sink) becomes an
    OUTPUT port and each mux input (source), excluding switch-matrix constants,
    becomes an INPUT port.

    Parameters
    ----------
    writer : CodeGenerator
        The code generator instance for RTL output.
    muxes : list[Mux]
        The wrapper matrix muxes, one per sink, in canonical order.
    """
    # outputs: mux sinks, in connection order
    for mux in muxes:
        writer.addPortScalar(mux.output.name, IO.OUTPUT, indentLevel=2)

    # inputs: unique mux sources (excluding constants), in first-seen order
    seen: set[str] = set()
    for mux in muxes:
        for source in mux.inputs:
            if source.name in SWITCH_MATRIX_CONSTANTS or source.name in seen:
                continue
            seen.add(source.name)
            writer.addPortScalar(source.name, IO.INPUT, indentLevel=2)


def genTileSwitchMatrix(
    writer: CodeGenerator,
    tile: Tile,
    switch_matrix_debug_signal: bool,
    config_bit_mode: ConfigBitMode = ConfigBitMode.FRAME_BASED,
    multiplexer_style: MultiplexerStyle = MultiplexerStyle.CUSTOM,
    default_pip_delay: int = 80,
) -> None:
    """Generate the RTL code for the tile switch matrix.

    The matrix is taken from ``tile.switch_matrix``, which the loader has already
    parsed into muxes (and, for leaf `.list` tiles, canonicalised to CSV order).
    A Verilog or VHDL matrix source is emitted elsewhere, so nothing is generated
    for it here.

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
    # A pre-existing HDL matrix is emitted from its source, not generated here.
    if tile.switch_matrix.matrix_file.suffix in (".v", ".sv", ".vhdl", ".vhd"):
        logger.info(
            f"{tile.name} provides a hand-written switch matrix HDL; "
            "skipping matrix generation."
        )
        return
    # A composite without a MATRIX line has no wrapper matrix module to emit.
    if tile.is_composite and tile.matrix_dir == Path():
        return

    muxes = tile.switch_matrix.muxes

    # Unconnected outputs are checked here (not at parse) because tile ports are
    # only final after fabric assembly; the switch matrix muxes are read once but
    # the port set backing the diagnostic changes.
    for mux in muxes:
        if not mux.inputs:
            hint = _unconnected_port_diagnostic(tile.ports_info, mux.output.name)
            raise ValueError(f"{mux.output.name} not connected to anything!{hint}")

    noConfigBits = tile.switch_matrix.total_config_bits

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

    if tile.is_composite:
        _add_composite_matrix_ports(writer, muxes)
    else:
        _add_leaf_matrix_ports(writer, tile)

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
        muxes,
        noConfigBits,
        config_bit_mode,
        multiplexer_style,
        default_pip_delay,
        switch_matrix_debug_signal,
    )


def _gen_switch_matrix_body(
    writer: CodeGenerator,
    name: str,
    muxes: list[Mux],
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
    muxes : list[Mux]
        The switch-matrix muxes, one per sink, in canonical order.
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
    for mux in muxes:
        if len(mux.inputs) > 1:
            writer.addConnectionVector(
                f"{mux.output.name}_input", f"{len(mux.inputs)}-1"
            )

    ### SwitchMatrixDebugSignals ### SwitchMatrixDebugSignals ###
    if switch_matrix_debug_signal:
        writer.addNewLine()
        for mux in muxes:
            muxSize = len(mux.inputs)
            if muxSize >= 2:
                paddedMuxSize = 2 ** (muxSize - 1).bit_length() - 1
                writer.addConnectionVector(
                    f"DEBUG_select_{mux.output.name}",
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
    for mux in muxes:
        port_name = mux.output.name
        sources = [inp.name for inp in mux.inputs]
        muxSize = len(sources)
        writer.addComment(
            f"switch matrix multiplexer {port_name} MUX-{muxSize}", onNewLine=True
        )
        if muxSize == 0:
            logger.warning(
                f"Input port {port_name} of switch matrix in {name} is unused"
            )
            writer.addComment(
                f"WARNING unused multiplexer MUX-{port_name}", onNewLine=True
            )
        elif muxSize == 1:
            if sources[0] == "0":
                writer.addAssignScalar(port_name, 0)
            elif sources[0] == "1":
                writer.addAssignScalar(port_name, 1)
            else:
                writer.addAssignScalar(
                    port_name,
                    sources[0],
                    delay=default_pip_delay,
                )
            writer.addNewLine()
        elif muxSize >= 2:
            paddedMuxSize = 2 ** (muxSize - 1).bit_length()
            muxComponentName = f"cus_mux{paddedMuxSize}1"

            portsPairs = []
            start = 0
            for start in range(muxSize):
                portsPairs.append((f"A{start}", f"{port_name}_input[{start}]"))
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

            portsPairs.append(("X", f"{port_name}"))

            # Drive the mux input vector for both mux styles.
            writer.addAssignScalar(
                f"{port_name}_input",
                sources[::-1],
                delay=default_pip_delay,
            )

            if multiplexer_style == MultiplexerStyle.CUSTOM:
                writer.addInstantiation(
                    compName=muxComponentName,
                    compInsName=f"inst_{muxComponentName}_{port_name}",
                    portsPairs=portsPairs,
                )
                if muxSize not in (2, 4, 8, 16):
                    logger.warning(
                        f"creating a MUX-{muxSize} for port {port_name} using "
                        f"MUX-{muxSize} in switch matrix for {name}"
                    )
            else:
                # generic multiplexer: select the input behaviorally so it
                # synthesises to standard cells. The writer emits the indexing
                # in language-correct syntax for Verilog and VHDL.
                select_width = paddedMuxSize.bit_length() - 1
                writer.addMuxAssign(
                    port_name,
                    f"{port_name}_input",
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
        for mux in muxes:
            port_name = mux.output.name
            muxSize = len(mux.inputs)
            if muxSize >= 2:
                paddedMuxSize = 2 ** (muxSize - 1).bit_length()
                configBitstreamPosition += paddedMuxSize.bit_length() - 1
                writer.addAssignVector(
                    f"DEBUG_select_{port_name:<15}",
                    "ConfigBits",
                    f"{configBitstreamPosition - 1}",
                    old_ConfigBitstreamPosition,
                )
                old_ConfigBitstreamPosition = configBitstreamPosition
    ### SwitchMatrixDebugSignals ### SwitchMatrixDebugSignals ###

    writer.addDesignDescriptionEnd()
    writer.writeToFile()

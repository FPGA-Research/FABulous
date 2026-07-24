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

from fabulous.fabric_definition.define import IO, ConfigBitMode, Direction, Side
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

    Each switch matrix entity is build up is a specific order:
    1.a) interconnect wire INPUTS (in the order defined by the fabric file,)
    2.a) BEL primitive INPUTS (in the order the BEL-VHDLs are listed
         in the fabric CSV) within each BEL, the order from the entity is maintained
         Note that INPUTS refers to the view of the switch matrix!
         Which corresponds to BEL outputs at the actual BEL
    3.a) JUMP wire INPUTS (in the order defined by the fabric file)
    1.b) interconnect wire OUTPUTS
    2.b) BEL primitive OUTPUTS
         Again: OUTPUTS refers to the view of the switch matrix which corresponds to
                BEL inputs at the actual BEL
    3.b) JUMP wire OUTPUTS
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
    if tile.is_composite:
        _generate_composite_tile(
            writer,
            tile,
            frame_bits_per_row,
            max_frame_per_col,
            disable_user_clk,
            config_bit_mode,
        )
        return

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
    if tile.total_config_bits > 0:
        writer.addParameter(
            "NoConfigBits", "integer", tile.total_config_bits, indentLevel=2
        )

    writer.addParameterEnd(indentLevel=1)
    writer.addPortStart(indentLevel=1)

    # holder for each direction of port string
    portList = (
        tile.get_port_on_side(Side.NORTH)
        + tile.get_port_on_side(Side.EAST)
        + tile.get_port_on_side(Side.WEST)
        + tile.get_port_on_side(Side.SOUTH)
    )

    side_of_port = None
    for port in portList:
        if side_of_port is not port.side_of_tile:
            side_of_port = port.side_of_tile
            writer.addComment(str(side_of_port), onNewLine=True)
        # destination port are input to the tile
        # source port are output of the tile
        wireSize = (abs(port.x_offset) + abs(port.y_offset)) * port.wire_count - 1
        writer.addPortVector(port.name, port.io_direction, wireSize, indentLevel=2)
        writer.addComment(str(port), indentLevel=2, onNewLine=False)

    # now we have to scan all BELs if they use external pins,
    # because they have to be exported to the tile entity
    externalPorts = []
    for i in tile.bels:
        for p in i.external_input:
            writer.addPortScalar(p, IO.INPUT, indentLevel=2)
        for p in i.external_output:
            writer.addPortScalar(p, IO.OUTPUT, indentLevel=2)
        externalPorts += i.external_input
        externalPorts += i.external_output

    # if we found BELs with top-level IO ports, we just pass them through
    sharedExternalPorts = set()
    for i in tile.bels:
        sharedExternalPorts.update(i.shared_port)

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

        if tile.total_config_bits > 0:
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
            # ``BelPort.name`` already includes ``bel.prefix``; the dedup key and
            # the stored key must be identical for the check to ever fire.
            if i.name not in repeatDeclaration:
                writer.addConnectionScalar(i.name)
                repeatDeclaration.add(i.name)

    # Jump wires
    writer.addComment("Jump wires", onNewLine=True)
    for p in tile.ports_info:
        if p.wire_direction == Direction.JUMP:
            if (
                p.source_name != "NULL"
                and p.destination_name != "NULL"
                and p.io_direction == IO.OUTPUT
            ):
                writer.addConnectionVector(p.name, f"{p.wire_count}-1")

            for k in range(p.wire_count):
                allJumpWireList.append(f"{p.name}( {k} )")

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
    if tile.total_config_bits > 0:
        writer.addConnectionVector("ConfigBits", "NoConfigBits-1", 0)
        writer.addConnectionVector("ConfigBits_N", "NoConfigBits-1", 0)

    writer.addNewLine()
    writer.addComment("Connection for outgoing wires", onNewLine=True)
    writer.addConnectionVector("FrameData_i", "FrameBitsPerRow-1", 0)
    writer.addConnectionVector("FrameData_O_i", "FrameBitsPerRow-1", 0)
    writer.addConnectionVector("FrameStrobe_i", "MaxFramesPerCol-1", 0)
    writer.addConnectionVector("FrameStrobe_O_i", "MaxFramesPerCol-1", 0)

    added = set()
    for port in tile.ports_info:
        span = abs(port.x_offset) + abs(port.y_offset)
        if (port.source_name, port.destination_name) in added:
            continue
        if span >= 2 and port.source_name != "NULL" and port.destination_name != "NULL":
            highBoundIndex = span * port.wire_count - 1
            writer.addConnectionVector(f"{port.destination_name}_i", highBoundIndex)
            writer.addConnectionVector(
                f"{port.source_name}_i", highBoundIndex - port.wire_count
            )
            added.add((port.source_name, port.destination_name))

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
    for port in tile.ports_info:
        span = abs(port.x_offset) + abs(port.y_offset)
        if (port.source_name, port.destination_name) in added:
            continue
        if span >= 2 and port.source_name != "NULL" and port.destination_name != "NULL":
            highBoundIndex = span * port.wire_count - 1
            # using scalar assignment to connect the two vectors
            # could replace with assign as vector,
            # but will lose the - wire_count readability
            writer.addAssignScalar(
                f"{port.source_name}_i[{highBoundIndex}-{port.wire_count}:0]",
                f"{port.destination_name}_i[{highBoundIndex}:{port.wire_count}]",
            )
            writer.addNewLine()
            for i in range(highBoundIndex - port.wire_count + 1):
                writer.addInstantiation(
                    "my_buf",
                    f"{port.destination_name}_inbuf_{i}",
                    portsPairs=[
                        ("A", f"{port.destination_name}[{i + port.wire_count}]"),
                        ("X", f"{port.destination_name}_i[{i + port.wire_count}]"),
                    ],
                )
            for i in range(highBoundIndex - port.wire_count + 1):
                writer.addInstantiation(
                    "my_buf",
                    f"{port.source_name}_outbuf_{i}",
                    portsPairs=[
                        ("A", f"{port.source_name}_i[{i}]"),
                        ("X", f"{port.source_name}[{i}]"),
                    ],
                )

            added.add((port.source_name, port.destination_name))

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

    if config_bit_mode == ConfigBitMode.FRAME_BASED and tile.total_config_bits > 0:
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
        for port in bel.shared_port:
            if port.name == "UserCLK":
                if not disable_user_clk:
                    userclk_pair = (port.name, port.name)
            else:
                portsPairs.append((port.name, port.name))

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
            if bel.config_bit > 0:
                portsPairs.append(
                    (
                        "ConfigBits",
                        f"ConfigBits[{belConfigBitsCounter + bel.config_bit}-1:"
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
        belConfigBitsCounter += bel.config_bit

        # for the next BEL (if any) for cascading configuration chain
        # (this information is also needed for chaining the switch matrix)
        belCounter += 1

    portsPairs = []
    # normal input wire (excludes JUMP, which is handled separately)
    for i in tile.ports_info:
        if i.wire_direction != Direction.JUMP and i.io_direction == IO.INPUT:
            portsPairs += list(
                zip(
                    i.expand_port_info_by_name(),
                    i.expand_port_info_by_name(indexed=True),
                    strict=False,
                )
            )
    # bel input wire (bel output is input to switch matrix)
    for bel in tile.bels:
        for p in bel.outputs:
            portsPairs.append((p.name, p.name))

    # jump input wire
    port, signal = [], []
    for i in tile.ports_info:
        if i.wire_direction == Direction.JUMP and i.io_direction == IO.INPUT:
            port += i.expand_port_info_by_name()
        if i.wire_direction == Direction.JUMP and i.io_direction == IO.OUTPUT:
            signal += i.expand_port_info_by_name(indexed=True)

    portsPairs += list(zip(port, signal, strict=False))

    # normal output wire (excludes JUMP, which is handled separately)
    for i in tile.ports_info:
        if i.wire_direction != Direction.JUMP and i.io_direction == IO.OUTPUT:
            portsPairs += list(
                zip(
                    i.expand_port_info_by_name(),
                    i.expand_port_info_by_name_top(indexed=True),
                    strict=False,
                )
            )

    # bel output wire (bel input is input to switch matrix)
    for bel in tile.bels:
        for p in bel.inputs:
            portsPairs.append((p.name, p.name))

    # jump output wire
    port, signal = [], []
    for i in tile.ports_info:
        if i.wire_direction == Direction.JUMP and i.io_direction == IO.OUTPUT:
            port += i.expand_port_info_by_name()
        if i.wire_direction == Direction.JUMP and i.io_direction == IO.OUTPUT:
            signal += i.expand_port_info_by_name(indexed=True)

    portsPairs += list(zip(port, signal, strict=True))

    if config_bit_mode == ConfigBitMode.FLIPFLOP_CHAIN:
        portsPairs.append(("MODE", "Mode"))
        portsPairs.append(("CONFin", f"conf_data({belCounter})"))
        portsPairs.append(("CONFout", f"conf_data({belCounter + 1})"))
        portsPairs.append(("CLK", "CLK"))

    if config_bit_mode == ConfigBitMode.FRAME_BASED and tile.total_config_bits > 0:
        portsPairs.append(
            (
                "ConfigBits",
                f"ConfigBits[{tile.total_config_bits}-1:{belConfigBitsCounter}]",
            )
        )
        portsPairs.append(
            (
                "ConfigBits_N",
                f"ConfigBits_N[{tile.total_config_bits}-1:{belConfigBitsCounter}]",
            )
        )

    writer.addInstantiation(
        compName=f"{tile.name}_switch_matrix",
        compInsName=f"Inst_{tile.name}_switch_matrix",
        portsPairs=portsPairs,
    )

    writer.addDesignDescriptionEnd()
    writer.writeToFile()


def _composite_ports_around(tile: Tile) -> dict[str, list[list]]:
    """Return the perimeter side ports of each composite sub-tile cell.

    Mirrors the pre-migration supertile perimeter wiring so the composite
    wrapper exposes exactly the same perimeter ports (and in the same
    order) as the pre-migration supertile generator. The dictionary key is the
    ``"x,y"`` cell coordinate using the same row/column indexing as
    ``tile.tile_map``; a side-port list is appended only when that side faces the
    composite boundary.

    Parameters
    ----------
    tile : Tile
        The composite tile whose ``tile_map`` cells are scanned.

    Returns
    -------
    dict[str, list[list]]
        Mapping from cell coordinate to its perimeter side-port lists.
    """
    tile_map = tile.tile_map
    ports: dict[str, list[list]] = {}
    for y, row in enumerate(tile_map):
        for x, sub in enumerate(row):
            if sub is None:
                continue
            ports[f"{x},{y}"] = []
            # Top-first storage: y-1 is physically north, y+1 is south (matches
            # gen_fabric ``_composite_perimeter_by_offset`` and the connection side).
            if y - 1 < 0 or tile_map[y - 1][x] is None:
                ports[f"{x},{y}"].append(sub.get_port_on_side(Side.NORTH))
            if x + 1 >= len(tile_map[y]) or tile_map[y][x + 1] is None:
                ports[f"{x},{y}"].append(sub.get_port_on_side(Side.EAST))
            if y + 1 >= len(tile_map) or tile_map[y + 1][x] is None:
                ports[f"{x},{y}"].append(sub.get_port_on_side(Side.SOUTH))
            if x - 1 < 0 or tile_map[y][x - 1] is None:
                ports[f"{x},{y}"].append(sub.get_port_on_side(Side.WEST))
    return ports


def _composite_internal_connections(tile: Tile) -> list[tuple[list, int, int]]:
    """Return the internal edge side ports between adjacent composite cells.

    Mirrors the pre-migration supertile internal wiring so the composite
    wrapper declares exactly the same internal connection signals (and
    in the same order) as the pre-migration supertile generator.

    Parameters
    ----------
    tile : Tile
        The composite tile whose ``tile_map`` cells are scanned.

    Returns
    -------
    list[tuple[list, int, int]]
        One entry per internal edge as ``(side_ports, x, y)``.
    """
    tile_map = tile.tile_map
    internal: list[tuple[list, int, int]] = []
    for y, row in enumerate(tile_map):
        for x, _sub in enumerate(row):
            # Top-first storage: y-1 is physically north, y+1 is south. Kept
            # complementary with ``_composite_ports_around`` so each side is either
            # a perimeter port or an internal wire, never both.
            if 0 <= y - 1 < len(tile_map) and tile_map[y - 1][x] is not None:
                internal.append((row[x].get_port_on_side(Side.NORTH), x, y))
            if 0 <= x + 1 < len(tile_map[0]) and tile_map[y][x + 1] is not None:
                internal.append((row[x].get_port_on_side(Side.EAST), x, y))
            if 0 <= y + 1 < len(tile_map) and tile_map[y + 1][x] is not None:
                internal.append((row[x].get_port_on_side(Side.SOUTH), x, y))
            if 0 <= x - 1 < len(tile_map[0]) and tile_map[y][x - 1] is not None:
                internal.append((row[x].get_port_on_side(Side.WEST), x, y))
    return internal


def _composite_wrapper_matrix_signals(
    tile: Tile,
) -> list[tuple[str, str, int, list[int]]]:
    """Return the sub-tile ports the composite wrapper matrix binds to.

    The composite wrapper switch matrix references its sub-tile instance ports by
    sub-tile-qualified name (``{subtile}_{port}{k}``). For each such ``(subtile,
    port)`` pair an intermediate signal is declared and bound to both the
    sub-tile instance port and the wrapper-matrix instance port. This scans the
    wrapper matrix (``tile.switch_matrix``) and reports every sub-tile port it
    references, along with the exact bit indices referenced.

    Only the referenced bits are reported because the wrapper switch matrix module
    (see ``_add_composite_matrix_ports``) declares a scalar port only for the
    referenced ``{subtile}_{port}{k}`` names, not for every bit ``0..wire_count-1``.

    Parameters
    ----------
    tile : Tile
        The composite tile whose ``switch_matrix`` references sub-tile ports.

    Returns
    -------
    list[tuple[str, str, int, list[int]]]
        One entry per referenced sub-tile port as ``(subtile_name, port_name,
        wire_count, referenced_bits)``, in deterministic sub-tile then port order.
        ``referenced_bits`` is the ascending list of bit indices the wrapper
        matrix actually references.
    """
    referenced: set[str] = set()
    for mux in tile.switch_matrix.muxes:
        referenced.add(mux.output.name)
        for inp in mux.inputs:
            referenced.add(inp.name)

    result: list[tuple[str, str, int, list[int]]] = []
    for sub_tile in tile.get_sub_tiles():
        for port in sub_tile.ports_info:
            if port.name == "NULL":
                continue
            referenced_bits = [
                k
                for k in range(port.wire_count)
                if f"{sub_tile.name}_{port.name}{k}" in referenced
            ]
            if referenced_bits:
                result.append(
                    (sub_tile.name, port.name, port.wire_count, referenced_bits)
                )
    return result


def _generate_composite_tile(
    writer: CodeGenerator,
    tile: Tile,
    frame_bits_per_row: int = 32,
    max_frame_per_col: int = 20,
    disable_user_clk: bool = False,
    config_bit_mode: ConfigBitMode = ConfigBitMode.FRAME_BASED,
) -> None:
    """Generate the wrapper module for a composite tile.

    A composite tile (former supertile) is emitted as a single module that
    instantiates each sub-tile, wires the internal sub-tile-to-sub-tile
    connections, exposes the perimeter ports, and instantiates the wrapper switch
    matrix, wrapper config memory and wrapper BELs at the master cell. The
    wrapper matrix binds to sub-tile instance ports directly via intermediate
    signals (the sub-tiles expose no special wrapper-only module ports).

    Parameters
    ----------
    writer : CodeGenerator
        The code generator instance for RTL output.
    tile : Tile
        The composite tile object (``tile.is_composite`` is ``True``).
    frame_bits_per_row : int
        Number of configuration bits per row for frame-based configuration.
    max_frame_per_col : int
        Maximum number of frames per column for frame-based configuration.
    disable_user_clk : bool
        If True, the UserCLK port will not be generated or connected.
    config_bit_mode : ConfigBitMode
        The configuration bit mode to use (frame-based or FlipFlop chain).

    Raises
    ------
    FileNotFoundError
        If the composite tile's switch matrix or ConfigMem HDL file is expected
        (per the instantiation conditions) but missing; run matrix / config_mem
        generation first.
    """
    tile_map = tile.tile_map
    sub_tiles = tile.get_sub_tiles()
    wrapper_signals = _composite_wrapper_matrix_signals(tile)

    writer.addHeader(f"{tile.name}")
    writer.addParameterStart(indentLevel=1)
    if isinstance(writer, VerilogCodeGenerator):
        writer.addPreprocIfDef("EMULATION")
        maxBits = frame_bits_per_row * max_frame_per_col
        for y, row in enumerate(tile_map):
            for x, sub in enumerate(row):
                if not sub:
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

    portsAround = _composite_ports_around(tile)

    for k, v in portsAround.items():
        if not v:
            continue
        x, y = k.split(",")
        for pList in v:
            # Skip empty port lists
            if not pList:
                continue

            writer.addComment(
                f"Tile_X{x}Y{y}_{pList[0].wire_direction}",
                onNewLine=True,
                indentLevel=1,
            )
            for p in pList:
                wire = (abs(p.x_offset) + abs(p.y_offset)) * p.wire_count - 1
                writer.addPortVector(
                    f"Tile_X{x}Y{y}_{p.name}", p.io_direction, wire, indentLevel=2
                )
                writer.addComment(str(p), onNewLine=False)

    # add tile external bel port
    writer.addComment("Tile IO ports from BELs", onNewLine=True, indentLevel=1)
    for i in sub_tiles:
        for b in i.bels:
            for p in b.external_input:
                writer.addPortScalar(p, IO.INPUT, indentLevel=2)
            for p in b.external_output:
                writer.addPortScalar(p, IO.OUTPUT, indentLevel=2)
            for p in b.shared_port:
                if p.name == "UserCLK":
                    continue
                writer.addPortScalar(p.name, p.io_direction, indentLevel=2)

    # add wrapper-level BEL external ports
    if tile.bels:
        writer.addComment("Wrapper BEL IO ports", onNewLine=True, indentLevel=1)
        for b in tile.bels:
            for p in b.external_input:
                writer.addPortScalar(p, IO.INPUT, indentLevel=2)
            for p in b.external_output:
                writer.addPortScalar(p, IO.OUTPUT, indentLevel=2)

    st_config_bits = tile.total_config_bits

    # add config port
    if config_bit_mode == ConfigBitMode.FRAME_BASED:
        for y, row in enumerate(tile_map):
            for x, _sub in enumerate(row):
                # Top-first storage: FrameStrobe_O exits north (the top cell), so
                # expose it when there is no tile to the north (y-1).
                if y - 1 < 0 or tile_map[y - 1][x] is None:
                    writer.addPortVector(
                        f"Tile_X{x}Y{y}_FrameStrobe_O",
                        IO.OUTPUT,
                        "MaxFramesPerCol-1",
                        indentLevel=2,
                    )
                    writer.addComment("CONFIG_PORT", onNewLine=False)
                if x - 1 < 0 or tile_map[y][x - 1] is None:
                    writer.addPortVector(
                        f"Tile_X{x}Y{y}_FrameData",
                        IO.INPUT,
                        "FrameBitsPerRow-1",
                        indentLevel=2,
                    )
                    writer.addComment("CONFIG_PORT", onNewLine=False)
                # Top-first storage: FrameStrobe enters from the south (the bottom
                # cell), so expose it when there is no tile to the south (y+1).
                if y + 1 >= len(tile_map) or tile_map[y + 1][x] is None:
                    writer.addPortVector(
                        f"Tile_X{x}Y{y}_FrameStrobe",
                        IO.INPUT,
                        "MaxFramesPerCol-1",
                        indentLevel=2,
                    )
                    writer.addComment("CONFIG_PORT", onNewLine=False)
                if x + 1 >= len(tile_map[y]) or tile_map[y][x + 1] is None:
                    writer.addPortVector(
                        f"Tile_X{x}Y{y}_FrameData_O",
                        IO.OUTPUT,
                        "FrameBitsPerRow-1",
                        indentLevel=2,
                    )
                    writer.addComment("CONFIG_PORT", onNewLine=False)
    if not disable_user_clk:
        for y, row in enumerate(tile_map):
            for x, _sub in enumerate(row):
                # Top-first storage: UserCLK enters from the north (the top cell)
                # and UserCLKo exits to the south (the bottom cell), so expose
                # UserCLK when no tile is to the north (y-1) and UserCLKo when no
                # tile is to the south (y+1).
                if y + 1 >= len(tile_map) or tile_map[y + 1][x] is None:
                    writer.addPortScalar(
                        f"Tile_X{x}Y{y}_UserCLKo", IO.OUTPUT, indentLevel=2
                    )
                if y - 1 < 0 or tile_map[y - 1][x] is None:
                    writer.addPortScalar(
                        f"Tile_X{x}Y{y}_UserCLK", IO.INPUT, indentLevel=2
                    )
    writer.addPortEnd()
    writer.addHeaderEnd(f"{tile.name}")
    writer.addDesignDescriptionStart(f"{tile.name}")
    writer.addNewLine()

    if isinstance(writer, VHDLCodeGenerator):
        basePath = Path(writer.outFileName).parent
        for t in sub_tiles:
            # This is only relevant to VHDL code generation,
            # will not affect Verilog code generation
            writer.addComponentDeclarationForFile(f"{basePath}/{t.name}/{t.name}.vhdl")
        # The wrapper instantiates the composite-level BELs directly, so declare
        # each BEL's component once (mirroring generateTile).
        bel_srcs_seen: list = []
        for bel in tile.bels:
            if bel.src not in bel_srcs_seen:
                bel_srcs_seen.append(bel.src)
                writer.addComponentDeclarationForFile(bel.src)
        # The wrapper also instantiates its own switch matrix and ConfigMem
        # (see below), so VHDL needs their component declarations too - mirroring
        # generateTile. Guarded by the same conditions as those instantiations.
        if tile.matrix_dir != Path():
            sm_file = basePath / f"{tile.name}_switch_matrix.vhdl"
            if not sm_file.exists():
                raise FileNotFoundError(
                    f"Could not find {sm_file.name} in {basePath}. "
                    "Need to run matrix generation first"
                )
            writer.addComponentDeclarationForFile(str(sm_file))
        if st_config_bits > 0 and config_bit_mode == ConfigBitMode.FRAME_BASED:
            cm_file = basePath / f"{tile.name}_ConfigMem.vhdl"
            if not cm_file.exists():
                raise FileNotFoundError(
                    f"Could not find {cm_file.name} in {basePath}. "
                    "Need to run config_mem generation first"
                )
            writer.addComponentDeclarationForFile(str(cm_file))

    # find all internal connections
    internal_connections = _composite_internal_connections(tile)

    # declare internal connections
    writer.addComment("signal declarations", onNewLine=True)

    # Wrapper-matrix intermediate signals: one vector per (sub-tile, port) pair
    # the wrapper switch matrix references. Each signal binds the sub-tile
    # instance port to the wrapper-matrix instance port of the same name.
    if wrapper_signals:
        writer.addComment(
            "wrapper matrix signals (sub-tile <-> wrapper SM)", onNewLine=True
        )
        for sub_name, port_name, wire_count, _referenced_bits in wrapper_signals:
            writer.addConnectionVector(
                f"{sub_name}_{port_name}", f"{wire_count}-1", indentLevel=1
            )

    # BEL pin signals bridging the wrapper BELs and the switch matrix
    bel_pin_signals = [pin for bel in tile.bels for pin in (*bel.inputs, *bel.outputs)]
    if bel_pin_signals:
        writer.addComment("BEL pin signals (BEL <-> wrapper SM)", onNewLine=True)
        for pin in bel_pin_signals:
            writer.addConnectionScalar(pin.name, indentLevel=1)

    for i, x, y in internal_connections:
        if i:
            writer.addComment(f"Tile_X{x}Y{y}_{i[0].wire_direction}", onNewLine=True)
            for p in i:
                if p.io_direction == IO.OUTPUT:
                    wire = (abs(p.x_offset) + abs(p.y_offset)) * p.wire_count - 1
                    writer.addConnectionVector(
                        f"Tile_X{x}Y{y}_{p.name}", wire, indentLevel=1
                    )
                    writer.addComment(str(p), onNewLine=False)

    # declare internal connections for frameData, frameStrobe, and UserCLK
    for y, row in enumerate(tile_map):
        for x, _sub in enumerate(row):
            # Top-first storage: FrameStrobe_O is internal when a tile is to the
            # north (y-1) to receive it (complementary with the FrameStrobe_O port).
            if 0 <= y - 1 < len(tile_map) and tile_map[y - 1][x] is not None:
                writer.addConnectionVector(
                    f"Tile_X{x}Y{y}_FrameStrobe_O",
                    "MaxFramesPerCol-1",
                    indentLevel=1,
                )
            # Top-first storage: UserCLKo is internal only when there's a tile to
            # the south (y+1) to receive it, and the user clock is enabled.
            if (
                not disable_user_clk
                and 0 <= y + 1 < len(tile_map)
                and tile_map[y + 1][x] is not None
            ):
                writer.addConnectionScalar(f"Tile_X{x}Y{y}_UserCLKo", indentLevel=1)
            if 0 <= x - 1 < len(tile_map[y]) and tile_map[y][x - 1] is not None:
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

    # sub-tile ports the wrapper matrix references, grouped by sub-tile name.
    wrapper_ports_by_sub: dict[str, list[str]] = defaultdict(list)
    for sub_name, port_name, _wire_count, _referenced_bits in wrapper_signals:
        wrapper_ports_by_sub[sub_name].append(port_name)

    # pair up the connection for tile instantiation
    for y, row in enumerate(tile_map):
        for x, sub in enumerate(row):
            northInput, southInput, eastInput, westInput = [], [], [], []
            portsPairs = []
            if sub is None:
                continue

            # north direction input connection
            northPort = [i.name for i in sub.get_port_on_side(Side.SOUTH, IO.INPUT)]
            # Top-first storage: north input comes from the north tile (y-1)
            if 0 <= y - 1 < len(tile_map) and tile_map[y - 1][x] is not None:
                for p in tile_map[y - 1][x].get_port_on_side(Side.NORTH, IO.OUTPUT):
                    northInput.append(f"Tile_X{x}Y{y - 1}_{p.name}")
            else:
                for p in sub.get_port_on_side(Side.SOUTH, IO.INPUT):
                    northInput.append(f"Tile_X{x}Y{y}_{p.name}")

            portsPairs += list(zip(northPort, northInput, strict=False))
            # east direction input connection
            eastPort = [i.name for i in sub.get_port_on_side(Side.WEST, IO.INPUT)]
            if 0 <= x - 1 < len(tile_map[0]) and tile_map[y][x - 1] is not None:
                for p in tile_map[y][x - 1].get_port_on_side(Side.EAST, IO.OUTPUT):
                    eastInput.append(f"Tile_X{x - 1}Y{y}_{p.name}")
            else:
                for p in sub.get_port_on_side(Side.WEST, IO.INPUT):
                    eastInput.append(f"Tile_X{x}Y{y}_{p.name}")

            portsPairs += list(zip(eastPort, eastInput, strict=False))

            # south direction input connection
            southPort = [
                i.name
                for i in sub.get_port_on_side(Side.NORTH, IO.INPUT)
                if i.io_direction == IO.INPUT
            ]
            # Top-first storage: south input comes from the south tile (y+1)
            if 0 <= y + 1 < len(tile_map) and tile_map[y + 1][x] is not None:
                for p in tile_map[y + 1][x].get_port_on_side(Side.SOUTH, IO.OUTPUT):
                    southInput.append(f"Tile_X{x}Y{y + 1}_{p.name}")
            else:
                for p in sub.get_port_on_side(Side.NORTH, IO.INPUT):
                    southInput.append(f"Tile_X{x}Y{y}_{p.name}")

            portsPairs += list(zip(southPort, southInput, strict=False))

            # west direction input connection
            westPort = [
                i.name
                for i in sub.get_port_on_side(Side.EAST, IO.INPUT)
                if i.io_direction == IO.INPUT
            ]
            if 0 <= x + 1 < len(tile_map[0]) and tile_map[y][x + 1] is not None:
                for p in tile_map[y][x + 1].get_port_on_side(Side.WEST, IO.OUTPUT):
                    westInput.append(f"Tile_X{x + 1}Y{y}_{p.name}")
            else:
                for p in sub.get_port_on_side(Side.EAST, IO.INPUT):
                    westInput.append(f"Tile_X{x}Y{y}_{p.name}")

            portsPairs += list(zip(westPort, westInput, strict=False))

            for p in (
                sub.get_port_on_side(Side.NORTH, IO.OUTPUT)
                + sub.get_port_on_side(Side.EAST, IO.OUTPUT)
                + sub.get_port_on_side(Side.SOUTH, IO.OUTPUT)
                + sub.get_port_on_side(Side.WEST, IO.OUTPUT)
            ):
                portsPairs.append((p.name, f"Tile_X{x}Y{y}_{p.name}"))

            for b in sub.bels:
                for p in b.external_input:
                    portsPairs.append((p, p))

                for p in b.external_output:
                    portsPairs.append((p, p))

                if not disable_user_clk:
                    for p in b.shared_port:
                        if "UserCLK" not in p.name:
                            portsPairs.append(("UserCLK", p.name))

            # connect the sub-tile ports the wrapper matrix references to their
            # intermediate signals (the wrapper SM binds to the same signals).
            for port_name in wrapper_ports_by_sub.get(sub.name, []):
                portsPairs.append((port_name, f"{sub.name}_{port_name}"))

            # add clock to tile
            if not disable_user_clk:
                # Top-first storage: UserCLK is chained from the north tile (y-1).
                if 0 <= y - 1 < len(tile_map) and tile_map[y - 1][x] is not None:
                    portsPairs.append(("UserCLK", f"Tile_X{x}Y{y - 1}_UserCLKo"))
                else:
                    portsPairs.append(("UserCLK", f"Tile_X{x}Y{y}_UserCLK"))
                portsPairs.append(("UserCLKo", f"Tile_X{x}Y{y}_UserCLKo"))
            if config_bit_mode == ConfigBitMode.FRAME_BASED:
                # add connection for frameData, frameStrobe
                if 0 <= x - 1 < len(tile_map[0]) and tile_map[y][x - 1] is not None:
                    portsPairs.append(("FrameData", f"Tile_X{x - 1}Y{y}_FrameData_O"))
                else:
                    portsPairs.append(("FrameData", f"Tile_X{x}Y{y}_FrameData"))

                portsPairs.append(("FrameData_O", f"Tile_X{x}Y{y}_FrameData_O"))

                # Top-first storage: FrameStrobe is chained from the south tile (y+1)
                if 0 <= y + 1 < len(tile_map) and tile_map[y + 1][x] is not None:
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
                compName=sub.name,
                compInsName=f"Tile_X{x}Y{y}_{sub.name}",
                portsPairs=portsPairs,
                emulateParamPairs=emulateParamPairs,
            )

    # Instantiate wrapper ConfigMem (shares free slots in master cell's frame space)
    mx, my = tile.get_master_offset()
    if st_config_bits > 0 and config_bit_mode == ConfigBitMode.FRAME_BASED:
        if 0 <= mx - 1 < len(tile_map[0]) and tile_map[my][mx - 1] is not None:
            cm_frame_data = f"Tile_X{mx - 1}Y{my}_FrameData_O"
        else:
            cm_frame_data = f"Tile_X{mx}Y{my}_FrameData"
        if 0 <= my + 1 < len(tile_map) and tile_map[my + 1][mx] is not None:
            cm_frame_strobe = f"Tile_X{mx}Y{my + 1}_FrameStrobe_O"
        else:
            cm_frame_strobe = f"Tile_X{mx}Y{my}_FrameStrobe"
        writer.addInstantiation(
            compName=f"{tile.name}_ConfigMem",
            compInsName=f"Inst_{tile.name}_ConfigMem",
            portsPairs=[
                ("FrameData", cm_frame_data),
                ("FrameStrobe", cm_frame_strobe),
                ("ConfigBits", f"ST_ConfigBits[{st_config_bits}-1:0]"),
                ("ConfigBits_N", f"ST_ConfigBits_N[{st_config_bits}-1:0]"),
            ],
            # The wrapper config bits live in free slots of the master cell's
            # frame space, so in emulation they are preloaded from the master
            # cell's bitstream parameter (not its own frame shift register).
            emulateParamPairs=[
                ("Emulate_Bitstream", f"Tile_X{mx}Y{my}_Emulate_Bitstream")
            ],
        )

    # Instantiate the wrapper switch matrix (only when a wrapper matrix exists).
    sm_config_bits = tile.switch_matrix.total_config_bits
    if tile.matrix_dir != Path():
        sm_ports_pairs = []
        # Bind each referenced sub-tile port to its intermediate signal, one
        # scalar SM port per referenced bit ({sub}_{port}{k} <- {sub}_{port}[k]).
        # Only referenced bits are bound: the wrapper SM module declares a scalar
        # port only for the bits it references, not for every bit 0..wire_count-1.
        for sub_name, port_name, _wire_count, referenced_bits in wrapper_signals:
            for k in referenced_bits:
                sm_ports_pairs.append(
                    (f"{sub_name}_{port_name}{k}", f"{sub_name}_{port_name}[{k}]")
                )
        # BEL pins are driven by / drive the SM via signals named after the pins.
        for bel in tile.bels:
            for ip in bel.inputs:
                sm_ports_pairs.append((ip.name, ip.name))
        for bel in tile.bels:
            for op in bel.outputs:
                sm_ports_pairs.append((op.name, op.name))
        if sm_config_bits > 0 and config_bit_mode == ConfigBitMode.FRAME_BASED:
            sm_ports_pairs.append(
                ("ConfigBits", f"ST_ConfigBits[{sm_config_bits}-1:0]")
            )
            sm_ports_pairs.append(
                ("ConfigBits_N", f"ST_ConfigBits_N[{sm_config_bits}-1:0]")
            )
        writer.addInstantiation(
            compName=f"{tile.name}_switch_matrix",
            compInsName=f"Inst_{tile.name}_switch_matrix",
            portsPairs=sm_ports_pairs,
        )

    # Instantiate wrapper BELs at the master cell.
    bel_config_offset = sm_config_bits
    for bel in tile.bels:
        bel_ports_pairs = []
        # Bus the individual switch-matrix signals into the BEL's vector ports,
        # mirroring the normal-tile BEL instantiation (e.g. .A({A7,...,A0})). The
        # signals {prefix}{port}{i} are the wrapper SM outputs / BEL inputs.
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
        if not disable_user_clk and bel.with_user_clock:
            # The wrapper has no bare "UserCLK"; the BEL shares the master cell's
            # clock net (same selection the master cell uses). Top-first storage:
            # the master's clock is the chained UserCLKo from the north cell (y-1),
            # or its own UserCLK input.
            if 0 <= my - 1 < len(tile_map) and tile_map[my - 1][mx] is not None:
                bel_user_clk = f"Tile_X{mx}Y{my - 1}_UserCLKo"
            else:
                bel_user_clk = f"Tile_X{mx}Y{my}_UserCLK"
            bel_ports_pairs.append(("UserCLK", bel_user_clk))
        if bel.config_bit > 0 and config_bit_mode == ConfigBitMode.FRAME_BASED:
            bel_ports_pairs.append(
                (
                    "ConfigBits",
                    f"ST_ConfigBits["
                    f"{bel_config_offset + bel.config_bit}-1:{bel_config_offset}]",
                )
            )
        bel_config_offset += bel.config_bit
        writer.addInstantiation(
            compName=bel.name,
            compInsName=f"Inst_ST_{bel.prefix}{bel.name}",
            portsPairs=bel_ports_pairs,
        )

    writer.addDesignDescriptionEnd()
    writer.writeToFile()

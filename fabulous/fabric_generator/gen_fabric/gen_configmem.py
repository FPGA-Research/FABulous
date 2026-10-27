"""Configuration memory generation module.

This module provides functions to generate configuration memory initialization files and
RTL code for fabric tiles. It handles the mapping of configuration bits to frames and
generates the necessary hardware description language code for memory access and
control.
"""

from dataclasses import replace
from pathlib import Path
from typing import TYPE_CHECKING

from loguru import logger

from fabulous.fabric_definition.configmem import ConfigMem
from fabulous.fabric_definition.define import IO
from fabulous.fabric_generator.code_generator.code_generator import CodeGenerator
from fabulous.fabric_generator.code_generator.code_generator_Verilog import (
    VerilogCodeGenerator,
)
from fabulous.fabric_generator.code_generator.code_generator_VHDL import (
    VHDLCodeGenerator,
)

if TYPE_CHECKING:
    from fabulous.fabric_definition.supertile import SuperTile
    from fabulous.fabric_definition.tile import Tile


def generate_config_mem(writer: CodeGenerator, name: str, memory: ConfigMem) -> None:
    """Generate the RTL code for a configuration memory.

    Parameters
    ----------
    writer : CodeGenerator
        The code generator the module is written with.
    name : str
        The tile the memory belongs to.
    memory : ConfigMem
        The mapping the module implements. A mapping holding no bits gets no
        module, since `ConfigBits[-1:0]` is not a vector.
    """
    if memory.config_bits == 0:
        logger.info(f"{name} maps no configuration bits, so it gets no module")
        return
    logger.info(
        f"{name} maps {memory.config_bits} configuration bits over "
        f"{len(memory.used_frames)} frames"
    )
    logger.info(f"Generating {writer.outFileName} for {name}")
    writer.addHeader(f"{name}_ConfigMem")
    writer.addParameterStart(indentLevel=1)
    if isinstance(writer, VerilogCodeGenerator):  # emulation only in Verilog
        maxBits = memory.frame_bits_per_row * memory.max_frames_per_col
        writer.addPreprocIfDef("EMULATION")
        writer.addParameter(
            "Emulate_Bitstream",
            f"[{maxBits - 1}:0]",
            f"{maxBits}'b0",
            indentLevel=2,
        )
        writer.addPreprocEndif()
    if memory.max_frames_per_col != 0:
        writer.addParameter(
            "MaxFramesPerCol", "integer", memory.max_frames_per_col, indentLevel=2
        )
    if memory.frame_bits_per_row != 0:
        writer.addParameter(
            "FrameBitsPerRow", "integer", memory.frame_bits_per_row, indentLevel=2
        )
    writer.addParameter("NoConfigBits", "integer", memory.config_bits, indentLevel=2)
    writer.addParameterEnd(indentLevel=1)
    writer.addPortStart(indentLevel=1)
    # the port definitions are generic
    writer.addPortVector("FrameData", IO.INPUT, "FrameBitsPerRow - 1", indentLevel=2)
    writer.addPortVector("FrameStrobe", IO.INPUT, "MaxFramesPerCol - 1", indentLevel=2)
    writer.addPortVector("ConfigBits", IO.OUTPUT, "NoConfigBits - 1", indentLevel=2)
    writer.addPortVector("ConfigBits_N", IO.OUTPUT, "NoConfigBits - 1", indentLevel=2)
    writer.addPortEnd(indentLevel=1)
    writer.addHeaderEnd(f"{name}_ConfigMem")
    writer.addNewLine()
    # declare architecture
    writer.addDesignDescriptionStart(f"{name}_ConfigMem")

    if isinstance(writer, VerilogCodeGenerator):  # emulation only in Verilog
        writer.addPreprocIfDef("EMULATION")
        for crosspoint, bit in memory.bit_at.items():
            index = crosspoint.frame * memory.frame_bits_per_row + crosspoint.data_bit
            writer.addAssignScalar(f"ConfigBits[{bit}]", f"Emulate_Bitstream[{index}]")
        writer.addPreprocElse()
    writer.addNewLine()
    writer.addNewLine()
    writer.addLogicStart()
    writer.addComment("instantiate frame latches", end="")
    for crosspoint, bit in memory.bit_at.items():
        writer.addInstantiation(
            compName="config_latch",
            compInsName=(
                f"Inst_{memory.frame_names[crosspoint.frame]}_bit{crosspoint.data_bit}"
            ),
            portsPairs=[
                ("D", f"FrameData[{crosspoint.data_bit}]"),
                ("E", f"FrameStrobe[{crosspoint.frame}]"),
                ("Q", f"ConfigBits[{bit}]"),
                ("QN", f"ConfigBits_N[{bit}]"),
            ],
        )
    if isinstance(writer, VerilogCodeGenerator):  # emulation only in Verilog
        writer.addPreprocEndif()
    writer.addDesignDescriptionEnd()
    writer.writeToFile()


def _module_path(writer: CodeGenerator, name: str, tile_dir: Path) -> Path:
    """Return the `<name>_ConfigMem` module path in the tile's own directory.

    `gen_tile` looks for the module there, so a `CONFIGMEM` entry naming another
    directory moves only the CSV.
    """
    extension = "vhdl" if isinstance(writer, VHDLCodeGenerator) else "v"
    return tile_dir / f"{name}_ConfigMem.{extension}"


def generate_tile_config_mem(writer: CodeGenerator, tile: "Tile") -> None:
    """Generate the tile's configuration memory module from its mapping.

    A tile whose mapping holds no bits yet gets the default mapping, written to
    its `source`. A tile with no configuration bits gets neither file.

    Parameters
    ----------
    writer : CodeGenerator
        The code generator the module is written with, which also decides the
        HDL the module is written in.
    tile : Tile
        The tile the memory belongs to.

    Raises
    ------
    ValueError
        If the tile's mapping, or an existing empty file, holds a different
        number of bits than the tile.
    """
    if tile.globalConfigBits == 0:
        logger.info(f"{tile.name} has no configuration bits to map")
        return
    memory = tile.config_mem
    if memory.config_bits == 0:
        # An existing empty file is stale; refuse rather than overwrite it.
        if memory.source.is_file():
            raise ValueError(
                f"{memory.source} maps no configuration bits but {tile.name} "
                f"has {tile.globalConfigBits}. Delete the file to regenerate it."
            )
        tile.config_mem = ConfigMem.default(
            tile.globalConfigBits,
            frame_bits_per_row=memory.frame_bits_per_row,
            max_frames_per_col=memory.max_frames_per_col,
            source=memory.source,
        )
        memory = tile.config_mem
        memory.to_csv()
        logger.info(f"Wrote the default mapping to {memory.source}")
    elif memory.config_bits != tile.globalConfigBits:
        raise ValueError(
            f"{memory} maps {memory.config_bits} bits but {tile.name} has "
            f"{tile.globalConfigBits}. Delete the file to regenerate it."
        )
    writer.outFileName = _module_path(writer, tile.name, tile.directory)
    generate_config_mem(writer, tile.name, memory)


def validate_super_tile_config_mem(
    super_tile: ConfigMem, master: ConfigMem, num_bits_needed: int
) -> None:
    """Check a supertile's memory against the master tile's.

    A supertile's memory occupies the free crosspoints of its master tile's
    frame space. One that already exists is only safe to keep if it still holds
    the current supertile bit count and overlaps no bit the master itself uses.

    Parameters
    ----------
    super_tile : ConfigMem
        The supertile's existing memory.
    master : ConfigMem
        The master tile's memory.
    num_bits_needed : int
        Number of supertile configuration bits that must be present.

    Raises
    ------
    ValueError
        If the supertile does not hold exactly `num_bits_needed` bits, or if any
        crosspoint is occupied by both memories.
    """
    if super_tile.config_bits != num_bits_needed:
        raise ValueError(
            f"Supertile ConfigMem {super_tile} uses {super_tile.config_bits} "
            f"config bits but the supertile switch matrix needs "
            f"{num_bits_needed}. Delete the file to regenerate it."
        )
    for st_frame, master_frame in zip(super_tile.frames, master.frames, strict=True):
        overlap = st_frame.used_bits_mask & master_frame.used_bits_mask
        conflicts = [k for k, bit in enumerate(overlap) if bit]
        if conflicts:
            raise ValueError(
                f"Supertile ConfigMem {super_tile} conflicts with the master "
                f"tile ConfigMem {master} in frame {st_frame.frame_index} at "
                f"bit position(s) {conflicts}: both drive the same physical "
                "config bit. Delete the supertile ConfigMem to regenerate it."
            )


def build_super_tile_config_mem(
    master: ConfigMem, num_bits_needed: int, *, source: Path
) -> ConfigMem:
    """Place a supertile's bits in the crosspoints the master tile leaves free.

    The bits take the free crosspoints in reading order, so the result is a
    memory of the master's own grid that occupies none of the master's bits.

    Parameters
    ----------
    master : ConfigMem
        The master tile's memory.
    num_bits_needed : int
        Number of supertile configuration bits to place.
    source : Path
        The supertile's own `<name>_ConfigMem.csv`, which is not the master's.

    Returns
    -------
    ConfigMem
        The supertile's memory, on the master's grid.

    Raises
    ------
    ValueError
        If the master leaves fewer free crosspoints than there are bits.
    """
    free_slots = master.free_crosspoints
    if len(free_slots) < num_bits_needed:
        raise ValueError(
            f"Not enough free config bit slots in master tile ({master}): need "
            f"{num_bits_needed}, found only {len(free_slots)} free slots."
        )
    return replace(
        master.rebuilt_with(
            {slot: bit for bit, slot in enumerate(free_slots[:num_bits_needed])}
        ),
        source=source,
    )


def generate_super_tile_config_mem(
    writer: CodeGenerator, super_tile: "SuperTile", master: ConfigMem
) -> None:
    """Give a supertile its configuration memory and generate the module for it.

    The supertile's bits go in the crosspoints the master tile's memory leaves
    free. An existing mapping is kept once checked against the master. A
    supertile with no configuration bits of its own gets no memory.

    Parameters
    ----------
    writer : CodeGenerator
        The code generator the module is written with, which also decides the
        HDL the module is written in.
    super_tile : SuperTile
        The supertile the memory belongs to.
    master : ConfigMem
        The master tile's memory, whose free crosspoints the bits take.

    Raises
    ------
    ValueError
        If the supertile was built without a configuration memory, or if a
        mapping already on disk holds no bits.
    """
    config_bits = super_tile.total_config_bits
    if config_bits <= 0:
        logger.info(f"{super_tile.name} has no configuration bits of its own")
        return

    existing = super_tile.config_mem
    if existing is None:
        raise ValueError(f"{super_tile.name} was built without a configuration memory.")
    if existing.config_bits > 0:
        validate_super_tile_config_mem(existing, master, config_bits)
    elif existing.source.is_file():
        # An existing empty file is stale; refuse rather than overwrite it.
        raise ValueError(
            f"{existing.source} maps no configuration bits but "
            f"{super_tile.name} has {config_bits}. Delete the file to "
            "regenerate it."
        )
    else:
        super_tile.config_mem = build_super_tile_config_mem(
            master, config_bits, source=existing.source
        )
        super_tile.config_mem.to_csv()

    writer.outFileName = _module_path(writer, super_tile.name, super_tile.directory)
    generate_config_mem(writer, super_tile.name, super_tile.config_mem)

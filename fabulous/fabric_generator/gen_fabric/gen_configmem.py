"""Configuration memory generation module.

This module provides functions to generate configuration memory initialization files and
RTL code for fabric tiles. It handles the mapping of configuration bits to frames and
generates the necessary hardware description language code for memory access and
control.
"""

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
from fabulous.fabric_generator.parser.parse_csv import (
    config_mem_csv_of,
    read_config_mem_of,
)

if TYPE_CHECKING:
    from fabulous.fabric_definition.tile import Tile


def generateConfigMem(writer: CodeGenerator, name: str, memory: ConfigMem) -> None:
    """Generate the RTL code for a configuration memory.

    Parameters
    ----------
    writer : CodeGenerator
        The code generator the module is written with.
    name : str
        The tile the memory belongs to.
    memory : ConfigMem
        The mapping the module implements, one frame per `FrameStrobe` line.
    """
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


def _module_path(writer: CodeGenerator, tile: "Tile") -> Path:
    """Return where a tile's `<tile>_ConfigMem` module goes, in the writer's HDL."""
    extension = "vhdl" if isinstance(writer, VHDLCodeGenerator) else "v"
    return config_mem_csv_of(tile).with_suffix(f".{extension}")


def generate_tile_config_mem(
    writer: CodeGenerator,
    tile: "Tile",
    *,
    frame_bits_per_row: int,
    max_frames_per_col: int,
) -> None:
    """Give a tile its configuration memory and generate the module for it.

    The tile takes the mapping of its `<tile>_ConfigMem.csv`, or the enumerated
    default where that file has still to be written, and the file is written
    from it so the RTL, the CSV and the model all say the same thing. A tile
    with no configuration bits has nothing to map and gets neither.

    Parameters
    ----------
    writer : CodeGenerator
        The code generator the module is written with, which also decides the
        HDL the module is written in.
    tile : Tile
        The tile the memory belongs to.
    frame_bits_per_row : int
        The fabric's `FrameBitsPerRow`.
    max_frames_per_col : int
        The fabric's `MaxFramesPerCol`.
    """
    tile.config_mem = read_config_mem_of(
        tile,
        frame_bits_per_row=frame_bits_per_row,
        max_frames_per_col=max_frames_per_col,
    )
    if tile.config_mem.config_bits == 0:
        logger.info(f"{tile.name} has no configuration bits to map")
        return
    config_mem_csv = config_mem_csv_of(tile)
    if not config_mem_csv.is_file():
        config_mem_csv.parent.mkdir(parents=True, exist_ok=True)
        tile.config_mem.to_csv(config_mem_csv)
        logger.info(f"Wrote the default mapping to {config_mem_csv}")
    writer.outFileName = _module_path(writer, tile)
    generateConfigMem(writer, tile.name, tile.config_mem)


def validate_composite_config_mem(
    composite_config_mem_csv: Path,
    master_config_mem_csv: Path,
    num_bits_needed: int,
    frame_bits_per_row: int = 32,
    max_frames_per_col: int = 20,
) -> None:
    """Validate an existing supertile ConfigMem against the master tile.

    A supertile ConfigMem reuses the *free* bit slots of its master tile's frame
    space.  Reusing an existing file is only safe if it still matches the current
    supertile bit count and does not overlap any bit the master tile itself uses.

    Parameters
    ----------
    composite_config_mem_csv : Path
        Path to the existing supertile `*_ConfigMem.csv` to validate.
    master_config_mem_csv : Path
        Path to the master tile's `*_ConfigMem.csv`.
    num_bits_needed : int
        Number of composite configuration bits that must be present.
    frame_bits_per_row : int
        Number of bits per frame row.
    max_frames_per_col : int
        Number of frames per column.

    Raises
    ------
    ValueError
        If either file has the wrong row count, the composite does not use exactly
        `num_bits_needed` bits, or any frame bit is used by both ConfigMems.
    """
    composite = ConfigMem.from_csv(
        composite_config_mem_csv,
        frame_bits_per_row=frame_bits_per_row,
        max_frames_per_col=max_frames_per_col,
    )
    master = ConfigMem.from_csv(
        master_config_mem_csv,
        frame_bits_per_row=frame_bits_per_row,
        max_frames_per_col=max_frames_per_col,
    )

    if composite.config_bits != num_bits_needed:
        raise ValueError(
            f"Composite ConfigMem {composite_config_mem_csv} uses "
            f"{composite.config_bits} config bits but the composite wrapper "
            f"needs {num_bits_needed}. Delete the file to regenerate it."
        )

    for st_frame, master_frame in zip(composite.frames, master.frames, strict=True):
        overlap = st_frame.used_bits_mask & master_frame.used_bits_mask
        conflicts = [k for k, bit in enumerate(overlap) if bit]
        if conflicts:
            raise ValueError(
                f"Composite ConfigMem {composite_config_mem_csv} conflicts with "
                f"the master tile ConfigMem {master_config_mem_csv} in frame "
                f"{st_frame.frame_index} at "
                f"bit position(s) {conflicts}: both drive the same physical config "
                "bit. Delete the composite ConfigMem to regenerate it."
            )


def build_composite_config_mem_csv(
    master_config_mem_csv: Path,
    num_bits_needed: int,
    output_path: Path,
    frame_bits_per_row: int = 32,
    max_frames_per_col: int = 20,
) -> None:
    """Build a ConfigMem CSV for a wrapper from the master cell's free slots.

    Reads the master cell's ConfigMem CSV, collects the crosspoints its
    `used_bits_mask` leaves free, and writes a new CSV that maps
    `ConfigBits[0..num_bits_needed-1]` to those positions in reading order.
    The output CSV has exactly `max_frames_per_col` rows, so it is a memory of
    the fabric's grid.

    Parameters
    ----------
    master_config_mem_csv : Path
        Path to the master tile's existing `*_ConfigMem.csv`.
    num_bits_needed : int
        Number of composite configuration bits to place.
    output_path : Path
        Destination path for the generated composite ConfigMem CSV.
    frame_bits_per_row : int
        Number of bits per frame row (must match the fabric setting).
    max_frames_per_col : int
        Number of frames per column (must match the fabric setting).

    Raises
    ------
    ValueError
        If the master tile's ConfigMem CSV does not have exactly `max_frames_per_col`
        rows, or if there are fewer free slots than `num_bits_needed`.
    """
    # Reuse an existing (possibly hand-tuned) supertile ConfigMem instead of
    # overwriting it, but only after confirming it is still consistent with the
    # master tile's frame usage. A mismatch raises so the user deletes the file
    # to force regeneration rather than silently shipping a broken bitstream.
    if output_path.exists():
        validate_composite_config_mem(
            output_path,
            master_config_mem_csv,
            num_bits_needed,
            frame_bits_per_row,
            max_frames_per_col,
        )
        return

    master = ConfigMem.from_csv(
        master_config_mem_csv,
        frame_bits_per_row=frame_bits_per_row,
        max_frames_per_col=max_frames_per_col,
    )
    free_slots = master.free_crosspoints
    if len(free_slots) < num_bits_needed:
        raise ValueError(
            f"Not enough free config bit slots in master tile "
            f"({master_config_mem_csv.parent.name}): need {num_bits_needed}, "
            f"found only {len(free_slots)} free slots."
        )

    master.rebuilt_with(
        {slot: bit for bit, slot in enumerate(free_slots[:num_bits_needed])}
    ).to_csv(output_path)


def generate_composite_config_mem(
    writer: CodeGenerator,
    composite: "Tile",
    *,
    frame_bits_per_row: int,
    max_frames_per_col: int,
) -> None:
    """Give a composite tile its configuration memory and generate the module for it.

    The wrapper bits go in the crosspoints the master cell's memory leaves free,
    so the master's mapping has to exist first. A composite with no wrapper
    configuration bits of its own gets no memory.

    Parameters
    ----------
    writer : CodeGenerator
        The code generator the module is written with, which also decides the
        HDL the module is written in.
    composite : Tile
        The composite tile the memory belongs to.
    frame_bits_per_row : int
        The fabric's `FrameBitsPerRow`.
    max_frames_per_col : int
        The fabric's `MaxFramesPerCol`.

    Raises
    ------
    ValueError
        If the master cell's `tile_dir` is unset, which would otherwise resolve
        silently to the current working directory.
    FileNotFoundError
        If the master cell has no directory, which would otherwise read as an
        all-free frame space and silently collide.
    """
    config_bits = composite.total_config_bits
    if config_bits <= 0:
        logger.info(f"{composite.name} has no configuration bits of its own")
        return

    master = composite.get_master_tile()
    if master.tile_dir == Path():
        raise ValueError(
            f"Master cell '{master.name}' of composite '{composite.name}' has an "
            "unset tile_dir, which resolves to the current working directory and "
            "would read or write the wrong ConfigMem. Set tile_dir on the master "
            "cell before generating the composite ConfigMem."
        )
    # `tile_dir` is the tile's CSV file for a parsed tile, its directory for a
    # tile built in memory.
    master_dir = master.tile_dir if master.tile_dir.is_dir() else master.tile_dir.parent
    if not master_dir.is_dir():
        raise FileNotFoundError(
            f"Master cell '{master.name}' of composite '{composite.name}' has no "
            f"directory at {master_dir}, so its used config bits cannot be read. "
            "Generate the master cell before the composite."
        )

    # The master's own mapping fixes which crosspoints the wrapper may use, so
    # it is written first where it does not exist yet.
    master_csv = config_mem_csv_of(master)
    if not master_csv.is_file():
        logger.info(
            f"{master_csv} does not exist; writing the master mapping before "
            f"allocating the bits of composite {composite.name}"
        )
        ConfigMem.default(
            master.total_config_bits,
            frame_bits_per_row=frame_bits_per_row,
            max_frames_per_col=max_frames_per_col,
        ).to_csv(master_csv)

    output_csv = config_mem_csv_of(composite)
    build_composite_config_mem_csv(
        master_csv,
        config_bits,
        output_csv,
        frame_bits_per_row=frame_bits_per_row,
        max_frames_per_col=max_frames_per_col,
    )
    composite.config_mem = ConfigMem.for_tile(
        output_csv,
        config_bits=config_bits,
        frame_bits_per_row=frame_bits_per_row,
        max_frames_per_col=max_frames_per_col,
    )
    writer.outFileName = _module_path(writer, composite)
    generateConfigMem(writer, composite.name, composite.config_mem)

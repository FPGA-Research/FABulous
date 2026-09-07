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

if TYPE_CHECKING:
    from fabulous.fabric_definition.supertile import SuperTile


def generateConfigMemInit(
    file: Path,
    tileConfigBitsCount: int,
    frame_bits_per_row: int = 32,
    max_frame_per_col: int = 20,
) -> None:
    """Generate the config memory initialization file.

    `ConfigMem.default` rejects a bit count above the grid's capacity.
    The amount of configuration bits is determined
    by `frame_bits_per_row`. The function will pack the configuration bit from
    the highest to the lowest bit in the config memory. I. e. if there are 100
    configuration bits, with 32 frame bits per row, the function will pack from
    bit 99 starting from bit 31 of frame 0 to bit 28 of frame 3.

    Parameters
    ----------
    file : Path
        The output file of the config memory initialization file.
    tileConfigBitsCount : int
        The number of tile config bits of the tile.
    frame_bits_per_row : int
        The number of configuration bits per frame row.
    max_frame_per_col : int
        The number of frames stored per tile column.
    """
    ConfigMem.default(
        tileConfigBitsCount,
        frame_bits_per_row=frame_bits_per_row,
        max_frames_per_col=max_frame_per_col,
    ).to_csv(file)


def generateConfigMem(
    writer: CodeGenerator,
    name: str,
    config_bits_count: int,
    configMemCsv: Path,
    frame_bits_per_row: int = 32,
    max_frame_per_col: int = 20,
) -> None:
    """Generate the RTL code for configuration memory.

    If the given configMemCsv file does not exist, it will be created using
    `generateConfigMemInit`.

    We use a file to describe the exact configuration bits to frame mapping
    the following command generates an init file with a
    simple enumerated default mapping (e.g. 'LUT4AB_ConfigMem.init.csv')
    if we run this function again, but have such a file (without the .init),
    then that mapping will be used

    Parameters
    ----------
    writer : CodeGenerator
        The code generator instance for RTL output
    name : str
        Name of the tile or module (used for module naming and log messages).
    config_bits_count : int
        Total number of configuration bits.
    configMemCsv : Path
        The directory of the config memory CSV file.
    frame_bits_per_row : int
        The number of configuration bits per frame row.
    max_frame_per_col : int
        The number of frames stored per tile column.

    Raises
    ------
    ValueError
        - If the config bits exceed the fabric capacity.
        - If the total config bits in the config memory CSV file does not match
          config_bits_count.
    """
    if config_bits_count > frame_bits_per_row * max_frame_per_col:
        raise ValueError(
            f"{name} has {config_bits_count} global config bits, "
            " which exceeds fabric capacity "
            f"({frame_bits_per_row * max_frame_per_col} bits). "
            "Please adjust the configuration."
        )

    if configMemCsv.exists():
        if config_bits_count <= 0:
            logger.warning(
                f"Found bitstream mapping file {name}_configMem.csv for {name}, "
                "but no global config bits are defined"
            )
        else:
            logger.info(f"Found bitstream mapping file {name}_configMem.csv for {name}")
    elif config_bits_count > 0:
        logger.info(f"{name}_configMem.csv does not exist")
        logger.info(f"Generating a default configMem for {name}")
        generateConfigMemInit(
            configMemCsv,
            config_bits_count,
            frame_bits_per_row=frame_bits_per_row,
            max_frame_per_col=max_frame_per_col,
        )
    else:
        logger.info(
            f"No config bits defined and no bitstream mapping file provided for {name}"
        )
        return

    logger.info(f"Parsing {name}_configMem.csv")
    memory = ConfigMem.from_csv(configMemCsv).validate(
        frame_bits_per_row=frame_bits_per_row,
        max_frames_per_col=max_frame_per_col,
        config_bits=config_bits_count,
    )
    logger.info(
        f"Found {len(memory.used_frames)} config memory entries in "
        f"{name}_configMem.csv with a total of {memory.config_bits} bits"
    )
    logger.info(f"{name} has {config_bits_count} global config bits")

    # start writing the file
    logger.info(f"Generating {writer.outFileName} for {name}")
    writer.addHeader(f"{name}_ConfigMem")
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
    if max_frame_per_col != 0:
        writer.addParameter(
            "MaxFramesPerCol", "integer", max_frame_per_col, indentLevel=2
        )
    if frame_bits_per_row != 0:
        writer.addParameter(
            "FrameBitsPerRow", "integer", frame_bits_per_row, indentLevel=2
        )
    writer.addParameter("NoConfigBits", "integer", config_bits_count, indentLevel=2)
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
            index = crosspoint.frame * frame_bits_per_row + crosspoint.data_bit
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


def _read_config_mem(
    config_mem_csv: Path, *, frame_bits_per_row: int, max_frames_per_col: int
) -> ConfigMem:
    """Read a ConfigMem CSV whose grid must match the fabric's frame parameters.

    Parameters
    ----------
    config_mem_csv : Path
        Path to a `*_ConfigMem.csv` file.
    frame_bits_per_row : int
        Expected width of every frame.
    max_frames_per_col : int
        Expected number of frame rows.

    Raises
    ------
    ValueError
        If the file does not have exactly `max_frames_per_col` rows of
        `frame_bits_per_row` bits.

    Returns
    -------
    ConfigMem
        The memory read from the file.
    """
    memory = ConfigMem.from_csv(config_mem_csv)
    if memory.max_frames_per_col != max_frames_per_col:
        raise ValueError(
            f"ConfigMem {config_mem_csv} has {memory.max_frames_per_col} rows but "
            f"MaxFramesPerCol is {max_frames_per_col}."
        )
    if memory.frame_bits_per_row != frame_bits_per_row:
        raise ValueError(
            f"ConfigMem {config_mem_csv} has {memory.frame_bits_per_row}-bit frames "
            f"but FrameBitsPerRow is {frame_bits_per_row}."
        )
    return memory


def validate_super_tile_config_mem(
    super_tile_config_mem_csv: Path,
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
    super_tile_config_mem_csv : Path
        Path to the existing supertile `*_ConfigMem.csv` to validate.
    master_config_mem_csv : Path
        Path to the master tile's `*_ConfigMem.csv`.
    num_bits_needed : int
        Number of supertile configuration bits that must be present.
    frame_bits_per_row : int
        Number of bits per frame row.
    max_frames_per_col : int
        Number of frames per column.

    Raises
    ------
    ValueError
        If either file has the wrong row count, the supertile does not use exactly
        `num_bits_needed` bits, or any frame bit is used by both ConfigMems.
    """
    super_tile = _read_config_mem(
        super_tile_config_mem_csv,
        frame_bits_per_row=frame_bits_per_row,
        max_frames_per_col=max_frames_per_col,
    )
    master = _read_config_mem(
        master_config_mem_csv,
        frame_bits_per_row=frame_bits_per_row,
        max_frames_per_col=max_frames_per_col,
    )

    if super_tile.config_bits != num_bits_needed:
        raise ValueError(
            f"Supertile ConfigMem {super_tile_config_mem_csv} uses "
            f"{super_tile.config_bits} config bits but the supertile switch matrix "
            f"needs {num_bits_needed}. Delete the file to regenerate it."
        )

    for st_frame, master_frame in zip(super_tile.frames, master.frames, strict=True):
        conflicts = [
            k
            for k, (a, b) in enumerate(
                zip(st_frame.usedBitMask, master_frame.usedBitMask, strict=True)
            )
            if a == "1" and b == "1"
        ]
        if conflicts:
            raise ValueError(
                f"Supertile ConfigMem {super_tile_config_mem_csv} conflicts with "
                f"the master tile ConfigMem {master_config_mem_csv} in frame "
                f"{st_frame.frameIndex} at "
                f"bit position(s) {conflicts}: both drive the same physical config "
                "bit. Delete the supertile ConfigMem to regenerate it."
            )


def build_super_tile_config_mem_csv(
    master_config_mem_csv: Path,
    num_bits_needed: int,
    output_path: Path,
    frame_bits_per_row: int = 32,
    max_frames_per_col: int = 20,
) -> None:
    """Build a ConfigMem CSV for a supertile SM using free slots from the master tile.

    Reads the master tile's ConfigMem CSV, collects the crosspoints its
    `used_bits_mask` leaves free, and writes a new CSV that maps
    `ST_ConfigBits[0..num_bits_needed-1]` to those positions in reading order.
    The output CSV has exactly `max_frames_per_col` rows so it is accepted by
    `parseConfigMem`.

    Parameters
    ----------
    master_config_mem_csv : Path
        Path to the master tile's existing `*_ConfigMem.csv`.
    num_bits_needed : int
        Number of supertile configuration bits to place.
    output_path : Path
        Destination path for the generated supertile ConfigMem CSV.
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
        validate_super_tile_config_mem(
            output_path,
            master_config_mem_csv,
            num_bits_needed,
            frame_bits_per_row,
            max_frames_per_col,
        )
        return

    master = _read_config_mem(
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


def generate_super_tile_config_mem(
    writer: CodeGenerator,
    superTile: "SuperTile",
    master_config_mem_csv: Path,
    frame_bits_per_row: int = 32,
    max_frame_per_col: int = 20,
) -> None:
    """Generate the ConfigMem RTL for a supertile switch matrix.

    Builds a ConfigMem CSV that places the supertile SM's config bits into the
    free slots of the master tile's frame space, then generates the Verilog/VHDL
    module via `generateConfigMem`.

    Parameters
    ----------
    writer : CodeGenerator
        Code generator instance for RTL output.
    superTile : SuperTile
        The supertile whose SM config bits need a ConfigMem.
    master_config_mem_csv : Path
        Path to the master tile's existing `*_ConfigMem.csv`.
    frame_bits_per_row : int
        Number of bits per frame row.
    max_frame_per_col : int
        Number of frames per column.
    """
    st_config_bits = superTile.total_config_bits
    if st_config_bits <= 0:
        return

    output_csv = superTile.config_mem_path
    build_super_tile_config_mem_csv(
        master_config_mem_csv,
        st_config_bits,
        output_csv,
        frame_bits_per_row=frame_bits_per_row,
        max_frames_per_col=max_frame_per_col,
    )
    generateConfigMem(
        writer,
        superTile.name,
        st_config_bits,
        output_csv,
        frame_bits_per_row=frame_bits_per_row,
        max_frame_per_col=max_frame_per_col,
    )

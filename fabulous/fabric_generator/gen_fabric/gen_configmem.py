"""Configuration memory generation module.

This module provides functions to generate configuration memory initialization files and
RTL code for fabric tiles. It handles the mapping of configuration bits to frames and
generates the necessary hardware description language code for memory access and
control.
"""

import csv
from pathlib import Path
from typing import TYPE_CHECKING

from bitarray import bitarray
from loguru import logger

from fabulous.fabric_definition.define import IO
from fabulous.fabric_generator.code_generator.code_generator import CodeGenerator
from fabulous.fabric_generator.code_generator.code_generator_Verilog import (
    VerilogCodeGenerator,
)
from fabulous.fabric_generator.parser.parse_configmem import parseConfigMem

if TYPE_CHECKING:
    from fabulous.fabric_definition.configmem import ConfigMem
    from fabulous.fabric_definition.supertile import SuperTile


def generateConfigMemInit(
    file: Path,
    tileConfigBitsCount: int,
    frame_bits_per_row: int = 32,
    max_frame_per_col: int = 20,
) -> None:
    """Generate the config memory initialization file.

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

    Raises
    ------
    ValueError
        If the tile config bits exceed the fabric capacity.
    """
    if tileConfigBitsCount > frame_bits_per_row * max_frame_per_col:
        raise ValueError(
            f"Tile config bits ({tileConfigBitsCount}) exceed fabric capacity "
            f"({frame_bits_per_row * max_frame_per_col} bits). "
            f"Please adjust the tile configuration."
        )

    fieldName = [
        "frame_name",
        "frame_index",
        "bits_used_in_frame",
        "used_bits_mask",
        "ConfigBits_ranges",
    ]

    with file.open("w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(fieldName)
        bits = bitarray(frame_bits_per_row * max_frame_per_col)
        bits[:tileConfigBitsCount] = 1

        # adjust for zero-based indexing in subsequent calculations
        tileConfigBitsCount -= 1

        count = 0
        for k in range(max_frame_per_col):
            entry = {}
            # frame0, frame1, ...
            entry["frame_name"] = f"frame{k}"
            # and the index (0, 1, 2, ...), in case we need
            entry["frame_index"] = str(k)
            bitSlice = bits[count : count + frame_bits_per_row]
            entry["bits_used_in_frame"] = bitSlice.count(1)
            entry["used_bits_mask"] = bitSlice.to01(group=4, sep="_")
            if bitSlice.count(1) == 0:
                entry["ConfigBits_ranges"] = "# NULL"
            else:
                entry["ConfigBits_ranges"] = (
                    f"{tileConfigBitsCount}:"
                    f"{max(tileConfigBitsCount - frame_bits_per_row + 1, 0)}"
                )
            count += frame_bits_per_row
            tileConfigBitsCount -= frame_bits_per_row

            writer.writerow([entry[field] for field in fieldName])


def generateConfigMem(
    writer: CodeGenerator,
    name: str,
    config_bits_count: int,
    configMemCsv: Path,
    frame_bits_per_row: int = 32,
    max_frame_per_col: int = 20,
    disable_config_bits_n: bool = False,
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
    disable_config_bits_n : bool
        Whether to disable the generation of the inverted configuration bit
        ports (`ConfigBits_N`) and the corresponding latch `QN` outputs. When
        `True`, only `ConfigBits` and the `Q` latch outputs are generated.

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

    configMemList: list[ConfigMem] = []
    if configMemCsv.exists():
        if config_bits_count <= 0:
            logger.warning(
                f"Found bitstream mapping file {name}_configMem.csv for {name}, "
                "but no global config bits are defined"
            )
        else:
            logger.info(f"Found bitstream mapping file {name}_configMem.csv for {name}")
        logger.info(f"Parsing {name}_configMem.csv")
        configMemList = parseConfigMem(
            configMemCsv,
            max_frame_per_col,
            frame_bits_per_row,
            config_bits_count,
        )
    elif config_bits_count > 0:
        logger.info(f"{name}_configMem.csv does not exist")
        logger.info(f"Generating a default configMem for {name}")
        generateConfigMemInit(
            configMemCsv,
            config_bits_count,
            frame_bits_per_row=frame_bits_per_row,
            max_frame_per_col=max_frame_per_col,
        )
        logger.info(f"Parsing {name}_configMem.csv")
        configMemList = parseConfigMem(
            configMemCsv,
            max_frame_per_col,
            frame_bits_per_row,
            config_bits_count,
        )
    else:
        logger.info(
            f"No config bits defined and no bitstream mapping file provided for {name}"
        )
        return

    totalConfigBits = sum(i.bitsUsedInFrame for i in configMemList)
    logger.info(
        f"Found {len(configMemList)} config memory entries in "
        f"{name}_configMem.csv with a total of {totalConfigBits} bits"
    )
    logger.info(f"{name} has {config_bits_count} global config bits")

    if totalConfigBits != config_bits_count:
        raise ValueError(
            f"Total config bits in {name}_configMem.csv ({totalConfigBits}) "
            f"does not match global config bits ({config_bits_count})"
        )

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
    if not disable_config_bits_n:
        writer.addPortVector(
            "ConfigBits_N", IO.OUTPUT, "NoConfigBits - 1", indentLevel=2
        )
    writer.addPortEnd(indentLevel=1)
    writer.addHeaderEnd(f"{name}_ConfigMem")
    writer.addNewLine()
    # declare architecture
    writer.addDesignDescriptionStart(f"{name}_ConfigMem")

    if isinstance(writer, VerilogCodeGenerator):  # emulation only in Verilog
        writer.addPreprocIfDef("EMULATION")
        for i in configMemList:
            counter = 0
            for k in range(frame_bits_per_row):
                # Safely check if bit is set, treat missing bits as '0'
                bit_value = i.usedBitMask[k] if k < len(i.usedBitMask) else "0"
                if bit_value == "1":
                    index = i.frameIndex * frame_bits_per_row + (
                        frame_bits_per_row - 1 - k
                    )
                    writer.addAssignScalar(
                        f"ConfigBits[{i.configBitRanges[counter]}]",
                        f"Emulate_Bitstream[{index}]",
                    )
                    counter += 1
        writer.addPreprocElse()
    writer.addNewLine()
    writer.addNewLine()
    writer.addLogicStart()
    writer.addComment("instantiate frame latches", end="")
    for i in configMemList:
        counter = 0
        for k in range(frame_bits_per_row):
            # Safely check if bit is set, treat missing bits as '0'
            bit_value = i.usedBitMask[k] if k < len(i.usedBitMask) else "0"
            if bit_value == "1":
                latchPorts = [
                    ("D", f"FrameData[{frame_bits_per_row - 1 - k}]"),
                    ("E", f"FrameStrobe[{i.frameIndex}]"),
                    ("Q", f"ConfigBits[{i.configBitRanges[counter]}]"),
                ]
                if not disable_config_bits_n:
                    latchPorts.append(
                        ("QN", f"ConfigBits_N[{i.configBitRanges[counter]}]")
                    )
                writer.addInstantiation(
                    compName="config_latch",
                    compInsName=(f"Inst_{i.frameName}_bit{frame_bits_per_row - 1 - k}"),
                    portsPairs=latchPorts,
                )
                counter += 1
    if isinstance(writer, VerilogCodeGenerator):  # emulation only in Verilog
        writer.addPreprocEndif()
    writer.addDesignDescriptionEnd()
    writer.writeToFile()


def _read_config_mem_masks(
    config_mem_csv: Path, max_frames_per_col: int
) -> dict[int, str]:
    """Read a ConfigMem CSV into a `{frame_index: used_bits_mask}` mapping.

    Parameters
    ----------
    config_mem_csv : Path
        Path to a `*_ConfigMem.csv` file.
    max_frames_per_col : int
        Expected number of frame rows.

    Raises
    ------
    ValueError
        If the file does not have exactly `max_frames_per_col` rows.

    Returns
    -------
    dict[int, str]
        Mapping from frame index to its `used_bits_mask` (underscores stripped).
    """
    with config_mem_csv.open() as f:
        rows = list(csv.DictReader(f))
    if len(rows) != max_frames_per_col:
        raise ValueError(
            f"ConfigMem {config_mem_csv} has {len(rows)} rows but MaxFramesPerCol "
            f"is {max_frames_per_col}."
        )
    return {int(r["frame_index"]): r["used_bits_mask"].replace("_", "") for r in rows}


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
    st_masks = _read_config_mem_masks(super_tile_config_mem_csv, max_frames_per_col)
    master_masks = _read_config_mem_masks(master_config_mem_csv, max_frames_per_col)

    used_bits = sum(mask.count("1") for mask in st_masks.values())
    if used_bits != num_bits_needed:
        raise ValueError(
            f"Supertile ConfigMem {super_tile_config_mem_csv} uses {used_bits} config "
            f"bits but the supertile switch matrix needs {num_bits_needed}. Delete "
            "the file to regenerate it."
        )

    for frame_idx, st_mask in st_masks.items():
        master_mask = master_masks.get(frame_idx, "0" * frame_bits_per_row)
        conflicts = [
            k
            for k, (a, b) in enumerate(zip(st_mask, master_mask, strict=True))
            if a == "1" and b == "1"
        ]
        if conflicts:
            raise ValueError(
                f"Supertile ConfigMem {super_tile_config_mem_csv} conflicts with "
                f"the master tile ConfigMem {master_config_mem_csv} in frame "
                f"{frame_idx} at "
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

    Reads the master tile's ConfigMem CSV, collects bit positions where the
    `used_bits_mask` is `'0'` (free), and writes a new CSV that maps
    `ST_ConfigBits[0..num_bits_needed-1]` to those positions.  The output CSV
    has exactly `max_frames_per_col` rows so it is accepted by `parseConfigMem`.

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

    with master_config_mem_csv.open() as f:
        master_rows = list(csv.DictReader(f))

    if len(master_rows) != max_frames_per_col:
        raise ValueError(
            f"Master tile ConfigMem {master_config_mem_csv} has "
            f"{len(master_rows)} rows but MaxFramesPerCol is {max_frames_per_col}."
        )

    # Collect free (frame_index, bit_k) slots in reading order.
    # bit_k is the left-to-right index in the mask string (0 = MSB).
    free_slots: list[tuple[int, int]] = []
    for row in master_rows:
        mask = row["used_bits_mask"].replace("_", "")
        frame_idx = int(row["frame_index"])
        for k, bit in enumerate(mask):
            if bit == "0":
                free_slots.append((frame_idx, k))

    if len(free_slots) < num_bits_needed:
        raise ValueError(
            f"Not enough free config bit slots in master tile "
            f"({master_config_mem_csv.parent.name}): need {num_bits_needed}, "
            f"found only {len(free_slots)} free slots."
        )

    # Assign config bit indices to the first num_bits_needed free slots.
    frame_assignments: dict[int, list[tuple[int, int]]] = {}
    for config_bit_idx, (frame_idx, bit_k) in enumerate(free_slots[:num_bits_needed]):
        frame_assignments.setdefault(frame_idx, []).append((bit_k, config_bit_idx))

    field_names = [
        "frame_name",
        "frame_index",
        "bits_used_in_frame",
        "used_bits_mask",
        "ConfigBits_ranges",
    ]
    with output_path.open("w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(field_names)
        for row in master_rows:
            frame_idx = int(row["frame_index"])
            assignments = frame_assignments.get(frame_idx, [])
            if not assignments:
                mask_str = "0" * frame_bits_per_row
                config_bits_ranges = "# NULL"
            else:
                mask_list = ["0"] * frame_bits_per_row
                for bit_k, _ in assignments:
                    mask_list[bit_k] = "1"
                mask_str = "_".join(
                    "".join(mask_list[i : i + 4])
                    for i in range(0, frame_bits_per_row, 4)
                )
                assignments.sort(key=lambda x: x[0])
                config_bits_ranges = ";".join(str(cb_idx) for _, cb_idx in assignments)
            bits_used = mask_str.replace("_", "").count("1")
            writer.writerow(
                [row["frame_name"], frame_idx, bits_used, mask_str, config_bits_ranges]
            )


def generate_super_tile_config_mem(
    writer: CodeGenerator,
    superTile: "SuperTile",
    master_config_mem_csv: Path,
    frame_bits_per_row: int = 32,
    max_frame_per_col: int = 20,
    disable_config_bits_n: bool = False,
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
    disable_config_bits_n : bool
        Whether to disable the generation of the inverted configuration bit
        ports (`ConfigBits_N`) and the corresponding latch `QN` outputs.
    """
    st_config_bits = superTile.total_config_bits
    if st_config_bits <= 0:
        return

    output_csv = superTile.tileDir.parent / f"{superTile.name}_ConfigMem.csv"
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
        disable_config_bits_n=disable_config_bits_n,
    )

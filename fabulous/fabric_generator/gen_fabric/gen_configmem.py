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
    from fabulous.fabric_definition.tile import Tile


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
    writer.addPortVector("ConfigBits_N", IO.OUTPUT, "NoConfigBits - 1", indentLevel=2)
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
                writer.addInstantiation(
                    compName="config_latch",
                    compInsName=(f"Inst_{i.frameName}_bit{frame_bits_per_row - 1 - k}"),
                    portsPairs=[
                        ("D", f"FrameData[{frame_bits_per_row - 1 - k}]"),
                        ("E", f"FrameStrobe[{i.frameIndex}]"),
                        ("Q", f"ConfigBits[{i.configBitRanges[counter]}]"),
                        ("QN", f"ConfigBits_N[{i.configBitRanges[counter]}]"),
                    ],
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
        If the file does not have exactly `max_frames_per_col` rows, or its
        `frame_index` values do not cover exactly `0..max_frames_per_col - 1`
        (a duplicate index alongside a missing one both satisfy the row
        count, so that check alone does not catch either).

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
    masks = {int(r["frame_index"]): r["used_bits_mask"].replace("_", "") for r in rows}
    expected = set(range(max_frames_per_col))
    if masks.keys() != expected:
        missing = sorted(expected - masks.keys())
        unexpected = sorted(masks.keys() - expected)
        raise ValueError(
            f"ConfigMem {config_mem_csv} does not have exactly one row per frame "
            f"index in 0..{max_frames_per_col - 1}: missing {missing}, "
            f"unexpected/duplicate {unexpected}."
        )
    return masks


def _master_config_mem_masks(
    composite: "Tile", frame_bits_per_row: int, max_frames_per_col: int
) -> dict[int, str]:
    """Return the frame masks the composite's master sub-tile occupies itself.

    The master's ConfigMem is generated when it is missing, so the composite can
    be generated on its own. A master with no config bits of its own has no
    ConfigMem file at all and leaves every slot free.

    Parameters
    ----------
    composite : Tile
        The composite tile whose master sub-tile is inspected.
    frame_bits_per_row : int
        Number of bits per frame row.
    max_frames_per_col : int
        Number of frames per column.

    Raises
    ------
    ValueError
        If the master sub-tile's `tile_dir` is unset (the default empty
        `Path()`), which would otherwise silently resolve to the current
        working directory.
    FileNotFoundError
        If the master sub-tile's directory does not exist, which would otherwise
        read as an all-free frame space and silently collide.

    Returns
    -------
    dict[int, str]
        Mapping from frame index to the master's own `used_bits_mask`.
    """
    master = composite.get_master_tile()
    if master.tile_dir == Path():
        raise ValueError(
            f"Master sub-tile '{master.name}' of composite '{composite.name}' has "
            "an unset tile_dir (the default empty Path()). Path().is_dir() resolves "
            "to the current working directory, so this would otherwise silently "
            "read (or write) the wrong ConfigMem file. Set tile_dir on the master "
            "tile before generating the composite ConfigMem."
        )
    # `tile_dir` is the tile's CSV file for a parsed tile, but its directory for
    # a tile built in memory.
    master_dir = master.tile_dir if master.tile_dir.is_dir() else master.tile_dir.parent
    if not master_dir.is_dir():
        raise FileNotFoundError(
            f"Master sub-tile '{master.name}' of composite '{composite.name}' has no "
            f"directory at {master_dir}, so its used config bits cannot be read. "
            "Generate the master tile before the composite."
        )

    master_config_mem_csv = master_dir / f"{master.name}_ConfigMem.csv"
    if not master_config_mem_csv.exists():
        if master.total_config_bits == 0:
            logger.info(
                f"Master sub-tile {master.name} has no config bits of its own; "
                f"the whole frame space is free for composite {composite.name}"
            )
            return {i: "0" * frame_bits_per_row for i in range(max_frames_per_col)}
        logger.info(
            f"{master_config_mem_csv} does not exist; generating the master "
            f"ConfigMem before allocating the bits of composite {composite.name}"
        )
        generateConfigMemInit(
            master_config_mem_csv,
            master.total_config_bits,
            frame_bits_per_row=frame_bits_per_row,
            max_frame_per_col=max_frames_per_col,
        )

    return _read_config_mem_masks(master_config_mem_csv, max_frames_per_col)


def _validate_composite_config_mem(
    composite_config_mem_csv: Path,
    master_masks: dict[int, str],
    num_bits_needed: int,
    max_frames_per_col: int,
) -> None:
    """Validate an existing composite ConfigMem against the master's frame usage.

    A composite ConfigMem reuses the FREE bit slots of its master sub-tile's frame
    space. Reusing an existing file is only safe if it still matches the current
    wrapper bit count and does not overlap any bit the master uses itself.

    Parameters
    ----------
    composite_config_mem_csv : Path
        Path to the existing composite `*_ConfigMem.csv` to validate.
    master_masks : dict[int, str]
        The master sub-tile's own `{frame_index: used_bits_mask}` mapping,
        covering exactly `0..max_frames_per_col - 1`.
    num_bits_needed : int
        Number of wrapper configuration bits that must be present.
    max_frames_per_col : int
        Number of frames per column.

    Raises
    ------
    ValueError
        If the file has the wrong row count, does not use exactly
        `num_bits_needed` bits, or any frame bit is used by both ConfigMems.
    """
    composite_masks = _read_config_mem_masks(
        composite_config_mem_csv, max_frames_per_col
    )

    used_bits = sum(mask.count("1") for mask in composite_masks.values())
    if used_bits != num_bits_needed:
        raise ValueError(
            f"Composite ConfigMem {composite_config_mem_csv} uses {used_bits} config "
            f"bits but the composite wrapper needs {num_bits_needed}. Delete the file "
            "and re-run tile generation to reallocate the wrapper bits."
        )

    for frame_idx, composite_mask in composite_masks.items():
        master_mask = master_masks[frame_idx]
        conflicts = [
            k
            for k, (a, b) in enumerate(zip(composite_mask, master_mask, strict=True))
            if a == "1" and b == "1"
        ]
        if conflicts:
            raise ValueError(
                f"Composite ConfigMem {composite_config_mem_csv} conflicts with the "
                f"master sub-tile ConfigMem in frame {frame_idx} at bit position(s) "
                f"{conflicts}: both drive the same physical config bit. Delete the "
                "file and re-run tile generation to reallocate the wrapper bits into "
                "the master's free slots."
            )


def _build_composite_config_mem_csv(
    master_masks: dict[int, str],
    num_bits_needed: int,
    output_path: Path,
    frame_bits_per_row: int,
    max_frames_per_col: int,
) -> None:
    """Build a composite ConfigMem CSV from the master sub-tile's free slots.

    Collects the bit positions where the master's `used_bits_mask` is `'0'`
    (free) and writes a CSV mapping the wrapper's config bits `0..n-1` onto them,
    in frame order. The output has exactly `max_frames_per_col` rows so it is
    accepted by `parseConfigMem`.

    Parameters
    ----------
    master_masks : dict[int, str]
        The master sub-tile's own `{frame_index: used_bits_mask}` mapping,
        covering exactly `0..max_frames_per_col - 1`.
    num_bits_needed : int
        Number of wrapper configuration bits to place.
    output_path : Path
        Destination path for the generated composite ConfigMem CSV.
    frame_bits_per_row : int
        Number of bits per frame row.
    max_frames_per_col : int
        Number of frames per column.

    Raises
    ------
    ValueError
        If there are fewer free slots than `num_bits_needed`.
    """
    # bit_k is the left-to-right index in the mask string (0 = MSB).
    free_slots: list[tuple[int, int]] = []
    for frame_idx in range(max_frames_per_col):
        mask = master_masks[frame_idx]
        for k, bit in enumerate(mask):
            if bit == "0":
                free_slots.append((frame_idx, k))

    if len(free_slots) < num_bits_needed:
        raise ValueError(
            f"Not enough free config bit slots in the master sub-tile's frame space: "
            f"need {num_bits_needed}, found only {len(free_slots)} free slots."
        )

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
        for frame_idx in range(max_frames_per_col):
            assignments = sorted(frame_assignments.get(frame_idx, []))
            mask_list = ["0"] * frame_bits_per_row
            for bit_k, _ in assignments:
                mask_list[bit_k] = "1"
            mask_str = "_".join(
                "".join(mask_list[i : i + 4]) for i in range(0, frame_bits_per_row, 4)
            )
            config_bits_ranges = (
                ";".join(str(cb_idx) for _, cb_idx in assignments)
                if assignments
                else "# NULL"
            )
            writer.writerow(
                [
                    f"frame{frame_idx}",
                    frame_idx,
                    len(assignments),
                    mask_str,
                    config_bits_ranges,
                ]
            )


def generate_composite_config_mem(
    writer: CodeGenerator,
    composite: "Tile",
    config_mem_csv: Path,
    frame_bits_per_row: int = 32,
    max_frame_per_col: int = 20,
) -> None:
    """Generate the ConfigMem of a composite tile's wrapper.

    A composite's wrapper config bits physically live in its master sub-tile's
    frame column, so they must be placed in the slots the master leaves free
    rather than packed from frame 0 bit 0 the way a leaf tile's are. An existing
    composite ConfigMem is validated against the master and reused, so a
    hand-tuned mapping survives regeneration but a stale one fails here instead
    of at bitstream-spec time.

    Parameters
    ----------
    writer : CodeGenerator
        The code generator instance for RTL output.
    composite : Tile
        The composite tile whose wrapper ConfigMem is generated.
    config_mem_csv : Path
        Path of the composite's `*_ConfigMem.csv`.
    frame_bits_per_row : int
        The number of configuration bits per frame row.
    max_frame_per_col : int
        The number of frames stored per tile column.
    """
    config_bits = composite.total_config_bits
    if config_bits > 0:
        master_masks = _master_config_mem_masks(
            composite, frame_bits_per_row, max_frame_per_col
        )
        if config_mem_csv.exists():
            _validate_composite_config_mem(
                config_mem_csv,
                master_masks,
                config_bits,
                max_frame_per_col,
            )
        else:
            logger.info(
                f"Allocating {config_bits} config bits of composite {composite.name} "
                "into the free slots of its master sub-tile"
            )
            _build_composite_config_mem_csv(
                master_masks,
                config_bits,
                config_mem_csv,
                frame_bits_per_row,
                max_frame_per_col,
            )

    generateConfigMem(
        writer,
        composite.name,
        config_bits,
        config_mem_csv,
        frame_bits_per_row=frame_bits_per_row,
        max_frame_per_col=max_frame_per_col,
    )

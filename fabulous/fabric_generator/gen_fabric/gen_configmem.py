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

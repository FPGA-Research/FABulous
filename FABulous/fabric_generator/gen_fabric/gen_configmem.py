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

from FABulous.fabric_definition.define import IO
from FABulous.fabric_definition.Fabric import Fabric
from FABulous.fabric_definition.Tile import Tile
from FABulous.fabric_generator.code_generator.code_generator import CodeGenerator
from FABulous.fabric_generator.code_generator.code_generator_Verilog import (
    VerilogCodeGenerator,
)
from FABulous.fabric_generator.parser.parse_configmem import parseConfigMem

if TYPE_CHECKING:
    from FABulous.fabric_definition.ConfigMem import ConfigMem


def generateConfigMemInit(fabric: Fabric, file: Path, tileConfigBitsCount: int) -> None:
    """Generate the config memory initialization file.

    The amount of configuration bits is determined
    by the `frameBitsPerRow` attribute of the fabric. The function will pack the
    configuration bit from the highest to the lowest bit in the config memory. I. e. if
    there are 100 configuration bits, with 32 frame bits per row, the function will pack
    from bit 99 starting from bit 31 of frame 0 to bit 28 of frame 3.

    Parameters
    ----------
    fabric : Fabric
        The fabric object containing fabric configuration
    file : Path
        The output file of the config memory initialization file.
    tileConfigBitsCount : int
        The number of tile config bits of the tile.

    Raises
    ------
    ValueError
        If the tile config bits exceed the fabric capacity.
    """
    if tileConfigBitsCount > fabric.frameBitsPerRow * fabric.maxFramesPerCol:
        raise ValueError(
            f"Tile config bits ({tileConfigBitsCount}) exceed fabric capacity "
            f"({fabric.frameBitsPerRow * fabric.maxFramesPerCol} bits). "
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
        bits = bitarray(fabric.frameBitsPerRow * fabric.maxFramesPerCol)
        bits[:tileConfigBitsCount] = 1

        # adjust for zero-based indexing in subsequent calculations
        tileConfigBitsCount -= 1

        count = 0
        for k in range(fabric.maxFramesPerCol):
            entry = {}
            # frame0, frame1, ...
            entry["frame_name"] = f"frame{k}"
            # and the index (0, 1, 2, ...), in case we need
            entry["frame_index"] = str(k)
            bitSlice = bits[count : count + fabric.frameBitsPerRow]
            entry["bits_used_in_frame"] = bitSlice.count(1)
            entry["used_bits_mask"] = bitSlice.to01(group=4, sep="_")
            if bitSlice.count(1) == 0:
                entry["ConfigBits_ranges"] = "# NULL"
            else:
                entry["ConfigBits_ranges"] = (
                    f"{tileConfigBitsCount}:"
                    f"{max(tileConfigBitsCount - fabric.frameBitsPerRow + 1, 0)}"
                )
            count += fabric.frameBitsPerRow
            tileConfigBitsCount -= fabric.frameBitsPerRow

            writer.writerow([entry[field] for field in fieldName])


def generateConfigMem(
    writer: CodeGenerator, fabric: Fabric, tile: Tile, configMemCsv: Path
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
    fabric : Fabric
        The fabric object containing fabric configuration
    tile : Tile
        A tile object.
    configMemCsv : Path
        The directory of the config memory CSV file.

    Raises
    ------
    ValueError
        - If the tile config bits exceed the fabric capacity.
        - If the total config bits in the config memory CSV file does not match
          the tile's global config bits.
    """
    # test if we have a bitstream mapping file
    # if not, we will take the default, which was passed on from  GenerateConfigMemInit
    if tile.globalConfigBits > fabric.frameBitsPerRow * fabric.maxFramesPerCol:
        raise ValueError(
            f"Tile {tile.name} has {tile.globalConfigBits} global config bits, "
            " which exceeds fabric capacity "
            f"({fabric.frameBitsPerRow * fabric.maxFramesPerCol} bits). "
            "Please adjust the tile configuration."
        )

    configMemList: list[ConfigMem] = []
    if configMemCsv.exists():
        if tile.globalConfigBits <= 0:
            logger.warning(
                f"Found bitstream mapping file {tile.name}_configMem.csv for tile "
                f"{tile.name}, but no global config bits are defined"
            )
        else:
            logger.info(
                f"Found bitstream mapping file {tile.name}_configMem.csv for tile "
                f"{tile.name}"
            )
        logger.info(f"Parsing {tile.name}_configMem.csv")
        configMemList = parseConfigMem(
            configMemCsv,
            fabric.maxFramesPerCol,
            fabric.frameBitsPerRow,
            tile.globalConfigBits,
        )
    elif tile.globalConfigBits > 0:
        logger.info(f"{tile.name}_configMem.csv does not exist")
        logger.info(f"Generating a default configMem for {tile.name}")
        generateConfigMemInit(fabric, configMemCsv, tile.globalConfigBits)
        logger.info(f"Parsing {tile.name}_configMem.csv")
        configMemList = parseConfigMem(
            configMemCsv,
            fabric.maxFramesPerCol,
            fabric.frameBitsPerRow,
            tile.globalConfigBits,
        )
    else:
        logger.info(
            f"No config bits defined and no bitstream mapping file provided for "
            f"tile {tile.name}"
        )
        return

    totalConfigBits = sum(i.bitsUsedInFrame for i in configMemList)
    logger.info(
        f"Found {len(configMemList)} config memory entries in "
        f"{tile.name}_configMem.csv with a total of {totalConfigBits} bits"
    )
    logger.info(f"Tile {tile.name} has {tile.globalConfigBits} global config bits")

    if totalConfigBits != tile.globalConfigBits:
        raise ValueError(
            f"Total config bits in {tile.name}_configMem.csv ({totalConfigBits}) "
            f"does not match tile global config bits ({tile.globalConfigBits})"
        )

    # start writing the file
    logger.info(f"Generating {writer.outFileName} for tile {tile.name}")
    writer.addHeader(f"{tile.name}_ConfigMem")
    writer.addParameterStart(indentLevel=1)
    if isinstance(writer, VerilogCodeGenerator):  # emulation only in Verilog
        maxBits = fabric.frameBitsPerRow * fabric.maxFramesPerCol
        writer.addPreprocIfDef("EMULATION")
        writer.addParameter(
            "Emulate_Bitstream",
            f"[{maxBits - 1}:0]",
            f"{maxBits}'b0",
            indentLevel=2,
        )
        writer.addPreprocEndif()
    if fabric.maxFramesPerCol != 0:
        writer.addParameter(
            "MaxFramesPerCol", "integer", fabric.maxFramesPerCol, indentLevel=2
        )
    if fabric.frameBitsPerRow != 0:
        writer.addParameter(
            "FrameBitsPerRow", "integer", fabric.frameBitsPerRow, indentLevel=2
        )
    writer.addParameter("NoConfigBits", "integer", tile.globalConfigBits, indentLevel=2)
    writer.addParameterEnd(indentLevel=1)
    writer.addPortStart(indentLevel=1)
    # the port definitions are generic
    writer.addPortVector("FrameData", IO.INPUT, "FrameBitsPerRow - 1", indentLevel=2)
    writer.addPortVector("FrameStrobe", IO.INPUT, "MaxFramesPerCol - 1", indentLevel=2)
    writer.addPortVector("ConfigBits", IO.OUTPUT, "NoConfigBits - 1", indentLevel=2)
    writer.addPortVector("ConfigBits_N", IO.OUTPUT, "NoConfigBits - 1", indentLevel=2)
    writer.addPortEnd(indentLevel=1)
    writer.addHeaderEnd(f"{tile.name}_ConfigMem")
    writer.addNewLine()
    # declare architecture
    writer.addDesignDescriptionStart(f"{tile.name}_ConfigMem")

    if isinstance(writer, VerilogCodeGenerator):  # emulation only in Verilog
        writer.addPreprocIfDef("EMULATION")
        for i in configMemList:
            counter = 0
            for k in range(fabric.frameBitsPerRow):
                # Safely check if bit is set, treat missing bits as '0'
                bit_value = i.usedBitMask[k] if k < len(i.usedBitMask) else "0"
                if bit_value == "1":
                    index = i.frameIndex * fabric.frameBitsPerRow + (
                        fabric.frameBitsPerRow - 1 - k
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
        for k in range(fabric.frameBitsPerRow):
            # Safely check if bit is set, treat missing bits as '0'
            bit_value = i.usedBitMask[k] if k < len(i.usedBitMask) else "0"
            if bit_value == "1":
                writer.addInstantiation(
                    compName="LHQD1",
                    compInsName=(
                        f"Inst_{i.frameName}_bit{fabric.frameBitsPerRow - 1 - k}"
                    ),
                    portsPairs=[
                        ("D", f"FrameData[{fabric.frameBitsPerRow - 1 - k}]"),
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

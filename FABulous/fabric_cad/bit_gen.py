#!/usr/bin/env python

"""Bitstream generation utilities for FABulous FPGA fabrics.

This module provides functionality for generating bitstreams from FASM (FPGA Assembly)
files for FABulous FPGA fabrics. It handles the conversion of place-and-route results
into configuration bitstreams that can be loaded onto the FPGA fabric.

The module includes functions for parsing FASM files, processing configuration bits, and
generating the final bitstream output in various formats.
"""

import pickle
import re
import sys
from pathlib import Path

from loguru import logger

from FABulous.custom_exception import SpecMissMatch

try:
    from fasm import (
        fasm_tuple_to_string,
        parse_fasm_filename,
        parse_fasm_string,
        set_feature_to_str,
    )
except ImportError:
    logger.critical("Could not import fasm. Bitstream generation not supported.")


def bitstring_to_bytes(s: str) -> bytes:
    """Convert binary string to bytes.

    Parameters
    ----------
    s : str
        Binary string (e.g., '10110101')

    Returns
    -------
    bytes
        Byte representation of the binary string
    """
    return int(s, 2).to_bytes((len(s) + 7) // 8, byteorder="big")


def genBitstream(fasmFile: str, specFile: str, bitstreamFile: str) -> None:
    """
    Generate the bitstream from the FASM file using the bitstream specification.

    ----------
    fasmFile : str
        Path to FASM file containing configuration features
    specFile : str
        Path to pickle file containing bitstream specification
    bitstreamFile : str
        Output path for generated bitstream file
    """
    lGen = parse_fasm_filename(fasmFile)
    canonStr = fasm_tuple_to_string(lGen, True)
    canonList = list(parse_fasm_string(canonStr))

    with Path(specFile).open("rb") as f:
        specDict = pickle.load(f)
    tileDict = {}
    tileDict_No_Mask = {}

    FrameBitsPerRow = specDict["ArchSpecs"]["FrameBitsPerRow"]
    MaxFramesPerCol = specDict["ArchSpecs"]["MaxFramesPerCol"]

    # Change this so it has the actual right dimensions, initialised as
    # an empty bitstream
    for tile in specDict["TileMap"]:
        tileDict[tile] = [0] * (MaxFramesPerCol * FrameBitsPerRow)
        tileDict_No_Mask[tile] = [0] * (MaxFramesPerCol * FrameBitsPerRow)

    # NOTE: SOME OF THE FOLLOWING METHODS HAVE BEEN CHANGED DUE TO A MODIFIED BITSTREAM
    # SPEC FORMAT
    # Please bear in mind that the tilespecs are now mapped by
    # tile loc and not by cell type

    for line in canonList:
        if "CLK" in set_feature_to_str(line.set_feature):
            continue
        if line.set_feature:
            tileVals = set_feature_to_str(line.set_feature).split(".")
            tileLoc = tileVals[0]
            featureName = ".".join((tileVals[1], tileVals[2]))
            if tileLoc not in specDict["TileMap"]:
                raise SpecMissMatch(
                    f"Tile location {tileLoc} not found in the bitstream spec"
                )
            # Set the necessary bits high
            tileType = specDict["TileMap"][tileLoc]
            if featureName in specDict["TileSpecs"][tileLoc]:
                if specDict["TileSpecs"][tileLoc][featureName]:
                    for bitIndex in specDict["TileSpecs"][tileLoc][featureName]:
                        tileDict[tileLoc][bitIndex] = int(
                            specDict["TileSpecs"][tileLoc][featureName][bitIndex]
                        )
                    for bitIndex_No_Mask in specDict["TileSpecs_No_Mask"][tileLoc][
                        featureName
                    ]:
                        tileDict_No_Mask[tileLoc][bitIndex_No_Mask] = int(
                            specDict["TileSpecs_No_Mask"][tileLoc][featureName][
                                bitIndex_No_Mask
                            ]
                        )

            else:
                raise SpecMissMatch(
                    f"Tile type: {tileType}\n"
                    "with location {tileLoc} and \n"
                    f"Feature: {featureName}\n"
                    "found in fasm file was not found in the bitstream spec"
                )

    # Write output string and introduce mask
    coordsRE = re.compile(r"X(\d*)Y(\d*)")
    num_columns = 0
    num_rows = 0

    for tileKey in tileDict:
        coordsMatch = coordsRE.match(tileKey)
        num_columns = max(int(coordsMatch.group(1)) + 1, num_columns)
        num_rows = max(int(coordsMatch.group(2)) + 1, num_rows)
    outStr = ""
    bitStr = bytes.fromhex("00AAFF01000000010000000000000000FAB0FAB1")
    bit_array = [[b"" for x in range(20)] for y in range(num_columns)]

    verilog_str = ""
    vhdl_str = (
        "library IEEE;\nuse IEEE.STD_LOGIC_1164.ALL;\n\npackage emulate_bitstream is\n"
    )
    for tileKey in tileDict_No_Mask:
        if (
            specDict["TileMap"][tileKey] == "NULL"
            or len(specDict["FrameMap"][specDict["TileMap"][tileKey]]) == 0
        ):
            continue
        verilog_str += f"// {tileKey}, {specDict['TileMap'][tileKey]}\n"
        verilog_str += (
            f"`define Tile_{tileKey}_Emulate_Bitstream "
            f"{MaxFramesPerCol * FrameBitsPerRow}'b"
        )

        vhdl_str += f"--{tileKey}, {specDict['TileMap'][tileKey]}\n"
        vhdl_str += (
            f"constant Tile_{tileKey}_Emulate_Bitstream : std_logic_vector("
            f'{MaxFramesPerCol * FrameBitsPerRow}-1 downto 0) := "'
        )

        for i in range((MaxFramesPerCol * FrameBitsPerRow) - 1, -1, -1):
            verilog_str += str(tileDict_No_Mask[tileKey][i])
            vhdl_str += str(tileDict_No_Mask[tileKey][i])
        verilog_str += "\n"
        vhdl_str += '";\n'
    vhdl_str += "end package emulate_bitstream;"

    # Top/bottom rows have no bitstream content (hardcoded throughout fabulous)
    # reversed row order
    for y in range(num_rows - 2, 0, -1):
        for x in range(num_columns):
            tileKey = f"X{x}Y{y}"
            curStr = ",".join((tileKey, specDict["TileMap"][tileKey], str(x), str(y)))
            curStr += "\n"

            for frameIndex in range(MaxFramesPerCol):
                if specDict["TileMap"][tileKey] == "NULL":
                    frame_bit_row = "0" * FrameBitsPerRow
                else:
                    frame_bit_row = (
                        "".join(
                            map(
                                str,
                                (
                                    tileDict[tileKey][
                                        FrameBitsPerRow * frameIndex : (
                                            FrameBitsPerRow * frameIndex
                                        )
                                        + FrameBitsPerRow
                                    ]
                                ),
                            )
                        )
                    )[::-1]
                curStr += ",".join(
                    (
                        f"frame{frameIndex}",
                        str(frameIndex),
                        str(FrameBitsPerRow),
                        frame_bit_row,
                    )
                )
                curStr += "\n"

                bit_hex = bitstring_to_bytes(frame_bit_row)
                bit_array[x][frameIndex] += bit_hex

            outStr += curStr + "\n"

    for i in range(num_columns):
        for j in range(20):
            bin_temp = f"{i:05b}"[::-1]
            frame_select = ["0" for k in range(32)]

            for k in range(-5, 0, 1):
                frame_select[k] = bin_temp[k]
            frame_select[j] = "1"
            frame_select_temp = ("".join(frame_select))[::-1]

            bitStr += bitstring_to_bytes(frame_select_temp)
            bitStr += bit_array[i][j]

    # Add desync frame
    # 20th bit is desync flag
    bitStr += bytes.fromhex("00100000")

    # Note - format in output file is line by line:
    # Tile Loc, Tile Type, X, Y, bits...... \n
    # Each line is one tile
    # Write out bitstream CSV representation
    with Path(bitstreamFile.replace("bin", "csv")).open("w+") as f:
        f.write(outStr)
    # Write out HDL representations
    with Path(bitstreamFile.replace("bin", "vh")).open("w+") as f:
        f.write(verilog_str)
    with Path(bitstreamFile.replace("bin", "vhd")).open("w+") as f:
        f.write(vhdl_str)
    # Write out binary representation
    with Path(bitstreamFile).open("bw+") as f:
        f.write(bitStr)


#####################################################################################
# Main
#####################################################################################
def bit_gen() -> None:
    """Command-line entry point for bitstream generation.

    Parses command-line arguments and calls genBitstream to create bitstream files from
    FASM and specification inputs.
    """
    # Strip arguments
    caseProcessedArguments = list(map(lambda x: x.strip(), sys.argv))
    processedArguments = list(map(lambda x: x.lower(), caseProcessedArguments))
    flagRE = re.compile(r"-\S*")
    if "-genBitstream".lower() in str(sys.argv).lower():
        argIndex = processedArguments.index("-genBitstream".lower())
        if len(processedArguments) <= argIndex + 3:
            logger.error(
                "genBitstream expects three file names - the fasm file, the spec file "
                "and the output file"
            )
            raise ValueError
        if (
            flagRE.match(caseProcessedArguments[argIndex + 1])
            or flagRE.match(caseProcessedArguments[argIndex + 2])
            or flagRE.match(caseProcessedArguments[argIndex + 3])
        ):
            logger.error(
                "genBitstream expects three file names, but"
                " found a flag in the arguments: "
                f"{caseProcessedArguments[argIndex + 1]}, "
                f"{caseProcessedArguments[argIndex + 2]}, "
                f"{caseProcessedArguments[argIndex + 3]}"
            )
            raise ValueError

        FasmFileName = caseProcessedArguments[argIndex + 1]
        SpecFileName = caseProcessedArguments[argIndex + 2]
        OutFileName = caseProcessedArguments[argIndex + 3]

        genBitstream(FasmFileName, SpecFileName, OutFileName)

    if ("-help".lower() in str(sys.argv).lower()) or ("-h" in str(sys.argv).lower()):
        logger.info("Help:")
        logger.info("Options/Switches")
        logger.info(
            "  -genBitstream foo.fasm spec.txt bitstream.txt - generates a bitstream - "
            "the first file is the fasm file, the second is the bitstream spec and "
            "the third is the fasm file to write to"
        )


if __name__ == "__main__":
    bit_gen()

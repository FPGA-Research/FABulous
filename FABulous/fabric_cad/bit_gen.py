#!/usr/bin/env python

import pickle
import re
import sys

from loguru import logger
from fasm import *  # Remove this line if you do not have the fasm library installed and will not be generating a bitstream


def replace(string, substitutions):
    substrings = sorted(substitutions, key=len, reverse=True)
    regex = re.compile("|".join(map(re.escape, substrings)))
    return regex.sub(lambda match: substitutions[match.group(0)], string)


def bitstring_to_bytes(s):
    return int(s, 2).to_bytes((len(s) + 7) // 8, byteorder="big")


# CAD methods from summer vacation project 2020


# Method to generate bitstream in the output format - more detail at the end
def genBitstream(fasmFile: str, specFile: str, bitstreamFile: str):
    lGen = parse_fasm_filename(fasmFile)
    canonStr = fasm_tuple_to_string(lGen, True)
    canonList = list(parse_fasm_string(canonStr))

    specDict = pickle.load(open(specFile, "rb"))
    tileDict = {}
    tileDict_No_Mask = {}

    FrameBitsPerRow = specDict["ArchSpecs"]["FrameBitsPerRow"]
    MaxFramesPerCol = specDict["ArchSpecs"]["MaxFramesPerCol"]

    # Change this so it has the actual right dimensions, initialised as an empty bitstream
    for tile in specDict["TileMap"].keys():
        tileDict[tile] = [0] * (MaxFramesPerCol * FrameBitsPerRow)
        tileDict_No_Mask[tile] = [0] * (MaxFramesPerCol * FrameBitsPerRow)

    ###NOTE: SOME OF THE FOLLOWING METHODS HAVE BEEN CHANGED DUE TO A MODIFIED BITSTREAM SPEC FORMAT
    # Please bear in mind that the tilespecs are now mapped by tile loc and not by cell type

    for line in canonList:
        if "CLK" in set_feature_to_str(line.set_feature):
            continue
        if line.set_feature:
            tileVals = set_feature_to_str(line.set_feature).split(".")
            tileLoc = tileVals[0]
            featureName = ".".join((tileVals[1], tileVals[2]))
            if tileLoc not in specDict["TileMap"].keys():
                logger.critical("Tile found in fasm file not found in bitstream spec")
                raise Exception
            tileType = specDict["TileMap"][tileLoc]  # Set the necessary bits high
            if featureName in specDict["TileSpecs"][tileLoc].keys():
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
                # print(specDict["TileSpecs"][tileLoc].keys())
                print(tileType)
                print(tileLoc)
                print(featureName)
                logger.critical(
                    "Feature found in fasm file was not found in the bitstream spec"
                )
                raise Exception

    # Write output string and introduce mask
    coordsRE = re.compile("X(\d*)Y(\d*)")
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
        verilog_str += f"`define Tile_{tileKey}_Emulate_Bitstream {MaxFramesPerCol*FrameBitsPerRow}'b"

        vhdl_str += f"--{tileKey}, {specDict['TileMap'][tileKey]}\n"
        vhdl_str += f'constant Tile_{tileKey}_Emulate_Bitstream : std_logic_vector({MaxFramesPerCol*FrameBitsPerRow}-1 downto 0) := "'

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
            bitPos = 0

            for frameIndex in range(MaxFramesPerCol):
                # print (tileDict[tileKey]) #:FrameBitsPerRow*frameIndex
                if specDict["TileMap"][tileKey] == "NULL":
                    frame_bit_row = "0" * FrameBitsPerRow
                else:
                    frame_bit_row = (
                        "".join(
                            map(
                                str,
                                (
                                    tileDict[tileKey][
                                        FrameBitsPerRow
                                        * frameIndex : (FrameBitsPerRow * frameIndex)
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

            # concatenatedTileDict[tileKey] = curStr
            outStr += curStr + "\n"

    # print(num_columns)
    for i in range(num_columns):
        for j in range(20):
            bin_temp = f"{i:05b}"[::-1]
            frame_select = ["0" for k in range(32)]
            # bitStr += "X"+str(i)+", frame"+str(j)+"\n"

            for k in range(-5, 0, 1):
                frame_select[k] = bin_temp[k]
            frame_select[j] = "1"
            frame_select_temp = ("".join(frame_select))[::-1]

            bitStr += bitstring_to_bytes(frame_select_temp)
            bitStr += bit_array[i][j]

    # Note - format in output file is line by line:
    # Tile Loc, Tile Type, X, Y, bits...... \n
    # Each line is one tile
    # Write out bitstream CSV representation
    print(outStr, file=open(bitstreamFile.replace("bin", "csv"), "w+"))
    # Write out HDL representations
    print(verilog_str, file=open(bitstreamFile.replace("bin", "vh"), "w+"))
    print(vhdl_str, file=open(bitstreamFile.replace("bin", "vhd"), "w+"))
    # Write out binary representation
    with open(bitstreamFile, "bw+") as f:
        f.write(bitStr)


# This class represents individual tiles in the architecture
class Tile:
    tileType = ""
    bels = []
    wires = []
    atomicWires = []  # For storing single wires (to handle cascading and termination)
    pips = []
    belPorts = set()
    matrixFileName = ""
    pipMuxes_MapSourceToSinks = []
    pipMuxes_MapSinkToSources = []

    x = -1  # Init with negative values to ease debugging
    y = -1

    def __init__(self, inType):
        self.tileType = inType

    def genTileLoc(self, separate=False):
        if separate:
            return ("X" + str(self.x), "Y" + str(self.y))
        return "X" + str(self.x) + "Y" + str(self.y)


# This class represents the fabric as a whole
class Fabric:
    tiles = []
    height = 0
    width = 0
    cellTypes = []

    def __init__(self, inHeight, inWidth):
        self.width = inWidth
        self.height = inHeight

    def getTileByCoords(self, x: int, y: int):
        for row in self.tiles:
            for tile in row:
                if tile.x == x and tile.y == y:
                    return tile
        return None

    def getTileByLoc(self, loc: str):
        for row in self.tiles:
            for tile in row:
                if tile.genTileLoc == loc:
                    return tile
        return None

    def getTileAndWireByWireDest(self, loc: str, dest: str, jumps: bool = True):
        for row in self.tiles:
            for tile in row:
                for wire in tile.wires:
                    if not jumps:
                        if wire["direction"] == "JUMP":
                            continue
                    for i in range(int(wire["wire-count"])):
                        desty = tile.y + int(wire["yoffset"])
                        destx = tile.x + int(wire["xoffset"])
                        desttileLoc = f"X{destx}Y{desty}"

                        if (desttileLoc == loc) and (
                            wire["destination"] + str(i) == dest
                        ):
                            return (tile, wire, i)

        return None


#####################################################################################
# Main
#####################################################################################
def bit_gen():
    # Strip arguments
    caseProcessedArguments = list(map(lambda x: x.strip(), sys.argv))
    processedArguments = list(map(lambda x: x.lower(), caseProcessedArguments))
    flagRE = re.compile("-\S*")
    if "-genBitstream".lower() in str(sys.argv).lower():
        argIndex = processedArguments.index("-genBitstream".lower())
        if len(processedArguments) <= argIndex + 3:
            logger.error(
                "genBitstream expects three file names - the fasm file, the spec file and the output file"
            )
            raise ValueError
        elif (
            flagRE.match(caseProcessedArguments[argIndex + 1])
            or flagRE.match(caseProcessedArguments[argIndex + 2])
            or flagRE.match(caseProcessedArguments[argIndex + 3])
        ):
            logger.error(
                "genBitstream expects three file names, but found a flag in the arguments:"
                f" {caseProcessedArguments[argIndex + 1]}, {caseProcessedArguments[argIndex + 2]}, {caseProcessedArguments[argIndex + 3]}"
            )
            raise ValueError

        FasmFileName = caseProcessedArguments[argIndex + 1]
        SpecFileName = caseProcessedArguments[argIndex + 2]
        OutFileName = caseProcessedArguments[argIndex + 3]

        genBitstream(FasmFileName, SpecFileName, OutFileName)

    if ("-help".lower() in str(sys.argv).lower()) or ("-h" in str(sys.argv).lower()):
        print("")
        print("Options/Switches")
        print(
            "  -genBitstream foo.fasm spec.txt bitstream.txt - generates a bitstream - the first file is the fasm file, the second is the bitstream spec and the third is the fasm file to write to"
        )


if __name__ == "__main__":
    bit_gen()

"""Configuration memory parser for FABulous FPGA tiles.

This module parses configuration memory CSV files that define how configuration
bits are mapped to memory frames in frame-based configuration systems. It validates
the configuration data structure and creates ConfigMem objects for code generation.

The parser handles:
- Frame-based configuration bit mapping
- Bit mask validation for frame utilization
- Configuration bit range parsing (single bits, ranges, lists)
- Error checking for bit allocation conflicts
- Memory frame structure validation
"""

import csv
import re
from pathlib import Path

from FABulous.fabric_definition.ConfigMem import ConfigMem


def parseConfigMem(
    fileName: Path,
    maxFramePerCol: int,
    frameBitPerRow: int,
    globalConfigBits: int,
) -> list[ConfigMem]:
    """Parse the config memory CSV file into a list of ConfigMem objects.

    Parameters
    ----------
    fileName : Path
        Directory of the config memory CSV file
    maxFramePerCol : int
        Maximum number of frames per column
    frameBitPerRow : int
        Number of bits per row
    globalConfigBits : int
        Number of global config bits for the config memory

    Raises
    ------
    ValueError
        - Invalid amount of frame entries in the config memory CSV file
        - Too many values in bit mask
        - Length of bit mask does not match the number of frame bits per row
        - Bit mask does not have enough values matching the number of the
          given config bits
        - Repeated config bit entry in ':' separated format in config bit range
        - Repeated config bit entry in list format in config bit range
        - Invalid range entry in config bit range

    Returns
    -------
    list[ConfigMem]
        List of ConfigMem objects parsed from the config memory CSV file.
    """
    with fileName.absolute().open() as f:
        mappingFile = list(csv.DictReader(f))

        # remove the pretty print from used_bits_mask
        for i, _ in enumerate(mappingFile):
            mappingFile[i]["used_bits_mask"] = mappingFile[i]["used_bits_mask"].replace(
                "_", ""
            )

        # we should have as many lines as we have frames (=framePerCol)
        if len(mappingFile) != maxFramePerCol:
            raise ValueError(
                f"The bitstream mapping file has only {len(mappingFile)} entries "
                f"but MaxFramesPerCol is {maxFramePerCol}."
            )

        # we also check used_bits_mask (is a vector that is as long as a frame and
        # contains a '1' for a bit used and a '0' if not used (padded)
        usedBitsCounter = 0
        for entry in mappingFile:
            if entry["used_bits_mask"].count("1") > frameBitPerRow:
                raise ValueError(
                    f"bitstream mapping file {fileName} has to many 1-elements in "
                    f"bitmask for frame : {entry['frame_name']}"
                )
            if len(entry["used_bits_mask"]) != frameBitPerRow:
                raise ValueError(
                    f"bitstream mapping file {fileName} has has a too long or short "
                    f"bitmask for frame : {entry['frame_name']}"
                )
            usedBitsCounter += entry["used_bits_mask"].count("1")

        if usedBitsCounter != globalConfigBits:
            raise ValueError(
                f"bitstream mapping file {fileName} has a bitmask mismatch; "
                f"bitmask has in total {usedBitsCounter} 1-values for "
                f"{globalConfigBits} bits."
            )

        allConfigBitsOrder = []
        configMemEntry = []
        for entry in mappingFile:
            configBitsOrder = []
            entry["ConfigBits_ranges"] = (
                entry["ConfigBits_ranges"].replace(" ", "").replace("\t", "")
            )

            if ":" in entry["ConfigBits_ranges"]:
                left, right = re.split(":", entry["ConfigBits_ranges"])
                # check the order of the number, if right is smaller than left,
                # then we swap them
                left, right = int(left), int(right)
                if right < left:
                    left, right = right, left
                    numList = list(reversed(range(left, right + 1)))
                else:
                    numList = list(range(left, right + 1))

                for i in numList:
                    if i in allConfigBitsOrder:
                        raise ValueError(
                            f"Configuration bit index {i} already allocated in "
                            f"{fileName}, {entry['frame_name']}."
                        )
                    configBitsOrder.append(i)

            elif ";" in entry["ConfigBits_ranges"]:
                for item in entry["ConfigBits_ranges"].split(";"):
                    if int(item) in allConfigBitsOrder:
                        raise ValueError(
                            f"Configuration bit index {item} already allocated in "
                            f"{fileName}, {entry['frame_name']}."
                        )
                    configBitsOrder.append(int(item))
            elif entry["ConfigBits_ranges"].isdigit():
                v = int(entry["ConfigBits_ranges"])
                if v in allConfigBitsOrder:
                    raise ValueError(
                        f"Configuration bit index {v} already allocated in "
                        f"{fileName}, {entry['frame_name']}."
                    )
                configBitsOrder.append(v)

            elif "NULL" in entry["ConfigBits_ranges"]:
                continue

            else:
                raise ValueError(
                    f"Range {entry['ConfigBits_ranges']} is not a valid format. "
                    "It should be in the form [int]:[int] or [int]. "
                    "If there are multiple ranges it should be separated by ';'."
                )

            if len(configBitsOrder) != entry["used_bits_mask"].count("1"):
                raise ValueError(
                    f"bitstream mapping file {fileName} has a mismatch between the "
                    f"number of bits used in the frame "
                    f"({entry['used_bits_mask'].count('1')}) and the number of "
                    f"config bits in the range({len(configBitsOrder)}) "
                    f"for frame {entry['frame_name']}."
                )
            if any([i < 0 for i in configBitsOrder]):
                raise ValueError(
                    f"Configuration bit index {configBitsOrder} in {fileName},"
                    f"{entry['frame_name']} is negative."
                )

            allConfigBitsOrder += configBitsOrder

            if entry["used_bits_mask"].count("1") > 0:
                configMemEntry.append(
                    ConfigMem(
                        frameName=entry["frame_name"],
                        frameIndex=int(entry["frame_index"]),
                        bitsUsedInFrame=entry["used_bits_mask"].count("1"),
                        usedBitMask=entry["used_bits_mask"],
                        configBitRanges=configBitsOrder,
                    )
                )

    return configMemEntry

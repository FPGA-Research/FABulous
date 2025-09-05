"""Bitstream specification generation module.

This module provides functionality to generate bitstream specifications from FPGA fabric
definitions. The specification defines how configuration bits map to physical frame
locations and is used during bitstream generation.
"""

import string
from typing import TYPE_CHECKING

from loguru import logger

from FABulous.fabric_definition.Fabric import Fabric
from FABulous.fabric_generator.parser.parse_configmem import parseConfigMem
from FABulous.fabric_generator.parser.parse_switchmatrix import parseMatrix
from FABulous.FABulous_settings import get_context

if TYPE_CHECKING:
    from FABulous.fabric_definition.ConfigMem import ConfigMem


def generateBitstreamSpec(fabric: Fabric) -> dict[str, dict]:
    """Generate the fabric's bitstream specification.

    This is needed to tell where each FASM configuration is mapped to the physical
    bitstream
    The result file will be further parsed by `bit_gen.py`.

    Parameters
    ----------
    fabric : Fabric
        The fabric object for generating the bitstream specification

    Returns
    -------
    dict[str, dict]
        The bits stream specification of the fabric.
    """
    specData = {
        "TileMap": {},
        "TileSpecs": {},
        "TileSpecs_No_Mask": {},
        "FrameMap": {},
        "FrameMapEncode": {},
        "ArchSpecs": {
            "MaxFramesPerCol": fabric.maxFramesPerCol,
            "FrameBitsPerRow": fabric.frameBitsPerRow,
        },
    }

    tileMap = {}
    for y, row in enumerate(fabric.tile):
        for x, tile in enumerate(row):
            if tile is not None:
                tileMap[f"X{x}Y{y}"] = tile.name
            else:
                tileMap[f"X{x}Y{y}"] = "NULL"

    specData["TileMap"] = tileMap
    configMemList: list[ConfigMem] = []
    for y, row in enumerate(fabric.tile):
        for x, tile in enumerate(row):
            if tile is None:
                continue
            if "fabric.csv" in str(tile.tileDir):
                # backward compatibility for old project structure
                # We need to take the matrixDir from the tile, since there
                # is the actual path to the tile defined in the fabric.csv
                if tile.matrixDir.is_file():
                    configMemPath = tile.matrixDir.parent / f"{tile.name}_ConfigMem.csv"
                elif tile.matrixDir.is_dir():
                    configMemPath = tile.matrixDir / f"{tile.name}_ConfigMem.csv"
                else:
                    configMemPath = (
                        get_context().proj_dir
                        / "Tile"
                        / tile.name
                        / f"{tile.name}_ConfigMem.csv"
                    )
                    logger.warning(
                        f"MatrixDir for {tile.name} is not a valid file or directory. "
                        f"Assuming default path: {configMemPath}"
                    )
            else:
                configMemPath = tile.tileDir.parent.joinpath(
                    f"{tile.name}_ConfigMem.csv"
                )
            logger.info(f"ConfigMemPath: {configMemPath}")

            if configMemPath.exists() and configMemPath.is_file():
                configMemList = parseConfigMem(
                    configMemPath,
                    fabric.maxFramesPerCol,
                    fabric.frameBitsPerRow,
                    tile.globalConfigBits,
                )
            elif tile.globalConfigBits > 0:
                logger.critical(
                    f"No ConfigMem csv file found for {tile.name} which "
                    "have config bits"
                )
                configMemList = []
            else:
                logger.info(f"No config memory for {tile.name}.")
                configMemList = []

            encodeDict = [-1] * (fabric.maxFramesPerCol * fabric.frameBitsPerRow)
            maskDic = {}
            for cfm in configMemList:
                maskDic[cfm.frameIndex] = cfm.usedBitMask
                # matching the value in the configBitRanges with the reversedBitMask
                # bit 0 in bit mask is the first value in the configBitRanges
                for i, char in enumerate(cfm.usedBitMask):
                    if char == "1":
                        encodeDict[cfm.configBitRanges.pop(0)] = (
                            fabric.frameBitsPerRow - 1 - i
                        ) + fabric.frameBitsPerRow * cfm.frameIndex

            # filling the maskDic with the unused frames
            for i in range(fabric.maxFramesPerCol - len(configMemList)):
                maskDic[len(configMemList) + i] = "0" * fabric.frameBitsPerRow

            specData["FrameMap"][tile.name] = maskDic
            if tile.globalConfigBits == 0:
                logger.info(f"No config memory for X{x}Y{y}_{tile.name}.")
                specData["FrameMap"][tile.name] = {}
                specData["FrameMapEncode"][tile.name] = {}

            curBitOffset = 0
            curTileMap = {}
            curTileMapNoMask = {}

            for i, bel in enumerate(tile.bels):
                for featureKey, keyDict in bel.belFeatureMap.items():
                    for entry in keyDict:
                        if isinstance(entry, int):
                            for v in keyDict[entry]:
                                curTileMap[
                                    f"{string.ascii_uppercase[i]}.{featureKey}"
                                ] = {encodeDict[curBitOffset + v]: keyDict[entry][v]}
                                curTileMapNoMask[
                                    f"{string.ascii_uppercase[i]}.{featureKey}"
                                ] = {encodeDict[curBitOffset + v]: keyDict[entry][v]}
                            curBitOffset += len(keyDict[entry])

            # All the generation will be working on the tile level with the tileDic
            # This is added to propagate the updated switch matrix to each of the tile
            # in the fabric
            if tile.matrixDir.suffix == ".list":
                tile.matrixDir = tile.matrixDir.with_suffix(".csv")

            result = parseMatrix(tile.matrixDir, tile.name)
            for source, sinkList in result.items():
                controlWidth = 0
                for i, sink in enumerate(reversed(sinkList)):
                    controlWidth = (len(sinkList) - 1).bit_length()
                    controlValue = f"{len(sinkList) - 1 - i:0{controlWidth}b}"
                    pip = f"{sink}.{source}"
                    if len(sinkList) < 2:
                        curTileMap[pip] = {}
                        curTileMapNoMask[pip] = {}
                        continue

                    for c, curChar in enumerate(controlValue[::-1]):
                        if pip not in curTileMap:
                            curTileMap[pip] = {}
                            curTileMapNoMask[pip] = {}

                        curTileMap[pip][encodeDict[curBitOffset + c]] = curChar
                        curTileMapNoMask[pip][encodeDict[curBitOffset + c]] = curChar

                curBitOffset += controlWidth

            # And now we add empty config bit mappings for immutable connections
            # (i.e. wires), as nextpnr sees these the same as normal pips
            for wire in tile.wireList:
                curTileMap[f"{wire.source}.{wire.destination}"] = {}
                curTileMapNoMask[f"{wire.source}.{wire.destination}"] = {}

            specData["TileSpecs"][f"X{x}Y{y}"] = curTileMap
            specData["TileSpecs_No_Mask"][f"X{x}Y{y}"] = curTileMapNoMask

    return specData

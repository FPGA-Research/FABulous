"""Bitstream specification generation module.

This module provides functionality to generate bitstream specifications from FPGA fabric
definitions. The specification defines how configuration bits map to physical frame
locations and is used during bitstream generation.
"""

import string
from importlib.metadata import version
from typing import TYPE_CHECKING

from loguru import logger

from fabulous.fabric_definition.fabric import Fabric
from fabulous.fabric_generator.parser.parse_configmem import parseConfigMem
from fabulous.fabric_generator.parser.parse_switchmatrix import parseList, parseMatrix
from fabulous.fabulous_settings import get_context

if TYPE_CHECKING:
    from fabulous.fabric_definition.configmem import ConfigMem


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
            "FrameSelectWidth": fabric.frameSelectWidth,
            "DesyncBit": fabric.desync_flag,
            "SyncHeaderHex": fabric.syncHeaderHex,
            "IncludeBorderRows": False,  # Currently not supported in FABulous
            "FABulousVersion": version("FABulous-FPGA"),
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

    # Supertile bitstream features. A supertile's config bits physically live in
    # its master tile's frame column (the master tile's own ConfigMem leaves those
    # bits free). Within the supertile config space the bit order is
    # [switch-matrix bits][BEL bits], matching genSuperTile()'s ST_ConfigBits
    # slicing. The BEL and switch-matrix features are added to the master tile's
    # TileSpecs entry alongside the master tile's own features.
    st_bel_count: dict[tuple[int, int], int] = {}
    for superTile in fabric.superTileDic.values():
        if not superTile.bels and superTile.supertile_matrix_dir is None:
            continue

        st_config_bits = superTile.total_config_bits

        st_encode_dict = [-1] * (fabric.maxFramesPerCol * fabric.frameBitsPerRow)
        st_mask_dic: dict[int, str] = {}
        if st_config_bits > 0:
            st_config_mem_list = parseConfigMem(
                superTile.tileDir.parent / f"{superTile.name}_ConfigMem.csv",
                fabric.maxFramesPerCol,
                fabric.frameBitsPerRow,
                st_config_bits,
            )
            for cfm in st_config_mem_list:
                st_mask_dic[cfm.frameIndex] = cfm.usedBitMask
                for i, char in enumerate(cfm.usedBitMask):
                    if char == "1":
                        st_encode_dict[cfm.configBitRanges.pop(0)] = (
                            fabric.frameBitsPerRow - 1 - i
                        ) + fabric.frameBitsPerRow * cfm.frameIndex

        sm_connections: dict[str, list[str]] = {}
        if superTile.supertile_matrix_dir is not None:
            mat_path = superTile.supertile_matrix_dir
            if mat_path.suffix == ".list":
                for dest, src in parseList(mat_path):
                    sm_connections.setdefault(dest, []).append(src)
            else:
                sm_connections = parseMatrix(mat_path, superTile.name)

        tx_local, ty_local = superTile.get_master_tile_coords()

        for base_fx, base_fy, _ in fabric.iter_super_tile_placements(superTile):
            ftx = base_fx + tx_local
            fty = base_fy + ty_local
            master_tile = fabric.tile[fty][ftx]

            frame_map = specData["FrameMap"].setdefault(master_tile.name, {})
            for frame_idx, mask in st_mask_dic.items():
                existing = frame_map.get(frame_idx, "0" * fabric.frameBitsPerRow)
                frame_map[frame_idx] = "".join(
                    "1" if a == "1" or b == "1" else "0"
                    for a, b in zip(existing, mask, strict=True)
                )

            curTileMap = specData["TileSpecs"].setdefault(f"X{ftx}Y{fty}", {})
            curTileMapNoMask = specData["TileSpecs_No_Mask"].setdefault(
                f"X{ftx}Y{fty}", {}
            )

            curBitOffset = 0
            for source, sinkList in sm_connections.items():
                controlWidth = (len(sinkList) - 1).bit_length()
                if st_config_bits == 0:
                    # No config bits — all connections are passthrough.
                    for sink in sinkList:
                        for t in (curTileMap, curTileMapNoMask):
                            t[f"{sink}.{source}"] = {}
                    continue
                for i, sink in enumerate(reversed(sinkList)):
                    pip = f"{sink}.{source}"
                    if len(sinkList) < 2:
                        for t in (curTileMap, curTileMapNoMask):
                            t[pip] = {}
                        continue
                    controlValue = f"{len(sinkList) - 1 - i:0{controlWidth}b}"
                    for c, curChar in enumerate(controlValue[::-1]):
                        for t in (curTileMap, curTileMapNoMask):
                            t.setdefault(pip, {})
                            t[pip][st_encode_dict[curBitOffset + c]] = curChar
                curBitOffset += controlWidth

            bel_coord = (ftx, fty)
            bel_offset = len(master_tile.bels) + st_bel_count.get(bel_coord, 0)
            for i, bel in enumerate(superTile.bels):
                letter = string.ascii_uppercase[bel_offset + i]
                for featureKey, keyDict in bel.belFeatureMap.items():
                    for entry in keyDict:
                        if not isinstance(entry, int):
                            continue
                        for v in keyDict[entry]:
                            for t in (curTileMap, curTileMapNoMask):
                                t[f"{letter}.{featureKey}"] = {
                                    st_encode_dict[curBitOffset + v]: keyDict[entry][v]
                                }
                        curBitOffset += len(keyDict[entry])
            st_bel_count[bel_coord] = bel_offset + len(superTile.bels)

    return specData

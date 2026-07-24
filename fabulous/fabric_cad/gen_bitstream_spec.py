"""Bitstream specification generation module.

This module provides functionality to generate bitstream specifications from FPGA fabric
definitions. The specification defines how configuration bits map to physical frame
locations and is used during bitstream generation.
"""

import string
from importlib.metadata import version
from pathlib import Path
from typing import TYPE_CHECKING

from loguru import logger

from fabulous.fabric_cad.gen_npnr_model import composite_master_fabric_coords
from fabulous.fabric_definition.fabric import Fabric
from fabulous.fabric_generator.parser.parse_configmem import parseConfigMem
from fabulous.fabulous_settings import get_context

if TYPE_CHECKING:
    from fabulous.fabric_definition.configmem import ConfigMem


def border_rows_have_config_bits(fabric: Fabric) -> bool:
    """Check whether the top or bottom fabric row holds any config bits.

    Parameters
    ----------
    fabric : Fabric
        The fabric object whose border rows are inspected.

    Returns
    -------
    bool
        True if any tile in the top or bottom row has configuration bits.
    """
    if not fabric.tile:
        return False

    border_rows = (fabric.tile[0], fabric.tile[-1])
    return any(
        tile is not None and tile.total_config_bits > 0
        for row in border_rows
        for tile in row
    )


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

    Raises
    ------
    ValueError
        If a composite tile's ConfigMem conflicts with its master tile's own
        ConfigMem (both drive the same physical config bit).
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
            "IncludeBorderRows": border_rows_have_config_bits(fabric),
            "MultiClkDomains": fabric.multiClkDomains,
            "FABulousVersion": version("FABulous-FPGA"),
        },
    }

    tile_map = {}
    for y, row in enumerate(fabric.tile):
        for x, tile in enumerate(row):
            if tile is not None:
                tile_map[f"X{x}Y{y}"] = tile.name
            else:
                tile_map[f"X{x}Y{y}"] = "NULL"

    specData["TileMap"] = tile_map
    configMemList: list[ConfigMem] = []
    for y, row in enumerate(fabric.tile):
        for x, tile in enumerate(row):
            if tile is None:
                continue
            if "fabric.csv" in str(tile.tile_dir):
                # backward compatibility for old project structure
                # We need to take the matrix_dir from the tile, since there
                # is the actual path to the tile defined in the fabric.csv
                if tile.matrix_dir.is_file():
                    configMemPath = (
                        tile.matrix_dir.parent / f"{tile.name}_ConfigMem.csv"
                    )
                elif tile.matrix_dir.is_dir():
                    configMemPath = tile.matrix_dir / f"{tile.name}_ConfigMem.csv"
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
                configMemPath = tile.tile_dir.parent.joinpath(
                    f"{tile.name}_ConfigMem.csv"
                )
            logger.info(f"ConfigMemPath: {configMemPath}")

            if configMemPath.exists() and configMemPath.is_file():
                configMemList = parseConfigMem(
                    configMemPath,
                    fabric.maxFramesPerCol,
                    fabric.frameBitsPerRow,
                    tile.total_config_bits,
                )
            elif tile.total_config_bits > 0:
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
            if tile.total_config_bits == 0:
                logger.info(f"No config memory for X{x}Y{y}_{tile.name}.")
                specData["FrameMap"][tile.name] = {}
                specData["FrameMapEncode"][tile.name] = {}

            curBitOffset = 0
            curTileMap = {}
            curTileMapNoMask = {}

            for i, bel in enumerate(tile.bels):
                for featureKey, keyDict in bel.bel_feature_map.items():
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

            # The switch matrix was parsed into muxes when the fabric was loaded.
            for mux in tile.switch_matrix.muxes:
                source = mux.output.name
                sinkList = [inp.name for inp in mux.inputs]
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
            for wire in tile.wire_list:
                curTileMap[f"{wire.source}.{wire.destination}"] = {}
                curTileMapNoMask[f"{wire.source}.{wire.destination}"] = {}

            specData["TileSpecs"][f"X{x}Y{y}"] = curTileMap
            specData["TileSpecs_No_Mask"][f"X{x}Y{y}"] = curTileMapNoMask

    # Composite bitstream features. A composite tile's config bits physically
    # live in its master cell's frame column (the master cell's own ConfigMem
    # leaves those bits free). Within the composite config space the bit order is
    # [switch-matrix bits][BEL bits], matching the composite ConfigMem layout. The
    # BEL and switch-matrix features are added to the master cell's TileSpecs entry
    # alongside the master cell's own features.
    st_bel_count: dict[tuple[int, int], int] = {}
    # Snapshot each tile type's own frame masks before any composite bits are
    # merged in, so the collision check below compares a composite against the
    # master's OWN config bits rather than bits a previous placement of the same
    # composite already merged (which would be a false positive).
    own_frame_masks = {
        name: dict(masks) for name, masks in specData["FrameMap"].items()
    }
    for composite in fabric.get_all_unique_tiles():
        if not composite.is_composite:
            continue
        if not composite.bels and composite.matrix_dir == Path():
            continue

        st_config_bits = composite.total_config_bits

        st_encode_dict = [-1] * (fabric.maxFramesPerCol * fabric.frameBitsPerRow)
        st_mask_dic: dict[int, str] = {}
        if st_config_bits > 0:
            st_config_mem_list = parseConfigMem(
                composite.tile_dir.parent / f"{composite.name}_ConfigMem.csv",
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

        for ftx, fty in composite_master_fabric_coords(fabric, composite):
            master_tile = fabric.tile[fty][ftx]

            frame_map = specData["FrameMap"].setdefault(master_tile.name, {})
            master_own_masks = own_frame_masks.get(master_tile.name, {})
            for frame_idx, mask in st_mask_dic.items():
                existing = frame_map.get(frame_idx, "0" * fabric.frameBitsPerRow)
                own = master_own_masks.get(frame_idx, "0" * fabric.frameBitsPerRow)
                conflicts = [
                    i
                    for i, (a, b) in enumerate(zip(own, mask, strict=True))
                    if a == "1" and b == "1"
                ]
                if conflicts:
                    raise ValueError(
                        f"Composite tile '{composite.name}' ConfigMem conflicts with "
                        f"the master tile '{master_tile.name}' own ConfigMem in frame "
                        f"{frame_idx} at bit position(s) {conflicts}: both drive the "
                        "same physical config bit. Delete the composite ConfigMem to "
                        "regenerate it."
                    )
                frame_map[frame_idx] = "".join(
                    "1" if a == "1" or b == "1" else "0"
                    for a, b in zip(existing, mask, strict=True)
                )

            curTileMap = specData["TileSpecs"].setdefault(f"X{ftx}Y{fty}", {})
            curTileMapNoMask = specData["TileSpecs_No_Mask"].setdefault(
                f"X{ftx}Y{fty}", {}
            )

            curBitOffset = 0
            for mux in composite.switch_matrix.muxes:
                source = mux.output.name
                sinkList = [inp.name for inp in mux.inputs]
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
            for i, bel in enumerate(composite.bels):
                letter = string.ascii_uppercase[bel_offset + i]
                for featureKey, keyDict in bel.bel_feature_map.items():
                    for entry in keyDict:
                        if not isinstance(entry, int):
                            continue
                        for v in keyDict[entry]:
                            for t in (curTileMap, curTileMapNoMask):
                                t[f"{letter}.{featureKey}"] = {
                                    st_encode_dict[curBitOffset + v]: keyDict[entry][v]
                                }
                        curBitOffset += len(keyDict[entry])
            st_bel_count[bel_coord] = bel_offset + len(composite.bels)

    return specData

"""Bitstream specification generation module.

This module provides functionality to generate bitstream specifications from FPGA fabric
definitions. The specification defines how configuration bits map to physical frame
locations and is used during bitstream generation.
"""

import string
from importlib.metadata import version

from loguru import logger

from fabulous.fabric_definition.fabric import Fabric


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
        tile is not None and tile.globalConfigBits > 0
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
    FileNotFoundError
        If a supertile with configuration bits has no configuration memory
        file yet.
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

    tileMap = {}
    for y, row in enumerate(fabric.tile):
        for x, tile in enumerate(row):
            if tile is not None:
                tileMap[f"X{x}Y{y}"] = tile.name
            else:
                tileMap[f"X{x}Y{y}"] = "NULL"

    specData["TileMap"] = tileMap
    for y, row in enumerate(fabric.tile):
        for x, tile in enumerate(row):
            if tile is None:
                continue
            logger.info(f"ConfigMemPath: {tile.config_mem_path}")
            memory = tile.config_mem
            if memory is not None:
                memory.validate(
                    frame_bits_per_row=fabric.frameBitsPerRow,
                    max_frames_per_col=fabric.maxFramesPerCol,
                    config_bits=tile.globalConfigBits,
                )
            elif tile.globalConfigBits > 0:
                logger.critical(
                    f"No ConfigMem csv file found for {tile.name} which "
                    "have config bits"
                )
            else:
                logger.info(f"No config memory for {tile.name}.")

            # The frame position of a bit is its data line within its frame.
            encodeDict = [-1] * (fabric.maxFramesPerCol * fabric.frameBitsPerRow)
            maskDic = {
                index: "0" * fabric.frameBitsPerRow
                for index in range(fabric.maxFramesPerCol)
            }
            if memory is not None:
                maskDic.update(
                    (frame.frameIndex, frame.usedBitMask) for frame in memory.frames
                )
                for crosspoint, bit in memory.bit_at.items():
                    encodeDict[bit] = (
                        crosspoint.data_bit + fabric.frameBitsPerRow * crosspoint.frame
                    )

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
                    for entry in (k for k in keyDict if isinstance(k, int)):
                        for v in keyDict[entry]:
                            curTileMap[f"{string.ascii_uppercase[i]}.{featureKey}"] = {
                                encodeDict[curBitOffset + v]: keyDict[entry][v]
                            }
                            curTileMapNoMask[
                                f"{string.ascii_uppercase[i]}.{featureKey}"
                            ] = {encodeDict[curBitOffset + v]: keyDict[entry][v]}
                        curBitOffset += len(keyDict[entry])

            result = tile.switch_matrix.connections
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
            for wire in fabric.wires.get((x, y), []):
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
    for super_tile in fabric.superTileDic.values():
        if not super_tile.bels and super_tile.supertile_matrix_dir is None:
            continue

        st_config_bits = super_tile.total_config_bits

        st_encode_dict = [-1] * (fabric.maxFramesPerCol * fabric.frameBitsPerRow)
        st_mask_dic: dict[int, str] = {}
        if st_config_bits > 0:
            st_memory = super_tile.config_mem
            if st_memory is None:
                raise FileNotFoundError(
                    f"Supertile {super_tile.name} has {st_config_bits} config bits "
                    f"but no configuration memory at {super_tile.config_mem_path}; "
                    "run gen_config_mem for it first."
                )
            st_memory.validate(
                frame_bits_per_row=fabric.frameBitsPerRow,
                max_frames_per_col=fabric.maxFramesPerCol,
                config_bits=st_config_bits,
            )
            st_mask_dic = {
                frame.frameIndex: frame.usedBitMask for frame in st_memory.used_frames
            }
            for crosspoint, bit in st_memory.bit_at.items():
                st_encode_dict[bit] = (
                    crosspoint.data_bit + fabric.frameBitsPerRow * crosspoint.frame
                )

        sm_connections: dict[str, list[str]] = {}
        if super_tile.switch_matrix is not None:
            sm_connections = super_tile.switch_matrix.connections

        tx_local, ty_local = super_tile.get_master_tile_coords()

        for base_fx, base_fy, _ in fabric.iter_super_tile_placements(super_tile):
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
            for i, bel in enumerate(super_tile.bels):
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
            st_bel_count[bel_coord] = bel_offset + len(super_tile.bels)

    return specData

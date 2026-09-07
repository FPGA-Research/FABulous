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
        If a tile's configuration memory holds a different number of bits than
        the tile has, which is what a missing mapping looks like.
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
            memory = tile.config_mem
            if memory.config_bits != tile.total_config_bits:
                raise ValueError(
                    f"{tile.name} holds {memory.config_bits} configuration bits "
                    f"in {memory} for {tile.total_config_bits} bits."
                )

            # The frame position of a bit is its data line within its frame.
            encodeDict = [-1] * (fabric.maxFramesPerCol * fabric.frameBitsPerRow)
            maskDic = {
                index: "0" * fabric.frameBitsPerRow
                for index in range(fabric.maxFramesPerCol)
            }
            maskDic.update(
                (frame.frame_index, frame.used_bits_mask.to01())
                for frame in memory.frames
            )
            for crosspoint, bit in memory.bit_at.items():
                encodeDict[bit] = (
                    crosspoint.data_bit + fabric.frameBitsPerRow * crosspoint.frame
                )

            specData["FrameMap"][tile.name] = maskDic
            if tile.total_config_bits == 0:
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

    # Composite bitstream features. A composite tile's config bits physically
    # live in its master cell's frame column (the master cell's own ConfigMem
    # leaves those bits free). Within the composite config space the bit order is
    # [switch-matrix bits][BEL bits], matching the composite ConfigMem layout. The
    # BEL and switch-matrix features are added to the master cell's TileSpecs entry
    # alongside the master cell's own features.
    st_bel_count: dict[tuple[int, int], int] = {}
    own_frame_masks = {
        name: dict(masks) for name, masks in specData["FrameMap"].items()
    }
    for composite in fabric.get_all_unique_tiles():
        if not composite.is_composite:
            continue
        if not composite.bels and composite.matrix_dir is None:
            continue

        st_config_bits = composite.total_config_bits

        st_encode_dict = [-1] * (fabric.maxFramesPerCol * fabric.frameBitsPerRow)
        st_mask_dic: dict[int, str] = {}
        if st_config_bits > 0:
            st_memory = composite.config_mem
            if st_memory.config_bits != st_config_bits:
                raise ValueError(
                    f"Composite {composite.name} has {st_config_bits} config bits "
                    f"but {st_memory} holds {st_memory.config_bits}; run "
                    "gen_config_mem for it first."
                )
            st_mask_dic = {
                frame.frame_index: frame.used_bits_mask.to01()
                for frame in st_memory.used_frames
            }
            for crosspoint, bit in st_memory.bit_at.items():
                st_encode_dict[bit] = (
                    crosspoint.data_bit + fabric.frameBitsPerRow * crosspoint.frame
                )

        for ftx, fty in fabric.composite_master_positions(composite):
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
                    composite_config_mem = (
                        composite.tile_dir.parent / f"{composite.name}_ConfigMem.csv"
                    )
                    raise ValueError(
                        f"Composite tile '{composite.name}' ConfigMem conflicts with "
                        f"the master tile '{master_tile.name}' own ConfigMem in frame "
                        f"{frame_idx} at bit position(s) {conflicts}: both drive the "
                        f"same physical config bit. Delete {composite_config_mem} and "
                        "re-run tile generation, which reallocates the wrapper bits "
                        "into the master's free slots."
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
            for source, sinkList in composite.switch_matrix.connections.items():
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
            st_bel_count[bel_coord] = bel_offset + len(composite.bels)

    return specData

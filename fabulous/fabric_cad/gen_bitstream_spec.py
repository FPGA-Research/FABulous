"""Bitstream specification generation module.

This module provides functionality to generate bitstream specifications from FPGA fabric
definitions. The specification defines how configuration bits map to physical frame
locations and is used during bitstream generation.
"""

import string
from importlib.metadata import version

from loguru import logger

from fabulous.fabric_definition.configmem import ConfigMem
from fabulous.fabric_definition.define import ConfigBitMode
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


def bit_positions(memory: ConfigMem, fabric: Fabric) -> list[int]:
    """Give the bitstream position of each configuration bit.

    A position is `data_bit + frame * FrameBitsPerRow`. Bits the memory does
    not hold keep -1, which `bit_gen` reads as unmapped.

    Parameters
    ----------
    memory : ConfigMem
        The mapping to read.
    fabric : Fabric
        The fabric whose frame grid the positions are counted over.

    Returns
    -------
    list[int]
        The position of every bit of the grid, indexed by configuration bit.
    """
    positions = [-1] * (fabric.maxFramesPerCol * fabric.frameBitsPerRow)
    for crosspoint, bit in memory.bit_at.items():
        positions[bit] = crosspoint.data_bit + fabric.frameBitsPerRow * crosspoint.frame
    return positions


def generate_bitstream_spec(fabric: Fabric) -> dict[str, dict]:
    """Generate the fabric's bitstream specification.

    This is needed to tell where each FASM configuration is mapped to the physical
    bitstream
    The result file will be further parsed by `bit_gen.py`.

    A FLIPFLOP_CHAIN fabric has no frames, so its specification carries only
    the tile map and the architecture parameters.

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
        If a tile's or supertile's configuration memory holds a different number
        of bits than it has, which is how an ungenerated mapping shows.
    """
    spec_data = {
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

    spec_data["TileMap"] = tile_map
    if fabric.configBitMode is not ConfigBitMode.FRAME_BASED:
        logger.warning(
            f"{fabric.name} shifts its configuration through a daisy chain, "
            "so its bitstream specification carries no frame map"
        )
        return spec_data

    for y, row in enumerate(fabric.tile):
        for x, tile in enumerate(row):
            if tile is None:
                continue
            if tile.globalConfigBits == 0:
                # Every pip of such a tile is single-sink, so no position is read.
                logger.info(f"No config memory for X{x}Y{y}_{tile.name}.")
                spec_data["FrameMap"][tile.name] = {}
                spec_data["FrameMapEncode"][tile.name] = {}
                positions = [-1] * (fabric.maxFramesPerCol * fabric.frameBitsPerRow)
            else:
                # Grid cells are deep copies; the memory lives on the tile type.
                memory = fabric.tileDic[tile.name].config_mem
                if memory.config_bits != tile.globalConfigBits:
                    raise ValueError(
                        f"{tile.name} holds {memory.config_bits} configuration "
                        f"bits in {memory} for {tile.globalConfigBits} bits."
                    )

                positions = bit_positions(memory, fabric)
                spec_data["FrameMap"][tile.name] = {
                    frame.frame_index: frame.used_bits_mask.to01()
                    for frame in memory.frames
                }

            bit_offset = 0
            tile_specs = {}
            tile_specs_no_mask = {}

            for i, bel in enumerate(tile.bels):
                for feature, feature_bits in bel.belFeatureMap.items():
                    for entry in (k for k in feature_bits if isinstance(k, int)):
                        for v in feature_bits[entry]:
                            tile_specs[f"{string.ascii_uppercase[i]}.{feature}"] = {
                                positions[bit_offset + v]: feature_bits[entry][v]
                            }
                            tile_specs_no_mask[
                                f"{string.ascii_uppercase[i]}.{feature}"
                            ] = {positions[bit_offset + v]: feature_bits[entry][v]}
                        bit_offset += len(feature_bits[entry])

            result = tile.switch_matrix.connections
            for source, sinks in result.items():
                control_width = 0
                for i, sink in enumerate(reversed(sinks)):
                    control_width = (len(sinks) - 1).bit_length()
                    control_value = f"{len(sinks) - 1 - i:0{control_width}b}"
                    pip = f"{sink}.{source}"
                    if len(sinks) < 2:
                        tile_specs[pip] = {}
                        tile_specs_no_mask[pip] = {}
                        continue

                    for c, char in enumerate(control_value[::-1]):
                        if pip not in tile_specs:
                            tile_specs[pip] = {}
                            tile_specs_no_mask[pip] = {}

                        tile_specs[pip][positions[bit_offset + c]] = char
                        tile_specs_no_mask[pip][positions[bit_offset + c]] = char

                bit_offset += control_width

            # And now we add empty config bit mappings for immutable connections
            # (i.e. wires), as nextpnr sees these the same as normal pips
            for wire in tile.wireList:
                tile_specs[f"{wire.source}.{wire.destination}"] = {}
                tile_specs_no_mask[f"{wire.source}.{wire.destination}"] = {}

            spec_data["TileSpecs"][f"X{x}Y{y}"] = tile_specs
            spec_data["TileSpecs_No_Mask"][f"X{x}Y{y}"] = tile_specs_no_mask

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

        st_positions = [-1] * (fabric.maxFramesPerCol * fabric.frameBitsPerRow)
        st_frame_map: dict[int, str] = {}
        if st_config_bits > 0:
            st_memory = super_tile.config_mem
            if st_memory is None:
                raise ValueError(
                    f"Supertile {super_tile.name} was built without a "
                    "configuration memory."
                )
            if st_memory.config_bits != st_config_bits:
                raise ValueError(
                    f"Supertile {super_tile.name} has {st_config_bits} config bits "
                    f"but {st_memory} holds {st_memory.config_bits}; run "
                    "gen_config_mem for it first."
                )
            st_frame_map = {
                frame.frame_index: frame.used_bits_mask.to01()
                for frame in st_memory.used_frames
            }
            st_positions = bit_positions(st_memory, fabric)

        sm_connections: dict[str, list[str]] = {}
        if super_tile.switch_matrix is not None:
            sm_connections = super_tile.switch_matrix.connections

        tx_local, ty_local = super_tile.get_master_tile_coords()

        for base_fx, base_fy, _ in fabric.iter_super_tile_placements(super_tile):
            ftx = base_fx + tx_local
            fty = base_fy + ty_local
            master_tile = fabric.tile[fty][ftx]

            frame_map = spec_data["FrameMap"].setdefault(master_tile.name, {})
            for frame_idx, mask in st_frame_map.items():
                existing = frame_map.get(frame_idx, "0" * fabric.frameBitsPerRow)
                frame_map[frame_idx] = "".join(
                    "1" if a == "1" or b == "1" else "0"
                    for a, b in zip(existing, mask, strict=True)
                )

            tile_specs = spec_data["TileSpecs"].setdefault(f"X{ftx}Y{fty}", {})
            tile_specs_no_mask = spec_data["TileSpecs_No_Mask"].setdefault(
                f"X{ftx}Y{fty}", {}
            )

            bit_offset = 0
            for source, sinks in sm_connections.items():
                control_width = (len(sinks) - 1).bit_length()
                if st_config_bits == 0:
                    # No config bits — all connections are passthrough.
                    for sink in sinks:
                        for t in (tile_specs, tile_specs_no_mask):
                            t[f"{sink}.{source}"] = {}
                    continue
                for i, sink in enumerate(reversed(sinks)):
                    pip = f"{sink}.{source}"
                    if len(sinks) < 2:
                        for t in (tile_specs, tile_specs_no_mask):
                            t[pip] = {}
                        continue
                    control_value = f"{len(sinks) - 1 - i:0{control_width}b}"
                    for c, char in enumerate(control_value[::-1]):
                        for t in (tile_specs, tile_specs_no_mask):
                            t.setdefault(pip, {})
                            t[pip][st_positions[bit_offset + c]] = char
                bit_offset += control_width

            bel_coord = (ftx, fty)
            bel_offset = len(master_tile.bels) + st_bel_count.get(bel_coord, 0)
            for i, bel in enumerate(super_tile.bels):
                letter = string.ascii_uppercase[bel_offset + i]
                for feature, feature_bits in bel.belFeatureMap.items():
                    for entry in feature_bits:
                        if not isinstance(entry, int):
                            continue
                        for v in feature_bits[entry]:
                            for t in (tile_specs, tile_specs_no_mask):
                                t[f"{letter}.{feature}"] = {
                                    st_positions[bit_offset + v]: feature_bits[entry][v]
                                }
                        bit_offset += len(feature_bits[entry])
            st_bel_count[bel_coord] = bel_offset + len(super_tile.bels)

    return spec_data

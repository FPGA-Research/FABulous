"""Fabric metadata export for machine-readable fabric inventory.

Builds a versioned, structured description of a fabric (geometry, config
architecture, tile/primitive counts, grid layout, bitstream size) and
optionally writes it as YAML and/or HDL constants.

The YAML document is the canonical form. Verilog headers, SystemVerilog
packages, and VHDL packages are derived views for firmware, testbenches, and
SoC integration.
"""

import re
from collections import Counter
from collections.abc import Iterable
from enum import StrEnum
from importlib.metadata import version
from pathlib import Path
from typing import TypedDict

import yaml
from jinja2 import Environment, PackageLoader, StrictUndefined
from loguru import logger

from fabulous.fabric_definition.fabric import Fabric

SCHEMA_VERSION = 1

# Frame-based bitstreams always end with a 32-bit DESYNC word (bit_gen).
_DESYNC_BYTES = 4
_WORD_BYTES = 4

# Same loader root as the tool script templates under fabulous/template.
_JINJA_ENV = Environment(
    loader=PackageLoader("fabulous", "template"),
    undefined=StrictUndefined,
    trim_blocks=True,
    lstrip_blocks=True,
    keep_trailing_newline=True,
)


class MetadataFormat(StrEnum):
    """Output formats for fabric metadata export."""

    YAML = "yaml"
    VERILOG = "verilog"
    SYSTEMVERILOG = "systemverilog"
    VHDL = "vhdl"


class BitstreamGeometry(TypedDict):
    """Layout sizes of a full frame-based bitstream."""

    header_bytes: int
    desync_bytes: int
    data_rows: int
    bytes_per_frame: int
    length_bytes: int
    length_words: int


class GeometryInfo(TypedDict):
    """Fabric grid dimensions."""

    columns: int
    rows: int


class ConfigurationInfo(TypedDict):
    """Configuration architecture and derived bitstream geometry."""

    mode: str
    frame_bits_per_row: int
    max_frames_per_col: int
    frame_select_width: int
    row_select_width: int
    desync_flag: int
    sync_header_hex: str
    multiplexer_style: str
    config_bits_capacity_per_column: int
    bitstream: BitstreamGeometry


class BelComposition(TypedDict):
    """BEL composition of a single tile type."""

    module: str
    count_per_tile: int
    config_bits: int
    src: str


class TileTypeInfo(TypedDict):
    """Inventory entry for one tile type."""

    count: int
    config_bits: int
    matrix_config_bits: int
    part_of_supertile: bool
    tile_dir: str
    switch_matrix: str
    bels: list[BelComposition]


class TilesSection(TypedDict):
    """Tile placement counts and per-type details."""

    counts: dict[str, int]
    types: dict[str, TileTypeInfo]


class PrimitiveInfo(TypedDict):
    """Fabric-wide inventory for one primitive (BEL module)."""

    count: int
    src: str


class PrimitivesSection(TypedDict):
    """Fabric-wide BEL/module instance counts and sources."""

    counts: dict[str, int]
    types: dict[str, PrimitiveInfo]


class SuperTileBelInfo(TypedDict):
    """BEL hosted on a supertile rather than a member tile."""

    module: str
    config_bits: int
    src: str


class SuperTileTypeInfo(TypedDict):
    """Inventory entry for one supertile type."""

    count: int
    width: int
    height: int
    member_tiles: list[str]
    tile_dir: str
    switch_matrix: str
    bels: list[SuperTileBelInfo]
    supertile_matrix_config_bits: int


class SuperTilesSection(TypedDict):
    """Supertile placement counts and per-type details."""

    counts: dict[str, int]
    types: dict[str, SuperTileTypeInfo]


class FabricMetadata(TypedDict):
    """Canonical fabric metadata document."""

    schema_version: int
    name: str
    fabulous_version: str
    fabric_csv: str
    geometry: GeometryInfo
    configuration: ConfigurationInfo
    tiles: TilesSection
    primitives: PrimitivesSection
    supertiles: SuperTilesSection
    grid: list[list[str]]


def compute_bitstream_geometry(fabric: Fabric) -> BitstreamGeometry:
    """Compute full frame-based bitstream layout sizes.

    Matches the layout produced by `FABulous_bit_gen.bit_gen.genBitstream`:
    sync header, then for every column and every frame a frame-select word
    plus one word per data-carrying fabric row (top and bottom border rows
    are excluded), then a trailing DESYNC word.

    Parameters
    ----------
    fabric : Fabric
        Fabric whose dimensions and frame parameters are used.

    Returns
    -------
    BitstreamGeometry
        Bitstream geometry fields (byte/word lengths and intermediate sizes).

    Raises
    ------
    ValueError
        If `frameBitsPerRow` is not a multiple of 8, or the computed length
        is not a multiple of 4 bytes.
    """
    header_bytes = len(bytes.fromhex(fabric.syncHeaderHex))
    # bit_gen iterates y from (num_rows - 2) down to 1 inclusive
    data_rows = max(fabric.numberOfRows - 2, 0)
    if fabric.frameBitsPerRow % 8 != 0:
        raise ValueError(
            f"frameBitsPerRow ({fabric.frameBitsPerRow}) must be a multiple of 8 "
            "to compute bitstream length in bytes"
        )
    # one frame-select word + one word per data row
    bytes_per_frame = _WORD_BYTES + data_rows * (fabric.frameBitsPerRow // 8)
    length_bytes = (
        header_bytes
        + fabric.numberOfColumns * fabric.maxFramesPerCol * bytes_per_frame
        + _DESYNC_BYTES
    )
    if length_bytes % _WORD_BYTES != 0:
        raise ValueError(
            f"Computed bitstream length ({length_bytes} bytes) is not a "
            "multiple of 4; cannot report length in 32-bit words"
        )
    return {
        "header_bytes": header_bytes,
        "desync_bytes": _DESYNC_BYTES,
        "data_rows": data_rows,
        "bytes_per_frame": bytes_per_frame,
        "length_bytes": length_bytes,
        "length_words": length_bytes // _WORD_BYTES,
    }


def _relative_path(path: Path, base: Path) -> str:
    """Return `path` relative to `base` as a forward-slash string.

    Parameters
    ----------
    path : Path
        Path to serialise. Empty paths become an empty string.
    base : Path
        Project root used for relativisation (parent of the fabric CSV).

    Returns
    -------
    str
        Path relative to `base` when possible, otherwise the absolute POSIX
        form. Empty input paths yield `""`.
    """
    if path is None or path == Path():
        return ""
    try:
        return path.resolve().relative_to(base.resolve()).as_posix()
    except (ValueError, OSError):
        return path.as_posix()


def build_fabric_metadata(fabric: Fabric) -> FabricMetadata:
    """Build a structured fabric metadata document.

    Paths in the document are relative to the project root (parent of the
    fabric CSV) when possible.

    Parameters
    ----------
    fabric : Fabric
        Loaded fabric model.

    Returns
    -------
    FabricMetadata
        Metadata document ready for serialisation (YAML) or HDL rendering.

    Raises
    ------
    ValueError
        If a tile name present in the grid is missing from the fabric tile
        dictionaries.
    """
    project_root = fabric.fabric_dir.parent
    tile_counts: Counter[str] = Counter()
    primitive_counts: Counter[str] = Counter()
    primitive_src: dict[str, str] = {}
    grid: list[list[str]] = []

    for y in range(fabric.numberOfRows):
        row_names: list[str] = []
        for x in range(fabric.numberOfColumns):
            tile = fabric.tile[y][x] if y < len(fabric.tile) else None
            if tile is None:
                name = "NULL"
            else:
                name = tile.name
                for bel in tile.bels:
                    key = bel.module_name or bel.name
                    primitive_counts[key] += 1
                    primitive_src.setdefault(key, _relative_path(bel.src, project_root))
            tile_counts[name] += 1
            row_names.append(name)
        grid.append(row_names)

    # One pass over supertile placements for counts and hosted BELs.
    super_tile_counts: Counter[str] = Counter()
    for _base_fx, _base_fy, super_tile in fabric.iter_super_tile_placements():
        super_tile_counts[super_tile.name] += 1
        for bel in super_tile.bels:
            key = bel.module_name or bel.name
            primitive_counts[key] += 1
            primitive_src.setdefault(key, _relative_path(bel.src, project_root))

    tile_types: dict[str, TileTypeInfo] = {}
    for tile_name, count in sorted(tile_counts.items()):
        if tile_name == "NULL":
            tile_types[tile_name] = {
                "count": count,
                "config_bits": 0,
                "matrix_config_bits": 0,
                "part_of_supertile": False,
                "tile_dir": "",
                "switch_matrix": "",
                "bels": [],
            }
            continue

        tile = fabric.tileDic.get(tile_name) or fabric.unusedTileDic.get(tile_name)
        if tile is None:
            raise ValueError(
                f"Tile type '{tile_name}' appears in the fabric grid but is "
                "missing from tileDic and unusedTileDic"
            )

        bel_counts: Counter[str] = Counter()
        bel_config: dict[str, int] = {}
        bel_src: dict[str, str] = {}
        for bel in tile.bels:
            key = bel.module_name or bel.name
            bel_counts[key] += 1
            bel_config[key] = bel.configBit
            bel_src.setdefault(key, _relative_path(bel.src, project_root))
        tile_types[tile_name] = {
            "count": count,
            "config_bits": tile.globalConfigBits,
            "matrix_config_bits": tile.matrixConfigBits,
            "part_of_supertile": tile.partOfSuperTile,
            "tile_dir": _relative_path(tile.tileDir, project_root),
            "switch_matrix": _relative_path(tile.matrixDir, project_root),
            "bels": [
                {
                    "module": module,
                    "count_per_tile": bel_counts[module],
                    "config_bits": bel_config[module],
                    "src": bel_src[module],
                }
                for module in sorted(bel_counts)
            ],
        }

    super_tile_types: dict[str, SuperTileTypeInfo] = {}
    for st_name, count in sorted(super_tile_counts.items()):
        st = fabric.superTileDic[st_name]
        matrix_path = st.supertile_matrix_dir
        super_tile_types[st_name] = {
            "count": count,
            "width": st.max_width,
            "height": st.max_height,
            "member_tiles": sorted({t.name for t in st.tiles if t is not None}),
            "tile_dir": _relative_path(st.tileDir, project_root),
            "switch_matrix": (
                _relative_path(matrix_path, project_root)
                if matrix_path is not None
                else ""
            ),
            "bels": [
                {
                    "module": bel.module_name,
                    "config_bits": bel.configBit,
                    "src": _relative_path(bel.src, project_root),
                }
                for bel in st.bels
            ],
            "supertile_matrix_config_bits": st.supertile_matrix_config_bits,
        }

    bitstream = compute_bitstream_geometry(fabric)
    return {
        "schema_version": SCHEMA_VERSION,
        "name": fabric.name,
        "fabulous_version": version("FABulous-FPGA"),
        "fabric_csv": _relative_path(fabric.fabric_dir, project_root),
        "geometry": {
            "columns": fabric.numberOfColumns,
            "rows": fabric.numberOfRows,
        },
        "configuration": {
            "mode": fabric.configBitMode.name,
            "frame_bits_per_row": fabric.frameBitsPerRow,
            "max_frames_per_col": fabric.maxFramesPerCol,
            "frame_select_width": fabric.frameSelectWidth,
            "row_select_width": fabric.rowSelectWidth,
            "desync_flag": fabric.desync_flag,
            "sync_header_hex": fabric.syncHeaderHex,
            "multiplexer_style": fabric.multiplexerStyle.name,
            "config_bits_capacity_per_column": (
                fabric.maxFramesPerCol * fabric.frameBitsPerRow
            ),
            "bitstream": bitstream,
        },
        "tiles": {
            "counts": dict(sorted(tile_counts.items())),
            "types": tile_types,
        },
        "primitives": {
            "counts": dict(sorted(primitive_counts.items())),
            "types": {
                name: {"count": primitive_counts[name], "src": primitive_src[name]}
                for name in sorted(primitive_counts)
            },
        },
        "supertiles": {
            "counts": dict(sorted(super_tile_counts.items())),
            "types": super_tile_types,
        },
        "grid": grid,
    }


def write_fabric_metadata(
    fabric: Fabric,
    output_dir: Path,
    formats: Iterable[MetadataFormat] | None = None,
    *,
    metadata: FabricMetadata | None = None,
) -> dict[MetadataFormat, Path]:
    """Write fabric metadata in the requested formats.

    Parameters
    ----------
    fabric : Fabric
        Fabric to describe.
    output_dir : Path
        Directory for output files (created if missing).
    formats : Iterable[MetadataFormat] | None, optional
        Subset of `MetadataFormat` values. Defaults to all formats.
    metadata : FabricMetadata | None, optional
        Pre-built metadata document. Built from `fabric` when omitted.

    Returns
    -------
    dict[MetadataFormat, Path]
        Mapping of format to written path.
    """
    requested = set(formats) if formats is not None else set(MetadataFormat)

    data = metadata if metadata is not None else build_fabric_metadata(fabric)
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    fabric_name = _sanitize_identifier(data["name"])
    written: dict[MetadataFormat, Path] = {}

    if MetadataFormat.YAML in requested:
        path = output_dir / "fabric_metadata.yaml"
        path.write_text(
            yaml.safe_dump(dict(data), sort_keys=False, default_flow_style=False),
            encoding="utf-8",
        )
        written[MetadataFormat.YAML] = path
        logger.info(f"Wrote fabric metadata ({MetadataFormat.YAML}): {path}")

    if MetadataFormat.VERILOG in requested:
        path = output_dir / f"{fabric_name}_defines.v"
        path.write_text(
            _render_hdl_template("fabric_metadata_defines.v.j2", data),
            encoding="utf-8",
        )
        written[MetadataFormat.VERILOG] = path
        logger.info(f"Wrote fabric metadata ({MetadataFormat.VERILOG}): {path}")

    if MetadataFormat.SYSTEMVERILOG in requested:
        path = output_dir / f"{fabric_name}_pkg.sv"
        path.write_text(
            _render_hdl_template("fabric_metadata_pkg.sv.j2", data),
            encoding="utf-8",
        )
        written[MetadataFormat.SYSTEMVERILOG] = path
        logger.info(f"Wrote fabric metadata ({MetadataFormat.SYSTEMVERILOG}): {path}")

    if MetadataFormat.VHDL in requested:
        path = output_dir / f"{fabric_name}_pkg.vhdl"
        path.write_text(
            _render_hdl_template("fabric_metadata_pkg.vhdl.j2", data),
            encoding="utf-8",
        )
        written[MetadataFormat.VHDL] = path
        logger.info(f"Wrote fabric metadata ({MetadataFormat.VHDL}): {path}")

    return written


def _render_hdl_template(template_name: str, metadata: FabricMetadata) -> str:
    """Render an HDL metadata template from `metadata`.

    Parameters
    ----------
    template_name : str
        Template file name under `fabulous/template`.
    metadata : FabricMetadata
        Document from `build_fabric_metadata`.

    Returns
    -------
    str
        Rendered template text.
    """
    geometry = metadata["geometry"]
    configuration = metadata["configuration"]
    bitstream = configuration["bitstream"]
    scalars = [
        ("FABRIC_COLUMNS", geometry["columns"]),
        ("FABRIC_ROWS", geometry["rows"]),
        ("FABRIC_FRAME_BITS_PER_ROW", configuration["frame_bits_per_row"]),
        ("FABRIC_MAX_FRAMES_PER_COL", configuration["max_frames_per_col"]),
        ("FABRIC_FRAME_SELECT_WIDTH", configuration["frame_select_width"]),
        ("FABRIC_ROW_SELECT_WIDTH", configuration["row_select_width"]),
        ("FABRIC_DESYNC_FLAG", configuration["desync_flag"]),
        (
            "FABRIC_CONFIG_BITS_CAPACITY_PER_COLUMN",
            configuration["config_bits_capacity_per_column"],
        ),
        ("FABRIC_BITSTREAM_LENGTH_BYTES", bitstream["length_bytes"]),
        ("FABRIC_BITSTREAM_LENGTH_WORDS", bitstream["length_words"]),
        ("FABRIC_BITSTREAM_HEADER_BYTES", bitstream["header_bytes"]),
        ("FABRIC_BITSTREAM_DESYNC_BYTES", bitstream["desync_bytes"]),
        ("FABRIC_BITSTREAM_DATA_ROWS", bitstream["data_rows"]),
        ("FABRIC_BITSTREAM_BYTES_PER_FRAME", bitstream["bytes_per_frame"]),
    ]
    tile_counts = [
        (_sanitize_identifier(name), count)
        for name, count in sorted(metadata["tiles"]["counts"].items())
    ]
    primitive_counts = [
        (_sanitize_identifier(name), count)
        for name, count in sorted(metadata["primitives"]["counts"].items())
    ]
    return _JINJA_ENV.get_template(template_name).render(
        name=metadata["name"],
        fabulous_version=metadata["fabulous_version"],
        schema_version=metadata["schema_version"],
        package_name=f"{_sanitize_identifier(metadata['name'])}_pkg",
        scalars=scalars,
        tile_counts=tile_counts,
        primitive_counts=primitive_counts,
    )


def _sanitize_identifier(name: str) -> str:
    """Turn an arbitrary name into a safe HDL / define identifier.

    Parameters
    ----------
    name : str
        Raw tile or primitive name.

    Returns
    -------
    str
        Identifier safe for Verilog defines, SystemVerilog parameters, and
        VHDL constants.
    """
    cleaned = re.sub(r"[^0-9A-Za-z_]", "_", name)
    cleaned = re.sub(r"_+", "_", cleaned).strip("_")
    if not cleaned:
        cleaned = "UNNAMED"
    if cleaned[0].isdigit():
        cleaned = f"N_{cleaned}"
    return cleaned

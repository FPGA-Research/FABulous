"""Fabric metadata export module.

Generate machine-readable summaries of a fabric's geometry, bitstream sizing
and per-tile inventory. The metadata is emitted in three formats so it can be
consumed by downstream tooling, HDL and software:

- YAML, the canonical, richly nested format. Each placed tile carries its
  switch-matrix path, BEL list (with prefix, module name, source RTL and
  config bits), and total config bits.
- Verilog ``define`` headers, exposing the scalar fabric parameters and per-
  tile / per-BEL counts as preprocessor macros.
- SystemVerilog packages, mirroring the Verilog header but as ``parameter``s
  in a named package suitable for ``import``.

Bitstream length matches the on-wire format produced by ``FABulous_bit_gen``:
a 20-byte sync header, followed for every (column, frame) pair by a 4-byte
``frame_select`` word and ``active_rows * (frame_bits_per_row / 8)`` bytes of
frame payload, terminated by a 4-byte desync word. ``active_rows`` excludes
the top and bottom termination rows that ``bit_gen`` skips. NULL slots inside
the active row range still contribute zeroed frame data because frames are
broadcast to every active row in their column.

Tile and BEL inventories iterate the placed grid and skip NULL slots, so they
are accurate for non-rectangular layouts.

See issue FPGA-Research/FABulous#650.
"""

from collections import Counter
from collections.abc import Mapping
from enum import StrEnum
from math import ceil
from pathlib import Path
from typing import Any

import yaml

from fabulous.fabric_definition.fabric import Fabric

# Constants matching FABulous_bit_gen's wire format (see bit_gen.genBitstream).
_BIT_GEN_HEADER_BYTES = 20  # 00AAFF01000000010000000000000000FAB0FAB1
_BIT_GEN_TRAILER_BYTES = 4  # 00100000 desync word
_BIT_GEN_FRAME_SELECT_BYTES = 4  # 32-bit frame_select word per (column, frame)
_BIT_GEN_TERMINATION_ROWS = 2  # bit_gen skips the top and bottom rows


class MetadataFormat(StrEnum):
    """Output format for fabric metadata generation."""

    YAML = "yaml"
    VERILOG = "verilog"
    SYSTEMVERILOG = "systemverilog"


def _identifier(name: str) -> str:
    """Return a Verilog/SV-safe upper-case identifier for ``name``."""
    return "".join(c if c.isalnum() else "_" for c in name).upper()


def _relative_to(path: Path, base: Path) -> str:
    """Return ``path`` relative to ``base`` as a forward-slash string.

    Falls back to the absolute POSIX path when ``path`` is not below ``base``.
    """
    try:
        return path.resolve().relative_to(base.resolve()).as_posix()
    except (ValueError, OSError):
        return path.as_posix()


def _hdl_path_in(folder: Path, stem: str) -> Path:
    """Return ``folder/<stem>.<ext>`` picking the first existing HDL extension.

    Falls back to ``.v`` when none of the candidates exist (e.g. before fabric
    generation runs), so the path is always well-defined.
    """
    for ext in (".v", ".vhdl", ".sv"):
        candidate = folder / f"{stem}{ext}"
        if candidate.exists():
            return candidate
    return folder / f"{stem}.v"


def _bitstream_length_bytes(
    rows: int, cols: int, frame_bits_per_row: int, max_frames_per_col: int
) -> int:
    """Return the on-wire bitstream length in bytes, matching ``bit_gen``.

    Computes::

        header
        + cols * max_frames_per_col * (frame_select + active_rows * frame_bytes)
        + trailer

    where ``active_rows = max(rows - 2, 0)`` (``bit_gen`` skips the top and
    bottom termination rows) and ``frame_bytes = ceil(frame_bits_per_row / 8)``.
    """
    active_rows = max(rows - _BIT_GEN_TERMINATION_ROWS, 0)
    frame_bytes = ceil(frame_bits_per_row / 8)
    per_frame_bytes = _BIT_GEN_FRAME_SELECT_BYTES + active_rows * frame_bytes
    total_frames = cols * max_frames_per_col
    return (
        _BIT_GEN_HEADER_BYTES + total_frames * per_frame_bytes + _BIT_GEN_TRAILER_BYTES
    )


def collect_fabric_metadata(fabric: Fabric) -> dict[str, Any]:
    """Collect a structured metadata dictionary describing ``fabric``.

    Returns a single top-level ``"fabric"`` mapping containing identity,
    geometry, frame parameters, bitstream sizing and a ``"tiles"`` sub-mapping
    keyed by placed-tile name. Each tile entry carries its placement count,
    total configuration bits, the switch-matrix file path and a list of BELs
    (each with prefix, module name, source RTL and config bits).

    Paths are emitted relative to the fabric directory when possible so the
    YAML output is portable; otherwise the absolute POSIX path is used.
    """
    rows = fabric.numberOfRows
    cols = fabric.numberOfColumns
    frame_bits = fabric.frameBitsPerRow
    max_frames = fabric.maxFramesPerCol

    total_bytes = _bitstream_length_bytes(rows, cols, frame_bits, max_frames)
    total_bits = total_bytes * 8

    placement_counts: Counter[str] = Counter()
    for row in fabric.tile:
        for tile in row:
            if tile is not None:
                placement_counts[tile.name] += 1

    project_root = Path(fabric.fabric_dir).parent

    tiles: dict[str, dict[str, Any]] = {}
    for tile_name in sorted(placement_counts):
        tile = fabric.tileDic.get(tile_name)
        if tile is None:
            continue
        # Collapse duplicate BEL modules (different prefixes) into one entry
        # whose ``count`` is the instance count inside the tile.
        bel_groups: dict[tuple[str, int, str], int] = {}
        for bel in tile.bels:
            key = (bel.name, bel.configBit, _relative_to(bel.src, project_root))
            bel_groups[key] = bel_groups.get(key, 0) + 1

        tiles[tile_name] = {
            "switch_matrix": _relative_to(tile.matrixDir, project_root),
            "rtl_file": _relative_to(
                _hdl_path_in(tile.tileDir.parent, tile.name), project_root
            ),
            "config_bits": tile.globalConfigBits,
            "count": placement_counts[tile_name],
            "bels": [
                {
                    "name": name,
                    "rtl_file": rtl,
                    "config_bits": cfg_bits,
                    "count": instances,
                }
                for (name, cfg_bits, rtl), instances in bel_groups.items()
            ],
        }

    fabric_csv = Path(fabric.fabric_dir)
    fabric_rtl = _hdl_path_in(project_root / "Fabric", fabric.name)
    geometry_csv = project_root / f"{fabric.name}_geometry.csv"

    tile_grid: list[list[str]] = [
        ["NULL" if cell is None else cell.name for cell in row] for row in fabric.tile
    ]

    return {
        "fabric": {
            "name": fabric.name,
            "config_bit_mode": fabric.configBitMode.value,
            "csv": _relative_to(fabric_csv, project_root),
            "rtl_file": _relative_to(fabric_rtl, project_root),
            "geometry_csv": _relative_to(geometry_csv, project_root),
            "dimension": {"width": cols, "height": rows},
            "frame": {
                "bits_per_row": frame_bits,
                "max_per_col": max_frames,
                "select_width": fabric.frameSelectWidth,
                "row_select_width": fabric.rowSelectWidth,
            },
            "bitstream": {
                "length_bits": total_bits,
                "length_bytes": total_bytes,
                "length_words": ceil(total_bits / frame_bits),
                "word_width": frame_bits,
            },
            "tile_count": sum(placement_counts.values()),
            "tiles": tiles,
            "tile_grid": tile_grid,
        }
    }


def _render_yaml(metadata: Mapping[str, Any]) -> str:
    """Render metadata as YAML with comment-labelled section breaks.

    Sections are nested under ``fabric:`` and separated by blank lines so the
    output reads top-down: identity, geometry, frame parameters, bitstream
    sizing, then per-tile inventory. Individual tile entries inside the
    ``tiles:`` block are also separated by blank lines for readability.
    """
    fab = metadata["fabric"]

    def _dump_indent(payload: Any, indent: int) -> str:  # noqa: ANN401
        prefix = " " * indent
        dumped = yaml.safe_dump(payload, sort_keys=False).rstrip()
        return "\n".join(
            f"{prefix}{line}" if line else "" for line in dumped.splitlines()
        )

    tiles_chunks = [
        f"  {tile_name}:\n{_dump_indent(tile_body, 4)}"
        for tile_name, tile_body in fab["tiles"].items()
    ]
    tiles_block = "tiles:\n" + "\n\n".join(tiles_chunks)

    sections: tuple[tuple[str, str], ...] = (
        (
            "# Identity",
            _dump_indent(
                {
                    "name": fab["name"],
                    "config_bit_mode": fab["config_bit_mode"],
                    "csv": fab["csv"],
                    "rtl_file": fab["rtl_file"],
                    "geometry_csv": fab["geometry_csv"],
                },
                2,
            ),
        ),
        ("# Geometry", _dump_indent({"dimension": fab["dimension"]}, 2)),
        ("# Frame parameters", _dump_indent({"frame": fab["frame"]}, 2)),
        (
            "# Bitstream sizing (matches FABulous_bit_gen on-wire format)",
            _dump_indent({"bitstream": fab["bitstream"]}, 2),
        ),
        (
            "# Tile inventory (placed grid, NULL slots excluded)",
            _dump_indent({"tile_count": fab["tile_count"]}, 2)
            + "\n"
            + "\n".join(
                f"  {line}" if line else "" for line in tiles_block.splitlines()
            ),
        ),
    )

    body = "\n\n".join(f"  {header}\n{body}" for header, body in sections)
    return "fabric:\n" + body + "\n"


def _render_verilog_defines(metadata: Mapping[str, Any]) -> str:
    """Render the metadata as a Verilog ``define`` header."""
    fab = metadata["fabric"]
    dim = fab["dimension"]
    frame = fab["frame"]
    bs = fab["bitstream"]

    bel_counts: Counter[str] = Counter()
    for tile in fab["tiles"].values():
        for bel in tile["bels"]:
            bel_counts[bel["name"]] += tile["count"] * bel["count"]

    lines: list[str] = [
        "// Auto-generated by FABulous. Do not edit by hand.",
        "",
        f"// Fabric: {fab['name']}",
        f'`define FABRIC_NAME "{fab["name"]}"',
        f'`define CONFIG_BIT_MODE "{fab["config_bit_mode"]}"',
        "",
        "// Geometry",
        f"`define FABRIC_TILE_WIDTH {dim['width']}",
        f"`define FABRIC_TILE_HEIGHT {dim['height']}",
        f"`define FABRIC_TILE_COUNT {fab['tile_count']}",
        "",
        "// Frame parameters",
        f"`define FRAME_BITS_PER_ROW {frame['bits_per_row']}",
        f"`define MAX_FRAMES_PER_COL {frame['max_per_col']}",
        f"`define FRAME_SELECT_WIDTH {frame['select_width']}",
        f"`define ROW_SELECT_WIDTH {frame['row_select_width']}",
        "",
        "// Bitstream sizing (FABulous_bit_gen on-wire format)",
        f"`define FABRIC_BITSTREAM_LENGTH_BITS {bs['length_bits']}",
        f"`define FABRIC_BITSTREAM_LENGTH_BYTES {bs['length_bytes']}",
        f"`define FABRIC_BITSTREAM_LENGTH_WORDS {bs['length_words']}",
        f"`define FABRIC_BITSTREAM_WORD_WIDTH {bs['word_width']}",
        "",
        "// Tile counts and config bits",
    ]
    for tile_name, tile in fab["tiles"].items():
        ident = _identifier(tile_name)
        lines.append(f"`define NUM_TILE_{ident} {tile['count']}")
        lines.append(f"`define CONFIG_BITS_{ident} {tile['config_bits']}")
    lines.append("")
    lines.append("// BEL counts (across all placed tiles)")
    for bel_name, count in sorted(bel_counts.items()):
        lines.append(f"`define NUM_BEL_{_identifier(bel_name)} {count}")

    return "\n".join(lines) + "\n"


def _render_systemverilog_pkg(metadata: Mapping[str, Any]) -> str:
    """Render the metadata as a SystemVerilog package.

    The package mirrors the YAML structure with strongly-typed parameters:
    a ``tile_type_e`` enum, ``bel_info_t``/``tile_info_t`` typedefs, one
    ``TILE_INFO_<NAME>`` parameter per placed tile type, and a 2D
    ``TILE_GRID`` array indexed ``[row][col]`` mapping each fabric position to
    its tile type. Flat scalars (``FABRIC_NAME``, dimensions, bitstream
    sizing, etc.) are kept alongside for ergonomic access.

    Note: the struct-typed parameters are intended for testbench / verification
    code; most synthesis tools accept the integer scalars but not the
    string-bearing structs.
    """
    fab = metadata["fabric"]
    dim = fab["dimension"]
    frame = fab["frame"]
    bs = fab["bitstream"]
    pkg_name = f"{_identifier(fab['name']).lower()}_pkg"

    tile_names = list(fab["tiles"].keys())
    enum_members = ["NULL", *tile_names]
    enum_lines = [
        f"        TILE_{_identifier(name)} = {idx}"
        for idx, name in enumerate(enum_members)
    ]

    def _bel_literal(b: Mapping[str, Any]) -> str:
        return (
            "'{"
            f'name: "{b["name"]}", '
            f'rtl_file: "{b["rtl_file"]}", '
            f"config_bits: {b['config_bits']}, "
            f"count: {b['count']}"
            "}"
        )

    grid_decl = (
        "    parameter tile_type_e "
        "TILE_GRID [FABRIC_TILE_HEIGHT][FABRIC_TILE_WIDTH] = '{"
    )

    lines: list[str] = [
        "// Auto-generated by FABulous. Do not edit by hand.",
        f"package {pkg_name};",
        "",
        "    // ---- Identity ----",
        f'    parameter string FABRIC_NAME = "{fab["name"]}";',
        f'    parameter string CONFIG_BIT_MODE = "{fab["config_bit_mode"]}";',
        f'    parameter string FABRIC_CSV = "{fab["csv"]}";',
        f'    parameter string FABRIC_RTL_FILE = "{fab["rtl_file"]}";',
        f'    parameter string FABRIC_GEOMETRY_CSV = "{fab["geometry_csv"]}";',
        "",
        "    // ---- Geometry ----",
        f"    parameter int FABRIC_TILE_WIDTH = {dim['width']};",
        f"    parameter int FABRIC_TILE_HEIGHT = {dim['height']};",
        f"    parameter int FABRIC_TILE_COUNT = {fab['tile_count']};",
        "",
        "    // ---- Frame parameters ----",
        f"    parameter int FRAME_BITS_PER_ROW = {frame['bits_per_row']};",
        f"    parameter int MAX_FRAMES_PER_COL = {frame['max_per_col']};",
        f"    parameter int FRAME_SELECT_WIDTH = {frame['select_width']};",
        f"    parameter int ROW_SELECT_WIDTH = {frame['row_select_width']};",
        "",
        "    // ---- Bitstream sizing (FABulous_bit_gen on-wire format) ----",
        f"    parameter int FABRIC_BITSTREAM_LENGTH_BITS = {bs['length_bits']};",
        f"    parameter int FABRIC_BITSTREAM_LENGTH_BYTES = {bs['length_bytes']};",
        f"    parameter int FABRIC_BITSTREAM_LENGTH_WORDS = {bs['length_words']};",
        f"    parameter int FABRIC_BITSTREAM_WORD_WIDTH = {bs['word_width']};",
        "",
        "    // ---- Tile type enum ----",
        "    typedef enum int {",
        ",\n".join(enum_lines),
        "    } tile_type_e;",
        "",
        "    // ---- 2D tile grid (indexed [row][col]) ----",
        grid_decl,
    ]
    grid = fab["tile_grid"]
    for r, row in enumerate(grid):
        cells = ", ".join(f"TILE_{_identifier(name)}" for name in row)
        comma = "," if r < len(grid) - 1 else ""
        lines.append(f"        '{{{cells}}}{comma}")
    lines.append("    };")
    lines.append("")

    lines.extend(
        [
            "    // ---- BEL info struct ----",
            "    typedef struct {",
            "        string name;",
            "        string rtl_file;",
            "        int    config_bits;",
            "        int    count;",
            "    } bel_info_t;",
            "",
            "    // ---- Tile info struct ----",
            "    // Each tile's BELs are emitted as a separate, exact-sized",
            "    // TILE_BELS_<NAME> array below; tiles with no BELs omit it",
            "    // and signal that via num_bels == 0.",
            "    typedef struct {",
            "        string switch_matrix;",
            "        string rtl_file;",
            "        int    config_bits;",
            "        int    count;",
            "        int    num_bels;",
            "    } tile_info_t;",
            "",
            "    // ---- Per-tile parameters ----",
        ]
    )
    for tile_name, tile in fab["tiles"].items():
        ident = _identifier(tile_name)
        lines.append(f"    parameter tile_info_t TILE_INFO_{ident} = '{{")
        lines.append(f'        switch_matrix: "{tile["switch_matrix"]}",')
        lines.append(f'        rtl_file: "{tile["rtl_file"]}",')
        lines.append(f"        config_bits: {tile['config_bits']},")
        lines.append(f"        count: {tile['count']},")
        lines.append(f"        num_bels: {len(tile['bels'])}")
        lines.append("    };")
        if tile["bels"]:
            n = len(tile["bels"])
            lines.append(f"    parameter bel_info_t TILE_BELS_{ident} [{n}] = '{{")
            for i, bel in enumerate(tile["bels"]):
                comma = "," if i < n - 1 else ""
                lines.append(f"        {_bel_literal(bel)}{comma}")
            lines.append("    };")
        lines.append("")

    lines.append(f"endpackage : {pkg_name}")
    return "\n".join(lines) + "\n"


def generate_fabric_metadata(
    fabric: Fabric,
    output_dir: Path,
    *,
    formats: tuple[MetadataFormat, ...] = tuple(MetadataFormat),
) -> dict[MetadataFormat, Path]:
    """Generate fabric metadata files in ``output_dir`` for each requested format.

    Parameters
    ----------
    fabric : Fabric
        Parsed fabric to summarise.
    output_dir : Path
        Directory to write into; created if missing.
    formats : tuple[MetadataFormat, ...]
        Subset of ``MetadataFormat`` members to emit. Defaults to all three.

    Returns
    -------
    dict[MetadataFormat, Path]
        Mapping from each requested format to the path written.
    """
    output_dir.mkdir(parents=True, exist_ok=True)
    metadata = collect_fabric_metadata(fabric)
    base = metadata["fabric"]["name"]

    written: dict[MetadataFormat, Path] = {}
    for fmt in formats:
        fmt_enum = MetadataFormat(fmt)
        if fmt_enum is MetadataFormat.YAML:
            path = output_dir / f"{base}.yaml"
            path.write_text(_render_yaml(metadata), encoding="utf-8")
        elif fmt_enum is MetadataFormat.VERILOG:
            path = output_dir / f"{base}_defines.v"
            path.write_text(_render_verilog_defines(metadata), encoding="utf-8")
        elif fmt_enum is MetadataFormat.SYSTEMVERILOG:
            path = output_dir / f"{base}_pkg.sv"
            path.write_text(_render_systemverilog_pkg(metadata), encoding="utf-8")
        written[fmt_enum] = path
    return written

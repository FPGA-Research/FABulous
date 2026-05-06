"""Fabric metadata export module.

Generate machine-readable summaries of a fabric's geometry, bitstream sizing,
tile inventory and primitive (BEL) inventory. The same metadata is rendered in
three formats so it can be consumed by downstream HDL, software and tooling:

- YAML, for general tooling and scripts.
- Verilog `define` headers, for inclusion in `.v` testbenches and IP.
- SystemVerilog packages, for `import`-style use in `.sv` projects.

Bitstream length matches the on-wire format produced by ``FABulous_bit_gen``:
a 20-byte sync header, followed for every (column, frame) pair by a 4-byte
``frame_select`` word and ``active_rows * (frame_bits_per_row / 8)`` bytes of
frame payload, terminated by a 4-byte desync word. ``active_rows`` excludes
the top and bottom termination rows that ``bit_gen`` skips. NULL slots inside
the active row range still contribute zeroed frame data because frames are
broadcast to every active row in their column.

Tile and primitive counts iterate the placed grid and skip NULL slots, so they
are accurate for non-rectangular layouts.

See issue FPGA-Research/FABulous#650.
"""

from collections import Counter
from collections.abc import Mapping
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


def _identifier(name: str) -> str:
    """Return a Verilog/SV-safe upper-case identifier for ``name``."""
    return "".join(c if c.isalnum() else "_" for c in name).upper()


def _count_used_tiles(fabric: Fabric) -> dict[str, int]:
    """Count occurrences of each tile name in the placed grid."""
    counter: Counter[str] = Counter()
    for row in fabric.tile:
        for tile in row:
            if tile is not None:
                counter[tile.name] += 1
    return dict(sorted(counter.items()))


def _count_primitives(fabric: Fabric) -> dict[str, int]:
    """Count BEL instances across every used tile position in the fabric.

    Each placed tile contributes its full BEL list, so a BEL appearing twice in
    a tile that is placed five times contributes ten primitive instances.
    """
    counter: Counter[str] = Counter()
    for row in fabric.tile:
        for tile in row:
            if tile is None:
                continue
            for bel in tile.bels:
                counter[bel.name] += 1
    return dict(sorted(counter.items()))


def _per_tile_config_bits(fabric: Fabric) -> dict[str, int]:
    """Map each used tile name to its declared global config bits."""
    bits: dict[str, int] = {}
    for tile_name in _count_used_tiles(fabric):
        tile = fabric.tileDic.get(tile_name)
        if tile is None:
            continue
        bits[tile_name] = getattr(tile, "globalConfigBits", 0)
    return bits


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
        _BIT_GEN_HEADER_BYTES
        + total_frames * per_frame_bytes
        + _BIT_GEN_TRAILER_BYTES
    )


def collect_fabric_metadata(fabric: Fabric) -> dict[str, Any]:
    """Collect a structured metadata dictionary describing ``fabric``.

    The dictionary uses plain Python types (``str``, ``int``, ``dict``) so it
    serialises cleanly to YAML and is straightforward to render as Verilog
    defines or a SystemVerilog package.

    Bitstream length fields match the on-wire format emitted by
    ``FABulous_bit_gen`` (header + per-(column, frame) select word and frame
    payload over active rows + desync trailer); the figure does not include
    user FASM contents on top of the empty bitstream because every config-bit
    slot is sized identically regardless of whether it is set.
    """
    rows = fabric.numberOfRows
    cols = fabric.numberOfColumns
    frame_bits_per_row = fabric.frameBitsPerRow
    max_frames_per_col = fabric.maxFramesPerCol

    total_bytes = _bitstream_length_bytes(
        rows, cols, frame_bits_per_row, max_frames_per_col
    )
    total_bits = total_bytes * 8
    word_width = frame_bits_per_row
    total_words = ceil(total_bits / word_width)

    return {
        "fabric_name": fabric.name,
        "fabric_tile_width": cols,
        "fabric_tile_height": rows,
        "config_bit_mode": fabric.configBitMode.value,
        "frame_bits_per_row": frame_bits_per_row,
        "max_frames_per_col": max_frames_per_col,
        "frame_select_width": fabric.frameSelectWidth,
        "row_select_width": fabric.rowSelectWidth,
        "fabric_bitstream_length_bits": total_bits,
        "fabric_bitstream_length_bytes": total_bytes,
        "fabric_bitstream_length_words": total_words,
        "fabric_bitstream_word_width": word_width,
        "tiles": _count_used_tiles(fabric),
        "primitives": _count_primitives(fabric),
        "tile_config_bits": _per_tile_config_bits(fabric),
    }


_SCALAR_KEYS: tuple[str, ...] = (
    "fabric_tile_width",
    "fabric_tile_height",
    "frame_bits_per_row",
    "max_frames_per_col",
    "frame_select_width",
    "row_select_width",
    "fabric_bitstream_length_bits",
    "fabric_bitstream_length_bytes",
    "fabric_bitstream_length_words",
    "fabric_bitstream_word_width",
)


_YAML_GROUPS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("# Identity", ("fabric_name", "config_bit_mode")),
    (
        "# Geometry",
        ("fabric_tile_width", "fabric_tile_height"),
    ),
    (
        "# Frame parameters",
        (
            "frame_bits_per_row",
            "max_frames_per_col",
            "frame_select_width",
            "row_select_width",
        ),
    ),
    (
        "# Bitstream sizing (matches FABulous_bit_gen on-wire format)",
        (
            "fabric_bitstream_length_bits",
            "fabric_bitstream_length_bytes",
            "fabric_bitstream_length_words",
            "fabric_bitstream_word_width",
        ),
    ),
    ("# Tile counts (placed grid, NULL slots excluded)", ("tiles",)),
    ("# Primitive (BEL) counts", ("primitives",)),
    ("# Per-tile config bits", ("tile_config_bits",)),
)


def render_metadata_yaml(metadata: Mapping[str, Any]) -> str:
    """Return YAML text describing ``metadata``, with blank-line section breaks."""
    sections: list[str] = []
    for header, keys in _YAML_GROUPS:
        chunk = {k: metadata[k] for k in keys if k in metadata}
        if not chunk:
            continue
        body = yaml.safe_dump(chunk, sort_keys=False).rstrip()
        sections.append(f"{header}\n{body}")
    return "\n\n".join(sections) + "\n"


def write_metadata_yaml(metadata: Mapping[str, Any], path: Path) -> None:
    """Write ``metadata`` to ``path`` as YAML."""
    path.write_text(render_metadata_yaml(metadata), encoding="utf-8")


def render_metadata_verilog_defines(metadata: Mapping[str, Any]) -> str:
    """Return Verilog `define` text describing ``metadata``."""
    lines: list[str] = ["// Auto-generated by FABulous. Do not edit by hand.", ""]
    lines.append(f"// Fabric: {metadata['fabric_name']}")
    lines.append(f'`define FABRIC_NAME "{metadata['fabric_name']}"')
    lines.append(f'`define CONFIG_BIT_MODE "{metadata['config_bit_mode']}"')
    lines.append("")

    lines.append("// Geometry and bitstream")
    for key in _SCALAR_KEYS:
        lines.append(f"`define {key.upper()} {metadata[key]}")
    lines.append("")

    lines.append("// Tile counts")
    for tile, count in metadata["tiles"].items():
        lines.append(f"`define NUM_TILE_{_identifier(tile)} {count}")
    lines.append("")

    lines.append("// Primitive (BEL) counts")
    for bel, count in metadata["primitives"].items():
        lines.append(f"`define NUM_BEL_{_identifier(bel)} {count}")
    lines.append("")

    lines.append("// Per-tile config bits")
    for tile, bits in metadata["tile_config_bits"].items():
        lines.append(f"`define CONFIG_BITS_{_identifier(tile)} {bits}")

    return "\n".join(lines) + "\n"


def write_metadata_verilog_defines(metadata: Mapping[str, Any], path: Path) -> None:
    """Write the Verilog defines header to ``path``."""
    path.write_text(render_metadata_verilog_defines(metadata), encoding="utf-8")


def render_metadata_systemverilog_pkg(metadata: Mapping[str, Any]) -> str:
    """Return SystemVerilog package text describing ``metadata``."""
    pkg_name = f"{_identifier(metadata['fabric_name']).lower()}_pkg"

    lines: list[str] = [
        "// Auto-generated by FABulous. Do not edit by hand.",
        f"package {pkg_name};",
        "",
        f'    parameter string FABRIC_NAME = "{metadata['fabric_name']}";',
        f'    parameter string CONFIG_BIT_MODE = "{metadata['config_bit_mode']}";',
        "",
        "    // Geometry and bitstream",
    ]
    for key in _SCALAR_KEYS:
        lines.append(f"    parameter int {key.upper()} = {metadata[key]};")
    lines.append("")

    lines.append("    // Tile counts")
    for tile, count in metadata["tiles"].items():
        lines.append(f"    parameter int NUM_TILE_{_identifier(tile)} = {count};")
    lines.append("")

    lines.append("    // Primitive (BEL) counts")
    for bel, count in metadata["primitives"].items():
        lines.append(f"    parameter int NUM_BEL_{_identifier(bel)} = {count};")
    lines.append("")

    lines.append("    // Per-tile config bits")
    for tile, bits in metadata["tile_config_bits"].items():
        lines.append(f"    parameter int CONFIG_BITS_{_identifier(tile)} = {bits};")

    lines.append("")
    lines.append(f"endpackage : {pkg_name}")
    return "\n".join(lines) + "\n"


def write_metadata_systemverilog_pkg(metadata: Mapping[str, Any], path: Path) -> None:
    """Write the SystemVerilog package to ``path``."""
    path.write_text(render_metadata_systemverilog_pkg(metadata), encoding="utf-8")


def generate_fabric_metadata(
    fabric: Fabric,
    output_dir: Path,
    *,
    formats: tuple[str, ...] = ("yaml", "verilog", "systemverilog"),
) -> dict[str, Path]:
    """Generate fabric metadata files in ``output_dir`` for the given formats.

    Returns a mapping from format name to the path written. Unknown format names
    raise ``ValueError`` so typos surface immediately.
    """
    output_dir.mkdir(parents=True, exist_ok=True)
    metadata = collect_fabric_metadata(fabric)
    base = metadata["fabric_name"]

    written: dict[str, Path] = {}
    for fmt in formats:
        if fmt == "yaml":
            path = output_dir / f"{base}.yaml"
            write_metadata_yaml(metadata, path)
        elif fmt == "verilog":
            path = output_dir / f"{base}_defines.v"
            write_metadata_verilog_defines(metadata, path)
        elif fmt == "systemverilog":
            path = output_dir / f"{base}_pkg.sv"
            write_metadata_systemverilog_pkg(metadata, path)
        else:
            raise ValueError(
                f"Unknown metadata format: {fmt!r}. "
                "Expected one of: yaml, verilog, systemverilog."
            )
        written[fmt] = path
    return written

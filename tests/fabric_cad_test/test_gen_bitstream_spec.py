"""Tests for bitstream specification generation.

Three layers of coverage:

* Unit tests for :func:`border_rows_have_config_bits`, the border-row detection
  that drives the ``IncludeBorderRows`` archspec flag.
* Integration tests that run the real generator on a fully generated demo fabric
  and assert the whole specification is internally consistent.
* Bit-offset tests: ``generateBitstreamSpec`` assigns configuration-bit offsets
  while iterating a tile's BEL feature map, switch-matrix sources, and wire
  list. Those offsets must mirror the order in which the fabric HDL wires its
  config bits: ``genTileSwitchMatrix`` walks ``parseMatrix``'s connections in
  insertion order and assigns ``ConfigBits`` positions accordingly, so the spec
  has to follow the same insertion order to stay aligned with the generated
  hardware.
"""

from pathlib import Path

import pytest

from fabulous.fabric_cad.gen_bitstream_spec import (
    border_rows_have_config_bits,
    generateBitstreamSpec,
)
from fabulous.fabric_definition.bel import Bel
from fabulous.fabric_definition.define import Direction
from fabulous.fabric_definition.fabric import Fabric
from fabulous.fabric_definition.switch_matrix import SwitchMatrix
from fabulous.fabric_definition.tile import Tile
from fabulous.fabric_definition.wire import Wire
from fabulous.fabulous_repl.fabulous_repl import FABulousREPL
from tests.conftest import make_empty_tile, make_fabric_from_grid, run_cmd


def _fabric_from_bits(grid: list[list[int | None]]) -> Fabric:
    """Build a real Fabric from a grid of per-tile config-bit counts.

    Parameters
    ----------
    grid : list[list[int | None]]
        Per-tile ``globalConfigBits``; ``None`` marks an empty (NULL) cell.

    Returns
    -------
    Fabric
        A real Fabric whose tiles report the requested config-bit counts.
    """
    tile_grid: list[list[object]] = [
        [
            None if bits is None else make_empty_tile(f"T{y}_{x}", config_bits=bits)
            for x, bits in enumerate(row)
        ]
        for y, row in enumerate(grid)
    ]
    return make_fabric_from_grid(tile_grid)


@pytest.mark.parametrize(
    ("grid", "expected"),
    [
        ([[0, 0], [127, 127], [0, 0]], False),  # config only in interior row
        ([[127, 0], [127, 127], [0, 0]], True),  # top row has config
        ([[0, 0], [127, 127], [0, 127]], True),  # bottom row has config
        ([[5, 5], [0, 0], [5, 5]], True),  # both border rows have config
        ([[None, None], [127, 127], [None, None]], False),  # border rows all NULL
        ([[0, None], [127, 127], [None, 42]], True),  # NULL mixed with config
        ([[127, 127]], True),  # single row counts as both borders
        ([[0, 0]], False),  # single zero-config row
        ([[1]], True),  # single tile, single bit
        ([[0], [0], [0]], False),  # tall single-column, no config
    ],
)
def test_border_rows_have_config_bits(
    grid: list[list[int | None]], expected: bool
) -> None:
    """Border-row detection flags config bits in the top or bottom row only."""
    fabric = _fabric_from_bits(grid)
    assert border_rows_have_config_bits(fabric) is expected


def test_border_rows_have_config_bits_empty_fabric() -> None:
    """An empty tile grid reports no border config bits."""
    fabric = make_fabric_from_grid([])
    assert border_rows_have_config_bits(fabric) is False


def test_border_rows_have_config_bits_interior_ignored() -> None:
    """Config bits confined to interior rows never flip the flag on."""
    grid = [[0, 0, 0]] + [[127, 127, 127]] * 5 + [[0, 0, 0]]
    fabric = _fabric_from_bits(grid)
    assert border_rows_have_config_bits(fabric) is False


@pytest.fixture
def generated_fabric(cli: FABulousREPL) -> Fabric:
    """Return the fully generated demo fabric bound to the CLI fixture."""
    run_cmd(cli, "gen_fabric")
    return cli.fabulousAPI.fabric


def _all_tile_locations(fabric: Fabric) -> set[str]:
    """Return every ``XxYy`` location string in the fabric grid."""
    return {f"X{x}Y{y}" for y, row in enumerate(fabric.tile) for x, _ in enumerate(row)}


def test_spec_is_internally_consistent(generated_fabric: Fabric) -> None:
    """The spec for a real fabric is complete and self-consistent."""
    fabric = generated_fabric
    spec = generateBitstreamSpec(fabric)

    arch = spec["ArchSpecs"]
    assert arch["FrameBitsPerRow"] == fabric.frameBitsPerRow
    assert arch["MaxFramesPerCol"] == fabric.maxFramesPerCol
    assert arch["FrameSelectWidth"] == fabric.frameSelectWidth
    assert arch["DesyncBit"] == fabric.desync_flag
    # the flag must mirror the detector on the actual fabric
    assert arch["IncludeBorderRows"] == border_rows_have_config_bits(fabric)
    assert arch["MultiClkDomains"] == fabric.multiClkDomains

    # TileMap covers the whole grid; NULL cells are mapped but carry no specs
    assert set(spec["TileMap"]) == _all_tile_locations(fabric)
    for loc, name in spec["TileMap"].items():
        if name == "NULL":
            assert loc not in spec["TileSpecs"]
        else:
            assert loc in spec["TileSpecs"]
            assert loc in spec["TileSpecs_No_Mask"]
            # masked and unmasked views describe the same features
            assert set(spec["TileSpecs"][loc]) == set(spec["TileSpecs_No_Mask"][loc])

    # FrameMap is keyed by the names of every placed (non-NULL) tile
    grid_names = {t.name for row in fabric.tile for t in row if t is not None}
    assert set(spec["FrameMap"]) == grid_names

    # every config bit resolves to a real frame position (no unassigned -1 leaks)
    max_bit = fabric.frameBitsPerRow * fabric.maxFramesPerCol
    for loc, features in spec["TileSpecs"].items():
        for feature, bits in features.items():
            for bit_index in bits:
                assert 0 <= bit_index < max_bit, (
                    f"{loc}.{feature} maps to invalid frame bit {bit_index}"
                )


def test_border_rows_excluded_for_demo_fabric(generated_fabric: Fabric) -> None:
    """The demo fabric terminates top/bottom rows, so the flag stays off."""
    spec = generateBitstreamSpec(generated_fabric)
    assert spec["ArchSpecs"]["IncludeBorderRows"] is False


def test_multi_clk_domains_defaults_off(generated_fabric: Fabric) -> None:
    """MultiClkDomains defaults to False for a plain fabric."""
    spec = generateBitstreamSpec(generated_fabric)
    assert spec["ArchSpecs"]["MultiClkDomains"] is False


def test_multi_clk_domains_flag_propagates(generated_fabric: Fabric) -> None:
    """Setting the fabric flag propagates into the spec's ArchSpecs."""
    fabric = generated_fabric
    fabric.multiClkDomains = True
    spec = generateBitstreamSpec(fabric)
    assert spec["ArchSpecs"]["MultiClkDomains"] is True


def test_config_tile_in_border_row_sets_flag(generated_fabric: Fabric) -> None:
    """Placing a config-bearing tile in the top row turns the flag on."""
    fabric = generated_fabric
    config_tile = next(
        tile
        for row in fabric.tile
        for tile in row
        if tile is not None and tile.globalConfigBits > 0
    )
    # replace a placed cell in the top border row with the config-bearing tile
    top_row = fabric.tile[0]
    target_x = next(x for x, tile in enumerate(top_row) if tile is not None)
    top_row[target_x] = config_tile

    spec = generateBitstreamSpec(fabric)

    assert spec["ArchSpecs"]["IncludeBorderRows"] is True
    assert f"X{target_x}Y0" in spec["TileSpecs"]


# Fabric.__post_init__ mandates 20 frames x 32 bits. Park all used config bits
# in frame 0 so encodeDict[0:_USED_BITS] resolve to distinct physical positions
# (frame 0 bit i -> 31 - i); that makes a wrong offset assignment observable
# instead of collapsing onto the unused -1 sentinel.
_FRAME_BITS = 32
_MAX_FRAMES = 20
_USED_BITS = 6
_TILE_NAME = "TESTTILE"
_DESTS = ["D0", "D1"]

# Three BEL features consuming four config bits (F_B is a two-bit feature) plus
# two switch-matrix sources consuming one control bit each => 6 global config
# bits, matching matrixConfigBits (2) + bel.configBit (4).
_FEATURE_MAP = {
    "F_A": {0: {0: "1"}},
    "F_B": {0: {0: "0", 1: "1"}},
    "F_C": {0: {0: "1"}},
}
_SOURCES = ["S0", "S1"]


def _write_configmem(path: Path) -> None:
    """Write a 20-frame ConfigMem CSV with all used bits in frame 0.

    Parameters
    ----------
    path : Path
        Destination CSV path.
    """
    header = (
        "frame_name,frame_index,bits_used_in_frame,used_bits_mask,ConfigBits_ranges"
    )
    mask = "1" * _USED_BITS + "0" * (_FRAME_BITS - _USED_BITS)
    rows = [header, f"frame0,0,{_USED_BITS},{mask},0:{_USED_BITS - 1}"]
    for index in range(1, _MAX_FRAMES):
        rows.append(f"frame{index},{index},0,{'0' * _FRAME_BITS},NULL")
    path.write_text("\n".join(rows) + "\n")


def _write_matrix(path: Path, sources: list[str]) -> None:
    """Write a switch-matrix CSV wiring every source to every destination.

    Parameters
    ----------
    path : Path
        Destination CSV path.
    sources : list[str]
        Source rows, written in the given order so the test can vary it.
    """
    lines = [f"{_TILE_NAME}," + ",".join(_DESTS)]
    for source in sources:
        lines.append(f"{source}," + ",".join(["1"] * len(_DESTS)))
    path.write_text("\n".join(lines) + "\n")


def _natural_wires() -> list[Wire]:
    """Return the wire list used by the tests.

    Returns
    -------
    list[Wire]
        Two immutable wires in their declared insertion order.
    """
    return [
        Wire(Direction.JUMP, "W_A", 0, 0, "W_B", "", ""),
        Wire(Direction.JUMP, "W_C", 0, 0, "W_D", "", ""),
    ]


def _build_fabric(
    root: Path,
    name: str,
    feature_map: dict[str, dict],
    sources: list[str],
    wires: list[Wire],
) -> Fabric:
    """Build a single-tile fabric backed by on-disk ConfigMem and matrix CSVs.

    Parameters
    ----------
    root : Path
        Temporary root directory; each fabric gets its own ``name`` subtree so
        their CSV files do not clobber one another.
    name : str
        Subdirectory name isolating this fabric's CSV files.
    feature_map : dict[str, dict]
        BEL feature map populating the single BEL.
    sources : list[str]
        Switch-matrix source rows, in the desired insertion order.
    wires : list[Wire]
        Immutable wire connections, in the desired insertion order.

    Returns
    -------
    Fabric
        A 1x1 fabric whose only tile carries the supplied feature map, switch
        matrix, and wire list.
    """
    tile_dir = root / name / _TILE_NAME
    tile_dir.mkdir(parents=True, exist_ok=True)

    _write_configmem(tile_dir / f"{_TILE_NAME}_ConfigMem.csv")
    matrix_path = tile_dir / f"{_TILE_NAME}_switch_matrix.csv"
    _write_matrix(matrix_path, sources)

    bel = Bel(
        src=tile_dir / "LUTA.v",
        prefix="",
        module_name="LUTA",
        internal=[],
        external=[],
        configPort=[],
        sharedPort=[],
        configBit=4,
        belMap=feature_map,
        userCLK=False,
        ports_vectors={},
        carry={},
        localShared={},
    )

    tile = Tile(
        name=_TILE_NAME,
        ports=[],
        bels=[bel],
        tileDir=tile_dir / f"{_TILE_NAME}.csv",
        switch_matrix=SwitchMatrix.from_file(matrix_path, _TILE_NAME),
        gen_ios=[],
        userCLK=False,
    )
    tile.wireList = wires

    fabric = Fabric(fabric_dir=root)
    fabric.tile = [[tile]]
    fabric.numberOfRows = 1
    fabric.numberOfColumns = 1
    return fabric


def test_bitstream_spec_is_deterministic(tmp_path: Path) -> None:
    """Identical fabric content yields an identical spec across runs."""
    first = _build_fabric(
        tmp_path,
        "first",
        feature_map=_FEATURE_MAP,
        sources=_SOURCES,
        wires=_natural_wires(),
    )
    second = _build_fabric(
        tmp_path,
        "second",
        feature_map=_FEATURE_MAP,
        sources=_SOURCES,
        wires=_natural_wires(),
    )

    spec_first = generateBitstreamSpec(first)
    spec_second = generateBitstreamSpec(second)

    assert spec_first == spec_second
    # Guard against a vacuous pass: the tile spec must actually be populated.
    assert spec_first["TileSpecs"]["X0Y0"]


def test_bitstream_spec_assigns_bit_offsets_in_insertion_order(
    tmp_path: Path,
) -> None:
    """Each feature/pip maps to the config bit implied by its insertion order.

    Frame 0 maps config bits 0..5 to physical positions 31..26. The three BEL
    features consume offsets 0..3 and the two switch-matrix sources consume
    offsets 4..5, in the order the parsers populate them, so the encoding below
    is fully determined.
    """
    fabric = _build_fabric(
        tmp_path,
        "golden",
        feature_map=_FEATURE_MAP,
        sources=_SOURCES,
        wires=_natural_wires(),
    )

    tile_spec = generateBitstreamSpec(fabric)["TileSpecs"]["X0Y0"]

    assert tile_spec["A.F_A"] == {31: "1"}
    # F_B is a two-bit feature; only the highest bit survives the per-bit
    # overwrite, landing on offset 2 -> physical position 29.
    assert tile_spec["A.F_B"] == {29: "1"}
    assert tile_spec["A.F_C"] == {28: "1"}
    assert tile_spec["D0.S0"] == {27: "0"}
    assert tile_spec["D1.S0"] == {27: "1"}
    assert tile_spec["D0.S1"] == {26: "0"}
    assert tile_spec["D1.S1"] == {26: "1"}
    # Immutable wires emit empty bit maps.
    assert tile_spec["W_A.W_B"] == {}
    assert tile_spec["W_C.W_D"] == {}

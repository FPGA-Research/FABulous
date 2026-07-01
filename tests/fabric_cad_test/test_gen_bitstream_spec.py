"""Tests for deterministic, canonical bitstream-spec generation.

``generateBitstreamSpec`` assigns configuration-bit offsets while iterating a
tile's BEL feature map, switch-matrix sources, and wire list. Those offsets
must be canonical: identical fabric content has to yield an identical bit
assignment regardless of the order in which the parsers happened to populate
those containers, so the emitted spec stays stable across unrelated upstream
flow changes.
"""

from pathlib import Path

from fabulous.fabric_cad.gen_bitstream_spec import generateBitstreamSpec
from fabulous.fabric_definition.bel import Bel
from fabulous.fabric_definition.define import Direction
from fabulous.fabric_definition.fabric import Fabric
from fabulous.fabric_definition.tile import Tile
from fabulous.fabric_definition.wire import Wire

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


def _reverse_feature_map(feature_map: dict[str, dict]) -> dict[str, dict]:
    """Rebuild a feature map with every dict's insertion order reversed.

    Parameters
    ----------
    feature_map : dict[str, dict]
        Feature map shaped ``{feature: {entry: {bit: value}}}``.

    Returns
    -------
    dict[str, dict]
        Logically identical map whose feature, entry, and bit keys were
        inserted in reverse order.
    """
    reversed_map: dict[str, dict] = {}
    for feature in reversed(list(feature_map)):
        entries: dict[int, dict] = {}
        for entry in reversed(list(feature_map[feature])):
            bits = feature_map[feature][entry]
            entries[entry] = {bit: bits[bit] for bit in reversed(list(bits))}
        reversed_map[feature] = entries
    return reversed_map


def _natural_wires() -> list[Wire]:
    """Return the canonical-order wire list used by the tests.

    Returns
    -------
    list[Wire]
        Two immutable wires whose ``(source, destination)`` keys are already
        in sorted order.
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
        matrixDir=matrix_path,
        gen_ios=[],
        userCLK=False,
        configBit=2,
    )
    tile.wireList = wires

    fabric = Fabric(fabric_dir=root)
    fabric.tile = [[tile]]
    fabric.numberOfRows = 1
    fabric.numberOfColumns = 1
    return fabric


def test_bitstream_spec_is_canonical_regardless_of_insertion_order(
    tmp_path: Path,
) -> None:
    """Reordering feature/source/wire insertion must not change the spec."""
    natural = _build_fabric(
        tmp_path,
        "natural",
        feature_map=_FEATURE_MAP,
        sources=_SOURCES,
        wires=_natural_wires(),
    )
    shuffled = _build_fabric(
        tmp_path,
        "shuffled",
        feature_map=_reverse_feature_map(_FEATURE_MAP),
        sources=list(reversed(_SOURCES)),
        wires=list(reversed(_natural_wires())),
    )

    spec_natural = generateBitstreamSpec(natural)
    spec_shuffled = generateBitstreamSpec(shuffled)

    assert spec_natural == spec_shuffled
    # Guard against a vacuous pass: the tile spec must actually be populated.
    assert spec_natural["TileSpecs"]["X0Y0"]


def test_bitstream_spec_assigns_canonical_bit_offsets(tmp_path: Path) -> None:
    """The canonical assignment maps each feature/pip to a fixed config bit.

    Frame 0 maps config bits 0..5 to physical positions 31..26. Sorted
    features consume offsets 0..3 and the two switch-matrix sources consume
    offsets 4..5, so the encoding below is fully determined.
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
    # F_B is a two-bit feature; only the highest sorted bit survives the
    # per-bit overwrite, landing on offset 2 -> physical position 29.
    assert tile_spec["A.F_B"] == {29: "1"}
    assert tile_spec["A.F_C"] == {28: "1"}
    assert tile_spec["D0.S0"] == {27: "0"}
    assert tile_spec["D1.S0"] == {27: "1"}
    assert tile_spec["D0.S1"] == {26: "0"}
    assert tile_spec["D1.S1"] == {26: "1"}
    # Immutable wires emit empty bit maps under canonical (source, dest) order.
    assert tile_spec["W_A.W_B"] == {}
    assert tile_spec["W_C.W_D"] == {}

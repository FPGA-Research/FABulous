"""Characterization tests for the automated custom tile generation.

These pin the *current* behaviour of the custom-tile generator
(`fabulous.fabric_generator.gen_fabric.fabric_automation`) so the upcoming
supertile-split extension cannot silently break the single-tile path.

The switch-matrix / prims logic is exercised with in-memory `Bel` objects (no
yosys). The `generateCustomTileConfig` cases parse real BEL HDL and are
therefore gated on yosys being available.

ponytail: the NORTH-carry / JUMP-shared *CSV emission* branch of
`generateCustomTileConfig` is not covered here — no Verilog template BEL
carries the CARRY / SHARED_RESET / SHARED_ENABLE attributes needed to trigger
it, and the corresponding *wiring* is already locked at the
`generateSwitchmatrixList` level below. Add a synthetic attributed BEL if that
CSV branch ever gains real logic.
"""

import shutil
from pathlib import Path

import pytest

from fabulous.fabric_definition.bel import Bel
from fabulous.fabric_definition.define import IO, Direction, Side
from fabulous.fabric_definition.port import TilePort
from fabulous.fabric_generator.gen_fabric.fabric_automation import (
    addBelsToPrim,
    generateCustomTileConfig,
    generateSwitchmatrixList,
)
from fabulous.fabric_generator.parser.parse_switchmatrix import parseList
from fabulous.fabulous_settings import get_context, init_context

LUT4C = "LUT4c_frame_config_dffesr.v"


def make_bel(
    *,
    name: str = "B",
    module_name: str = "B",
    inputs: tuple[str, ...] = (),
    outputs: tuple[str, ...] = (),
    shared: tuple[tuple[str, IO], ...] = (),
    carry: dict[str, dict[IO, str]] | None = None,
    local: dict[str, tuple[str, IO]] | None = None,
    belMap: dict[str, dict] | None = None,
) -> Bel:
    """Build a minimal in-memory Verilog `Bel` for the automation functions."""
    internal = [(p, IO.INPUT) for p in inputs] + [(p, IO.OUTPUT) for p in outputs]
    if carry:
        for chain in carry.values():
            internal.append((chain[IO.INPUT], IO.INPUT))
            internal.append((chain[IO.OUTPUT], IO.OUTPUT))
    if local:
        for port, io in local.values():
            internal.append((port, io))
    return Bel(
        src=Path(f"{name}.v"),
        prefix="",
        module_name=module_name,
        internal=internal,
        external=[],
        configPort=[],
        sharedPort=list(shared),
        configBit=0,
        belMap=belMap or {},
        userCLK=False,
        ports_vectors={},
        carry=carry or {},
        localShared=local or {},
    )


def tile_port(name: str, io: IO) -> TilePort:
    """A JUMP port used as a tile-level shared reset/enable endpoint."""
    return TilePort(
        name=name,
        io_direction=io,
        width=1,
        side_of_tile=Side.ANY,
        wire_direction=Direction.JUMP,
        source_name=name if io == IO.OUTPUT else "NULL",
        destination_name=name if io == IO.INPUT else "NULL",
    )


@pytest.fixture
def ctx_project(project: Path) -> Path:
    """A real Verilog project with the FABulous context initialised on it."""
    init_context(project)
    return project


@pytest.fixture
def requires_yosys() -> None:
    """Skip the test unless the yosys binary is on PATH."""
    if shutil.which(str(get_context().yosys_path)) is None:
        pytest.skip("yosys not on PATH; BEL parsing needs the Nix toolchain")


# --------------------------------------------------------------------------- #
# generateSwitchmatrixList
# --------------------------------------------------------------------------- #


def test_switchmatrix_happy_path(ctx_project: Path) -> None:
    """A small BEL yields a parseable list with the BEL ports and a prims stub."""
    out = ctx_project / "Tile" / "T_switch_matrix.list"
    out.parent.mkdir(parents=True, exist_ok=True)
    bel = make_bel(inputs=("in0", "in1", "in2", "in3"), outputs=("out0",))

    generateSwitchmatrixList("T", [bel], out, {}, {})

    text = out.read_text()
    assert text.startswith("# --------------WARNING")
    # Every BEL port must be routed into the matrix.
    for port in ("in0", "in1", "in2", "in3", "out0"):
        assert port in text
    # The result must re-parse as a valid list.
    assert parseList(out)
    prims = (ctx_project / "user_design" / "custom_prims.v").read_text()
    assert "module B" in prims


@pytest.mark.parametrize(
    ("inputs", "outputs", "limit"), [(33, 1, "32"), (1, 9, "8")], ids=["in", "out"]
)
def test_switchmatrix_too_many_ports(
    ctx_project: Path, inputs: int, outputs: int, limit: str
) -> None:
    """More than 32 BEL inputs or 8 BEL outputs is rejected."""
    bel = make_bel(
        inputs=tuple(f"in{i}" for i in range(inputs)),
        outputs=tuple(f"out{i}" for i in range(outputs)),
    )
    with pytest.raises(ValueError, match=limit):
        generateSwitchmatrixList("T", [bel], ctx_project / "over.list", {}, {})


def test_switchmatrix_carry_prefix_mismatch(ctx_project: Path) -> None:
    """Carry prefixes declared on the tile but absent from the BELs are rejected."""
    out = ctx_project / "mismatch.list"
    bel = make_bel(inputs=("in0",), outputs=("out0",))
    carryports_tile = {"ch": {IO.INPUT: "Ci_t", IO.OUTPUT: "Co_t"}}
    # The production code raises a message-less `ValueError` here, so there is
    # nothing to match on.
    with pytest.raises(ValueError):  # noqa: PT011
        generateSwitchmatrixList("T", [bel], out, carryports_tile, {})


def test_switchmatrix_carry_wiring(ctx_project: Path) -> None:
    """A matching carry prefix emits the carry-chain connection block."""
    out = ctx_project / "carry.list"
    bel = make_bel(
        inputs=("in0",),
        outputs=("out0",),
        carry={"ch": {IO.INPUT: "Ci", IO.OUTPUT: "Co"}},
    )
    carryports_tile = {"ch": {IO.INPUT: "Ci_t", IO.OUTPUT: "Co_t"}}

    generateSwitchmatrixList("T", [bel], out, carryports_tile, {})

    text = out.read_text()
    assert "# Connect carry chain ch" in text
    assert "Ci,Ci_t" in text
    assert "Co_t,Co" in text


def test_switchmatrix_shared_reset_enable(ctx_project: Path) -> None:
    """Shared reset/enable BEL ports are wired to the tile shared ports."""
    out = ctx_project / "shared.list"
    bel = make_bel(
        inputs=("in0",),
        outputs=("out0",),
        local={"RESET": ("SR", IO.INPUT), "ENABLE": ("EN", IO.INPUT)},
    )
    local_shared_tile = {
        "RESET": [tile_port("LR0", IO.OUTPUT), tile_port("LR1", IO.INPUT)],
        "ENABLE": [tile_port("LE0", IO.OUTPUT), tile_port("LE1", IO.INPUT)],
    }

    generateSwitchmatrixList("T", [bel], out, {}, local_shared_tile)

    text = out.read_text()
    assert "# Connect shared reset" in text
    assert "{2}SR,[LR10|GND0]" in text
    assert "# Connect shared enable" in text
    assert "{2}EN,[LE10|VCC0]" in text


# --------------------------------------------------------------------------- #
# addBelsToPrim
# --------------------------------------------------------------------------- #


def test_prim_stub_emitted(tmp_path: Path) -> None:
    """A fresh prims file gains a blackbox module with the BEL ports."""
    prims = tmp_path / "custom_prims.v"
    bel = make_bel(module_name="MYBEL", inputs=("a", "b"), outputs=("y",))

    addBelsToPrim(prims, [bel])

    text = prims.read_text()
    assert "(* blackbox, keep *)" in text
    assert "module MYBEL (" in text
    assert "input a" in text
    assert "output y" in text


def test_prim_dedup(tmp_path: Path) -> None:
    """A module already present is not written a second time."""
    prims = tmp_path / "custom_prims.v"
    bel = make_bel(module_name="MYBEL", inputs=("a",), outputs=("y",))

    addBelsToPrim(prims, [bel])
    addBelsToPrim(prims, [bel])

    assert prims.read_text().count("module MYBEL (") == 1


def test_prim_userclk_renamed(tmp_path: Path) -> None:
    """A shared `UserCLK` port is emitted as `CLK` for yosys mapping."""
    prims = tmp_path / "custom_prims.v"
    bel = make_bel(
        module_name="CLKBEL",
        inputs=("a",),
        outputs=("y",),
        shared=(("UserCLK", IO.INPUT),),
    )

    addBelsToPrim(prims, [bel])

    text = prims.read_text()
    assert "input CLK" in text
    assert "UserCLK" not in text


def test_prim_params(tmp_path: Path) -> None:
    """BEL feature-map entries become module parameters."""
    prims = tmp_path / "custom_prims.v"
    bel = make_bel(
        module_name="PBEL",
        inputs=("a",),
        outputs=("y",),
        belMap={"A_reg": {}, "B_reg": {}},
    )

    addBelsToPrim(prims, [bel])

    text = prims.read_text()
    assert "parameter A_reg = 0;" in text
    assert "parameter B_reg = 0;" in text


# --------------------------------------------------------------------------- #
# generateCustomTileConfig  (needs yosys to parse the BEL HDL)
# --------------------------------------------------------------------------- #


def _custom_tile_dir(project: Path, name: str = "CustomTile") -> Path:
    """Create ``Tile/<name>/`` under the project and drop the LUT4c BEL in it."""
    tile_dir = project / "Tile" / name
    tile_dir.mkdir(parents=True)
    shutil.copy(project / "Tile" / "LUT4AB" / LUT4C, tile_dir / LUT4C)
    return tile_dir


@pytest.mark.usefixtures("requires_yosys")
def test_custom_tile_config_happy(ctx_project: Path) -> None:
    """A tile folder with one BEL produces the expected tile CSV."""
    tile_dir = _custom_tile_dir(ctx_project)

    csv_path = generateCustomTileConfig(tile_dir)

    assert csv_path == tile_dir / "CustomTile.csv"
    lines = csv_path.read_text().splitlines()
    assert lines[0] == "TILE,CustomTile"
    assert "INCLUDE,./../include/Base.csv" in lines
    assert f"BEL,./{LUT4C}" in lines
    assert "MATRIX,GENERATE" in lines
    assert lines[-1] == "EndTILE"


@pytest.mark.usefixtures("requires_yosys")
def test_custom_tile_config_existing_list(ctx_project: Path) -> None:
    """An existing (non-generated) list file is referenced instead of GENERATE."""
    tile_dir = _custom_tile_dir(ctx_project)
    (tile_dir / "mymatrix.list").write_text("# hand-written\n")

    csv_path = generateCustomTileConfig(tile_dir)

    lines = csv_path.read_text().splitlines()
    assert "MATRIX,mymatrix.list" in lines
    assert "MATRIX,GENERATE" not in lines


@pytest.mark.usefixtures("requires_yosys")
def test_custom_tile_config_generated_file_ignored(ctx_project: Path) -> None:
    """A ``*switch_matrix*`` file is never treated as a BEL.

    It is still referenced as the tile matrix, because it matches the default
    ``<tile>_switch_matrix.list`` name the generator looks for.
    """
    tile_dir = _custom_tile_dir(ctx_project)
    (tile_dir / "CustomTile_switch_matrix.list").write_text("# stale\n")

    csv_path = generateCustomTileConfig(tile_dir)

    lines = csv_path.read_text().splitlines()
    bel_lines = [line for line in lines if line.startswith("BEL,")]
    assert bel_lines == [f"BEL,./{LUT4C}"]
    assert "MATRIX,CustomTile_switch_matrix.list" in lines


@pytest.mark.usefixtures("requires_yosys")
def test_custom_tile_config_existing_csv_returns_early(ctx_project: Path) -> None:
    """A pre-existing tile CSV short-circuits generation and is returned as-is."""
    tile_dir = _custom_tile_dir(ctx_project)
    existing = tile_dir / "CustomTile.csv"
    existing.write_text("TILE,PreExisting\nEndTILE")

    result = generateCustomTileConfig(tile_dir)

    assert result == existing
    assert existing.read_text() == "TILE,PreExisting\nEndTILE"


@pytest.mark.usefixtures("ctx_project")
def test_custom_tile_config_rejects_path_outside_tile_dir(tmp_path: Path) -> None:
    """A path outside the project `Tile` directory is rejected."""
    outside = tmp_path / "outside"
    outside.mkdir()
    with pytest.raises(ValueError, match="not a valid tile path"):
        generateCustomTileConfig(outside)

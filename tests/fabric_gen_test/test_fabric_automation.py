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
`generate_switch_matrix_list` level below. Add a synthetic attributed BEL if that
CSV branch ever gains real logic.
"""

import shutil
from pathlib import Path

import pytest
from pytest_mock import MockerFixture

from fabulous.fabric_definition.bel import Bel
from fabulous.fabric_definition.define import (
    IO,
    BelRole,
    ConfigBitMode,
    Direction,
    Side,
)
from fabulous.fabric_definition.port import TilePort
from fabulous.fabric_definition.supertile import SuperTile
from fabulous.fabric_generator.gen_fabric.fabric_automation import (
    addBelsToPrim,
    existing_tile_outputs,
    generate_custom_supertile_config,
    generate_switch_matrix_list,
    generateCustomTileConfig,
    is_supertile_csv,
)
from fabulous.fabric_generator.parser.parse_csv import (
    parse_tile_from_dir,
    parseTilesCSV,
)
from fabulous.fabric_generator.parser.parse_switchmatrix import parseList
from fabulous.fabulous_settings import get_context, init_context

LUT4C = "LUT4c_frame_config_dffesr.v"
MULADD_SRC = (
    Path(__file__).parents[2]
    / "fabulous/fabric_files/FABulous_project_template_verilog"
    / "Tile/DSP/DSP_bot/MULADD.v"
)
MULADD_VHDL_SRC = (
    Path(__file__).parents[2]
    / "fabulous/fabric_files/FABulous_project_template_vhdl"
    / "Tile/DSP/DSP_bot/MULADD.vhdl"
)
PARSE = "fabulous.fabric_generator.gen_fabric.fabric_automation.parseBelFile"


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
    src: Path | None = None,
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
        src=src or Path(f"{name}.v"),
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
        role=BelRole.OTHER,
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
# generate_switch_matrix_list
# --------------------------------------------------------------------------- #


def test_switchmatrix_happy_path(ctx_project: Path) -> None:
    """A small BEL yields a parseable list with the BEL ports and a prims stub."""
    out = ctx_project / "Tile" / "T_switch_matrix.list"
    out.parent.mkdir(parents=True, exist_ok=True)
    bel = make_bel(inputs=("in0", "in1", "in2", "in3"), outputs=("out0",))

    generate_switch_matrix_list("T", [bel], out, {}, {})

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
        generate_switch_matrix_list("T", [bel], ctx_project / "over.list", {}, {})


def test_switchmatrix_carry_prefix_mismatch(ctx_project: Path) -> None:
    """Carry prefixes declared on the tile but absent from the BELs are rejected."""
    out = ctx_project / "mismatch.list"
    bel = make_bel(inputs=("in0",), outputs=("out0",))
    carryports_tile = {"ch": {IO.INPUT: "Ci_t", IO.OUTPUT: "Co_t"}}
    # The production code raises a message-less `ValueError` here, so there is
    # nothing to match on.
    with pytest.raises(ValueError):  # noqa: PT011
        generate_switch_matrix_list("T", [bel], out, carryports_tile, {})


def test_switchmatrix_carry_wiring(ctx_project: Path) -> None:
    """A matching carry prefix emits the carry-chain connection block."""
    out = ctx_project / "carry.list"
    bel = make_bel(
        inputs=("in0",),
        outputs=("out0",),
        carry={"ch": {IO.INPUT: "Ci", IO.OUTPUT: "Co"}},
    )
    carryports_tile = {"ch": {IO.INPUT: "Ci_t", IO.OUTPUT: "Co_t"}}

    generate_switch_matrix_list("T", [bel], out, carryports_tile, {})

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

    generate_switch_matrix_list("T", [bel], out, {}, local_shared_tile)

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
    """Create `Tile/<name>/` under the project and drop the LUT4c BEL in it."""
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
    assert "MATRIX,./CustomTile_switch_matrix.list" in lines
    assert lines[-1] == "EndTILE"
    matrix = (tile_dir / "CustomTile_switch_matrix.list").read_text()
    assert "# This is a generated list file!" in matrix


@pytest.mark.usefixtures("requires_yosys")
def test_switch_matrix_list_regenerated_only_on_request(ctx_project: Path) -> None:
    """Parsing keeps an edited list; only `generate_matrix_list=True` rewrites it."""
    tile_dir = _custom_tile_dir(ctx_project)
    csv_path = generateCustomTileConfig(tile_dir)
    matrix = tile_dir / "CustomTile_switch_matrix.list"
    edited = matrix.read_text() + "\n# my edit\n"
    matrix.write_text(edited)

    parseTilesCSV(csv_path)
    assert matrix.read_text() == edited

    parseTilesCSV(csv_path, generate_matrix_list=True)
    assert "# my edit" not in matrix.read_text()


@pytest.mark.usefixtures("requires_yosys")
def test_custom_tile_config_without_switch_matrix(ctx_project: Path) -> None:
    """`switch_matrix=False` references the default list but leaves it to the user."""
    tile_dir = _custom_tile_dir(ctx_project)

    csv_path = generateCustomTileConfig(tile_dir, switch_matrix=False)

    assert "MATRIX,./CustomTile_switch_matrix.list" in csv_path.read_text()
    assert not (tile_dir / "CustomTile_switch_matrix.list").exists()


@pytest.mark.usefixtures("requires_yosys")
@pytest.mark.parametrize("name", ["mymatrix.list", "custom_switch_matrix.list"])
def test_custom_tile_config_existing_list(ctx_project: Path, name: str) -> None:
    """An existing (non-generated) list file is referenced, not regenerated."""
    tile_dir = _custom_tile_dir(ctx_project)
    (tile_dir / name).write_text("# hand-written\n")

    csv_path = generateCustomTileConfig(tile_dir)

    lines = csv_path.read_text().splitlines()
    assert f"MATRIX,./{name}" in lines
    assert (tile_dir / name).read_text() == "# hand-written\n"
    assert not (tile_dir / "CustomTile_switch_matrix.list").exists()


@pytest.mark.usefixtures("requires_yosys")
@pytest.mark.parametrize(
    "earlier",
    [
        "CustomTile.csv",
        "CustomTile_switch_matrix.list",
        # Written by the removed MATRIX,GENERATE flow.
        "CustomTile_generated_switch_matrix.list",
    ],
    ids=["csv", "list", "legacy-list"],
)
def test_custom_tile_config_replaces_earlier_output_on_request(
    ctx_project: Path, earlier: str
) -> None:
    """Earlier output is only replaced with `overwrite`, and is never a BEL."""
    tile_dir = _custom_tile_dir(ctx_project)
    (tile_dir / earlier).write_text("# earlier\n")

    with pytest.raises(FileExistsError, match="overwrite"):
        generateCustomTileConfig(tile_dir)
    assert (tile_dir / earlier).read_text() == "# earlier\n"

    csv_path = generateCustomTileConfig(tile_dir, overwrite=True)

    lines = csv_path.read_text().splitlines()
    assert [line for line in lines if line.startswith("BEL,")] == [f"BEL,./{LUT4C}"]
    assert "MATRIX,./CustomTile_switch_matrix.list" in lines
    matrix = (tile_dir / "CustomTile_switch_matrix.list").read_text()
    assert "# This is a generated list file!" in matrix
    assert not (tile_dir / "CustomTile_generated_switch_matrix.list").exists()


@pytest.mark.usefixtures("ctx_project")
def test_custom_tile_config_rejects_path_outside_tile_dir(tmp_path: Path) -> None:
    """A path outside the project `Tile` directory is rejected."""
    outside = tmp_path / "outside"
    outside.mkdir()
    with pytest.raises(ValueError, match="not a valid tile path"):
        generateCustomTileConfig(outside)


# --------------------------------------------------------------------------- #
# Supertile generation
# --------------------------------------------------------------------------- #


def _supertile_dir(project: Path, name: str = "WideTile") -> Path:
    """Create `Tile/<name>/` under the project for supertile generation."""
    d = project / "Tile" / name
    d.mkdir(parents=True)
    return d


def _wide_bel(
    src: Path,
    inputs: int = 1,
    outputs: int = 20,
    carry: dict[str, dict[IO, str]] | None = None,
    local: dict[str, tuple[str, IO]] | None = None,
) -> Bel:
    """A BEL in `src` with `inputs` inputs and `outputs` outputs."""
    return make_bel(
        name="WIDE",
        module_name="WIDE",
        inputs=tuple(f"in{i}" for i in range(inputs)),
        outputs=tuple(f"out{i}" for i in range(outputs)),
        src=src,
        carry=carry,
        local=local,
    )


def test_supertile_split_shape(ctx_project: Path) -> None:
    """A wide BEL is split into N subtiles within the per-subtile 32/8 budget."""
    tile_dir = _supertile_dir(ctx_project)
    bel = _wide_bel(tile_dir / "WIDE.v", inputs=36)

    csv_path = generate_custom_supertile_config(tile_dir, bel)

    assert csv_path == tile_dir / "WideTile.csv"
    lines = csv_path.read_text().splitlines()
    assert lines[0] == "SuperTILE,WideTile"
    assert lines[-1] == "EndSuperTILE"
    assert "BEL,./WIDE.v" in lines
    assert "MATRIX,./WideTile_switch_matrix.list" in lines

    # N = max(ceil(36/32), ceil(20/8)) = 3 subtiles.
    sub_rows = [ln for ln in lines if ln.startswith("WideTile_sub")]
    assert sub_rows == ["WideTile_sub0", "WideTile_sub1", "WideTile_sub2"]

    si_total, so_total = 0, 0
    for sub in sub_rows:
        sub_lines = (tile_dir / sub / f"{sub}.csv").read_text().splitlines()
        si = next((ln for ln in sub_lines if ln.startswith("SJUMP,SI")), "")
        so = next((ln for ln in sub_lines if ln.startswith("SJUMP,NULL,0,0,SO")), "")
        si_w = int(si.split(",")[5])
        so_w = int(so.split(",")[5])
        assert si_w <= 32
        assert so_w <= 8
        si_total += si_w
        so_total += so_w
        assert (tile_dir / sub / f"{sub}_switch_matrix.list").is_file()
    assert si_total == 36
    assert so_total == 20


def test_supertile_matrix_is_one_to_one(ctx_project: Path) -> None:
    """The supertile matrix maps every BEL port exactly once, 1:1, no muxes."""
    tile_dir = _supertile_dir(ctx_project)
    bel = _wide_bel(tile_dir / "WIDE.v", inputs=36)

    generate_custom_supertile_config(tile_dir, bel)

    pairs = [
        ln.split(",")
        for ln in (tile_dir / "WideTile_switch_matrix.list").read_text().splitlines()
        if ln.strip()
    ]
    assert all(len(p) == 2 for p in pairs)  # 1:1, no bracket muxes
    input_names = [p.name for p in bel.input_ports]
    output_names = [p.name for p in bel.output_ports]
    # BEL inputs are sinks (field0); BEL outputs are sources (field1).
    input_sinks = [p[0] for p in pairs if p[0] in input_names]
    output_sources = [p[1] for p in pairs if p[1] in output_names]
    assert sorted(input_sinks) == sorted(input_names)
    assert sorted(output_sources) == sorted(output_names)


@pytest.mark.parametrize(
    ("carry", "local"),
    [
        ({"ch": {IO.INPUT: "Ci", IO.OUTPUT: "Co"}}, None),
        (None, {"RESET": ("SR", IO.INPUT)}),
        (None, {"ENABLE": ("EN", IO.INPUT)}),
    ],
    ids=["carry", "shared-reset", "shared-enable"],
)
def test_supertile_rejects_carry_and_shared(
    ctx_project: Path,
    mocker: MockerFixture,
    carry: dict[str, dict[IO, str]] | None,
    local: dict[str, tuple[str, IO]] | None,
) -> None:
    """Carry and shared reset/enable on a wide BEL are not yet supported."""
    tile_dir = _supertile_dir(ctx_project)
    (tile_dir / "WIDE.v").write_text("module WIDE(); endmodule\n")
    mocker.patch(
        PARSE, return_value=_wide_bel(tile_dir / "WIDE.v", 33, 1, carry, local)
    )

    with pytest.raises(NotImplementedError, match="not yet supported"):
        generateCustomTileConfig(tile_dir)


def test_supertile_bel_path_is_relative_to_tile(ctx_project: Path) -> None:
    """A BEL in a subfolder of the tile keeps that subfolder in the CSV."""
    tile_dir = _supertile_dir(ctx_project)

    csv_path = generate_custom_supertile_config(
        tile_dir, _wide_bel(tile_dir / "rtl" / "WIDE.v")
    )

    assert "BEL,./rtl/WIDE.v" in csv_path.read_text().splitlines()


def test_regenerated_supertile_drops_stale_output(
    ctx_project: Path, mocker: MockerFixture
) -> None:
    """Regenerating a supertile removes the subtiles and RTL of the earlier run."""
    tile_dir = _supertile_dir(ctx_project)
    (tile_dir / "WIDE.v").write_text("module WIDE(); endmodule\n")
    parse = mocker.patch(PARSE, return_value=_wide_bel(tile_dir / "WIDE.v"))
    generateCustomTileConfig(tile_dir)
    # What gen_tile leaves behind.
    (tile_dir / "WideTile.v").touch()
    (tile_dir / "WideTile_switch_matrix.v").touch()
    (tile_dir / "WideTile_config_mem.csv").touch()
    (tile_dir / "WideTile_sub0" / "WideTile_sub0.v").touch()
    # A user folder that only looks like a subtile.
    (tile_dir / "WideTile_subsystem").mkdir()

    parse.return_value = _wide_bel(tile_dir / "WIDE.v", outputs=12)
    generateCustomTileConfig(tile_dir, overwrite=True)

    sub_dirs = sorted(d.name for d in tile_dir.iterdir() if d.is_dir())
    assert sub_dirs == ["WideTile_sub0", "WideTile_sub1", "WideTile_subsystem"]
    assert not (tile_dir / "WideTile.v").exists()
    assert (tile_dir / "WIDE.v").is_file()
    # Only the real BEL was parsed, not the generated RTL.
    assert [c.args[0].name for c in parse.call_args_list[1:]] == ["WIDE.v"]


@pytest.mark.parametrize("outputs", [12, 4], ids=["supertile", "single-tile"])
def test_regeneration_refreshes_prim_stub(
    ctx_project: Path, mocker: MockerFixture, outputs: int
) -> None:
    """A first generation keeps an existing stub; a regeneration replaces it."""
    prims_file = ctx_project / "user_design" / "custom_prims.v"
    hand = "module WIDE (input in0);\nendmodule\n"
    prims_file.write_text(hand)
    tile_dir = _supertile_dir(ctx_project)
    (tile_dir / "WIDE.v").write_text("module WIDE(); endmodule\n")
    parse = mocker.patch(PARSE, return_value=_wide_bel(tile_dir / "WIDE.v"))
    generateCustomTileConfig(tile_dir)
    assert prims_file.read_text() == hand

    parse.return_value = _wide_bel(tile_dir / "WIDE.v", outputs=outputs)
    # The single tile's list generation parses the BEL again, through parse_csv.
    mocker.patch(
        "fabulous.fabric_generator.parser.parse_csv.parseBelFile",
        return_value=parse.return_value,
    )
    generateCustomTileConfig(tile_dir, overwrite=True)

    prims = prims_file.read_text()
    assert f"out{outputs - 1}" in prims
    assert f"out{outputs}" not in prims


def test_regeneration_adds_no_stub_without_switch_matrix(
    ctx_project: Path, mocker: MockerFixture
) -> None:
    """Without a generated switch matrix, BELs get no stub, also on regeneration."""
    prims_file = ctx_project / "user_design" / "custom_prims.v"
    prims_file.write_text("// mine\n")
    tile_dir = _supertile_dir(ctx_project)
    (tile_dir / "WIDE.v").write_text("module WIDE(); endmodule\n")
    mocker.patch(PARSE, return_value=_wide_bel(tile_dir / "WIDE.v", outputs=4))
    generateCustomTileConfig(tile_dir, switch_matrix=False)
    generateCustomTileConfig(tile_dir, switch_matrix=False, overwrite=True)

    assert prims_file.read_text() == "// mine\n"


def test_failed_regeneration_restores_earlier_output(
    ctx_project: Path, mocker: MockerFixture
) -> None:
    """If writing the new output fails, the earlier output is put back."""
    tile_dir = _supertile_dir(ctx_project)
    (tile_dir / "WIDE.v").write_text("module WIDE(); endmodule\n")
    mocker.patch(PARSE, return_value=_wide_bel(tile_dir / "WIDE.v"))
    generateCustomTileConfig(tile_dir)
    before = {
        p.relative_to(tile_dir): p.read_bytes()
        for p in tile_dir.rglob("*")
        if p.is_file()
    }

    def fail_halfway(path: Path, _bel: Bel) -> Path:
        (path / "WideTile_sub0").mkdir()
        (path / "WideTile.csv").write_text("half\n")
        raise OSError("disk full")

    mocker.patch(
        "fabulous.fabric_generator.gen_fabric.fabric_automation."
        "generate_custom_supertile_config",
        side_effect=fail_halfway,
    )
    with pytest.raises(OSError, match="disk full"):
        generateCustomTileConfig(tile_dir, overwrite=True)

    after = {
        p.relative_to(tile_dir): p.read_bytes()
        for p in tile_dir.rglob("*")
        if p.is_file()
    }
    assert after == before


def test_rejected_regeneration_does_not_ask_first(
    ctx_project: Path, mocker: MockerFixture
) -> None:
    """A regeneration that cannot go ahead fails as such, not as an overwrite."""
    tile_dir = _supertile_dir(ctx_project)
    (tile_dir / "WIDE.v").write_text("module WIDE(); endmodule\n")
    mocker.patch(PARSE, return_value=_wide_bel(tile_dir / "WIDE.v"))
    generateCustomTileConfig(tile_dir)

    with pytest.raises(ValueError, match="need a supertile"):
        generateCustomTileConfig(tile_dir, switch_matrix=False)


def test_custom_tile_config_counts_ports_per_bel(
    ctx_project: Path, mocker: MockerFixture
) -> None:
    """BELs sharing port names still each need their own switch matrix pins."""
    tile_dir = _supertile_dir(ctx_project)
    for name in ("A", "B"):
        (tile_dir / f"{name}.v").write_text(f"module {name}(); endmodule\n")
    mocker.patch(PARSE, return_value=_wide_bel(tile_dir / "A.v", inputs=20, outputs=1))

    with pytest.raises(NotImplementedError, match="exactly one wide BEL"):
        generateCustomTileConfig(tile_dir)

    assert not (tile_dir / "WideTile.csv").exists()


def test_supertile_rejects_bel_named_like_tile(
    ctx_project: Path, mocker: MockerFixture
) -> None:
    """A BEL file named after the tile would be overwritten by the wrapper RTL."""
    tile_dir = _supertile_dir(ctx_project)
    (tile_dir / "WideTile.v").write_text("module WIDE(); endmodule\n")
    mocker.patch(PARSE, return_value=_wide_bel(tile_dir / "WideTile.v"))

    with pytest.raises(ValueError, match="Rename the BEL file"):
        generateCustomTileConfig(tile_dir)

    assert [f.name for f in tile_dir.iterdir()] == ["WideTile.v"]


@pytest.mark.parametrize(
    "user_file",
    ["WideTile_sub0/notes.txt", "WideTile_switch_matrix.list"],
    ids=["subtile-folder", "matrix-list"],
)
def test_supertile_needs_overwrite_for_existing_paths(
    ctx_project: Path, mocker: MockerFixture, user_file: str
) -> None:
    """A path generation would replace stops it unless `overwrite` is given."""
    tile_dir = _supertile_dir(ctx_project)
    (tile_dir / "WIDE.v").write_text("module WIDE(); endmodule\n")
    mocker.patch(PARSE, return_value=_wide_bel(tile_dir / "WIDE.v"))
    user_path = tile_dir / user_file
    user_path.parent.mkdir(exist_ok=True)
    user_path.write_text("mine\n")

    with pytest.raises(FileExistsError, match=user_file.split("/")[0]):
        generateCustomTileConfig(tile_dir)

    assert user_path.read_text() == "mine\n"
    assert not (tile_dir / "WideTile.csv").exists()


@pytest.mark.parametrize("ext", ["v", "vhdl"])
def test_existing_tile_outputs_lists_tile_rtl(tmp_path: Path, ext: str) -> None:
    """`<name>.<ext>` is tile RTL only next to the switch matrix RTL gen_tile wrote."""
    tile_dir = tmp_path / "T"
    tile_dir.mkdir()
    (tile_dir / f"T.{ext}").write_text("")
    assert existing_tile_outputs(tile_dir) == []

    (tile_dir / f"T_switch_matrix.{ext}").write_text("")
    assert existing_tile_outputs(tile_dir) == [
        tile_dir / f"T.{ext}",
        tile_dir / f"T_switch_matrix.{ext}",
    ]


def test_supertile_include_follows_nested_tile_dir(ctx_project: Path) -> None:
    """Subtiles of a tile nested below `Tile/` still find `Base.csv`."""
    tile_dir = _supertile_dir(ctx_project, "custom/WideTile")

    generate_custom_supertile_config(tile_dir, _wide_bel(tile_dir / "WIDE.v"))

    sub_csv = (tile_dir / "WideTile_sub0" / "WideTile_sub0.csv").read_text()
    assert "INCLUDE,../../../include/Base.csv" in sub_csv.splitlines()
    assert (tile_dir / "WideTile_sub0" / "../../../include/Base.csv").is_file()


def test_custom_tile_config_rejects_supertile_when_not_allowed(
    ctx_project: Path, mocker: MockerFixture
) -> None:
    """With `switch_matrix=False` a wide BEL fails before anything is written."""
    tile_dir = _supertile_dir(ctx_project)
    (tile_dir / "WIDE.v").write_text("module WIDE(); endmodule\n")
    mocker.patch(PARSE, return_value=_wide_bel(tile_dir / "WIDE.v"))

    with pytest.raises(ValueError, match="need a supertile"):
        generateCustomTileConfig(tile_dir, switch_matrix=False)

    assert sorted(p.name for p in tile_dir.iterdir()) == ["WIDE.v"]


def test_custom_tile_config_skips_vhdl_conversion_output(
    ctx_project: Path, mocker: MockerFixture
) -> None:
    """The `.v` that BEL parsing writes next to a VHDL BEL is not a second BEL."""
    tile_dir = _supertile_dir(ctx_project)
    (tile_dir / "WIDE.vhdl").write_text("-- VHDL BEL\n")
    (tile_dir / "WIDE.v").write_text("module WIDE(); endmodule\n")
    parse = mocker.patch(PARSE, return_value=_wide_bel(tile_dir / "WIDE.vhdl"))

    generateCustomTileConfig(tile_dir)

    assert [c.args[0].name for c in parse.call_args_list] == ["WIDE.vhdl"]


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("SuperTILE,X\nX_sub0\nEndSuperTILE", True),
        ("# notes\n\nSuperTILE,X # trailing\nEndSuperTILE", True),
        ("TILE,X\nEndTILE", False),
        ("# SuperTILE,X\nTILE,X\nEndTILE", False),
    ],
    ids=["plain", "comment-header", "tile", "commented-out"],
)
def test_is_supertile_csv(tmp_path: Path, text: str, expected: bool) -> None:
    """Supertile CSVs are recognised with comments stripped like the parser does."""
    csv = tmp_path / "X.csv"
    csv.write_text(text)
    assert is_supertile_csv(csv) is expected


@pytest.mark.parametrize("change", ["second-bel", "carry"])
def test_rejected_regeneration_keeps_earlier_output(
    ctx_project: Path, mocker: MockerFixture, change: str
) -> None:
    """A regeneration that is rejected leaves the earlier supertile in place."""
    tile_dir = _supertile_dir(ctx_project)
    (tile_dir / "WIDE.v").write_text("module WIDE(); endmodule\n")
    parse = mocker.patch(PARSE, return_value=_wide_bel(tile_dir / "WIDE.v"))
    generateCustomTileConfig(tile_dir)

    if change == "second-bel":
        (tile_dir / "WIDE2.v").write_text("module WIDE2(); endmodule\n")
    else:
        parse.return_value = _wide_bel(
            tile_dir / "WIDE.v", carry={"ch": {IO.INPUT: "Ci", IO.OUTPUT: "Co"}}
        )
    with pytest.raises(NotImplementedError):
        generateCustomTileConfig(tile_dir, overwrite=True)

    assert (tile_dir / "WideTile.csv").is_file()
    sub_dirs = sorted(d.name for d in tile_dir.glob("WideTile_sub*"))
    assert sub_dirs == ["WideTile_sub0", "WideTile_sub1", "WideTile_sub2"]


def test_custom_tile_config_ignores_dedicated_ports_for_budget(
    ctx_project: Path, mocker: MockerFixture
) -> None:
    """Carry / shared ports do not count towards the 32-in / 8-out split trigger.

    They get dedicated wiring instead of a switch-matrix slot, so a BEL that is
    only over budget because of them still fits into a single tile.
    """
    tile_dir = _custom_tile_dir(ctx_project, "AtBudget")
    bel = make_bel(
        name="AT_BUDGET",
        module_name="AT_BUDGET",
        inputs=tuple(f"in{i}" for i in range(32)),
        outputs=tuple(f"out{i}" for i in range(8)),
        carry={"ch": {IO.INPUT: "Ci", IO.OUTPUT: "Co"}},
    )
    # 33 raw inputs / 9 raw outputs, but only 32 / 8 of them are routable.
    assert len(bel.input_ports) == 33
    assert len(bel.output_ports) == 9
    mocker.patch(PARSE, return_value=bel)

    # The mocked BEL has no HDL behind it to build a switch matrix from.
    csv_path = generateCustomTileConfig(tile_dir, switch_matrix=False)

    lines = csv_path.read_text().splitlines()
    assert lines[0] == "TILE,AtBudget"
    assert 'NORTH,Co0,0,-1,Ci0,1,CARRY="ch"' in lines
    assert not list(tile_dir.glob("AtBudget_sub*"))


@pytest.mark.usefixtures("requires_yosys")
def test_generated_supertile_parses_and_validates(ctx_project: Path) -> None:
    """A BEL over budget becomes a supertile that parses and validates."""
    tile_dir = ctx_project / "Tile" / "DSPblk"
    tile_dir.mkdir(parents=True)
    shutil.copy(MULADD_SRC, tile_dir / "MULADD.v")
    assert generateCustomTileConfig(tile_dir) == tile_dir / "DSPblk.csv"
    prims = (ctx_project / "user_design" / "custom_prims.v").read_text()
    assert "module MULADD" in prims

    # parse_tile_from_dir runs parseSupertilesCSV + validate_super_tile_matrix.
    super_tile = parse_tile_from_dir(
        tile_dir,
        "DSPblk",
        is_supertile=True,
        config_bit_mode=ConfigBitMode.FRAME_BASED,
        frame_bits_per_row=32,
        max_frames_per_col=20,
    )

    assert isinstance(super_tile, SuperTile)
    assert super_tile.name == "DSPblk"
    assert [t.name for t in super_tile.tiles] == [
        "DSPblk_sub0",
        "DSPblk_sub1",
        "DSPblk_sub2",
    ]
    assert super_tile.switch_matrix is not None
    # 1:1 concat matrix carries no config bits; all config is the BEL's own.
    assert super_tile.supertile_matrix_config_bits == 0
    assert super_tile.total_config_bits == super_tile.bels[0].configBit

from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace

import pytest
from pytest_mock import MockerFixture

import fabulous.fabric_cad.timing_model.FABulous_timing_model as tm_mod
from fabulous.fabric_cad.timing_model.FABulous_timing_model import (
    FABulousTileTimingModel,
)
from fabulous.fabric_cad.timing_model.models import (
    DelayType,
    InternalPipCacheEntry,
    TimingModelMode,
)
from fabulous.fabric_cad.timing_model.netlist import NetlistIndex
from fabulous.fabric_definition.supertile import SuperTile
from tests.conftest import make_empty_tile, make_fabric_from_grid
from tests.timing_model_test.conftest import ReadNetlist


def make_source_override(
    *,
    rtl_files: Path | list[Path] | None = None,
    netlist_file: Path | None = None,
    rc_file: Path | None = None,
) -> SimpleNamespace:
    return SimpleNamespace(
        rtl_files=rtl_files,
        netlist_file=netlist_file,
        rc_file=rc_file,
    )


def make_config(
    tmp_path: Path,
    *,
    mode: TimingModelMode = TimingModelMode.STRUCTURAL,
    consider_wire_delay: bool = False,
    liberty_files: list[Path] | Path | None = None,
    techmap_files: list[Path] | Path | None = None,
    custom_per_tile_source_files: dict[str, SimpleNamespace] | None = None,
    delay_scaling_factor: Decimal = Decimal(1),
) -> SimpleNamespace:
    return SimpleNamespace(
        project_dir=tmp_path,
        liberty_files=[tmp_path / "lib.lib"]
        if liberty_files is None
        else liberty_files,
        delay_type_str=DelayType.MAX_ALL,
        techmap_files=techmap_files,
        tiehi_cell_and_port="TIEHI Y",
        tielo_cell_and_port="TIELO Y",
        min_buf_cell_and_ports="BUF A Y",
        consider_wire_delay=consider_wire_delay,
        mode=mode,
        custom_per_tile_source_files=custom_per_tile_source_files,
        delay_scaling_factor=delay_scaling_factor,
    )


class DummyFabric:
    def __init__(self, unique_tiles: list[object]) -> None:
        self._unique_tiles = unique_tiles

    def get_all_unique_tiles(self) -> list[object]:
        return self._unique_tiles


class DummyTile:
    def __init__(self, name: object) -> None:
        self.name = name


class DummySuperTile:
    def __init__(self, name: object, tiles: object) -> None:
        self.name = name
        self.tiles = tiles


class DummyHdlnx:
    def __init__(self) -> None:
        self.output_ports = set()
        self.input_ports = set()

    def single_delay(self, _src: object, _dst: object) -> Decimal:
        return Decimal("0.0")

    def nearest_ports_from_pins(
        self,
        net_pins: dict[str, list[str]],
        reverse: bool = False,
        num_ports: int = 1,
    ) -> tuple[dict[str, list[str]], list[str]]:
        _ = (net_pins, reverse, num_ports)
        return {}, []

    def earliest_common_nodes(
        self,
        sources: object,
        mode: str = "max",
        sentinel: object = None,
        prefer_sentinel_for_single_source: bool = False,
        follow_steps_to_sentinel: int = 0,
    ) -> tuple[list[str], int, dict[str, object]]:
        _ = (
            sources,
            mode,
            sentinel,
            prefer_sentinel_for_single_source,
            follow_steps_to_sentinel,
        )
        return ["X"], 1, {}

    def follow_first_fanout_from_pins(
        self, hier_pin_path: object, num_follow: int = 1
    ) -> str:
        _ = num_follow
        assert hier_pin_path == "X"
        return "X"

    def path_to_nearest_target_sentinel(
        self, _src: object, _targets: object
    ) -> tuple[list[str], object | None]:
        return [], None


@pytest.fixture
def bare_model(tmp_path: Path, mocker: MockerFixture) -> FABulousTileTimingModel:
    m = FABulousTileTimingModel.__new__(FABulousTileTimingModel)
    m.fabric = DummyFabric([])
    m.tile_name = "TILE_A"
    m.unique_tile_name = "TILE_A"
    m.is_in_which_super_tile = None
    m.tm_config = make_config(tmp_path)
    m.verilog_files = None
    m.work_dir = tmp_path / "work"
    m.hdlnx_tm_synth = DummyHdlnx()
    m.hdlnx_tm_phys = DummyHdlnx()
    m.tile_scope = ()
    m.synth_netlist = mocker.create_autospec(NetlistIndex, instance=True)
    m.switch_matrix_hier_path = ("tile_inst_switch_matrix",)
    m.internal_pips_grouped_by_inst = {}
    m.internal_pip_cache = {}
    return m


def test_init_sets_attributes_and_calls_helpers(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(tm_mod, "SuperTile", DummySuperTile)

    called = {"init_tm": 0, "extract": 0}

    def fake_init_tm(self: FABulousTileTimingModel) -> None:
        called["init_tm"] += 1
        self.verilog_files = [tmp_path / "a.v"]
        self.hdlnx_tm_synth = "SYNTH"
        self.hdlnx_tm_phys = "PHYS"

    def fake_extract(self: FABulousTileTimingModel) -> None:
        called["extract"] += 1
        self.switch_matrix_hier_path = ("swm_inst",)
        self.internal_pips_grouped_by_inst = {"u0": ["A", "B"]}

    monkeypatch.setattr(
        FABulousTileTimingModel, "_initialize_timing_models", fake_init_tm
    )
    monkeypatch.setattr(
        FABulousTileTimingModel, "_extract_switch_matrix_info", fake_extract
    )

    fabric = DummyFabric([])
    cfg = make_config(tmp_path)

    obj = FABulousTileTimingModel(cfg, fabric, tile_name="TILE_A", work_dir=tmp_path)

    assert obj.fabric is fabric
    assert obj.tile_name == "TILE_A"
    assert obj.work_dir == tmp_path
    assert obj.unique_tile_name == "TILE_A"
    assert obj.is_in_which_super_tile is None
    assert obj.verilog_files == [tmp_path / "a.v"]
    assert obj.hdlnx_tm_synth == "SYNTH"
    assert obj.hdlnx_tm_phys == "PHYS"
    assert obj.tile_scope == ()
    assert obj.switch_matrix_hier_path == ("swm_inst",)
    assert obj.internal_pips_grouped_by_inst == {"u0": ["A", "B"]}
    assert obj.internal_pip_cache == {}
    assert called == {"init_tm": 1, "extract": 1}


def test_get_unique_tile_name_regular_tile_keeps_name(
    bare_model: FABulousTileTimingModel, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(tm_mod, "SuperTile", DummySuperTile)
    bare_model.fabric = DummyFabric([DummyTile("OTHER")])

    bare_model._get_unique_tile_name()  # noqa: SLF001

    assert bare_model.unique_tile_name == "TILE_A"
    assert bare_model.is_in_which_super_tile is None


@pytest.mark.parametrize(
    ("tile_map", "tile_scope"),
    [
        ([["TILE_A", "TILE_B"]], ("Tile_X0Y0_TILE_A",)),
        ([["TILE_B"], ["TILE_A"]], ("Tile_X0Y1_TILE_A",)),
    ],
)
def test_get_unique_tile_name_inside_supertile(
    bare_model: FABulousTileTimingModel,
    tile_map: list[list[str]],
    tile_scope: tuple[str, ...],
) -> None:
    tiles = {name: make_empty_tile(name) for name in ("TILE_A", "TILE_B")}
    st = SuperTile(
        name="SUPER_X",
        tileDir=Path(),
        tiles=list(tiles.values()),
        tileMap=[[tiles[name] for name in row] for row in tile_map],
    )
    bare_model.fabric = make_fabric_from_grid([list(tiles.values())])
    bare_model.fabric.superTileDic = {st.name: st}

    bare_model._get_unique_tile_name()  # noqa: SLF001

    assert bare_model.unique_tile_name == "SUPER_X"
    assert bare_model.is_in_which_super_tile == "SUPER_X"
    assert bare_model.tile_scope == tile_scope


def test_get_unique_tile_name_tile_placed_twice_in_supertile_raises(
    bare_model: FABulousTileTimingModel,
) -> None:
    tile = make_empty_tile("TILE_A")
    st = SuperTile(name="SUPER_X", tileDir=Path(), tiles=[tile], tileMap=[[tile, tile]])
    bare_model.fabric = make_fabric_from_grid([[tile]])
    bare_model.fabric.superTileDic = {st.name: st}

    with pytest.raises(ValueError, match="places tile 'TILE_A' 2 times"):
        bare_model._get_unique_tile_name()  # noqa: SLF001


def test_get_project_rtl_files_uses_default_search(
    bare_model: FABulousTileTimingModel,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    def fake_find(
        root_dir: Path,
        file_pattern: str,
        exclude_dir_patterns: list[str] | None = None,
        exclude_file_patterns: list[str] | None = None,
    ) -> list[Path]:
        assert root_dir == tmp_path
        assert file_pattern == r".*\.v$"
        assert exclude_dir_patterns == ["macro", "user_design", "Test", "^yosys$"]
        assert exclude_file_patterns is None
        return [tmp_path / "a.v", tmp_path / "b.v"]

    monkeypatch.setattr(bare_model, "_find_matching_files", fake_find)

    bare_model._get_project_rtl_files()  # noqa: SLF001

    assert bare_model.verilog_files == [tmp_path / "a.v", tmp_path / "b.v"]


def test_get_project_rtl_files_override_single_rtl_file(
    bare_model: FABulousTileTimingModel,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    default_files = [tmp_path / "default.v"]
    custom_file = tmp_path / "custom.v"

    monkeypatch.setattr(
        bare_model,
        "_find_matching_files",
        lambda *_args, **_kwargs: default_files,
    )

    bare_model.tm_config.custom_per_tile_source_files = {
        "TILE_A": make_source_override(rtl_files=custom_file)
    }

    bare_model._get_project_rtl_files()  # noqa: SLF001

    assert bare_model.verilog_files == [custom_file]


def test_get_project_rtl_files_override_rtl_list(
    bare_model: FABulousTileTimingModel,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    f1 = tmp_path / "a.v"
    f2 = tmp_path / "b.v"

    monkeypatch.setattr(
        bare_model,
        "_find_matching_files",
        lambda *_args, **_kwargs: [tmp_path / "default.v"],
    )

    bare_model.tm_config.custom_per_tile_source_files = {
        "TILE_A": make_source_override(rtl_files=[f1, f2])
    }

    bare_model._get_project_rtl_files()  # noqa: SLF001

    assert bare_model.verilog_files == [f1, f2]


def test_get_project_rtl_files_override_wildcard_expands_matches(
    bare_model: FABulousTileTimingModel,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    rtl_dir = tmp_path / "rtl"
    rtl_dir.mkdir()
    f1 = rtl_dir / "one.v"
    f2 = rtl_dir / "two.v"
    f3 = rtl_dir / "skip.txt"
    f1.write_text("module one; endmodule")
    f2.write_text("module two; endmodule")
    f3.write_text("x")

    monkeypatch.setattr(
        bare_model,
        "_find_matching_files",
        lambda *_args, **_kwargs: [tmp_path / "default.v"],
    )

    bare_model.tm_config.custom_per_tile_source_files = {
        "TILE_A": make_source_override(rtl_files=rtl_dir / "*.v")
    }

    bare_model._get_project_rtl_files()  # noqa: SLF001

    assert sorted(bare_model.verilog_files) == sorted([f1, f2])


def test_get_project_rtl_files_override_missing_tile_keeps_default(
    bare_model: FABulousTileTimingModel,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    default_files = [tmp_path / "default.v"]

    monkeypatch.setattr(
        bare_model,
        "_find_matching_files",
        lambda *_args, **_kwargs: default_files,
    )

    bare_model.tm_config.custom_per_tile_source_files = {
        "OTHER_TILE": make_source_override(rtl_files=tmp_path / "other.v")
    }

    bare_model._get_project_rtl_files()  # noqa: SLF001

    assert bare_model.verilog_files == default_files


def test_get_project_rtl_files_override_tile_entry_without_rtl_keeps_default(
    bare_model: FABulousTileTimingModel,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    default_files = [tmp_path / "default.v"]

    monkeypatch.setattr(
        bare_model,
        "_find_matching_files",
        lambda *_args, **_kwargs: default_files,
    )

    bare_model.tm_config.custom_per_tile_source_files = {
        "TILE_A": make_source_override(rtl_files=None)
    }

    bare_model._get_project_rtl_files()  # noqa: SLF001

    assert bare_model.verilog_files == default_files


@pytest.fixture
def tools(mocker: MockerFixture) -> SimpleNamespace:
    """Replace Yosys, OpenSTA, the SDF graph and the netlist index with mocks."""
    return SimpleNamespace(
        synthesize=mocker.patch.object(tm_mod.YosysTool, "synthesize_gate_level"),
        write_sdf=mocker.patch.object(tm_mod.OpenStaTool, "write_sdf"),
        graph=mocker.patch.object(tm_mod, "HdlnxTimingModel"),
        netlist_read=mocker.patch.object(tm_mod.NetlistIndex, "read"),
    )


def test_initialize_timing_models_structural_synthesises_into_work_dir(
    tmp_path: Path,
    bare_model: FABulousTileTimingModel,
    tools: SimpleNamespace,
    mocker: MockerFixture,
) -> None:
    rtl = [tmp_path / "rtl.v"]

    def fake_get_project_rtl_files() -> None:
        bare_model.verilog_files = rtl

    mocker.patch.object(
        bare_model, "_get_project_rtl_files", side_effect=fake_get_project_rtl_files
    )
    bare_model.tm_config = make_config(tmp_path, mode=TimingModelMode.STRUCTURAL)
    work = bare_model.work_dir

    bare_model._initialize_timing_models()  # noqa: SLF001

    tools.synthesize.assert_called_once_with(
        verilog_files=rtl,
        liberty_files=[tmp_path / "lib.lib"],
        top_name="TILE_A",
        netlist_file=work / "synth.v",
        techmap_files=[],
        tiehi_cell_and_port="TIEHI Y",
        tielo_cell_and_port="TIELO Y",
        min_buf_cell_and_ports="BUF A Y",
    )
    tools.write_sdf.assert_called_once_with(
        netlist_file=work / "synth.v",
        liberty_files=[tmp_path / "lib.lib"],
        top_name="TILE_A",
        spef_files=[],
        sdf_file=work / "synth.sdf",
    )
    tools.graph.assert_called_once_with(work / "synth.sdf", DelayType.MAX_ALL)
    tools.netlist_read.assert_called_once_with(work / "synth.v", top="TILE_A")
    assert bare_model.hdlnx_tm_synth is tools.graph.return_value
    assert bare_model.synth_netlist is tools.netlist_read.return_value


@pytest.mark.parametrize(
    ("liberty", "techmap", "expected_liberty", "expected_techmap"),
    [
        pytest.param(["a.lib", "b.lib"], None, ["a.lib", "b.lib"], [], id="lists"),
        pytest.param("a.lib", "map.v", ["a.lib"], ["map.v"], id="single-paths"),
        pytest.param("a.lib", ["m1.v", "m2.v"], ["a.lib"], ["m1.v", "m2.v"], id="mix"),
    ],
)
def test_initialize_timing_models_passes_library_files_as_lists(
    tmp_path: Path,
    bare_model: FABulousTileTimingModel,
    tools: SimpleNamespace,
    mocker: MockerFixture,
    liberty: list[str] | str,
    techmap: list[str] | str | None,
    expected_liberty: list[str],
    expected_techmap: list[str],
) -> None:
    def to_paths(names: list[str] | str) -> list[Path] | Path:
        if isinstance(names, str):
            return tmp_path / names
        return [tmp_path / name for name in names]

    mocker.patch.object(bare_model, "_get_project_rtl_files")
    bare_model.tm_config = make_config(
        tmp_path,
        liberty_files=to_paths(liberty),
        techmap_files=None if techmap is None else to_paths(techmap),
    )

    bare_model._initialize_timing_models()  # noqa: SLF001

    synth = tools.synthesize.call_args.kwargs
    assert synth["liberty_files"] == [tmp_path / name for name in expected_liberty]
    assert synth["techmap_files"] == [tmp_path / name for name in expected_techmap]
    sta = tools.write_sdf.call_args.kwargs
    assert sta["liberty_files"] == [tmp_path / name for name in expected_liberty]


DEFAULT_NETLIST = Path("Tile/TILE_A/macro/final_views/nl/TILE_A.nl.v")
DEFAULT_SPEF = Path("Tile/TILE_A/macro/final_views/spef/nom/TILE_A.nom.spef")


@pytest.mark.parametrize(
    ("consider_wire_delay", "overrides", "expected_netlist", "expected_spef"),
    [
        pytest.param(False, None, DEFAULT_NETLIST, [], id="defaults"),
        pytest.param(True, None, DEFAULT_NETLIST, [DEFAULT_SPEF], id="wire-delay"),
        pytest.param(
            False,
            {"TILE_A": {"netlist_file": "custom.nl.v"}},
            Path("custom.nl.v"),
            [],
            id="custom-netlist",
        ),
        pytest.param(
            True,
            {"TILE_A": {"rc_file": "custom.nom.spef"}},
            DEFAULT_NETLIST,
            [Path("custom.nom.spef")],
            id="custom-rc",
        ),
        pytest.param(
            True,
            {"OTHER_TILE": {"netlist_file": "other.nl.v", "rc_file": "other.spef"}},
            DEFAULT_NETLIST,
            [DEFAULT_SPEF],
            id="other-tile-override",
        ),
    ],
)
def test_initialize_timing_models_physical_writes_the_netlist_sdf(
    tmp_path: Path,
    bare_model: FABulousTileTimingModel,
    tools: SimpleNamespace,
    mocker: MockerFixture,
    consider_wire_delay: bool,
    overrides: dict[str, dict[str, str]] | None,
    expected_netlist: Path,
    expected_spef: list[Path],
) -> None:
    mocker.patch.object(bare_model, "_get_project_rtl_files")
    bare_model.tm_config = make_config(
        tmp_path,
        mode=TimingModelMode.PHYSICAL,
        consider_wire_delay=consider_wire_delay,
        custom_per_tile_source_files=None
        if overrides is None
        else {
            tile: make_source_override(
                **{field: tmp_path / name for field, name in fields.items()}
            )
            for tile, fields in overrides.items()
        },
    )
    work = bare_model.work_dir
    physical_graph = mocker.Mock()
    tools.graph.side_effect = [mocker.Mock(), physical_graph]

    bare_model._initialize_timing_models()  # noqa: SLF001

    assert tools.synthesize.call_count == 1
    assert tools.write_sdf.call_args_list[1] == mocker.call(
        netlist_file=tmp_path / expected_netlist,
        liberty_files=[tmp_path / "lib.lib"],
        top_name="TILE_A",
        spef_files=[tmp_path / spef for spef in expected_spef],
        sdf_file=work / "physical.sdf",
    )
    assert tools.graph.call_args_list[1] == mocker.call(
        work / "physical.sdf", DelayType.MAX_ALL
    )
    assert bare_model.hdlnx_tm_phys is physical_graph


def test_find_matching_files_filters_dirs_and_files(
    tmp_path: Path, bare_model: FABulousTileTimingModel
) -> None:
    keep_dir = tmp_path / "keep"
    skip_macro = tmp_path / "macro"
    skip_user = tmp_path / "user_design"
    skip_test = tmp_path / "Test"

    keep_dir.mkdir()
    skip_macro.mkdir()
    skip_user.mkdir()
    skip_test.mkdir()

    (keep_dir / "a.v").write_text("module a; endmodule")
    (keep_dir / "b.txt").write_text("x")
    (keep_dir / "skip_me.v").write_text("module x; endmodule")
    (skip_macro / "macro.v").write_text("module m; endmodule")
    (skip_user / "user.v").write_text("module u; endmodule")
    (skip_test / "test.v").write_text("module t; endmodule")

    result = bare_model._find_matching_files(  # noqa: SLF001
        tmp_path,
        r".*\.v$",
        exclude_dir_patterns=["macro", "user_design", "Test"],
        exclude_file_patterns=["skip_me"],
    )

    assert result == [keep_dir / "a.v"]


def test_find_matching_files_invalid_root_raises(
    bare_model: FABulousTileTimingModel,
) -> None:
    with pytest.raises(TypeError, match="root_dir must be a Path object"):
        bare_model._find_matching_files("not_a_path", r".*\.v$")  # noqa: SLF001


SWITCH_MATRIX_NETLIST = """
module TILE_A_switch_matrix (A, B, C, Y, Z);
    input A, B, C;
    output Y, Z;
    MUX mux0 (.A(A), .B(B), .Y(Y));
    BUF buf1 (.A(C), .Y(Z));
endmodule
module TILE_A (A, B, C, Y, Z);
    input A, B, C;
    output Y, Z;
    TILE_A_switch_matrix Inst_TILE_A_switch_matrix (
        .A(A), .B(B), .C(C), .Y(Y), .Z(Z));
endmodule
module SUPER_X (A, B, C, Y, Z);
    input A, B, C;
    output Y, Z;
    TILE_A Tile_X0Y0_TILE_A (.A(A), .B(B), .C(C), .Y(Y), .Z(Z));
endmodule
"""


@pytest.mark.parametrize(
    ("top", "tile_scope"),
    [("TILE_A", ()), ("SUPER_X", ("Tile_X0Y0_TILE_A",))],
)
def test_extract_switch_matrix_info_finds_the_generated_instance(
    bare_model: FABulousTileTimingModel,
    read_netlist: ReadNetlist,
    top: str,
    tile_scope: tuple[str, ...],
) -> None:
    bare_model.fabric = make_fabric_from_grid([[make_empty_tile("TILE_A")]])
    bare_model.synth_netlist = read_netlist(SWITCH_MATRIX_NETLIST, top)
    bare_model.tile_scope = tile_scope

    bare_model._extract_switch_matrix_info()  # noqa: SLF001

    assert bare_model.switch_matrix_hier_path == (
        *tile_scope,
        "Inst_TILE_A_switch_matrix",
    )
    assert {
        mux: set(nets) for mux, nets in bare_model.internal_pips_grouped_by_inst.items()
    } == {"mux0": {"A", "B", "Y"}, "buf1": {"C", "Z"}}


@pytest.mark.parametrize(
    ("top", "tile_scope"),
    [("TILE_A", ("Tile_X0Y0_TILE_A",)), ("SUPER_X", ())],
)
def test_extract_switch_matrix_info_missing_instance_raises(
    bare_model: FABulousTileTimingModel,
    read_netlist: ReadNetlist,
    top: str,
    tile_scope: tuple[str, ...],
) -> None:
    bare_model.fabric = make_fabric_from_grid([[make_empty_tile("TILE_A")]])
    bare_model.synth_netlist = read_netlist(SWITCH_MATRIX_NETLIST, top)
    bare_model.tile_scope = tile_scope

    with pytest.raises(ValueError, match="Inst_TILE_A_switch_matrix.*not found"):
        bare_model._extract_switch_matrix_info()  # noqa: SLF001


def test_is_tile_internal_pip_true_and_false(
    bare_model: FABulousTileTimingModel,
) -> None:
    bare_model.internal_pips_grouped_by_inst = {
        "mux0": ["A", "B", "Y"],
        "mux1": ["C", "D", "Z"],
    }

    assert bare_model.is_tile_internal_pip("A", "Y") is True
    assert bare_model.is_tile_internal_pip("A", "Z") is False


def test_is_tile_internal_pip_false_when_same_src_and_dst(
    bare_model: FABulousTileTimingModel,
) -> None:
    bare_model.internal_pips_grouped_by_inst = {"mux0": ["A", "Y"]}
    assert bare_model.is_tile_internal_pip("A", "A") is False


def test_internal_pip_delay_structural_no_mux_raises_indexerror(
    bare_model: FABulousTileTimingModel,
) -> None:
    bare_model.internal_pips_grouped_by_inst = {"mux0": ["B", "Y"]}

    with pytest.raises(IndexError, match="list index out of range"):
        bare_model.internal_pip_delay_structural("A", "Y")


def test_internal_pip_delay_structural_success_and_caches(
    bare_model: FABulousTileTimingModel, mocker: MockerFixture
) -> None:
    class Synth(DummyHdlnx):
        def single_delay(self, _src: object, _dst: object) -> Decimal:
            return Decimal("0.123")

    netlist = mocker.create_autospec(NetlistIndex, instance=True)
    netlist.net_leaf_pins.return_value = {
        "A": ["mux0/A0", "mux0/A1"],
        "Y": ["mux0/Y0", "mux0/Y1"],
    }
    bare_model.hdlnx_tm_synth = Synth()
    bare_model.synth_netlist = netlist
    bare_model.internal_pips_grouped_by_inst = {
        "mux0": ["A", "Y"],
        "mux1": ["A", "Y", "Z"],
        "mux2": ["B", "Y"],
    }
    bare_model.internal_pip_cache = {}

    delay = bare_model.internal_pip_delay_structural("A", "Y")

    assert delay == Decimal("0.123")
    netlist.net_leaf_pins.assert_called_once_with(("tile_inst_switch_matrix", "mux0"))
    assert "Y" in bare_model.internal_pip_cache
    cache_entry = bare_model.internal_pip_cache["Y"]
    assert isinstance(cache_entry, InternalPipCacheEntry)
    assert cache_entry.begin_pip == "Y"
    assert cache_entry.swm_mux_for_pips == [
        ("tile_inst_switch_matrix", "mux0"),
        ("tile_inst_switch_matrix", "mux1"),
    ]
    assert cache_entry.swm_mux_resolved == {
        "A": ["mux0/A0", "mux0/A1"],
        "Y": ["mux0/Y0", "mux0/Y1"],
    }


def test_internal_pip_delay_structural_cache_hit_reuses_cached_values(
    bare_model: FABulousTileTimingModel, mocker: MockerFixture
) -> None:
    class Synth(DummyHdlnx):
        def single_delay(self, _src: object, _dst: object) -> Decimal:
            return Decimal("1.5")

    netlist = mocker.create_autospec(NetlistIndex, instance=True)
    netlist.net_leaf_pins.return_value = {"bad": ["bad"]}
    bare_model.hdlnx_tm_synth = Synth()
    bare_model.synth_netlist = netlist
    bare_model.internal_pip_cache = {
        "Y": InternalPipCacheEntry(
            begin_pip="Y",
            swm_mux_for_pips=[("cached_mux",)],
            swm_nearest_ports_in=None,
            swm_nearest_ports_out=None,
            swm_output_pin=None,
            swm_mux_resolved={
                "A": ["CACHED_A"],
                "Y": ["CACHED_Y"],
            },
        )
    }

    delay = bare_model.internal_pip_delay_structural("A", "Y")

    assert delay == Decimal("1.5")
    netlist.net_leaf_pins.assert_not_called()


def test_internal_pip_delay_physical_cache_miss_multiple_ports(
    bare_model: FABulousTileTimingModel, mocker: MockerFixture
) -> None:
    netlist = mocker.create_autospec(NetlistIndex, instance=True)
    netlist.net_leaf_pins.return_value = {"A": ["mux0/A"], "Y": ["mux0/Y"]}

    class Synth(DummyHdlnx):
        def __init__(self) -> None:
            super().__init__()
            self.nearest_calls = 0

        def nearest_ports_from_pins(
            self,
            net_pins: dict[str, list[str]],
            reverse: bool = False,
            num_ports: int = 1,
        ) -> tuple[dict[str, list[str]], list[str]]:
            _ = num_ports
            assert net_pins == netlist.net_leaf_pins.return_value
            self.nearest_calls += 1
            if reverse:
                return (
                    {"A": ["IN_A"], "Y": ["IN_Y"]},
                    ["IN_A", "IN_Y"],
                )
            return (
                {"Y": ["OUT_REF"]},
                ["OUT_REF"],
            )

    class Phys(DummyHdlnx):
        def __init__(self) -> None:
            super().__init__()
            self.earliest_calls = 0

        def earliest_common_nodes(
            self,
            sources: object,
            mode: str = "max",
            sentinel: object = None,
            prefer_sentinel_for_single_source: bool = False,
            follow_steps_to_sentinel: int = 0,
        ) -> tuple[list[str], int, dict[str, object]]:
            self.earliest_calls += 1
            assert sources == ["IN_A", "IN_Y"]
            assert mode == "max"
            assert sentinel is None
            assert prefer_sentinel_for_single_source is True
            assert follow_steps_to_sentinel == 3
            return ["OUT2", "OUT1"], 3, {"dummy": 1}

        def single_delay(self, _src: object, _dst: object) -> Decimal:
            return Decimal("0.456")

    synth = Synth()
    phys = Phys()

    bare_model.hdlnx_tm_synth = synth
    bare_model.hdlnx_tm_phys = phys
    bare_model.synth_netlist = netlist
    bare_model.internal_pips_grouped_by_inst = {
        "mux0": ["A", "Y"],
        "mux1": ["A", "Y"],
    }
    bare_model.internal_pip_cache = {}

    delay = bare_model.internal_pip_delay_physical("A", "Y")

    assert delay == Decimal("0.456")
    netlist.net_leaf_pins.assert_called_once_with(("tile_inst_switch_matrix", "mux0"))
    assert synth.nearest_calls == 1
    assert phys.earliest_calls == 1
    assert "Y" in bare_model.internal_pip_cache
    cache_entry = bare_model.internal_pip_cache["Y"]
    assert isinstance(cache_entry, InternalPipCacheEntry)
    assert cache_entry.begin_pip == "Y"
    assert cache_entry.swm_mux_for_pips == [
        ("tile_inst_switch_matrix", "mux0"),
        ("tile_inst_switch_matrix", "mux1"),
    ]
    assert cache_entry.swm_nearest_ports_in == (
        {"A": ["IN_A"], "Y": ["IN_Y"]},
        ["IN_A", "IN_Y"],
    )
    assert cache_entry.swm_nearest_ports_out is None
    assert cache_entry.swm_output_pin == (["OUT2", "OUT1"], 3, {"dummy": 1})
    assert cache_entry.swm_mux_resolved is None


def test_internal_pip_delay_physical_cache_miss_single_input_uses_output_reference_and_caches(  # noqa: E501
    bare_model: FABulousTileTimingModel,
) -> None:
    class Synth(DummyHdlnx):
        def __init__(self) -> None:
            super().__init__()
            self.nearest_calls = 0

        def nearest_ports_from_pins(
            self,
            net_pins: dict[str, list[str]],
            reverse: bool = False,
            num_ports: int = 1,
        ) -> tuple[dict[str, list[str]], list[str]]:
            _ = (net_pins, num_ports)
            self.nearest_calls += 1
            if reverse:
                return (
                    {"A": ["IN_A"], "Y": ["IN_Y"]},
                    ["IN_A"],
                )
            return (
                {"Y": ["OUT_REF"]},
                ["OUT_REF"],
            )

    class Phys(DummyHdlnx):
        def earliest_common_nodes(
            self,
            sources: object,
            mode: str = "max",
            sentinel: object = None,
            prefer_sentinel_for_single_source: bool = False,
            follow_steps_to_sentinel: int = 0,
        ) -> tuple[list[str], int, dict[str, object]]:
            _ = mode
            assert sources == ["IN_A"]
            assert sentinel == "OUT_REF"
            assert prefer_sentinel_for_single_source is True
            assert follow_steps_to_sentinel == 3
            return ["PHYS_OUT"], 1, {}

        def single_delay(self, _src: object, _dst: object) -> Decimal:
            return Decimal("0.789")

    synth = Synth()
    phys = Phys()

    bare_model.hdlnx_tm_synth = synth
    bare_model.hdlnx_tm_phys = phys
    bare_model.internal_pips_grouped_by_inst = {"mux0": ["A", "Y"]}
    bare_model.internal_pip_cache = {}

    delay = bare_model.internal_pip_delay_physical("A", "Y")

    assert delay == Decimal("0.789")
    assert synth.nearest_calls == 2
    cache_entry = bare_model.internal_pip_cache["Y"]
    assert cache_entry.swm_nearest_ports_out == ({"Y": ["OUT_REF"]}, ["OUT_REF"])
    assert cache_entry.swm_output_pin == (["PHYS_OUT"], 1, {})


def test_internal_pip_delay_physical_cache_hit_reuses_cached_values(
    bare_model: FABulousTileTimingModel, mocker: MockerFixture
) -> None:
    class Synth(DummyHdlnx):
        def __init__(self) -> None:
            super().__init__()
            self.nearest_calls = 0

        def nearest_ports_from_pins(
            self,
            net_pins: dict[str, list[str]],
            reverse: bool = False,
            num_ports: int = 1,
        ) -> tuple[dict[str, list[str]], list[str]]:
            _ = (net_pins, reverse, num_ports)
            self.nearest_calls += 1
            return {"bad": ["bad"]}, ["bad"]

    class Phys(DummyHdlnx):
        def __init__(self) -> None:
            super().__init__()
            self.earliest_calls = 0

        def earliest_common_nodes(
            self,
            sources: object,
            mode: str = "max",
            sentinel: object = None,
            prefer_sentinel_for_single_source: bool = False,
            follow_steps_to_sentinel: int = 0,
        ) -> tuple[list[str], int, dict[str, object]]:
            _ = (
                sources,
                mode,
                sentinel,
                prefer_sentinel_for_single_source,
                follow_steps_to_sentinel,
            )
            self.earliest_calls += 1
            return ["should_not_be_used"], 0, {}

        def single_delay(self, _src: object, _dst: object) -> Decimal:
            return Decimal("1.234")

    synth = Synth()
    phys = Phys()
    netlist = mocker.create_autospec(NetlistIndex, instance=True)
    netlist.net_leaf_pins.return_value = {"bad": ["bad"]}

    bare_model.hdlnx_tm_synth = synth
    bare_model.hdlnx_tm_phys = phys
    bare_model.synth_netlist = netlist
    bare_model.internal_pip_cache = {
        "Y": InternalPipCacheEntry(
            begin_pip="Y",
            swm_mux_for_pips=[("cached_mux",)],
            swm_nearest_ports_in=(
                {"A": ["CACHED_IN"], "Y": ["CACHED_DST"]},
                ["CACHED_IN", "CACHED_DST"],
            ),
            swm_nearest_ports_out=None,
            swm_output_pin=(["CACHED_PHYS_OUT"], 0, {}),
            swm_mux_resolved=None,
        )
    }

    delay = bare_model.internal_pip_delay_physical("A", "Y")

    assert delay == Decimal("1.234")
    netlist.net_leaf_pins.assert_not_called()
    assert synth.nearest_calls == 0
    assert phys.earliest_calls == 0


def test_external_pip_delay_structural_output_port_returns_default(
    bare_model: FABulousTileTimingModel,
) -> None:
    synth = DummyHdlnx()
    synth.output_ports = {"NN2BEG[3]"}
    bare_model.hdlnx_tm_synth = synth

    assert bare_model.external_pip_delay_structural("NN2BEG3", "X") == Decimal("0.001")


def test_external_pip_delay_structural_input_port_no_nearest_returns_default_real_input_branch(  # noqa: E501
    bare_model: FABulousTileTimingModel,
) -> None:
    class Synth(DummyHdlnx):
        def __init__(self) -> None:
            super().__init__()
            self.input_ports = {"NN2BEG[3]"}
            self.output_ports = {"OUT0"}

        def path_to_nearest_target_sentinel(
            self, src: object, targets: object
        ) -> tuple[list[str], object | None]:
            assert src == "NN2BEG[3]"
            assert targets == {"OUT0"}
            return [], None

    bare_model.hdlnx_tm_synth = Synth()

    assert bare_model.external_pip_delay_structural("NN2BEG3", "X") == Decimal("0.001")


def test_external_pip_delay_structural_input_port_uses_single_delay(
    bare_model: FABulousTileTimingModel,
) -> None:
    class Synth(DummyHdlnx):
        def __init__(self) -> None:
            super().__init__()
            self.input_ports = {"NN2BEG[3]"}
            self.output_ports = {"OUT0"}

        def path_to_nearest_target_sentinel(
            self, _src: object, _targets: object
        ) -> tuple[list[str], object | None]:
            return ["NN2BEG[3]", "OUT0"], "OUT0"

        def single_delay(self, _src: object, _dst: object) -> Decimal:
            return Decimal("0.222")

    bare_model.hdlnx_tm_synth = Synth()

    assert bare_model.external_pip_delay_structural("NN2BEG3", "X") == Decimal("0.222")


def test_external_pip_delay_structural_swm_to_swm_without_cache_returns_default(
    bare_model: FABulousTileTimingModel,
) -> None:
    synth = DummyHdlnx()
    synth.input_ports = {"IN0"}
    synth.output_ports = {"OUT0"}
    bare_model.hdlnx_tm_synth = synth
    bare_model.internal_pip_cache = {}

    assert bare_model.external_pip_delay_structural("SOME_INTERNAL", "X") == Decimal(
        "0.001"
    )


def test_external_pip_delay_structural_swm_to_swm_with_cache_uses_follow_and_delay(
    bare_model: FABulousTileTimingModel,
) -> None:
    class Synth(DummyHdlnx):
        def follow_first_fanout_from_pins(
            self, hier_pin_path: object, num_follow: int = 1
        ) -> str:
            assert hier_pin_path == "SWM_OUT_PIN"
            assert num_follow == 2
            return "NEXT_INPUT_PIN"

        def single_delay(self, src: object, dst: object) -> Decimal:
            assert src == "SWM_OUT_PIN"
            assert dst == "NEXT_INPUT_PIN"
            return Decimal("0.444")

    bare_model.hdlnx_tm_synth = Synth()
    bare_model.internal_pip_cache = {
        "PIP_SRC": InternalPipCacheEntry(
            begin_pip="PIP_SRC",
            swm_mux_for_pips=[("mux0",)],
            swm_nearest_ports_in=None,
            swm_nearest_ports_out=None,
            swm_output_pin=None,
            swm_mux_resolved={"PIP_SRC": ["SWM_OUT_PIN"]},
        )
    }

    assert bare_model.external_pip_delay_structural("PIP_SRC", "X") == Decimal("0.444")


def test_external_pip_delay_structural_swm_to_swm_with_tiny_delay_returns_default(
    bare_model: FABulousTileTimingModel,
) -> None:
    class Synth(DummyHdlnx):
        def follow_first_fanout_from_pins(
            self, hier_pin_path: object, num_follow: int = 1
        ) -> str:
            assert hier_pin_path == "SWM_OUT_PIN"
            assert num_follow == 2
            return "NEXT_INPUT_PIN"

        def single_delay(self, _src: object, _dst: object) -> Decimal:
            return Decimal("0.0")

    bare_model.hdlnx_tm_synth = Synth()
    bare_model.internal_pip_cache = {
        "PIP_SRC": InternalPipCacheEntry(
            begin_pip="PIP_SRC",
            swm_mux_for_pips=[("mux0",)],
            swm_nearest_ports_in=None,
            swm_nearest_ports_out=None,
            swm_output_pin=None,
            swm_mux_resolved={"PIP_SRC": ["SWM_OUT_PIN"]},
        )
    }

    assert bare_model.external_pip_delay_structural("PIP_SRC", "X") == Decimal("0.001")


def test_external_pip_delay_physical_output_port_returns_default(
    bare_model: FABulousTileTimingModel,
) -> None:
    phys = DummyHdlnx()
    phys.output_ports = {"NN2BEG[3]"}
    bare_model.hdlnx_tm_phys = phys

    assert bare_model.external_pip_delay_physical("NN2BEG3", "X") == Decimal("0.001")


def test_external_pip_delay_physical_input_port_no_nearest_returns_default_real_input_branch(  # noqa: E501
    bare_model: FABulousTileTimingModel,
) -> None:
    class Phys(DummyHdlnx):
        def __init__(self) -> None:
            super().__init__()
            self.input_ports = {"NN2BEG[3]"}
            self.output_ports = {"OUT0"}

        def path_to_nearest_target_sentinel(
            self, src: object, targets: object
        ) -> tuple[list[str], object | None]:
            assert src == "NN2BEG[3]"
            assert targets == {"OUT0"}
            return [], None

    bare_model.hdlnx_tm_phys = Phys()

    assert bare_model.external_pip_delay_physical("NN2BEG3", "X") == Decimal("0.001")


def test_external_pip_delay_physical_input_port_uses_single_delay(
    bare_model: FABulousTileTimingModel,
) -> None:
    class Phys(DummyHdlnx):
        def __init__(self) -> None:
            super().__init__()
            self.input_ports = {"NN2BEG[3]"}
            self.output_ports = {"OUT0"}

        def path_to_nearest_target_sentinel(
            self, _src: object, _targets: object
        ) -> tuple[list[str], object | None]:
            return ["NN2BEG[3]", "OUT0"], "OUT0"

        def single_delay(self, _src: object, _dst: object) -> Decimal:
            return Decimal("0.333")

    bare_model.hdlnx_tm_phys = Phys()

    assert bare_model.external_pip_delay_physical("NN2BEG3", "X") == Decimal("0.333")


def test_external_pip_delay_physical_swm_to_swm_without_cache_returns_default(
    bare_model: FABulousTileTimingModel,
) -> None:
    phys = DummyHdlnx()
    phys.input_ports = {"IN0"}
    phys.output_ports = {"OUT0"}
    bare_model.hdlnx_tm_phys = phys
    bare_model.internal_pip_cache = {}

    assert bare_model.external_pip_delay_physical("SOME_INTERNAL", "X") == Decimal(
        "0.001"
    )


def test_external_pip_delay_physical_swm_to_swm_with_cache_uses_follow_and_delay(
    bare_model: FABulousTileTimingModel,
) -> None:
    class Phys(DummyHdlnx):
        def follow_first_fanout_from_pins(
            self, hier_pin_path: object, num_follow: int = 1
        ) -> str:
            assert hier_pin_path == "PHYS_OUT_PIN"
            assert num_follow == 2
            return "NEXT_PHYS_INPUT"

        def single_delay(self, src: object, dst: object) -> Decimal:
            assert src == "PHYS_OUT_PIN"
            assert dst == "NEXT_PHYS_INPUT"
            return Decimal("0.555")

    bare_model.hdlnx_tm_phys = Phys()
    bare_model.internal_pip_cache = {
        "PIP_SRC": InternalPipCacheEntry(
            begin_pip="PIP_SRC",
            swm_mux_for_pips=[("mux0",)],
            swm_nearest_ports_in=None,
            swm_nearest_ports_out=None,
            swm_output_pin=(["PHYS_OUT_PIN"], 1, {}),
            swm_mux_resolved=None,
        )
    }

    assert bare_model.external_pip_delay_physical("PIP_SRC", "X") == Decimal("0.555")


def test_external_pip_delay_physical_swm_to_swm_with_tiny_delay_returns_default(
    bare_model: FABulousTileTimingModel,
) -> None:
    class Phys(DummyHdlnx):
        def follow_first_fanout_from_pins(
            self, hier_pin_path: object, num_follow: int = 1
        ) -> str:
            assert hier_pin_path == "PHYS_OUT_PIN"
            assert num_follow == 2
            return "NEXT_PHYS_INPUT"

        def single_delay(self, _src: object, _dst: object) -> Decimal:
            return Decimal("0.0")

    bare_model.hdlnx_tm_phys = Phys()
    bare_model.internal_pip_cache = {
        "PIP_SRC": InternalPipCacheEntry(
            begin_pip="PIP_SRC",
            swm_mux_for_pips=[("mux0",)],
            swm_nearest_ports_in=None,
            swm_nearest_ports_out=None,
            swm_output_pin=(["PHYS_OUT_PIN"], 1, {}),
            swm_mux_resolved=None,
        )
    }

    assert bare_model.external_pip_delay_physical("PIP_SRC", "X") == Decimal("0.001")


def test_internal_pip_delay_dispatch_physical(
    bare_model: FABulousTileTimingModel, monkeypatch: pytest.MonkeyPatch
) -> None:
    bare_model.tm_config.mode = TimingModelMode.PHYSICAL
    monkeypatch.setattr(
        bare_model, "internal_pip_delay_physical", lambda _s, _d: Decimal("1.23")
    )
    monkeypatch.setattr(
        bare_model, "internal_pip_delay_structural", lambda _s, _d: Decimal("9.99")
    )

    assert bare_model.internal_pip_delay("A", "Y") == Decimal("1.23")


def test_internal_pip_delay_dispatch_structural(
    bare_model: FABulousTileTimingModel, monkeypatch: pytest.MonkeyPatch
) -> None:
    bare_model.tm_config.mode = TimingModelMode.STRUCTURAL
    monkeypatch.setattr(
        bare_model, "internal_pip_delay_physical", lambda _s, _d: Decimal("9.99")
    )
    monkeypatch.setattr(
        bare_model, "internal_pip_delay_structural", lambda _s, _d: Decimal("2.34")
    )

    assert bare_model.internal_pip_delay("A", "Y") == Decimal("2.34")


def test_external_pip_delay_dispatch_physical(
    bare_model: FABulousTileTimingModel, monkeypatch: pytest.MonkeyPatch
) -> None:
    bare_model.tm_config.mode = TimingModelMode.PHYSICAL
    monkeypatch.setattr(
        bare_model, "external_pip_delay_physical", lambda _s, _d: Decimal("3.45")
    )
    monkeypatch.setattr(
        bare_model, "external_pip_delay_structural", lambda _s, _d: Decimal("9.99")
    )

    assert bare_model.external_pip_delay("A", "Y") == Decimal("3.45")


def test_external_pip_delay_dispatch_structural(
    bare_model: FABulousTileTimingModel, monkeypatch: pytest.MonkeyPatch
) -> None:
    bare_model.tm_config.mode = TimingModelMode.STRUCTURAL
    monkeypatch.setattr(
        bare_model, "external_pip_delay_physical", lambda _s, _d: Decimal("9.99")
    )
    monkeypatch.setattr(
        bare_model, "external_pip_delay_structural", lambda _s, _d: Decimal("4.56")
    )

    assert bare_model.external_pip_delay("A", "Y") == Decimal("4.56")


@pytest.mark.parametrize("internal", [True, False], ids=["internal", "external"])
@pytest.mark.parametrize(
    ("delay", "scale", "expected"),
    [
        pytest.param(Decimal("1.234"), Decimal("2.5"), "3.085", id="exact"),
        pytest.param(Decimal("0.333"), Decimal(3), "0.999", id="integer-scale"),
        pytest.param(Decimal("0.25"), Decimal("2.0"), "0.5", id="trailing-zeros"),
        pytest.param(Decimal("1.5"), Decimal(2), "3.0", id="integral"),
        pytest.param(Decimal("0.0"), Decimal(1), "0.0", id="zero"),
        pytest.param(Decimal("0.123"), Decimal("1.05"), "0.12915", id="sub-ps-scale"),
        pytest.param(Decimal("0.333"), Decimal("0.5"), "0.1665", id="sub-ps-half"),
        pytest.param(Decimal("1.23456"), Decimal(1), "1.23456", id="sub-ps-sdf"),
    ],
)
def test_pip_delay_scales_exactly(
    bare_model: FABulousTileTimingModel,
    mocker: MockerFixture,
    internal: bool,
    delay: Decimal,
    scale: Decimal,
    expected: str,
) -> None:
    bare_model.tm_config.delay_scaling_factor = scale
    mocker.patch.object(bare_model, "is_tile_internal_pip", return_value=internal)
    mocker.patch.object(bare_model, "internal_pip_delay", return_value=delay)
    mocker.patch.object(bare_model, "external_pip_delay", return_value=delay)

    assert str(bare_model.pip_delay("A", "Y")) == expected


def test_pip_delay_float_scale_raises(
    bare_model: FABulousTileTimingModel, mocker: MockerFixture
) -> None:
    bare_model.tm_config.delay_scaling_factor = 2.0  # ty: ignore[invalid-assignment]
    mocker.patch.object(bare_model, "is_tile_internal_pip", return_value=True)
    mocker.patch.object(bare_model, "internal_pip_delay", return_value=Decimal("0.1"))

    with pytest.raises(TypeError):
        bare_model.pip_delay("A", "Y")

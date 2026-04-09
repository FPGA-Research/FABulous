from pathlib import Path
from types import SimpleNamespace

import pytest

import fabulous.fabric_cad.timing_model.FABulous_timing_model as tm_mod
from fabulous.fabric_cad.timing_model.FABulous_timing_model import (
    FABulousTileTimingModel,
)
from fabulous.fabric_cad.timing_model.models import (
    DelayType,
    InternalPipCacheEntry,
    TimingModelMode,
    TimingModelStaTools,
    TimingModelSynthTools,
)


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
    debug: bool = False,
    synth_program: TimingModelSynthTools = TimingModelSynthTools.YOSYS,
    sta_program: TimingModelStaTools = TimingModelStaTools.OPENSTA,
    custom_per_tile_source_files: dict[str, SimpleNamespace] | None = None,
    delay_scaling_factor: float = 1.0,
) -> SimpleNamespace:
    return SimpleNamespace(
        project_dir=tmp_path,
        liberty_files=[tmp_path / "lib.lib"],
        delay_type_str=DelayType.MAX_ALL,
        debug=debug,
        synth_program=synth_program,
        sta_program=sta_program,
        synth_executable="yosys",
        sta_executable="opensta",
        techmap_files=[tmp_path / "techmap.v"],
        tiehi_cell_and_port=("TIEHI", "Y"),
        tielo_cell_and_port=("TIELO", "Y"),
        min_buf_cell_and_ports=("BUF", "A", "Y"),
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


class DummySynthTool:
    def __init__(self) -> None:
        self.synth_rtl_files = None
        self.synth_passthrough = False


class DummyStaTool:
    def __init__(self) -> None:
        self.sta_rc_files = None


class DummyHdlnx:
    def __init__(self) -> None:
        self.output_ports = set()
        self.input_ports = set()

    def find_instance_paths_by_regex(self, _regex: object) -> list[object]:
        return []

    def find_verilog_modules_regex(self, _regex: object) -> list[object]:
        return []

    def get_module_instance_nets(self, _module_name: object) -> dict[object, object]:
        return {}

    def get_instance_pins(self, _inst_path: object) -> list[object]:
        return []

    def find_instances_paths_with_all_nets(
        self, _module_name: object, _nets: object, filter_regex: object = None
    ) -> list[object]:
        _ = filter_regex
        return []

    def net_to_pin_paths_for_instance_resolved(
        self, _inst: object
    ) -> dict[object, object]:
        return {}

    def single_delay(self, _src: object, _dst: object) -> float:
        return 0.0

    def nearest_ports_from_instance_pin_nets(
        self, _inst_path: object, reverse: bool = False, num_ports: int = 1
    ) -> tuple[dict[str, list[str]], list[str]]:
        _ = (reverse, num_ports)
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
def bare_model(tmp_path: Path) -> FABulousTileTimingModel:
    m = FABulousTileTimingModel.__new__(FABulousTileTimingModel)
    m.fabric = DummyFabric([])
    m.tile_name = "TILE_A"
    m.unique_tile_name = "TILE_A"
    m.is_in_which_super_tile = None
    m.tm_config = make_config(tmp_path)
    m.verilog_files = None
    m.hdlnx_tm_synth = DummyHdlnx()
    m.hdlnx_tm_phys = DummyHdlnx()
    m.switch_matrix_hier_path = "tile_inst_switch_matrix"
    m.switch_matrix_module_name = "tile_switch_matrix"
    m.internal_pips_grouped_by_inst = {}
    m.internal_pips = []
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
        self.switch_matrix_hier_path = "swm_inst"
        self.switch_matrix_module_name = "swm_mod"
        self.internal_pips_grouped_by_inst = {"u0": ["A", "B"]}
        self.internal_pips = ["A", "B"]

    monkeypatch.setattr(
        FABulousTileTimingModel, "_initialize_timing_models", fake_init_tm
    )
    monkeypatch.setattr(
        FABulousTileTimingModel, "_extract_switch_matrix_info", fake_extract
    )

    fabric = DummyFabric([])
    cfg = make_config(tmp_path)

    obj = FABulousTileTimingModel(cfg, fabric, tile_name="TILE_A")

    assert obj.fabric is fabric
    assert obj.tile_name == "TILE_A"
    assert obj.unique_tile_name == "TILE_A"
    assert obj.is_in_which_super_tile is None
    assert obj.verilog_files == [tmp_path / "a.v"]
    assert obj.hdlnx_tm_synth == "SYNTH"
    assert obj.hdlnx_tm_phys == "PHYS"
    assert obj.switch_matrix_hier_path == "swm_inst"
    assert obj.switch_matrix_module_name == "swm_mod"
    assert obj.internal_pips == ["A", "B"]
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


def test_get_unique_tile_name_inside_supertile(
    bare_model: FABulousTileTimingModel, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(tm_mod, "SuperTile", DummySuperTile)
    st = DummySuperTile("SUPER_X", [DummyTile("TILE_A"), DummyTile("TILE_B")])
    bare_model.fabric = DummyFabric([st])

    bare_model._get_unique_tile_name()  # noqa: SLF001

    assert bare_model.unique_tile_name == "SUPER_X"
    assert bare_model.is_in_which_super_tile == "SUPER_X"


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
        assert exclude_dir_patterns == ["macro", "user_design", "Test"]
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


def test_cad_tools_success(
    tmp_path: Path,
    bare_model: FABulousTileTimingModel,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls = {}

    class FakeYosys:
        def __init__(self, **kwargs: object) -> None:
            calls["yosys"] = kwargs

    class FakeOpenSta:
        def __init__(self, **kwargs: object) -> None:
            calls["opensta"] = kwargs

    monkeypatch.setattr(tm_mod, "YosysTool", FakeYosys)
    monkeypatch.setattr(tm_mod, "OpenStaTool", FakeOpenSta)

    bare_model.verilog_files = [tmp_path / "rtl.v"]
    bare_model.unique_tile_name = "TILE_A"
    bare_model.tm_config = make_config(tmp_path, debug=True)

    tools = bare_model._cad_tools()  # noqa: SLF001

    assert isinstance(tools["synth_tool"], FakeYosys)
    assert isinstance(tools["sta_tool"], FakeOpenSta)

    assert calls["yosys"]["verilog_files"] == [tmp_path / "rtl.v"]
    assert calls["yosys"]["liberty_files"] == [tmp_path / "lib.lib"]
    assert calls["yosys"]["top_name"] == "TILE_A"
    assert calls["yosys"]["synth_executable"] == "yosys"
    assert calls["yosys"]["is_gate_level"] is False
    assert calls["yosys"]["debug"] is True
    assert calls["yosys"]["flat"] is False

    assert calls["opensta"]["sta_executable"] == "opensta"
    assert calls["opensta"]["spef_files"] is None
    assert calls["opensta"]["debug"] is True


def test_cad_tools_unsupported_synth_raises(
    tmp_path: Path, bare_model: FABulousTileTimingModel
) -> None:
    bare_model.tm_config = make_config(tmp_path, synth_program="bad_synth")
    with pytest.raises(ValueError, match="Unsupported synthesis tool"):
        bare_model._cad_tools()  # noqa: SLF001


def test_cad_tools_unsupported_sta_raises(
    tmp_path: Path, bare_model: FABulousTileTimingModel
) -> None:
    bare_model.tm_config = make_config(tmp_path, sta_program="bad_sta")
    with pytest.raises(ValueError, match="Unsupported STA tool"):
        bare_model._cad_tools()  # noqa: SLF001


def test_initialize_timing_models_structural_calls_project_rtl_loader(
    tmp_path: Path,
    bare_model: FABulousTileTimingModel,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    synth_tool = DummySynthTool()
    sta_tool = DummyStaTool()
    created = []
    called = {"rtl": 0}

    def fake_get_project_rtl_files() -> None:
        called["rtl"] += 1
        bare_model.verilog_files = [tmp_path / "rtl.v"]

    def fake_cad_tools() -> dict[str, object]:
        return {"synth_tool": synth_tool, "sta_tool": sta_tool}

    class FakeHdlnxTimingModel:
        def __init__(
            self, sta: object, synth: object, delay_type: object, debug: object
        ) -> None:
            created.append((sta, synth, delay_type, debug))

    monkeypatch.setattr(
        bare_model, "_get_project_rtl_files", fake_get_project_rtl_files
    )
    monkeypatch.setattr(bare_model, "_cad_tools", fake_cad_tools)
    monkeypatch.setattr(tm_mod, "HdlnxTimingModel", FakeHdlnxTimingModel)

    bare_model.tm_config = make_config(
        tmp_path, mode=TimingModelMode.STRUCTURAL, debug=True
    )

    bare_model._initialize_timing_models()  # noqa: SLF001

    assert called["rtl"] == 1
    assert len(created) == 1
    assert synth_tool.synth_passthrough is False
    assert sta_tool.sta_rc_files is None


def test_initialize_timing_models_physical_without_wire_delay(
    tmp_path: Path,
    bare_model: FABulousTileTimingModel,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    synth_tool = DummySynthTool()
    sta_tool = DummyStaTool()
    created = []

    def fake_get_project_rtl_files() -> None:
        bare_model.verilog_files = [tmp_path / "rtl.v"]

    def fake_cad_tools() -> dict[str, object]:
        return {"synth_tool": synth_tool, "sta_tool": sta_tool}

    class FakeHdlnxTimingModel:
        def __init__(
            self, sta: object, synth: object, delay_type: object, debug: object
        ) -> None:
            created.append((sta, synth, delay_type, debug))

    monkeypatch.setattr(
        bare_model, "_get_project_rtl_files", fake_get_project_rtl_files
    )
    monkeypatch.setattr(bare_model, "_cad_tools", fake_cad_tools)
    monkeypatch.setattr(tm_mod, "HdlnxTimingModel", FakeHdlnxTimingModel)

    bare_model.unique_tile_name = "TILE_A"
    bare_model.tm_config = make_config(
        tmp_path, mode=TimingModelMode.PHYSICAL, consider_wire_delay=False
    )

    bare_model._initialize_timing_models()  # noqa: SLF001

    assert len(created) == 2
    assert synth_tool.synth_passthrough is True
    assert (
        synth_tool.synth_rtl_files
        == tmp_path / "Tile" / "TILE_A" / "macro" / "final_views" / "nl" / "TILE_A.nl.v"
    )
    assert sta_tool.sta_rc_files is None


def test_initialize_timing_models_physical_with_wire_delay(
    tmp_path: Path,
    bare_model: FABulousTileTimingModel,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    synth_tool = DummySynthTool()
    sta_tool = DummyStaTool()
    created = []

    def fake_get_project_rtl_files() -> None:
        bare_model.verilog_files = [tmp_path / "rtl.v"]

    def fake_cad_tools() -> dict[str, object]:
        return {"synth_tool": synth_tool, "sta_tool": sta_tool}

    class FakeHdlnxTimingModel:
        def __init__(
            self, sta: object, synth: object, delay_type: object, debug: object
        ) -> None:
            created.append((sta, synth, delay_type, debug))

    monkeypatch.setattr(
        bare_model, "_get_project_rtl_files", fake_get_project_rtl_files
    )
    monkeypatch.setattr(bare_model, "_cad_tools", fake_cad_tools)
    monkeypatch.setattr(tm_mod, "HdlnxTimingModel", FakeHdlnxTimingModel)

    bare_model.unique_tile_name = "TILE_A"
    bare_model.tm_config = make_config(
        tmp_path, mode=TimingModelMode.PHYSICAL, consider_wire_delay=True
    )

    bare_model._initialize_timing_models()  # noqa: SLF001

    assert len(created) == 2
    assert (
        sta_tool.sta_rc_files
        == tmp_path
        / "Tile"
        / "TILE_A"
        / "macro"
        / "final_views"
        / "spef"
        / "nom"
        / "TILE_A.nom.spef"
    )


def test_initialize_timing_models_physical_uses_custom_netlist_file(
    tmp_path: Path,
    bare_model: FABulousTileTimingModel,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    synth_tool = DummySynthTool()
    sta_tool = DummyStaTool()
    created = []
    custom_netlist = tmp_path / "custom.nl.v"

    def fake_get_project_rtl_files() -> None:
        bare_model.verilog_files = [tmp_path / "rtl.v"]

    def fake_cad_tools() -> dict[str, object]:
        return {"synth_tool": synth_tool, "sta_tool": sta_tool}

    class FakeHdlnxTimingModel:
        def __init__(
            self, sta: object, synth: object, delay_type: object, debug: object
        ) -> None:
            created.append((sta, synth, delay_type, debug))

    monkeypatch.setattr(
        bare_model, "_get_project_rtl_files", fake_get_project_rtl_files
    )
    monkeypatch.setattr(bare_model, "_cad_tools", fake_cad_tools)
    monkeypatch.setattr(tm_mod, "HdlnxTimingModel", FakeHdlnxTimingModel)

    bare_model.unique_tile_name = "TILE_A"
    bare_model.tm_config = make_config(
        tmp_path,
        mode=TimingModelMode.PHYSICAL,
        custom_per_tile_source_files={
            "TILE_A": make_source_override(netlist_file=custom_netlist)
        },
    )

    bare_model._initialize_timing_models()  # noqa: SLF001

    assert len(created) == 2
    assert synth_tool.synth_rtl_files == custom_netlist
    assert synth_tool.synth_passthrough is True


def test_initialize_timing_models_physical_uses_custom_rc_file(
    tmp_path: Path,
    bare_model: FABulousTileTimingModel,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    synth_tool = DummySynthTool()
    sta_tool = DummyStaTool()
    created = []
    custom_rc = tmp_path / "custom.nom.spef"

    def fake_get_project_rtl_files() -> None:
        bare_model.verilog_files = [tmp_path / "rtl.v"]

    def fake_cad_tools() -> dict[str, object]:
        return {"synth_tool": synth_tool, "sta_tool": sta_tool}

    class FakeHdlnxTimingModel:
        def __init__(
            self, sta: object, synth: object, delay_type: object, debug: object
        ) -> None:
            created.append((sta, synth, delay_type, debug))

    monkeypatch.setattr(
        bare_model, "_get_project_rtl_files", fake_get_project_rtl_files
    )
    monkeypatch.setattr(bare_model, "_cad_tools", fake_cad_tools)
    monkeypatch.setattr(tm_mod, "HdlnxTimingModel", FakeHdlnxTimingModel)

    bare_model.unique_tile_name = "TILE_A"
    bare_model.tm_config = make_config(
        tmp_path,
        mode=TimingModelMode.PHYSICAL,
        consider_wire_delay=True,
        custom_per_tile_source_files={
            "TILE_A": make_source_override(rc_file=custom_rc)
        },
    )

    bare_model._initialize_timing_models()  # noqa: SLF001

    assert len(created) == 2
    assert sta_tool.sta_rc_files == custom_rc


def test_initialize_timing_models_physical_missing_tile_in_custom_source_mapping_keeps_defaults(  # noqa: E501
    tmp_path: Path,
    bare_model: FABulousTileTimingModel,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    synth_tool = DummySynthTool()
    sta_tool = DummyStaTool()
    created = []

    def fake_get_project_rtl_files() -> None:
        bare_model.verilog_files = [tmp_path / "rtl.v"]

    def fake_cad_tools() -> dict[str, object]:
        return {"synth_tool": synth_tool, "sta_tool": sta_tool}

    class FakeHdlnxTimingModel:
        def __init__(
            self, sta: object, synth: object, delay_type: object, debug: object
        ) -> None:
            created.append((sta, synth, delay_type, debug))

    monkeypatch.setattr(
        bare_model, "_get_project_rtl_files", fake_get_project_rtl_files
    )
    monkeypatch.setattr(bare_model, "_cad_tools", fake_cad_tools)
    monkeypatch.setattr(tm_mod, "HdlnxTimingModel", FakeHdlnxTimingModel)

    bare_model.unique_tile_name = "TILE_A"
    bare_model.tm_config = make_config(
        tmp_path,
        mode=TimingModelMode.PHYSICAL,
        consider_wire_delay=True,
        custom_per_tile_source_files={
            "OTHER_TILE": make_source_override(
                netlist_file=tmp_path / "other.nl.v",
                rc_file=tmp_path / "other.spef",
            )
        },
    )

    bare_model._initialize_timing_models()  # noqa: SLF001

    assert len(created) == 2
    assert (
        synth_tool.synth_rtl_files
        == tmp_path / "Tile" / "TILE_A" / "macro" / "final_views" / "nl" / "TILE_A.nl.v"
    )
    assert (
        sta_tool.sta_rc_files
        == tmp_path
        / "Tile"
        / "TILE_A"
        / "macro"
        / "final_views"
        / "spef"
        / "nom"
        / "TILE_A.nom.spef"
    )


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


def test_extract_switch_matrix_info_regular_success(
    bare_model: FABulousTileTimingModel,
) -> None:
    synth = DummyHdlnx()
    synth.find_instance_paths_by_regex = lambda _regex: ["tile_inst_switch_matrix"]
    synth.find_verilog_modules_regex = lambda _regex: ["tile_switch_matrix"]
    synth.get_module_instance_nets = lambda _module_name: {"mux0": ["A", "B", "Y"]}
    synth.get_instance_pins = lambda _inst_path: ["A", "B", "Y"]

    bare_model.hdlnx_tm_synth = synth
    bare_model.is_in_which_super_tile = None

    bare_model._extract_switch_matrix_info()  # noqa: SLF001

    assert bare_model.switch_matrix_hier_path == "tile_inst_switch_matrix"
    assert bare_model.switch_matrix_module_name == "tile_switch_matrix"
    assert bare_model.internal_pips_grouped_by_inst == {"mux0": ["A", "B", "Y"]}
    assert bare_model.internal_pips == ["A", "B", "Y"]


def test_extract_switch_matrix_info_none_found_returns_without_loading(
    bare_model: FABulousTileTimingModel,
) -> None:
    synth = DummyHdlnx()
    synth.find_instance_paths_by_regex = lambda _regex: []
    synth.find_verilog_modules_regex = lambda _regex: []

    bare_model.hdlnx_tm_synth = synth
    bare_model.switch_matrix_hier_path = None
    bare_model.switch_matrix_module_name = None
    bare_model.internal_pips_grouped_by_inst = None
    bare_model.internal_pips = None

    bare_model._extract_switch_matrix_info()  # noqa: SLF001

    assert bare_model.switch_matrix_hier_path == []
    assert bare_model.switch_matrix_module_name == []
    assert bare_model.internal_pips_grouped_by_inst is None
    assert bare_model.internal_pips is None


def test_extract_switch_matrix_info_regular_multiple_raises(
    bare_model: FABulousTileTimingModel,
) -> None:
    synth = DummyHdlnx()
    synth.find_instance_paths_by_regex = lambda _regex: ["a", "b"]
    synth.find_verilog_modules_regex = lambda _regex: ["m1", "m2"]
    bare_model.hdlnx_tm_synth = synth
    bare_model.is_in_which_super_tile = None

    with pytest.raises(
        ValueError,
        match="Multiple switch matrix instances or modules found for a non-SuperTile",
    ):
        bare_model._extract_switch_matrix_info()  # noqa: SLF001


def test_extract_switch_matrix_info_supertile_success(
    bare_model: FABulousTileTimingModel,
) -> None:
    synth = DummyHdlnx()
    synth.find_instance_paths_by_regex = lambda _regex: [
        "OTHER_switch_matrix",
        "TILE_A_switch_matrix",
    ]
    synth.find_verilog_modules_regex = lambda _regex: [
        "OTHER_switch_matrix_mod",
        "TILE_A_switch_matrix_mod",
    ]
    synth.get_module_instance_nets = lambda _module_name: {"mux0": ["I0", "I1", "O"]}
    synth.get_instance_pins = lambda _inst_path: ["I0", "I1", "O"]

    bare_model.hdlnx_tm_synth = synth
    bare_model.tile_name = "TILE_A"
    bare_model.unique_tile_name = "SUPER_X"
    bare_model.is_in_which_super_tile = "SUPER_X"

    bare_model._extract_switch_matrix_info()  # noqa: SLF001

    assert bare_model.switch_matrix_hier_path == "TILE_A_switch_matrix"
    assert bare_model.switch_matrix_module_name == "TILE_A_switch_matrix_mod"
    assert bare_model.internal_pips == ["I0", "I1", "O"]


def test_extract_switch_matrix_info_supertile_none_raises(
    bare_model: FABulousTileTimingModel,
) -> None:
    synth = DummyHdlnx()
    synth.find_instance_paths_by_regex = lambda _regex: ["OTHER_switch_matrix"]
    synth.find_verilog_modules_regex = lambda _regex: ["OTHER_switch_matrix_mod"]

    bare_model.hdlnx_tm_synth = synth
    bare_model.tile_name = "TILE_A"
    bare_model.unique_tile_name = "SUPER_X"
    bare_model.is_in_which_super_tile = "SUPER_X"

    with pytest.raises(
        ValueError,
        match="No switch matrix instance or module found for SuperTile SUPER_X",
    ):
        bare_model._extract_switch_matrix_info()  # noqa: SLF001


def test_extract_switch_matrix_info_supertile_multiple_raises(
    bare_model: FABulousTileTimingModel,
) -> None:
    synth = DummyHdlnx()
    synth.find_instance_paths_by_regex = lambda _regex: [
        "TILE_A_swm0",
        "TILE_A_swm1",
    ]
    synth.find_verilog_modules_regex = lambda _regex: ["TILE_A_mod0", "TILE_A_mod1"]

    bare_model.hdlnx_tm_synth = synth
    bare_model.tile_name = "TILE_A"
    bare_model.unique_tile_name = "SUPER_X"
    bare_model.is_in_which_super_tile = "SUPER_X"

    with pytest.raises(
        ValueError,
        match=(
            "Multiple switch matrix instances or modules found Tile TILE_A "
            "in SuperTile SUPER_X"
        ),
    ):
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


def test_is_tile_internal_pip_false_when_mapping_none(
    bare_model: FABulousTileTimingModel,
) -> None:
    bare_model.internal_pips_grouped_by_inst = None
    assert bare_model.is_tile_internal_pip("A", "Y") is False


def test_is_tile_internal_pip_false_when_same_src_and_dst(
    bare_model: FABulousTileTimingModel,
) -> None:
    bare_model.internal_pips_grouped_by_inst = {"mux0": ["A", "Y"]}
    assert bare_model.is_tile_internal_pip("A", "A") is False


def test_internal_pip_delay_structural_no_mux_raises_indexerror(
    bare_model: FABulousTileTimingModel,
) -> None:
    synth = DummyHdlnx()

    def _find_instances_paths_with_all_nets(
        _module_name: object, _nets: object, filter_regex: object = None
    ) -> list[object]:
        _ = filter_regex
        return []

    synth.find_instances_paths_with_all_nets = _find_instances_paths_with_all_nets

    bare_model.hdlnx_tm_synth = synth

    with pytest.raises(IndexError, match="list index out of range"):
        bare_model.internal_pip_delay_structural("A", "Y")


def test_internal_pip_delay_structural_success_and_caches(
    bare_model: FABulousTileTimingModel,
) -> None:
    class Synth(DummyHdlnx):
        def __init__(self) -> None:
            super().__init__()
            self.find_instances_calls = 0
            self.resolve_calls = 0

        def find_instances_paths_with_all_nets(
            self, _module_name: object, _nets: object, filter_regex: object = None
        ) -> list[str]:
            _ = filter_regex
            self.find_instances_calls += 1
            return ["mux0", "mux1"]

        def net_to_pin_paths_for_instance_resolved(
            self, _inst: object
        ) -> dict[str, list[str]]:
            self.resolve_calls += 1
            return {
                "A": ["mux0/A0", "mux0/A1"],
                "Y": ["mux0/Y0", "mux0/Y1"],
            }

        def single_delay(self, _src: object, _dst: object) -> float:
            return 0.123

    synth = Synth()
    bare_model.hdlnx_tm_synth = synth
    bare_model.internal_pip_cache = {}

    delay = bare_model.internal_pip_delay_structural("A", "Y")

    assert delay == 0.123
    assert synth.find_instances_calls == 1
    assert synth.resolve_calls == 1
    assert "Y" in bare_model.internal_pip_cache
    cache_entry = bare_model.internal_pip_cache["Y"]
    assert isinstance(cache_entry, InternalPipCacheEntry)
    assert cache_entry.begin_pip == "Y"
    assert cache_entry.swm_mux_for_pips == ["mux0", "mux1"]
    assert cache_entry.swm_mux_resolved == {
        "A": ["mux0/A0", "mux0/A1"],
        "Y": ["mux0/Y0", "mux0/Y1"],
    }


def test_internal_pip_delay_structural_cache_hit_reuses_cached_values(
    bare_model: FABulousTileTimingModel,
) -> None:
    class Synth(DummyHdlnx):
        def __init__(self) -> None:
            super().__init__()
            self.find_instances_calls = 0
            self.resolve_calls = 0

        def find_instances_paths_with_all_nets(
            self, _module_name: object, _nets: object, filter_regex: object = None
        ) -> list[str]:
            _ = filter_regex
            self.find_instances_calls += 1
            return ["should_not_be_used"]

        def net_to_pin_paths_for_instance_resolved(
            self, _inst: object
        ) -> dict[str, list[str]]:
            self.resolve_calls += 1
            return {"bad": ["bad"]}

        def single_delay(self, _src: object, _dst: object) -> float:
            return 1.5

    synth = Synth()
    bare_model.hdlnx_tm_synth = synth
    bare_model.internal_pip_cache = {
        "Y": InternalPipCacheEntry(
            begin_pip="Y",
            swm_mux_for_pips=["cached_mux"],
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

    assert delay == 1.5
    assert synth.find_instances_calls == 0
    assert synth.resolve_calls == 0


def test_internal_pip_delay_physical_cache_miss_multiple_ports(
    bare_model: FABulousTileTimingModel,
) -> None:
    class Synth(DummyHdlnx):
        def __init__(self) -> None:
            super().__init__()
            self.find_instances_calls = 0
            self.nearest_calls = 0

        def find_instances_paths_with_all_nets(
            self, _module_name: object, _nets: object, filter_regex: object = None
        ) -> list[str]:
            _ = filter_regex
            self.find_instances_calls += 1
            return ["mux0", "mux1"]

        def nearest_ports_from_instance_pin_nets(
            self,
            _inst_path: object,
            reverse: bool = False,
            num_ports: int = 1,
        ) -> tuple[dict[str, list[str]], list[str]]:
            _ = num_ports
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

        def single_delay(self, _src: object, _dst: object) -> float:
            return 0.456

    synth = Synth()
    phys = Phys()

    bare_model.hdlnx_tm_synth = synth
    bare_model.hdlnx_tm_phys = phys
    bare_model.internal_pip_cache = {}

    delay = bare_model.internal_pip_delay_physical("A", "Y")

    assert delay == 0.456
    assert synth.find_instances_calls == 1
    assert synth.nearest_calls == 1
    assert phys.earliest_calls == 1
    assert "Y" in bare_model.internal_pip_cache
    cache_entry = bare_model.internal_pip_cache["Y"]
    assert isinstance(cache_entry, InternalPipCacheEntry)
    assert cache_entry.begin_pip == "Y"
    assert cache_entry.swm_mux_for_pips == ["mux0", "mux1"]
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

        def find_instances_paths_with_all_nets(
            self, _module_name: object, _nets: object, filter_regex: object = None
        ) -> list[str]:
            _ = filter_regex
            return ["mux0"]

        def nearest_ports_from_instance_pin_nets(
            self,
            _inst_path: object,
            reverse: bool = False,
            num_ports: int = 1,
        ) -> tuple[dict[str, list[str]], list[str]]:
            _ = num_ports
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

        def single_delay(self, _src: object, _dst: object) -> float:
            return 0.789

    synth = Synth()
    phys = Phys()

    bare_model.hdlnx_tm_synth = synth
    bare_model.hdlnx_tm_phys = phys
    bare_model.internal_pip_cache = {}

    delay = bare_model.internal_pip_delay_physical("A", "Y")

    assert delay == 0.789
    assert synth.nearest_calls == 2
    cache_entry = bare_model.internal_pip_cache["Y"]
    assert cache_entry.swm_nearest_ports_out == ({"Y": ["OUT_REF"]}, ["OUT_REF"])
    assert cache_entry.swm_output_pin == (["PHYS_OUT"], 1, {})


def test_internal_pip_delay_physical_cache_hit_reuses_cached_values(
    bare_model: FABulousTileTimingModel,
) -> None:
    class Synth(DummyHdlnx):
        def __init__(self) -> None:
            super().__init__()
            self.find_instances_calls = 0
            self.nearest_calls = 0

        def find_instances_paths_with_all_nets(
            self, _module_name: object, _nets: object, filter_regex: object = None
        ) -> list[str]:
            _ = filter_regex
            self.find_instances_calls += 1
            return ["should_not_be_used"]

        def nearest_ports_from_instance_pin_nets(
            self,
            _inst_path: object,
            reverse: bool = False,
            num_ports: int = 1,
        ) -> tuple[dict[str, list[str]], list[str]]:
            _ = (reverse, num_ports)
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

        def single_delay(self, _src: object, _dst: object) -> float:
            return 1.234

    synth = Synth()
    phys = Phys()

    bare_model.hdlnx_tm_synth = synth
    bare_model.hdlnx_tm_phys = phys
    bare_model.internal_pip_cache = {
        "Y": InternalPipCacheEntry(
            begin_pip="Y",
            swm_mux_for_pips=["cached_mux"],
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

    assert delay == 1.234
    assert synth.find_instances_calls == 0
    assert synth.nearest_calls == 0
    assert phys.earliest_calls == 0


def test_external_pip_delay_structural_output_port_returns_default(
    bare_model: FABulousTileTimingModel,
) -> None:
    synth = DummyHdlnx()
    synth.output_ports = {"NN2BEG[3]"}
    bare_model.hdlnx_tm_synth = synth

    assert bare_model.external_pip_delay_structural("NN2BEG3", "X") == 0.001


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

    assert bare_model.external_pip_delay_structural("NN2BEG3", "X") == 0.001


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

        def single_delay(self, _src: object, _dst: object) -> float:
            return 0.222

    bare_model.hdlnx_tm_synth = Synth()

    assert bare_model.external_pip_delay_structural("NN2BEG3", "X") == 0.222


def test_external_pip_delay_structural_swm_to_swm_without_cache_returns_default(
    bare_model: FABulousTileTimingModel,
) -> None:
    synth = DummyHdlnx()
    synth.input_ports = {"IN0"}
    synth.output_ports = {"OUT0"}
    bare_model.hdlnx_tm_synth = synth
    bare_model.internal_pip_cache = {}

    assert bare_model.external_pip_delay_structural("SOME_INTERNAL", "X") == 0.001


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

        def single_delay(self, src: object, dst: object) -> float:
            assert src == "SWM_OUT_PIN"
            assert dst == "NEXT_INPUT_PIN"
            return 0.444

    bare_model.hdlnx_tm_synth = Synth()
    bare_model.internal_pip_cache = {
        "PIP_SRC": InternalPipCacheEntry(
            begin_pip="PIP_SRC",
            swm_mux_for_pips=["mux0"],
            swm_nearest_ports_in=None,
            swm_nearest_ports_out=None,
            swm_output_pin=None,
            swm_mux_resolved={"PIP_SRC": ["SWM_OUT_PIN"]},
        )
    }

    assert bare_model.external_pip_delay_structural("PIP_SRC", "X") == 0.444


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

        def single_delay(self, _src: object, _dst: object) -> float:
            return 0.0

    bare_model.hdlnx_tm_synth = Synth()
    bare_model.internal_pip_cache = {
        "PIP_SRC": InternalPipCacheEntry(
            begin_pip="PIP_SRC",
            swm_mux_for_pips=["mux0"],
            swm_nearest_ports_in=None,
            swm_nearest_ports_out=None,
            swm_output_pin=None,
            swm_mux_resolved={"PIP_SRC": ["SWM_OUT_PIN"]},
        )
    }

    assert bare_model.external_pip_delay_structural("PIP_SRC", "X") == 0.001


def test_external_pip_delay_physical_output_port_returns_default(
    bare_model: FABulousTileTimingModel,
) -> None:
    phys = DummyHdlnx()
    phys.output_ports = {"NN2BEG[3]"}
    bare_model.hdlnx_tm_phys = phys

    assert bare_model.external_pip_delay_physical("NN2BEG3", "X") == 0.001


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

    assert bare_model.external_pip_delay_physical("NN2BEG3", "X") == 0.001


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

        def single_delay(self, _src: object, _dst: object) -> float:
            return 0.333

    bare_model.hdlnx_tm_phys = Phys()

    assert bare_model.external_pip_delay_physical("NN2BEG3", "X") == 0.333


def test_external_pip_delay_physical_swm_to_swm_without_cache_returns_default(
    bare_model: FABulousTileTimingModel,
) -> None:
    phys = DummyHdlnx()
    phys.input_ports = {"IN0"}
    phys.output_ports = {"OUT0"}
    bare_model.hdlnx_tm_phys = phys
    bare_model.internal_pip_cache = {}

    assert bare_model.external_pip_delay_physical("SOME_INTERNAL", "X") == 0.001


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

        def single_delay(self, src: object, dst: object) -> float:
            assert src == "PHYS_OUT_PIN"
            assert dst == "NEXT_PHYS_INPUT"
            return 0.555

    bare_model.hdlnx_tm_phys = Phys()
    bare_model.internal_pip_cache = {
        "PIP_SRC": InternalPipCacheEntry(
            begin_pip="PIP_SRC",
            swm_mux_for_pips=["mux0"],
            swm_nearest_ports_in=None,
            swm_nearest_ports_out=None,
            swm_output_pin=(["PHYS_OUT_PIN"], 1, {}),
            swm_mux_resolved=None,
        )
    }

    assert bare_model.external_pip_delay_physical("PIP_SRC", "X") == 0.555


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

        def single_delay(self, _src: object, _dst: object) -> float:
            return 0.0

    bare_model.hdlnx_tm_phys = Phys()
    bare_model.internal_pip_cache = {
        "PIP_SRC": InternalPipCacheEntry(
            begin_pip="PIP_SRC",
            swm_mux_for_pips=["mux0"],
            swm_nearest_ports_in=None,
            swm_nearest_ports_out=None,
            swm_output_pin=(["PHYS_OUT_PIN"], 1, {}),
            swm_mux_resolved=None,
        )
    }

    assert bare_model.external_pip_delay_physical("PIP_SRC", "X") == 0.001


def test_internal_pip_delay_dispatch_physical(
    bare_model: FABulousTileTimingModel, monkeypatch: pytest.MonkeyPatch
) -> None:
    bare_model.tm_config.mode = TimingModelMode.PHYSICAL
    monkeypatch.setattr(bare_model, "internal_pip_delay_physical", lambda _s, _d: 1.23)
    monkeypatch.setattr(
        bare_model, "internal_pip_delay_structural", lambda _s, _d: 9.99
    )

    assert bare_model.internal_pip_delay("A", "Y") == 1.23


def test_internal_pip_delay_dispatch_structural(
    bare_model: FABulousTileTimingModel, monkeypatch: pytest.MonkeyPatch
) -> None:
    bare_model.tm_config.mode = TimingModelMode.STRUCTURAL
    monkeypatch.setattr(bare_model, "internal_pip_delay_physical", lambda _s, _d: 9.99)
    monkeypatch.setattr(
        bare_model, "internal_pip_delay_structural", lambda _s, _d: 2.34
    )

    assert bare_model.internal_pip_delay("A", "Y") == 2.34


def test_external_pip_delay_dispatch_physical(
    bare_model: FABulousTileTimingModel, monkeypatch: pytest.MonkeyPatch
) -> None:
    bare_model.tm_config.mode = TimingModelMode.PHYSICAL
    monkeypatch.setattr(bare_model, "external_pip_delay_physical", lambda _s, _d: 3.45)
    monkeypatch.setattr(
        bare_model, "external_pip_delay_structural", lambda _s, _d: 9.99
    )

    assert bare_model.external_pip_delay("A", "Y") == 3.45


def test_external_pip_delay_dispatch_structural(
    bare_model: FABulousTileTimingModel, monkeypatch: pytest.MonkeyPatch
) -> None:
    bare_model.tm_config.mode = TimingModelMode.STRUCTURAL
    monkeypatch.setattr(bare_model, "external_pip_delay_physical", lambda _s, _d: 9.99)
    monkeypatch.setattr(
        bare_model, "external_pip_delay_structural", lambda _s, _d: 4.56
    )

    assert bare_model.external_pip_delay("A", "Y") == 4.56


def test_pip_delay_dispatch_internal_applies_scaling_and_rounding(
    bare_model: FABulousTileTimingModel, monkeypatch: pytest.MonkeyPatch
) -> None:
    bare_model.tm_config.delay_scaling_factor = 2.5
    monkeypatch.setattr(bare_model, "is_tile_internal_pip", lambda _s, _d: True)
    monkeypatch.setattr(bare_model, "internal_pip_delay", lambda _s, _d: 1.23456)
    monkeypatch.setattr(bare_model, "external_pip_delay", lambda _s, _d: 9.99)

    assert bare_model.pip_delay("A", "Y") == round(1.23456 * 2.5, 3)


def test_pip_delay_dispatch_external_applies_scaling_and_rounding(
    bare_model: FABulousTileTimingModel, monkeypatch: pytest.MonkeyPatch
) -> None:
    bare_model.tm_config.delay_scaling_factor = 3.0
    monkeypatch.setattr(bare_model, "is_tile_internal_pip", lambda _s, _d: False)
    monkeypatch.setattr(bare_model, "internal_pip_delay", lambda _s, _d: 9.99)
    monkeypatch.setattr(bare_model, "external_pip_delay", lambda _s, _d: 0.33333)

    assert bare_model.pip_delay("A", "Y") == round(0.33333 * 3.0, 3)

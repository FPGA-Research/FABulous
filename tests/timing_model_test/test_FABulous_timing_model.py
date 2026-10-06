from collections.abc import Callable
from pathlib import Path

import pytest
from pytest_mock import MockerFixture

import fabulous.fabric_cad.timing_model.FABulous_timing_model as tm_mod
from fabulous.fabric_cad.timing_model.FABulous_timing_model import (
    FABulousTileTimingModel,
)
from fabulous.fabric_cad.timing_model.hdlnx.hdlnx_timing_model import HdlnxTimingModel
from fabulous.fabric_cad.timing_model.models import (
    DelayType,
    InternalPipCacheEntry,
    TimingModelConfig,
    TimingModelMode,
    TimingModelTileSourceFiles,
)

MUX = "Inst_TILE_switch_matrix/inst_cus_mux21_N1BEG0/cell0"
SWM_BUF = "Inst_TILE_switch_matrix/inst_cus_buf_JN2BEG0/cell0"

# A one-tile fabric slice: a 2:1 mux and a 1-input buffer in the switch matrix,
# tile-level buffers on E1END, FrameData and W1END, and the jump wire JN2BEG0
# leaving the tile as E1BEG[0]. W1END[0] reaches no output.
TILE_NETLIST = """
module cus_mux21 (A0, A1, S, X);
    MUX2 cell0 ( .A0(A0), .A1(A1), .S(S), .X(X) );
endmodule

module cus_buf (A, X);
    BUF cell0 ( .A(A), .X(X) );
endmodule

module TILE_switch_matrix (N1END0, E1END0, ConfigBits0, N1BEG0, JN2BEG0);
    cus_mux21 inst_cus_mux21_N1BEG0 ( .A0(N1END0), .A1(E1END0), .S(ConfigBits0), .X(N1BEG0) );
    cus_buf inst_cus_buf_JN2BEG0 ( .A(N1END0), .X(JN2BEG0) );
endmodule

module TILE (N1END, E1END, FrameData, W1END, N1BEG, E1BEG);
    wire e_int;
    wire cfg_int;
    wire n1beg_int;
    wire jn2beg;
    wire w_nc;
    BUF inst_e_buf ( .A(E1END[0]), .X(e_int) );
    BUF inst_cfg_buf ( .A(FrameData[0]), .X(cfg_int) );
    BUF inst_w_buf ( .A(W1END[0]), .X(w_nc) );
    TILE_switch_matrix Inst_TILE_switch_matrix ( .N1END0(N1END[0]), .E1END0(e_int), .ConfigBits0(cfg_int), .N1BEG0(n1beg_int), .JN2BEG0(jn2beg) );
    BUF inst_n1beg_buf ( .A(n1beg_int), .X(N1BEG[0]) );
    BUF inst_jump_buf ( .A(jn2beg), .X(E1BEG[0]) );
endmodule
"""  # noqa: E501

# Two tiles of one SuperTile, each with its own switch matrix.
SUPER_TILE_NETLIST = """
module cus_buf (A, X);
    BUF cell0 ( .A(A), .X(X) );
endmodule

module TILE_A_switch_matrix (I0, O);
    cus_buf inst_cus_buf_O ( .A(I0), .X(O) );
endmodule

module TILE_B_switch_matrix (I0, O);
    cus_buf inst_cus_buf_O ( .A(I0), .X(O) );
endmodule

module TILE_A (I, O);
    TILE_A_switch_matrix Inst_TILE_A_switch_matrix ( .I0(I), .O(O) );
endmodule

module TILE_B (I, O);
    TILE_B_switch_matrix Inst_TILE_B_switch_matrix ( .I0(I), .O(O) );
endmodule

module SUPER (IA, OA, IB, OB);
    TILE_A Tile_X0Y0_TILE_A ( .I(IA), .O(OA) );
    TILE_B Tile_X0Y1_TILE_B ( .I(IB), .O(OB) );
endmodule
"""

NO_SWITCH_MATRIX_NETLIST = """
module LUT (I, O);
    BUF u0 ( .A(I), .X(O) );
endmodule
"""


def _sdf(
    interconnects: list[tuple[str, str, float]],
    cells: dict[str, tuple[str, list[tuple[str, str, float]]]],
) -> str:
    """Render an SDF file with one single-triple delay per arc."""
    wires = "".join(
        f"  (INTERCONNECT {a} {b} ({d}::{d}))\n" for a, b, d in interconnects
    )
    text = (
        '(DELAYFILE (SDFVERSION "3.0") (DESIGN "TILE") (DIVIDER /)\n'
        f'(CELL (CELLTYPE "TILE") (INSTANCE)\n (DELAY (ABSOLUTE\n{wires} )))\n'
    )
    for instance, (cell_type, arcs) in cells.items():
        paths = "".join(f"  (IOPATH {a} {b} ({d}::{d}))\n" for a, b, d in arcs)
        text += (
            f'(CELL (CELLTYPE "{cell_type}") (INSTANCE {instance})\n'
            f" (DELAY (ABSOLUTE\n{paths} )))\n"
        )
    return text + ")\n"


def synth_sdf(*, jump_wire: float = 0.11, jump_buf: float = 1.0) -> str:
    """Return the STA view of the synthesised `TILE_NETLIST`."""
    return _sdf(
        [
            ("N1END[0]", f"{MUX}/A0", 0.01),
            ("N1END[0]", f"{SWM_BUF}/A", 0.02),
            ("E1END[0]", "inst_e_buf/A", 0.03),
            ("inst_e_buf/X", f"{MUX}/A1", 0.04),
            ("FrameData[0]", "inst_cfg_buf/A", 0.05),
            ("inst_cfg_buf/X", f"{MUX}/S", 0.06),
            ("W1END[0]", "inst_w_buf/A", 0.07),
            (f"{MUX}/X", "inst_n1beg_buf/A", 0.08),
            ("inst_n1beg_buf/X", "N1BEG[0]", 0.09),
            (f"{SWM_BUF}/X", "inst_jump_buf/A", jump_wire),
            ("inst_jump_buf/X", "E1BEG[0]", 0.12),
        ],
        {
            MUX: ("MUX2", [("A0", "X", 0.2), ("A1", "X", 0.3), ("S", "X", 0.4)]),
            SWM_BUF: ("BUF", [("A", "X", 0.5)]),
            "inst_e_buf": ("BUF", [("A", "X", 0.6)]),
            "inst_cfg_buf": ("BUF", [("A", "X", 0.7)]),
            "inst_w_buf": ("BUF", [("A", "X", 0.8)]),
            "inst_n1beg_buf": ("BUF", [("A", "X", 0.9)]),
            "inst_jump_buf": ("BUF", [("A", "X", jump_buf)]),
        },
    )


def phys_sdf(*, swm_buf: float = 0.7, jump_wire: float = 0.11) -> str:
    """Return the STA view of the hardened tile: an input buffer on every port."""
    return _sdf(
        [
            ("N1END[0]", "input1/A", 0.001),
            ("input1/X", f"{MUX}/A0", 0.02),
            ("input1/X", f"{SWM_BUF}/A", 0.03),
            ("E1END[0]", "input2/A", 0.001),
            ("input2/X", "inst_e_buf/A", 0.04),
            ("inst_e_buf/X", f"{MUX}/A1", 0.05),
            ("FrameData[0]", "input3/A", 0.001),
            ("input3/X", "inst_cfg_buf/A", 0.06),
            ("inst_cfg_buf/X", f"{MUX}/S", 0.07),
            ("W1END[0]", "input4/A", 0.001),
            ("input4/X", "inst_w_buf/A", 0.08),
            (f"{MUX}/X", "inst_n1beg_buf/A", 0.09),
            ("inst_n1beg_buf/X", "N1BEG[0]", 0.1),
            (f"{SWM_BUF}/X", "inst_jump_buf/A", jump_wire),
            ("inst_jump_buf/X", "E1BEG[0]", 0.12),
        ],
        {
            "input1": ("BUF", [("A", "X", 0.1)]),
            "input2": ("BUF", [("A", "X", 0.1)]),
            "input3": ("BUF", [("A", "X", 0.1)]),
            "input4": ("BUF", [("A", "X", 0.1)]),
            MUX: ("MUX2", [("A0", "X", 0.4), ("A1", "X", 0.5), ("S", "X", 0.6)]),
            SWM_BUF: ("BUF", [("A", "X", swm_buf)]),
            "inst_e_buf": ("BUF", [("A", "X", 0.8)]),
            "inst_cfg_buf": ("BUF", [("A", "X", 0.9)]),
            "inst_w_buf": ("BUF", [("A", "X", 1.0)]),
            "inst_n1beg_buf": ("BUF", [("A", "X", 1.1)]),
            "inst_jump_buf": ("BUF", [("A", "X", 1.2)]),
        },
    )


def make_source_override(
    *,
    rtl_files: Path | list[Path] | None = None,
    netlist_file: Path | None = None,
    rc_file: Path | None = None,
) -> TimingModelTileSourceFiles:
    return TimingModelTileSourceFiles(
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
    custom_per_tile_source_files: dict[str, TimingModelTileSourceFiles] | None = None,
    delay_scaling_factor: float = 1.0,
) -> TimingModelConfig:
    return TimingModelConfig(
        project_dir=tmp_path,
        liberty_files=[tmp_path / "lib.lib"],
        delay_type_str=DelayType.MAX_ALL,
        debug=debug,
        synth_executable="yosys",
        sta_executable="opensta",
        techmap_files=[tmp_path / "techmap.v"],
        tiehi_cell_and_port="TIEHI Y",
        tielo_cell_and_port="TIELO Y",
        min_buf_cell_and_ports="BUF A Y",
        consider_wire_delay=consider_wire_delay,
        mode=mode,
        custom_per_tile_source_files=custom_per_tile_source_files,
        delay_scaling_factor=delay_scaling_factor,
    )


class FakeYosysTool:
    """Yosys stand-in: the tile source on disc is already the gate-level netlist."""

    def __init__(
        self,
        *,
        verilog_files: list[Path] | Path,
        top_name: str,
        liberty_files: list[Path],
        **_kwargs: object,
    ) -> None:
        self.synth_rtl_files: list[Path] | Path = verilog_files
        self.synth_design_name = top_name
        self.synth_liberty_files = liberty_files
        self.synth_passthrough = False
        self.synth_netlist_file: Path | None = None

    def synth_synthesize(self) -> None:
        """Hand back the netlist the fixture wrote."""
        rtl = self.synth_rtl_files
        self.synth_netlist_file = rtl if isinstance(rtl, Path) else rtl[0]

    def synth_clean_up(self) -> None:
        """Do nothing; `tmp_path` owns the netlist."""


class FakeOpenStaTool:
    """OpenSTA stand-in: the SDF of a netlist is written next to it by the fixture."""

    def __init__(self, **_kwargs: object) -> None:
        self.sta_netlist_file: Path | None = None
        self.sta_design_name: str | None = None
        self.sta_liberty_files: list[Path] | None = None
        self.sta_rc_files: Path | None = None
        self.sta_sdf_file: Path | None = None

    def sta_analyze(self) -> None:
        """Point at the SDF beside the netlist."""
        self.sta_sdf_file = self.sta_netlist_file.with_suffix(".sdf")

    def sta_clean_up(self) -> None:
        """Do nothing; `tmp_path` owns the SDF."""


def hdlnx_model(tmp_path: Path, netlist: str, top_name: str) -> HdlnxTimingModel:
    """Build a real timing model of `netlist` with a placeholder SDF."""
    netlist_file = tmp_path / f"{top_name}.v"
    netlist_file.write_text(netlist)
    netlist_file.with_suffix(".sdf").write_text(
        _sdf([], {"u0": ("BUF", [("A", "X", 0.1)])})
    )
    synth_tool = FakeYosysTool(
        verilog_files=[netlist_file], top_name=top_name, liberty_files=[]
    )
    return HdlnxTimingModel(FakeOpenStaTool(), synth_tool, DelayType.MAX_ALL)


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


@pytest.fixture
def bare_model(tmp_path: Path) -> FABulousTileTimingModel:
    m = FABulousTileTimingModel.__new__(FABulousTileTimingModel)
    m.fabric = DummyFabric([])
    m.tile_name = "TILE_A"
    m.unique_tile_name = "TILE_A"
    m.is_in_which_super_tile = None
    m.tm_config = make_config(tmp_path)
    m.verilog_files = None
    m.hdlnx_tm_synth = None
    m.hdlnx_tm_phys = None
    m.switch_matrix_hier_path = None
    m.switch_matrix_module_name = None
    m.internal_pips_grouped_by_inst = None
    m.internal_pips = None
    m.internal_pip_cache = {}
    return m


TileModelFactory = Callable[..., FABulousTileTimingModel]


@pytest.fixture
def make_tile_model(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> TileModelFactory:
    """Build `FABulousTileTimingModel` for `TILE_NETLIST` through `__init__`.

    Only the external Yosys and OpenSTA runs are replaced; the netlists and SDFs
    they would produce sit where the project layout puts them.
    """
    monkeypatch.setattr(tm_mod, "YosysTool", FakeYosysTool)
    monkeypatch.setattr(tm_mod, "OpenStaTool", FakeOpenStaTool)

    def build(
        *,
        mode: TimingModelMode,
        delay_scaling_factor: float = 1.0,
        synth: str | None = None,
        phys: str | None = None,
    ) -> FABulousTileTimingModel:
        tile_dir = tmp_path / "Tile" / "TILE"
        nl_dir = tile_dir / "macro" / "final_views" / "nl"
        nl_dir.mkdir(parents=True, exist_ok=True)
        (tile_dir / "TILE.v").write_text(TILE_NETLIST)
        (tile_dir / "TILE.sdf").write_text(synth or synth_sdf())
        (nl_dir / "TILE.nl.v").write_text(TILE_NETLIST)
        (nl_dir / "TILE.nl.sdf").write_text(phys or phys_sdf())
        config = make_config(
            tmp_path, mode=mode, delay_scaling_factor=delay_scaling_factor
        )
        return FABulousTileTimingModel(config, DummyFabric([]), tile_name="TILE")

    return build


@pytest.mark.parametrize(
    "mode",
    [TimingModelMode.STRUCTURAL, TimingModelMode.PHYSICAL],
    ids=["structural", "physical"],
)
def test_init_discovers_rtl_and_switch_matrix(
    make_tile_model: TileModelFactory, tmp_path: Path, mode: TimingModelMode
) -> None:
    model = make_tile_model(mode=mode)

    assert model.unique_tile_name == "TILE"
    assert model.is_in_which_super_tile is None
    assert model.verilog_files == [tmp_path / "Tile" / "TILE" / "TILE.v"]
    assert model.switch_matrix_hier_path == "Inst_TILE_switch_matrix"
    assert model.switch_matrix_module_name == "TILE_switch_matrix"
    assert model.internal_pips_grouped_by_inst == {
        "inst_cus_mux21_N1BEG0": ["N1END0", "E1END0", "ConfigBits0", "N1BEG0"],
        "inst_cus_buf_JN2BEG0": ["N1END0", "JN2BEG0"],
    }
    assert model.internal_pips == [
        "N1END0",
        "E1END0",
        "ConfigBits0",
        "N1BEG0",
        "JN2BEG0",
    ]
    assert model.internal_pip_cache == {}
    assert sorted(model.hdlnx_tm_synth.input_ports) == [
        "E1END[0]",
        "FrameData[0]",
        "N1END[0]",
        "W1END[0]",
    ]
    if mode == TimingModelMode.STRUCTURAL:
        assert model.hdlnx_tm_phys is None
    else:
        # the physical model is read from the hardened netlist's SDF
        assert model.hdlnx_tm_phys.has_path("N1END[0]", "input1/X")


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


# `TimingModelConfig` rejects these values; `model_copy` skips validation to reach
# the guard that a new enum member without a `case` would hit.
@pytest.mark.parametrize(
    ("field", "match"),
    [
        ("synth_program", "Unsupported synthesis tool: bad"),
        ("sta_program", "Unsupported STA tool: bad"),
    ],
    ids=["synth", "sta"],
)
def test_cad_tools_unsupported_tool_raises(
    tmp_path: Path, bare_model: FABulousTileTimingModel, field: str, match: str
) -> None:
    bare_model.tm_config = make_config(tmp_path).model_copy(update={field: "bad"})
    with pytest.raises(ValueError, match=match):
        bare_model._cad_tools()  # noqa: SLF001


class DummySynthTool:
    def __init__(self) -> None:
        self.synth_rtl_files: Path | None = None
        self.synth_passthrough = False


class DummyStaTool:
    def __init__(self) -> None:
        self.sta_rc_files: Path | None = None


NETLIST = Path("Tile/TILE_A/macro/final_views/nl/TILE_A.nl.v")
SPEF = Path("Tile/TILE_A/macro/final_views/spef/nom/TILE_A.nom.spef")


# Each built model is recorded with the tool state it saw at construction:
# (synth_rtl_files, synth_passthrough, sta_rc_files), relative to `tmp_path`.
@pytest.mark.parametrize(
    ("mode", "consider_wire_delay", "overrides", "expected_states"),
    [
        (TimingModelMode.STRUCTURAL, True, None, [(None, False, None)]),
        (
            TimingModelMode.PHYSICAL,
            False,
            None,
            [(None, False, None), (NETLIST, True, None)],
        ),
        (
            TimingModelMode.PHYSICAL,
            True,
            None,
            [(None, False, None), (NETLIST, True, SPEF)],
        ),
        (
            TimingModelMode.PHYSICAL,
            False,
            {"TILE_A": {"netlist_file": "custom.nl.v"}},
            [(None, False, None), (Path("custom.nl.v"), True, None)],
        ),
        (
            TimingModelMode.PHYSICAL,
            True,
            {"TILE_A": {"rc_file": "custom.nom.spef"}},
            [(None, False, None), (NETLIST, True, Path("custom.nom.spef"))],
        ),
        (
            TimingModelMode.PHYSICAL,
            True,
            {"OTHER_TILE": {"netlist_file": "other.nl.v", "rc_file": "other.spef"}},
            [(None, False, None), (NETLIST, True, SPEF)],
        ),
    ],
    ids=[
        "structural",
        "physical_without_wire_delay",
        "physical_with_wire_delay",
        "physical_custom_netlist",
        "physical_custom_rc_file",
        "physical_override_for_other_tile",
    ],
)
def test_initialize_timing_models(
    tmp_path: Path,
    bare_model: FABulousTileTimingModel,
    monkeypatch: pytest.MonkeyPatch,
    mode: TimingModelMode,
    consider_wire_delay: bool,
    overrides: dict[str, dict[str, str]] | None,
    expected_states: list[tuple[Path | None, bool, Path | None]],
) -> None:
    synth_tool = DummySynthTool()
    sta_tool = DummyStaTool()
    created = []

    def relative(path: Path | None) -> Path | None:
        return None if path is None else path.relative_to(tmp_path)

    class FakeHdlnxTimingModel:
        def __init__(
            self, sta: object, synth: object, delay_type: object, debug: object
        ) -> None:
            assert sta is sta_tool
            assert synth is synth_tool
            created.append(
                (
                    delay_type,
                    debug,
                    (
                        relative(synth_tool.synth_rtl_files),
                        synth_tool.synth_passthrough,
                        relative(sta_tool.sta_rc_files),
                    ),
                )
            )

    monkeypatch.setattr(
        bare_model,
        "_cad_tools",
        lambda: {"synth_tool": synth_tool, "sta_tool": sta_tool},
    )
    monkeypatch.setattr(tm_mod, "HdlnxTimingModel", FakeHdlnxTimingModel)
    bare_model.tm_config = make_config(
        tmp_path,
        mode=mode,
        consider_wire_delay=consider_wire_delay,
        debug=True,
        custom_per_tile_source_files=None
        if overrides is None
        else {
            tile: make_source_override(
                **{key: tmp_path / name for key, name in files.items()}
            )
            for tile, files in overrides.items()
        },
    )

    bare_model._initialize_timing_models()  # noqa: SLF001

    assert created == [(DelayType.MAX_ALL, True, state) for state in expected_states]


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


@pytest.mark.parametrize(
    (
        "netlist",
        "top_name",
        "tile_name",
        "super_tile",
        "expected_hier_path",
        "expected_module",
        "expected_grouped",
        "expected_pips",
    ),
    [
        (
            TILE_NETLIST,
            "TILE",
            "TILE",
            None,
            "Inst_TILE_switch_matrix",
            "TILE_switch_matrix",
            {
                "inst_cus_mux21_N1BEG0": ["N1END0", "E1END0", "ConfigBits0", "N1BEG0"],
                "inst_cus_buf_JN2BEG0": ["N1END0", "JN2BEG0"],
            },
            ["N1END0", "E1END0", "ConfigBits0", "N1BEG0", "JN2BEG0"],
        ),
        (
            SUPER_TILE_NETLIST,
            "SUPER",
            "TILE_B",
            "SUPER",
            "Tile_X0Y1_TILE_B/Inst_TILE_B_switch_matrix",
            "TILE_B_switch_matrix",
            {"inst_cus_buf_O": ["I0", "O"]},
            ["I0", "O"],
        ),
        # all PIPs of a tile without a switch matrix are external
        (NO_SWITCH_MATRIX_NETLIST, "LUT", "LUT", None, [], [], None, None),
    ],
    ids=["regular_tile", "tile_in_super_tile", "no_switch_matrix"],
)
def test_extract_switch_matrix_info(
    tmp_path: Path,
    bare_model: FABulousTileTimingModel,
    netlist: str,
    top_name: str,
    tile_name: str,
    super_tile: str | None,
    expected_hier_path: str | list[str],
    expected_module: str | list[str],
    expected_grouped: dict[str, list[str]] | None,
    expected_pips: list[str] | None,
) -> None:
    bare_model.hdlnx_tm_synth = hdlnx_model(tmp_path, netlist, top_name)
    bare_model.tile_name = tile_name
    bare_model.unique_tile_name = super_tile or tile_name
    bare_model.is_in_which_super_tile = super_tile

    bare_model._extract_switch_matrix_info()  # noqa: SLF001

    assert bare_model.switch_matrix_hier_path == expected_hier_path
    assert bare_model.switch_matrix_module_name == expected_module
    assert bare_model.internal_pips_grouped_by_inst == expected_grouped
    assert bare_model.internal_pips == expected_pips


@pytest.mark.parametrize(
    ("tile_name", "super_tile", "match"),
    [
        (
            "SUPER",
            None,
            "Multiple switch matrix instances or modules found for a non-SuperTile",
        ),
        ("TILE_C", "SUPER", "No switch matrix instance or module found for SuperTile"),
        # tile names are matched as substrings, so "TILE" claims both matrices
        (
            "TILE",
            "SUPER",
            "Multiple switch matrix instances or modules found Tile TILE "
            "in SuperTile SUPER",
        ),
    ],
    ids=["regular_tile_with_two", "super_tile_none", "super_tile_two"],
)
def test_extract_switch_matrix_info_raises(
    tmp_path: Path,
    bare_model: FABulousTileTimingModel,
    tile_name: str,
    super_tile: str | None,
    match: str,
) -> None:
    bare_model.hdlnx_tm_synth = hdlnx_model(tmp_path, SUPER_TILE_NETLIST, "SUPER")
    bare_model.tile_name = tile_name
    bare_model.unique_tile_name = super_tile or tile_name
    bare_model.is_in_which_super_tile = super_tile

    with pytest.raises(ValueError, match=match):
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


INTERNAL_PIPS = [("N1END0", "N1BEG0"), ("E1END0", "N1BEG0"), ("N1END0", "JN2BEG0")]
# Output port, input-port twist, input port reaching no output, jump wire before
# and after the internal PIP that drives it is cached.
EXTERNAL_PIPS = [
    ("N1BEG0", "S1END0"),
    ("E1END0", "E1BEG0"),
    ("W1END0", "W1BEG0"),
    ("JN2BEG0", "JN2END0"),
    ("N1END0", "JN2BEG0"),
    ("JN2BEG0", "JN2END0"),
]


# Expected delays are hand sums of the arcs in `synth_sdf` / `phys_sdf`.
@pytest.mark.parametrize(
    ("mode", "pips", "expected"),
    [
        # mux A0->X, mux A1->X, switch-matrix buffer A->X
        (TimingModelMode.STRUCTURAL, INTERNAL_PIPS, [0.2, 0.3, 0.5]),
        # from the nearest tile input to the mux output pin found by convergence;
        # for the single-input buffer, step 3 towards E1BEG[0] is its A pin
        (TimingModelMode.PHYSICAL, INTERNAL_PIPS, [0.521, 1.491, 0.131]),
        (
            TimingModelMode.STRUCTURAL,
            EXTERNAL_PIPS,
            [0.001, 2.04, 0.001, 0.001, 0.5, 1.11],
        ),
        (
            TimingModelMode.PHYSICAL,
            EXTERNAL_PIPS,
            [0.001, 2.781, 0.001, 0.001, 0.131, 0.81],
        ),
    ],
    ids=[
        "internal_structural",
        "internal_physical",
        "external_structural",
        "external_physical",
    ],
)
def test_pip_delay(
    make_tile_model: TileModelFactory,
    mode: TimingModelMode,
    pips: list[tuple[str, str]],
    expected: list[float],
) -> None:
    model = make_tile_model(mode=mode)

    assert [model.pip_delay(src, dst) for src, dst in pips] == expected


def test_pip_delay_applies_scaling_factor(make_tile_model: TileModelFactory) -> None:
    model = make_tile_model(mode=TimingModelMode.STRUCTURAL, delay_scaling_factor=2.5)

    assert model.pip_delay("N1END0", "N1BEG0") == 0.5
    assert model.pip_delay("E1END0", "E1BEG0") == 5.1


@pytest.mark.parametrize(
    ("mode", "sdfs"),
    [
        (TimingModelMode.STRUCTURAL, {"synth": synth_sdf(jump_wire=0.0, jump_buf=0.0)}),
        (TimingModelMode.PHYSICAL, {"phys": phys_sdf(swm_buf=0.0, jump_wire=0.0)}),
    ],
    ids=["structural", "physical"],
)
def test_pip_delay_zero_jump_wire_uses_default_delay(
    make_tile_model: TileModelFactory, mode: TimingModelMode, sdfs: dict[str, str]
) -> None:
    model = make_tile_model(mode=mode, **sdfs)
    model.pip_delay("N1END0", "JN2BEG0")

    assert model.pip_delay("JN2BEG0", "JN2END0") == 0.001


def test_internal_pip_delay_structural_caches_per_destination(
    make_tile_model: TileModelFactory, mocker: MockerFixture
) -> None:
    model = make_tile_model(mode=TimingModelMode.STRUCTURAL)
    finder = mocker.spy(model.hdlnx_tm_synth, "find_instances_paths_with_all_nets")

    first = model.internal_pip_delay_structural("N1END0", "N1BEG0")
    second = model.internal_pip_delay_structural("E1END0", "N1BEG0")

    assert (first, second) == (0.2, 0.3)
    assert finder.call_count == 1
    assert model.internal_pip_cache == {
        "N1BEG0": InternalPipCacheEntry(
            begin_pip="N1BEG0",
            swm_mux_for_pips=["Inst_TILE_switch_matrix/inst_cus_mux21_N1BEG0"],
            swm_nearest_ports_in=None,
            swm_nearest_ports_out=None,
            swm_output_pin=None,
            swm_mux_resolved={
                "N1END0": [f"{MUX}/A0"],
                "E1END0": [f"{MUX}/A1"],
                "ConfigBits0": [f"{MUX}/S"],
                "N1BEG0": [f"{MUX}/X"],
            },
        )
    }


def test_internal_pip_delay_physical_caches_per_destination(
    make_tile_model: TileModelFactory, mocker: MockerFixture
) -> None:
    model = make_tile_model(mode=TimingModelMode.PHYSICAL)
    finder = mocker.spy(model.hdlnx_tm_synth, "find_instances_paths_with_all_nets")
    converge = mocker.spy(model.hdlnx_tm_phys, "earliest_common_nodes")

    first = model.internal_pip_delay_physical("N1END0", "N1BEG0")
    second = model.internal_pip_delay_physical("E1END0", "N1BEG0")

    assert (round(first, 3), round(second, 3)) == (0.521, 1.491)
    assert finder.call_count == 1
    assert converge.call_count == 1
    entry = model.internal_pip_cache["N1BEG0"]
    assert entry.swm_mux_for_pips == ["Inst_TILE_switch_matrix/inst_cus_mux21_N1BEG0"]
    assert entry.swm_nearest_ports_in == (
        {
            "N1END0": ["N1END[0]"],
            "E1END0": ["E1END[0]"],
            "ConfigBits0": ["FrameData[0]"],
            "N1BEG0": ["N1END[0]"],
        },
        ["N1END[0]", "E1END[0]", "FrameData[0]"],
    )
    # several tile inputs feed the mux, so no output port is used as sentinel
    assert entry.swm_nearest_ports_out is None
    assert entry.swm_output_pin[:2] == ([f"{MUX}/X"], 6)
    assert entry.swm_mux_resolved is None


def test_internal_pip_delay_physical_single_input_cache_hit(
    make_tile_model: TileModelFactory, mocker: MockerFixture
) -> None:
    model = make_tile_model(mode=TimingModelMode.PHYSICAL)
    nearest = mocker.spy(model.hdlnx_tm_synth, "nearest_ports_from_instance_pin_nets")

    first = model.internal_pip_delay_physical("N1END0", "JN2BEG0")
    second = model.internal_pip_delay_physical("N1END0", "JN2BEG0")

    assert (round(first, 3), round(second, 3)) == (0.131, 0.131)
    # the miss looks up input and output ports; the hit reads both from the cache
    assert nearest.call_count == 2
    # one tile input feeds the buffer, so its output port is the sentinel
    assert model.internal_pip_cache["JN2BEG0"].swm_nearest_ports_out == (
        {"N1END0": ["E1BEG[0]"], "JN2BEG0": ["E1BEG[0]"]},
        ["E1BEG[0]"],
    )


def test_internal_pip_delay_structural_without_common_mux_raises(
    make_tile_model: TileModelFactory,
) -> None:
    model = make_tile_model(mode=TimingModelMode.STRUCTURAL)

    with pytest.raises(IndexError, match="list index out of range"):
        model.internal_pip_delay_structural("E1END0", "JN2BEG0")

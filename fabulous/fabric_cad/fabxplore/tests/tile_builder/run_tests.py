"""Ad-hoc tests for FABulous tile building."""

from __future__ import annotations

import shutil
from dataclasses import dataclass, field
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import TYPE_CHECKING

from fabulous.fabric_cad.fabxplore.flow.architecture_synthesizer import (
    ArchitectureSynthesizer,
)
from fabulous.fabric_cad.fabxplore.modules.tile_builder import (
    BaselineRouting,
    TileBel,
)
from fabulous.fabric_cad.fabxplore.modules.tile_builder.core import (
    baseline_list_generator,
)
from fabulous.fabric_cad.fabxplore.modules.tile_builder.core import (
    builder as builder_mod,
)
from fabulous.fabric_cad.fabxplore.modules.tile_builder.core.base_model import (
    build_base_routing_model,
)
from fabulous.fabric_cad.fabxplore.modules.tile_builder.core.models import (
    TileBuilderOptions,
)
from fabulous.fabric_cad.fabxplore.pnr.custom_passes.tile_builder_pass import (
    TileBuilderPass,
)
from fabulous.fabric_cad.fabxplore.pyosys.pyosys_bridge import PyosysBridge
from fabulous.fabric_definition.define import IO
from fabulous.fabulous_cli.helper import setup_logger

if TYPE_CHECKING:
    from collections.abc import Callable

setup_logger(verbosity=0, debug=False)


@dataclass
class _FakeBel:
    """Small BEL stand-in for tile-builder tests.

    Attributes
    ----------
    src : Path
        BEL RTL path.
    prefix : str
        Instance prefix.
    module_name : str
        Parsed module name.
    inputs : list[str]
        Parsed internal input ports.
    outputs : list[str]
        Parsed internal output ports.
    configBit : int
        Number of BEL config bits.
    carry : dict[str, dict[IO, str]]
        Parsed carry-chain ports.
    localShared : dict[str, tuple[str, IO]]
        Parsed local shared ports.
    withUserCLK : bool
        Whether the BEL has a user clock.
    """

    src: Path
    prefix: str
    module_name: str = "toy_bel"
    inputs: list[str] = field(default_factory=list)
    outputs: list[str] = field(default_factory=list)
    configBit: int = 2
    carry: dict[str, dict[IO, str]] = field(default_factory=dict)
    localShared: dict[str, tuple[str, IO]] = field(default_factory=dict)
    withUserCLK: bool = False


@dataclass
class _FakeTile:
    """Small FABulous tile stand-in.

    Attributes
    ----------
    name : str
        Tile name.
    matrixConfigBits : int
        Switch-matrix config bits.
    globalConfigBits : int
        Total tile config bits.
    """

    name: str
    matrixConfigBits: int
    globalConfigBits: int


class _FakeFabric:
    """Small FABulous fabric stand-in.

    Parameters
    ----------
    fabric_dir : Path
        Fabric CSV path.
    tile : _FakeTile
        Tile returned by ``getTileByName``.
    """

    def __init__(self, fabric_dir: Path, tile: _FakeTile) -> None:
        self.fabric_dir = fabric_dir
        self.frameBitsPerRow = 8
        self.maxFramesPerCol = 8
        self.tile = tile

    def getTileByName(self, name: str) -> _FakeTile:
        """Return the fake tile.

        Parameters
        ----------
        name : str
            Requested tile name.

        Returns
        -------
        _FakeTile
            Fake tile.
        """
        _ = name
        return self.tile


class _FakeFab:
    """Small FABulous API stand-in.

    Parameters
    ----------
    fabric_csv : Path
        Fabric CSV path.
    tile : _FakeTile
        Tile returned by the fake fabric object.
    """

    def __init__(self, fabric_csv: Path, tile: _FakeTile) -> None:
        self.fabric = _FakeFabric(fabric_csv, tile)
        self.fileExtension = ".v"
        self.output_file: Path | None = None
        self.loaded = False
        self.config_mem_existed_at_gen: bool | None = None

    def setWriterOutputFile(self, output_file: Path) -> None:
        """Record the active output path.

        Parameters
        ----------
        output_file : Path
            Output path.
        """
        self.output_file = output_file

    def loadFabric(self, fabric_csv: Path) -> None:
        """Record a fabric load.

        Parameters
        ----------
        fabric_csv : Path
            Fabric CSV path.
        """
        self.loaded = True
        self.fabric.fabric_dir = fabric_csv

    def genSwitchMatrix(self, tile_name: str) -> None:
        """Write fake switch-matrix artifacts.

        Parameters
        ----------
        tile_name : str
            Tile name.
        """
        assert self.output_file is not None
        self.output_file.write_text(f"module {tile_name}_switch_matrix; endmodule\n")
        self.output_file.with_suffix(".csv").write_text(f"{tile_name}\n")

    def genConfigMem(self, tile_name: str, config_mem: Path) -> None:
        """Write fake config-memory artifacts.

        Parameters
        ----------
        tile_name : str
            Tile name.
        config_mem : Path
            Config-memory CSV path.
        """
        assert self.output_file is not None
        self.config_mem_existed_at_gen = config_mem.exists()
        config_mem.write_text("Frame,ConfigBits_ranges\n")
        self.output_file.write_text(f"module {tile_name}_ConfigMem; endmodule\n")

    def genTile(self, tile_name: str) -> None:
        """Write fake tile RTL.

        Parameters
        ----------
        tile_name : str
            Tile name.
        """
        assert self.output_file is not None
        self.output_file.write_text(f"module {tile_name}; endmodule\n")


class _TileBuilderTestSynthesizer(ArchitectureSynthesizer):
    """Concrete architecture synthesizer for tile-builder wrapper tests."""

    def run_flow(self) -> None:
        """No-op flow entry point for tests."""


def test_models_validate_inputs() -> None:
    """Test public option models validate obvious invalid inputs."""
    _assert_raises_contains(
        lambda: TileBel(verilog_path=Path("x.v"), prefixes=[]), "prefixes"
    )
    _assert_raises_contains(
        lambda: BaselineRouting(input_fanin=1, min_input_fanin=2),
        "min_input_fanin",
    )
    _assert_raises_contains(
        lambda: TileBuilderOptions(
            tile_name="", bels=[TileBel(verilog_path=Path("x.v"))]
        ),
        "tile_name",
    )


def test_baseline_list_handles_carry_and_shared_ports() -> None:
    """Test carry and local shared ports are not treated as ordinary routing."""
    with TemporaryDirectory(prefix="tile_builder_carry_") as td:
        tmp_dir = Path(td)
        bels = [
            _make_fake_bel(Path("a.v"), "LA_"),
            _make_fake_bel(Path("a.v"), "LB_"),
        ]
        routing = BaselineRouting(
            base_csv_includes=[],
            base_list_includes=[],
            input_fanin=4,
            output_fanin=3,
        )
        base_model = build_base_routing_model(
            tile_dir=tmp_dir,
            routing=routing,
            require_gnd=True,
            require_vcc=True,
        )
        result = baseline_list_generator.generate_baseline_list(
            tile_name="test_tile",
            bels=bels,
            routing=routing,
            base_model=base_model,
            matrix_config_budget=None,
        )

    assert "{4}LA_I0" in result.text
    assert "LA_Ci,Ci00" in result.text
    assert "LB_Ci,LA_Co" in result.text
    assert "Co00,LB_Co" in result.text
    assert "{2}LA_SR,[J_SRST_END0|GND0]" in result.text
    assert "{2}LA_EN,[J_SEN_END0|VCC0]" in result.text
    assert "{4}LA_Ci" not in result.text
    assert "{4}LA_SR" not in result.text
    assert result.input_muxes == 2
    assert result.output_muxes == 0


def test_baseline_list_discovers_multiple_base_fragments() -> None:
    """Test base ports and existing connections are discovered from fragments."""
    with TemporaryDirectory(prefix="tile_builder_base_") as td:
        tmp_dir = Path(td)
        base_a_csv = tmp_dir / "BaseA.csv"
        base_b_csv = tmp_dir / "BaseB.csv"
        base_a_list = tmp_dir / "BaseA.list"
        base_b_list = tmp_dir / "BaseB.list"
        base_a_csv.write_text(
            "\n".join(
                [
                    "NORTH,FOO_OUT,0,-1,FOO_IN,2",
                    "JUMP,LOCAL_A_BEG,0,0,LOCAL_A_END,2",
                ]
            )
            + "\n",
            encoding="utf-8",
        )
        base_b_csv.write_text(
            "EAST,BAR_OUT,1,0,BAR_IN,1\nJUMP,LOCAL_B_BEG,0,0,LOCAL_B_END,1\n",
            encoding="utf-8",
        )
        base_a_list.write_text("FOO_OUT0,LOCAL_A_END0\n", encoding="utf-8")
        base_b_list.write_text("BAR_OUT0,BAR_IN0\n", encoding="utf-8")
        routing = BaselineRouting(
            base_csv_includes=["BaseA.csv", "BaseB.csv"],
            base_list_includes=["BaseA.list", "BaseB.list"],
            input_fanin=2,
            output_fanin=2,
        )
        base_model = build_base_routing_model(
            tile_dir=tmp_dir,
            routing=routing,
            require_gnd=False,
            require_vcc=False,
        )
        result = baseline_list_generator.generate_baseline_list(
            tile_name="base_tile",
            bels=[_make_fake_bel(Path("a.v"), "LA_")],
            routing=routing,
            base_model=base_model,
            matrix_config_budget=None,
        )

    assert "INCLUDE, BaseA.list" in result.text
    assert "INCLUDE, BaseB.list" in result.text
    assert "FOO_OUT0" not in _generated_body(result.text)
    assert "FOO_OUT1" in result.text
    assert "LA_O" in result.text
    assert "BAR_OUT0" not in _generated_body(result.text)
    assert "LOCAL_A_BEG" in result.text


def test_base_model_uses_fabulous_null_endpoint_expansion() -> None:
    """Test base discovery follows FABulous AutoSwitchMatrix expansion rules."""
    with TemporaryDirectory(prefix="tile_builder_null_base_") as td:
        tmp_dir = Path(td)
        base_csv = tmp_dir / "BaseNull.csv"
        base_csv.write_text(
            "\n".join(
                [
                    "NORTH,NULL,0,-2,TERM_IN,3",
                    "WEST,TERM_OUT,-2,0,NULL,2",
                ]
            )
            + "\n",
            encoding="utf-8",
        )
        routing = BaselineRouting(
            base_csv_includes=["BaseNull.csv"],
            base_list_includes=[],
        )
        base_model = build_base_routing_model(
            tile_dir=tmp_dir,
            routing=routing,
            require_gnd=False,
            require_vcc=False,
        )

    assert base_model.input_ports == [
        "TERM_IN0",
        "TERM_IN1",
        "TERM_IN2",
        "TERM_IN3",
        "TERM_IN4",
        "TERM_IN5",
    ]
    assert base_model.output_ports == [
        "TERM_OUT0",
        "TERM_OUT1",
        "TERM_OUT2",
        "TERM_OUT3",
    ]


def test_baseline_list_reduces_fanin_for_budget() -> None:
    """Test fanin is reduced when a matrix budget is provided."""
    with TemporaryDirectory(prefix="tile_builder_budget_") as td:
        tmp_dir = Path(td)
        bels = [_make_fake_bel(Path("a.v"), f"L{i}_") for i in range(4)]
        routing = BaselineRouting(
            base_csv_includes=[],
            base_list_includes=[],
            input_fanin=4,
            output_fanin=4,
            min_input_fanin=1,
            min_output_fanin=1,
        )
        base_model = build_base_routing_model(
            tile_dir=tmp_dir,
            routing=routing,
            require_gnd=True,
            require_vcc=True,
        )
        result = baseline_list_generator.generate_baseline_list(
            tile_name="budget_tile",
            bels=bels,
            routing=routing,
            base_model=base_model,
            matrix_config_budget=4,
        )

    assert result.input_fanin_used < 4 or result.output_fanin_used < 4
    assert result.warnings


def test_real_verilog_bel_edge_shapes_parse_and_route() -> None:
    """Test real FABulous parsing for input-only and output-only BEL shapes."""
    if not _has_yosys():
        return
    with TemporaryDirectory(prefix="tile_builder_real_edges_") as td:
        tmp_dir = Path(td)
        input_only = _write_verilog_source(
            tmp_dir,
            "input_only.v",
            """
            module input_only(input [1:0] I);
                wire keep = ^I;
            endmodule
            """,
        )
        output_only = _write_verilog_source(
            tmp_dir,
            "output_only.v",
            """
            module output_only(output O);
                assign O = 1'b0;
            endmodule
            """,
        )
        base_csv = tmp_dir / "Base.csv"
        base_csv.write_text(
            "NORTH,ROUTE_OUT,0,-1,ROUTE_IN,2\n",
            encoding="utf-8",
        )
        routing = BaselineRouting(
            base_csv_includes=["Base.csv"],
            base_list_includes=[],
            input_fanin=2,
            output_fanin=2,
        )
        base_model = build_base_routing_model(
            tile_dir=tmp_dir,
            routing=routing,
            require_gnd=False,
            require_vcc=False,
        )
        bels = [
            builder_mod.parseBelFile(input_only, "IA_"),
            builder_mod.parseBelFile(output_only, "OA_"),
        ]
        result = baseline_list_generator.generate_baseline_list(
            tile_name="real_edge_tile",
            bels=bels,
            routing=routing,
            base_model=base_model,
            matrix_config_budget=None,
        )

    assert "{2}IA_I0" in result.text
    assert "{2}IA_I1" in result.text
    assert "{2}ROUTE_OUT0,[OA_O|ROUTE_IN0]" in result.text
    assert "{2}ROUTE_OUT1,[OA_O|ROUTE_IN1]" in result.text
    assert "OA_O" in result.text


def test_real_verilog_carry_and_shared_ports_parse_and_route() -> None:
    """Test real FABulous parsing keeps carry and shared ports special."""
    if not _has_yosys():
        return
    with TemporaryDirectory(prefix="tile_builder_real_special_") as td:
        tmp_dir = Path(td)
        source = _write_verilog_source(
            tmp_dir,
            "carry_shared.v",
            """
            module carry_shared(
                (* FABulous, CARRY="C0" *) input Ci,
                (* FABulous, CARRY="C0" *) output Co,
                (* FABulous, SHARED_RESET *) input SR,
                (* FABulous, SHARED_ENABLE *) input EN,
                input I,
                output O
            );
                assign Co = Ci;
                assign O = I & EN & ~SR;
            endmodule
            """,
        )
        bels = [
            builder_mod.parseBelFile(source, "LA_"),
            builder_mod.parseBelFile(source, "LB_"),
        ]
        routing = BaselineRouting(
            base_csv_includes=[],
            base_list_includes=[],
            input_fanin=2,
            output_fanin=2,
        )
        base_model = build_base_routing_model(
            tile_dir=tmp_dir,
            routing=routing,
            require_gnd=True,
            require_vcc=True,
        )
        result = baseline_list_generator.generate_baseline_list(
            tile_name="real_special_tile",
            bels=bels,
            routing=routing,
            base_model=base_model,
            matrix_config_budget=None,
        )

    assert "LA_Ci,Ci00" in result.text
    assert "LB_Ci,LA_Co" in result.text
    assert "Co00,LB_Co" in result.text
    assert "{2}LA_I" in result.text
    assert "{2}LA_SR,[J_SRST_END0|GND0]" in result.text
    assert "{2}LA_EN,[J_SEN_END0|VCC0]" in result.text
    assert "{2}LA_SR,[VCC0|LA_O]" not in result.text
    assert "{2}LA_EN,[VCC0|LA_O]" not in result.text


def test_builder_accepts_real_vector_verilog_bel() -> None:
    """Test the builder can use a real vector BEL parsed by FABulous."""
    if not _has_yosys():
        return
    with TemporaryDirectory(prefix="tile_builder_real_builder_") as td:
        tmp_dir = Path(td)
        fabric_csv = _write_project(tmp_dir)
        source = _write_verilog_source(
            tmp_dir,
            "vector_passthrough.v",
            """
            module vector_passthrough(input [1:0] I, output [1:0] O);
                assign O = I;
            endmodule
            """,
        )
        fab = _FakeFab(
            fabric_csv=fabric_csv,
            tile=_FakeTile(name="real_tile", matrixConfigBits=8, globalConfigBits=8),
        )

        result = builder_mod.TileBuilder(
            TileBuilderOptions(
                tile_name="real_tile",
                bels=[TileBel(verilog_path=source, prefixes=["L_"])],
                routing=BaselineRouting(
                    base_csv_includes=[],
                    base_list_includes=[],
                    input_fanin=2,
                    output_fanin=2,
                ),
                track_progress=False,
            )
        ).build(PyosysBridge(debug=False), fab)

        assert result.parsed_bel_modules == ("vector_passthrough",)
        assert result.matrix_list is not None
        assert "{2}L_I0,[L_O0|L_O1]" in result.matrix_list.read_text(encoding="utf-8")
        assert "module vector_passthrough" in (
            tmp_dir / "user_design" / "custom_prims.v"
        ).read_text(encoding="utf-8")


def test_builder_generates_files_and_registers_tile() -> None:
    """Test builder writes core artifacts and registers the tile in fabric.csv."""
    with TemporaryDirectory(prefix="tile_builder_") as td:
        tmp_dir = Path(td)
        fabric_csv = _write_project(tmp_dir)
        source = _write_bel_source(tmp_dir)
        fab = _FakeFab(
            fabric_csv=fabric_csv,
            tile=_FakeTile(name="test_tile", matrixConfigBits=10, globalConfigBits=14),
        )

        with _patched_builder_functions():
            result = builder_mod.TileBuilder(
                TileBuilderOptions(
                    tile_name="test_tile",
                    bels=[TileBel(verilog_path=source, prefixes=["LA_", "LB_"])],
                    routing=BaselineRouting(input_fanin=2, output_fanin=2),
                    track_progress=False,
                )
            ).build(PyosysBridge(debug=False), fab)

        assert fab.loaded
        assert result.stats.bel_instances == 2
        assert result.stats.total_config_bits == 14
        assert result.tile_csv.is_file()
        assert result.matrix_list is not None
        assert result.matrix_list.is_file()
        assert (tmp_dir / "user_design" / "custom_prims.v").is_file()
        assert "Tile,./Tile/test_tile/test_tile.csv" in fabric_csv.read_text()
        assert "Tile Builder Report" in result.report_summary
        assert (tmp_dir / "Tile" / "test_tile" / "test_tile.v").is_file()


def test_builder_can_use_fabulous_auto_matrix() -> None:
    """Test auto mode emits MATRIX,GENERATE instead of a baseline list."""
    with TemporaryDirectory(prefix="tile_builder_auto_") as td:
        tmp_dir = Path(td)
        fabric_csv = _write_project(tmp_dir)
        source = _write_bel_source(tmp_dir)
        fab = _FakeFab(
            fabric_csv=fabric_csv,
            tile=_FakeTile(name="auto_tile", matrixConfigBits=6, globalConfigBits=8),
        )

        with _patched_builder_functions():
            result = builder_mod.TileBuilder(
                TileBuilderOptions(
                    tile_name="auto_tile",
                    bels=[TileBel(verilog_path=source, prefixes=["L_"])],
                    routing=BaselineRouting(use_fabulous_auto=True),
                    track_progress=False,
                )
            ).build(PyosysBridge(debug=False), fab)

        assert result.matrix_list is None
        assert "MATRIX,GENERATE" in result.tile_csv.read_text()


def test_builder_regenerates_stale_config_memory_csv() -> None:
    """Test stale config-memory CSV files are removed before regeneration."""
    with TemporaryDirectory(prefix="tile_builder_stale_config_") as td:
        tmp_dir = Path(td)
        fabric_csv = _write_project(tmp_dir)
        source = _write_bel_source(tmp_dir)
        tile_dir = tmp_dir / "Tile" / "stale_tile"
        tile_dir.mkdir(parents=True)
        stale_config_mem = tile_dir / "stale_tile_ConfigMem.csv"
        stale_config_mem.write_text("stale,bitmask\n", encoding="utf-8")
        fab = _FakeFab(
            fabric_csv=fabric_csv,
            tile=_FakeTile(name="stale_tile", matrixConfigBits=6, globalConfigBits=8),
        )

        with _patched_builder_functions():
            builder_mod.TileBuilder(
                TileBuilderOptions(
                    tile_name="stale_tile",
                    tile_dir=tile_dir,
                    bels=[TileBel(verilog_path=source, prefixes=["L_"])],
                    routing=BaselineRouting(use_fabulous_auto=True),
                    track_progress=False,
                )
            ).build(PyosysBridge(debug=False), fab)

        assert fab.config_mem_existed_at_gen is False
        assert stale_config_mem.read_text(encoding="utf-8") == (
            "Frame,ConfigBits_ranges\n"
        )


def test_builder_fails_when_config_capacity_is_exceeded() -> None:
    """Test over-capacity generated tiles fail clearly."""
    with TemporaryDirectory(prefix="tile_builder_capacity_") as td:
        tmp_dir = Path(td)
        fabric_csv = _write_project(tmp_dir)
        source = _write_bel_source(tmp_dir)
        fab = _FakeFab(
            fabric_csv=fabric_csv,
            tile=_FakeTile(name="big_tile", matrixConfigBits=60, globalConfigBits=70),
        )

        with _patched_builder_functions():
            _assert_raises_contains(
                lambda: builder_mod.TileBuilder(
                    TileBuilderOptions(
                        tile_name="big_tile",
                        bels=[TileBel(verilog_path=source, prefixes=["L_"])],
                        routing=BaselineRouting(config_bit_margin=0),
                        track_progress=False,
                    )
                ).build(PyosysBridge(debug=False), fab),
                "config bits",
            )


def test_pnr_pass_wrapper_runs_builder() -> None:
    """Test the PnR pass wrapper runs and exposes result data."""
    with TemporaryDirectory(prefix="tile_builder_pass_") as td:
        tmp_dir = Path(td)
        fabric_csv = _write_project(tmp_dir)
        source = _write_bel_source(tmp_dir)
        fab = _FakeFab(
            fabric_csv=fabric_csv,
            tile=_FakeTile(name="pass_tile", matrixConfigBits=8, globalConfigBits=10),
        )
        pass_ = TileBuilderPass(
            tile_name="pass_tile",
            bels=[{"verilog_path": source, "prefixes": ["L_"]}],
            routing={"input_fanin": 2, "output_fanin": 2},
            track_progress=False,
        )

        with _patched_builder_functions():
            pass_.run_on(PyosysBridge(debug=False), fab)

        assert pass_.result_data is not None
        assert "Tile Builder Report" in pass_.report_summary


def test_synthesizer_wrapper_runs_builder() -> None:
    """Test the ArchitectureSynthesizer PnR helper."""
    with TemporaryDirectory(prefix="tile_builder_synth_") as td:
        tmp_dir = Path(td)
        fabric_csv = _write_project(tmp_dir)
        source = _write_bel_source(tmp_dir)
        fab = _FakeFab(
            fabric_csv=fabric_csv,
            tile=_FakeTile(name="synth_tile", matrixConfigBits=8, globalConfigBits=10),
        )
        synth = _TileBuilderTestSynthesizer(debug=False)
        synth.attach_fabulous_api(fab)  # type: ignore[arg-type]

        with _patched_builder_functions():
            result = synth.pnr_tile_builder_pass(
                tile_name="synth_tile",
                bels=[TileBel(verilog_path=source, prefixes=["L_"])],
                routing=BaselineRouting(input_fanin=2, output_fanin=2),
                track_progress=False,
                log_report=False,
            )

        assert result.result_data is not None
        assert "Tile Builder Report" in result.report_summary


def _make_fake_bel(path: Path, prefix: str) -> _FakeBel:
    """Build a fake BEL with ordinary, carry, reset, and enable ports.

    Parameters
    ----------
    path : Path
        Fake RTL path.
    prefix : str
        Instance prefix.

    Returns
    -------
    _FakeBel
        Fake BEL instance.
    """
    return _FakeBel(
        src=path,
        prefix=prefix,
        inputs=[f"{prefix}I0", f"{prefix}Ci", f"{prefix}SR", f"{prefix}EN"],
        outputs=[f"{prefix}O", f"{prefix}Co"],
        carry={"C0": {IO.INPUT: f"{prefix}Ci", IO.OUTPUT: f"{prefix}Co"}},
        localShared={
            "RESET": (f"{prefix}SR", IO.INPUT),
            "ENABLE": (f"{prefix}EN", IO.INPUT),
        },
    )


def _write_project(tmp_dir: Path) -> Path:
    """Write a minimal project directory.

    Parameters
    ----------
    tmp_dir : Path
        Temporary project directory.

    Returns
    -------
    Path
        Fabric CSV path.
    """
    (tmp_dir / "Tile" / "include").mkdir(parents=True)
    (tmp_dir / "user_design").mkdir()
    (tmp_dir / "Tile" / "include" / "Base.list").write_text("BASE_OUT,BASE_IN\n")
    (tmp_dir / "Tile" / "include" / "Base.csv").write_text("")
    fabric_csv = tmp_dir / "fabric.csv"
    fabric_csv.write_text(
        "\n".join(
            [
                "FabricBegin",
                "NULL",
                "FabricEnd",
                "",
                "ParametersBegin",
                "ConfigBitMode,frame_based",
                "ParametersEnd",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    return fabric_csv


def _write_bel_source(tmp_dir: Path) -> Path:
    """Write a tiny fake BEL RTL source.

    Parameters
    ----------
    tmp_dir : Path
        Temporary directory.

    Returns
    -------
    Path
        BEL RTL path.
    """
    path = tmp_dir / "toy_bel.v"
    path.write_text("module toy_bel(input I0, output O); endmodule\n")
    return path


def _write_verilog_source(tmp_dir: Path, name: str, body: str) -> Path:
    """Write a temporary Verilog source file.

    Parameters
    ----------
    tmp_dir : Path
        Temporary directory.
    name : str
        File name.
    body : str
        Verilog body.

    Returns
    -------
    Path
        Verilog path.
    """
    path = tmp_dir / name
    path.write_text(body.strip() + "\n", encoding="utf-8")
    return path


def _has_yosys() -> bool:
    """Return whether Yosys is available for real FABulous BEL parsing tests.

    Returns
    -------
    bool
        Whether ``yosys`` is on ``PATH``.
    """
    return shutil.which("yosys") is not None


class _patched_builder_functions:
    """Patch FABulous-heavy builder functions for unit tests."""

    def __enter__(self) -> None:
        """Install test doubles for FABulous-heavy functions."""
        self._old_parse = builder_mod.parseBelFile
        self._old_add = builder_mod.addBelsToPrim
        builder_mod.parseBelFile = _fake_parse_bel_file  # type: ignore[assignment]
        builder_mod.addBelsToPrim = _fake_add_bels_to_prim  # type: ignore[assignment]

    def __exit__(self, *args: object) -> None:
        """Restore patched builder functions.

        Parameters
        ----------
        *args : object
            Exception information supplied by the context-manager protocol.
        """
        builder_mod.parseBelFile = self._old_parse  # type: ignore[assignment]
        builder_mod.addBelsToPrim = self._old_add  # type: ignore[assignment]


def _fake_parse_bel_file(path: Path, prefix: str) -> _FakeBel:
    """Return a fake parsed BEL.

    Parameters
    ----------
    path : Path
        BEL RTL path.
    prefix : str
        BEL instance prefix.

    Returns
    -------
    _FakeBel
        Fake BEL.
    """
    return _make_fake_bel(path, prefix)


def _fake_add_bels_to_prim(prims_file: Path, bels: list[_FakeBel]) -> None:
    """Write fake custom primitive declarations.

    Parameters
    ----------
    prims_file : Path
        Custom primitives file.
    bels : list[_FakeBel]
        Fake BELs to write.
    """
    modules = sorted({bel.module_name for bel in bels})
    prims_file.write_text(
        "\n".join(f"module {module}; endmodule" for module in modules)
    )


def _generated_body(text: str) -> str:
    """Return generated non-include list-file lines.

    Parameters
    ----------
    text : str
        List file text.

    Returns
    -------
    str
        Body text without comments and include lines.
    """
    return "\n".join(
        line
        for line in text.splitlines()
        if line and not line.startswith("#") and not line.startswith("INCLUDE")
    )


def _assert_raises_contains(fn: Callable[[], object], expected: str) -> None:
    """Assert that a callable raises an exception containing text.

    Parameters
    ----------
    fn : Callable[[], object]
        Callable expected to fail.
    expected : str
        Expected substring.

    Raises
    ------
    AssertionError
        If the callable does not fail or the exception text does not match.
    """
    try:
        fn()
    except Exception as exc:
        if expected not in str(exc):
            raise AssertionError(f"expected {expected!r} in {exc!s}") from exc
        return
    raise AssertionError("expected callable to raise")


def main() -> None:
    """Run all tile-builder tests."""
    test_models_validate_inputs()
    test_baseline_list_handles_carry_and_shared_ports()
    test_baseline_list_discovers_multiple_base_fragments()
    test_base_model_uses_fabulous_null_endpoint_expansion()
    test_baseline_list_reduces_fanin_for_budget()
    test_real_verilog_bel_edge_shapes_parse_and_route()
    test_real_verilog_carry_and_shared_ports_parse_and_route()
    test_builder_accepts_real_vector_verilog_bel()
    test_builder_generates_files_and_registers_tile()
    test_builder_can_use_fabulous_auto_matrix()
    test_builder_regenerates_stale_config_memory_csv()
    test_builder_fails_when_config_capacity_is_exceeded()
    test_pnr_pass_wrapper_runs_builder()
    test_synthesizer_wrapper_runs_builder()


if __name__ == "__main__":
    main()

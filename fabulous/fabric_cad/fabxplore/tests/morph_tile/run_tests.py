"""Ad-hoc tests for morph-tile mapping."""

from pathlib import Path
from tempfile import TemporaryDirectory

import pyosys.libyosys as ys

from fabulous.fabric_cad.fabxplore.modules.morph_tile import CutSolver
from fabulous.fabric_cad.fabxplore.modules.morph_tile.core.reader import (
    MorphTileReader,
)
from fabulous.fabric_cad.fabxplore.pyosys.custom_passes.morph_tile_pass import (
    MorphTilePass,
)
from fabulous.fabric_cad.fabxplore.pyosys.pyosys_bridge import PyosysBridge
from fabulous.fabric_cad.fabxplore.pyosys.synthesizer import ArchitectureSynthesizer
from fabulous.fabulous_cli.helper import setup_logger

setup_logger(verbosity=0, debug=False)


class _MorphTileTestSynthesizer(ArchitectureSynthesizer):
    """Tiny concrete synthesizer for morph-tile pass tests."""

    def synthesize(self) -> None:
        """No-op synthesis entry point for tests."""

    def generate_primitives(self) -> None:
        """No-op primitive generation for tests."""

    def generate_switch_matrix(self) -> None:
        """No-op switch-matrix generation for tests."""


def test_cut_solver_simple_and() -> None:
    """Test CutSolver accepts a direct two-input AND implementation."""
    with TemporaryDirectory(prefix="morph_cut_solver_") as td:
        tmp_dir = Path(td)
        tile = tmp_dir / "and_tile.v"
        tile.write_text(
            """
module and_tile(input I0, input I1, output O);
  assign O = I0 & I1;
endmodule
""",
            encoding="utf-8",
        )

        result = CutSolver(
            verilog_path=tile,
            top_name="and_tile",
            inputs=["I0", "I1"],
            outputs=["O"],
        ).solve_lut(init=0x8, lut_size=2, allow_input_reuse=False)

        assert result.sat
        assert set(result.input_mapping) == {"I0", "I1"}
        assert set(result.input_mapping.values()) == {"A0", "A1"}
        assert result.output_mapping == {"X": "O"}


def test_morph_tile_pass_replaces_and_lut_eq() -> None:
    """Test a compatible LUT is replaced and remains equivalent."""
    with TemporaryDirectory(prefix="morph_tile_replace_") as td:
        tmp_dir = Path(td)
        base = _write_and_base(tmp_dir)
        tile = _write_and_tile(tmp_dir)

        bridge = PyosysBridge(debug=False)
        bridge.read_verilog_paths([base])
        pass_ = MorphTilePass(
            tile_verilog_path=tile,
            tile_top_name="and_tile",
            tile_inputs=["I0", "I1"],
            tile_outputs=["O"],
            considered_lut_widths=[2],
            top_name="base",
            track_progress=False,
        )
        pass_.run_on(bridge)

        assert pass_.result_data is not None
        assert pass_.result_data.stats.candidate_luts == 1
        assert pass_.result_data.stats.replaced_luts == 1
        assert pass_.result_data.stats.failed_luts == 0
        assert "Replaced LUTs: 1" in pass_.report_summary
        assert "of all LUTs: 100.0%" in pass_.report_summary
        assert "of checked candidates: 100.0%" in pass_.report_summary

        netlist = bridge.to_netlist_dict()
        cells = netlist["modules"]["base"]["cells"]
        assert "u_lut" not in cells
        assert cells["u_lut__morph_tile"]["type"] == "and_tile"

        gate = tmp_dir / "gate.v"
        bridge.write_verilog_path(gate)
        _assert_equiv(base, gate, tile, "base")


def test_morph_tile_reader_extracts_internal_lut_view() -> None:
    """Test the reader builds the compact internal LUT representation."""
    with TemporaryDirectory(prefix="morph_tile_reader_") as td:
        tmp_dir = Path(td)
        base = _write_and_base(tmp_dir)

        bridge = PyosysBridge(debug=False)
        bridge.read_verilog_paths([base])
        morph_design = MorphTileReader().read_design(bridge, "base")

        assert morph_design.top_name == "base"
        assert len(morph_design.lut_cells) == 1
        assert morph_design.lut_cells[0].cell_id == "u_lut"
        assert morph_design.lut_cells[0].width == 2
        assert morph_design.lut_cells[0].init == 0x8


def test_morph_tile_reader_rejects_malformed_lut_output() -> None:
    """Test malformed LUT output vectors are rejected before planning."""
    with TemporaryDirectory(prefix="morph_tile_bad_lut_") as td:
        tmp_dir = Path(td)
        base = tmp_dir / "base.v"
        base.write_text(
            """
module base(input a, input b, output y0, output y1);
  \\$lut #(.LUT(4'h8), .WIDTH(32'd2)) u_lut (.A({b, a}), .Y({y1, y0}));
endmodule
""",
            encoding="utf-8",
        )

        bridge = PyosysBridge(debug=False)
        bridge.read_verilog_paths([base])
        error_text = ""
        try:
            MorphTileReader().read_design(bridge, "base")
        except RuntimeError as exc:
            error_text = str(exc)

        assert "must have exactly one Y bit" in error_text


def test_morph_tile_pass_leaves_unsupported_lut() -> None:
    """Test an incompatible LUT is reported as failed and left unchanged."""
    with TemporaryDirectory(prefix="morph_tile_fail_") as td:
        tmp_dir = Path(td)
        base = tmp_dir / "base.v"
        base.write_text(
            """
module base(input a, input b, output y);
  \\$lut #(.LUT(4'h6), .WIDTH(32'd2)) u_lut (.A({b, a}), .Y(y));
endmodule
""",
            encoding="utf-8",
        )
        tile = _write_and_tile(tmp_dir)

        bridge = PyosysBridge(debug=False)
        bridge.read_verilog_paths([base])
        pass_ = MorphTilePass(
            tile_verilog_path=tile,
            tile_top_name="and_tile",
            tile_inputs=["I0", "I1"],
            tile_outputs=["O"],
            considered_lut_widths=[2],
            top_name="base",
            track_progress=False,
        )
        pass_.run_on(bridge)

        assert pass_.result_data is not None
        assert pass_.result_data.stats.replaced_luts == 0
        assert pass_.result_data.stats.failed_luts == 1
        cells = bridge.to_netlist_dict()["modules"]["base"]["cells"]
        assert cells["u_lut"]["type"].lstrip("\\") == "$lut"


def test_morph_tile_pass_uses_solver_cache() -> None:
    """Test identical LUT functions are solved once and then served from cache."""
    with TemporaryDirectory(prefix="morph_tile_cache_") as td:
        tmp_dir = Path(td)
        base = tmp_dir / "base.v"
        base.write_text(
            """
module base(input a, input b, input c, input d, output y0, output y1);
  \\$lut #(.LUT(4'h8), .WIDTH(32'd2)) lut0 (.A({b, a}), .Y(y0));
  \\$lut #(.LUT(4'h8), .WIDTH(32'd2)) lut1 (.A({d, c}), .Y(y1));
endmodule
""",
            encoding="utf-8",
        )
        tile = _write_and_tile(tmp_dir)

        bridge = PyosysBridge(debug=False)
        bridge.read_verilog_paths([base])
        pass_ = MorphTilePass(
            tile_verilog_path=tile,
            tile_top_name="and_tile",
            tile_inputs=["I0", "I1"],
            tile_outputs=["O"],
            considered_lut_widths=[2],
            top_name="base",
            track_progress=False,
        )
        pass_.run_on(bridge)

        assert pass_.result_data is not None
        assert pass_.result_data.stats.replaced_luts == 2
        assert pass_.result_data.stats.cache_misses == 1
        assert pass_.result_data.stats.cache_hits == 1


def test_morph_tile_pass_respects_max_replacements() -> None:
    """Test max_replacements limits successful replacements."""
    with TemporaryDirectory(prefix="morph_tile_limit_") as td:
        tmp_dir = Path(td)
        base = tmp_dir / "base.v"
        base.write_text(
            """
module base(input a, input b, input c, input d, output y0, output y1);
  \\$lut #(.LUT(4'h8), .WIDTH(32'd2)) lut0 (.A({b, a}), .Y(y0));
  \\$lut #(.LUT(4'h8), .WIDTH(32'd2)) lut1 (.A({d, c}), .Y(y1));
endmodule
""",
            encoding="utf-8",
        )
        tile = _write_and_tile(tmp_dir)

        bridge = PyosysBridge(debug=False)
        bridge.read_verilog_paths([base])
        pass_ = MorphTilePass(
            tile_verilog_path=tile,
            tile_top_name="and_tile",
            tile_inputs=["I0", "I1"],
            tile_outputs=["O"],
            considered_lut_widths=[2],
            max_replacements=1,
            top_name="base",
            track_progress=False,
        )
        pass_.run_on(bridge)

        assert pass_.result_data is not None
        assert pass_.result_data.stats.replaced_luts == 1
        assert pass_.result_data.stats.skipped_luts == 1
        assert pass_.result_data.stats.skipped_limit_luts == 1
        assert pass_.result_data.stats.skipped_width_luts == 0


def test_morph_tile_pass_wires_scalar_config() -> None:
    """Test solved scalar config bits are wired into replacement cells."""
    with TemporaryDirectory(prefix="morph_tile_config_") as td:
        tmp_dir = Path(td)
        base = _write_and_base(tmp_dir)
        tile = tmp_dir / "cfg_tile.v"
        tile.write_text(
            """
module cfg_tile(input I0, input I1, input C, output O);
  assign O = C ? (I0 ^ I1) : (I0 & I1);
endmodule
""",
            encoding="utf-8",
        )

        bridge = PyosysBridge(debug=False)
        bridge.read_verilog_paths([base])
        pass_ = MorphTilePass(
            tile_verilog_path=tile,
            tile_top_name="cfg_tile",
            tile_inputs=["I0", "I1"],
            tile_outputs=["O"],
            considered_lut_widths=[2],
            tile_configs=["C"],
            top_name="base",
            track_progress=False,
        )
        pass_.run_on(bridge)

        assert pass_.result_data is not None
        assert pass_.result_data.stats.replaced_luts == 1
        cell = bridge.to_netlist_dict()["modules"]["base"]["cells"]["u_lut__morph_tile"]
        assert cell["connections"]["C"] == ["0"]


def test_synthesizer_morph_tile_pass_smoke() -> None:
    """Test the synthesizer convenience wrapper runs the morph-tile pass."""
    with TemporaryDirectory(prefix="morph_tile_synth_") as td:
        tmp_dir = Path(td)
        base = _write_and_base(tmp_dir)
        tile = _write_and_tile(tmp_dir)

        synth = _MorphTileTestSynthesizer(debug=False)
        synth.design.read_verilog_paths([base])
        pass_ = synth.design_morph_tile_pass(
            tile_verilog_path=tile,
            tile_top_name="and_tile",
            tile_inputs=["I0", "I1"],
            tile_outputs=["O"],
            considered_lut_widths=[2],
            top_name="base",
            track_progress=False,
            log_report=False,
        )

        assert pass_.result_data is not None
        assert pass_.result_data.stats.replaced_luts == 1
        assert "Morph Tile Mapping Report" in pass_.report_summary


def _write_and_base(tmp_dir: Path) -> Path:
    """Write a one-LUT AND base design."""
    base = tmp_dir / "base.v"
    base.write_text(
        """
module base(input a, input b, output y);
  \\$lut #(.LUT(4'h8), .WIDTH(32'd2)) u_lut (.A({b, a}), .Y(y));
endmodule
""",
        encoding="utf-8",
    )
    return base


def _write_and_tile(tmp_dir: Path) -> Path:
    """Write a direct two-input AND tile."""
    tile = tmp_dir / "and_tile.v"
    tile.write_text(
        """
module and_tile(input I0, input I1, output O);
  assign O = I0 & I1;
endmodule
""",
        encoding="utf-8",
    )
    return tile


def _assert_equiv(gold: Path, gate: Path, tile: Path, top_name: str) -> None:
    """Run a Yosys equivalence check between gold and mapped designs."""
    design = ys.Design()

    def run(command: str) -> None:
        ys.run_pass(f"tee -q {command}", design)

    run(f"read_verilog {gold}")
    run(f"rename {top_name} {top_name}_gold")
    run(f"read_verilog {tile}")
    run(f"read_verilog {gate}")
    run(f"rename {top_name} {top_name}_gate")
    run(f"equiv_make {top_name}_gold {top_name}_gate equiv")
    run("hierarchy -top equiv")
    run("flatten")
    run("opt_clean")
    run("equiv_simple -undef")
    run("equiv_status -assert")


def main() -> None:
    """Run all tests."""
    test_cut_solver_simple_and()
    test_morph_tile_pass_replaces_and_lut_eq()
    test_morph_tile_reader_extracts_internal_lut_view()
    test_morph_tile_reader_rejects_malformed_lut_output()
    test_morph_tile_pass_leaves_unsupported_lut()
    test_morph_tile_pass_uses_solver_cache()
    test_morph_tile_pass_respects_max_replacements()
    test_morph_tile_pass_wires_scalar_config()
    test_synthesizer_morph_tile_pass_smoke()


if __name__ == "__main__":
    main()

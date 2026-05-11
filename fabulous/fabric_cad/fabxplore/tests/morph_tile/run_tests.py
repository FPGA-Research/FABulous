"""Ad-hoc tests for morph-tile mapping."""

from pathlib import Path
from tempfile import TemporaryDirectory

import pyosys.libyosys as ys

from fabulous.fabric_cad.fabxplore.modules.lut_combinator.core.verilog_model import (
    FracLutBehavioralModel,
)
from fabulous.fabric_cad.fabxplore.modules.morph_tile import CutSolver
from fabulous.fabric_cad.fabxplore.modules.morph_tile.core.base import (
    MorphCircuitKind,
)
from fabulous.fabric_cad.fabxplore.modules.morph_tile.core.permute_cache import (
    canonicalize_truth_table,
    permute_truth_init,
)
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


def test_permute_cache_groups_multi_output_truth_tables() -> None:
    """Test permutation-equivalent truth tables share one cache key."""
    assert permute_truth_init(0x4, 2, (1, 0)) == 0x2

    left = canonicalize_truth_table(["A0", "A1"], {"O0": 0x2, "O1": 0x8})
    right = canonicalize_truth_table(["A0", "A1"], {"O0": 0x4, "O1": 0x8})

    assert left.cache_key == right.cache_key
    assert right.permutation == (1, 0)


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
            circuit_options={"lut": {"widths": [2]}},
            top_name="base",
            track_progress=False,
        )
        pass_.run_on(bridge)

        assert pass_.result_data is not None
        assert pass_.result_data.stats.candidate_luts == 1
        assert pass_.result_data.stats.replaced_luts == 1
        assert pass_.result_data.stats.failed_luts == 0
        replacement = pass_.result_data.replacements[0]
        assert set(replacement.input_ports) == {"I0", "I1"}
        assert set(replacement.output_ports) == {"O"}
        assert "Replaced candidates: 1" in pass_.report_summary
        assert "of all candidates: 100.0%" in pass_.report_summary
        assert "of checked candidates:" in pass_.report_summary
        assert "100.0%" in pass_.report_summary

        netlist = bridge.to_netlist_dict()
        cells = netlist["modules"]["base"]["cells"]
        assert "u_lut" not in cells
        assert cells["u_lut__morph_tile"]["type"] == "and_tile"

        gate = tmp_dir / "gate.v"
        bridge.write_verilog_path(gate)
        _assert_equiv(base, gate, tile, "base")


def test_morph_tile_pass_accepts_lut_options() -> None:
    """Test circuit_options controls the registered LUT adapter."""
    with TemporaryDirectory(prefix="morph_tile_lut_options_") as td:
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
            circuit_options={"lut": {"widths": [2]}},
            top_name="base",
            track_progress=False,
        )
        pass_.run_on(bridge)

        assert pass_.result_data is not None
        assert pass_.result_data.stats.replaced_luts == 1
        assert pass_.result_data.filter_summary["lut.widths"] == ["LUT2"]


def test_morph_tile_pass_accepts_enum_circuit_kind() -> None:
    """Test enabled_circuits accepts internal enum values."""
    with TemporaryDirectory(prefix="morph_tile_enum_kind_") as td:
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
            enabled_circuits=[MorphCircuitKind.LUT],
            circuit_options={"lut": {"widths": [2]}},
            top_name="base",
            track_progress=False,
        )
        pass_.run_on(bridge)

        assert pass_.result_data is not None
        assert pass_.result_data.stats.replaced_luts == 1


def test_morph_tile_pass_replaces_dual_frac_lut_eq() -> None:
    """Test a compatible dual-output FRAC LUT is replaced and equivalent."""
    with TemporaryDirectory(prefix="morph_tile_frac_dual_") as td:
        tmp_dir = Path(td)
        base = _write_frac_dual_base(tmp_dir)
        tile = _write_dual_frac_tile(tmp_dir)

        bridge = PyosysBridge(debug=False)
        bridge.read_verilog_paths([base])
        pass_ = MorphTilePass(
            tile_verilog_path=tile,
            tile_top_name="dual_frac_tile",
            tile_inputs=["I0", "A0", "B0"],
            tile_outputs=["T0", "T1"],
            enabled_circuits=["frac_lut"],
            top_name="base",
            track_progress=False,
        )
        pass_.run_on(bridge)

        assert pass_.result_data is not None
        assert pass_.result_data.stats.replaced_luts == 1
        assert pass_.result_data.stats.failed_luts == 0
        assert "FRAC_LUT2:dual" in pass_.report_summary
        cells = bridge.to_netlist_dict()["modules"]["base"]["cells"]
        assert "u_frac" not in cells
        assert cells["u_frac__morph_tile"]["type"] == "dual_frac_tile"

        gate = tmp_dir / "gate.v"
        bridge.run_pass("hierarchy -top base")
        bridge.write_verilog_path(gate)
        _assert_equiv(base, gate, tile, "base")


def test_morph_tile_pass_frac_lut_mode_filter_skips() -> None:
    """Test frac_lut modes can filter out otherwise valid FRAC candidates."""
    with TemporaryDirectory(prefix="morph_tile_frac_filter_") as td:
        tmp_dir = Path(td)
        base = _write_frac_dual_base(tmp_dir)
        tile = _write_dual_frac_tile(tmp_dir)

        bridge = PyosysBridge(debug=False)
        bridge.read_verilog_paths([base])
        pass_ = MorphTilePass(
            tile_verilog_path=tile,
            tile_top_name="dual_frac_tile",
            tile_inputs=["I0", "A0", "B0"],
            tile_outputs=["T0", "T1"],
            enabled_circuits=["frac_lut"],
            circuit_options={"frac_lut": {"modes": ["single"]}},
            top_name="base",
            track_progress=False,
        )
        pass_.run_on(bridge)

        assert pass_.result_data is not None
        assert pass_.result_data.stats.replaced_luts == 0
        assert pass_.result_data.stats.skipped_width_luts == 1
        assert "u_frac" in bridge.to_netlist_dict()["modules"]["base"]["cells"]


def test_morph_tile_pass_replaces_select_as_data_frac_lut_eq() -> None:
    """Test a select-as-data FRAC LUT is solved with its special pin mapping."""
    with TemporaryDirectory(prefix="morph_tile_frac_sad_") as td:
        tmp_dir = Path(td)
        base = _write_frac_select_as_data_base(tmp_dir)
        tile = _write_select_as_data_frac_tile(tmp_dir)

        bridge = PyosysBridge(debug=False)
        bridge.read_verilog_paths([base])
        pass_ = MorphTilePass(
            tile_verilog_path=tile,
            tile_top_name="select_as_data_frac_tile",
            tile_inputs=["I0", "A0", "B0", "S"],
            tile_outputs=["T0", "T1"],
            enabled_circuits=["frac_lut"],
            top_name="base",
            track_progress=False,
        )
        pass_.run_on(bridge)

        assert pass_.result_data is not None
        assert pass_.result_data.stats.replaced_luts == 1
        assert pass_.result_data.stats.failed_luts == 0
        assert "FRAC_LUT2:dual_select_as_data" in pass_.report_summary

        gate = tmp_dir / "gate.v"
        bridge.run_pass("hierarchy -top base")
        bridge.write_verilog_path(gate)
        _assert_equiv(base, gate, tile, "base")


def test_morph_tile_pass_replaces_reduce_chain_eq() -> None:
    """Test a reduction ``__chain`` cell is replaced through CO."""
    with TemporaryDirectory(prefix="morph_tile_chain_reduce_") as td:
        tmp_dir = Path(td)
        base = _write_reduce_chain_base(tmp_dir)
        tile = _write_reduce_or_chain_tile(tmp_dir)

        bridge = PyosysBridge(debug=False)
        bridge.read_verilog_paths([base])
        pass_ = MorphTilePass(
            tile_verilog_path=tile,
            tile_top_name="reduce_or_tile",
            tile_inputs=["P0", "P1", "P2"],
            tile_outputs=["O"],
            enabled_circuits=["chain"],
            top_name="base",
            track_progress=False,
        )
        pass_.run_on(bridge)

        assert pass_.result_data is not None
        assert pass_.result_data.stats.replaced_luts == 1
        assert pass_.result_data.stats.failed_luts == 0
        assert "CHAIN:REDUCE_OR:N2" in pass_.report_summary
        cells = bridge.to_netlist_dict()["modules"]["base"]["cells"]
        assert "u_chain" not in cells
        assert cells["u_chain__morph_tile"]["type"] == "reduce_or_tile"

        gate = tmp_dir / "gate.v"
        bridge.run_pass("hierarchy -top base")
        bridge.write_verilog_path(gate)
        _assert_equiv(base, gate, tile, "base")


def test_morph_tile_pass_replaces_add_chain_eq() -> None:
    """Test an ADD ``__chain`` cell maps both Y and CO outputs."""
    with TemporaryDirectory(prefix="morph_tile_chain_add_") as td:
        tmp_dir = Path(td)
        base = _write_add_chain_base(tmp_dir)
        tile = _write_full_adder_tile(tmp_dir)

        bridge = PyosysBridge(debug=False)
        bridge.read_verilog_paths([base])
        pass_ = MorphTilePass(
            tile_verilog_path=tile,
            tile_top_name="full_adder_tile",
            tile_inputs=["P0", "P1", "P2"],
            tile_outputs=["SUM", "CARRY"],
            enabled_circuits=["chain"],
            top_name="base",
            track_progress=False,
        )
        pass_.run_on(bridge)

        assert pass_.result_data is not None
        assert pass_.result_data.stats.replaced_luts == 1
        assert pass_.result_data.stats.failed_luts == 0
        replacement = pass_.result_data.replacements[0]
        assert set(replacement.output_ports) == {"SUM", "CARRY"}
        assert "CHAIN:ADD:N2" in pass_.report_summary

        gate = tmp_dir / "gate.v"
        bridge.run_pass("hierarchy -top base")
        bridge.write_verilog_path(gate)
        _assert_equiv(base, gate, tile, "base")


def test_morph_tile_pass_skips_reduction_chain_without_co() -> None:
    """Test reduction chains without CO are ignored because Y is unused."""
    with TemporaryDirectory(prefix="morph_tile_chain_no_co_") as td:
        tmp_dir = Path(td)
        base = tmp_dir / "chain_no_co_base.v"
        base.write_text(
            f"""
{_chain_model_verilog()}

module base(input a, input b, input ci, output y);
  __chain #(
    .MODE("REDUCE_OR"),
    .N(32'd2),
    .INIT(4'he)
  ) u_chain (
    .I({{b, a}}),
    .A(2'b0),
    .B(2'b0),
    .CI(ci),
    .Y(y)
  );
endmodule
""",
            encoding="utf-8",
        )
        tile = _write_reduce_or_chain_tile(tmp_dir)

        bridge = PyosysBridge(debug=False)
        bridge.read_verilog_paths([base])
        pass_ = MorphTilePass(
            tile_verilog_path=tile,
            tile_top_name="reduce_or_tile",
            tile_inputs=["P0", "P1", "P2"],
            tile_outputs=["O"],
            enabled_circuits=["chain"],
            top_name="base",
            track_progress=False,
        )
        pass_.run_on(bridge)

        assert pass_.result_data is not None
        assert pass_.result_data.stats.total_luts == 0
        assert pass_.result_data.stats.replaced_luts == 0
        assert "u_chain" in bridge.to_netlist_dict()["modules"]["base"]["cells"]


def test_morph_tile_pass_uses_chain_permute_cache() -> None:
    """Test input-permuted chain truth tables share the permutation cache."""
    with TemporaryDirectory(prefix="morph_tile_chain_permute_cache_") as td:
        tmp_dir = Path(td)
        base = _write_chain_permute_cache_base(tmp_dir)
        tile = _write_asymmetric_chain_tile(tmp_dir)

        bridge = PyosysBridge(debug=False)
        bridge.read_verilog_paths([base])
        pass_ = MorphTilePass(
            tile_verilog_path=tile,
            tile_top_name="asym_chain_tile",
            tile_inputs=["P0", "P1"],
            tile_outputs=["O"],
            enabled_circuits=["chain"],
            top_name="base",
            track_progress=False,
        )
        pass_.run_on(bridge)

        assert pass_.result_data is not None
        assert pass_.result_data.stats.replaced_luts == 2
        assert pass_.result_data.stats.cache_misses == 1
        assert pass_.result_data.stats.cache_hits == 1

        gate = tmp_dir / "gate.v"
        bridge.run_pass("hierarchy -top base")
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
        assert len(morph_design.cells) == 1
        assert morph_design.cells[0].cell_id == "u_lut"
        assert morph_design.cells[0].cell_type == "$lut"
        assert len(morph_design.cells[0].connections["A"]) == 2
        assert morph_design.cells[0].parameters["LUT"] == "1000"


def test_morph_tile_lut_adapter_rejects_malformed_lut_output() -> None:
    """Test malformed LUT output vectors are rejected by the LUT adapter."""
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
        tile = _write_and_tile(tmp_dir)

        bridge = PyosysBridge(debug=False)
        bridge.read_verilog_paths([base])
        pass_ = MorphTilePass(
            tile_verilog_path=tile,
            tile_top_name="and_tile",
            tile_inputs=["I0", "I1"],
            tile_outputs=["O"],
            circuit_options={"lut": {"widths": [2]}},
            top_name="base",
            track_progress=False,
        )
        error_text = ""
        try:
            pass_.run_on(bridge)
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
            circuit_options={"lut": {"widths": [2]}},
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
            circuit_options={"lut": {"widths": [2]}},
            top_name="base",
            track_progress=False,
        )
        pass_.run_on(bridge)

        assert pass_.result_data is not None
        assert pass_.result_data.stats.replaced_luts == 2
        assert pass_.result_data.stats.cache_misses == 1
        assert pass_.result_data.stats.cache_hits == 1


def test_morph_tile_pass_uses_permute_solver_cache() -> None:
    """Test input-permuted LUT functions share one cached SAT result."""
    with TemporaryDirectory(prefix="morph_tile_permute_cache_") as td:
        tmp_dir = Path(td)
        base = tmp_dir / "base.v"
        base.write_text(
            """
module base(input a, input b, input c, input d, output y0, output y1);
  \\$lut #(.LUT(4'h2), .WIDTH(32'd2)) lut0 (.A({b, a}), .Y(y0));
  \\$lut #(.LUT(4'h4), .WIDTH(32'd2)) lut1 (.A({d, c}), .Y(y1));
endmodule
""",
            encoding="utf-8",
        )
        tile = _write_asymmetric_tile(tmp_dir)

        bridge = PyosysBridge(debug=False)
        bridge.read_verilog_paths([base])
        pass_ = MorphTilePass(
            tile_verilog_path=tile,
            tile_top_name="asym_tile",
            tile_inputs=["I0", "I1"],
            tile_outputs=["O"],
            circuit_options={"lut": {"widths": [2]}},
            top_name="base",
            track_progress=False,
        )
        pass_.run_on(bridge)

        assert pass_.result_data is not None
        assert pass_.result_data.stats.replaced_luts == 2
        assert pass_.result_data.stats.cache_misses == 1
        assert pass_.result_data.stats.cache_hits == 1

        gate = tmp_dir / "gate.v"
        bridge.write_verilog_path(gate)
        _assert_equiv(base, gate, tile, "base")


def test_morph_tile_pass_can_disable_permute_solver_cache() -> None:
    """Test raw INIT cache mode keeps permuted functions separate."""
    with TemporaryDirectory(prefix="morph_tile_raw_cache_") as td:
        tmp_dir = Path(td)
        base = tmp_dir / "base.v"
        base.write_text(
            """
module base(input a, input b, input c, input d, output y0, output y1);
  \\$lut #(.LUT(4'h2), .WIDTH(32'd2)) lut0 (.A({b, a}), .Y(y0));
  \\$lut #(.LUT(4'h4), .WIDTH(32'd2)) lut1 (.A({d, c}), .Y(y1));
endmodule
""",
            encoding="utf-8",
        )
        tile = _write_asymmetric_tile(tmp_dir)

        bridge = PyosysBridge(debug=False)
        bridge.read_verilog_paths([base])
        pass_ = MorphTilePass(
            tile_verilog_path=tile,
            tile_top_name="asym_tile",
            tile_inputs=["I0", "I1"],
            tile_outputs=["O"],
            top_name="base",
            circuit_options={
                "lut": {
                    "widths": [2],
                    "enable_permute_cache": False,
                },
            },
            track_progress=False,
        )
        pass_.run_on(bridge)

        assert pass_.result_data is not None
        assert pass_.result_data.stats.replaced_luts == 2
        assert pass_.result_data.stats.cache_misses == 2
        assert pass_.result_data.stats.cache_hits == 0


def test_morph_tile_pass_uses_frac_lut_permute_cache() -> None:
    """Test FRAC multi-output truth tables share the permutation cache."""
    with TemporaryDirectory(prefix="morph_tile_frac_permute_cache_") as td:
        tmp_dir = Path(td)
        base = _write_frac_permute_cache_base(tmp_dir)
        tile = _write_asymmetric_frac_tile(tmp_dir)

        bridge = PyosysBridge(debug=False)
        bridge.read_verilog_paths([base])
        pass_ = MorphTilePass(
            tile_verilog_path=tile,
            tile_top_name="asym_frac_tile",
            tile_inputs=["I0", "A0"],
            tile_outputs=["T0", "T1"],
            enabled_circuits=["frac_lut"],
            top_name="base",
            track_progress=False,
        )
        pass_.run_on(bridge)

        assert pass_.result_data is not None
        assert pass_.result_data.stats.replaced_luts == 2
        assert pass_.result_data.stats.cache_misses == 1
        assert pass_.result_data.stats.cache_hits == 1

        gate = tmp_dir / "gate.v"
        bridge.run_pass("hierarchy -top base")
        bridge.write_verilog_path(gate)
        _assert_equiv(base, gate, tile, "base")


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
            circuit_options={"lut": {"widths": [2]}},
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
            circuit_options={"lut": {"widths": [2]}},
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
            circuit_options={"lut": {"widths": [2]}},
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


def _write_asymmetric_tile(tmp_dir: Path) -> Path:
    """Write a two-input tile with input-order-sensitive behavior."""
    tile = tmp_dir / "asym_tile.v"
    tile.write_text(
        """
module asym_tile(input I0, input I1, output O);
  assign O = I0 & ~I1;
endmodule
""",
        encoding="utf-8",
    )
    return tile


def _write_frac_dual_base(tmp_dir: Path) -> Path:
    """Write a base design containing one dual-output FRAC LUT."""
    base = tmp_dir / "frac_base.v"
    frac_model = FracLutBehavioralModel(
        name="__frac_lut",
        lut_size=2,
        num_shared_inputs=1,
    ).to_verilog()
    base.write_text(
        f"""
{frac_model}

module base(input a, input b, input c, output y0, output y1);
  __frac_lut #(
    .L0_INIT(4'h8),
    .L1_INIT(4'he),
    .LUT_SIZE("2"),
    .NUM_SHARED_INPUTS("1"),
    .META_DATA("lut_mapping=dual;lut0_width=2;lut1_width=2"),
    .SELECT_AS_DATA_USED(1'b0),
    .MUX_SELECT_CONFIG(1'b0)
  ) u_frac (
    .I0(a),
    .A0(b),
    .B0(c),
    .S(1'b0),
    .O0(y0),
    .O1(y1)
  );
endmodule
""",
        encoding="utf-8",
    )
    return base


def _write_dual_frac_tile(tmp_dir: Path) -> Path:
    """Write a direct tile matching the FRAC LUT test behavior."""
    tile = tmp_dir / "dual_frac_tile.v"
    tile.write_text(
        """
module dual_frac_tile(input I0, input A0, input B0, output T0, output T1);
  assign T0 = I0 & A0;
  assign T1 = I0 | B0;
endmodule
""",
        encoding="utf-8",
    )
    return tile


def _write_frac_select_as_data_base(tmp_dir: Path) -> Path:
    """Write a base design containing one select-as-data FRAC LUT."""
    base = tmp_dir / "frac_select_as_data_base.v"
    frac_model = FracLutBehavioralModel(
        name="__frac_lut",
        lut_size=2,
        num_shared_inputs=1,
    ).to_verilog()
    base.write_text(
        f"""
{frac_model}

module base(input a, input b, input c, input d, output y0, output y1);
  __frac_lut #(
    .L0_INIT(4'h8),
    .L1_INIT(4'he),
    .LUT_SIZE("2"),
    .NUM_SHARED_INPUTS("1"),
    .META_DATA("lut_mapping=dual_select_as_data;lut0_width=2;lut1_width=2"),
    .SELECT_AS_DATA_USED(1'b1),
    .MUX_SELECT_CONFIG(1'b0)
  ) u_frac (
    .I0(a),
    .A0(b),
    .B0(c),
    .S(d),
    .O0(y0),
    .O1(y1)
  );
endmodule
""",
        encoding="utf-8",
    )
    return base


def _write_select_as_data_frac_tile(tmp_dir: Path) -> Path:
    """Write a direct tile matching the select-as-data FRAC behavior."""
    tile = tmp_dir / "select_as_data_frac_tile.v"
    tile.write_text(
        """
module select_as_data_frac_tile(
  input I0,
  input A0,
  input B0,
  input S,
  output T0,
  output T1
);
  assign T0 = A0 & S;
  assign T1 = B0 | I0;
endmodule
""",
        encoding="utf-8",
    )
    return tile


def _write_frac_permute_cache_base(tmp_dir: Path) -> Path:
    """Write two input-permuted FRAC LUTs for cache testing."""
    base = tmp_dir / "frac_permute_cache_base.v"
    frac_model = FracLutBehavioralModel(
        name="__frac_lut",
        lut_size=2,
        num_shared_inputs=1,
    ).to_verilog()
    base.write_text(
        f"""
{frac_model}

module base(
  input a,
  input b,
  input c,
  input d,
  output y0,
  output y1,
  output y2,
  output y3
);
  __frac_lut #(
    .L0_INIT(4'h2),
    .L1_INIT(4'h0),
    .LUT_SIZE("2"),
    .NUM_SHARED_INPUTS("1"),
    .META_DATA("lut_mapping=dual;lut0_width=2;lut1_width=2"),
    .SELECT_AS_DATA_USED(1'b0),
    .MUX_SELECT_CONFIG(1'b0)
  ) frac0 (
    .I0(a),
    .A0(b),
    .B0(1'b0),
    .S(1'b0),
    .O0(y0),
    .O1(y1)
  );

  __frac_lut #(
    .L0_INIT(4'h4),
    .L1_INIT(4'h0),
    .LUT_SIZE("2"),
    .NUM_SHARED_INPUTS("1"),
    .META_DATA("lut_mapping=dual;lut0_width=2;lut1_width=2"),
    .SELECT_AS_DATA_USED(1'b0),
    .MUX_SELECT_CONFIG(1'b0)
  ) frac1 (
    .I0(c),
    .A0(d),
    .B0(1'b0),
    .S(1'b0),
    .O0(y2),
    .O1(y3)
  );
endmodule
""",
        encoding="utf-8",
    )
    return base


def _write_asymmetric_frac_tile(tmp_dir: Path) -> Path:
    """Write a tile that implements one asymmetric two-output FRAC function."""
    tile = tmp_dir / "asym_frac_tile.v"
    tile.write_text(
        """
module asym_frac_tile(input I0, input A0, output T0, output T1);
  assign T0 = I0 & ~A0;
  assign T1 = 1'b0;
endmodule
""",
        encoding="utf-8",
    )
    return tile


def _chain_model_verilog() -> str:
    """Return a compact behavioral model for test ``__chain`` cells."""
    return r"""
module __chain #(
  parameter MODE = "REDUCE_OR",
  parameter [31:0] N = 32'd1,
  parameter INIT = 0,
  parameter [N-1:0] INV_IN = {N{1'b0}},
  parameter INV_OUT = 1'b0,
  parameter ALU_INIT_MODE = "xor"
) (
  input [N-1:0] I,
  input [N-1:0] A,
  input [N-1:0] B,
  input CI,
  output Y,
  output CO
);
  wire local = INIT[I];
  wire add_a = N > 1 ? I[1] : I[0];
  wire add_b = I[0];
  assign Y = MODE == "ADD" ? (local ^ CI) : local;
  assign CO =
    MODE == "REDUCE_OR"  ? (CI | local) :
    MODE == "REDUCE_AND" ? (CI & local) :
    MODE == "REDUCE_XOR" ? (CI ^ local) :
    MODE == "ADD"        ? ((add_a & add_b) | (add_a & CI) | (add_b & CI)) :
    local;
endmodule
"""


def _write_reduce_chain_base(tmp_dir: Path) -> Path:
    """Write a base design containing one reduction chain cell."""
    base = tmp_dir / "chain_reduce_base.v"
    base.write_text(
        f"""
{_chain_model_verilog()}

module base(input a, input b, input ci, output y);
  __chain #(
    .MODE("REDUCE_OR"),
    .N(32'd2),
    .INIT(4'he)
  ) u_chain (
    .I({{b, a}}),
    .A(2'b0),
    .B(2'b0),
    .CI(ci),
    .Y(),
    .CO(y)
  );
endmodule
""",
        encoding="utf-8",
    )
    return base


def _write_add_chain_base(tmp_dir: Path) -> Path:
    """Write a base design containing one ADD chain cell."""
    base = tmp_dir / "chain_add_base.v"
    base.write_text(
        f"""
{_chain_model_verilog()}

module base(input a, input b, input ci, output sum, output carry);
  __chain #(
    .MODE("ADD"),
    .N(32'd2),
    .INIT(4'h6),
    .ALU_INIT_MODE("xor")
  ) u_chain (
    .I({{a, b}}),
    .A({{a, b}}),
    .B({{a, b}}),
    .CI(ci),
    .Y(sum),
    .CO(carry)
  );
endmodule
""",
        encoding="utf-8",
    )
    return base


def _write_chain_permute_cache_base(tmp_dir: Path) -> Path:
    """Write two input-permuted chain cells for cache testing."""
    base = tmp_dir / "chain_permute_cache_base.v"
    base.write_text(
        f"""
{_chain_model_verilog()}

module base(input a, input b, input c, input d, output y0, output y1);
  __chain #(
    .MODE("REDUCE_XOR"),
    .N(32'd2),
    .INIT(4'h2)
  ) chain0 (
    .I({{b, a}}),
    .A(2'b0),
    .B(2'b0),
    .CI(1'b0),
    .Y(),
    .CO(y0)
  );

  __chain #(
    .MODE("REDUCE_XOR"),
    .N(32'd2),
    .INIT(4'h4)
  ) chain1 (
    .I({{d, c}}),
    .A(2'b0),
    .B(2'b0),
    .CI(1'b0),
    .Y(),
    .CO(y1)
  );
endmodule
""",
        encoding="utf-8",
    )
    return base


def _write_reduce_or_chain_tile(tmp_dir: Path) -> Path:
    """Write a tile that implements one two-input OR chain step."""
    tile = tmp_dir / "reduce_or_tile.v"
    tile.write_text(
        """
module reduce_or_tile(input P0, input P1, input P2, output O);
  assign O = P0 | P1 | P2;
endmodule
""",
        encoding="utf-8",
    )
    return tile


def _write_full_adder_tile(tmp_dir: Path) -> Path:
    """Write a tile that implements one ADD chain step."""
    tile = tmp_dir / "full_adder_tile.v"
    tile.write_text(
        """
module full_adder_tile(input P0, input P1, input P2, output SUM, output CARRY);
  assign SUM = P0 ^ P1 ^ P2;
  assign CARRY = (P0 & P1) | (P0 & P2) | (P1 & P2);
endmodule
""",
        encoding="utf-8",
    )
    return tile


def _write_asymmetric_chain_tile(tmp_dir: Path) -> Path:
    """Write a tile for asymmetric chain cache tests."""
    tile = tmp_dir / "asym_chain_tile.v"
    tile.write_text(
        """
module asym_chain_tile(input P0, input P1, output O);
  assign O = P0 & ~P1;
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
    run(f"read_verilog -overwrite {gate}")
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
    test_permute_cache_groups_multi_output_truth_tables()
    test_morph_tile_pass_replaces_and_lut_eq()
    test_morph_tile_pass_accepts_lut_options()
    test_morph_tile_pass_accepts_enum_circuit_kind()
    test_morph_tile_pass_replaces_dual_frac_lut_eq()
    test_morph_tile_pass_frac_lut_mode_filter_skips()
    test_morph_tile_pass_replaces_select_as_data_frac_lut_eq()
    test_morph_tile_pass_replaces_reduce_chain_eq()
    test_morph_tile_pass_replaces_add_chain_eq()
    test_morph_tile_pass_skips_reduction_chain_without_co()
    test_morph_tile_pass_uses_chain_permute_cache()
    test_morph_tile_reader_extracts_internal_lut_view()
    test_morph_tile_lut_adapter_rejects_malformed_lut_output()
    test_morph_tile_pass_leaves_unsupported_lut()
    test_morph_tile_pass_uses_solver_cache()
    test_morph_tile_pass_uses_permute_solver_cache()
    test_morph_tile_pass_can_disable_permute_solver_cache()
    test_morph_tile_pass_uses_frac_lut_permute_cache()
    test_morph_tile_pass_respects_max_replacements()
    test_morph_tile_pass_wires_scalar_config()
    test_synthesizer_morph_tile_pass_smoke()


if __name__ == "__main__":
    main()

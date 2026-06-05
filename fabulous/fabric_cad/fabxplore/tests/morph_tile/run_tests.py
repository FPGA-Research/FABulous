"""Ad-hoc tests for morph-tile mapping."""

from pathlib import Path
from tempfile import TemporaryDirectory

import pyosys.libyosys as ys
from pydantic import ValidationError

from fabulous.fabric_cad.fabxplore.flow.architecture_synthesizer import (
    ArchitectureSynthesizer,
)
from fabulous.fabric_cad.fabxplore.modules.lut_combinator.core.verilog_model import (
    FracLutBehavioralModel,
)
from fabulous.fabric_cad.fabxplore.modules.morph_tile import CutSolver
from fabulous.fabric_cad.fabxplore.modules.morph_tile.core.base import (
    MorphCircuitKind,
    MorphSolveOptions,
)
from fabulous.fabric_cad.fabxplore.modules.morph_tile.core.models import (
    CutSolveResult,
    MorphTileDesign,
    MorphTileNetlistCell,
)
from fabulous.fabric_cad.fabxplore.modules.morph_tile.core.permute_cache import (
    canonicalize_truth_table,
    permute_truth_init,
)
from fabulous.fabric_cad.fabxplore.modules.morph_tile.core.reader import (
    MorphTileReader,
)
from fabulous.fabric_cad.fabxplore.modules.morph_tile.multi_map.extractor import (
    extract_lut_graph,
)
from fabulous.fabric_cad.fabxplore.modules.morph_tile.multi_map.group_finder import (
    iter_group_candidates,
)
from fabulous.fabric_cad.fabxplore.modules.morph_tile.multi_map.models import (
    LutGraph,
    LutGroupCandidate,
    LutGroupTruth,
    LutNode,
    MultiMapMatch,
    MultiMapResult,
    MultiMapStats,
    PortBitRef,
)
from fabulous.fabric_cad.fabxplore.modules.morph_tile.multi_map.options import (
    MultiMapOptions,
)
from fabulous.fabric_cad.fabxplore.modules.morph_tile.multi_map.report import (
    render_multi_map_report,
)
from fabulous.fabric_cad.fabxplore.modules.morph_tile.multi_map.selector import (
    CpSatSetPackingSelector,
    GreedyDisjointSelector,
    LocalImprovementDisjointSelector,
    select_disjoint_matches,
    select_disjoint_matches_with_report,
)
from fabulous.fabric_cad.fabxplore.modules.morph_tile.multi_map.truth import (
    CyclicGroupError,
    build_group_truth,
)
from fabulous.fabric_cad.fabxplore.modules.sat_fab.circuit import Circuit
from fabulous.fabric_cad.fabxplore.pyosys.custom_passes.morph_tile_pass import (
    MorphTilePass,
)
from fabulous.fabric_cad.fabxplore.pyosys.pyosys_bridge import PyosysBridge
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

    def run_flow(self) -> None:
        """No-op full-flow entry point for tests."""


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


def test_cut_solver_lut0_constants() -> None:
    """Test CutSolver handles zero-input constant LUT specs."""
    with TemporaryDirectory(prefix="morph_cut_solver_lut0_") as td:
        tmp_dir = Path(td)
        tile = _write_const_config_tile(tmp_dir)
        solver = CutSolver(
            verilog_path=tile,
            top_name="const_config_tile",
            inputs=[],
            outputs=["O0", "O1"],
            configs=["CFG"],
        )

        zero = solver.solve_lut(init=0x0, lut_size=0)
        one = solver.solve_lut(init=0x1, lut_size=0)

        assert zero.sat
        assert one.sat
        assert zero.input_mapping == {}
        assert one.input_mapping == {}
        assert set(zero.output_mapping) == {"X"}
        assert set(one.output_mapping) == {"X"}


def test_preconfigured_blif_removes_dead_sequential_path() -> None:
    """Test fixed config lets Yosys remove an unselected BLIF latch cone."""
    with TemporaryDirectory(prefix="morph_tile_preconfig_blif_") as td:
        tmp_dir = Path(td)
        source = tmp_dir / "muxseq.blif"
        output = tmp_dir / "muxseq_out.blif"
        source.write_text(
            """.model muxseq
.inputs D CFG CLK
.outputs O
.names D C
1 1
.latch C Q re CLK 0
.names CFG Q C O
11- 1
0-1 1
.end
""",
            encoding="utf-8",
        )

        bridge = PyosysBridge(debug=False)
        bridge.run_pass(f"read_blif {source}")
        bridge.run_pass("hierarchy -top muxseq")
        bridge.run_pass("cd muxseq")
        bridge.run_pass("connect -set CFG 1'0")
        bridge.run_pass("cd ..")
        bridge.run_pass("simplemap")
        bridge.run_pass("opt -full")
        bridge.run_pass("clean")
        bridge.write_blif_path(output)

        blif = output.read_text(encoding="utf-8")
        assert ".latch" not in blif
        assert ".inputs CLK D CFG" in blif
        assert ".names D O" in blif

        circuit = Circuit.from_blif(
            output,
            top="muxseq",
            inputs=["D", "CFG", "CLK"],
            outputs=["O"],
        )
        assert circuit.config_names() == []


def test_preconfigured_verilog_config_bus_removes_dead_sequential_path() -> None:
    """Test fixed config bus bits keep names while pruning sequential logic."""
    with TemporaryDirectory(prefix="morph_tile_preconfig_verilog_") as td:
        tmp_dir = Path(td)
        source = tmp_dir / "buscfgseq.v"
        output = tmp_dir / "buscfgseq.blif"
        source.write_text(
            """
module buscfgseq(input D, input CLK, input [2:0] ConfigBits, output O);
  reg Q;
  wire comb = ConfigBits[1] ? ~D : D;
  always @(posedge CLK) Q <= comb;
  assign O = ConfigBits[0] ? Q : comb;
endmodule
""",
            encoding="utf-8",
        )

        bridge = PyosysBridge(debug=False)
        bridge.read_verilog_paths([source], replace_design=True)
        bridge.run_pass("hierarchy -top buscfgseq")
        bridge.run_pass("proc")
        bridge.run_pass("opt -fast")
        bridge.run_pass("cd buscfgseq")
        bridge.run_pass("connect -set ConfigBits[0] 1'0")
        bridge.run_pass("cd ..")
        bridge.run_pass("simplemap")
        bridge.run_pass("opt -full")
        bridge.run_pass("clean")
        bridge.write_blif_path(output)

        blif = output.read_text(encoding="utf-8")
        assert ".latch" not in blif
        assert "$dff" not in blif
        assert ".inputs D CLK ConfigBits[0] ConfigBits[1] ConfigBits[2]" in blif
        assert ".names $false ConfigBits[0]" in blif

        circuit = Circuit.from_blif(
            output,
            top="buscfgseq",
            inputs=["D"],
            config_prefixes=["ConfigBits"],
            outputs=["O"],
        )
        assert circuit.config_names() == [
            "ConfigBits[0]",
            "ConfigBits[1]",
            "ConfigBits[2]",
        ]


def test_cut_solver_fixed_config_maps_combinational_side_of_seq_tile() -> None:
    """Test CutSolver fixes config bits before importing a sequential tile."""
    with TemporaryDirectory(prefix="morph_tile_fixed_config_solver_") as td:
        tmp_dir = Path(td)
        tile = _write_seq_config_and_tile(tmp_dir)

        result = CutSolver(
            verilog_path=tile,
            top_name="seq_config_and_tile",
            inputs=["I0", "I1"],
            outputs=["O"],
            config_prefixes=["ConfigBits"],
            fixed_configs={"ConfigBits[0]": 0},
        ).solve_lut(init=0x8, lut_size=2, allow_input_reuse=False)

        assert result.sat
        assert result.config_bits["ConfigBits[0]"] is False
        assert result.output_mapping == {"X": "O"}
        assert set(result.input_mapping) == {"I0", "I1"}


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


def test_morph_tile_pass_wires_fixed_config_bits() -> None:
    """Test fixed config bits are emitted on replacement instances."""
    with TemporaryDirectory(prefix="morph_tile_fixed_config_pass_") as td:
        tmp_dir = Path(td)
        base = _write_and_base(tmp_dir)
        tile = _write_seq_config_and_tile(tmp_dir)

        bridge = PyosysBridge(debug=False)
        bridge.read_verilog_paths([base])
        pass_ = MorphTilePass(
            tile_verilog_path=tile,
            tile_top_name="seq_config_and_tile",
            tile_inputs=["I0", "I1"],
            tile_outputs=["O"],
            circuit_options={"lut": {"widths": [2]}},
            tile_config_prefixes=["ConfigBits"],
            tile_fixed_configs={"ConfigBits[0]": 0},
            top_name="base",
            track_progress=False,
        )
        pass_.run_on(bridge)

        assert pass_.result_data is not None
        assert pass_.result_data.stats.replaced_luts == 1
        replacement = pass_.result_data.replacements[0]
        assert replacement.config_bits["ConfigBits[0]"] is False

        cell = bridge.to_netlist_dict()["modules"]["base"]["cells"]["u_lut__morph_tile"]
        assert cell["connections"]["ConfigBits"][0] == "0"


def test_morph_tile_pass_replaces_lut0_constants_and_cache() -> None:
    """Test LUT0 constants are replaced and identical constants hit cache."""
    with TemporaryDirectory(prefix="morph_tile_lut0_") as td:
        tmp_dir = Path(td)
        base = _write_lut0_constants_base(tmp_dir)
        tile = _write_const_config_tile(tmp_dir)

        bridge = PyosysBridge(debug=False)
        bridge.read_verilog_paths([base])
        pass_ = MorphTilePass(
            tile_verilog_path=tile,
            tile_top_name="const_config_tile",
            tile_inputs=[],
            tile_outputs=["O0", "O1"],
            tile_configs=["CFG"],
            circuit_options={"lut": {"widths": [0]}},
            top_name="base",
            track_progress=False,
        )
        pass_.run_on(bridge)

        assert pass_.result_data is not None
        assert pass_.result_data.stats.replaced_luts == 3
        assert pass_.result_data.stats.failed_luts == 0
        assert pass_.result_data.stats.cache_misses == 2
        assert pass_.result_data.stats.cache_hits == 1

        gate = tmp_dir / "gate.v"
        bridge.write_verilog_path(gate)
        _assert_equiv(base, gate, tile, "base")


def test_morph_tile_pass_replaces_single_constant_frac_lut() -> None:
    """Test a single-output constant FRAC LUT maps without input routing."""
    with TemporaryDirectory(prefix="morph_tile_frac_const_single_") as td:
        tmp_dir = Path(td)
        base = _write_frac_single_constant_base(tmp_dir)
        tile = _write_const_config_tile(tmp_dir)

        bridge = PyosysBridge(debug=False)
        bridge.read_verilog_paths([base])
        pass_ = MorphTilePass(
            tile_verilog_path=tile,
            tile_top_name="const_config_tile",
            tile_inputs=[],
            tile_outputs=["O0", "O1"],
            tile_configs=["CFG"],
            enabled_circuits=["frac_lut"],
            top_name="base",
            track_progress=False,
        )
        pass_.run_on(bridge)

        assert pass_.result_data is not None
        assert pass_.result_data.stats.replaced_luts == 1
        assert pass_.result_data.stats.failed_luts == 0

        gate = tmp_dir / "gate.v"
        bridge.run_pass("hierarchy -top base")
        bridge.write_verilog_path(gate)
        _assert_equiv(base, gate, tile, "base")


def test_morph_tile_pass_replaces_dual_constant_frac_lut() -> None:
    """Test a dual-output constant FRAC LUT maps without input routing."""
    with TemporaryDirectory(prefix="morph_tile_frac_const_dual_") as td:
        tmp_dir = Path(td)
        base = _write_frac_dual_constant_base(tmp_dir)
        tile = _write_const_config_tile(tmp_dir)

        bridge = PyosysBridge(debug=False)
        bridge.read_verilog_paths([base])
        pass_ = MorphTilePass(
            tile_verilog_path=tile,
            tile_top_name="const_config_tile",
            tile_inputs=[],
            tile_outputs=["O0", "O1"],
            tile_configs=["CFG"],
            enabled_circuits=["frac_lut"],
            top_name="base",
            track_progress=False,
        )
        pass_.run_on(bridge)

        assert pass_.result_data is not None
        assert pass_.result_data.stats.replaced_luts == 1
        assert pass_.result_data.stats.failed_luts == 0

        gate = tmp_dir / "gate.v"
        bridge.run_pass("hierarchy -top base")
        bridge.write_verilog_path(gate)
        _assert_equiv(base, gate, tile, "base")


def test_morph_tile_pass_replaces_mixed_frac_lut4_lut0() -> None:
    """Test a mixed FRAC LUT with one LUT4 side and one constant side."""
    with TemporaryDirectory(prefix="morph_tile_frac_mixed_") as td:
        tmp_dir = Path(td)
        base = _write_frac_mixed_lut4_constant_base(tmp_dir)
        tile = _write_mixed_frac_tile(tmp_dir)

        bridge = PyosysBridge(debug=False)
        bridge.read_verilog_paths([base])
        pass_ = MorphTilePass(
            tile_verilog_path=tile,
            tile_top_name="mixed_frac_tile",
            tile_inputs=["I0", "I1", "I2", "A0"],
            tile_outputs=["T0", "T1"],
            enabled_circuits=["frac_lut"],
            top_name="base",
            track_progress=False,
        )
        pass_.run_on(bridge)

        assert pass_.result_data is not None
        assert pass_.result_data.stats.replaced_luts == 1
        assert pass_.result_data.stats.failed_luts == 0

        gate = tmp_dir / "gate.v"
        bridge.run_pass("hierarchy -top base")
        bridge.write_verilog_path(gate)
        _assert_equiv(base, gate, tile, "base")


def test_morph_tile_pass_constant_unsat_fails_without_crash() -> None:
    """Test an unsupported constant candidate fails cleanly instead of crashing."""
    with TemporaryDirectory(prefix="morph_tile_const_unsat_") as td:
        tmp_dir = Path(td)
        base = _write_single_lut0_base(tmp_dir, value=1)
        tile = _write_const_zero_tile(tmp_dir)

        bridge = PyosysBridge(debug=False)
        bridge.read_verilog_paths([base])
        pass_ = MorphTilePass(
            tile_verilog_path=tile,
            tile_top_name="const_zero_tile",
            tile_inputs=[],
            tile_outputs=["O"],
            circuit_options={"lut": {"widths": [0]}},
            top_name="base",
            track_progress=False,
        )
        pass_.run_on(bridge)

        assert pass_.result_data is not None
        assert pass_.result_data.stats.replaced_luts == 0
        assert pass_.result_data.stats.failed_luts == 1
        assert "u_lut" in bridge.to_netlist_dict()["modules"]["base"]["cells"]


def test_morph_tile_pass_duplicate_input_reuse_flag() -> None:
    """Test duplicate logical input use obeys allow_input_reuse."""
    with TemporaryDirectory(prefix="morph_tile_input_reuse_") as td:
        tmp_dir = Path(td)
        base = _write_identity_lut_base(tmp_dir)
        tile = _write_and_tile(tmp_dir)

        bridge_reuse = PyosysBridge(debug=False)
        bridge_reuse.read_verilog_paths([base])
        pass_reuse = MorphTilePass(
            tile_verilog_path=tile,
            tile_top_name="and_tile",
            tile_inputs=["I0", "I1"],
            tile_outputs=["O"],
            circuit_options={"lut": {"widths": [1]}},
            allow_input_reuse=True,
            top_name="base",
            track_progress=False,
        )
        pass_reuse.run_on(bridge_reuse)

        bridge_no_reuse = PyosysBridge(debug=False)
        bridge_no_reuse.read_verilog_paths([base])
        pass_no_reuse = MorphTilePass(
            tile_verilog_path=tile,
            tile_top_name="and_tile",
            tile_inputs=["I0", "I1"],
            tile_outputs=["O"],
            circuit_options={"lut": {"widths": [1]}},
            allow_input_reuse=False,
            top_name="base",
            track_progress=False,
        )
        pass_no_reuse.run_on(bridge_no_reuse)

        assert pass_reuse.result_data is not None
        assert pass_no_reuse.result_data is not None
        assert pass_reuse.result_data.stats.replaced_luts == 1
        assert pass_no_reuse.result_data.stats.replaced_luts == 0
        assert pass_no_reuse.result_data.stats.failed_luts == 1


def test_morph_tile_pass_extra_inputs_and_output_choice() -> None:
    """Test extra tile inputs may be routed and output choice is handled."""
    with TemporaryDirectory(prefix="morph_tile_unused_output_") as td:
        tmp_dir = Path(td)
        base = _write_and_base(tmp_dir)
        tile = _write_output_choice_tile(tmp_dir)

        bridge = PyosysBridge(debug=False)
        bridge.read_verilog_paths([base])
        pass_ = MorphTilePass(
            tile_verilog_path=tile,
            tile_top_name="output_choice_tile",
            tile_inputs=["I0", "I1", "UNUSED"],
            tile_outputs=["BAD", "GOOD"],
            include_unused_inputs=True,
            circuit_options={"lut": {"widths": [2]}},
            top_name="base",
            track_progress=False,
        )
        pass_.run_on(bridge)

        assert pass_.result_data is not None
        assert pass_.result_data.stats.replaced_luts == 1
        replacement = pass_.result_data.replacements[0]
        assert replacement.output_mapping == {"X": "GOOD"}
        cell = bridge.to_netlist_dict()["modules"]["base"]["cells"]["u_lut__morph_tile"]
        assert "UNUSED" in cell["connections"]


def test_morph_tile_pass_disallows_output_reuse_for_multi_output() -> None:
    """Test multi-output candidates cannot reuse one tile output by default."""
    with TemporaryDirectory(prefix="morph_tile_output_reuse_") as td:
        tmp_dir = Path(td)
        base = _write_frac_same_outputs_base(tmp_dir)
        tile = _write_single_and_output_tile(tmp_dir)

        bridge = PyosysBridge(debug=False)
        bridge.read_verilog_paths([base])
        pass_ = MorphTilePass(
            tile_verilog_path=tile,
            tile_top_name="single_and_output_tile",
            tile_inputs=["I0", "A0"],
            tile_outputs=["O"],
            enabled_circuits=["frac_lut"],
            top_name="base",
            track_progress=False,
        )
        pass_.run_on(bridge)

        assert pass_.result_data is not None
        assert pass_.result_data.stats.replaced_luts == 0
        assert pass_.result_data.stats.failed_luts == 1


def test_morph_tile_rejects_output_reuse_option() -> None:
    """Test morph-tile rejects output reuse until writers can preserve all nets."""
    try:
        MorphSolveOptions(
            allow_input_reuse=True,
            allow_input_constants=False,
            allow_output_reuse=True,
        )
    except ValueError as exc:
        message = str(exc)
        assert "allow_output_reuse=True is currently not supported" in message
        assert "overwrite output connections" in message
        return
    raise AssertionError("allow_output_reuse=True must be rejected")


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


def test_morph_tile_multi_map_replaces_two_luts_eq() -> None:
    """Test multi-map replaces two LUTs with one multi-output tile."""
    with TemporaryDirectory(prefix="morph_tile_multi_map_") as td:
        tmp_dir = Path(td)
        base = _write_multi_lut_shared_base(tmp_dir)
        tile = _write_dual_logic_tile(tmp_dir)

        bridge = PyosysBridge(debug=False)
        bridge.read_verilog_paths([base])
        pass_ = MorphTilePass(
            tile_verilog_path=tile,
            tile_top_name="dual_logic_tile",
            tile_inputs=["I0", "I1", "I2"],
            tile_outputs=["T0", "T1"],
            enabled_circuits=["multi_map"],
            circuit_options={
                "multi_map": {
                    "luts_per_group": 2,
                    "min_boundary_inputs": 3,
                    "max_boundary_inputs": 3,
                    "min_boundary_outputs": 2,
                    "max_boundary_outputs": 2,
                    "max_iterations": 20,
                    "random_seed": 4,
                }
            },
            top_name="base",
            track_progress=True,
            progress_chunk_size=1,
        )
        pass_.run_on(bridge)

        cells = bridge.to_netlist_dict()["modules"]["base"]["cells"]
        assert "lut_and" not in cells
        assert "lut_or" not in cells
        assert len(cells) == 1
        replacement = next(iter(cells.values()))
        assert replacement["type"] == "dual_logic_tile"

        gate = tmp_dir / "gate.v"
        bridge.write_verilog_path(gate)
        _assert_equiv(base, gate, tile, "base")


def test_morph_tile_multi_map_wires_permuted_inputs_eq() -> None:
    """Test multi-map preserves input-order-sensitive LUT functions."""
    with TemporaryDirectory(prefix="morph_tile_multi_map_permuted_") as td:
        tmp_dir = Path(td)
        base = _write_multi_map_permuted_base(tmp_dir)
        tile = _write_dual_asymmetric_tile(tmp_dir)

        bridge = PyosysBridge(debug=False)
        bridge.read_verilog_paths([base])
        pass_ = MorphTilePass(
            tile_verilog_path=tile,
            tile_top_name="dual_asymmetric_tile",
            tile_inputs=["I0", "I1", "I2", "I3"],
            tile_outputs=["T0", "T1"],
            enabled_circuits=["multi_map"],
            circuit_options={
                "multi_map": {
                    "luts_per_group": 2,
                    "min_boundary_inputs": 4,
                    "max_boundary_inputs": 4,
                    "min_boundary_outputs": 2,
                    "max_boundary_outputs": 2,
                    "max_iterations": 20,
                    "random_seed": 7,
                }
            },
            top_name="base",
            track_progress=False,
        )
        pass_.run_on(bridge)

        result = pass_.result_data
        assert result is not None
        assert "- replaced LUTs: 2" in result.report_summary
        cells = bridge.to_netlist_dict()["modules"]["base"]["cells"]
        assert "lut_left" not in cells
        assert "lut_right" not in cells
        assert next(iter(cells.values()))["type"] == "dual_asymmetric_tile"

        gate = tmp_dir / "gate.v"
        bridge.write_verilog_path(gate)
        _assert_equiv(base, gate, tile, "base")


def test_morph_tile_multi_map_wires_exposed_internal_output_eq() -> None:
    """Test replacing a cascade preserves an internal net used outside LUTs."""
    with TemporaryDirectory(prefix="morph_tile_multi_map_internal_output_") as td:
        tmp_dir = Path(td)
        base = _write_multi_map_internal_output_base(tmp_dir)
        tile = _write_cascade_with_internal_output_tile(tmp_dir)

        bridge = PyosysBridge(debug=False)
        bridge.read_verilog_paths([base])
        pass_ = MorphTilePass(
            tile_verilog_path=tile,
            tile_top_name="cascade_with_internal_output_tile",
            tile_inputs=["I0", "I1", "I2"],
            tile_outputs=["MID", "OUT"],
            enabled_circuits=["multi_map"],
            circuit_options={
                "multi_map": {
                    "luts_per_group": 2,
                    "min_boundary_inputs": 3,
                    "max_boundary_inputs": 3,
                    "min_boundary_outputs": 2,
                    "max_boundary_outputs": 2,
                    "max_iterations": 20,
                    "connected_only": True,
                }
            },
            top_name="base",
            track_progress=False,
        )
        pass_.run_on(bridge)

        result = pass_.result_data
        assert result is not None
        assert "- replaced LUTs: 2" in result.report_summary
        cells = bridge.to_netlist_dict()["modules"]["base"]["cells"]
        assert "lut_mid" not in cells
        assert "lut_out" not in cells
        replacement = next(
            cell
            for cell in cells.values()
            if cell["type"] == "cascade_with_internal_output_tile"
        )
        assert {"MID", "OUT"} <= set(replacement["connections"])
        assert "u_side" in cells

        gate = tmp_dir / "gate.v"
        bridge.write_verilog_path(gate)
        _assert_equiv(base, gate, tile, "base")


def test_morph_tile_multi_map_mixed_group_sizes_eq() -> None:
    """Test mixed one- and two-LUT replacements keep the mapped netlist equal."""
    with TemporaryDirectory(prefix="morph_tile_multi_map_mixed_sizes_") as td:
        tmp_dir = Path(td)
        base = _write_multi_map_mixed_sizes_base(tmp_dir)
        tile = _write_configurable_mixed_logic_tile(tmp_dir)

        bridge = PyosysBridge(debug=False)
        bridge.read_verilog_paths([base])
        pass_ = MorphTilePass(
            tile_verilog_path=tile,
            tile_top_name="configurable_mixed_logic_tile",
            tile_inputs=["I0", "I1", "I2"],
            tile_outputs=["T0", "T1"],
            tile_configs=["CFG"],
            enabled_circuits=["multi_map"],
            circuit_options={
                "multi_map": {
                    "luts_per_group": [1, 2],
                    "min_boundary_inputs": 2,
                    "max_boundary_inputs": 3,
                    "min_boundary_outputs": 1,
                    "max_boundary_outputs": 2,
                    "max_iterations": 20,
                    "random_seed": 3,
                }
            },
            top_name="base",
            track_progress=False,
        )
        pass_.run_on(bridge)

        result = pass_.result_data
        assert result is not None
        assert "- selected groups: 2" in result.report_summary
        assert "- replaced LUTs: 3" in result.report_summary
        cells = bridge.to_netlist_dict()["modules"]["base"]["cells"]
        assert "lut_and" not in cells
        assert "lut_or" not in cells
        assert "lut_xor" not in cells
        assert len(cells) == 2
        assert {cell["type"] for cell in cells.values()} == {
            "configurable_mixed_logic_tile"
        }

        gate = tmp_dir / "gate.v"
        bridge.write_verilog_path(gate)
        _assert_equiv(base, gate, tile, "base")


def test_morph_tile_multi_map_rejects_outputs_option() -> None:
    """Test multi-map rejects the removed legacy outputs option."""
    try:
        MultiMapOptions.model_validate({"outputs": 2})
    except ValidationError as exc:
        if "outputs" not in str(exc):
            raise AssertionError("validation error should name outputs") from exc
    else:
        raise AssertionError("legacy outputs option must be rejected")


def test_morph_tile_multi_map_local_selector_improves_greedy() -> None:
    """Test local selector replaces one greedy match with two better matches."""
    matches = [
        _fake_multi_map_match(("a", "b"), score=30),
        _fake_multi_map_match(("a", "c"), score=20),
        _fake_multi_map_match(("b", "d"), score=20),
    ]
    options = MultiMapOptions()

    greedy = GreedyDisjointSelector().select(matches, options)
    improved = LocalImprovementDisjointSelector().select(matches, options)
    public = select_disjoint_matches(matches, options)

    assert [match.candidate.lut_ids for match in greedy] == [("a", "b")]
    assert {match.candidate.lut_ids for match in improved} == {
        ("a", "c"),
        ("b", "d"),
    }
    assert public == improved


def test_morph_tile_multi_map_cp_sat_selector_looks_past_local_swap() -> None:
    """Test CP-SAT selector improves cases requiring two greedy removals."""
    matches = [
        _fake_multi_map_match(("a", "b"), score=100),
        _fake_multi_map_match(("c", "d"), score=100),
        _fake_multi_map_match(("a", "c"), score=90),
        _fake_multi_map_match(("b", "e"), score=90),
        _fake_multi_map_match(("d", "f"), score=90),
    ]
    options = MultiMapOptions()

    greedy = GreedyDisjointSelector().select(matches, options)
    local = LocalImprovementDisjointSelector().select(matches, options)
    cp_sat = CpSatSetPackingSelector(max_time_seconds=10).select(matches, options)

    assert {match.candidate.lut_ids for match in greedy} == {
        ("a", "b"),
        ("c", "d"),
    }
    assert local == greedy
    assert {match.candidate.lut_ids for match in cp_sat} == {
        ("a", "c"),
        ("b", "e"),
        ("d", "f"),
    }


def test_morph_tile_multi_map_cp_sat_prefers_fewer_replacements_on_tie() -> None:
    """Test same LUT coverage prefers fewer replacement instances."""
    matches = [
        _fake_multi_map_match(("a", "b", "c", "d"), score=1),
        _fake_multi_map_match(("a", "b"), score=1_000),
        _fake_multi_map_match(("c", "d"), score=1_000),
    ]
    options = MultiMapOptions(
        luts_per_group=[2, 4],
        min_boundary_outputs=1,
    )

    selected = CpSatSetPackingSelector(max_time_seconds=10).select(matches, options)

    assert [match.candidate.lut_ids for match in selected] == [("a", "b", "c", "d")]


def test_morph_tile_multi_map_cp_sat_reports_selector_metadata() -> None:
    """Test CP-SAT selector returns report metadata and progress events."""
    matches = [
        _fake_multi_map_match(("a", "b"), score=100),
        _fake_multi_map_match(("c", "d"), score=100),
        _fake_multi_map_match(("a", "c"), score=90),
        _fake_multi_map_match(("b", "e"), score=90),
        _fake_multi_map_match(("d", "f"), score=90),
    ]
    events: list[dict[str, object]] = []

    selected, metadata = select_disjoint_matches_with_report(
        matches,
        MultiMapOptions(),
        progress=events.append,
    )

    assert {match.candidate.lut_ids for match in selected} == {
        ("a", "c"),
        ("b", "e"),
        ("d", "f"),
    }
    assert metadata["selector"] == "cp_sat_set_packing"
    assert metadata["status"] in {"OPTIMAL", "FEASIBLE"}
    assert metadata["fallback_used"] is False
    assert metadata["input_matches"] == len(matches)
    assert metadata["selected_groups"] == 3
    assert metadata["replaced_luts"] == 6
    assert any(event["event"] == "start" for event in events)
    assert any(event["event"] == "finish" for event in events)


def test_morph_tile_multi_map_report_shows_selector_and_stored_matches() -> None:
    """Test multi-map report distinguishes total and retained SAT matches."""
    result = MultiMapResult(
        top_name="top",
        tile_top_name="tile",
        options_summary={},
        stats=MultiMapStats(
            total_groups=10,
            checked_groups=10,
            sat_matches_total=7,
            matched_groups=3,
            selected_groups=2,
            replaced_luts=4,
            cache_hits=5,
            cache_misses=5,
        ),
        replacements=(),
        metadata={
            "selector": {
                "selector": "cp_sat_set_packing",
                "status": "OPTIMAL",
                "fallback_used": False,
                "wall_time_s": 1.25,
            }
        },
    )

    report = render_multi_map_report(result)

    assert "- SAT matches total: 7" in report
    assert "- SAT matches stored: 3" in report
    assert "- selector: cp_sat_set_packing" in report
    assert "- selector status: OPTIMAL" in report
    assert "- selector fallback used: False" in report
    assert "- selector time: 1.250s" in report


def test_morph_tile_multi_map_validates_luts_per_group_choices() -> None:
    """Test LUT group sizes can be one value or a normalized list."""
    assert MultiMapOptions(luts_per_group=3).group_sizes() == (3,)
    assert MultiMapOptions(luts_per_group=[3, 2, 2]).group_sizes() == (2, 3)
    for value in (0, [], [2, 0]):
        try:
            MultiMapOptions(luts_per_group=value)
        except (TypeError, ValidationError, ValueError):
            continue
        raise AssertionError("luts_per_group choices must be positive and non-empty")


def test_morph_tile_multi_map_generates_multiple_group_sizes() -> None:
    """Test group finder merges candidates from multiple exact group sizes."""
    nodes = {
        "l0": LutNode(
            cell_id="l0",
            width=2,
            init=0x8,
            input_tokens=("a", "b"),
            output_token="n0",
            input_refs=(PortBitRef("l0", "A", 0), PortBitRef("l0", "A", 1)),
            output_ref=PortBitRef("l0", "Y", 0),
        ),
        "l1": LutNode(
            cell_id="l1",
            width=2,
            init=0xE,
            input_tokens=("c", "d"),
            output_token="n1",
            input_refs=(PortBitRef("l1", "A", 0), PortBitRef("l1", "A", 1)),
            output_ref=PortBitRef("l1", "Y", 0),
        ),
    }
    graph = LutGraph(
        nodes=nodes,
        driver_by_token={"n0": "l0", "n1": "l1"},
        users_by_token={},
    )

    candidates = iter_group_candidates(
        graph,
        MultiMapOptions(
            luts_per_group=[1, 2],
            min_boundary_inputs=2,
            max_boundary_inputs=4,
            min_boundary_outputs=1,
            max_boundary_outputs=2,
            max_iterations=1,
        ),
    )

    assert {len(candidate.lut_ids) for candidate in candidates} == {1, 2}


def test_morph_tile_multi_map_validates_pure_random_match() -> None:
    """Test pure random match ratio must stay within probability bounds."""
    assert MultiMapOptions(pure_random_match=0.25).pure_random_match == 0.25
    for value in (-0.1, 1.1):
        try:
            MultiMapOptions(pure_random_match=value)
        except ValidationError:
            continue
        raise AssertionError("pure_random_match must be in [0, 1]")


def test_morph_tile_multi_map_validates_max_graph_hops() -> None:
    """Test graph hop override must be positive when set."""
    assert MultiMapOptions(max_graph_hops=2).max_graph_hops == 2
    try:
        MultiMapOptions(max_graph_hops=0)
    except ValidationError:
        return
    raise AssertionError("max_graph_hops must be positive when set")


def test_morph_tile_multi_map_max_graph_hops_reaches_far_partner() -> None:
    """Test graph hop override can find a farther local cone partner."""
    nodes = {
        "l0": LutNode(
            cell_id="l0",
            width=2,
            init=0x8,
            input_tokens=("a", "b"),
            output_token="n0",
            input_refs=(PortBitRef("l0", "A", 0), PortBitRef("l0", "A", 1)),
            output_ref=PortBitRef("l0", "Y", 0),
        ),
        "l1": LutNode(
            cell_id="l1",
            width=3,
            init=0xE8,
            input_tokens=("n0", "b", "c"),
            output_token="n1",
            input_refs=(
                PortBitRef("l1", "A", 0),
                PortBitRef("l1", "A", 1),
                PortBitRef("l1", "A", 2),
            ),
            output_ref=PortBitRef("l1", "Y", 0),
        ),
        "l2": LutNode(
            cell_id="l2",
            width=3,
            init=0x96,
            input_tokens=("n1", "c", "d"),
            output_token="y",
            input_refs=(
                PortBitRef("l2", "A", 0),
                PortBitRef("l2", "A", 1),
                PortBitRef("l2", "A", 2),
            ),
            output_ref=PortBitRef("l2", "Y", 0),
        ),
    }
    graph = LutGraph(
        nodes=nodes,
        driver_by_token={"n0": "l0", "n1": "l1", "y": "l2"},
        users_by_token={"n0": ("l1",), "n1": ("l2",)},
    )
    base_options = {
        "luts_per_group": 2,
        "min_boundary_inputs": 5,
        "max_boundary_inputs": 5,
        "min_boundary_outputs": 2,
        "max_boundary_outputs": 2,
        "max_graph_frontier": 2,
        "max_iterations": 1,
        "random_seed": 1,
    }

    default_candidates = iter_group_candidates(graph, MultiMapOptions(**base_options))
    assert all(candidate.lut_ids != ("l0", "l2") for candidate in default_candidates)

    deep_candidates = iter_group_candidates(
        graph,
        MultiMapOptions(**base_options, max_graph_hops=2),
    )
    far = next(
        candidate for candidate in deep_candidates if candidate.lut_ids == ("l0", "l2")
    )
    assert far.boundary_tokens == ("a", "b", "n1", "c", "d")
    assert list(far.output_refs) == ["Y0", "Y1"]


def test_morph_tile_multi_map_rejects_cyclic_group_truth() -> None:
    """Test cyclic LUT groups are classified with a dedicated exception."""
    nodes = {
        "l0": LutNode(
            cell_id="l0",
            width=2,
            init=0x8,
            input_tokens=("n1", "a"),
            output_token="n0",
            input_refs=(PortBitRef("l0", "A", 0), PortBitRef("l0", "A", 1)),
            output_ref=PortBitRef("l0", "Y", 0),
        ),
        "l1": LutNode(
            cell_id="l1",
            width=2,
            init=0xE,
            input_tokens=("n0", "b"),
            output_token="n1",
            input_refs=(PortBitRef("l1", "A", 0), PortBitRef("l1", "A", 1)),
            output_ref=PortBitRef("l1", "Y", 0),
        ),
    }
    graph = LutGraph(
        nodes=nodes,
        driver_by_token={"n0": "l0", "n1": "l1"},
        users_by_token={"n0": ("l1",), "n1": ("l0",)},
    )
    candidate = LutGroupCandidate(
        lut_ids=("l0", "l1"),
        boundary_tokens=("a", "b"),
        boundary_refs={
            "a": PortBitRef("l0", "A", 1),
            "b": PortBitRef("l1", "A", 1),
        },
        output_refs={"Y0": PortBitRef("l0", "Y", 0)},
    )

    error_text = ""
    try:
        build_group_truth(graph, candidate)
    except CyclicGroupError as exc:
        error_text = str(exc)
    assert "group contains a cycle" in error_text


def test_morph_tile_multi_map_graph_growth_finds_cascade_group() -> None:
    """Test deterministic graph growth finds a small LUT cascade group."""
    nodes = {
        "l0": LutNode(
            cell_id="l0",
            width=2,
            init=0x8,
            input_tokens=("a", "b"),
            output_token="n0",
            input_refs=(PortBitRef("l0", "A", 0), PortBitRef("l0", "A", 1)),
            output_ref=PortBitRef("l0", "Y", 0),
        ),
        "l1": LutNode(
            cell_id="l1",
            width=2,
            init=0xE,
            input_tokens=("a", "c"),
            output_token="n1",
            input_refs=(PortBitRef("l1", "A", 0), PortBitRef("l1", "A", 1)),
            output_ref=PortBitRef("l1", "Y", 0),
        ),
        "l2": LutNode(
            cell_id="l2",
            width=2,
            init=0x6,
            input_tokens=("b", "c"),
            output_token="n2",
            input_refs=(PortBitRef("l2", "A", 0), PortBitRef("l2", "A", 1)),
            output_ref=PortBitRef("l2", "Y", 0),
        ),
        "l3": LutNode(
            cell_id="l3",
            width=3,
            init=0x80,
            input_tokens=("n0", "n1", "n2"),
            output_token="y",
            input_refs=(
                PortBitRef("l3", "A", 0),
                PortBitRef("l3", "A", 1),
                PortBitRef("l3", "A", 2),
            ),
            output_ref=PortBitRef("l3", "Y", 0),
        ),
    }
    graph = LutGraph(
        nodes=nodes,
        driver_by_token={"n0": "l0", "n1": "l1", "n2": "l2", "y": "l3"},
        users_by_token={"n0": ("l3",), "n1": ("l3",), "n2": ("l3",)},
    )

    candidates = iter_group_candidates(
        graph,
        MultiMapOptions(
            luts_per_group=4,
            min_boundary_inputs=3,
            max_boundary_inputs=3,
            min_boundary_outputs=1,
            max_boundary_outputs=1,
            max_graph_frontier=2,
            max_iterations=1,
            connected_only=True,
        ),
    )

    cascade = next(
        candidate
        for candidate in candidates
        if candidate.lut_ids == ("l0", "l1", "l2", "l3")
    )
    assert cascade.boundary_tokens == ("a", "b", "c")
    assert list(cascade.output_refs) == ["Y0"]
    assert cascade.output_refs["Y0"].cell_id == "l3"


def test_morph_tile_multi_map_extracts_non_lut_output_use() -> None:
    """Test extractor marks LUT outputs touched by non-LUT cells."""
    design = MorphTileDesign(
        top_name="top",
        cells=(
            MorphTileNetlistCell(
                cell_id="l0",
                cell_type="$lut",
                parameters={"LUT": "8"},
                connections={"A": ("a", "b"), "Y": ("n0",)},
            ),
            MorphTileNetlistCell(
                cell_id="l1",
                cell_type="$lut",
                parameters={"LUT": "14"},
                connections={"A": ("n0", "c"), "Y": ("y",)},
            ),
            MorphTileNetlistCell(
                cell_id="ff0",
                cell_type="$dff",
                parameters={},
                connections={"D": ("n0",), "Q": ("q",), "CLK": ("clk",)},
            ),
        ),
    )

    graph = extract_lut_graph(design)

    assert graph.users_by_token["n0"] == ("l1",)
    assert graph.external_user_tokens == frozenset({"n0"})


def test_morph_tile_multi_map_exposes_internal_net_with_non_lut_use() -> None:
    """Test non-LUT users turn an internal cascade net into an output."""
    nodes = {
        "l0": LutNode(
            cell_id="l0",
            width=2,
            init=0x8,
            input_tokens=("a", "b"),
            output_token="n0",
            input_refs=(PortBitRef("l0", "A", 0), PortBitRef("l0", "A", 1)),
            output_ref=PortBitRef("l0", "Y", 0),
        ),
        "l1": LutNode(
            cell_id="l1",
            width=2,
            init=0xE,
            input_tokens=("n0", "c"),
            output_token="y",
            input_refs=(PortBitRef("l1", "A", 0), PortBitRef("l1", "A", 1)),
            output_ref=PortBitRef("l1", "Y", 0),
        ),
    }
    graph = LutGraph(
        nodes=nodes,
        driver_by_token={"n0": "l0", "y": "l1"},
        users_by_token={"n0": ("l1",)},
        external_user_tokens=frozenset({"n0"}),
    )

    candidates = iter_group_candidates(
        graph,
        MultiMapOptions(
            luts_per_group=2,
            min_boundary_inputs=3,
            max_boundary_inputs=3,
            min_boundary_outputs=2,
            max_boundary_outputs=2,
            max_iterations=1,
            connected_only=True,
        ),
    )

    cascade = next(
        candidate for candidate in candidates if candidate.lut_ids == ("l0", "l1")
    )
    assert cascade.boundary_tokens == ("a", "b", "c")
    assert list(cascade.output_refs) == ["Y0", "Y1"]
    assert cascade.output_refs["Y0"].cell_id == "l0"
    assert cascade.output_refs["Y1"].cell_id == "l1"


def test_morph_tile_multi_map_rejects_extra_non_lut_output_when_not_allowed() -> None:
    """Test boundary output limits reject exposed non-LUT side uses."""
    nodes = {
        "l0": LutNode(
            cell_id="l0",
            width=2,
            init=0x8,
            input_tokens=("a", "b"),
            output_token="n0",
            input_refs=(PortBitRef("l0", "A", 0), PortBitRef("l0", "A", 1)),
            output_ref=PortBitRef("l0", "Y", 0),
        ),
        "l1": LutNode(
            cell_id="l1",
            width=2,
            init=0xE,
            input_tokens=("n0", "c"),
            output_token="y",
            input_refs=(PortBitRef("l1", "A", 0), PortBitRef("l1", "A", 1)),
            output_ref=PortBitRef("l1", "Y", 0),
        ),
    }
    graph = LutGraph(
        nodes=nodes,
        driver_by_token={"n0": "l0", "y": "l1"},
        users_by_token={"n0": ("l1",)},
        external_user_tokens=frozenset({"n0"}),
    )

    candidates = iter_group_candidates(
        graph,
        MultiMapOptions(
            luts_per_group=2,
            min_boundary_inputs=3,
            max_boundary_inputs=3,
            min_boundary_outputs=1,
            max_boundary_outputs=1,
            max_iterations=1,
            connected_only=True,
        ),
    )

    assert all(candidate.lut_ids != ("l0", "l1") for candidate in candidates)


def test_morph_tile_multi_map_keeps_pure_internal_cascade_internal() -> None:
    """Test LUT-only cascade nets are not exposed unnecessarily."""
    nodes = {
        "l0": LutNode(
            cell_id="l0",
            width=2,
            init=0x8,
            input_tokens=("a", "b"),
            output_token="n0",
            input_refs=(PortBitRef("l0", "A", 0), PortBitRef("l0", "A", 1)),
            output_ref=PortBitRef("l0", "Y", 0),
        ),
        "l1": LutNode(
            cell_id="l1",
            width=2,
            init=0xE,
            input_tokens=("n0", "c"),
            output_token="y",
            input_refs=(PortBitRef("l1", "A", 0), PortBitRef("l1", "A", 1)),
            output_ref=PortBitRef("l1", "Y", 0),
        ),
    }
    graph = LutGraph(
        nodes=nodes,
        driver_by_token={"n0": "l0", "y": "l1"},
        users_by_token={"n0": ("l1",)},
    )

    candidates = iter_group_candidates(
        graph,
        MultiMapOptions(
            luts_per_group=2,
            min_boundary_inputs=3,
            max_boundary_inputs=3,
            min_boundary_outputs=1,
            max_boundary_outputs=1,
            max_iterations=1,
            connected_only=True,
        ),
    )

    cascade = next(
        candidate for candidate in candidates if candidate.lut_ids == ("l0", "l1")
    )
    assert list(cascade.output_refs) == ["Y0"]
    assert cascade.output_refs["Y0"].cell_id == "l1"


def test_morph_tile_multi_map_shared_input_fallback_keeps_unrelated_group() -> None:
    """Test shared-input grouping falls back to zero-shared LUT partners."""
    nodes = {
        "l0": LutNode(
            cell_id="l0",
            width=2,
            init=0x8,
            input_tokens=("a", "b"),
            output_token="n0",
            input_refs=(PortBitRef("l0", "A", 0), PortBitRef("l0", "A", 1)),
            output_ref=PortBitRef("l0", "Y", 0),
        ),
        "l1": LutNode(
            cell_id="l1",
            width=2,
            init=0xE,
            input_tokens=("c", "d"),
            output_token="n1",
            input_refs=(PortBitRef("l1", "A", 0), PortBitRef("l1", "A", 1)),
            output_ref=PortBitRef("l1", "Y", 0),
        ),
    }
    graph = LutGraph(
        nodes=nodes,
        driver_by_token={"n0": "l0", "n1": "l1"},
        users_by_token={},
    )

    candidates = iter_group_candidates(
        graph,
        MultiMapOptions(
            luts_per_group=2,
            min_boundary_inputs=4,
            max_boundary_inputs=4,
            min_boundary_outputs=2,
            max_boundary_outputs=2,
            max_iterations=1,
        ),
    )

    fallback = next(
        candidate for candidate in candidates if candidate.lut_ids == ("l0", "l1")
    )
    assert fallback.boundary_tokens == ("a", "b", "c", "d")
    assert list(fallback.output_refs) == ["Y0", "Y1"]


def test_morph_tile_multi_map_wires_constant_input_route_eq() -> None:
    """Test multi-map emits constant-routed tile inputs."""
    with TemporaryDirectory(prefix="morph_tile_multi_map_const_") as td:
        tmp_dir = Path(td)
        base = _write_identity_pair_base(tmp_dir)
        tile = _write_const_route_dual_tile(tmp_dir)

        bridge = PyosysBridge(debug=False)
        bridge.read_verilog_paths([base])
        pass_ = MorphTilePass(
            tile_verilog_path=tile,
            tile_top_name="const_route_dual_tile",
            tile_inputs=["D0", "D1", "ONE"],
            tile_outputs=["O0", "O1"],
            enabled_circuits=["multi_map"],
            circuit_options={
                "multi_map": {
                    "luts_per_group": 2,
                    "min_boundary_inputs": 2,
                    "max_boundary_inputs": 2,
                    "min_boundary_outputs": 2,
                    "max_boundary_outputs": 2,
                    "max_iterations": 20,
                }
            },
            allow_input_constants=True,
            top_name="base",
            track_progress=False,
        )
        pass_.run_on(bridge)

        cells = bridge.to_netlist_dict()["modules"]["base"]["cells"]
        replacement = next(iter(cells.values()))
        assert replacement["type"] == "const_route_dual_tile"
        assert replacement["connections"]["ONE"] == ["1"]

        gate = tmp_dir / "gate.v"
        bridge.write_verilog_path(gate)
        _assert_equiv(base, gate, tile, "base")


def _fake_multi_map_match(lut_ids: tuple[str, ...], score: int) -> MultiMapMatch:
    """Build a lightweight selector-only multi-map match."""
    return MultiMapMatch(
        candidate=LutGroupCandidate(
            lut_ids=lut_ids,
            boundary_tokens=(),
            boundary_refs={},
            output_refs={},
        ),
        truth=LutGroupTruth(input_names=[], output_inits={}),
        result=CutSolveResult(sat=True),
        score=score,
    )


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


def _write_multi_lut_shared_base(tmp_dir: Path) -> Path:
    """Write two LUTs with one shared source input."""
    base = tmp_dir / "multi_lut_shared_base.v"
    base.write_text(
        """
module base(input a, input b, input c, output y0, output y1);
  \\$lut #(.LUT(4'h8), .WIDTH(32'd2)) lut_and (.A({b, a}), .Y(y0));
  \\$lut #(.LUT(4'he), .WIDTH(32'd2)) lut_or (.A({c, a}), .Y(y1));
endmodule
""",
        encoding="utf-8",
    )
    return base


def _write_dual_logic_tile(tmp_dir: Path) -> Path:
    """Write a two-output tile that can implement the shared-base test."""
    tile = tmp_dir / "dual_logic_tile.v"
    tile.write_text(
        """
module dual_logic_tile(input I0, input I1, input I2, output T0, output T1);
  assign T0 = I0 & I1;
  assign T1 = I0 | I2;
endmodule
""",
        encoding="utf-8",
    )
    return tile


def _write_multi_map_permuted_base(tmp_dir: Path) -> Path:
    """Write two input-order-sensitive LUTs for multi-map wiring tests."""
    base = tmp_dir / "multi_map_permuted_base.v"
    base.write_text(
        """
module base(input a, input b, input c, input d, output y0, output y1);
  \\$lut #(.LUT(4'h2), .WIDTH(32'd2)) lut_left (.A({b, a}), .Y(y0));
  \\$lut #(.LUT(4'h4), .WIDTH(32'd2)) lut_right (.A({d, c}), .Y(y1));
endmodule
""",
        encoding="utf-8",
    )
    return base


def _write_dual_asymmetric_tile(tmp_dir: Path) -> Path:
    """Write a dual-output tile with input-order-sensitive logic."""
    tile = tmp_dir / "dual_asymmetric_tile.v"
    tile.write_text(
        """
module dual_asymmetric_tile(
  input I0,
  input I1,
  input I2,
  input I3,
  output T0,
  output T1
);
  assign T0 = I0 & ~I1;
  assign T1 = I2 & ~I3;
endmodule
""",
        encoding="utf-8",
    )
    return tile


def _write_multi_map_internal_output_base(tmp_dir: Path) -> Path:
    """Write a cascade whose internal net also feeds a non-LUT cell."""
    base = tmp_dir / "multi_map_internal_output_base.v"
    base.write_text(
        """
module side_consumer(input A, input B, output Y);
  assign Y = A ^ B;
endmodule

module base(input a, input b, input c, output y, output side);
  wire n_mid;
  \\$lut #(.LUT(4'h8), .WIDTH(32'd2)) lut_mid (.A({b, a}), .Y(n_mid));
  \\$lut #(.LUT(4'he), .WIDTH(32'd2)) lut_out (.A({c, n_mid}), .Y(y));
  side_consumer u_side (.A(n_mid), .B(c), .Y(side));
endmodule
""",
        encoding="utf-8",
    )
    return base


def _write_cascade_with_internal_output_tile(tmp_dir: Path) -> Path:
    """Write a tile that exposes both cascade middle and final outputs."""
    tile = tmp_dir / "cascade_with_internal_output_tile.v"
    tile.write_text(
        """
module cascade_with_internal_output_tile(
  input I0,
  input I1,
  input I2,
  output MID,
  output OUT
);
  wire middle = I0 & I1;
  assign MID = middle;
  assign OUT = middle | I2;
endmodule
""",
        encoding="utf-8",
    )
    return tile


def _write_multi_map_mixed_sizes_base(tmp_dir: Path) -> Path:
    """Write a small design that benefits from mixed-size multi-map groups."""
    base = tmp_dir / "multi_map_mixed_sizes_base.v"
    base.write_text(
        """
module base(
  input a, input b, input c, input d, input e,
  output y0, output y1, output y2
);
  \\$lut #(.LUT(4'h8), .WIDTH(32'd2)) lut_and (.A({b, a}), .Y(y0));
  \\$lut #(.LUT(4'he), .WIDTH(32'd2)) lut_or (.A({c, a}), .Y(y1));
  \\$lut #(.LUT(4'h6), .WIDTH(32'd2)) lut_xor (.A({e, d}), .Y(y2));
endmodule
""",
        encoding="utf-8",
    )
    return base


def _write_configurable_mixed_logic_tile(tmp_dir: Path) -> Path:
    """Write a tile usable as a dual AND/OR group or a single XOR group."""
    tile = tmp_dir / "configurable_mixed_logic_tile.v"
    tile.write_text(
        """
module configurable_mixed_logic_tile(
  input I0,
  input I1,
  input I2,
  input CFG,
  output T0,
  output T1
);
  assign T0 = CFG ? (I0 ^ I1) : (I0 & I1);
  assign T1 = I0 | I2;
endmodule
""",
        encoding="utf-8",
    )
    return tile


def _write_identity_pair_base(tmp_dir: Path) -> Path:
    """Write two independent identity LUTs."""
    base = tmp_dir / "identity_pair_base.v"
    base.write_text(
        """
module base(input a, input b, output y0, output y1);
  \\$lut #(.LUT(2'h2), .WIDTH(32'd1)) lut_a (.A(a), .Y(y0));
  \\$lut #(.LUT(2'h2), .WIDTH(32'd1)) lut_b (.A(b), .Y(y1));
endmodule
""",
        encoding="utf-8",
    )
    return base


def _write_const_route_dual_tile(tmp_dir: Path) -> Path:
    """Write a dual tile that requires a constant-one input for identity."""
    tile = tmp_dir / "const_route_dual_tile.v"
    tile.write_text(
        """
module const_route_dual_tile(input D0, input D1, input ONE, output O0, output O1);
  assign O0 = D0 & ONE;
  assign O1 = D1 & ONE;
endmodule
""",
        encoding="utf-8",
    )
    return tile


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


def _write_seq_config_and_tile(tmp_dir: Path) -> Path:
    """Write a tile with config-selectable combinational/sequential output."""
    tile = tmp_dir / "seq_config_and_tile.v"
    tile.write_text(
        """
module seq_config_and_tile(
    input I0,
    input I1,
    input CLK,
    input [1:0] ConfigBits,
    output O
);
  reg Q;
  wire comb = I0 & I1;
  always @(posedge CLK) Q <= comb;
  assign O = ConfigBits[0] ? Q : comb;
endmodule
""",
        encoding="utf-8",
    )
    return tile


def _write_lut0_constants_base(tmp_dir: Path) -> Path:
    """Write three LUT0 constants with one duplicated constant value."""
    base = tmp_dir / "lut0_constants_base.v"
    base.write_text(
        """
module base(output y0, output y1, output y2);
  \\$lut #(.LUT(1'h0), .WIDTH(32'd0)) const0 (.A(), .Y(y0));
  \\$lut #(.LUT(1'h1), .WIDTH(32'd0)) const1 (.A(), .Y(y1));
  \\$lut #(.LUT(1'h1), .WIDTH(32'd0)) const2 (.A(), .Y(y2));
endmodule
""",
        encoding="utf-8",
    )
    return base


def _write_single_lut0_base(tmp_dir: Path, value: int) -> Path:
    """Write one LUT0 constant base design."""
    base = tmp_dir / "single_lut0_base.v"
    base.write_text(
        f"""
module base(output y);
  \\$lut #(.LUT(1'h{value}), .WIDTH(32'd0)) u_lut (.A(), .Y(y));
endmodule
""",
        encoding="utf-8",
    )
    return base


def _write_identity_lut_base(tmp_dir: Path) -> Path:
    """Write one one-input identity LUT base design."""
    base = tmp_dir / "identity_lut_base.v"
    base.write_text(
        """
module base(input a, output y);
  \\$lut #(.LUT(2'h2), .WIDTH(32'd1)) u_lut (.A(a), .Y(y));
endmodule
""",
        encoding="utf-8",
    )
    return base


def _write_const_config_tile(tmp_dir: Path) -> Path:
    """Write a config-controlled constant tile with two output polarities."""
    tile = tmp_dir / "const_config_tile.v"
    tile.write_text(
        """
module const_config_tile(input CFG, output O0, output O1);
  assign O0 = CFG;
  assign O1 = ~CFG;
endmodule
""",
        encoding="utf-8",
    )
    return tile


def _write_const_zero_tile(tmp_dir: Path) -> Path:
    """Write a tile that can only produce constant zero."""
    tile = tmp_dir / "const_zero_tile.v"
    tile.write_text(
        """
module const_zero_tile(output O);
  assign O = 1'b0;
endmodule
""",
        encoding="utf-8",
    )
    return tile


def _write_output_choice_tile(tmp_dir: Path) -> Path:
    """Write a tile with one wrong output, one right output, and one unused input."""
    tile = tmp_dir / "output_choice_tile.v"
    tile.write_text(
        """
module output_choice_tile(input I0, input I1, input UNUSED, output BAD, output GOOD);
  assign BAD = I0 ^ I1 ^ UNUSED;
  assign GOOD = I0 & I1;
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


def _write_frac_single_constant_base(tmp_dir: Path) -> Path:
    """Write a single-output constant fractional-LUT base design."""
    base = tmp_dir / "frac_single_constant_base.v"
    frac_model = FracLutBehavioralModel(
        name="__frac_lut",
        lut_size=4,
        num_shared_inputs=3,
    ).to_verilog()
    base.write_text(
        f"""
{frac_model}

module base(output y);
  __frac_lut #(
    .L0_INIT(16'hffff),
    .L1_INIT(16'h0000),
    .LUT_SIZE("4"),
    .NUM_SHARED_INPUTS("3"),
    .META_DATA("lut_mapping=single;lut_width=0;leftover_lut_width=4"),
    .SELECT_AS_DATA_USED(1'b0),
    .MUX_SELECT_CONFIG(1'b0)
  ) u_frac (
    .S(1'b0),
    .O0(y)
  );
endmodule
""",
        encoding="utf-8",
    )
    return base


def _write_frac_dual_constant_base(tmp_dir: Path) -> Path:
    """Write a dual-output constant fractional-LUT base design."""
    base = tmp_dir / "frac_dual_constant_base.v"
    frac_model = FracLutBehavioralModel(
        name="__frac_lut",
        lut_size=4,
        num_shared_inputs=3,
    ).to_verilog()
    base.write_text(
        f"""
{frac_model}

module base(output y0, output y1);
  __frac_lut #(
    .L0_INIT(16'hffff),
    .L1_INIT(16'h0000),
    .LUT_SIZE("4"),
    .NUM_SHARED_INPUTS("3"),
    .META_DATA("lut_mapping=dual;lut0_width=0;lut1_width=0"),
    .SELECT_AS_DATA_USED(1'b0),
    .MUX_SELECT_CONFIG(1'b0)
  ) u_frac (
    .S(1'b0),
    .O0(y0),
    .O1(y1)
  );
endmodule
""",
        encoding="utf-8",
    )
    return base


def _write_frac_mixed_lut4_constant_base(tmp_dir: Path) -> Path:
    """Write a mixed fractional LUT with one LUT4 and one constant side."""
    base = tmp_dir / "frac_mixed_lut4_constant_base.v"
    frac_model = FracLutBehavioralModel(
        name="__frac_lut",
        lut_size=4,
        num_shared_inputs=3,
    ).to_verilog()
    base.write_text(
        f"""
{frac_model}

module base(input a, input b, input c, input d, output y0, output y1);
  __frac_lut #(
    .L0_INIT(16'h8000),
    .L1_INIT(16'hffff),
    .LUT_SIZE("4"),
    .NUM_SHARED_INPUTS("3"),
    .META_DATA("lut_mapping=dual;lut0_width=4;lut1_width=0"),
    .SELECT_AS_DATA_USED(1'b0),
    .MUX_SELECT_CONFIG(1'b0)
  ) u_frac (
    .I0(a),
    .I1(b),
    .I2(c),
    .A0(d),
    .S(1'b0),
    .O0(y0),
    .O1(y1)
  );
endmodule
""",
        encoding="utf-8",
    )
    return base


def _write_mixed_frac_tile(tmp_dir: Path) -> Path:
    """Write a tile matching the mixed LUT4 plus constant FRAC behavior."""
    tile = tmp_dir / "mixed_frac_tile.v"
    tile.write_text(
        """
module mixed_frac_tile(input I0, input I1, input I2, input A0, output T0, output T1);
  assign T0 = I0 & I1 & I2 & A0;
  assign T1 = 1'b1;
endmodule
""",
        encoding="utf-8",
    )
    return tile


def _write_frac_same_outputs_base(tmp_dir: Path) -> Path:
    """Write a FRAC LUT whose two outputs are identical nonconstant functions."""
    base = tmp_dir / "frac_same_outputs_base.v"
    frac_model = FracLutBehavioralModel(
        name="__frac_lut",
        lut_size=2,
        num_shared_inputs=1,
    ).to_verilog()
    base.write_text(
        f"""
{frac_model}

module base(input a, input b, output y0, output y1);
  __frac_lut #(
    .L0_INIT(4'h8),
    .L1_INIT(4'h8),
    .LUT_SIZE("2"),
    .NUM_SHARED_INPUTS("1"),
    .META_DATA("lut_mapping=dual;lut0_width=2;lut1_width=2"),
    .SELECT_AS_DATA_USED(1'b0),
    .MUX_SELECT_CONFIG(1'b0)
  ) u_frac (
    .I0(a),
    .A0(b),
    .B0(b),
    .S(1'b0),
    .O0(y0),
    .O1(y1)
  );
endmodule
""",
        encoding="utf-8",
    )
    return base


def _write_single_and_output_tile(tmp_dir: Path) -> Path:
    """Write a tile with one output that can implement one AND function."""
    tile = tmp_dir / "single_and_output_tile.v"
    tile.write_text(
        """
module single_and_output_tile(input I0, input A0, output O);
  assign O = I0 & A0;
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
    test_cut_solver_lut0_constants()
    test_preconfigured_blif_removes_dead_sequential_path()
    test_preconfigured_verilog_config_bus_removes_dead_sequential_path()
    test_cut_solver_fixed_config_maps_combinational_side_of_seq_tile()
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
    test_morph_tile_pass_wires_fixed_config_bits()
    test_morph_tile_pass_replaces_lut0_constants_and_cache()
    test_morph_tile_pass_replaces_single_constant_frac_lut()
    test_morph_tile_pass_replaces_dual_constant_frac_lut()
    test_morph_tile_pass_replaces_mixed_frac_lut4_lut0()
    test_morph_tile_pass_constant_unsat_fails_without_crash()
    test_morph_tile_pass_duplicate_input_reuse_flag()
    test_morph_tile_pass_extra_inputs_and_output_choice()
    test_morph_tile_pass_disallows_output_reuse_for_multi_output()
    test_morph_tile_rejects_output_reuse_option()
    test_synthesizer_morph_tile_pass_smoke()
    test_morph_tile_multi_map_replaces_two_luts_eq()
    test_morph_tile_multi_map_wires_permuted_inputs_eq()
    test_morph_tile_multi_map_wires_exposed_internal_output_eq()
    test_morph_tile_multi_map_mixed_group_sizes_eq()
    test_morph_tile_multi_map_rejects_outputs_option()
    test_morph_tile_multi_map_local_selector_improves_greedy()
    test_morph_tile_multi_map_cp_sat_selector_looks_past_local_swap()
    test_morph_tile_multi_map_cp_sat_prefers_fewer_replacements_on_tie()
    test_morph_tile_multi_map_cp_sat_reports_selector_metadata()
    test_morph_tile_multi_map_report_shows_selector_and_stored_matches()
    test_morph_tile_multi_map_validates_luts_per_group_choices()
    test_morph_tile_multi_map_generates_multiple_group_sizes()
    test_morph_tile_multi_map_validates_pure_random_match()
    test_morph_tile_multi_map_validates_max_graph_hops()
    test_morph_tile_multi_map_max_graph_hops_reaches_far_partner()
    test_morph_tile_multi_map_rejects_cyclic_group_truth()
    test_morph_tile_multi_map_graph_growth_finds_cascade_group()
    test_morph_tile_multi_map_extracts_non_lut_output_use()
    test_morph_tile_multi_map_exposes_internal_net_with_non_lut_use()
    test_morph_tile_multi_map_rejects_extra_non_lut_output_when_not_allowed()
    test_morph_tile_multi_map_keeps_pure_internal_cascade_internal()
    test_morph_tile_multi_map_shared_input_fallback_keeps_unrelated_group()
    test_morph_tile_multi_map_wires_constant_input_route_eq()


if __name__ == "__main__":
    main()

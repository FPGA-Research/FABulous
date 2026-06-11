"""Ad-hoc tests for register absorption."""

from pathlib import Path
from tempfile import TemporaryDirectory

from fabulous.fabric_cad.fabxplore.pyosys.custom_passes.reg_absorber_pass import (
    RegAbsorberPass,
)
from fabulous.fabric_cad.fabxplore.pyosys.pyosys_bridge import PyosysBridge
from fabulous.fabulous_cli.helper import setup_logger

setup_logger(verbosity=0, debug=False)


def test_output_absorption_equiv() -> None:
    """Test output-side FF absorption preserves behavior."""
    with TemporaryDirectory(prefix="reg_abs_output_") as td:
        tmp_dir = Path(td)
        base = _write_output_base(tmp_dir)
        tile = _write_output_tile(tmp_dir)

        bridge = PyosysBridge(debug=False)
        bridge.read_verilog_paths([tile, base])
        bridge.run_pass("proc")
        result = RegAbsorberPass(
            cell_types=["seq_output_tile"],
            rules=[
                {
                    "side": "output",
                    "cell_type": "seq_output_tile",
                    "comb_port": "O",
                    "seq_port": "OQ",
                    "clock_port": "CLK",
                    "config": {"ConfigBits[0]": 1},
                    "attributes": {"FF_USED": 1},
                    "remove_disconnected_comb_port": True,
                }
            ],
            ff_ports={"$dff": {"clock": "CLK", "data": "D", "output": "Q"}},
            top_name="base",
            track_progress=False,
        )
        result.run_on(bridge)

        assert result.result_data is not None
        assert result.result_data.stats.output_absorptions == 1
        cells = bridge.to_netlist_dict()["modules"]["base"]["cells"]
        assert not _has_cell_type(cells, "$dff")
        assert "OQ" in cells["u_tile"]["connections"]
        assert "O" not in cells["u_tile"]["connections"]
        assert cells["u_tile"]["connections"]["ConfigBits"] == ["1"]
        assert int(cells["u_tile"]["attributes"]["FF_USED"], 2) == 1

        bridge.run_pass("hierarchy -top base -check")
        gate = tmp_dir / "gate_output.v"
        bridge.run_pass(f"write_verilog {gate}")
        _assert_equiv(base, gate, tile, "base")


def test_input_absorption_equiv() -> None:
    """Test input-side FF absorption preserves behavior."""
    with TemporaryDirectory(prefix="reg_abs_input_") as td:
        tmp_dir = Path(td)
        base = _write_input_base(tmp_dir)
        tile = _write_input_tile(tmp_dir)

        bridge = PyosysBridge(debug=False)
        bridge.read_verilog_paths([tile, base])
        bridge.run_pass("proc")
        result = RegAbsorberPass(
            cell_types=["seq_input_tile"],
            rules=[
                {
                    "side": "input",
                    "cell_type": "seq_input_tile",
                    "comb_port": "I",
                    "seq_port": "IQ",
                    "clock_port": "CLK",
                    "config": {"ConfigBits[0]": 1},
                    "remove_disconnected_comb_port": True,
                }
            ],
            ff_ports={"$dff": {"clock": "CLK", "data": "D", "output": "Q"}},
            top_name="base",
            track_progress=False,
        )
        result.run_on(bridge)

        assert result.result_data is not None
        assert result.result_data.stats.input_absorptions == 1
        cells = bridge.to_netlist_dict()["modules"]["base"]["cells"]
        assert not _has_cell_type(cells, "$dff")
        assert "IQ" in cells["u_tile"]["connections"]
        assert "I" not in cells["u_tile"]["connections"]

        bridge.run_pass("hierarchy -top base -check")
        gate = tmp_dir / "gate_input.v"
        bridge.run_pass(f"write_verilog {gate}")
        _assert_equiv(base, gate, tile, "base")


def test_same_port_output_absorption_keeps_port() -> None:
    """Test same comb/seq port absorption keeps the primitive port."""
    with TemporaryDirectory(prefix="reg_abs_same_port_") as td:
        tmp_dir = Path(td)
        base = _write_output_base(tmp_dir)
        tile = _write_same_output_tile(tmp_dir)

        bridge = PyosysBridge(debug=False)
        bridge.read_verilog_paths([tile, base])
        bridge.run_pass("proc")
        result = RegAbsorberPass(
            cell_types=["seq_output_tile"],
            rules=[
                {
                    "side": "output",
                    "cell_type": "seq_output_tile",
                    "comb_port": "O",
                    "seq_port": "O",
                    "clock_port": "CLK",
                    "config": {"ConfigBits[1]": 1},
                    "remove_disconnected_comb_port": True,
                }
            ],
            ff_ports={"$dff": {"clock": "CLK", "data": "D", "output": "Q"}},
            top_name="base",
            track_progress=False,
        )
        result.run_on(bridge)

        assert result.result_data is not None
        cells = bridge.to_netlist_dict()["modules"]["base"]["cells"]
        assert not _has_cell_type(cells, "$dff")
        assert "O" in cells["u_tile"]["connections"]
        assert cells["u_tile"]["connections"]["ConfigBits"] == ["1", "1"]

        bridge.run_pass("hierarchy -top base -check")


def test_extra_fanout_is_skipped_by_default() -> None:
    """Test ambiguous fanout is skipped when not allowed."""
    with TemporaryDirectory(prefix="reg_abs_fanout_") as td:
        tmp_dir = Path(td)
        base = _write_output_extra_fanout_base(tmp_dir)
        tile = _write_output_tile(tmp_dir)

        bridge = PyosysBridge(debug=False)
        bridge.read_verilog_paths([tile, base])
        bridge.run_pass("proc")
        result = RegAbsorberPass(
            cell_types=["seq_output_tile"],
            rules=[
                {
                    "side": "output",
                    "cell_type": "seq_output_tile",
                    "comb_port": "O",
                    "seq_port": "OQ",
                    "clock_port": "CLK",
                }
            ],
            ff_ports={"$dff": {"clock": "CLK", "data": "D", "output": "Q"}},
            top_name="base",
            track_progress=False,
        )
        result.run_on(bridge)

        assert result.result_data is not None
        assert result.result_data.stats.output_absorptions == 0
        assert result.result_data.stats.skipped_extra_fanout == 1
        cells = bridge.to_netlist_dict()["modules"]["base"]["cells"]
        assert _has_cell_type(cells, "$dff")


def test_clock_mismatch_is_skipped() -> None:
    """Test clock mismatches prevent absorption."""
    with TemporaryDirectory(prefix="reg_abs_clock_") as td:
        tmp_dir = Path(td)
        base = _write_clock_mismatch_base(tmp_dir)
        tile = _write_output_tile(tmp_dir)

        bridge = PyosysBridge(debug=False)
        bridge.read_verilog_paths([tile, base])
        bridge.run_pass("proc")
        result = RegAbsorberPass(
            cell_types=["seq_output_tile"],
            rules=[
                {
                    "side": "output",
                    "cell_type": "seq_output_tile",
                    "comb_port": "O",
                    "seq_port": "OQ",
                    "clock_port": "CLK",
                }
            ],
            ff_ports={"$dff": {"clock": "CLK", "data": "D", "output": "Q"}},
            top_name="base",
            track_progress=False,
        )
        result.run_on(bridge)

        assert result.result_data is not None
        assert result.result_data.stats.output_absorptions == 0
        assert result.result_data.stats.skipped_clock_mismatch == 1


def test_config_conflict_is_skipped() -> None:
    """Test conflicting planned config bits prevent shared absorption."""
    with TemporaryDirectory(prefix="reg_abs_cfg_") as td:
        tmp_dir = Path(td)
        base = _write_multi_output_base(tmp_dir)
        tile = _write_multi_output_tile(tmp_dir)

        bridge = PyosysBridge(debug=False)
        bridge.read_verilog_paths([tile, base])
        bridge.run_pass("proc")
        result = RegAbsorberPass(
            cell_types=["dual_seq_output_tile"],
            rules=[
                {
                    "side": "output",
                    "cell_type": "dual_seq_output_tile",
                    "comb_port": "O0",
                    "seq_port": "OQ0",
                    "clock_port": "CLK",
                    "config": {"ConfigBits[0]": 1},
                },
                {
                    "side": "output",
                    "cell_type": "dual_seq_output_tile",
                    "comb_port": "O1",
                    "seq_port": "OQ1",
                    "clock_port": "CLK",
                    "config": {"ConfigBits[0]": 0},
                },
            ],
            ff_ports={"$dff": {"clock": "CLK", "data": "D", "output": "Q"}},
            top_name="base",
            track_progress=False,
        )
        result.run_on(bridge)

        assert result.result_data is not None
        assert result.result_data.stats.output_absorptions == 1
        assert result.result_data.stats.skipped_config_conflict == 1


def test_multiple_output_absorptions_in_one_tile() -> None:
    """Test independent output rules can absorb two FFs in one primitive."""
    with TemporaryDirectory(prefix="reg_abs_multi_") as td:
        tmp_dir = Path(td)
        base = _write_multi_output_base(tmp_dir)
        tile = _write_multi_output_tile(tmp_dir)

        bridge = PyosysBridge(debug=False)
        bridge.read_verilog_paths([tile, base])
        bridge.run_pass("proc")
        result = RegAbsorberPass(
            cell_types=["dual_seq_output_tile"],
            rules=[
                {
                    "side": "output",
                    "cell_type": "dual_seq_output_tile",
                    "comb_port": "O0",
                    "seq_port": "OQ0",
                    "clock_port": "CLK",
                    "config": {"ConfigBits[0]": 1},
                },
                {
                    "side": "output",
                    "cell_type": "dual_seq_output_tile",
                    "comb_port": "O1",
                    "seq_port": "OQ1",
                    "clock_port": "CLK",
                    "config": {"ConfigBits[1]": 1},
                },
            ],
            ff_ports={"$dff": {"clock": "CLK", "data": "D", "output": "Q"}},
            top_name="base",
            track_progress=False,
        )
        result.run_on(bridge)

        assert result.result_data is not None
        assert result.result_data.stats.output_absorptions == 2
        cells = bridge.to_netlist_dict()["modules"]["base"]["cells"]
        assert not _has_cell_type(cells, "$dff")
        assert "OQ0" in cells["u_tile"]["connections"]
        assert "OQ1" in cells["u_tile"]["connections"]

        bridge.run_pass("hierarchy -top base -check")


def test_default_dffe_with_active_enable_is_absorbed() -> None:
    """Test default FF ports absorb an enabled Yosys $dffe."""
    with TemporaryDirectory(prefix="reg_abs_dffe_active_") as td:
        tmp_dir = Path(td)
        base = _write_dffe_base(tmp_dir, enable="1'b1")
        tile = _write_output_tile(tmp_dir)

        bridge = PyosysBridge(debug=False)
        bridge.read_verilog_paths([tile, base])
        bridge.run_pass("proc")
        result = RegAbsorberPass(
            cell_types=["seq_output_tile"],
            rules=[
                {
                    "side": "output",
                    "cell_type": "seq_output_tile",
                    "comb_port": "O",
                    "seq_port": "OQ",
                    "clock_port": "CLK",
                }
            ],
            top_name="base",
            track_progress=False,
        )
        result.run_on(bridge)

        assert result.result_data is not None
        assert result.result_data.stats.output_absorptions == 1
        cells = bridge.to_netlist_dict()["modules"]["base"]["cells"]
        assert not _has_cell_type(cells, "$dffe")


def test_default_dffe_with_variable_enable_is_skipped() -> None:
    """Test variable enabled Yosys $dffe is not absorbed by default."""
    with TemporaryDirectory(prefix="reg_abs_dffe_variable_") as td:
        tmp_dir = Path(td)
        base = _write_dffe_base(tmp_dir, enable="en", extra_input=", input en")
        tile = _write_output_tile(tmp_dir)

        bridge = PyosysBridge(debug=False)
        bridge.read_verilog_paths([tile, base])
        bridge.run_pass("proc")
        result = RegAbsorberPass(
            cell_types=["seq_output_tile"],
            rules=[
                {
                    "side": "output",
                    "cell_type": "seq_output_tile",
                    "comb_port": "O",
                    "seq_port": "OQ",
                    "clock_port": "CLK",
                }
            ],
            top_name="base",
            track_progress=False,
        )
        result.run_on(bridge)

        assert result.result_data is not None
        assert result.result_data.stats.output_absorptions == 0


def test_include_enable_ff_absorbs_variable_enable_without_wiring() -> None:
    """Test variable enabled FF can be structurally absorbed when allowed."""
    with TemporaryDirectory(prefix="reg_abs_dffe_structural_") as td:
        tmp_dir = Path(td)
        base = _write_dffe_base(tmp_dir, enable="en", extra_input=", input en")
        tile = _write_output_tile(tmp_dir)

        bridge = PyosysBridge(debug=False)
        bridge.read_verilog_paths([tile, base])
        bridge.run_pass("proc")
        result = RegAbsorberPass(
            cell_types=["seq_output_tile"],
            rules=[
                {
                    "side": "output",
                    "cell_type": "seq_output_tile",
                    "comb_port": "O",
                    "seq_port": "OQ",
                    "clock_port": "CLK",
                    "include_enable_ff": True,
                }
            ],
            top_name="base",
            track_progress=False,
        )
        result.run_on(bridge)

        assert result.result_data is not None
        assert result.result_data.stats.output_absorptions == 1
        cells = bridge.to_netlist_dict()["modules"]["base"]["cells"]
        assert not _has_cell_type(cells, "$dffe")
        assert "EN" not in cells["u_tile"]["connections"]


def test_include_enable_ff_wires_tile_enable_port() -> None:
    """Test variable enabled FF can wire its enable into the tile."""
    with TemporaryDirectory(prefix="reg_abs_dffe_wired_") as td:
        tmp_dir = Path(td)
        base = _write_dffe_base(tmp_dir, enable="en", extra_input=", input en")
        tile = _write_enable_output_tile(tmp_dir)

        bridge = PyosysBridge(debug=False)
        bridge.read_verilog_paths([tile, base])
        bridge.run_pass("proc")
        result = RegAbsorberPass(
            cell_types=["seq_output_tile"],
            rules=[
                {
                    "side": "output",
                    "cell_type": "seq_output_tile",
                    "comb_port": "O",
                    "seq_port": "OQ",
                    "clock_port": "CLK",
                    "include_enable_ff": True,
                    "enable_tile_port": "EN",
                    "enable_neutral": 1,
                }
            ],
            top_name="base",
            track_progress=False,
        )
        result.run_on(bridge)

        assert result.result_data is not None
        assert result.result_data.stats.output_absorptions == 1
        cells = bridge.to_netlist_dict()["modules"]["base"]["cells"]
        assert "EN" in cells["u_tile"]["connections"]


def test_include_reset_ff_wires_tile_reset_port() -> None:
    """Test variable sync-reset FF can wire its reset into the tile."""
    with TemporaryDirectory(prefix="reg_abs_sdff_wired_") as td:
        tmp_dir = Path(td)
        base = _write_sdff_base(tmp_dir)
        tile = _write_reset_output_tile(tmp_dir)

        bridge = PyosysBridge(debug=False)
        bridge.read_verilog_paths([tile, base])
        bridge.run_pass("proc")
        result = RegAbsorberPass(
            cell_types=["seq_output_tile"],
            rules=[
                {
                    "side": "output",
                    "cell_type": "seq_output_tile",
                    "comb_port": "O",
                    "seq_port": "OQ",
                    "clock_port": "CLK",
                    "include_reset_ff": True,
                    "reset_tile_port": "SR",
                    "reset_neutral": 0,
                    "reset_kind": "sync",
                    "reset_value": 0,
                }
            ],
            top_name="base",
            track_progress=False,
        )
        result.run_on(bridge)

        assert result.result_data is not None
        assert result.result_data.stats.output_absorptions == 1
        cells = bridge.to_netlist_dict()["modules"]["base"]["cells"]
        assert "SR" in cells["u_tile"]["connections"]


def test_reset_kind_mismatch_is_skipped() -> None:
    """Test async reset FF does not absorb into sync-reset rule."""
    with TemporaryDirectory(prefix="reg_abs_reset_kind_") as td:
        tmp_dir = Path(td)
        base = _write_adff_base(tmp_dir, reset_value=0)
        tile = _write_reset_output_tile(tmp_dir)

        bridge = PyosysBridge(debug=False)
        bridge.read_verilog_paths([tile, base])
        bridge.run_pass("proc")
        result = RegAbsorberPass(
            cell_types=["seq_output_tile"],
            rules=[
                {
                    "side": "output",
                    "cell_type": "seq_output_tile",
                    "comb_port": "O",
                    "seq_port": "OQ",
                    "clock_port": "CLK",
                    "include_reset_ff": True,
                    "reset_tile_port": "SR",
                    "reset_neutral": 0,
                    "reset_kind": "sync",
                    "reset_value": 0,
                }
            ],
            top_name="base",
            track_progress=False,
        )
        result.run_on(bridge)

        assert result.result_data is not None
        assert result.result_data.stats.output_absorptions == 0


def test_reset_value_mismatch_is_skipped() -> None:
    """Test reset-value mismatch prevents reset FF absorption."""
    with TemporaryDirectory(prefix="reg_abs_reset_value_") as td:
        tmp_dir = Path(td)
        base = _write_sdff_base(tmp_dir, reset_value=1)
        tile = _write_reset_output_tile(tmp_dir)

        bridge = PyosysBridge(debug=False)
        bridge.read_verilog_paths([tile, base])
        bridge.run_pass("proc")
        result = RegAbsorberPass(
            cell_types=["seq_output_tile"],
            rules=[
                {
                    "side": "output",
                    "cell_type": "seq_output_tile",
                    "comb_port": "O",
                    "seq_port": "OQ",
                    "clock_port": "CLK",
                    "include_reset_ff": True,
                    "reset_tile_port": "SR",
                    "reset_neutral": 0,
                    "reset_kind": "sync",
                    "reset_value": 0,
                }
            ],
            top_name="base",
            track_progress=False,
        )
        result.run_on(bridge)

        assert result.result_data is not None
        assert result.result_data.stats.output_absorptions == 0


def test_enable_polarity_constant_inactive_is_skipped() -> None:
    """Test constant inactive enable prevents default absorption."""
    with TemporaryDirectory(prefix="reg_abs_enable_pol_") as td:
        tmp_dir = Path(td)
        base = _write_dffe_base(
            tmp_dir,
            enable="1'b1",
            enable_polarity="1'b0",
        )
        tile = _write_output_tile(tmp_dir)

        bridge = PyosysBridge(debug=False)
        bridge.read_verilog_paths([tile, base])
        bridge.run_pass("proc")
        result = RegAbsorberPass(
            cell_types=["seq_output_tile"],
            rules=[
                {
                    "side": "output",
                    "cell_type": "seq_output_tile",
                    "comb_port": "O",
                    "seq_port": "OQ",
                    "clock_port": "CLK",
                }
            ],
            top_name="base",
            track_progress=False,
        )
        result.run_on(bridge)

        assert result.result_data is not None
        assert result.result_data.stats.output_absorptions == 0


def test_vector_dff_is_skipped() -> None:
    """Test vector FFs are skipped by the one-bit absorber."""
    with TemporaryDirectory(prefix="reg_abs_vector_") as td:
        tmp_dir = Path(td)
        base = _write_vector_dff_base(tmp_dir)
        tile = _write_output_tile(tmp_dir)

        bridge = PyosysBridge(debug=False)
        bridge.read_verilog_paths([tile, base])
        bridge.run_pass("proc")
        result = RegAbsorberPass(
            cell_types=["seq_output_tile"],
            rules=[
                {
                    "side": "output",
                    "cell_type": "seq_output_tile",
                    "comb_port": "O",
                    "seq_port": "OQ",
                    "clock_port": "CLK",
                }
            ],
            top_name="base",
            track_progress=False,
        )
        result.run_on(bridge)

        assert result.result_data is not None
        assert result.result_data.stats.output_absorptions == 0


def test_multi_clock_tile_absorbs_independent_output_ffs() -> None:
    """Test one tile can absorb two output FFs with distinct clocks."""
    with TemporaryDirectory(prefix="reg_abs_multi_clock_") as td:
        tmp_dir = Path(td)
        base = _write_multi_clock_output_base(tmp_dir)
        tile = _write_multi_clock_output_tile(tmp_dir)

        bridge = PyosysBridge(debug=False)
        bridge.read_verilog_paths([tile, base])
        bridge.run_pass("proc")
        result = RegAbsorberPass(
            cell_types=["multi_clock_tile"],
            rules=[
                {
                    "side": "output",
                    "cell_type": "multi_clock_tile",
                    "comb_port": "O0",
                    "seq_port": "Q0",
                    "clock_port": "CLK0",
                },
                {
                    "side": "output",
                    "cell_type": "multi_clock_tile",
                    "comb_port": "O1",
                    "seq_port": "Q1",
                    "clock_port": "CLK1",
                },
            ],
            ff_ports={"$dff": {"clock": "CLK", "data": "D", "output": "Q"}},
            top_name="base",
            track_progress=False,
        )
        result.run_on(bridge)

        assert result.result_data is not None
        assert result.result_data.stats.output_absorptions == 2
        cells = bridge.to_netlist_dict()["modules"]["base"]["cells"]
        assert not _has_cell_type(cells, "$dff")
        assert "CLK0" in cells["u_tile"]["connections"]
        assert "CLK1" in cells["u_tile"]["connections"]
        assert "Q0" in cells["u_tile"]["connections"]
        assert "Q1" in cells["u_tile"]["connections"]


def test_shared_clock_port_rejects_second_distinct_clock() -> None:
    """Test two different FF clocks cannot share one tile clock port."""
    with TemporaryDirectory(prefix="reg_abs_shared_clock_") as td:
        tmp_dir = Path(td)
        base = _write_multi_clock_output_base(tmp_dir, shared_tile_clock=True)
        tile = _write_multi_clock_output_tile(tmp_dir, shared_clock=True)

        bridge = PyosysBridge(debug=False)
        bridge.read_verilog_paths([tile, base])
        bridge.run_pass("proc")
        result = RegAbsorberPass(
            cell_types=["multi_clock_tile"],
            rules=[
                {
                    "side": "output",
                    "cell_type": "multi_clock_tile",
                    "comb_port": "O0",
                    "seq_port": "Q0",
                    "clock_port": "CLK",
                },
                {
                    "side": "output",
                    "cell_type": "multi_clock_tile",
                    "comb_port": "O1",
                    "seq_port": "Q1",
                    "clock_port": "CLK",
                },
            ],
            ff_ports={"$dff": {"clock": "CLK", "data": "D", "output": "Q"}},
            top_name="base",
            track_progress=False,
        )
        result.run_on(bridge)

        assert result.result_data is not None
        assert result.result_data.stats.output_absorptions == 1
        assert result.result_data.stats.skipped_clock_mismatch == 1


def test_multi_clock_input_and_output_absorption() -> None:
    """Test one tile can absorb input and output FFs on different clocks."""
    with TemporaryDirectory(prefix="reg_abs_inout_clock_") as td:
        tmp_dir = Path(td)
        base = _write_multi_clock_input_output_base(tmp_dir)
        tile = _write_multi_clock_input_output_tile(tmp_dir)

        bridge = PyosysBridge(debug=False)
        bridge.read_verilog_paths([tile, base])
        bridge.run_pass("proc")
        result = RegAbsorberPass(
            cell_types=["multi_clock_io_tile"],
            rules=[
                {
                    "side": "input",
                    "cell_type": "multi_clock_io_tile",
                    "comb_port": "I0",
                    "seq_port": "IQ0",
                    "clock_port": "CLKI",
                },
                {
                    "side": "output",
                    "cell_type": "multi_clock_io_tile",
                    "comb_port": "O0",
                    "seq_port": "Q0",
                    "clock_port": "CLKO",
                },
            ],
            ff_ports={"$dff": {"clock": "CLK", "data": "D", "output": "Q"}},
            top_name="base",
            track_progress=False,
        )
        result.run_on(bridge)

        assert result.result_data is not None
        assert result.result_data.stats.input_absorptions == 1
        assert result.result_data.stats.output_absorptions == 1
        cells = bridge.to_netlist_dict()["modules"]["base"]["cells"]
        assert not _has_cell_type(cells, "$dff")
        assert "CLKI" in cells["u_tile"]["connections"]
        assert "CLKO" in cells["u_tile"]["connections"]
        assert "IQ0" in cells["u_tile"]["connections"]
        assert "Q0" in cells["u_tile"]["connections"]


def test_rule_without_clock_port_does_not_wire_clock() -> None:
    """Test omitting clock_port still absorbs without touching tile clock."""
    with TemporaryDirectory(prefix="reg_abs_no_clock_") as td:
        tmp_dir = Path(td)
        base = _write_output_base(tmp_dir)
        tile = _write_output_tile(tmp_dir)

        bridge = PyosysBridge(debug=False)
        bridge.read_verilog_paths([tile, base])
        bridge.run_pass("proc")
        result = RegAbsorberPass(
            cell_types=["seq_output_tile"],
            rules=[
                {
                    "side": "output",
                    "cell_type": "seq_output_tile",
                    "comb_port": "O",
                    "seq_port": "OQ",
                }
            ],
            ff_ports={"$dff": {"clock": "CLK", "data": "D", "output": "Q"}},
            top_name="base",
            track_progress=False,
        )
        result.run_on(bridge)

        assert result.result_data is not None
        assert result.result_data.stats.output_absorptions == 1


def test_escaped_generated_cell_name_absorption() -> None:
    """Test absorption with a Yosys escaped generated-style instance name."""
    with TemporaryDirectory(prefix="reg_abs_escaped_") as td:
        tmp_dir = Path(td)
        base = _write_escaped_name_base(tmp_dir)
        tile = _write_output_tile(tmp_dir)

        bridge = PyosysBridge(debug=False)
        bridge.read_verilog_paths([tile, base])
        bridge.run_pass("proc")
        result = RegAbsorberPass(
            cell_types=["seq_output_tile"],
            rules=[
                {
                    "side": "output",
                    "cell_type": "seq_output_tile",
                    "comb_port": "O",
                    "seq_port": "OQ",
                    "clock_port": "CLK",
                }
            ],
            ff_ports={"$dff": {"clock": "CLK", "data": "D", "output": "Q"}},
            top_name="base",
            track_progress=False,
        )
        result.run_on(bridge)

        assert result.result_data is not None
        assert result.result_data.stats.output_absorptions == 1


def test_many_output_absorptions_use_indexed_planner_and_writer_eq() -> None:
    """Test many output absorptions preserve behavior through indexed paths."""
    width = 32
    with TemporaryDirectory(prefix="reg_abs_many_output_") as td:
        tmp_dir = Path(td)
        base = _write_many_output_base(tmp_dir, width=width)
        tile = _write_output_tile(tmp_dir)

        bridge = PyosysBridge(debug=False)
        bridge.read_verilog_paths([tile, base])
        bridge.run_pass("proc")
        result = RegAbsorberPass(
            cell_types=["seq_output_tile"],
            rules=[
                {
                    "side": "output",
                    "cell_type": "seq_output_tile",
                    "comb_port": "O",
                    "seq_port": "OQ",
                    "clock_port": "CLK",
                    "config": {"ConfigBits[0]": 1},
                    "remove_disconnected_comb_port": True,
                }
            ],
            ff_ports={"$dff": {"clock": "CLK", "data": "D", "output": "Q"}},
            top_name="base",
            track_progress=False,
        )
        result.run_on(bridge)

        assert result.result_data is not None
        assert result.result_data.stats.output_absorptions == width
        cells = bridge.to_netlist_dict()["modules"]["base"]["cells"]
        assert not _has_cell_type(cells, "$dff")

        bridge.run_pass("hierarchy -top base -check")
        gate = tmp_dir / "gate_many_output.v"
        bridge.run_pass(f"write_verilog {gate}")
        _assert_equiv(base, gate, tile, "base")


def _write_output_tile(tmp_dir: Path) -> Path:
    """Write a tile with separate combinational and sequential outputs."""
    path = tmp_dir / "seq_output_tile.v"
    path.write_text(
        """
module seq_output_tile(input CLK, input I, input [0:0] ConfigBits, output O, output OQ);
  reg q;
  assign O = I;
  assign OQ = q;
  always @(posedge CLK) q <= I;
endmodule
""",
        encoding="utf-8",
    )
    return path


def _write_enable_output_tile(tmp_dir: Path) -> Path:
    """Write a tile with an explicit enable input."""
    path = tmp_dir / "seq_output_tile.v"
    path.write_text(
        """
module seq_output_tile(
  input CLK,
  input EN,
  input I,
  input [0:0] ConfigBits,
  output O,
  output OQ
);
  reg q;
  assign O = I;
  assign OQ = q;
  always @(posedge CLK) if (EN) q <= I;
endmodule
""",
        encoding="utf-8",
    )
    return path


def _write_reset_output_tile(tmp_dir: Path) -> Path:
    """Write a tile with an explicit sync-reset input."""
    path = tmp_dir / "seq_output_tile.v"
    path.write_text(
        """
module seq_output_tile(
  input CLK,
  input SR,
  input I,
  input [0:0] ConfigBits,
  output O,
  output OQ
);
  reg q;
  assign O = I;
  assign OQ = q;
  always @(posedge CLK) begin
    if (SR) q <= 1'b0;
    else q <= I;
  end
endmodule
""",
        encoding="utf-8",
    )
    return path


def _write_same_output_tile(tmp_dir: Path) -> Path:
    """Write a tile whose output is selected by a config bit."""
    path = tmp_dir / "seq_output_tile.v"
    path.write_text(
        """
module seq_output_tile(input CLK, input I, input [1:0] ConfigBits, output O, output OQ);
  reg q;
  assign O = ConfigBits[1] ? q : I;
  assign OQ = q;
  always @(posedge CLK) q <= I;
endmodule
""",
        encoding="utf-8",
    )
    return path


def _write_input_tile(tmp_dir: Path) -> Path:
    """Write a tile with a sequential input path."""
    path = tmp_dir / "seq_input_tile.v"
    path.write_text(
        """
module seq_input_tile(input CLK, input I, input IQ, input [0:0] ConfigBits, output O);
  reg q;
  assign O = ConfigBits[0] ? q : I;
  always @(posedge CLK) q <= IQ;
endmodule
""",
        encoding="utf-8",
    )
    return path


def _write_multi_output_tile(tmp_dir: Path) -> Path:
    """Write a tile with two independent sequential outputs."""
    path = tmp_dir / "dual_seq_output_tile.v"
    path.write_text(
        """
module dual_seq_output_tile(
  input CLK,
  input I0,
  input I1,
  input [1:0] ConfigBits,
  output O0,
  output O1,
  output OQ0,
  output OQ1
);
  reg q0;
  reg q1;
  assign O0 = I0;
  assign O1 = I1;
  assign OQ0 = q0;
  assign OQ1 = q1;
  always @(posedge CLK) begin
    q0 <= I0;
    q1 <= I1;
  end
endmodule
""",
        encoding="utf-8",
    )
    return path


def _write_multi_clock_output_tile(
    tmp_dir: Path,
    shared_clock: bool = False,
) -> Path:
    """Write a tile with two registered outputs.

    Parameters
    ----------
    tmp_dir : Path
        Directory for the generated file.
    shared_clock : bool
        Whether both registers use one tile clock port.

    Returns
    -------
    Path
        Generated Verilog path.
    """
    path = tmp_dir / "multi_clock_tile.v"
    if shared_clock:
        ports = "input CLK"
        clocks = ("CLK", "CLK")
    else:
        ports = "input CLK0, input CLK1"
        clocks = ("CLK0", "CLK1")
    path.write_text(
        f"""
module multi_clock_tile(
  {ports},
  input I0,
  input I1,
  output O0,
  output O1,
  output Q0,
  output Q1
);
  reg q0;
  reg q1;
  assign O0 = I0;
  assign O1 = I1;
  assign Q0 = q0;
  assign Q1 = q1;
  always @(posedge {clocks[0]}) q0 <= I0;
  always @(posedge {clocks[1]}) q1 <= I1;
endmodule
""",
        encoding="utf-8",
    )
    return path


def _write_multi_clock_input_output_tile(tmp_dir: Path) -> Path:
    """Write a tile with one registered input and one registered output.

    Parameters
    ----------
    tmp_dir : Path
        Directory for the generated file.

    Returns
    -------
    Path
        Generated Verilog path.
    """
    path = tmp_dir / "multi_clock_io_tile.v"
    path.write_text(
        """
module multi_clock_io_tile(
  input CLKI,
  input CLKO,
  input I0,
  input IQ0,
  output O0,
  output Q0
);
  reg iq0;
  reg q0;
  assign O0 = iq0;
  assign Q0 = q0;
  always @(posedge CLKI) iq0 <= IQ0;
  always @(posedge CLKO) q0 <= iq0;
endmodule
""",
        encoding="utf-8",
    )
    return path


def _write_escaped_name_base(tmp_dir: Path) -> Path:
    """Write a base design with an escaped generated-style tile name.

    Parameters
    ----------
    tmp_dir : Path
        Directory for the generated file.

    Returns
    -------
    Path
        Generated Verilog path.
    """
    path = tmp_dir / "base_escaped.v"
    instance_name = (
        r"\$auto$alumacc.cc:512:replace_alu$16632.slice[0]"
        r".u_chain_add__morph_tile"
    )
    path.write_text(
        f"""
module base(input clock, input a, output reg y);
  wire comb;
  seq_output_tile {instance_name} (
    .CLK(clock),
    .I(a),
    .ConfigBits(1'b1),
    .O(comb)
  );
  always @(posedge clock) y <= comb;
endmodule
""",
        encoding="utf-8",
    )
    return path


def _write_multi_clock_output_base(
    tmp_dir: Path,
    shared_tile_clock: bool = False,
) -> Path:
    """Write a base with two output FFs on different clocks.

    Parameters
    ----------
    tmp_dir : Path
        Directory for the generated file.
    shared_tile_clock : bool
        Whether the tile instance has one clock port.

    Returns
    -------
    Path
        Generated Verilog path.
    """
    path = tmp_dir / "base_multi_clock.v"
    clock_ports = ".CLK(clk0)" if shared_tile_clock else ".CLK0(clk0),\n    .CLK1(clk1)"
    path.write_text(
        f"""
module base(input clk0, input clk1, input a, input b, output reg y0, output reg y1);
  wire o0;
  wire o1;
  multi_clock_tile u_tile(
    {clock_ports},
    .I0(a),
    .I1(b),
    .O0(o0),
    .O1(o1)
  );
  always @(posedge clk0) y0 <= o0;
  always @(posedge clk1) y1 <= o1;
endmodule
""",
        encoding="utf-8",
    )
    return path


def _write_multi_clock_input_output_base(tmp_dir: Path) -> Path:
    """Write a base with input and output FFs on different clocks.

    Parameters
    ----------
    tmp_dir : Path
        Directory for the generated file.

    Returns
    -------
    Path
        Generated Verilog path.
    """
    path = tmp_dir / "base_multi_clock_io.v"
    path.write_text(
        """
module base(input clki, input clko, input a, output reg y);
  reg in_q;
  wire o0;
  always @(posedge clki) in_q <= a;
  multi_clock_io_tile u_tile(.CLKI(clki), .CLKO(clko), .I0(in_q), .O0(o0));
  always @(posedge clko) y <= o0;
endmodule
""",
        encoding="utf-8",
    )
    return path


def _write_many_output_base(tmp_dir: Path, width: int) -> Path:
    """Write many independent output-side FF absorption opportunities.

    Parameters
    ----------
    tmp_dir : Path
        Directory for the generated file.
    width : int
        Number of independent tile/FF pairs to emit.

    Returns
    -------
    Path
        Generated Verilog path.
    """
    path = tmp_dir / "base_many_output.v"
    tile_lines = []
    ff_lines = []
    for index in range(width):
        tile_lines.append(
            f"""
  seq_output_tile u_tile_{index}(
    .CLK(clock),
    .I(a[{index}]),
    .ConfigBits(1'b1),
    .O(comb[{index}])
  );"""
        )
        ff_lines.append(
            f"""
  \\$dff #(
    .WIDTH(1),
    .CLK_POLARITY(1'b1)
  ) u_ff_{index} (
    .CLK(clock),
    .D(comb[{index}]),
    .Q(y[{index}])
  );"""
        )

    path.write_text(
        f"""
module base(input clock, input [{width - 1}:0] a, output [{width - 1}:0] y);
  wire [{width - 1}:0] comb;
{"".join(tile_lines)}
{"".join(ff_lines)}
endmodule
""",
        encoding="utf-8",
    )
    return path


def _write_dffe_base(
    tmp_dir: Path,
    enable: str,
    extra_input: str = "",
    enable_polarity: str = "1'b1",
) -> Path:
    """Write a base design with an explicit Yosys $dffe cell.

    Parameters
    ----------
    tmp_dir : Path
        Directory for the generated file.
    enable : str
        Verilog expression connected to ``EN``.
    extra_input : str
        Optional extra module input declaration.
    enable_polarity : str
        EN polarity parameter value.

    Returns
    -------
    Path
        Generated Verilog path.
    """
    path = tmp_dir / "base_dffe.v"
    path.write_text(
        f"""
module base(input clock, input a{extra_input}, output y);
  wire comb;
  seq_output_tile u_tile(.CLK(clock), .I(a), .ConfigBits(1'b1), .O(comb));
  \\$dffe #(
    .WIDTH(1),
    .CLK_POLARITY(1'b1),
    .EN_POLARITY({enable_polarity})
  ) u_ff (
    .CLK(clock),
    .EN({enable}),
    .D(comb),
    .Q(y)
  );
endmodule
""",
        encoding="utf-8",
    )
    return path


def _write_sdff_base(tmp_dir: Path, reset_value: int = 0) -> Path:
    """Write a base design with an explicit Yosys $sdff cell.

    Parameters
    ----------
    tmp_dir : Path
        Directory for the generated file.
    reset_value : int
        SRST_VALUE parameter.

    Returns
    -------
    Path
        Generated Verilog path.
    """
    path = tmp_dir / "base_sdff.v"
    path.write_text(
        f"""
module base(input clock, input rst, input a, output y);
  wire comb;
  seq_output_tile u_tile(.CLK(clock), .SR(1'b0), .I(a), .ConfigBits(1'b1), .O(comb));
  \\$sdff #(
    .WIDTH(1),
    .CLK_POLARITY(1'b1),
    .SRST_POLARITY(1'b1),
    .SRST_VALUE(1'b{reset_value})
  ) u_ff (
    .CLK(clock),
    .SRST(rst),
    .D(comb),
    .Q(y)
  );
endmodule
""",
        encoding="utf-8",
    )
    return path


def _write_adff_base(tmp_dir: Path, reset_value: int) -> Path:
    """Write a base design with an explicit Yosys $adff cell.

    Parameters
    ----------
    tmp_dir : Path
        Directory for the generated file.
    reset_value : int
        ARST_VALUE parameter.

    Returns
    -------
    Path
        Generated Verilog path.
    """
    path = tmp_dir / "base_adff.v"
    path.write_text(
        f"""
module base(input clock, input rst, input a, output y);
  wire comb;
  seq_output_tile u_tile(.CLK(clock), .SR(1'b0), .I(a), .ConfigBits(1'b1), .O(comb));
  \\$adff #(
    .WIDTH(1),
    .CLK_POLARITY(1'b1),
    .ARST_POLARITY(1'b1),
    .ARST_VALUE(1'b{reset_value})
  ) u_ff (
    .CLK(clock),
    .ARST(rst),
    .D(comb),
    .Q(y)
  );
endmodule
""",
        encoding="utf-8",
    )
    return path


def _write_vector_dff_base(tmp_dir: Path) -> Path:
    """Write a base design with a two-bit Yosys $dff cell.

    Parameters
    ----------
    tmp_dir : Path
        Directory for the generated file.

    Returns
    -------
    Path
        Generated Verilog path.
    """
    path = tmp_dir / "base_vector_dff.v"
    path.write_text(
        """
module base(input clock, input a, output [1:0] y);
  wire comb;
  seq_output_tile u_tile(.CLK(clock), .I(a), .ConfigBits(1'b1), .O(comb));
  \\$dff #(
    .WIDTH(2),
    .CLK_POLARITY(1'b1)
  ) u_ff (
    .CLK(clock),
    .D({a, comb}),
    .Q(y)
  );
endmodule
""",
        encoding="utf-8",
    )
    return path


def _write_output_base(tmp_dir: Path) -> Path:
    """Write an output-side absorption base design."""
    path = tmp_dir / "base_output.v"
    path.write_text(
        """
module base(input clock, input a, output reg y);
  wire comb;
  seq_output_tile u_tile(.CLK(clock), .I(a), .ConfigBits(1'b1), .O(comb));
  always @(posedge clock) y <= comb;
endmodule
""",
        encoding="utf-8",
    )
    return path


def _write_input_base(tmp_dir: Path) -> Path:
    """Write an input-side absorption base design."""
    path = tmp_dir / "base_input.v"
    path.write_text(
        """
module base(input clock, input a, output y);
  reg q;
  always @(posedge clock) q <= a;
  seq_input_tile u_tile(.CLK(clock), .I(q), .ConfigBits(1'b0), .O(y));
endmodule
""",
        encoding="utf-8",
    )
    return path


def _write_output_extra_fanout_base(tmp_dir: Path) -> Path:
    """Write a base design with extra combinational fanout."""
    path = tmp_dir / "base_fanout.v"
    path.write_text(
        """
module base(input clock, input a, output reg y, output z);
  wire comb;
  seq_output_tile u_tile(.CLK(clock), .I(a), .ConfigBits(1'b1), .O(comb));
  always @(posedge clock) y <= comb;
  assign z = comb;
endmodule
""",
        encoding="utf-8",
    )
    return path


def _write_clock_mismatch_base(tmp_dir: Path) -> Path:
    """Write a base design whose tile and FF clocks differ."""
    path = tmp_dir / "base_clock.v"
    path.write_text(
        """
module base(input clock0, input clock1, input a, output reg y);
  wire comb;
  seq_output_tile u_tile(.CLK(clock0), .I(a), .ConfigBits(1'b1), .O(comb));
  always @(posedge clock1) y <= comb;
endmodule
""",
        encoding="utf-8",
    )
    return path


def _write_multi_output_base(tmp_dir: Path) -> Path:
    """Write a base design with two absorbable FFs on one primitive."""
    path = tmp_dir / "base_multi.v"
    path.write_text(
        """
module base(input clock, input a, input b, output reg y0, output reg y1);
  wire o0;
  wire o1;
  dual_seq_output_tile u_tile(
    .CLK(clock),
    .I0(a),
    .I1(b),
    .ConfigBits(2'b11),
    .O0(o0),
    .O1(o1)
  );
  always @(posedge clock) begin
    y0 <= o0;
    y1 <= o1;
  end
endmodule
""",
        encoding="utf-8",
    )
    return path


def _assert_equiv(
    gold: Path,
    gate: Path,
    tile: Path,
    top_name: str,
) -> None:
    """Run a Yosys equivalence check.

    Parameters
    ----------
    gold : Path
        Original design.
    gate : Path
        Rewritten design.
    tile : Path
        Tile model.
    top_name : str
        Top module name.
    """
    equiv = PyosysBridge(debug=False)
    equiv.read_verilog_paths([tile, gold])
    equiv.run_pass("proc")
    equiv.run_pass(f"rename {top_name} {top_name}_gold")
    equiv.run_pass(f"read_verilog -overwrite {gate}")
    equiv.run_pass("proc")
    equiv.run_pass(f"rename {top_name} {top_name}_gate")
    equiv.run_pass(f"equiv_make {top_name}_gold {top_name}_gate equiv")
    equiv.run_pass("hierarchy -top equiv")
    equiv.run_pass("flatten")
    equiv.run_pass("techmap")
    equiv.run_pass("opt_clean")
    equiv.run_pass("equiv_simple -undef")
    equiv.run_pass("equiv_induct -undef")
    equiv.run_pass("equiv_status -assert")


def _has_cell_type(cells: dict[str, dict[str, object]], cell_type: str) -> bool:
    """Return whether a netlist dictionary contains a cell type.

    Parameters
    ----------
    cells : dict[str, dict[str, object]]
        JSON-style cell dictionary.
    cell_type : str
        Cell type to find.

    Returns
    -------
    bool
        ``True`` if any cell has the requested type.
    """
    return any(cell.get("type") == cell_type for cell in cells.values())


def main() -> None:
    """Run all reg-absorber tests."""
    test_output_absorption_equiv()
    test_input_absorption_equiv()
    test_same_port_output_absorption_keeps_port()
    test_extra_fanout_is_skipped_by_default()
    test_clock_mismatch_is_skipped()
    test_config_conflict_is_skipped()
    test_multiple_output_absorptions_in_one_tile()
    test_default_dffe_with_active_enable_is_absorbed()
    test_default_dffe_with_variable_enable_is_skipped()
    test_include_enable_ff_absorbs_variable_enable_without_wiring()
    test_include_enable_ff_wires_tile_enable_port()
    test_include_reset_ff_wires_tile_reset_port()
    test_reset_kind_mismatch_is_skipped()
    test_reset_value_mismatch_is_skipped()
    test_enable_polarity_constant_inactive_is_skipped()
    test_vector_dff_is_skipped()
    test_multi_clock_tile_absorbs_independent_output_ffs()
    test_shared_clock_port_rejects_second_distinct_clock()
    test_multi_clock_input_and_output_absorption()
    test_rule_without_clock_port_does_not_wire_clock()
    test_escaped_generated_cell_name_absorption()
    test_many_output_absorptions_use_indexed_planner_and_writer_eq()


if __name__ == "__main__":
    main()

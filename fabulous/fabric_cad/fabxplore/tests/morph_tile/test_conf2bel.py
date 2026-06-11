"""Tests for FABulous config-bit to BEL-parameter conversion."""

from __future__ import annotations

import tempfile
from pathlib import Path

import pyosys.libyosys as ys
import pytest  # deptry: ignore[DEP004]

from fabulous.fabric_cad.fabxplore.pyosys.pyosys_bridge import PyosysBridge
from fabulous.fabric_cad.fabxplore.utils.conf2bel import (
    CLK_PORT,
    Conf2BelModel,
    apply_conf2bel_to_design,
    derive_conf2bel_from_verilog,
    normalize_belmap_feature,
)


def test_normalize_belmap_feature() -> None:
    """Check FABulous-style feature normalization, including edge cases."""
    assert normalize_belmap_feature("INIT0_11") == "INIT0[11]"
    assert normalize_belmap_feature("INIT0_0") == "INIT0[0]"
    assert normalize_belmap_feature("MODE") == "MODE"
    assert normalize_belmap_feature("MODE_fast") == "MODE_fast"
    assert normalize_belmap_feature("A_B_12") == "A_B[12]"


def test_derive_conf2bel_from_verilog_groups_attributes() -> None:
    """Derive grouped parameters and remove GLOBAL ports from the blackbox."""
    with tempfile.TemporaryDirectory() as tmpdir:
        bel_path = Path(tmpdir) / "tiny_bel.v"
        bel_path.write_text(_tiny_bel_verilog(), encoding="utf-8")

        model = derive_conf2bel_from_verilog(bel_path)

    assert model.module_name == "tiny_bel"
    assert model.config_ports == {"Cfg": 5}
    assert set(model.parameters) == {"INIT0", "CFG", "MODE"}
    assert model.parameters["INIT0"].width == 2
    assert model.parameters["INIT0"].config_to_parameter_bits == {0: 0, 1: 1}
    assert model.parameters["CFG"].config_to_parameter_bits == {2: 0, 3: 1}
    assert model.parameters["MODE"].config_to_parameter_bits == {4: 0}
    assert "Cfg" not in model.blackbox_verilog
    assert "parameter [1:0] INIT0 = 2'b00" in model.blackbox_verilog

    module = next(iter(model.blackbox_bridge.design.modules_.values()))
    wire_names = {str(wire.name).removeprefix("\\") for wire in module.wires_.values()}
    assert "Cfg" not in wire_names
    assert module.parameter_default_values[ys.IdString("\\INIT0")].as_int() == 0


def test_apply_conf2bel_to_design_sets_params_and_removes_config_port() -> None:
    """Map constant config vectors onto BEL parameters in an active design."""
    model = _derive_tiny_model()
    bridge = PyosysBridge()
    bridge.read_verilog_string(
        """
module tiny_bel(input I, output O, input [4:0] Cfg);
endmodule

module top(input I, output O);
  tiny_bel u0 (.I(I), .O(O), .Cfg(5'b10110));
endmodule
""",
        replace_design=True,
    )

    apply_conf2bel_to_design(bridge, model)

    cell = _only_top_cell(bridge)
    assert not cell.hasPort(ys.IdString("\\Cfg"))
    assert cell.getParam(ys.IdString("\\INIT0")).as_int() == 2
    assert cell.getParam(ys.IdString("\\CFG")).as_int() == 1
    assert cell.getParam(ys.IdString("\\MODE")).as_int() == 1


def test_conf2bel_renames_userclk_to_configured_clock_port() -> None:
    """Rename FABulous UserCLK to the configured routing-model clock port."""
    with tempfile.TemporaryDirectory() as tmpdir:
        bel_path = Path(tmpdir) / "clocked_bel.v"
        bel_path.write_text(_clocked_bel_verilog(), encoding="utf-8")
        model = derive_conf2bel_from_verilog(bel_path)

    assert f"input {CLK_PORT}" in model.blackbox_verilog
    if CLK_PORT != "UserCLK":
        assert "UserCLK" not in model.blackbox_verilog

    bridge = PyosysBridge()
    bridge.read_verilog_string(
        """
module clocked_bel(input I, input UserCLK, output O, input [0:0] Cfg);
endmodule

module top(input I, input clk, output O);
  clocked_bel u0 (.I(I), .UserCLK(clk), .O(O), .Cfg(1'b1));
endmodule
""",
        replace_design=True,
    )

    apply_conf2bel_to_design(bridge, model)

    cell = _only_top_cell(bridge)
    assert cell.hasPort(ys.IdString(f"\\{CLK_PORT}"))
    if CLK_PORT != "UserCLK":
        assert not cell.hasPort(ys.IdString("\\UserCLK"))


def test_apply_conf2bel_skips_already_converted_cells() -> None:
    """Skip matching BEL cells when no config carrier port remains."""
    model = _derive_tiny_model()
    bridge = PyosysBridge()
    bridge.read_verilog_string(
        """
module tiny_bel #(parameter [1:0] INIT0 = 2'b10, parameter [1:0] CFG = 2'b01,
                  parameter MODE = 1'b1)(input I, output O);
endmodule

module top(input I, output O);
  tiny_bel #(.INIT0(2'b10), .CFG(2'b01), .MODE(1'b1)) u0 (.I(I), .O(O));
endmodule
""",
        replace_design=True,
    )

    apply_conf2bel_to_design(bridge, model)

    cell = _only_top_cell(bridge)
    assert not cell.hasPort(ys.IdString("\\Cfg"))
    assert cell.getParam(ys.IdString("\\INIT0")).as_int() == 2
    assert cell.getParam(ys.IdString("\\CFG")).as_int() == 1
    assert cell.getParam(ys.IdString("\\MODE")).as_int() == 1


def test_apply_conf2bel_rejects_partial_config_ports() -> None:
    """Reject cells that still have only part of their config carrier ports."""
    model = _derive_multi_config_model()
    bridge = PyosysBridge()
    bridge.read_verilog_string(
        """
module multi_config_bel(input I, output O, input [1:0] CfgA);
endmodule

module top(input I, output O);
  multi_config_bel u0 (.I(I), .O(O), .CfgA(2'b10));
endmodule
""",
        replace_design=True,
    )

    with pytest.raises(ValueError, match="CfgB"):
        apply_conf2bel_to_design(bridge, model)


def test_apply_conf2bel_rejects_non_constant_config_bits() -> None:
    """Reject cells whose config carrier is still connected to logic."""
    model = _derive_tiny_model()
    bridge = PyosysBridge()
    bridge.read_verilog_string(
        """
module tiny_bel(input I, output O, input [4:0] Cfg);
endmodule

module top(input I, input [4:0] Cfg, output O);
  tiny_bel u0 (.I(I), .O(O), .Cfg(Cfg));
endmodule
""",
        replace_design=True,
    )

    with pytest.raises(ValueError, match="constant config bits"):
        apply_conf2bel_to_design(bridge, model)


def test_derive_conf2bel_rejects_sparse_belmap_indices() -> None:
    """Reject BelMap attributes with missing config-vector indices."""
    with tempfile.TemporaryDirectory() as tmpdir:
        bel_path = Path(tmpdir) / "bad_bel.v"
        bel_path.write_text(
            """
(* FABulous, BelMap, INIT0_0=0, INIT0_1=2 *)
module bad_bel(input I, output O, (* FABulous, GLOBAL *) input [2:0] Cfg);
  assign O = I;
endmodule
""",
            encoding="utf-8",
        )

        with pytest.raises(ValueError, match="contiguous"):
            derive_conf2bel_from_verilog(bel_path)


def main() -> None:
    """Execute the self-contained conf2bel tests."""
    tests = [
        test_normalize_belmap_feature,
        test_derive_conf2bel_from_verilog_groups_attributes,
        test_apply_conf2bel_to_design_sets_params_and_removes_config_port,
        test_conf2bel_renames_userclk_to_configured_clock_port,
        test_apply_conf2bel_skips_already_converted_cells,
        test_apply_conf2bel_rejects_partial_config_ports,
        test_apply_conf2bel_rejects_non_constant_config_bits,
        test_derive_conf2bel_rejects_sparse_belmap_indices,
    ]
    for test in tests:
        test()


def _derive_tiny_model() -> Conf2BelModel:
    with tempfile.TemporaryDirectory() as tmpdir:
        bel_path = Path(tmpdir) / "tiny_bel.v"
        bel_path.write_text(_tiny_bel_verilog(), encoding="utf-8")
        return derive_conf2bel_from_verilog(bel_path)


def _derive_multi_config_model() -> Conf2BelModel:
    with tempfile.TemporaryDirectory() as tmpdir:
        bel_path = Path(tmpdir) / "multi_config_bel.v"
        bel_path.write_text(
            """
(* FABulous, BelMap, CFG_0=0, CFG_1=1, CFG_2=2 *)
module multi_config_bel(
  input I,
  output O,
  (* FABulous, GLOBAL *) input [1:0] CfgA,
  (* FABulous, GLOBAL *) input [0:0] CfgB
);
  assign O = I;
endmodule
""",
            encoding="utf-8",
        )
        return derive_conf2bel_from_verilog(bel_path)


def _only_top_cell(bridge: PyosysBridge) -> ys.Cell:
    top = [
        module
        for module in bridge.design.modules_.values()
        if str(module.name).removeprefix("\\") == "top"
    ][0]
    return next(iter(top.cells_.values()))


def _tiny_bel_verilog() -> str:
    return """
(* FABulous, BelMap, INIT0_0=0, INIT0_1=1, CFG_0=2, CFG_1=3, MODE=4 *)
module tiny_bel(input I, output O, (* FABulous, GLOBAL *) input [4:0] Cfg);
  assign O = I;
endmodule
"""


def _clocked_bel_verilog() -> str:
    return """
(* FABulous, BelMap, MODE=0 *)
module clocked_bel(
  input I,
  (* FABulous, EXTERNAL, SHARED_PORT *) input UserCLK,
  output O,
  (* FABulous, GLOBAL *) input [0:0] Cfg
);
  assign O = I;
endmodule
"""


if __name__ == "__main__":
    main()

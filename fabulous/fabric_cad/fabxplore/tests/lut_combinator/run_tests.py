"""Ad-hoc tests."""

import re
import tempfile
from pathlib import Path

from loguru import logger

from fabulous.fabric_cad.fabxplore.modules.lut_combinator.core.combinator import (
    FracLutArchitecture,
    LutCombinator,
    LutCombinatorConfig,
)
from fabulous.fabric_cad.fabxplore.modules.lut_combinator.core.models import (
    LogicalLutCell,
    LutSpec,
    MatchingMode,
)
from fabulous.fabric_cad.fabxplore.modules.lut_combinator.utils.equiv_checker import (
    EquivalenceCheckConfig,
    LutEquivalenceChecker,
)
from fabulous.fabric_cad.fabxplore.pyosys.pyosys_bridge import PyosysBridge
from fabulous.fabulous_cli.helper import (
    setup_logger,
)

ROOT = Path(__file__).resolve().parents[2]
OUT_DIR = ROOT / "tests" / "lut_combinator" / "out"
setup_logger(verbosity=0, debug=False)


def _named_lut_spec() -> LutSpec:
    """Return the LUT spec used by simple named-LUT benchmarks."""
    return LutSpec(
        lut_re=re.compile(r"^LUT(\d+)$"),
        init_name="INIT",
        input_re=re.compile(r"^I\d+$"),
        output_ports=frozenset({"O", "Q", "Y"}),
    )


def test_lut_32_mix_benchmark_eq(
    fls: int, ns: int, passthrough: bool, mode: MatchingMode
) -> None:
    """Test mapping and equivalence checking of a LUT32-mixed benchmark."""
    benchmark_verilog = ROOT / "benchmarks" / "lut_mapped_simple" / "lut32_mixed.v"
    out_dir = OUT_DIR
    out_dir.mkdir(parents=True, exist_ok=True)
    logger.info("Mapping a LUT32-mixed benchmark with FRAC_LUT5 architecture")
    frac_arch = FracLutArchitecture(
        frac_lut_size=fls,
        num_shared_inputs=ns,
        name="FRAC_LUT5",
    )
    cfg = LutCombinatorConfig(
        architecture=frac_arch,
        top_name="lut32_mixed",
        lut_spec=_named_lut_spec(),
        passthrough=passthrough,
        mode=mode,
    )

    comb = LutCombinator(cfg)
    bridge: PyosysBridge = PyosysBridge(debug=False)
    bridge.read_verilog_paths([benchmark_verilog])
    comb.map_from_design(bridge, inplace=True)
    bridge.write_verilog_path(out_dir / "lut32_mixed_mapped.v")
    comb.write_report(out_dir / "lut32_mixed_report.txt")

    eq_cfg = EquivalenceCheckConfig(
        gold_verilog=benchmark_verilog,
        gate_verilog=out_dir / "lut32_mixed_mapped.v",
        top_name="lut32_mixed",
        frac_cell_name=frac_arch.name,
        frac_lut_size=frac_arch.frac_lut_size,
        num_shared_inputs=frac_arch.num_shared_inputs,
    )
    LutEquivalenceChecker(eq_cfg).run()

    logger.info(
        "Test passed: LUT32-mixed benchmark mapped successfully "
        "with FRAC_LUT5 architecture."
    )


def test_lut_32_mix_benchmark_eq_iterative() -> None:
    """Test mapping and equivalence checking of a LUT32-mixed benchmark iteratively."""
    for fls in [4, 5, 6]:
        for ns in [2, 3, 4]:
            for passthrough in [False, True]:
                for mode in [MatchingMode.MAX_WEIGHT, MatchingMode.MAXIMAL]:
                    test_lut_32_mix_benchmark_eq(fls, ns, passthrough, mode)
    logger.info("All LUT32-mixed benchmark tests passed.")


def test_two_lut_plus_bad_unknown_benchmark_eq(
    fls: int, ns: int, passthrough: bool, mode: MatchingMode
) -> None:
    """Test mapping and equivalence checking of a two_lut_plus_bad_unknown benchmark."""
    benchmark_verilog = (
        ROOT / "benchmarks" / "lut_mapped_simple" / "two_lut_plus_bad_unknown.v"
    )
    out_dir = OUT_DIR
    out_dir.mkdir(parents=True, exist_ok=True)
    logger.info(
        "Mapping a two_lut_plus_bad_unknown benchmark with FRAC_LUT5 architecture"
    )
    frac_arch = FracLutArchitecture(
        frac_lut_size=fls,
        num_shared_inputs=ns,
        name="FRAC_LUT5",
    )
    cfg = LutCombinatorConfig(
        architecture=frac_arch,
        top_name="two_lut_plus_bad_unknown",
        lut_spec=_named_lut_spec(),
        passthrough=passthrough,
        mode=mode,
    )

    comb = LutCombinator(cfg)
    bridge: PyosysBridge = PyosysBridge(debug=False)
    bridge.read_verilog_paths([benchmark_verilog])
    comb.map_from_design(bridge, inplace=True)
    bridge.write_verilog_path(out_dir / "two_lut_plus_bad_unknown_mapped.v")
    comb.write_report(out_dir / "two_lut_plus_bad_unknown_report.txt")

    eq_cfg = EquivalenceCheckConfig(
        gold_verilog=benchmark_verilog,
        gate_verilog=out_dir / "two_lut_plus_bad_unknown_mapped.v",
        top_name="two_lut_plus_bad_unknown",
        frac_cell_name=frac_arch.name,
        frac_lut_size=frac_arch.frac_lut_size,
        num_shared_inputs=frac_arch.num_shared_inputs,
    )
    LutEquivalenceChecker(eq_cfg).run()

    logger.info(
        "Test passed: two_lut_plus_bad_unknown benchmark mapped "
        "successfully with FRAC_LUT5 architecture."
    )


def test_two_lut_plus_bad_unknown_benchmark_eq_iterative() -> None:
    """Test mapping and equivalence checking of this benchmark iteratively."""
    for fls in [4, 5, 6]:
        for ns in [2, 3, 4]:
            for passthrough in [False, True]:
                for mode in [MatchingMode.MAX_WEIGHT, MatchingMode.MAXIMAL]:
                    test_two_lut_plus_bad_unknown_benchmark_eq(
                        fls, ns, passthrough, mode
                    )
    logger.info("All two_lut_plus_bad_unknown benchmark tests passed.")


def test_enet_benchmark(
    fls: int, ns: int, passthrough: bool, mode: MatchingMode
) -> None:
    """Test mapping and equivalence checking of an ENET benchmark."""
    benchmark_verilog = ROOT / "benchmarks" / "lut_mapped_complex" / "enet" / "netl.v"
    out_dir = OUT_DIR
    out_dir.mkdir(parents=True, exist_ok=True)
    logger.info("Mapping an ENET benchmark with FRAC_LUT5 architecture")
    frac_arch = FracLutArchitecture(
        frac_lut_size=fls,
        num_shared_inputs=ns,
        name="FRAC_LUT5",
    )
    cfg = LutCombinatorConfig(
        architecture=frac_arch,
        top_name="enet",
        lut_spec=_named_lut_spec(),
        passthrough=passthrough,
        mode=mode,
        debug=False,
    )

    comb = LutCombinator(cfg)
    bridge: PyosysBridge = PyosysBridge(debug=False)
    bridge.read_verilog_paths([benchmark_verilog])
    comb.map_from_design(bridge, inplace=True)
    bridge.write_verilog_path(out_dir / "enet_mapped.v")
    comb.write_report(out_dir / "enet_report.txt")

    logger.info(
        "Test passed: ENET benchmark mapped successfully with FRAC_LUT5 architecture."
    )


def test_enet_benchmark_manual() -> None:
    """Test mapping and equivalence checking of an ENET benchmark."""
    test_enet_benchmark(
        fls=4,
        ns=3,
        passthrough=False,
        mode=MatchingMode.MAX_WEIGHT,
    )

    logger.info("ENET benchmark test passed.")


def test_lut_32_mixed_yosys_lut_benchmark_eq(
    fls: int, ns: int, passthrough: bool, mode: MatchingMode
) -> None:
    """Test mapping and equivalence checking of a LUT32-mixed benchmark."""
    benchmark_verilog = (
        ROOT / "benchmarks" / "lut_mapped_simple" / "lut32_mixed_yosys_lut.v"
    )
    out_dir = OUT_DIR
    out_dir.mkdir(parents=True, exist_ok=True)
    logger.info("Mapping a LUT32-mixed benchmark with FRAC_LUT5 architecture")
    frac_arch = FracLutArchitecture(
        frac_lut_size=fls,
        num_shared_inputs=ns,
        name="FRAC_LUT5",
        use_select_as_data_in_pair_mode=True,
    )
    cfg = LutCombinatorConfig(
        architecture=frac_arch,
        top_name="lut32_mixed",
        lut_spec=LutSpec(
            lut_re=re.compile(r"^\$lut$"),
            init_name="LUT",
            input_re=re.compile(r"^A\d+$"),
            output_ports=frozenset({"O", "Q", "Y"}),
        ),
        passthrough=passthrough,
        mode=mode,
    )

    comb = LutCombinator(cfg)
    bridge: PyosysBridge = PyosysBridge(debug=True)
    bridge.read_verilog_paths([benchmark_verilog])
    comb.map_from_design(bridge, inplace=True)
    bridge.write_verilog_path(out_dir / "lut32_mixed_mapped_yosys_lut.v")
    comb.write_report(out_dir / "lut32_mixed_report_yosys_lut.txt")

    eq_cfg = EquivalenceCheckConfig(
        gold_verilog=benchmark_verilog,
        gate_verilog=out_dir / "lut32_mixed_mapped_yosys_lut.v",
        top_name="lut32_mixed",
        frac_cell_name=frac_arch.name,
        frac_lut_size=frac_arch.frac_lut_size,
        num_shared_inputs=frac_arch.num_shared_inputs,
    )
    LutEquivalenceChecker(eq_cfg).run()

    logger.info(
        "Test passed: LUT32-mixed benchmark mapped successfully "
        "with FRAC_LUT5 architecture."
    )


def test_lut_32_mixed_yosys_lut_benchmark_eq_iterative() -> None:
    """Test mapping and equivalence checking of a LUT32-mixed benchmark iteratively."""
    for fls in [4, 5, 6]:
        for ns in [2, 3, 4]:
            for passthrough in [False, True]:
                for mode in [MatchingMode.MAX_WEIGHT, MatchingMode.MAXIMAL]:
                    test_lut_32_mixed_yosys_lut_benchmark_eq(fls, ns, passthrough, mode)
    logger.info("All LUT32-mixed benchmark tests passed.")


def test_select_as_data_pair_mapping_eq() -> None:
    """Test that select-as-data mode packs a pair normal mode cannot pack."""
    benchmark_text = """
module select_as_data_pair(
    input a, b, c, d, e, f,
    output y0, y1
);
  LUT4 #(.INIT(16'h6996)) lut0 (
    .I0(a), .I1(b), .I2(c), .I3(d), .O(y0)
  );
  LUT4 #(.INIT(16'he8e8)) lut1 (
    .I0(a), .I1(b), .I2(e), .I3(f), .O(y1)
  );
endmodule
"""
    with tempfile.TemporaryDirectory(prefix="lut_select_as_data_") as td:
        tmp_dir = Path(td)
        gold = tmp_dir / "select_as_data_pair.v"
        gate = tmp_dir / "select_as_data_pair_mapped.v"
        gold.write_text(benchmark_text, encoding="utf-8")

        normal_arch = FracLutArchitecture(
            frac_lut_size=4,
            num_shared_inputs=3,
            name="FRAC_LUT5",
        )
        normal_cfg = LutCombinatorConfig(
            architecture=normal_arch,
            top_name="select_as_data_pair",
            lut_spec=_named_lut_spec(),
            passthrough=False,
            mode=MatchingMode.MAX_WEIGHT,
        )
        normal_comb = LutCombinator(normal_cfg)
        normal_bridge = PyosysBridge(debug=False)
        normal_bridge.read_verilog_paths([gold])
        normal_result = normal_comb.map_from_design(normal_bridge, inplace=False)
        assert normal_result.stats.mapped_groups == 0

        select_arch = FracLutArchitecture(
            frac_lut_size=4,
            num_shared_inputs=3,
            name="FRAC_LUT5",
            use_select_as_data_in_pair_mode=True,
        )
        select_cfg = LutCombinatorConfig(
            architecture=select_arch,
            top_name="select_as_data_pair",
            lut_spec=_named_lut_spec(),
            passthrough=False,
            mode=MatchingMode.MAX_WEIGHT,
        )
        select_comb = LutCombinator(select_cfg)
        select_bridge = PyosysBridge(debug=False)
        select_bridge.read_verilog_paths([gold])
        select_result = select_comb.map_from_design(select_bridge, inplace=True)
        assert select_result.stats.mapped_groups == 1
        assert select_result.stats.passthrough_luts == 0

        mapped_cell = select_result.mapped_cells[0]
        assert mapped_cell.parameters["SELECT_AS_DATA_CAPABLE"] == "1"
        assert mapped_cell.parameters["SELECT_AS_DATA_USED"] == "1"
        assert mapped_cell.parameters["EFFECTIVE_SHARED_INPUTS"] == "2"
        assert mapped_cell.parameters["CUT_SHARED_INDEX"] == "2"
        assert "S" in mapped_cell.external_pin_nets
        assert "I2" in mapped_cell.external_pin_nets
        assert mapped_cell.placements[0].input_to_slot_source == (
            "I0",
            "I1",
            "A0",
            "S",
        )
        assert mapped_cell.placements[1].input_to_slot_source == (
            "I0",
            "I1",
            "B0",
            "I2",
        )

        select_bridge.write_verilog_path(gate)

        eq_cfg = EquivalenceCheckConfig(
            gold_verilog=gold,
            gate_verilog=gate,
            top_name="select_as_data_pair",
            frac_cell_name=select_arch.name,
            frac_lut_size=select_arch.frac_lut_size,
            num_shared_inputs=select_arch.num_shared_inputs,
        )
        LutEquivalenceChecker(eq_cfg).run()


def test_select_as_data_pair_mapping_edge_cases() -> None:
    """Test select-as-data arithmetic for the smallest valid LUT sizes."""
    try:
        FracLutArchitecture(
            frac_lut_size=1,
            num_shared_inputs=0,
            use_select_as_data_in_pair_mode=True,
        )
    except ValueError:
        pass
    else:
        raise AssertionError("select-as-data with zero shared inputs must fail")

    lut0 = LogicalLutCell(
        cell_id="lut0",
        cell_type="LUT1",
        input_nets=("a",),
        output_net="y0",
        init=0b10,
        width=1,
    )
    lut1 = LogicalLutCell(
        cell_id="lut1",
        cell_type="LUT1",
        input_nets=("b",),
        output_net="y1",
        init=0b01,
        width=1,
    )
    arch = FracLutArchitecture(
        frac_lut_size=1,
        num_shared_inputs=1,
        name="FRAC_LUT2",
        use_select_as_data_in_pair_mode=True,
    )
    binding = arch.try_bind_pair(lut0, lut1)
    assert binding is not None
    assert binding.external_pin_nets == {"I0": "b", "S": "a"}
    assert binding.placement0.input_to_slot_pin == (0,)
    assert binding.placement1.input_to_slot_pin == (0,)


def test_select_as_data_parameters_are_stable() -> None:
    """Test FRAC cells always emit the same select-as-data parameter schema."""
    lut0 = LogicalLutCell(
        cell_id="lut0",
        cell_type="LUT1",
        input_nets=("a",),
        output_net="y0",
        init=0b10,
        width=1,
    )
    lut1 = LogicalLutCell(
        cell_id="lut1",
        cell_type="LUT1",
        input_nets=("a",),
        output_net="y1",
        init=0b01,
        width=1,
    )
    arch = FracLutArchitecture(
        frac_lut_size=4,
        num_shared_inputs=3,
        name="FRAC_LUT5",
    )
    binding = arch.try_bind_pair(lut0, lut1)
    assert binding is not None
    packed = arch.build_mapped_cell("packed", binding)
    assert packed.parameters["SELECT_AS_DATA_CAPABLE"] == "0"
    assert packed.parameters["SELECT_AS_DATA_USED"] == "0"
    assert packed.parameters["EFFECTIVE_SHARED_INPUTS"] == "3"
    assert packed.parameters["CUT_SHARED_INDEX"] == "-1"
    assert packed.parameters["MUX_SELECT_CONFIG"] == "0"

    select_arch = FracLutArchitecture(
        frac_lut_size=4,
        num_shared_inputs=3,
        name="FRAC_LUT5",
        use_select_as_data_in_pair_mode=True,
    )
    single = select_arch.bind_single_lut(lut0)
    assert single is not None
    assert single.parameters["SELECT_AS_DATA_CAPABLE"] == "1"
    assert single.parameters["SELECT_AS_DATA_USED"] == "0"
    assert single.parameters["EFFECTIVE_SHARED_INPUTS"] == "2"
    assert single.parameters["CUT_SHARED_INDEX"] == "2"
    assert single.parameters["MUX_SELECT_CONFIG"] == "0"


def test_packed_cascade_output_feeds_packed_input_eq() -> None:
    """Test packing when one LUT output feeds the other packed LUT input."""
    benchmark_text = """
module packed_cascade(
    input a, b, c,
    output y_mid, y
);
  wire n;
  LUT2 #(.INIT(4'h8)) producer (
    .I0(a), .I1(b), .O(n)
  );
  LUT2 #(.INIT(4'h6)) consumer (
    .I0(n), .I1(c), .O(y)
  );
  assign y_mid = n;
endmodule
"""
    with tempfile.TemporaryDirectory(prefix="lut_packed_cascade_") as td:
        tmp_dir = Path(td)
        gold = tmp_dir / "packed_cascade.v"
        gate = tmp_dir / "packed_cascade_mapped.v"
        gold.write_text(benchmark_text, encoding="utf-8")

        arch = FracLutArchitecture(
            frac_lut_size=4,
            num_shared_inputs=3,
            name="FRAC_LUT5",
        )
        cfg = LutCombinatorConfig(
            architecture=arch,
            top_name="packed_cascade",
            lut_spec=_named_lut_spec(),
            passthrough=False,
            mode=MatchingMode.MAX_WEIGHT,
        )
        comb = LutCombinator(cfg)
        bridge = PyosysBridge(debug=False)
        bridge.read_verilog_paths([gold])
        result = comb.map_from_design(bridge, inplace=True)

        assert result.stats.mapped_groups == 1
        mapped_cell = result.mapped_cells[0]
        feedback_nets = set(mapped_cell.output_pin_nets.values()) & set(
            mapped_cell.external_pin_nets.values()
        )
        assert feedback_nets

        bridge.write_verilog_path(gate)
        eq_cfg = EquivalenceCheckConfig(
            gold_verilog=gold,
            gate_verilog=gate,
            top_name="packed_cascade",
            frac_cell_name=arch.name,
            frac_lut_size=arch.frac_lut_size,
            num_shared_inputs=arch.num_shared_inputs,
        )
        LutEquivalenceChecker(eq_cfg).run()


def test_select_as_data_packed_feedback_unused_input_eq() -> None:
    """Test select-as-data packing with a feedback-looking unused LUT input."""
    benchmark_text = """
module select_as_data_feedback(
    input a, b, c,
    output y_mid, y
);
  wire n;
  LUT3 #(.INIT(8'h88)) producer (
    .I0(a), .I1(b), .I2(n), .O(n)
  );
  LUT2 #(.INIT(4'h6)) consumer (
    .I0(n), .I1(c), .O(y)
  );
  assign y_mid = n;
endmodule
"""
    with tempfile.TemporaryDirectory(prefix="lut_select_feedback_") as td:
        tmp_dir = Path(td)
        gold = tmp_dir / "select_as_data_feedback.v"
        gate = tmp_dir / "select_as_data_feedback_mapped.v"
        gold.write_text(benchmark_text, encoding="utf-8")

        arch = FracLutArchitecture(
            frac_lut_size=4,
            num_shared_inputs=3,
            name="FRAC_LUT5",
            use_select_as_data_in_pair_mode=True,
        )
        cfg = LutCombinatorConfig(
            architecture=arch,
            top_name="select_as_data_feedback",
            lut_spec=_named_lut_spec(),
            passthrough=False,
            mode=MatchingMode.MAX_WEIGHT,
        )
        comb = LutCombinator(cfg)
        bridge = PyosysBridge(debug=False)
        bridge.read_verilog_paths([gold])
        result = comb.map_from_design(bridge, inplace=True)

        assert result.stats.mapped_groups == 1
        mapped_cell = result.mapped_cells[0]
        assert mapped_cell.parameters["SELECT_AS_DATA_USED"] == "1"
        feedback_nets = set(mapped_cell.output_pin_nets.values()) & set(
            mapped_cell.external_pin_nets.values()
        )
        assert feedback_nets

        bridge.write_verilog_path(gate)
        eq_cfg = EquivalenceCheckConfig(
            gold_verilog=gold,
            gate_verilog=gate,
            top_name="select_as_data_feedback",
            frac_cell_name=arch.name,
            frac_lut_size=arch.frac_lut_size,
            num_shared_inputs=arch.num_shared_inputs,
        )
        LutEquivalenceChecker(eq_cfg).run()


def main() -> None:
    """Run all tests."""
    sel_test: int = 0

    match sel_test:
        case 0:
            test_lut_32_mix_benchmark_eq_iterative()
        case 1:
            test_two_lut_plus_bad_unknown_benchmark_eq_iterative()
        case 2:
            test_enet_benchmark_manual()
        case 3:
            test_lut_32_mixed_yosys_lut_benchmark_eq_iterative()
        case 4:
            test_select_as_data_pair_mapping_eq()
            test_select_as_data_pair_mapping_edge_cases()
            test_select_as_data_parameters_are_stable()
            test_packed_cascade_output_feeds_packed_input_eq()
            test_select_as_data_packed_feedback_unused_input_eq()


if __name__ == "__main__":
    """Run all tests."""
    main()

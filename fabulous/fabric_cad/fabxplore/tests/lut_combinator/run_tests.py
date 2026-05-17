"""Ad-hoc tests."""

import re
import tempfile
from pathlib import Path

from loguru import logger

from fabulous.fabric_cad.fabxplore.flow.architecture_synthesizer import (
    ArchitectureSynthesizer,
)
from fabulous.fabric_cad.fabxplore.modules.lut_combinator.core.combinator import (
    FracLutArchitecture,
    LutCombinator,
    LutCombinatorConfig,
)
from fabulous.fabric_cad.fabxplore.modules.lut_combinator.core.json_transform import (
    apply_mapping_to_json,
)
from fabulous.fabric_cad.fabxplore.modules.lut_combinator.core.models import (
    LogicalLutCell,
    LutSpec,
    MappingResult,
    MappingStats,
    MatchingMode,
)
from fabulous.fabric_cad.fabxplore.modules.lut_combinator.core.netlist import (
    parse_model_json,
)
from fabulous.fabric_cad.fabxplore.modules.lut_combinator.core.report import (
    render_report,
)
from fabulous.fabric_cad.fabxplore.modules.lut_combinator.reorder_opt import (
    ReorderOptOptimizer,
)
from fabulous.fabric_cad.fabxplore.modules.lut_combinator.reordering import (
    LeftoverReorderer,
)
from fabulous.fabric_cad.fabxplore.modules.lut_combinator.utils.equiv_checker import (
    EquivalenceCheckConfig,
    LutEquivalenceChecker,
)
from fabulous.fabric_cad.fabxplore.modules.lut_layering.core.inventory import (
    effective_leftover_width,
)
from fabulous.fabric_cad.fabxplore.modules.lut_layering.core.layerer import (
    normalize_cost_vector,
)
from fabulous.fabric_cad.fabxplore.pyosys.custom_passes.lut_combinator_pass import (
    LutCombinatorPass,
)
from fabulous.fabric_cad.fabxplore.pyosys.custom_passes.lut_layering_pass import (
    LutLayeringPass,
)
from fabulous.fabric_cad.fabxplore.pyosys.pyosys_bridge import PyosysBridge
from fabulous.fabulous_cli.helper import (
    setup_logger,
)

ROOT = Path(__file__).resolve().parents[2]
OUT_DIR = ROOT / "tests" / "lut_combinator" / "out"
setup_logger(verbosity=0, debug=False)


class _LayeringTestSynthesizer(ArchitectureSynthesizer):
    """Tiny concrete synthesizer used by LUT layering smoke tests."""

    def synthesize(self) -> None:
        """No-op synthesis entry point for tests."""

    def generate_primitives(self) -> None:
        """No-op primitive generation for tests."""

    def generate_switch_matrix(self) -> None:
        """No-op switch-matrix generation for tests."""


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


def test_lut0_single_leftover_is_clamped_to_frac_lut_size() -> None:
    """Test LUT0 single hosts cannot report impossible effective LUT capacity."""
    arch = FracLutArchitecture(
        frac_lut_size=4,
        num_shared_inputs=3,
        name="FRAC_LUT5",
        use_select_as_data_in_pair_mode=True,
    )
    lut0 = LogicalLutCell(
        cell_id="const_lut",
        cell_type="$lut",
        input_nets=(),
        output_net="const_y",
        init=1,
        width=0,
    )

    packed = arch.bind_single_lut(lut0)
    assert packed is not None
    assert packed.leftover_lut_width == arch.frac_lut_size
    assert effective_leftover_width(packed, arch) == arch.frac_lut_size

    mapping = MappingResult(
        architecture_name=arch.name,
        top_name="lut0_single",
        mapped_cells=[packed],
        passthrough_luts=[],
        stats=MappingStats(
            total_luts_before=1,
            total_cells_after=1,
            mapped_groups=1,
            mapped_luts=1,
            source_type_count={"LUT0": 1},
            result_type_count={arch.name: 1},
        ),
    )
    report = render_report(mapping)
    assert "effective LUT5" not in report
    assert "effective LUT6" not in report
    assert "reusable LUT4 capacity" in report

    lut4 = LogicalLutCell(
        cell_id="lut4",
        cell_type="$lut",
        input_nets=("a", "b", "c", "d"),
        output_net="lut4_y",
        init=0x6996,
        width=4,
    )
    packed_lut4 = arch.bind_single_lut(lut4)
    assert packed_lut4 is not None
    assert packed_lut4.leftover_lut_width == 1
    assert effective_leftover_width(packed_lut4, arch) == 2


def test_select_as_data_uses_normal_binding_when_possible() -> None:
    """Test select-as-data capable architectures keep normal pair wiring if enough."""
    lut0 = LogicalLutCell(
        cell_id="lut0",
        cell_type="LUT4",
        input_nets=("a", "b", "c", "d"),
        output_net="y0",
        init=0x6996,
        width=4,
    )
    lut1 = LogicalLutCell(
        cell_id="lut1",
        cell_type="LUT4",
        input_nets=("a", "b", "c", "e"),
        output_net="y1",
        init=0xE8E8,
        width=4,
    )
    arch = FracLutArchitecture(
        frac_lut_size=4,
        num_shared_inputs=3,
        name="FRAC_LUT5",
        use_select_as_data_in_pair_mode=True,
    )

    binding = arch.try_bind_pair(lut0, lut1)
    assert binding is not None
    assert binding.select_as_data_used is False
    assert binding.effective_shared_inputs == 3
    assert binding.cut_shared_index == -1
    assert binding.external_pin_nets["S"] == "0"
    assert binding.placement0.input_to_slot_source == ("I0", "I1", "I2", "A0")
    assert binding.placement1.input_to_slot_source == ("I0", "I1", "I2", "B0")

    packed = arch.build_mapped_cell("packed", binding)
    assert packed.parameters["SELECT_AS_DATA_CAPABLE"] == "1"
    assert packed.parameters["SELECT_AS_DATA_USED"] == "0"
    assert packed.parameters["EFFECTIVE_SHARED_INPUTS"] == "3"
    assert packed.parameters["CUT_SHARED_INDEX"] == "-1"
    assert packed.external_pin_nets["S"] == "0"


def test_select_as_data_with_duplicate_private_nets_disabled() -> None:
    """Test select-as-data still packs when effective private nets are distinct."""
    lut0 = LogicalLutCell(
        cell_id="lut0",
        cell_type="LUT4",
        input_nets=("a", "b", "c", "d"),
        output_net="y0",
        init=0x6996,
        width=4,
    )
    lut1 = LogicalLutCell(
        cell_id="lut1",
        cell_type="LUT4",
        input_nets=("a", "b", "e", "f"),
        output_net="y1",
        init=0xE8E8,
        width=4,
    )
    arch = FracLutArchitecture(
        frac_lut_size=4,
        num_shared_inputs=3,
        name="FRAC_LUT5",
        use_select_as_data_in_pair_mode=True,
        allow_duplicate_private_nets=False,
    )

    binding = arch.try_bind_pair(lut0, lut1)
    assert binding is not None
    assert binding.select_as_data_used is True
    assert binding.effective_shared_inputs == 2
    assert binding.cut_shared_index == 2
    assert set(binding.placement0.input_to_slot_source) == {"I0", "I1", "A0", "S"}
    assert set(binding.placement1.input_to_slot_source) == {"I0", "I1", "B0", "I2"}

    packed = arch.build_mapped_cell("packed", binding)
    assert packed.parameters["SELECT_AS_DATA_CAPABLE"] == "1"
    assert packed.parameters["SELECT_AS_DATA_USED"] == "1"
    assert packed.parameters["EFFECTIVE_SHARED_INPUTS"] == "2"
    assert packed.parameters["CUT_SHARED_INDEX"] == "2"


def test_allow_duplicate_private_nets_option() -> None:
    """Test duplicate private-net sharing can be allowed or rejected globally."""
    lut0 = LogicalLutCell(
        cell_id="lut0",
        cell_type="LUT4",
        input_nets=("a", "b", "c", "d"),
        output_net="y0",
        init=0x6996,
        width=4,
    )
    same_lut1 = LogicalLutCell(
        cell_id="same_lut1",
        cell_type="LUT4",
        input_nets=("a", "b", "c", "d"),
        output_net="y1",
        init=0xE8E8,
        width=4,
    )
    different_lut1 = LogicalLutCell(
        cell_id="different_lut1",
        cell_type="LUT4",
        input_nets=("a", "b", "c", "e"),
        output_net="y2",
        init=0xE8E8,
        width=4,
    )

    arch_allow = FracLutArchitecture(
        frac_lut_size=4,
        num_shared_inputs=3,
        name="FRAC_LUT5",
    )
    allowed_binding = arch_allow.try_bind_pair(lut0, same_lut1)
    assert allowed_binding is not None
    assert allowed_binding.external_pin_nets["A0"] == "d"
    assert allowed_binding.external_pin_nets["B0"] == "d"

    arch_disallow = FracLutArchitecture(
        frac_lut_size=4,
        num_shared_inputs=3,
        name="FRAC_LUT5",
        allow_duplicate_private_nets=False,
    )
    assert arch_disallow.try_bind_pair(lut0, same_lut1) is None

    non_duplicate_binding = arch_disallow.try_bind_pair(lut0, different_lut1)
    assert non_duplicate_binding is not None
    assert non_duplicate_binding.external_pin_nets["A0"] == "d"
    assert non_duplicate_binding.external_pin_nets["B0"] == "e"


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
        assert mapped_cell.parameters["SELECT_AS_DATA_CAPABLE"] == "1"
        assert mapped_cell.parameters["SELECT_AS_DATA_USED"] == "0"
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


def test_leftover_reordering_improves_reusable_capacity_eq() -> None:
    """Test reordering moves a small paired LUT into a single-cell leftover."""
    benchmark_text = """
module leftover_reordering_case(
    input a, b, c, d, e, f, g, h,
    output y_host, y_moved, y_remaining
);
  LUT4 #(.INIT(16'h6996)) host (
    .I0(a), .I1(b), .I2(c), .I3(d), .O(y_host)
  );
  LUT2 #(.INIT(4'h8)) moved (
    .I0(e), .I1(f), .O(y_moved)
  );
  LUT2 #(.INIT(4'h6)) remaining (
    .I0(g), .I1(h), .O(y_remaining)
  );
endmodule
"""
    with tempfile.TemporaryDirectory(prefix="lut_leftover_reorder_") as td:
        tmp_dir = Path(td)
        gold = tmp_dir / "leftover_reordering_case.v"
        gate = tmp_dir / "leftover_reordering_case_mapped.v"
        gold.write_text(benchmark_text, encoding="utf-8")

        arch = FracLutArchitecture(
            frac_lut_size=4,
            num_shared_inputs=3,
            name="FRAC_LUT5",
            use_select_as_data_in_pair_mode=True,
        )

        bridge = PyosysBridge(debug=False)
        bridge.read_verilog_paths([gold])
        src_json = bridge.to_netlist_dict()
        model = parse_model_json(
            model_json=src_json,
            top_name="leftover_reordering_case",
            lut_spec=_named_lut_spec(),
        )
        cells_by_id = {cell.cell_id: cell for cell in model.lut_cells}
        host = cells_by_id["host"]
        moved = cells_by_id["moved"]
        remaining = cells_by_id["remaining"]

        host_cell = arch.bind_single_lut(host)
        assert host_cell is not None
        donor_binding = arch.try_bind_pair(moved, remaining)
        assert donor_binding is not None
        donor_cell = arch.build_mapped_cell("FRAC_LUT5_donor", donor_binding)

        mapping = MappingResult(
            architecture_name=arch.name,
            top_name="leftover_reordering_case",
            mapped_cells=[host_cell, donor_cell],
            passthrough_luts=[],
            stats=MappingStats(
                total_luts_before=3,
                total_cells_after=2,
                mapped_groups=2,
                mapped_luts=3,
                passthrough_luts=0,
                source_type_count={"LUT2": 2, "LUT4": 1},
                result_type_count={arch.name: 2},
            ),
            metadata={
                "frac_lut_size": arch.frac_lut_size,
                "num_shared_inputs": arch.num_shared_inputs,
            },
        )

        result = LeftoverReorderer(arch).reorder(mapping)
        assert result.stats.applied_moves == 1
        assert result.stats.reusable_leftover_gain > 0
        assert len(result.mapping.mapped_cells) == 2
        assert sorted(len(c.placements) for c in result.mapping.mapped_cells) == [1, 2]

        single_cells = [
            c for c in result.mapping.mapped_cells if len(c.placements) == 1
        ]
        pair_cells = [c for c in result.mapping.mapped_cells if len(c.placements) == 2]
        assert single_cells[0].placements[0].cell.cell_id in {"moved", "remaining"}
        assert {p.cell.cell_id for p in pair_cells[0].placements} in (
            {"host", "moved"},
            {"host", "remaining"},
        )

        mapped_json = apply_mapping_to_json(src_json, result.mapping)
        bridge.load_netlist_dict(mapped_json)
        bridge.write_verilog_path(gate)

        eq_cfg = EquivalenceCheckConfig(
            gold_verilog=gold,
            gate_verilog=gate,
            top_name="leftover_reordering_case",
            frac_cell_name=arch.name,
            frac_lut_size=arch.frac_lut_size,
            num_shared_inputs=arch.num_shared_inputs,
        )
        LutEquivalenceChecker(eq_cfg).run()


def test_lut_combinator_pass_reordering_option_smoke() -> None:
    """Test the public pyosys pass accepts and reports the reordering option."""
    benchmark_text = """
module leftover_reordering_smoke(
    input a, b, c, d,
    output y0, y1
);
  \\$lut #(.LUT(4'h8), .WIDTH(32'd2)) lut0 (
    .A({b, a}), .Y(y0)
  );
  \\$lut #(.LUT(4'h6), .WIDTH(32'd2)) lut1 (
    .A({d, c}), .Y(y1)
  );
endmodule
"""
    with tempfile.TemporaryDirectory(prefix="lut_reorder_pass_smoke_") as td:
        tmp_dir = Path(td)
        source = tmp_dir / "leftover_reordering_smoke.v"
        source.write_text(benchmark_text, encoding="utf-8")

        bridge = PyosysBridge(debug=False)
        bridge.read_verilog_paths([source])

        pass_ = LutCombinatorPass(
            frac_lut_size=4,
            num_shared_inputs=3,
            lut_name="FRAC_LUT5",
            top_name="leftover_reordering_smoke",
            passthrough=True,
            mode=MatchingMode.MAX_WEIGHT,
            use_select_as_data_in_pair_mode=True,
            reorder_leftover_luts=True,
        )
        pass_.run_on(bridge)

        assert pass_.result_data is not None
        assert pass_.result_data.metadata["leftover_reordering_enabled"] is True
        assert "Leftover Reordering" in pass_.report_summary
        assert "module FRAC_LUT5" in pass_.verilog_model


def test_reorder_opt_saves_pair_cell_eq() -> None:
    """Test reorder-opt spends two leftovers to remove one donor pair cell."""
    benchmark_text = """
module reorder_opt_case(
    input a, b, c, d, e, f, g, h, i, j, k, l,
    output y_host0, y_host1, y_moved0, y_moved1
);
  LUT4 #(.INIT(16'h6996)) host0 (
    .I0(a), .I1(b), .I2(c), .I3(d), .O(y_host0)
  );
  LUT4 #(.INIT(16'he8e8)) host1 (
    .I0(e), .I1(f), .I2(g), .I3(h), .O(y_host1)
  );
  LUT2 #(.INIT(4'h8)) moved0 (
    .I0(i), .I1(j), .O(y_moved0)
  );
  LUT2 #(.INIT(4'h6)) moved1 (
    .I0(k), .I1(l), .O(y_moved1)
  );
endmodule
"""
    with tempfile.TemporaryDirectory(prefix="lut_reorder_opt_") as td:
        tmp_dir = Path(td)
        gold = tmp_dir / "reorder_opt_case.v"
        gate = tmp_dir / "reorder_opt_case_mapped.v"
        gold.write_text(benchmark_text, encoding="utf-8")

        bridge = PyosysBridge(debug=False)
        bridge.read_verilog_paths([gold])
        src_json = bridge.to_netlist_dict()
        model = parse_model_json(
            model_json=src_json,
            top_name="reorder_opt_case",
            lut_spec=_named_lut_spec(),
        )
        cells_by_id = {cell.cell_id: cell for cell in model.lut_cells}

        arch = FracLutArchitecture(
            frac_lut_size=4,
            num_shared_inputs=3,
            name="FRAC_LUT5",
            use_select_as_data_in_pair_mode=True,
        )

        host0_cell = arch.bind_single_lut(cells_by_id["host0"])
        host1_cell = arch.bind_single_lut(cells_by_id["host1"])
        assert host0_cell is not None
        assert host1_cell is not None

        donor_binding = arch.try_bind_pair(cells_by_id["moved0"], cells_by_id["moved1"])
        assert donor_binding is not None
        donor_cell = arch.build_mapped_cell("FRAC_LUT5_donor", donor_binding)

        mapping = MappingResult(
            architecture_name=arch.name,
            top_name="reorder_opt_case",
            mapped_cells=[host0_cell, host1_cell, donor_cell],
            passthrough_luts=[],
            stats=MappingStats(
                total_luts_before=4,
                total_cells_after=3,
                mapped_groups=3,
                mapped_luts=4,
                passthrough_luts=0,
                source_type_count={"LUT2": 2, "LUT4": 2},
                result_type_count={arch.name: 3},
            ),
            metadata={
                "frac_lut_size": arch.frac_lut_size,
                "num_shared_inputs": arch.num_shared_inputs,
            },
        )

        result = ReorderOptOptimizer(arch).optimize(mapping)
        assert result.stats.applied_optimizations == 1
        assert result.stats.frac_cells_saved == 1
        assert len(result.mapping.mapped_cells) == 2
        assert result.mapping.stats.mapped_groups == 2
        assert result.mapping.stats.total_cells_after == 2
        assert result.mapping.stats.mapped_luts == 4
        assert all(len(c.placements) == 2 for c in result.mapping.mapped_cells)

        mapped_json = apply_mapping_to_json(src_json, result.mapping)
        bridge.load_netlist_dict(mapped_json)
        bridge.write_verilog_path(gate)

        eq_cfg = EquivalenceCheckConfig(
            gold_verilog=gold,
            gate_verilog=gate,
            top_name="reorder_opt_case",
            frac_cell_name=arch.name,
            frac_lut_size=arch.frac_lut_size,
            num_shared_inputs=arch.num_shared_inputs,
        )
        LutEquivalenceChecker(eq_cfg).run()


def test_lut_combinator_pass_reorder_opt_option_smoke() -> None:
    """Test the public pyosys pass accepts combined reorder/reorder-opt options."""
    benchmark_text = """
module reorder_opt_smoke(
    input a, b, c, d,
    output y0, y1
);
  \\$lut #(.LUT(4'h8), .WIDTH(32'd2)) lut0 (
    .A({b, a}), .Y(y0)
  );
  \\$lut #(.LUT(4'h6), .WIDTH(32'd2)) lut1 (
    .A({d, c}), .Y(y1)
  );
endmodule
"""
    with tempfile.TemporaryDirectory(prefix="lut_reorder_opt_smoke_") as td:
        tmp_dir = Path(td)
        source = tmp_dir / "reorder_opt_smoke.v"
        source.write_text(benchmark_text, encoding="utf-8")

        bridge = PyosysBridge(debug=False)
        bridge.read_verilog_paths([source])

        pass_ = LutCombinatorPass(
            frac_lut_size=4,
            num_shared_inputs=3,
            lut_name="FRAC_LUT5",
            top_name="reorder_opt_smoke",
            passthrough=True,
            mode=MatchingMode.MAX_WEIGHT,
            use_select_as_data_in_pair_mode=True,
            reorder_leftover_luts=True,
            reorder_opt_luts=True,
        )
        pass_.run_on(bridge)

        assert pass_.result_data is not None
        assert pass_.result_data.metadata["leftover_reordering_enabled"] is True
        assert pass_.result_data.metadata["reorder_opt_enabled"] is True
        assert "Leftover Reordering" in pass_.report_summary
        assert "Reorder Opt" in pass_.report_summary


def test_lut_layering_pass_injects_overlay_lut_smoke() -> None:
    """Test layering injects a small overlay LUT into single-cell leftover space."""
    base_text = """
module layering_base(
    input a, b, c, d,
    output y
);
  \\$lut #(.LUT(16'h6996), .WIDTH(32'd4)) base_lut (
    .A({d, c, b, a}), .Y(y)
  );
endmodule
"""
    overlay_text = """
module overlay_and2(
    input e, f,
    output z
);
  assign z = e & f;
endmodule
"""
    with tempfile.TemporaryDirectory(prefix="lut_layering_smoke_") as td:
        tmp_dir = Path(td)
        base = tmp_dir / "base.v"
        overlay = tmp_dir / "overlay.v"
        base.write_text(base_text, encoding="utf-8")
        overlay.write_text(overlay_text, encoding="utf-8")

        bridge = PyosysBridge(debug=False)
        bridge.read_verilog_paths([base])

        comb_pass = LutCombinatorPass(
            frac_lut_size=4,
            num_shared_inputs=3,
            lut_name="FRAC_LUT5",
            top_name="layering_base",
            passthrough=True,
            mode=MatchingMode.MAX_WEIGHT,
            use_select_as_data_in_pair_mode=True,
        )
        comb_pass.run_on(bridge)
        assert comb_pass.result_data is not None
        assert comb_pass.architecture is not None
        assert len(comb_pass.result_data.mapped_cells) == 1
        assert len(comb_pass.result_data.mapped_cells[0].placements) == 1

        layer_pass = LutLayeringPass(
            overlay_verilog_paths=[overlay],
            overlay_top_name="overlay_and2",
            base_mapping=comb_pass.result_data,
            architecture=comb_pass.architecture,
            top_name="layering_base",
            overlay_prefix="design1_",
            base_prefix="design0_",
        )
        layer_pass.run_on(bridge)

        assert layer_pass.result_data is not None
        assert layer_pass.result_data.stats.injected_luts == 1
        assert len(layer_pass.result_data.mapping.mapped_cells[0].placements) == 2
        assert "LUT Layering" in layer_pass.report_summary

        netlist = bridge.to_netlist_dict()
        top = netlist["modules"]["layering_base"]
        assert "design0_a" in top["ports"]
        assert "design1_e" in top["ports"]
        assert "design1_z" in top["ports"]


def test_lut_layering_pass_rejects_overlay_that_does_not_fit() -> None:
    """Test layering raises when the complete overlay cannot fit."""
    base_text = """
module layering_no_fit_base(
    input a, b, c, d,
    output y
);
  \\$lut #(.LUT(16'h6996), .WIDTH(32'd4)) base_lut (
    .A({d, c, b, a}), .Y(y)
  );
endmodule
"""
    overlay_text = """
module overlay_and3(
    input e, f, g,
    output z
);
  assign z = e & f & g;
endmodule
"""
    with tempfile.TemporaryDirectory(prefix="lut_layering_no_fit_") as td:
        tmp_dir = Path(td)
        base = tmp_dir / "base.v"
        overlay = tmp_dir / "overlay.v"
        base.write_text(base_text, encoding="utf-8")
        overlay.write_text(overlay_text, encoding="utf-8")

        bridge = PyosysBridge(debug=False)
        bridge.read_verilog_paths([base])

        comb_pass = LutCombinatorPass(
            frac_lut_size=4,
            num_shared_inputs=3,
            lut_name="FRAC_LUT5",
            top_name="layering_no_fit_base",
            passthrough=True,
            mode=MatchingMode.MAX_WEIGHT,
            use_select_as_data_in_pair_mode=True,
        )
        comb_pass.run_on(bridge)
        assert comb_pass.result_data is not None
        assert comb_pass.architecture is not None

        before = bridge.to_netlist_dict()
        layer_pass = LutLayeringPass(
            overlay_verilog_paths=[overlay],
            overlay_top_name="overlay_and3",
            base_mapping=comb_pass.result_data,
            architecture=comb_pass.architecture,
            top_name="layering_no_fit_base",
            overlay_prefix="design1_",
            base_prefix=None,
            overlay_mapper_max_tries=0,
            overlay_mapper_fallback_lut_size=2,
        )

        try:
            layer_pass.run_on(bridge)
        except RuntimeError as exc:
            message = str(exc)
            assert "Overlay design does not fit leftover inventory." in message
            assert "Inventory:" in message
            assert "Attempts:" in message
            assert "overlay by width:" in message
            assert "costs:" in message
        else:
            raise AssertionError("Expected layering to reject a non-fitting overlay")

        after = bridge.to_netlist_dict()
        assert before == after


def test_synthesizer_lut_layering_flow_smoke() -> None:
    """Test synthesizer-level combinator-to-layering state handoff."""
    base_text = """
module layering_synth_base(
    input a, b, c, d,
    output y
);
  \\$lut #(.LUT(16'h6996), .WIDTH(32'd4)) base_lut (
    .A({d, c, b, a}), .Y(y)
  );
endmodule
"""
    overlay_text = """
module layering_synth_overlay(
    input e, f,
    output z
);
  assign z = e ^ f;
endmodule
"""
    with tempfile.TemporaryDirectory(prefix="lut_layering_synth_") as td:
        tmp_dir = Path(td)
        base = tmp_dir / "base.v"
        overlay = tmp_dir / "overlay.v"
        base.write_text(base_text, encoding="utf-8")
        overlay.write_text(overlay_text, encoding="utf-8")

        synth = _LayeringTestSynthesizer(debug=False)
        synth.design.read_verilog_paths([base])
        synth.design_lut_combinator_pass(
            log_report=False,
            frac_lut_size=4,
            num_shared_inputs=3,
            lut_name="FRAC_LUT5",
            top_name="layering_synth_base",
            passthrough=True,
            mode=MatchingMode.MAX_WEIGHT,
            use_select_as_data_in_pair_mode=True,
        )
        layer_pass = synth.design_lut_layering_pass(
            overlay_verilog_paths=[overlay],
            overlay_top_name="layering_synth_overlay",
            log_report=False,
            top_name="layering_synth_base",
        )

        assert layer_pass.result_data is not None
        assert layer_pass.result_data.stats.injected_luts == 1
        assert "LUT Layering" in layer_pass.report_summary


def test_synthesizer_lut_layering_requires_lut_combinator() -> None:
    """Test synthesizer-level layering rejects missing base mapping state."""
    synth = _LayeringTestSynthesizer(debug=False)
    try:
        synth.design_lut_layering_pass(
            overlay_verilog_paths=[],
            overlay_top_name="missing",
            log_report=False,
        )
    except RuntimeError:
        pass
    else:
        raise AssertionError("Expected layering to require a previous combinator pass")


def test_synthesizer_lut_layering_repeated_prefixes_smoke() -> None:
    """Test repeated synthesizer layering keeps existing base names stable."""
    base_text = """
module layering_repeat_base(
    input a0, b0, c0, d0,
    input a1, b1, c1, d1,
    output y0, y1
);
  \\$lut #(.LUT(16'h6996), .WIDTH(32'd4)) base_lut0 (
    .A({d0, c0, b0, a0}), .Y(y0)
  );
  \\$lut #(.LUT(16'h6996), .WIDTH(32'd4)) base_lut1 (
    .A({d1, c1, b1, a1}), .Y(y1)
  );
endmodule
"""
    overlay1_text = """
module repeat_overlay1(
    input e, f,
    output z
);
  assign z = e & f;
endmodule
"""
    overlay2_text = """
module repeat_overlay2(
    input g, h,
    output q
);
  assign q = g ^ h;
endmodule
"""
    with tempfile.TemporaryDirectory(prefix="lut_layering_repeat_") as td:
        tmp_dir = Path(td)
        base = tmp_dir / "base.v"
        overlay1 = tmp_dir / "overlay1.v"
        overlay2 = tmp_dir / "overlay2.v"
        base.write_text(base_text, encoding="utf-8")
        overlay1.write_text(overlay1_text, encoding="utf-8")
        overlay2.write_text(overlay2_text, encoding="utf-8")

        synth = _LayeringTestSynthesizer(debug=False)
        synth.design.read_verilog_paths([base])
        synth.design_lut_combinator_pass(
            log_report=False,
            frac_lut_size=4,
            num_shared_inputs=3,
            lut_name="FRAC_LUT5",
            top_name="layering_repeat_base",
            passthrough=True,
            mode=MatchingMode.MAX_WEIGHT,
            use_select_as_data_in_pair_mode=True,
        )
        first_layer = synth.design_lut_layering_pass(
            overlay_verilog_paths=[overlay1],
            overlay_top_name="repeat_overlay1",
            log_report=False,
            top_name="layering_repeat_base",
        )
        second_layer = synth.design_lut_layering_pass(
            overlay_verilog_paths=[overlay2],
            overlay_top_name="repeat_overlay2",
            log_report=False,
            top_name="layering_repeat_base",
        )

        assert first_layer.result_data is not None
        assert second_layer.result_data is not None
        assert first_layer.result_data.stats.injected_luts == 1
        assert second_layer.result_data.stats.injected_luts == 1

        netlist = synth.design.to_netlist_dict()
        top = netlist["modules"]["layering_repeat_base"]
        names = set(top["ports"]) | set(top["netnames"])
        assert "design0_a0" in names
        assert "design1_e" in names
        assert "design2_g" in names
        assert not any("design0_design0_" in name for name in names)
        assert not any("design0_design1_" in name for name in names)


def test_lut_layering_fallback_lut2_mapping_smoke() -> None:
    """Test overlay mapping can force the LUT2 fallback candidate."""
    host_count = 12
    ports = "\n".join(f"    input a{i}, b{i}, c{i}, d{i}," for i in range(host_count))
    outputs = ", ".join(f"y{i}" for i in range(host_count))
    luts = "\n".join(
        f"""  \\$lut #(.LUT(16'h6996), .WIDTH(32'd4)) base_lut{i} (
    .A({{d{i}, c{i}, b{i}, a{i}}}), .Y(y{i})
  );"""
        for i in range(host_count)
    )
    base_text = f"""
module layering_fallback_base(
{ports}
    output {outputs}
);
{luts}
endmodule
"""
    overlay_text = """
module overlay_mux4(
    input a, b, c, d,
    input s0, s1,
    output y
);
  assign y = s1 ? (s0 ? d : c) : (s0 ? b : a);
endmodule
"""
    with tempfile.TemporaryDirectory(prefix="lut_layering_fallback_") as td:
        tmp_dir = Path(td)
        base = tmp_dir / "base.v"
        overlay = tmp_dir / "overlay.v"
        base.write_text(base_text, encoding="utf-8")
        overlay.write_text(overlay_text, encoding="utf-8")

        bridge = PyosysBridge(debug=False)
        bridge.read_verilog_paths([base])

        comb_pass = LutCombinatorPass(
            frac_lut_size=4,
            num_shared_inputs=3,
            lut_name="FRAC_LUT5",
            top_name="layering_fallback_base",
            passthrough=True,
            mode=MatchingMode.MAX_WEIGHT,
            use_select_as_data_in_pair_mode=True,
        )
        comb_pass.run_on(bridge)
        assert comb_pass.result_data is not None
        assert comb_pass.architecture is not None

        layer_pass = LutLayeringPass(
            overlay_verilog_paths=[overlay],
            overlay_top_name="overlay_mux4",
            base_mapping=comb_pass.result_data,
            architecture=comb_pass.architecture,
            top_name="layering_fallback_base",
            overlay_mapper_max_tries=0,
            overlay_mapper_fallback_lut_size=2,
        )
        layer_pass.run_on(bridge)

        assert layer_pass.result_data is not None
        assert layer_pass.result_data.selected_attempt.name == "fallback_lut2"
        assert all(lut.width <= 2 for lut in layer_pass.result_data.overlay_luts)
        assert layer_pass.result_data.stats.injected_luts > 1


def test_lut_layering_inventory_cost_vector_is_normalized() -> None:
    """Test aggressive retry penalties still emit bounded ABC9 costs."""
    costs = normalize_cost_vector(
        (100, 855, 4_887, 23_687, 104_891, 438_669),
        target_min=100,
    )

    assert min(costs) == 100
    assert max(costs) <= 10_000
    assert costs == tuple(sorted(costs))


def test_lut_layering_cost_normalization_keeps_gentle_shape() -> None:
    """Test small raw cost differences remain small after normalization."""
    costs = normalize_cost_vector((253, 264, 331), target_min=100)

    assert costs == (100, 104, 131)


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
            test_lut0_single_leftover_is_clamped_to_frac_lut_size()
            test_select_as_data_uses_normal_binding_when_possible()
            test_select_as_data_with_duplicate_private_nets_disabled()
            test_allow_duplicate_private_nets_option()
            test_select_as_data_parameters_are_stable()
            test_packed_cascade_output_feeds_packed_input_eq()
            test_select_as_data_packed_feedback_unused_input_eq()
            test_leftover_reordering_improves_reusable_capacity_eq()
            test_lut_combinator_pass_reordering_option_smoke()
            test_reorder_opt_saves_pair_cell_eq()
            test_lut_combinator_pass_reorder_opt_option_smoke()
            test_lut_layering_pass_injects_overlay_lut_smoke()
            test_lut_layering_pass_rejects_overlay_that_does_not_fit()
            test_synthesizer_lut_layering_flow_smoke()
            test_synthesizer_lut_layering_requires_lut_combinator()
            test_synthesizer_lut_layering_repeated_prefixes_smoke()
            test_lut_layering_fallback_lut2_mapping_smoke()
            test_lut_layering_inventory_cost_vector_is_normalized()
            test_lut_layering_cost_normalization_keeps_gentle_shape()


if __name__ == "__main__":
    """Run all tests."""
    main()

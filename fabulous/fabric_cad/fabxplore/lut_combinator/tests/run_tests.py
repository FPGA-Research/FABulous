"""Ad-hoc tests."""

from pathlib import Path

from loguru import logger

from fabulous.fabric_cad.fabxplore.lut_combinator.core.combinator import (
    FracLutArchitecture,
    LutCombinator,
    LutCombinatorConfig,
)
from fabulous.fabric_cad.fabxplore.lut_combinator.core.models import MatchingMode
from fabulous.fabric_cad.fabxplore.lut_combinator.tests.equiv_only import (
    EquivalenceCheckConfig,
    LutEquivalenceChecker,
)
from fabulous.fabulous_cli.helper import (
    setup_logger,
)

ROOT = Path(__file__).resolve().parents[1]
setup_logger(verbosity=0, debug=False)


def test_lut_32_mix_benchmark_eq(
    fls: int, ns: int, passthrough: bool, mode: MatchingMode
) -> None:
    """Test mapping and equivalence checking of a LUT32-mixed benchmark."""
    benchmark_verilog = ROOT / "benchmarks" / "lut_mapped_simple" / "lut32_mixed.v"
    out_dir = ROOT / "tests" / "out"
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
        passthrough=passthrough,
        mode=mode,
    )
    comb = LutCombinator(cfg)
    comb.map_from_verilog(benchmark_verilog)
    mapped_path = out_dir / "lut32_mixed_mapped.v"
    mapped_path.write_text(comb.mapped_verilog_string, encoding="utf-8")
    (out_dir / "lut32_mixed_report.txt").write_text(
        comb.build_report(), encoding="utf-8"
    )

    eq_cfg = EquivalenceCheckConfig(
        gold_verilog=benchmark_verilog,
        gate_verilog=mapped_path,
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
    out_dir = ROOT / "tests" / "out"
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
        passthrough=passthrough,
        mode=mode,
    )
    comb = LutCombinator(cfg)
    comb.map_from_verilog(benchmark_verilog)
    mapped_path = out_dir / "two_lut_plus_bad_unknown_mapped.v"
    mapped_path.write_text(comb.mapped_verilog_string, encoding="utf-8")
    (out_dir / "two_lut_plus_bad_unknown_report.txt").write_text(
        comb.build_report(), encoding="utf-8"
    )

    eq_cfg = EquivalenceCheckConfig(
        gold_verilog=benchmark_verilog,
        gate_verilog=mapped_path,
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
    out_dir = ROOT / "tests" / "out"
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
        passthrough=passthrough,
        mode=mode,
        debug=False,
    )
    comb = LutCombinator(cfg)
    comb.map_from_verilog(benchmark_verilog)
    mapped_path = out_dir / "enet_mapped.v"
    mapped_path.write_text(comb.mapped_verilog_string, encoding="utf-8")
    (out_dir / "enet_report.txt").write_text(comb.build_report(), encoding="utf-8")

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


def main() -> None:
    """Run all tests."""
    sel_test: int = 2

    match sel_test:
        case 0:
            test_lut_32_mix_benchmark_eq_iterative()
        case 1:
            test_two_lut_plus_bad_unknown_benchmark_eq_iterative()
        case 2:
            test_enet_benchmark_manual()


if __name__ == "__main__":
    """Run all tests."""
    main()

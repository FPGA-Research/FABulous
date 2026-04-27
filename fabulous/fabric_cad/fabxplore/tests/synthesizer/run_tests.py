"""Ad-hoc tests."""

from pathlib import Path

from loguru import logger

from fabulous.fabric_cad.fabxplore.architectures.fabr_v2.fabulous_architecture import (
    FabulousArchitecture,
)
from fabulous.fabric_cad.fabxplore.architectures.fabr_v2.models import (
    FabulousArchitectureConfig,
)
from fabulous.fabulous_cli.helper import (
    setup_logger,
)

ROOT = Path(__file__).resolve().parents[2]
OUT_DIR = ROOT / "tests" / "synthesizer" / "out"
setup_logger(verbosity=0, debug=False)


def test_basic_synth_flow() -> None:
    """Test the basic synthesis flow of the FABulousArchitecture."""
    logger.info("Testing basic synthesis flow of FABulousArchitecture")
    hdl_files = [ROOT / "benchmarks" / "verilog_rtl" / "ode" / "ode.v"]
    config = FabulousArchitectureConfig(
        hdl_files=hdl_files,
        top_module="ode",
        allow_resource_sharing=True,
        map_alu_macc_cells=True,
        map_ram_cells=True,
        optimize_fsm=True,
        map_io_pads=True,
        map_carry_chains=True,
        user_design_out_dir=OUT_DIR,
    )
    arch = FabulousArchitecture(config, debug=True)
    arch.synthesize()
    arch.write_verilog_path()
    arch.write_json_path()


def test_basic_large_or_benchmark() -> None:
    """Test large OR benchmark FABulousArchitecture."""
    logger.info("Testing large OR benchmark FABulousArchitecture")
    hdl_files = [ROOT / "benchmarks" / "verilog_rtl" / "large_or" / "or17_chain.v"]
    config = FabulousArchitectureConfig(
        hdl_files=hdl_files,
        top_module="or17_chain",
        allow_resource_sharing=True,
        map_alu_macc_cells=True,
        map_ram_cells=True,
        optimize_fsm=True,
        map_io_pads=True,
        map_carry_chains=True,
        user_design_out_dir=OUT_DIR,
    )
    arch = FabulousArchitecture(config, debug=True)
    arch.synthesize()
    arch.write_verilog_path()
    arch.write_json_path()


def test_lut32_mixed_benchmark() -> None:
    """Test LUT32 mixed benchmark FABulousArchitecture."""
    logger.info("Testing LUT32 mixed benchmark FABulousArchitecture")
    hdl_files = [ROOT / "benchmarks" / "verilog_rtl" / "lut32_mixed" / "lut32_mixed.v"]
    config = FabulousArchitectureConfig(
        hdl_files=hdl_files,
        top_module="lut32_mixed",
        allow_resource_sharing=True,
        map_alu_macc_cells=True,
        map_ram_cells=True,
        optimize_fsm=True,
        map_io_pads=True,
        map_carry_chains=True,
        user_design_out_dir=OUT_DIR,
    )
    arch = FabulousArchitecture(config, debug=True)
    arch.synthesize()
    arch.write_verilog_path()
    arch.write_json_path()


def main() -> None:
    """Run all tests."""
    sel_test: int = 0

    match sel_test:
        case 0:
            test_basic_synth_flow()
        case 1:
            test_basic_large_or_benchmark()
        case 2:
            test_lut32_mixed_benchmark()


if __name__ == "__main__":
    """Run all tests."""
    main()

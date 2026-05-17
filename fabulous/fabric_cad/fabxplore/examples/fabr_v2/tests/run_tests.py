"""Ad-hoc tests."""

from pathlib import Path

from loguru import logger

from fabulous.fabric_cad.fabxplore.examples.fabr_v2.models import (
    FabulousArchitectureConfig,
)
from fabulous.fabulous_cli.helper import (
    setup_logger,
)

ROOT = Path(__file__).resolve().parents[3]
OUT_DIR = ROOT / "examples" / "fabr_v2" / "tests" / "out"
setup_logger(verbosity=0, debug=False)


def test_basic_synth_flow() -> FabulousArchitectureConfig:
    """Test the basic synthesis flow of the FABulousArchitecture."""
    logger.info("Testing basic synthesis flow of FABulousArchitecture")
    hdl_files = [ROOT / "benchmarks" / "verilog_rtl" / "ode" / "ode.v"]
    return FabulousArchitectureConfig(
        hdl_files=hdl_files,
        top_module="ode",
        allow_resource_sharing=True,
        map_alu_macc_cells=True,
        map_ram_cells=True,
        optimize_fsm=True,
        map_io_pads=False,
        map_carry_chains=True,
        user_design_out_dir=OUT_DIR,
    )


def test_basic_large_or_benchmark() -> FabulousArchitectureConfig:
    """Test large OR benchmark FABulousArchitecture."""
    logger.info("Testing large OR benchmark FABulousArchitecture")
    hdl_files = [ROOT / "benchmarks" / "verilog_rtl" / "large_or" / "or17_chain.v"]
    return FabulousArchitectureConfig(
        hdl_files=hdl_files,
        top_module="or17_chain",
        allow_resource_sharing=True,
        map_alu_macc_cells=True,
        map_ram_cells=True,
        optimize_fsm=True,
        map_io_pads=False,
        map_carry_chains=True,
        user_design_out_dir=OUT_DIR,
    )


def test_lut32_mixed_benchmark() -> FabulousArchitectureConfig:
    """Test LUT32 mixed benchmark FABulousArchitecture."""
    logger.info("Testing LUT32 mixed benchmark FABulousArchitecture")
    hdl_files = [ROOT / "benchmarks" / "verilog_rtl" / "lut32_mixed" / "lut32_mixed.v"]
    return FabulousArchitectureConfig(
        hdl_files=hdl_files,
        top_module="lut32_mixed",
        allow_resource_sharing=True,
        map_alu_macc_cells=True,
        map_ram_cells=True,
        optimize_fsm=True,
        map_io_pads=False,
        map_carry_chains=True,
        user_design_out_dir=OUT_DIR,
    )


def test_aes_like_sboxes_benchmark() -> FabulousArchitectureConfig:
    """Test AES-like S-box benchmark FABulousArchitecture."""
    logger.info("Testing AES-like S-box benchmark FABulousArchitecture")
    hdl_files = [
        ROOT / "benchmarks" / "verilog_rtl" / "aes_like_sboxes" / "aes_like_sboxes.v"
    ]
    return FabulousArchitectureConfig(
        hdl_files=hdl_files,
        top_module="aes_like_sboxes",
        allow_resource_sharing=True,
        map_alu_macc_cells=True,
        map_ram_cells=True,
        optimize_fsm=True,
        map_io_pads=False,
        map_carry_chains=True,
        user_design_out_dir=OUT_DIR,
    )

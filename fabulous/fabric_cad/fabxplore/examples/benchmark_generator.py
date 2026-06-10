"""Benchmark generator for FABulousArchitectureConfig instances.

This module provides a utility class, BenchmarkGenerator, to create
FABulousArchitectureConfig instances for various benchmark designs. Each method in the
class corresponds to a specific benchmark.
"""

from pathlib import Path

from loguru import logger

from fabulous.fabric_cad.fabxplore.examples.models import (
    FabulousArchitectureConfig,
)
from fabulous.fabulous_cli.helper import (
    setup_logger,
)

BENCH_ROOT = Path(__file__).resolve().parents[1] / "benchmarks"
setup_logger(verbosity=0, debug=False)


class BenchmarkGenerator:
    """Utility class to generate FABulousArchitectureConfig instances for benchmarks."""

    def __init__(self, out_dir: Path) -> None:
        self.out_dir = out_dir

    def test_basic_synth_flow(self, name: str) -> FabulousArchitectureConfig:
        """Test the basic synthesis flow of the FABulousArchitecture."""
        logger.info("Testing basic synthesis flow of FABulousArchitecture")
        hdl_files = [BENCH_ROOT / "verilog_rtl" / "ode" / "ode.v"]
        (self.out_dir / name).mkdir(parents=True, exist_ok=True)
        return FabulousArchitectureConfig(
            hdl_files=hdl_files,
            top_module=name,
            allow_resource_sharing=True,
            map_alu_macc_cells=True,
            map_ram_cells=True,
            optimize_fsm=True,
            map_io_pads=False,
            map_carry_chains=True,
            user_design_out_dir=self.out_dir / name,
        )

    def test_basic_large_or_benchmark(self, name: str) -> FabulousArchitectureConfig:
        """Test large OR benchmark FABulousArchitecture."""
        logger.info("Testing large OR benchmark FABulousArchitecture")
        hdl_files = [BENCH_ROOT / "verilog_rtl" / "large_or" / "or17_chain.v"]
        (self.out_dir / name).mkdir(parents=True, exist_ok=True)
        return FabulousArchitectureConfig(
            hdl_files=hdl_files,
            top_module=name,
            allow_resource_sharing=True,
            map_alu_macc_cells=True,
            map_ram_cells=True,
            optimize_fsm=True,
            map_io_pads=True,
            map_carry_chains=True,
            user_design_out_dir=self.out_dir / name,
        )

    def test_lut32_mixed_benchmark(self, name: str) -> FabulousArchitectureConfig:
        """Test LUT32 mixed benchmark FABulousArchitecture."""
        logger.info("Testing LUT32 mixed benchmark FABulousArchitecture")
        hdl_files = [BENCH_ROOT / "verilog_rtl" / "lut32_mixed" / "lut32_mixed.v"]
        (self.out_dir / name).mkdir(parents=True, exist_ok=True)
        return FabulousArchitectureConfig(
            hdl_files=hdl_files,
            top_module=name,
            allow_resource_sharing=True,
            map_alu_macc_cells=True,
            map_ram_cells=True,
            optimize_fsm=True,
            map_io_pads=True,
            map_carry_chains=True,
            user_design_out_dir=self.out_dir / name,
        )

    def test_aes_like_sboxes_benchmark(self, name: str) -> FabulousArchitectureConfig:
        """Test AES-like S-box benchmark FABulousArchitecture."""
        logger.info("Testing AES-like S-box benchmark FABulousArchitecture")
        hdl_files = [
            BENCH_ROOT / "verilog_rtl" / "aes_like_sboxes" / "aes_like_sboxes.v"
        ]
        (self.out_dir / name).mkdir(parents=True, exist_ok=True)
        return FabulousArchitectureConfig(
            hdl_files=hdl_files,
            top_module=name,
            allow_resource_sharing=True,
            map_alu_macc_cells=True,
            map_ram_cells=True,
            optimize_fsm=True,
            map_io_pads=False,
            map_carry_chains=True,
            user_design_out_dir=self.out_dir / name,
        )

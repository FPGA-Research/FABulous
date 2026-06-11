"""Benchmark generator for FABulousArchitectureConfig instances.

This module provides a utility class, BenchmarkGenerator, to create
FABulousArchitectureConfig instances for various benchmark designs. Each method in the
class corresponds to a specific benchmark.
"""

from pathlib import Path

from loguru import logger
from pydantic import BaseModel, ConfigDict

from fabulous.fabulous_cli.helper import (
    setup_logger,
)

BENCH_ROOT = Path(__file__).resolve().parents[1] / "benchmarks"
setup_logger(verbosity=0, debug=False)


class FabulousArchitectureConfig(BaseModel):
    """Configuration parameters for the FABulous architecture mapping process."""

    model_config = ConfigDict(strict=False, validate_assignment=True, frozen=False)

    hdl_files: list[Path]
    top_module: str
    allow_resource_sharing: bool
    map_alu_macc_cells: bool
    map_ram_cells: bool
    optimize_fsm: bool
    map_io_pads: bool
    map_carry_chains: bool
    defines: list[str] | None = None
    tile_output_dir: Path | None = None
    user_design_out_dir: Path | None = None


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

    def test_swm_micro24_benchmark(self, name: str) -> FabulousArchitectureConfig:
        """Test SWM Micro24 benchmark FABulousArchitecture."""
        logger.info("Testing SWM Micro24 benchmark FABulousArchitecture")
        hdl_files = [BENCH_ROOT / "verilog_rtl" / "micro_complex" / "swm_micro24.v"]
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

    def test_vtr_riscv_core_benchmark(self, name: str) -> FabulousArchitectureConfig:
        """Test VTR RISC-V core benchmark FABulousArchitecture."""
        logger.info("Testing VTR RISC-V core benchmark FABulousArchitecture")
        hdl_files = [BENCH_ROOT / "vtr" / "riscv_core.v"]
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

    def test_vtr_sha1_benchmark(self, name: str) -> FabulousArchitectureConfig:
        """Test VTR SHA1 benchmark FABulousArchitecture."""
        logger.info("Testing VTR SHA1 benchmark FABulousArchitecture")
        hdl_files = [BENCH_ROOT / "vtr" / "sha1.v"]
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

    def test_vtr_enet_benchmark(self, name: str) -> FabulousArchitectureConfig:
        """Test VTR Ethernet benchmark FABulousArchitecture."""
        logger.info("Testing VTR Ethernet benchmark FABulousArchitecture")
        hdl_files = [BENCH_ROOT / "vtr" / "enet.v"]
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

    def test_vtr_ode_benchmark(self, name: str) -> FabulousArchitectureConfig:
        """Test VTR ODE benchmark FABulousArchitecture."""
        logger.info("Testing VTR ODE benchmark FABulousArchitecture")
        hdl_files = [BENCH_ROOT / "vtr" / "ode.v"]
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

    def test_vtr_aes_cipher_top_benchmark(
        self,
        name: str,
    ) -> FabulousArchitectureConfig:
        """Test VTR AES cipher benchmark FABulousArchitecture."""
        logger.info("Testing VTR AES cipher benchmark FABulousArchitecture")
        hdl_files = [BENCH_ROOT / "vtr" / "aes_cipher_top.v"]
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

    def test_vtr_mm3_benchmark(self, name: str) -> FabulousArchitectureConfig:
        """Test VTR MM3 benchmark FABulousArchitecture."""
        logger.info("Testing VTR MM3 benchmark FABulousArchitecture")
        hdl_files = [BENCH_ROOT / "vtr" / "mm3.v"]
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

    def test_titan_wb_conmax_top_benchmark(
        self,
        name: str,
    ) -> FabulousArchitectureConfig:
        """Test Titan Wishbone conmax benchmark FABulousArchitecture."""
        logger.info("Testing Titan Wishbone conmax benchmark FABulousArchitecture")
        hdl_files = [BENCH_ROOT / "titan" / "wb_conmax_top.v"]
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

    def test_titan_ucsb_152_tap_fir_benchmark(
        self,
        name: str,
    ) -> FabulousArchitectureConfig:
        """Test Titan UCSB 152-tap FIR benchmark FABulousArchitecture."""
        logger.info("Testing Titan UCSB 152-tap FIR benchmark FABulousArchitecture")
        hdl_files = [BENCH_ROOT / "titan" / "ucsb_152_tap_fir.v"]
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

    def test_titan_sudoku_check_benchmark(
        self,
        name: str,
    ) -> FabulousArchitectureConfig:
        """Test Titan Sudoku checker benchmark FABulousArchitecture."""
        logger.info("Testing Titan Sudoku checker benchmark FABulousArchitecture")
        hdl_files = [BENCH_ROOT / "titan" / "sudoku_check.v"]
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

    def test_koios_attention_layer_benchmark(
        self,
        name: str,
    ) -> FabulousArchitectureConfig:
        """Test Koios attention layer benchmark FABulousArchitecture."""
        logger.info("Testing Koios attention layer benchmark FABulousArchitecture")
        hdl_files = [BENCH_ROOT / "koios" / "attention_layer.v"]
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

    def test_koios_conv_layer_benchmark(
        self,
        name: str,
    ) -> FabulousArchitectureConfig:
        """Test Koios convolution layer benchmark FABulousArchitecture."""
        logger.info("Testing Koios convolution layer benchmark FABulousArchitecture")
        hdl_files = [BENCH_ROOT / "koios" / "conv_layer.v"]
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

    def test_koios_tpu_like_small_os_benchmark(
        self,
        name: str,
    ) -> FabulousArchitectureConfig:
        """Test Koios TPU-like small OS benchmark FABulousArchitecture."""
        logger.info("Testing Koios TPU-like small OS benchmark FABulousArchitecture")
        hdl_files = [BENCH_ROOT / "koios" / "tpu_like_small_os.v"]
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

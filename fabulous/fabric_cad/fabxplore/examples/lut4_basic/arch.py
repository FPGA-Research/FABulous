"""FABulous Architecture Synthesizer.

Simple basic LUT4 flow
"""

from __future__ import annotations

from pathlib import Path

from fabulous.fabric_cad.fabxplore.flow.architecture_synthesizer import (
    ArchitectureSynthesizer,
)
from fabulous.fabric_cad.fabxplore.utils.benchmark_generator import (
    BenchmarkGenerator,
    FabulousArchitectureConfig,
)


class FabulousArchitecture(ArchitectureSynthesizer):
    """Concrete implementation of the ArchitectureSynthesizer for FABulous.

    This class implements the synthesis flow for the FABulous architecture, including
    all mapping stages and optimizations. It uses the PyosysBridge to interact with
    the design representation and applies architecture-specific transformations.

    Parameters
    ----------
    debug : bool
        Enable debug mode for verbose logging and intermediate design dumps.
    """

    def __init__(self, debug: bool = False) -> None:
        super().__init__(debug=debug)

        self.x_root = Path(__file__).resolve().parents[2]
        self.my_root: Path = self.x_root / "examples" / "lut4_basic"
        self.bench_out_dir: Path = self.my_root / "out"
        self.nextpnr_exec: Path = Path(
            "/home/hausding/Documents/FABulous/demo_master_thesis/"
            "nextpnr/build/nextpnr-generic"
        )
        self.sta_exec: Path = Path(
            "/home/hausding/Documents/FABulous/demo_master_thesis/sta/sta"
        )

    ### Synthesis and Packing Stages

    def read_hdl(self, config: FabulousArchitectureConfig) -> None:
        """Read the input HDL design into the PyosysBridge."""
        self.design.read_verilog_paths(config.hdl_files, defines=config.defines)
        self.design.run_pass("read_verilog -lib +/fabulous/prims.v")

    def coarse(self, config: FabulousArchitectureConfig) -> None:
        """Run the coarse synthesis stages, including optimizations and mapping."""
        self.design.run_pass(f"hierarchy -check -top {config.top_module}")
        self.design.run_pass("proc")
        self.design.run_pass("flatten")
        self.design.run_pass("tribuf -logic")
        self.design.run_pass("deminout")
        self.design.run_pass("tribuf -logic")
        self.design.run_pass("deminout")
        self.design.run_pass("opt_expr")
        self.design.run_pass("opt_clean")
        self.design.run_pass("check")
        self.design.run_pass("opt -nodffe -nosdff")
        if config.optimize_fsm:
            self.design.run_pass("fsm")
        self.design.run_pass("opt")
        self.design.run_pass("wreduce")
        self.design.run_pass("peepopt")
        self.design.run_pass("opt_clean")
        if config.map_alu_macc_cells:
            self.design.run_pass("alumacc")
        if config.allow_resource_sharing:
            self.design.run_pass("share")
        self.design.run_pass("opt")
        self.design.run_pass("memory -nomap")
        self.design.run_pass("opt_clean")

        self.design_analyzer_pass()

    def synth_fabulous(self, config: FabulousArchitectureConfig) -> None:
        """Run default synth script, but converting FFs."""
        # REGFILE MAP
        self.design.run_pass("memory_libmap -lib +/fabulous/ram_regfile.txt")
        self.design.run_pass("techmap -map +/fabulous/regfile_map.v")

        self.design.run_pass("opt -fast -mux_undef -undriven -fine")
        self.design.run_pass("memory_map")
        self.design.run_pass("opt -undriven -fine")

        # DSP MAP
        self.design_auto_techmap(
            cell_type="$macc_v2",
            techmap_file=Path(f"{self.my_root / 'dsp_map.v'}"),
        )

        # Avoid too large carry chains.
        self.design_auto_techmap(
            cell_type="$alu",
            techmap_file=Path(
                "-map +/techmap.v -map +/fabulous/arith_map.v -D ARITH_ha"
            ),
            min_replacements=10,
            ratio=0.1,
        )

        # Yosys macc cell are pure comb logic, so the clock must be connected
        # afer techmapping, since FABulous MULADD are also clocked.
        self.design_connect_clock(cell_type="MULADD", clock_port="CLK")

        self.design.run_pass("techmap -map +/techmap.v")
        self.design.run_pass("opt -fast")

        self.design.run_pass(
            "iopadmap -bits -outpad $__FABULOUS_OBUF I:PAD "
            "-inpad $__FABULOUS_IBUF O:PAD "
            "-toutpad IO_1_bidirectional_frame_config_pass ~T:I:PAD "
            "-tinoutpad IO_1_bidirectional_frame_config_pass ~T:O:I:PAD A:top"
        )
        self.design.run_pass("techmap -map +/fabulous/io_map.v")

        # No async seq logic.
        self.design_analyzer_pass()
        self.design.run_pass("dffunmap; async2sync")
        self.design.run_pass("dfflegalize -cell $_DFF_P_ 0 -cell $_DLATCH_?_ x")
        self.design.run_pass("techmap -map +/fabulous/latches_map.v")
        self.design.run_pass("techmap -map +/fabulous/ff_map.v")

        # We have here comb loops, nextpnr complained about them,
        # so we basically inserted loop breakers as passthrough latches.
        self.design.run_pass(f"techmap -map {self.my_root / 'custom_map.v'}")
        self.design_connect_clock(cell_type="LUTFF", clock_port="CLK")
        self.design.run_pass("clean")

        # ABC costfunction for MUX2,3,8LUT
        self.design.run_pass("abc9 -luts 69,67,62,58,128,188,256")

        # MAP to MUX8LUT
        self.design_decompose_lut_pass(
            source_lut_widths=[7],
            leaf_lut_width=4,
            mux_verilog_path=self.my_root / "FABULOUS_MUX8.v",
            mux_dependency_paths=[self.project_context.models_pack],
            mux_top_name="FABULOUS_MUX8",
            mux_data_inputs=["I0", "I1", "I2", "I3", "I4", "I5", "I6", "I7"],
            mux_select_inputs=["S0", "S1", "S2"],
            mux_outputs=["O"],
            progress_chunk_size=5,
        )

        # MAP to MUX4LUT
        self.design_decompose_lut_pass(
            source_lut_widths=[6],
            leaf_lut_width=4,
            mux_verilog_path=self.my_root / "FABULOUS_MUX4.v",
            mux_dependency_paths=[self.project_context.models_pack],
            mux_top_name="FABULOUS_MUX4",
            mux_data_inputs=["I0", "I1", "I2", "I3"],
            mux_select_inputs=["S0", "S1"],
            mux_outputs=["O"],
            progress_chunk_size=5,
        )

        # MAP to MUX2LUT
        self.design_decompose_lut_pass(
            source_lut_widths=[5],
            leaf_lut_width=4,
            mux_verilog_path=self.my_root / "FABULOUS_MUX2.v",
            mux_dependency_paths=[self.project_context.models_pack],
            mux_top_name="FABULOUS_MUX2",
            mux_data_inputs=["I0", "I1"],
            mux_select_inputs=["S0"],
            mux_outputs=["O"],
            progress_chunk_size=5,
        )

        self.design.run_pass("clean")

        self.design.run_pass("techmap -D LUT_K=4 -map +/fabulous/cells_map.v")
        self.design.run_pass("clean")

        self.design.run_pass(
            f"hierarchy -top {config.top_module} -check", no_quiet=True
        )
        self.design_analyzer_pass()

    ### Placement, Routing, and Tile Generation Stages

    def build_tile(self, config: FabulousArchitectureConfig) -> None:
        """Run the tile generation, placement, and routing stages."""
        print(self.fpga_model.fabric_dimensions())  # noqa: T201

        # columns=100, rows=150, 15000 Tiles
        self.fpga_model.resize_fabric(
            insert_row_block_after=(1, 2, 2, 67),
            insert_column_block_after=(2, 6, 8, 15),
        )

        print(self.fpga_model.fabric_dimensions())  # noqa: T201

        self.fpga_model.nextpnr_route(
            nextpnr_exec=self.nextpnr_exec,
            check=False,
            log_report=True,
            live_output=True,
            out_dir=config.user_design_out_dir / "pnr",
            extra_args=["--freq", "1.0", "--router", "router2"],
        )

        a = self.netlist_tool_pass(
            tile_name="LUT4AB",
            sub_circuit_map_rules=[
                """
                (* extract_order = 0 *)
                module DLHQ_MUX2_S (
                    input D,
                    input GATE,
                    input A0,
                    input A1,
                    output X
                );
                    wire q;

                    sg13g2_dlhq_1 latch (
                        .D(D),
                        .GATE(GATE),
                        .Q(q)
                    );

                    sg13g2_mux2_1 mux (
                        .A0(A0),
                        .A1(A1),
                        .S(q),
                        .X(X)
                    );
                endmodule
                """
            ],
            add_liberty_cells=[
                """
                cell (DLHQ_MUX2_S) {
                    area : 42.0;
                    pin(D)    { direction : input; }
                    pin(GATE) { direction : input; }
                    pin(A0) { direction : input; }
                    pin(A1) { direction : input; }
                    pin(X) { direction : output; }
                }
                """
            ],
        )

        a.run_sta(
            clk_ports=["UserCLK"],
            period_ns=10.0,
            sta_exec=self.sta_exec,
        )

        print(a.stats)  # noqa: T201
        print(a.area)  # noqa: T201

        print(a.sta_report)  # noqa: T201
        print("\nExtracted slacks:")  # noqa: T201
        print(a.slacks)  # noqa: T201

        print(self.fpga_model.get_config_bits("LUT4AB"))  # noqa: T201

    def write_design(self, config: FabulousArchitectureConfig) -> None:
        """Write the synthesized design to a file."""
        self.design.write_verilog_path(
            config.user_design_out_dir / f"{config.top_module}.v",
            include_attributes=True,
        )
        self.design.write_json_path(
            config.user_design_out_dir / f"{config.top_module}.json"
        )
        self.design_report_summary_pass(
            path=config.user_design_out_dir / f"{config.top_module}.rpt",
            log_report=False,
        )
        self.design.run_pass(
            f"tee -o {config.user_design_out_dir / f'{config.top_module}.stat'} stat",
            no_quiet=True,
        )

    def synthesize(
        self,
        config: FabulousArchitectureConfig,
        pnr: bool = True,
        syth_coarse_only: bool = False,
    ) -> None:
        """Run the full synthesis pipeline for a user design."""
        self.log_info(f"Starting synthesis for top module: {config.top_module}")

        self.read_hdl(config)
        self.coarse(config)

        if syth_coarse_only:
            self.write_design(config)
            self.log_info(
                "Coarse synthesis completed. Skipping mapping and PnR stages."
            )
            return

        self.synth_fabulous(config)

        self.write_design(config)

        self.log_info(f"Synthesis completed for top module: {config.top_module}")

        if pnr:
            self.log_info("Starting placement and routing stages.")
            self.build_tile(config)

    def dse_flow(
        self, benchmark_id: int, syth_coarse_only: bool = False, pnr: bool = True
    ) -> None:
        """Run the entire synthesis flow."""
        sel_test: int = benchmark_id % 17
        bg = BenchmarkGenerator(out_dir=self.bench_out_dir)
        config: FabulousArchitectureConfig = None

        match sel_test:
            case 0:
                config = bg.test_basic_synth_flow("ode")
            case 1:
                config = bg.test_basic_large_or_benchmark("or17_chain")
            case 2:
                config = bg.test_lut32_mixed_benchmark("lut32_mixed")
            case 3:
                config = bg.test_aes_like_sboxes_benchmark("aes_like_sboxes")
            case 4:
                config = bg.test_swm_micro24_benchmark("swm_micro24")
                config.defines = ["-DIOS=0 -DCASCADES=0"]
            case 5:
                config = bg.test_vtr_riscv_core_benchmark("riscv_core")
            case 6:
                config = bg.test_vtr_sha1_benchmark("sha1")
            case 7:
                config = bg.test_vtr_enet_benchmark("enet")
            case 8:
                config = bg.test_vtr_ode_benchmark("ode")
            case 9:
                config = bg.test_vtr_aes_cipher_top_benchmark("aes_cipher_top")
            case 10:
                config = bg.test_vtr_mm3_benchmark("mm3")
            case 11:
                config = bg.test_titan_wb_conmax_top_benchmark("wb_conmax_top")
            case 12:
                config = bg.test_titan_ucsb_152_tap_fir_benchmark("ucsb_152_tap_fir")
            case 13:
                config = bg.test_titan_sudoku_check_benchmark("sudoku_check")
            case 14:
                config = bg.test_koios_attention_layer_benchmark("attention_layer")
                config.defines = ["-DVECTOR_DEPTH=32 -DVECTOR_BITS=512 -DNUM_WORDS=16"]
            case 15:
                config = bg.test_koios_conv_layer_benchmark("conv_layer")
                config.defines = [
                    "-DDWIDTH=4 -DAWIDTH=6 -DMEM_SIZE=64 "
                    "-DDESIGN_SIZE=2 -DMAT_MUL_SIZE=2 "
                    "-DMASK_WIDTH=2 -DLOG2_MAT_MUL_SIZE=1"
                ]
            case 16:
                config = bg.test_koios_tpu_like_small_os_benchmark("tpu_like_small_os")
                config.defines = ["-DDWIDTH=2 -DAWIDTH=6"]

        self.synthesize(config, syth_coarse_only=syth_coarse_only, pnr=pnr)
        self.clear_flow()

    def run_flow(self) -> None:
        """Run the DSE loop over multiple benchmarks."""
        b = 10
        for benchmark_id in range(b, b + 1):
            self.dse_flow(benchmark_id=benchmark_id, syth_coarse_only=False, pnr=True)

"""FABulous Architecture Synthesizer.

This module defines the core synthesis flow for the FABulous architecture,
including the `FabulousArchitecture` class which implements the
`ArchitectureSynthesizer` interface. The `FabulousArchitecture` class provides
concrete implementations of the synthesis stages, such as flattening, coarse
optimizations, and various mapping passes for RAM, gates, IO pads, flip-flops,
and LUTs. It also includes methods for generating architecture-specific primitives
and switch-matrix resources. The `synthesize` method orchestrates the entire synthesis
process, producing an `ArchitectureMapResult` that encapsulates the results of the
mapping and optimization stages. This module serves as the central point for defining
the synthesis flow and architecture-specific transformations for FABulous.
"""

from pathlib import Path

from fabulous.fabric_cad.fabxplore.examples.fabr_v2.models import (
    FabulousArchitectureConfig,
)
from fabulous.fabric_cad.fabxplore.examples.fabr_v2.tests.run_tests import (
    test_aes_like_sboxes_benchmark,
    test_basic_large_or_benchmark,
    test_basic_synth_flow,
    test_lut32_mixed_benchmark,
)
from fabulous.fabric_cad.fabxplore.flow.architecture_synthesizer import (
    ArchitectureSynthesizer,
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
        self.my_root = self.x_root / "examples" / "fabr_v2"

    def read_hdl(self, config: FabulousArchitectureConfig) -> None:
        """Read the input HDL design into the PyosysBridge."""
        self.design.read_verilog_paths(config.hdl_files)
        self.design.run_pass("read_verilog -lib +/fabulous/prims.v")

    def begin(self, config: FabulousArchitectureConfig) -> None:
        """Prepare the design and initialize the synthesis flow."""
        self.design.run_pass(f"hierarchy -check -top {config.top_module}")
        self.design.run_pass("proc")

    def flatten(self) -> None:
        """Flatten hierarchy to simplify downstream mapping passes."""
        self.design.run_pass("flatten")
        self.design.run_pass("tribuf -logic")
        self.design.run_pass("deminout")

    def coarse(self, config: FabulousArchitectureConfig) -> None:
        """Run coarse-grain synthesis optimizations on the design."""
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

    def map_ram(self) -> None:
        """Map inferred memory structures to RAM primitives."""
        self.design.run_pass("memory_libmap -lib +/fabulous/ram_regfile.txt")
        self.design.run_pass("techmap -map +/fabulous/regfile_map.v")

    def map_ffram(self) -> None:
        """Map FF-based RAM structures when dedicated RAM is unavailable."""
        self.design.run_pass("opt -fast -mux_undef -undriven -fine")
        self.design.run_pass("memory_map")
        self.design.run_pass("opt -undriven -fine")

    def map_gates(self, config: FabulousArchitectureConfig) -> None:
        """Map generic logic into technology-specific gate primitives."""
        self.design.run_pass("opt -full")

        if config.map_carry_chains:
            self.design.run_pass("simplemap")
            self.design_chain_mapper_pass(chunk_size=5)
            self.design.run_pass("techmap -map +/techmap.v")

        self.design_morph_tile_pass(
            tile_verilog_path=self.my_root / "arch_rtl" / "FLUT5_1P_2PS.v",
            tile_top_name="FLUT5_1P_2PS",
            tile_inputs=["I0", "I1", "I2", "A0", "B0", "S", "Ci"],
            tile_outputs=["O0", "O1", "Co"],
            enabled_circuits=["chain"],
            tile_config_prefixes=["ConfigBits"],
            progress_chunk_size=5,
            conf2bel=True,
        )

        self.design.run_pass("opt -fast")

    def map_iopad(self) -> None:
        """Map top-level IO signals to architecture IO pad primitives."""
        self.design.run_pass("opt -full")
        self.design.run_pass(
            "iopadmap -bits -outpad $__FABULOUS_OBUF I:PAD "
            "-inpad $__FABULOUS_IBUF O:PAD "
            "-toutpad IO_1_bidirectional_frame_config_pass ~T:I:PAD "
            "-tinoutpad IO_1_bidirectional_frame_config_pass ~T:O:I:PAD A:top"
        )
        self.design.run_pass("techmap -map +/fabulous/io_map.v")

    def map_ffs(self) -> None:
        """Map sequential elements to architecture flip-flop primitives."""
        self.design.run_pass("dfflegalize -cell $_DFF_P_ 0 -cell $_DLATCH_?_ x")
        self.design.run_pass("techmap -map +/fabulous/latches_map.v")
        self.design.run_pass("techmap -map +/fabulous/ff_map.v")
        self.design.run_pass("clean")

    def map_luts(self) -> None:
        """Map combinational logic into LUT resources."""
        self.design_lut_mapper_pass(
            max_lut_size=8,
            use_select_as_data_in_pair_mode=True,
            sharing_penalty_factor=3,
            size_penalty_factor=0.7,
            larger_lut_discount_factor=0.7,
            backend="abc9",
        )

        self.design_decompose_lut_pass(
            source_lut_widths=[6, 7, 8],
            leaf_lut_width=5,
            mux_verilog_path=self.my_root / "arch_rtl" / "MUX8LUT_frame_config_mux.v",
            mux_dependency_paths=[self.project_context.models_pack],
            mux_top_name="MUX8LUT_frame_config_mux",
            mux_data_inputs=["A", "B", "C", "D", "E", "F", "G", "H"],
            mux_select_inputs=["S0", "S1", "S2", "S3"],
            mux_outputs=["M_AB", "M_AD", "M_AH", "M_EF"],
            mux_config_prefixes=["ConfigBits"],
            progress_chunk_size=5,
            conf2bel=True,
        )

        self.design_lut_combinator_pass(
            passthrough=True,
            use_select_as_data_in_pair_mode=True,
            reorder_leftover_luts=True,
        )

        # Can be called multiple times with different overlay
        # modules to support.

        mode: bool = False
        if mode:
            self.design_lut_layering_pass(
                overlay_top_name="mux4",
                overlay_verilog_paths=[
                    Path(self.x_root / "benchmarks" / "verilog_rtl" / "mux4" / "mux4.v")
                ],
            )

        self.design_morph_tile_pass(
            tile_verilog_path=self.my_root / "arch_rtl" / "FLUT5_1P_2PS.v",
            tile_top_name="FLUT5_1P_2PS",
            tile_inputs=["I0", "I1", "I2", "A0", "B0", "S", "Ci"],
            tile_outputs=["O0", "O1", "Co"],
            enabled_circuits=["lut", "frac_lut"],
            circuit_options={"lut": {"widths": [6]}},
            tile_config_prefixes=["ConfigBits"],
            progress_chunk_size=5,
            conf2bel=True,
        )

        self.design_absorb_registers_pass(
            cell_types=["FLUT5_1P_2PS"],
            rules=[
                {
                    "side": "output",
                    "cell_type": "FLUT5_1P_2PS",
                    "comb_port": "O0",
                    "seq_port": "Q0",
                    "remove_disconnected_comb_port": True,
                    "include_enable_ff": True,
                    "include_reset_ff": True,
                    "attributes": {"FF_USED": 1},
                },
                {
                    "side": "output",
                    "cell_type": "FLUT5_1P_2PS",
                    "comb_port": "O1",
                    "seq_port": "Q1",
                    "remove_disconnected_comb_port": True,
                    "include_enable_ff": True,
                    "include_reset_ff": True,
                    "attributes": {"FF_USED": 1},
                },
            ],
            progress_chunk_size=5,
        )

        self.design_materialize_registers_pass(
            tile_verilog_path=self.my_root / "arch_rtl" / "FLUT5_1P_2PS.v",
            tile_top_name="FLUT5_1P_2PS",
            tile_inputs=[
                "I0",
                "I1",
                "I2",
                "A0",
                "B0",
                "S",
                "Ci",
                "EN",
                "SR",
                "UserCLK",
            ],
            tile_outputs=[
                "Q0",
                "Q1",
            ],
            tile_config_prefixes=[
                "ConfigBits",
            ],
            lanes=[
                {
                    # FF.D -> I0, Q0 replaces FF.Q
                    "data_port": "I0",
                    "output_port": "Q0",
                    "clock_port": "UserCLK",
                    # Plain FFs get EN=1 and SR=0.
                    # Enabled/reset FFs can also be materialized if compatible.
                    "include_enable_ff": True,
                    "enable_tile_port": "EN",
                    "enable_neutral": 1,
                    "include_reset_ff": True,
                    "reset_tile_port": "SR",
                    "reset_neutral": 0,
                    "reset_kind": "sync",
                    "reset_value": 0,
                    "attributes": {"FF_USED": 123, "ANOTHER_ATTR": 456},
                },
                {
                    # FF.D -> I1, Q1 replaces FF.Q
                    "data_port": "I1",
                    "output_port": "Q1",
                    "clock_port": "UserCLK",
                    "include_enable_ff": True,
                    "enable_tile_port": "EN",
                    "enable_neutral": 1,
                    "include_reset_ff": True,
                    "reset_tile_port": "SR",
                    "reset_neutral": 0,
                    "reset_kind": "sync",
                    "reset_value": 0,
                    "attributes": {"FF_USED": 1234, "ANOTHER_ATTR": 5678},
                },
            ],
            pack_multiple_ffs_per_tile=True,
            progress_chunk_size=5,
            auto_config=True,
            conf2bel=True,
        )

        self.design_placement_hints_pass(
            rules=[
                {
                    "kind": "linear_chain",
                    "name": "carry",
                    "cell_types": ["FLUT5_1P_2PS"],
                    "source_port": "Co",
                    "sink_port": "Ci",
                    "allow_branching": True,
                    "min_length": 4,
                },
            ],
            progress_chunk_size=5,
        )

    def build_tile(self) -> None:
        """Generate the FABulous tile files used by this architecture."""
        self.pnr_tile_builder_pass(
            tile_name="LUT5F",
            bels=[
                {
                    "verilog_path": self.my_root / "arch_rtl" / "FLUT5_1P_2PS.v",
                    "prefixes": [
                        "LA_",
                        "LB_",
                        "LC_",
                        "LD_",
                        "LE_",
                        "LF_",
                        "LG_",
                        "LH_",
                    ],
                    "add_as_custom_prim": True,
                },
                {
                    "verilog_path": (
                        self.my_root / "arch_rtl" / "MUX8LUT_frame_config_mux.v"
                    ),
                    "prefixes": ["LM_"],
                    "add_as_custom_prim": True,
                },
            ],
            use_fabulous_auto=False,
            base_csv_includes=["./../include/Base.csv"],
            base_list_includes=["../include/Base.list"],
            input_fanin=6,
            output_fanin=3,
            min_input_fanin=2,
            min_output_fanin=2,
            config_bit_margin=0,
            derive_sources_from_base=True,
            cover_unconnected_outputs=True,
            emit_constants_if_missing=True,
            allow_bel_output_feedback_sources=True,
            register_in_fabric=True,
            track_progress=True,
            progress_chunk_size=5,
            register_tile_in_fpga_model=True,
        )

        self.pnr_switch_matrix_pattern_pass(
            tile_name="LUT5F",
            input_fanin=3,
            include_bel_output_sources=True,
            include_constant_sources=True,
            output_fanin=3,
            cover_unconnected_matrix_rows=True,
            routing_pip_pattern="wilton",
            routing_pip_fs=4,
            generate_straight_routing_pips=True,
            generate_turn_routing_pips=True,
            hierarchy_enabled=False,
            hierarchy_levels=[2, 2],
            hierarchy_jump_prefix="J_LOCAL",
            hierarchy_replace_direct_input_pips=True,
            delay=8.0,
            progress_chunk_size=5,
        )

        self.pnr_switch_block_factorizer_pass(
            tile_name="LUT5F",
            global_reduction=1,
            reduction_rules=[
                {"from_fanin": 16, "to_fanin": 8},
                {"from_fanin": 8, "to_fanin": 4},
            ],
            min_mux_fanin_to_factorize=8,
            jump_prefix="J_FAC",
            max_added_jump_wires=None,
            track_progress=True,
        )

        self.pnr_routing_demand_evaluator_pass(
            tile_name="LUT5F",
            demand_profile="full",
            demand_iterations=1000,
            random_demand_ratio=0.25,
            seed=1,
            opt=False,
            optimizer="greedy",
            opt_target_pip_reduction=0.1,
            opt_max_soft_failure_rate=0.1,
            opt_max_hard_failure_rate=0.1,
            opt_use_baseline_failure_rates=True,
            opt_clean_mux=True,
            opt_power_of_two_muxes=False,
            opt_write_back=True,
            opt_max_iterations=400,
            report_max_soft_failure_rate=0.1,
            router="pathfinder",
            router_max_iterations=30,
            router_present_cost_multiplier=1.3,
            router_history_cost_increment=1.0,
            router_base_resource_capacity=1,
            fanout_targets=[2, 4, 8],
            max_net_sinks=8,
            config_bit_capacity_override=None,
            config_bit_margin=0,
            track_progress=True,
            progress_chunk_size=5,
        )

        self.fpga_model.nextpnr_route(
            nextpnr_exec=Path(
                "/home/hausding/Documents/FABulous/demo_master_thesis"
                "/nextpnr/build/nextpnr-generic"
            ),
            check=False,
            log_report=True,
        )

    def map_cells(self) -> None:
        """Run final cell-level mapping and legalization passes."""
        self.design.run_pass("techmap -D LUT_K=5 -map +/fabulous/cells_map.v")
        self.design.run_pass("clean")

    def check(self, config: FabulousArchitectureConfig) -> None:
        """Validate the mapped design and report structural issues."""
        self.design.run_pass(f"hierarchy -top {config.top_module} -check")
        self.design.run_pass("stat")
        self.design_analyzer_pass()

    def write_verilog_path(self, config: FabulousArchitectureConfig) -> None:
        """Write the synthesized design to a Verilog file."""
        config.user_design_out_dir.mkdir(parents=True, exist_ok=True)
        self.design.write_verilog_path(
            config.user_design_out_dir / f"{config.top_module}.v",
            include_attributes=True,
        )

    def write_json_path(self, config: FabulousArchitectureConfig) -> None:
        """Write a JSON report of the synthesis results."""
        config.user_design_out_dir.mkdir(parents=True, exist_ok=True)
        self.design.write_json_path(
            config.user_design_out_dir / f"{config.top_module}.json"
        )

    def write_report_path(self, config: FabulousArchitectureConfig) -> None:
        """Write a report summarizing the results."""
        config.user_design_out_dir.mkdir(parents=True, exist_ok=True)
        self.design_report_summary_pass(
            path=config.user_design_out_dir / f"{config.top_module}.rpt",
            log_report=False,
        )

    def synthesize(self, config: FabulousArchitectureConfig) -> None:
        """Run the full synthesis pipeline for a user design."""
        self.read_hdl(config)
        self.begin(config)
        self.flatten()
        self.coarse(config)
        if config.map_ram_cells:
            self.map_ram()
        self.map_ffram()
        self.map_gates(config)
        if config.map_io_pads:
            self.map_iopad()
        self.map_ffs()
        self.map_luts()
        self.map_cells()
        self.check(config)
        self.build_tile()

        self.write_verilog_path(config)
        self.write_json_path(config)
        self.write_report_path(config)

    def run_flow(self) -> None:
        """Run the entire synthesis flow."""
        # TODO: Implement timing driven optimizations (weight match) subgraph
        # matching for critical path optimization
        # TODO: Explain how to do simulation and verification.
        # TODO: sequential pattern graph.

        sel_test: int = 2
        config: FabulousArchitectureConfig = None
        match sel_test:
            case 0:
                config = test_basic_synth_flow()
            case 1:
                config = test_basic_large_or_benchmark()
            case 2:
                config = test_lut32_mixed_benchmark()
            case 3:
                config = test_aes_like_sboxes_benchmark()

        self.synthesize(config)

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

from fabulous.fabric_cad.fabxplore.pyosys.pyosys_bridge import (
    PyosysBridge,
)
from fabulous.fabric_cad.fabxplore.synthesizer.core.architecture import (
    ArchitectureSynthesizer,
)
from fabulous.fabric_cad.fabxplore.synthesizer.core.models import (
    ArchitectureMapResult,
    FabulousArchitectureMapConfig,
)


class FabulousArchitecture(ArchitectureSynthesizer):
    """Concrete implementation of the ArchitectureSynthesizer for FABulous.

    This class implements the synthesis flow for the FABulous architecture, including
    all mapping stages and optimizations. It uses the PyosysBridge to interact with
    the design representation and applies architecture-specific transformations.

    Parameters
    ----------
    config : FabulousArchitectureMapConfig
        Configuration parameters for the architecture mapping process.
    debug : bool, optional
        Enable debug mode for verbose logging and intermediate design dumps.
    """

    def __init__(
        self, config: FabulousArchitectureMapConfig, debug: bool = False
    ) -> None:
        self.config = config
        self.debug = debug

        self.map_result: ArchitectureMapResult | None = None

        self.design: PyosysBridge = PyosysBridge(debug=self.debug)

        self._read_hdl()

    def _read_hdl(self) -> None:
        """Read the input HDL design into the PyosysBridge."""
        self.design.read_verilog_paths(self.config.hdl_files)
        self.design.run_pass("read_verilog -lib +/fabulous/prims.v")

    def begin(self) -> None:
        """Prepare the design and initialize the synthesis flow."""
        self.design.run_pass(f"hierarchy -check -top {self.config.top_module}")
        self.design.run_pass("proc")

    def flatten(self) -> None:
        """Flatten hierarchy to simplify downstream mapping passes."""
        self.design.run_pass("flatten")
        self.design.run_pass("tribuf -logic")
        self.design.run_pass("deminout")

    def coarse(self) -> None:
        """Run coarse-grain synthesis optimizations on the design."""
        self.design.run_pass("tribuf -logic")
        self.design.run_pass("deminout")
        self.design.run_pass("opt_expr")
        self.design.run_pass("opt_clean")
        self.design.run_pass("check")
        self.design.run_pass("opt -nodffe -nosdff")
        if self.config.optimize_fsm:
            self.design.run_pass("fsm")
        self.design.run_pass("opt")
        self.design.run_pass("wreduce")
        self.design.run_pass("peepopt")
        self.design.run_pass("opt_clean")
        if self.config.map_alu_macc_cells:
            self.design.run_pass("alumacc")
        if self.config.allow_resource_sharing:
            self.design.run_pass("share")
        self.design.run_pass("opt")
        self.design.run_pass("memory -nomap")
        self.design.run_pass("opt_clean")

    def map_ram(self) -> None:
        """Map inferred memory structures to RAM primitives."""
        self.design.run_pass("memory_libmap -lib +/fabulous/ram_regfile.txt")
        self.design.run_pass("techmap -map +/fabulous/regfile_map.v")

    def map_ffram(self) -> None:
        """Map FF-based RAM structures when dedicated RAM is unavailable."""
        self.design.run_pass("opt -fast -mux_undef -undriven -fine")
        self.design.run_pass("memory_map")
        self.design.run_pass("opt -undriven -fine")

    def map_gates(self) -> None:
        """Map generic logic into technology-specific gate primitives."""
        self.design.run_pass("opt -full")
        self.design.run_pass("techmap -map +/techmap.v")
        if self.config.map_carry_chains:
            self.design.run_pass("techmap -map +/fabulous/arith_map.v -D ARITH_ha")
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
        self.design.run_pass("abc -lut 5 -dress")
        self.design.run_pass("clean")

    def map_cells(self) -> None:
        """Run final cell-level mapping and legalization passes."""
        self.design.run_pass("techmap -D LUT_K=5 -map +/fabulous/cells_map.v")
        self.design.run_pass("clean")

    def check(self) -> None:
        """Validate the mapped design and report structural issues."""
        self.design.run_pass("hierarchy -check")
        self.design.run_pass("stat")

    def synthesize(self) -> None:
        """Run the full synthesis pipeline for a user design."""
        self.begin()
        self.flatten()
        self.coarse()
        if self.config.map_ram_cells:
            self.map_ram()
        self.map_ffram()
        self.map_gates()
        if self.config.map_io_pads:
            self.map_iopad()
        self.map_ffs()
        self.map_luts()
        self.map_cells()
        self.check()

    def write_verilog_path(self) -> None:
        """Write the synthesized design to a Verilog file."""
        self.config.user_design_out_dir.mkdir(parents=True, exist_ok=True)
        self.design.write_verilog_path(
            self.config.user_design_out_dir / f"{self.config.top_module}.v"
        )

    def write_json_path(self) -> None:
        """Write a JSON report of the synthesis results."""
        self.config.user_design_out_dir.mkdir(parents=True, exist_ok=True)
        self.design.write_json_path(
            self.config.user_design_out_dir / f"{self.config.top_module}.json"
        )

    def generate_primitives(self) -> None:
        """Generate primitive definitions required by this architecture."""

    def generate_switch_matrix(self) -> None:
        """Generate switch-matrix resources for routing integration."""

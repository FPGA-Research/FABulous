"""The Pyosys LutCombinator pass.

It identifies and combines LUTs in a given design to optimize for area and performance.
The pass supports various configurations, including different LUT architectures,
passthrough options, and matching modes.
"""

from dataclasses import dataclass

from fabulous.fabric_cad.fabxplore.lut_combinator.core.combinator import (
    FracLutArchitecture,
    LutCombinator,
    LutCombinatorConfig,
)
from fabulous.fabric_cad.fabxplore.lut_combinator.core.models import (
    LutSpec,
    MappingResult,
    MatchingMode,
)
from fabulous.fabric_cad.fabxplore.pyosys.pyosys_bridge import PyosysBridge


@dataclass(frozen=True)
class LutCombinatorPass:
    """Pyosys pass to combine LUTs in a design using the LutCombinator.

    Attributes
    ----------
    frac_lut_size : int
        The size of the fractional LUTs to be used in the architecture.
    num_shared_inputs : int
        The number of shared inputs allowed in the LUT architecture.
    lut_name : str
        The name to be used for the generated LUT cells.
    top_name : str
        The name of the top module in the design to be processed.
    passthrough : bool
        Whether to allow passthrough of non-mapped full LUTs.
    mode : MatchingMode
        The matching mode to be used for combining LUTs.
    """

    frac_lut_size: int = 4
    num_shared_inputs: int = 3
    lut_name: str = "FRAC_LUT"
    top_name: str = "top"
    passthrough: bool = False
    mode: MatchingMode = MatchingMode.MAXIMAL

    def run_on(self, design: PyosysBridge) -> MappingResult:
        """Run the LutCombinator pass on the given design.

        Parameters
        ----------
        design : PyosysBridge
            The design to be processed by the LutCombinator.

        Returns
        -------
        MappingResult
            The result of the LUT combination process.
        """
        frac_arch = FracLutArchitecture(
            frac_lut_size=self.frac_lut_size,
            num_shared_inputs=self.num_shared_inputs,
            name=self.lut_name,
        )

        cfg = LutCombinatorConfig(
            architecture=frac_arch,
            top_name=self.top_name,
            lut_spec=LutSpec(),
            passthrough=self.passthrough,
            mode=self.mode,
        )

        comb = LutCombinator(cfg)
        result: MappingResult = comb.map_from_design(design, inplace=True)
        design.read_verilog_string(
            self.build_frac_behavioral_model(),
            blackbox=True,
        )

        return result

    def build_frac_behavioral_model(self) -> str:
        """Build a FRAC-cell behavioral Verilog model from combinator config.

        The emitted model follows the common FRAC LUT interface used by the
        mapper output:
        - inputs: shared ``I*``, private ``A*``/``B*``, select ``S``
        - outputs: ``O0`` and ``O1``
        - parameters: ``LUT_SIZE``, ``NUM_SHARED_INPUTS``, ``L0_*``/``L1_*``

        Returns
        -------
        str
            Verilog module text implementing FRAC-cell behavior.
        """
        k: int = self.frac_lut_size
        s: int = self.num_shared_inputs
        p: int = k - s
        init_width: int = 1 << k

        shared_ports: list[str] = [f"I{i}" for i in range(s)]
        a_ports: list[str] = [f"A{i}" for i in range(p)]
        b_ports: list[str] = [f"B{i}" for i in range(p)]
        all_ports: list[str] = shared_ports + a_ports + b_ports + ["S", "O0", "O1"]

        idx0_bits: list[str] = shared_ports + a_ports
        idx1_bits: list[str] = shared_ports + b_ports
        idx0_expr: str = ", ".join(reversed(idx0_bits))
        idx1_expr: str = ", ".join(reversed(idx1_bits))

        lines: list[str] = [f"module {self.lut_name}({', '.join(all_ports)});"]
        if shared_ports:
            lines.append(f"  input {', '.join(shared_ports)};")
        if a_ports:
            lines.append(f"  input {', '.join(a_ports)};")
        if b_ports:
            lines.append(f"  input {', '.join(b_ports)};")
        lines.append("  input S;")
        lines.append("  output O0, O1;")
        lines.append('  parameter L0_CELL_ID = "";')
        lines.append('  parameter L1_CELL_ID = "";')
        lines.append(f"  parameter [{init_width - 1}:0] L0_INIT = {init_width}'b0;")
        lines.append(f"  parameter [{init_width - 1}:0] L1_INIT = {init_width}'b0;")
        lines.append(f'  parameter LUT_SIZE = "{k}";')
        lines.append(f'  parameter NUM_SHARED_INPUTS = "{s}";')
        lines.append(f"  wire [{k - 1}:0] _idx0 = {{{idx0_expr}}};")
        lines.append(f"  wire [{k - 1}:0] _idx1 = {{{idx1_expr}}};")
        lines.append("  wire _l0 = L0_INIT[_idx0];")
        lines.append("  wire _l1 = L1_INIT[_idx1];")
        lines.append("  assign O0 = S ? _l1 : _l0;")
        lines.append("  assign O1 = _l1;")
        lines.append("endmodule")

        return "\n".join(lines) + "\n"

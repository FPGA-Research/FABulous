"""The Pyosys LutCombinator pass.

It identifies and combines LUTs in a given design to optimize for area and performance.
The pass supports various configurations, including different LUT architectures,
passthrough options, and matching modes.
"""

from dataclasses import dataclass

from fabulous.fabric_cad.fabxplore.modules.lut_combinator.core.combinator import (
    FracLutArchitecture,
    LutCombinator,
    LutCombinatorConfig,
)
from fabulous.fabric_cad.fabxplore.modules.lut_combinator.core.models import (
    LutSpec,
    MappingResult,
    MatchingMode,
)
from fabulous.fabric_cad.fabxplore.pyosys.pyosys_bridge import PyosysBridge
from fabulous.fabric_cad.fabxplore.pyosys.synth_pass import SynthPass


@dataclass
class LutCombinatorPass(SynthPass):
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
    use_select_as_data_in_pair_mode : bool
        Whether to enable the select-as-data dual-LUT pairing mode for more
        flexible mappings.
    """

    frac_lut_size: int = 4
    num_shared_inputs: int = 3
    lut_name: str = "FRAC_LUT"
    top_name: str = "top"
    passthrough: bool = False
    mode: MatchingMode = MatchingMode.MAXIMAL
    use_select_as_data_in_pair_mode: bool = False

    _result: MappingResult | None = None

    def run_on(self, design: PyosysBridge) -> None:
        """Run the LutCombinator pass on the given design.

        Parameters
        ----------
        design : PyosysBridge
            The design to be processed by the LutCombinator.
        """
        frac_arch = FracLutArchitecture(
            frac_lut_size=self.frac_lut_size,
            num_shared_inputs=self.num_shared_inputs,
            name=self.lut_name,
            use_select_as_data_in_pair_mode=self.use_select_as_data_in_pair_mode,
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
        frac_model = frac_arch.build_behavioral_model()
        design.read_verilog_string(frac_model.to_verilog(), blackbox=True)

        self._result = result

    @property
    def report_summary(self) -> str:
        """Return a summary report of the LUT combination results."""
        return self._result.report_summary if self._result else "No result available."

    @property
    def result_data(self) -> MappingResult | None:
        """Return the MappingResult data from the LUT combination pass.

        Returns
        -------
        MappingResult | None
            The result of the LUT combination, or None if not available.
        """
        return self._result

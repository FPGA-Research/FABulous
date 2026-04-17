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
    lut_name: str = "FRAC_LUT5"
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
        return comb.map_from_design(design, inplace=True)

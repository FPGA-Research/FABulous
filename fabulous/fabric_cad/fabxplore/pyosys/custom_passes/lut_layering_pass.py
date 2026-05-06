"""Pyosys custom pass wrapper for LUT layering."""

from dataclasses import dataclass, field
from pathlib import Path

from fabulous.fabric_cad.fabxplore.modules.lut_combinator.core.architecture import (
    FracLutArchitecture,
)
from fabulous.fabric_cad.fabxplore.modules.lut_combinator.core.models import (
    LutSpec,
    MappingResult,
)
from fabulous.fabric_cad.fabxplore.modules.lut_layering.core.layerer import (
    LutLayerer,
)
from fabulous.fabric_cad.fabxplore.modules.lut_layering.core.models import (
    LutLayeringConfig,
    LutLayeringResult,
)
from fabulous.fabric_cad.fabxplore.pyosys.pyosys_bridge import PyosysBridge
from fabulous.fabric_cad.fabxplore.pyosys.synth_pass import SynthPass


@dataclass
class LutLayeringPass(SynthPass):
    """Inject a second LUT-mapped design into leftover FRAC LUT capacity.

    Attributes
    ----------
    overlay_verilog_paths : list[Path]
        Verilog source files for the overlay design.
    overlay_top_name : str
        Top module name of the overlay design.
    base_mapping : MappingResult
        Latest LUT-combinator result for the already packed base design.
    architecture : FracLutArchitecture
        FRAC architecture used to rebuild changed packed cells.
    top_name : str
        Base design top module name.
    overlay_prefix : str
        Prefix for overlay ports, netnames, and cells. Use a unique value for
        each repeated layer when this low-level pass is used directly.
    base_prefix : str | None
        Optional prefix for base ports and netnames. For repeated layering,
        apply this only on the first layer and pass ``None`` on later layers so
        the already-prefixed base is not prefixed again.
    lut_spec : LutSpec
        LUT parser convention for the overlay netlist.
    overlay_lut_size : int | None
        Manual maximum LUT size for overlay mapping. If set, skip the
        inventory-aware retry loop.
    overlay_mapper_max_tries : int
        Number of inventory-aware ABC9 cost-vector attempts before fallback.
    overlay_mapper_cost_scale : int
        Integer baseline for generated ABC9 LUT costs.
    overlay_mapper_size_penalty : float
        Compactness preference strength for larger LUTs in early attempts.
    overlay_mapper_retry_penalty : float
        Larger-LUT penalty multiplier used to push later attempts toward LUT2.
    overlay_mapper_fallback_lut_size : int
        Final forced maximum LUT size if inventory-aware attempts fail.
    debug : bool
        Enable verbose output in the temporary overlay pyosys bridge.
    """

    overlay_verilog_paths: list[Path]
    overlay_top_name: str
    base_mapping: MappingResult
    architecture: FracLutArchitecture
    top_name: str
    overlay_prefix: str = "design1_"
    base_prefix: str | None = "design0_"
    lut_spec: LutSpec = field(default_factory=LutSpec)
    overlay_lut_size: int | None = None
    overlay_mapper_max_tries: int = 4
    overlay_mapper_cost_scale: int = 100
    overlay_mapper_size_penalty: float = 1.4
    overlay_mapper_retry_penalty: float = 1.8
    overlay_mapper_fallback_lut_size: int = 2
    debug: bool = False

    _verilog_model: str = ""
    _result: LutLayeringResult | None = None

    def run_on(self, design: PyosysBridge) -> None:
        """Run LUT layering on the given design.

        Parameters
        ----------
        design : PyosysBridge
            Already packed base design to mutate in place.
        """
        config = LutLayeringConfig(
            overlay_verilog_paths=self.overlay_verilog_paths,
            overlay_top_name=self.overlay_top_name,
            base_mapping=self.base_mapping,
            architecture=self.architecture,
            top_name=self.top_name,
            overlay_prefix=self.overlay_prefix,
            base_prefix=self.base_prefix,
            lut_spec=self.lut_spec,
            overlay_lut_size=self.overlay_lut_size,
            overlay_mapper_max_tries=self.overlay_mapper_max_tries,
            overlay_mapper_cost_scale=self.overlay_mapper_cost_scale,
            overlay_mapper_size_penalty=self.overlay_mapper_size_penalty,
            overlay_mapper_retry_penalty=self.overlay_mapper_retry_penalty,
            overlay_mapper_fallback_lut_size=self.overlay_mapper_fallback_lut_size,
            debug=self.debug,
        )
        layerer = LutLayerer(config)
        self._result = layerer.map_from_design(design, inplace=True)

        frac_model = self.architecture.build_behavioral_model()
        self._verilog_model = frac_model.to_verilog()
        design.read_verilog_string(self._verilog_model, blackbox=True)

    @property
    def report_summary(self) -> str:
        """Return the layering report summary.

        Returns
        -------
        str
            Report text if the pass has run.
        """
        return self._result.report_summary if self._result else "No result available."

    @property
    def result_data(self) -> LutLayeringResult | None:
        """Return the latest structured layering result.

        Returns
        -------
        LutLayeringResult | None
            Latest result if available.
        """
        return self._result

    @property
    def verilog_model(self) -> str:
        """Return the FRAC LUT behavioral model used after layering.

        Returns
        -------
        str
            Behavioral Verilog model string.
        """
        return self._verilog_model

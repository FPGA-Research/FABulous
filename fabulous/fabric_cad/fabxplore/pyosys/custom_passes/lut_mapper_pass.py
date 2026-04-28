"""Pyosys pass wrapper for architecture-aware ABC LUT mapping."""

from dataclasses import dataclass

from fabulous.fabric_cad.fabxplore.modules.lut_mapper.core.mapper import LutMapper
from fabulous.fabric_cad.fabxplore.modules.lut_mapper.core.models import (
    LutMapperBackend,
    LutMapperConfig,
    LutMapperResult,
)
from fabulous.fabric_cad.fabxplore.pyosys.pyosys_bridge import PyosysBridge
from fabulous.fabric_cad.fabxplore.pyosys.synth_pass import SynthPass


@dataclass
class LutMapperPass(SynthPass):
    """Pyosys pass that runs ABC with architecture-aware LUT costs.

    Attributes
    ----------
    base_lut_size : int
        Size ``K`` of the internal LUT fragments in the target fractional LUT.
    num_shared_inputs : int
        Nominal shared inputs between the two internal LUT fragments.
    use_select_as_data_in_pair_mode : bool
        Whether the cost model should account for select-as-data pair mode as
        one additional effective private input.
    max_lut_size : int
        Largest LUT width ABC may generate.
    backend : LutMapperBackend | str
        Yosys backend used for LUT mapping. Supported values are ``"abc"`` and
        ``"abc9"``.
    sharing_penalty_factor : float
        Multiplier for the required-shared-input pair table.
    size_penalty_factor : float
        Multiplier for the unused-capacity pair table.
    pair_discount_strength : float
        Maximum cost discount for LUT widths that are easy to pair later.
    larger_lut_base_multiplier : float
        Multiplicative growth factor for LUT widths greater than
        ``base_lut_size``.
    larger_lut_discount_factor : float
        Per-extra-input discount for larger composed LUTs.
    cost_scale : int
        Base integer cost scale for analytical costs.
    min_cost : int
        Minimum emitted ABC cost.
    max_cost : int | None
        Optional maximum emitted ABC cost.
    raw_cost_vector : tuple[int | float, ...] | None
        Optional direct ABC cost vector. If set, analytical cost generation is
        skipped.
    run_opt_lut : bool
        Whether to run ``opt_lut`` after the selected backend.
    run_clean : bool
        Whether to run ``clean`` after the selected backend.
    top_name : str | None
        Optional top module name for reporting.
    debug : bool
        Debug flag used if non-inplace mapping creates a temporary bridge.
    """

    base_lut_size: int = 4
    num_shared_inputs: int = 3
    use_select_as_data_in_pair_mode: bool = False
    max_lut_size: int = 8
    backend: LutMapperBackend | str = LutMapperBackend.ABC9

    sharing_penalty_factor: float = 1.0
    size_penalty_factor: float = 1.0
    pair_discount_strength: float = 0.5

    larger_lut_base_multiplier: float = 2.0
    larger_lut_discount_factor: float = 0.9

    cost_scale: int = 100
    min_cost: int = 1
    max_cost: int | None = None
    raw_cost_vector: tuple[int | float, ...] | None = None

    run_opt_lut: bool = True
    run_clean: bool = True
    top_name: str | None = None
    debug: bool = False

    _result: LutMapperResult | None = None

    def run_on(self, design: PyosysBridge) -> None:
        """Run the LUT mapper pass on the given design.

        Parameters
        ----------
        design : PyosysBridge
            The pyosys design wrapper to map.
        """
        mapper = LutMapper(
            LutMapperConfig(
                base_lut_size=self.base_lut_size,
                num_shared_inputs=self.num_shared_inputs,
                use_select_as_data_in_pair_mode=(self.use_select_as_data_in_pair_mode),
                max_lut_size=self.max_lut_size,
                backend=_normalize_backend(self.backend),
                sharing_penalty_factor=self.sharing_penalty_factor,
                size_penalty_factor=self.size_penalty_factor,
                pair_discount_strength=self.pair_discount_strength,
                larger_lut_base_multiplier=self.larger_lut_base_multiplier,
                larger_lut_discount_factor=self.larger_lut_discount_factor,
                cost_scale=self.cost_scale,
                min_cost=self.min_cost,
                max_cost=self.max_cost,
                raw_cost_vector=self.raw_cost_vector,
                run_opt_lut=self.run_opt_lut,
                run_clean=self.run_clean,
                debug=self.debug,
            )
        )
        self._result = mapper.map_from_design(
            design,
            inplace=True,
            top_name=self.top_name,
        )

    @property
    def report_summary(self) -> str:
        """Return the summary report from the latest mapper run.

        Returns
        -------
        str
            Rendered report text, or a placeholder if the pass has not run.
        """
        return self._result.report_summary if self._result else "No result available."

    @property
    def result_data(self) -> LutMapperResult | None:
        """Return the latest structured mapper result.

        Returns
        -------
        LutMapperResult | None
            Latest result object if available.
        """
        return self._result


def _normalize_backend(backend: LutMapperBackend | str) -> LutMapperBackend:
    """Normalize public backend input before building core config.

    Parameters
    ----------
    backend : LutMapperBackend | str
        Backend value provided to the pass.

    Returns
    -------
    LutMapperBackend
        Strict enum value accepted by ``LutMapperConfig``.
    """
    return (
        backend if isinstance(backend, LutMapperBackend) else LutMapperBackend(backend)
    )

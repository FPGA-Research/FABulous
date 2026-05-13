"""Pyosys pass wrapper for register absorption."""

from dataclasses import dataclass

from fabulous.fabric_cad.fabxplore.modules.reg_absorber.core.absorber import (
    RegAbsorber,
)
from fabulous.fabric_cad.fabxplore.modules.reg_absorber.core.models import (
    FfPortsInput,
    RegAbsorberResult,
    RuleInput,
)
from fabulous.fabric_cad.fabxplore.pyosys.pyosys_bridge import PyosysBridge
from fabulous.fabric_cad.fabxplore.pyosys.synth_pass import SynthPass


@dataclass
class RegAbsorberPass(SynthPass):
    """Absorb adjacent FFs into primitive sequential ports.

    Attributes
    ----------
    cell_types : list[str]
        Primitive cell types that may absorb FFs.
    rules : list[RuleInput]
        Absorption rules. Dicts are validated as pydantic models internally.
    ff_ports : FfPortsInput | None
        Supported FF cell port mapping. ``None`` selects defaults.
    allow_extra_fanout : bool
        Whether non-clean fanout patterns may be absorbed.
    strict : bool
        Whether invalid matches raise instead of being skipped.
    track_progress : bool
        Whether progress should be logged.
    progress_chunk_size : int
        Number of processed checks between progress updates.
    top_name : str | None
        Top module to process.
    """

    cell_types: list[str]
    rules: list[RuleInput]
    ff_ports: FfPortsInput | None = None
    allow_extra_fanout: bool = False
    strict: bool = False
    track_progress: bool = True
    progress_chunk_size: int = 100
    top_name: str | None = None

    _result: RegAbsorberResult | None = None

    def run_on(self, design: PyosysBridge) -> None:
        """Run the pass on a design.

        Parameters
        ----------
        design : PyosysBridge
            Design to mutate.
        """
        absorber = RegAbsorber(
            cell_types=self.cell_types,
            rules=self.rules,
            ff_ports=self.ff_ports,
            allow_extra_fanout=self.allow_extra_fanout,
            strict=self.strict,
            track_progress=self.track_progress,
            progress_chunk_size=self.progress_chunk_size,
        )
        self._result = absorber.map_from_design(design, top_name=self.top_name)

    @property
    def report_summary(self) -> str:
        """Return the latest report summary.

        Returns
        -------
        str
            Report text, or a placeholder if the pass has not run.
        """
        return self._result.report_summary if self._result else "No result available."

    @property
    def result_data(self) -> RegAbsorberResult | None:
        """Return the latest structured result.

        Returns
        -------
        RegAbsorberResult | None
            Latest result if available.
        """
        return self._result

"""Pyosys pass wrapper for placement hint generation."""

from dataclasses import dataclass

from fabulous.fabric_cad.fabxplore.modules.placement_hints.core.hinter import (
    PlacementHinter,
)
from fabulous.fabric_cad.fabxplore.modules.placement_hints.core.models import (
    PlacementHintsOptions,
    PlacementHintsResult,
    PlacementRuleInput,
)
from fabulous.fabric_cad.fabxplore.pyosys.pyosys_bridge import PyosysBridge
from fabulous.fabric_cad.fabxplore.pyosys.synth_pass import SynthPass


@dataclass
class PlacementHintsPass(SynthPass):
    """Add placement hint attributes to existing cells.

    Attributes
    ----------
    rules : list[PlacementRuleInput]
        Structural hint rules to apply.
    attribute_prefix : str
        Prefix used for emitted attributes.
    overwrite_existing : bool
        Whether existing placement attributes may be replaced.
    fail_on_conflict : bool
        Whether conflicting attributes should raise.
    track_progress : bool
        Whether progress should be logged.
    progress_chunk_size : int
        Number of processed candidate cells between progress updates.
    top_name : str | None
        Top module to process.
    """

    rules: list[PlacementRuleInput]
    attribute_prefix: str = "FAB_CLUSTER"
    overwrite_existing: bool = False
    fail_on_conflict: bool = True
    track_progress: bool = True
    progress_chunk_size: int = 100
    top_name: str | None = None

    _result: PlacementHintsResult | None = None

    def run_on(self, design: PyosysBridge) -> None:
        """Run the pass on a design.

        Parameters
        ----------
        design : PyosysBridge
            Design to mutate in place.
        """
        options = PlacementHintsOptions(
            rules=self.rules,
            attribute_prefix=self.attribute_prefix,
            overwrite_existing=self.overwrite_existing,
            fail_on_conflict=self.fail_on_conflict,
            track_progress=self.track_progress,
            progress_chunk_size=self.progress_chunk_size,
            top_name=self.top_name,
        )
        hinter = PlacementHinter(options=options)
        self._result = hinter.map_from_design(design, top_name=self.top_name)

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
    def result_data(self) -> PlacementHintsResult | None:
        """Return the latest structured result.

        Returns
        -------
        PlacementHintsResult | None
            Latest result if available.
        """
        return self._result

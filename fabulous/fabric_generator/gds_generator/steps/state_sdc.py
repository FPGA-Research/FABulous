"""OpenROAD steps that read the SDC view of their input state.

librelane's OpenROAD steps read `PNR_SDC_FILE`, a path fixed when the flow is
built, but the tile flow's loop-break cuts exist only once `FABulousLoopBreakSDC`
has run. `TileAreaOptimisation` points its own steps at the SDC view. The steps
here do the same for the tile flow's steps after it. Each keeps the librelane step
id, so `classic_gating_config_vars` still gates it, and writes the SDC it read back
out, so the cuts reach the final SDC view.
"""

from librelane.common.types import Path
from librelane.state.design_format import DesignFormat
from librelane.state.state import State
from librelane.steps import openroad as OpenROAD
from librelane.steps.step import MetricsUpdate, ViewsUpdate


class StateSDCStep(OpenROAD.OpenROADStep):
    """Run an OpenROAD step with `PNR_SDC_FILE` set to the input SDC view."""

    def run(self, state_in: State, **kwargs: str) -> tuple[ViewsUpdate, MetricsUpdate]:
        """Point `PNR_SDC_FILE` at the input SDC view, then run the step."""
        self.config = self.config.copy(
            PNR_SDC_FILE=Path(str(state_in[DesignFormat.SDC]))
        )
        return super().run(state_in, **kwargs)


class FillInsertion(StateSDCStep, OpenROAD.FillInsertion):
    """`OpenROAD.FillInsertion` reading the input SDC view."""

    inputs = [*OpenROAD.FillInsertion.inputs, DesignFormat.SDC]


class RCX(StateSDCStep, OpenROAD.RCX):
    """`OpenROAD.RCX` reading the input SDC view."""

    inputs = [*OpenROAD.RCX.inputs, DesignFormat.SDC]


class IRDropReport(StateSDCStep, OpenROAD.IRDropReport):
    """`OpenROAD.IRDropReport` reading the input SDC view."""

    inputs = [*OpenROAD.IRDropReport.inputs, DesignFormat.SDC]

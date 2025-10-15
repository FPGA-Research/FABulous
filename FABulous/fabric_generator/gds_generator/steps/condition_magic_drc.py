"""FABulous GDS Generator - Conditional Magic DRC Step."""

from librelane.logging.logger import info
from librelane.state.state import State
from librelane.steps.magic import DRC
from librelane.steps.step import (
    MetricsUpdate,
    ViewsUpdate,
)


class ConditionalMagicDRC(DRC):
    """Run Magic DRC if klayout DRC errors are found."""

    id = "Condition.MagicDRC"
    name = "Magic DRC Check"
    long_name = "KLayout DRC Check with Conditional Flow Control"

    def run(self, state_in: State, **kwargs: dict) -> tuple[ViewsUpdate, MetricsUpdate]:
        """Run Magic DRC only if KLayout DRC errors are found."""
        if state_in.metrics.get("klayout__drc_error__count") == 0:
            info("No DRC violations found. Continuing the flow.")
            return {}, {}
        return super().run(state_in, **kwargs)

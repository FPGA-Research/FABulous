"""FABulous Magic StreamOut - syncs DIE_AREA env with state's design__die__bbox.

Magic.StreamOut tries to honour `state_in.metrics["design__die__bbox"]`
(librelane/steps/magic.py:329-330) but TclStep.run re-calls `prepare_env`,
which iterates `self.config` and overwrites `env["DIE_AREA"]` from config.
When TileOptimisation evolves DIE_AREA across iterations, the new value lands
in state metrics rather than Flow config, so the stock streamout renders the
stale smart-init rectangle on layer 189/4. Rebinding `self.config["DIE_AREA"]`
from the state metric makes `prepare_env` emit the right value.
"""

from decimal import Decimal
from typing import Any

from librelane.state.state import State
from librelane.steps.magic import StreamOut
from librelane.steps.step import MetricsUpdate, ViewsUpdate

from fabulous.fabric_generator.gds_generator.registry import register_step


@register_step
class FABulousMagicStreamOut(StreamOut):
    """Magic.StreamOut variant that pulls DIE_AREA from `design__die__bbox`."""

    id = "Magic.FABulousStreamOut"
    name = "GDSII Stream Out (Magic, FABulous)"
    long_name = "Magic GDSII stream-out with DIE_AREA sync from design__die__bbox"

    def run(
        self,
        state_in: State,
        **kwargs: Any,  # noqa: ANN401
    ) -> tuple[ViewsUpdate, MetricsUpdate]:
        """Rebind DIE_AREA from the state metric, then delegate to `StreamOut`."""
        die_bbox = state_in.metrics.get("design__die__bbox")
        if die_bbox is not None:
            die_area = tuple(Decimal(c) for c in die_bbox.split())
            self.config = self.config.copy(DIE_AREA=die_area)
        return super().run(state_in, **kwargs)

"""FABulous GDS Generator - Diodes on Ports step."""

from librelane.logging.logger import info
from librelane.state.state import State
from librelane.steps.odb import PortDiodePlacement
from librelane.steps.openroad import DetailedPlacement, GlobalPlacement
from librelane.steps.step import CompositeStep, MetricsUpdate, Step, ViewsUpdate


@Step.factory.register()
class FABulousDiodesOnPorts(CompositeStep):
    """Insert diodes on design ports and legalize via global + detailed placement.

    Mirrors `Odb.DiodesOnPorts` but omits the GlobalRouting re-run after
    placement, since global routing is run at a separate step later in the flow.
    """

    id = "FABulous.DiodesOnPorts"
    name = "FABulous Diodes on Ports"

    Steps = [
        PortDiodePlacement,
        GlobalPlacement,
        DetailedPlacement,
    ]

    def run(self, state_in: State, **kwargs: dict) -> tuple[ViewsUpdate, MetricsUpdate]:
        """Run the step if diodes on ports are configured and a diode cell is set."""
        if self.config["DIODE_ON_PORTS"] == "none":
            info(f"'DIODE_ON_PORTS' is set to 'none': skipping '{self.id}'...")
            return {}, {}
        if self.config["DIODE_CELL"] is None:
            raise ValueError(f"'DIODE_CELL' not set but '{self.id}' is enabled.")
        return super().run(state_in, **kwargs)

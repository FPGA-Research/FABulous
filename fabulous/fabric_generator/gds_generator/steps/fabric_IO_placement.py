"""FABulous GDS Generator - FABulous I/O Placement Step."""

from importlib import resources

from librelane.state.state import State
from librelane.steps.odb import OdbpyStep
from librelane.steps.step import (
    MetricsUpdate,
    Step,
    ViewsUpdate,
)


@Step.factory.register()
class FABulousFabricIOPlacement(OdbpyStep):
    """Stamp fabric-level signal BPins onto their driving/sinking macro pins."""

    id = "Odb.FABulousFabricIOPlacement"
    name = "FABulous fabric I/O Placement"
    long_name = "FABulous fabric I/O Pin Placement Script"

    def get_script_path(self) -> str:
        """Get the path to the I/O placement script."""
        return str(
            resources.files("fabulous.fabric_generator.gds_generator.script")
            / "fabric_io_place.py"
        )

    def run(self, state_in: State, **kwargs: dict) -> tuple[ViewsUpdate, MetricsUpdate]:
        """Place I/O pins using the upstream-compatible stamping strategy."""
        return super().run(state_in, **kwargs)

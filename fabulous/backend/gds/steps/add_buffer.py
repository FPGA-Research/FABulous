"""FABulous GDS Generator - Add Buffers Step."""

from importlib import resources

from librelane.config.variable import Variable
from librelane.state.state import State
from librelane.steps.common_variables import (
    grt_variables,
    rsz_variables,
)
from librelane.steps.openroad import OpenROADStep
from librelane.steps.step import (
    MetricsUpdate,
    Step,
    ViewsUpdate,
)


@Step.factory.register()
class AddBuffers(OpenROADStep):
    """Adds buffers to a global-placed ODB file."""

    id = "OpenROAD.AddBuffers"
    name = "Add Buffers (Post-Global Placement)"

    config_vars = (
        OpenROADStep.config_vars
        + grt_variables
        + rsz_variables
        + [
            Variable(
                "DESIGN_REPAIR_BUFFER_INPUT_PORTS",
                bool,
                "Specifies whether or not to insert buffers on input ports when design "
                "repairs are run.",
                default=True,
                deprecated_names=["PL_RESIZER_BUFFER_INPUT_PORTS"],
            ),
            Variable(
                "DESIGN_REPAIR_BUFFER_OUTPUT_PORTS",
                bool,
                "Specifies whether or not to insert buffers on input ports when design "
                "repairs are run.",
                default=True,
                deprecated_names=["PL_RESIZER_BUFFER_OUTPUT_PORTS"],
            ),
            Variable(
                "DESIGN_REPAIR_REMOVE_BUFFERS",
                bool,
                "Invokes OpenROAD's remove_buffers command to remove buffers from "
                "synthesis, which gives OpenROAD more flexibility when buffering nets.",
                default=False,
            ),
        ]
    )

    def run(
        self,
        state_in: State,
        **kwargs: dict,
    ) -> tuple[ViewsUpdate, MetricsUpdate]:
        """Run the AddBuffers step."""
        kwargs, env = self.extract_env(kwargs)
        return super().run(
            state_in,
            corners=self.config["RSZ_CORNERS"] or self.config["STA_CORNERS"],
            env=env,
            **kwargs,
        )

    def get_script_path(self) -> str:
        """Get the path to the add buffers script."""
        return str(
            resources.files("fabulous.backend.gds.script")
            / "add_buffers.tcl"
        )

"""FABulous GDS Generator - Fabric Macro Generation Step."""

from librelane.state.design_format import DesignFormat
from librelane.state.state import State
from librelane.steps.step import MetricsUpdate, Step, ViewsUpdate

from FABulous.fabric_generator.gds_generator.flows.fabric_macro_flow import (
    FABulousFabricMacroFlow,
)


@Step.factory.register()
class FabricMacroGen(Step):
    """LibreLane step for stitching FABulous tile macros into a complete fabric.

    This step takes pre-compiled tile macros and stitches them together into the final
    fabric layout, including power distribution and IO placement.
    """

    id = "FABulous.FabricMacroGen"
    name = "FABulous Fabric Macro Assembly"

    inputs = [
        DesignFormat.GDS,
        DesignFormat.LEF,
        DesignFormat.LIB,
        DesignFormat.DEF,
    ]
    outputs = [
        DesignFormat.GDS,
        DesignFormat.LEF,
        DesignFormat.LIB,
        DesignFormat.DEF,
    ]

    def run(self, state_in: State, **kwargs: str) -> tuple[ViewsUpdate, MetricsUpdate]:
        """Run the fabric macro generation process."""
        views_updates: dict = {}
        metrics_updates: dict = {}

        flow = FABulousFabricMacroFlow(self.config, **kwargs)
        final_state = flow.start(state_in)
        metrics_updates.update({self.config["DESIGN_NAME"]: final_state.metrics})

        for key in final_state:
            if (
                state_in.get(key) != final_state.get(key)
                and DesignFormat.factory.get(key) in self.outputs
            ):
                views_updates[key] = final_state[key]

        return (views_updates, metrics_updates)

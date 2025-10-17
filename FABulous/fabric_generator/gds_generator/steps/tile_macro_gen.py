"""FABulous GDS Generator - Tile to Macro Conversion Step."""

from librelane.config.variable import Variable
from librelane.state.design_format import DesignFormat
from librelane.state.state import State
from librelane.steps.step import MetricsUpdate, Step, ViewsUpdate

from FABulous.fabric_generator.gds_generator.flows.tile_macro_flow import (
    FABulousTileVerilogMarcoFlow,
    FABulousTileVerilogMarcoFlowClassic,
)


@Step.factory.register()
class TileMarcoGen(Step):
    """LibreLane step for converting FABulous tiles into macros.

    This step prepares tile-specific configuration and state, then delegates the actual
    processing to a classic flow or simplified processing chain. The goal is to generate
    macro files (GDS, LEF) suitable for hierarchical integration.
    """

    id = "FABulous.TileMarcoGen"
    name = "FABulous Tile to Macro Conversion"

    config_vars = [
        Variable(
            "FABULOUS_RUN_TILE_OPTIMISATION",
            bool,
            description="Whether to run tile size optimisation "
            "before macro generation.",
            default=True,
        ),
    ]

    inputs = []
    outputs = [
        DesignFormat.GDS,
        DesignFormat.LEF,
        DesignFormat.LIB,
        DesignFormat.DEF,
    ]

    def run(self, state_in: State, **kwargs: str) -> tuple[ViewsUpdate, MetricsUpdate]:
        """Run the tile to macro conversion process."""
        views_updates: dict = {}
        metrics_updates: dict = {}
        if self.config["FABULOUS_RUN_TILE_OPTIMISATION"]:
            flow = FABulousTileVerilogMarcoFlow(self.config, **kwargs)
        else:
            flow = FABulousTileVerilogMarcoFlowClassic(self.config, **kwargs)

        final_state = flow.start(state_in, _force_run_dir=self.step_dir)
        metrics_updates.update({self.config["DESIGN_NAME"]: final_state.metrics})

        for key in final_state:
            if (
                state_in.get(key) != final_state.get(key)
                and DesignFormat.factory.get(key) in self.outputs
            ):
                views_updates[key] = final_state[key]

        return (views_updates, metrics_updates)

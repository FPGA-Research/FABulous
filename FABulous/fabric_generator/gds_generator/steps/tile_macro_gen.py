"""FABulous GDS Generator - Tile to Macro Conversion Step."""

from librelane.config.variable import Variable
from librelane.logging.logger import warn
from librelane.state.design_format import DesignFormat
from librelane.state.state import State
from librelane.steps.step import MetricsUpdate, Step, ViewsUpdate

from FABulous.fabric_generator.gds_generator.flows.tile_macro_flow import (
    FABulousTileVerilogMarcoFlow,
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
            "FABULOUS_IGNORE_ERRORS",
            bool,
            description="Whether to ignore errors during macro generation.",
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
        flow = FABulousTileVerilogMarcoFlow(self.config, **kwargs)

        try:
            final_state = flow.start(state_in, _force_run_dir=self.step_dir)
        except Exception as e:
            if self.config["FABULOUS_IGNORE_ERRORS"]:
                warn(
                    f"Tile macro generation step failed with exception {e}, "
                    "but continuing as FABULOUS_IGNORE_ERRORS is True."
                )
                final_state = state_in
            else:
                raise e from None
        metrics_updates.update(final_state.metrics)

        for key in final_state:
            if (
                state_in.get(key) != final_state.get(key)
                and DesignFormat.factory.get(key) in self.outputs
            ):
                views_updates[key] = final_state[key]

        return (views_updates, metrics_updates)

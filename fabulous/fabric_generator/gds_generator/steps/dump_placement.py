"""Read the placed tile back out of OpenDB as a JSON view."""

from importlib import resources
from pathlib import Path

from librelane.common.types import Path as LibrelanePath
from librelane.logging.logger import info
from librelane.state.state import State
from librelane.steps.odb import OdbpyStep
from librelane.steps.step import MetricsUpdate, Step, ViewsUpdate

from fabulous.fabric_generator.gds_generator.formats import PLACEMENT_FORMAT
from fabulous.fabric_generator.gds_generator.opt.variables import (
    CONFIG_MAPPING_VARIABLE,
    TILE_INTERFACE_VARIABLE,
)


@Step.factory.register()
class DumpPlacement(OdbpyStep):
    """Dump placed instances, ports and signal nets to a JSON view.

    The view is what the placement-driven optimisations under
    `fabulous.fabric_generator.gds_generator.opt` read, so it runs only when one
    of them is on.
    """

    id = "FABulous.DumpPlacement"
    name = "Dump Placement"

    outputs = [PLACEMENT_FORMAT]

    config_vars = [CONFIG_MAPPING_VARIABLE, TILE_INTERFACE_VARIABLE]

    @property
    def placement_path(self) -> LibrelanePath:
        """Destination of the JSON dump inside the step directory."""
        design = self.config["DESIGN_NAME"]
        return LibrelanePath(
            str(Path(self.step_dir) / f"{design}.{PLACEMENT_FORMAT.extension}")
        )

    def get_script_path(self) -> str:
        """Get the path to the dump script."""
        return str(
            resources.files("fabulous.fabric_generator.gds_generator.script")
            / "dump_placement.py"
        )

    def get_command(self) -> list[str]:
        """Get the command running the dump script."""
        return [*super().get_command(), "--placement-out", str(self.placement_path)]

    def run(self, state_in: State, **kwargs: str) -> tuple[ViewsUpdate, MetricsUpdate]:
        """Run the dump and publish the JSON as the placement view."""
        if not (
            self.config[CONFIG_MAPPING_VARIABLE.name]
            or self.config[TILE_INTERFACE_VARIABLE.name]
        ):
            info(
                f"Neither '{CONFIG_MAPPING_VARIABLE.name}' nor "
                f"'{TILE_INTERFACE_VARIABLE.name}' is on: skipping '{self.id}'..."
            )
            return {}, {}
        views, metrics = super().run(state_in, **kwargs)
        views[PLACEMENT_FORMAT] = self.placement_path
        return views, metrics

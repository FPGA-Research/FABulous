"""Rewire a floorplanned netlist to a proposed configuration memory mapping."""

import json
from importlib import resources
from pathlib import Path

from librelane.logging.logger import info
from librelane.state.state import State
from librelane.steps.odb import OdbpyStep
from librelane.steps.step import MetricsUpdate, Step, ViewsUpdate

from fabulous.custom_exception import GDSFlowError
from fabulous.fabric_generator.gds_generator.opt.variables import (
    CONFIG_MAPPING_RECONNECT_VARIABLE,
    CONFIG_MAPPING_VARIABLE,
)


@Step.factory.register()
class ApplyConfigMapping(OdbpyStep):
    """Rewire the placed netlist to a proposed configuration memory mapping.

    Synthesis stays outside the area optimisation loop, so the netlist always
    implements the mapping it was synthesised with. Editing the ODB right after
    the floorplan is what lets an iteration implement a proposal without a
    second synthesis run.
    """

    id = "FABulous.ApplyConfigMapping"
    name = "Apply Configuration Mapping"

    config_vars = [CONFIG_MAPPING_VARIABLE, CONFIG_MAPPING_RECONNECT_VARIABLE]

    @property
    def report_path(self) -> Path:
        """Destination of the rewire report inside the step directory."""
        design = self.config["DESIGN_NAME"]
        return Path(self.step_dir) / f"{design}.reconnect_report.json"

    def get_script_path(self) -> str:
        """Get the path to the rewire script."""
        return str(
            resources.files("fabulous.fabric_generator.gds_generator.script")
            / "apply_config_mapping.py"
        )

    def get_command(self) -> list[str]:
        """Get the command running the rewire script."""
        return [
            *super().get_command(),
            "--reconnect",
            str(self.config[CONFIG_MAPPING_RECONNECT_VARIABLE.name]),
            "--report",
            str(self.report_path),
        ]

    def run(self, state_in: State, **kwargs: str) -> tuple[ViewsUpdate, MetricsUpdate]:
        """Rewire the ODB and stop the flow if any pin could not be moved.

        Parameters
        ----------
        state_in : State
            The state carrying the ODB the floorplan built.
        **kwargs : str
            Forwarded to the odbpy runner.

        Returns
        -------
        tuple[ViewsUpdate, MetricsUpdate]
            The rewritten ODB views and how many latch pins moved.

        Raises
        ------
        GDSFlowError
            If the report lists a pin the script could not move, since the
            netlist then does not implement the proposal.
        """
        if not self.config[CONFIG_MAPPING_VARIABLE.name]:
            info(f"'{CONFIG_MAPPING_VARIABLE.name}' is off: skipping '{self.id}'...")
            return {}, {}
        if self.config[CONFIG_MAPPING_RECONNECT_VARIABLE.name] is None:
            info(
                f"'{CONFIG_MAPPING_RECONNECT_VARIABLE.name}' is unset: "
                f"skipping '{self.id}'..."
            )
            return {}, {}
        views, metrics = super().run(state_in, **kwargs)
        report = json.loads(self.report_path.read_text())
        if report["errors"]:
            raise GDSFlowError(
                "The netlist cannot be rewired to the proposal:\n"
                + "\n".join(report["errors"])
            )
        info(
            f"Moved {report['reconnected']} latch pins onto their proposed frame lines"
        )
        return views, {
            **metrics,
            "fabulous__config_mapping__reconnected_pins": report["reconnected"],
        }

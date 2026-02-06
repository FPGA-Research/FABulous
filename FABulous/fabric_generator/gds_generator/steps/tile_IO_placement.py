"""Custom IO placement step for FABulous tiles."""

from importlib import resources
from typing import Literal

from librelane.common.types import Path
from librelane.config.variable import Variable
from librelane.state.state import State
from librelane.steps.common_variables import (
    io_layer_variables,
)
from librelane.steps.odb import OdbpyStep
from librelane.steps.step import (
    MetricsUpdate,
    Step,
    ViewsUpdate,
)


def _migrate_unmatched_io(x: object) -> str:
    return "unmatched_design" if x else "none"


@Step.factory.register()
class FABulousTileIOPlacement(OdbpyStep):
    """Place I/O pins using a custom script.

    This step uses a custom Python script to place I/O pins according to a user-defined
    configuration file.
    """

    id = "Odb.FABulousTileIOPlacement"
    name = "FABulous I/O Placement"
    long_name = "FABulous I/O Pin Placement Script"

    config_vars = io_layer_variables + [
        Variable(
            "FABULOUS_IO_PIN_ORDER_CFG",
            Path,
            "Path to a custom pin configuration file.",
        ),
        Variable(
            "ERRORS_ON_UNMATCHED_IO",
            Literal["none", "unmatched_design", "unmatched_cfg", "both"],
            "Controls whether to emit an error in: no situation, when pins exist in "
            "the design that do not exist in the config file, when pins exist in the "
            "config file that do not exist in the design, and both respectively. "
            "`both` is recommended, as the default is only for backwards compatibility "
            "with librelane 1.",
            default="unmatched_design",  # Backwards compatible with librelane 1
            deprecated_names=[
                ("QUIT_ON_UNMATCHED_IO", _migrate_unmatched_io),
            ],
        ),
    ]

    def get_script_path(self) -> str:
        """Get the path to the I/O placement script."""
        return str(
            resources.files("FABulous.fabric_generator.gds_generator.script")
            / "tile_io_place.py"
        )

    def get_command(self) -> list[str]:
        """Get the command to run the I/O placement script."""
        length_args = []
        if self.config["IO_PIN_V_LENGTH"] is not None:
            length_args += ["--ver-length", self.config["IO_PIN_V_LENGTH"]]
        if self.config["IO_PIN_H_LENGTH"] is not None:
            length_args += ["--hor-length", self.config["IO_PIN_H_LENGTH"]]

        return (
            super().get_command()
            + [
                "--config",
                self.config["FABULOUS_IO_PIN_ORDER_CFG"],
                "--hor-layer",
                self.config["FP_IO_HLAYER"],
                "--ver-layer",
                self.config["FP_IO_VLAYER"],
                "--hor-width-mult",
                str(self.config["IO_PIN_V_THICKNESS_MULT"]),
                "--ver-width-mult",
                str(self.config["IO_PIN_H_THICKNESS_MULT"]),
                "--hor-extension",
                str(self.config["IO_PIN_H_EXTENSION"]),
                "--ver-extension",
                str(self.config["IO_PIN_V_EXTENSION"]),
                "--unmatched-error",
                self.config["ERRORS_ON_UNMATCHED_IO"],
            ]
            + length_args
        )

    def run(self, state_in: State, **kwargs: str) -> tuple[ViewsUpdate, MetricsUpdate]:
        """Run the I/O placement step."""
        return super().run(state_in, **kwargs)

"""FABulous GDS Generator - FABulous I/O Placement Step."""

from decimal import Decimal
from importlib import resources

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
class FABulousFabricIOPlacement(OdbpyStep):
    """Place I/O pins using a custom script. This is the fabric-level version.

    This step uses a custom Python script to place I/O pins according to the macro pin
    coordinates. This is intended for use in the stitching flow to place top level macro
    I/Os. This step will just line up to the master driver terminals and does not care
    is the pin placement is pitch aligned.
    """

    id = "Odb.FABulousFabricIOPlacement"
    name = "FABulous fabric I/O Placement"
    long_name = "FABulous fabric I/O Pin Placement Script"

    config_vars = io_layer_variables + [
        Variable(
            "IO_PIN_V_LENGTH",
            Decimal | None,
            """
            The length of the pins with a north or south orientation. If unspecified by
            a PDK, the script will use whichever is higher of the following two values:
                * The pin width
                * The minimum value satisfying the minimum area constraint given the
                  pin width
            """,
            units="µm",
            pdk=True,
        ),
        Variable(
            "IO_PIN_H_LENGTH",
            Decimal | None,
            """
            The length of the pins with an east or west orientation. If unspecified by
            a PDK, the script will use whichever is higher of the following two values:
                * The pin width
                * The minimum value satisfying the minimum area constraint given the
                  pin width
            """,
            units="µm",
            pdk=True,
        ),
    ]

    def get_script_path(self) -> str:
        """Get the path to the I/O placement script."""
        return str(
            resources.files("FABulous.fabric_generator.gds_generator.script")
            / "fabric_io_place.py"
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
            ]
            + length_args
        )

    def run(self, state_in: State, **kwargs: dict) -> tuple[ViewsUpdate, MetricsUpdate]:
        """Place I/O pins using a custom script.

        This is the fabric-level version.
        """
        return super().run(state_in, **kwargs)

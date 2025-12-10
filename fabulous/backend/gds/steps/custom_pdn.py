"""FABulous GDS Generator - Custom PDN Generation Step."""

from importlib import resources
from pathlib import Path
from typing import Optional

from librelane.config.variable import Variable
from librelane.steps.common_variables import pdn_variables
from librelane.steps.openroad import OpenROADStep
from librelane.steps.step import (
    Step,
)


@Step.factory.register()
class CustomGeneratePDN(OpenROADStep):
    """Creates a power distribution network on a floorplanned ODB file."""

    id = "FABulous.GeneratePDN"
    name = "Generate PDN"
    long_name = "Power Distribution Network Generation"

    config_vars = (
        OpenROADStep.config_vars
        + pdn_variables
        + [
            Variable(
                "PDN_CFG",
                Optional[Path],  # librelane limitation  # noqa: UP045
                "A custom PDN configuration file. If not provided, "
                "the default PDN config will be used. This default config is a custom "
                "config that differ from the librelane default.",
                default=str(
                    resources.files("fabulous.backend.gds.script")
                    / "pdn_config.tcl"
                ),
            )
        ]
    )

    def get_script_path(self) -> str:
        """Get the path to the PDN generation script."""
        return str(
            resources.files("fabulous.backend.gds.script")
            / "pdn.tcl"
        )

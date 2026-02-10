"""FABulous GDS Generator - ODB Power Connection Step."""

from importlib import resources

from librelane.steps.common_variables import pdn_variables
from librelane.steps.odb import OdbpyStep
from librelane.steps.step import Step


@Step.factory.register()
class FABulousPDN(OdbpyStep):
    """Connect power rails for the tiles using a custom script."""

    id = "Odb.FABulousPDN"
    name = "FABulous PDN connections for the tiles"

    config_vars = pdn_variables

    def get_script_path(self) -> str:
        """Get the path to the power connection script."""
        return str(
            resources.files("FABulous.fabric_generator.gds_generator.script")
            / "odb_power.py"
        )

    def get_command(self) -> list[str]:
        """Get the command to run the power connection script."""
        return super().get_command() + [
            "--metal-layer-name",
            self.config["PDN_VERTICAL_LAYER"],
        ]

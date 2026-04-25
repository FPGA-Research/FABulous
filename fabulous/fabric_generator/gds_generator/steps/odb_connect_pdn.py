"""FABulous GDS Generator - ODB Power Connection Step."""

from importlib import resources
from typing import Tuple

from librelane.config.flow import option_variables
from librelane.steps.common_variables import pdn_variables
from librelane.steps.odb import OdbpyStep
from librelane.steps.step import Step, ViewsUpdate, MetricsUpdate
from librelane.state.state import DesignFormat, State



@Step.factory.register()
class FABulousPDN(OdbpyStep):
    """Connect power rails for the tiles using a custom script."""

    id = "Odb.FABulousPDN"
    name = "FABulous PDN connections for the tiles"

    config_vars = pdn_variables + option_variables

    def get_script_path(self) -> str:
        """Get the path to the power connection script."""
        return str(
            resources.files("fabulous.fabric_generator.gds_generator.script")
            / "odb_power.py"
        )

    def run(self, state_in: State, **kwargs) -> Tuple[ViewsUpdate, MetricsUpdate]:
        kwargs, env = self.extract_env(kwargs)

        # default values for FABulousPDN
        if self.config["VDD_NETS"] == None:
            env["VDD_NETS"] = "VPWR"
        else:
            env["VDD_NETS"] = ''.join(self.config["VDD_NETS"])

        if self.config["GND_NETS"] == None:
            env["GND_NETS"] = "VGND"
        else:
            env["GND_NETS"] = ''.join(self.config["GND_NETS"])

        return super().run(state_in, env=env, **kwargs)

"""FABulous GDS Generator - ODB Power Connection Step."""

from importlib import resources

from librelane.config.flow import option_variables
from librelane.steps.common_variables import pdn_variables
from librelane.steps.odb import OdbpyStep
from librelane.steps.step import Step


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

    def get_command(self) -> list[str]:
        """Get the command to run the power connection script."""
        vdd_pins = []
        if self.config["VDD_NETS"] is None:
            vdd_pins.append("--power-names")
            vdd_pins.append("VPWR")
        else:
            for power_net in self.config["VDD_NETS"]:
                vdd_pins.append("--power-names")
                vdd_pins.append(power_net)

        gnd_pins = []
        if self.config["GND_NETS"] is None:
            gnd_pins.append("--ground-names")
            gnd_pins.append("VGND")
        else:
            for power_net in self.config["GND_NETS"]:
                gnd_pins.append("--ground-names")
                gnd_pins.append(power_net)

        return super().get_command() + vdd_pins + gnd_pins

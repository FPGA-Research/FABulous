"""FABulous GDS Generator - ODB Power Connection Step."""

from importlib import resources

from librelane.config.flow import option_variables, pdk_variables
from librelane.steps.common_variables import pdn_variables
from librelane.steps.odb import OdbpyStep

from fabulous.fabric_generator.gds_generator.registry import register_step

_power_pin_variables = [v for v in pdk_variables if v.name in ("VDD_PIN", "GND_PIN")]


@register_step
class FABulousPDN(OdbpyStep):
    """Connect power rails for the tiles using a custom script."""

    id = "Odb.FABulousPDN"
    name = "FABulous PDN connections for the tiles"

    config_vars = pdn_variables + option_variables + _power_pin_variables

    def get_script_path(self) -> str:
        """Get the path to the power connection script."""
        return str(
            resources.files("fabulous.fabric_generator.gds_generator.script")
            / "odb_power.py"
        )

    def get_command(self) -> list[str]:
        """Get the command to run the power connection script."""
        vdd_nets = self.config["VDD_NETS"] or [self.config["VDD_PIN"]]
        gnd_nets = self.config["GND_NETS"] or [self.config["GND_PIN"]]

        vdd_pins = []
        for power_net in vdd_nets:
            vdd_pins.append("--power-names")
            vdd_pins.append(power_net)

        gnd_pins = []
        for ground_net in gnd_nets:
            gnd_pins.append("--ground-names")
            gnd_pins.append(ground_net)

        return super().get_command() + vdd_pins + gnd_pins

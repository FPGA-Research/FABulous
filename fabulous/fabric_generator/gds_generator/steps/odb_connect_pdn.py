"""FABulous GDS Generator - ODB Power Connection Step."""

from importlib import resources

from librelane.steps.odb import OdbpyStep
from librelane.steps.openroad import pdn_variables

from fabulous.fabric_generator.gds_generator.helper import get_supply_nets
from fabulous.fabric_generator.gds_generator.registry import register_step


@register_step
class FABulousPDN(OdbpyStep):
    """Connect power rails for the tiles using a custom script."""

    id = "Odb.FABulousPDN"
    name = "FABulous PDN connections for the tiles"

    config_vars = pdn_variables

    def get_script_path(self) -> str:
        """Get the path to the power connection script."""
        return str(
            resources.files("fabulous.fabric_generator.gds_generator.script")
            / "odb_power.py"
        )

    def get_command(self) -> list[str]:
        """Get the command to run the power connection script."""
        vdd_nets, gnd_nets = get_supply_nets(self.config)

        vdd_pins = []
        for power_net in vdd_nets:
            vdd_pins.append("--power-names")
            vdd_pins.append(power_net)

        gnd_pins = []
        for ground_net in gnd_nets:
            gnd_pins.append("--ground-names")
            gnd_pins.append(ground_net)

        return super().get_command() + vdd_pins + gnd_pins

"""FABulous GDS Generator - tile PDN generation step.

The step plans the stripe placement and writes it to `pdn_stripes.txt` in the step
directory, one `net offset count` stripe train per line. `tile_pdn.tcl` only
replays those as `add_pdn_stripe` calls, so the placement rule stays independent
of the PDN tool.
"""

from decimal import Decimal
from importlib import resources
from pathlib import Path

from librelane.state.state import State
from librelane.steps import openroad as OpenROAD
from librelane.steps.step import MetricsUpdate, Step, StepException, ViewsUpdate

from fabulous.fabric_generator.gds_generator.helper import get_supply_nets
from fabulous.fabric_generator.gds_generator.steps.common_variables import (
    tile_logical_width_variable,
)


@Step.factory.register()
class FABulousTilePDN(OpenROAD.GeneratePDN):
    """Generate the tile PDN with the stripes aligned per logical tile."""

    id = "OpenROAD.FABulousTilePDN"
    name = "Generate tile PDN"

    config_vars = OpenROAD.GeneratePDN.config_vars + [tile_logical_width_variable]

    def get_script_path(self) -> str:
        """Get the path to the tile PDN script."""
        return str(
            resources.files("fabulous.fabric_generator.gds_generator.script")
            / "tile_pdn.tcl"
        )

    def run(self, state_in: State, **kwargs: dict) -> tuple[ViewsUpdate, MetricsUpdate]:
        """Plan the stripe trains from the floorplan bounding boxes, then run pdngen."""
        bboxes: dict[str, list[Decimal]] = {}
        for metric in ("design__die__bbox", "design__core__bbox"):
            if metric not in state_in.metrics:
                raise StepException(
                    f"The '{metric}' metric is missing. Run a floorplan step before "
                    f"'{self.id}'."
                )
            bboxes[metric] = [Decimal(v) for v in state_in.metrics[metric].split()]
        die_x0, _, die_x1, _ = bboxes["design__die__bbox"]
        core_x0, _, core_x1, _ = bboxes["design__core__bbox"]

        # pdngen orders a stripe set that starts with POWER as the primary power
        # and ground nets followed by the secondary pairs.
        power_nets, ground_nets = get_supply_nets(self.config)
        nets = [power_nets[0], ground_nets[0]]
        for power_net, ground_net in zip(power_nets[1:], ground_nets[1:], strict=True):
            nets += [power_net, ground_net]

        # Repeat a regular tile's stripes in every logical tile so they line up with
        # the regular tiles in the same columns. pdngen can end a stripe set part
        # way through at the core edge, so each net gets its own train.
        offset: Decimal = self.config["PDN_VOFFSET"]
        pitch: Decimal = self.config["PDN_VPITCH"]
        net_pitch: Decimal = self.config["PDN_VWIDTH"] + self.config["PDN_VSPACING"]
        tile_count: int = self.config["FABULOUS_TILE_LOGICAL_WIDTH"]
        tile_width = (die_x1 - die_x0) / tile_count
        tile_core_width = tile_width - (core_x0 - die_x0) - (die_x1 - core_x1)
        if offset > tile_core_width:
            raise StepException(
                f"PDN_VOFFSET ({offset}) lies outside the {tile_core_width} wide core "
                "of a logical tile. Reduce PDN_VOFFSET or enlarge the tile."
            )

        stripes: list[str] = []
        for tile_index in range(tile_count):
            for net_index, net in enumerate(nets):
                net_offset = offset + net_index * net_pitch
                if net_offset > tile_core_width:
                    break
                count = int((tile_core_width - net_offset) // pitch) + 1
                stripes.append(f"{net} {net_offset + tile_index * tile_width} {count}")
        (Path(self.step_dir) / "pdn_stripes.txt").write_text("\n".join(stripes) + "\n")
        return super().run(state_in, **kwargs)

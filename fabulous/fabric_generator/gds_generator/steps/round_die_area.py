"""FABulous GDS Generator - Round Die Area Step."""

import math
from decimal import Decimal
from pathlib import Path

from librelane.state.state import State
from librelane.steps import openroad as OpenROAD
from librelane.steps.step import MetricsUpdate, ViewsUpdate


class RoundDieArea(OpenROAD.Floorplan):
    """Round the die area to the nearest multiple of the smallest track pitch."""

    id = "FABulous.RoundDieArea"
    name = "Round Die Area"
    long_name = "Round Die Area to Nearest PDK Site"

    inputs = []
    outputs = []

    def run(
        self,
        state_in: State,  # noqa: ARG002
        **kwargs: str,  # noqa: ARG002
    ) -> tuple[ViewsUpdate, MetricsUpdate]:
        """Round the die area to the nearest multiple of the smallest track pitch."""
        with Path(self.config["FP_TRACKS_INFO"]).open() as f:
            lines = f.readlines()

        layers: dict[str, dict[str, tuple[Decimal, Decimal]]] = {}
        for line in lines:
            if line.strip() == "":
                continue
            layer, cardinal, offset, pitch = line.split()
            layers[layer] = layers.get(layer) or {}
            layers[layer][cardinal] = (Decimal(offset), Decimal(pitch))

        all_pitches = []
        for _layer, info in layers.items():
            for _cardinal, (_offset, pitch) in info.items():
                all_pitches.append(pitch)
        min_pitch = min(all_pitches)

        die_area = self.config.get("DIE_AREA", None)
        if die_area is None:
            raise ValueError("DIE_AREA metric not found in state.")
        _, _, width, height = die_area
        # Round width and height to the next multiple of the smallest pitch
        width = math.ceil(width / min_pitch) * min_pitch
        height = math.ceil(height / min_pitch) * min_pitch

        self.config = self.config.copy(DIE_AREA=(0, 0, Decimal(width), Decimal(height)))

        metric = {"pdk__track_info": layers}
        return {}, metric

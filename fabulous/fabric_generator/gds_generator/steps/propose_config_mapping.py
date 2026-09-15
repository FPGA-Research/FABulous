"""Propose a configuration memory mapping from the placed latches."""

import json
from pathlib import Path

from librelane.common.types import Path as LibrelanePath
from librelane.logging.logger import info
from librelane.state.state import State
from librelane.steps.step import MetricsUpdate, Step, ViewsUpdate

from fabulous.custom_exception import GDSFlowError
from fabulous.fabric_definition.configmem import ConfigMem
from fabulous.fabric_generator.gds_generator.formats import (
    CONFIG_MEM_FORMAT,
    PLACEMENT_FORMAT,
    RECONNECT_FORMAT,
)
from fabulous.fabric_generator.gds_generator.opt.config_mapping import (
    FrameLines,
    frame_grid,
    latch_pins,
    reconnections,
    solve_config_mapping,
)
from fabulous.fabric_generator.gds_generator.opt.placement import Placement
from fabulous.fabric_generator.gds_generator.opt.tile_interface import read_bus_pairs
from fabulous.fabric_generator.gds_generator.opt.variables import (
    CONFIG_MAPPING_TARGET_VARIABLE,
    CONFIG_MAPPING_VARIABLE,
    CONFIG_MEM_CSV_VARIABLE,
    TILE_INTERFACE_PAIRS_VARIABLE,
)


@Step.factory.register()
class ProposeConfigMapping(Step):
    """Write a `ConfigMem.csv` that puts every bit on a crosspoint near its latch.

    The proposal is a view in the step directory and never touches the tile
    directory, so the CSV on disk keeps matching the netlist that was
    hardened. The reconnection list written next to it is what
    `ApplyConfigMapping` needs to make a netlist implement the proposal.
    """

    id = "FABulous.ProposeConfigMapping"
    name = "Propose Configuration Mapping"

    inputs = [PLACEMENT_FORMAT]
    outputs = [CONFIG_MEM_FORMAT, RECONNECT_FORMAT]

    config_vars = [
        CONFIG_MAPPING_VARIABLE,
        CONFIG_MEM_CSV_VARIABLE,
        CONFIG_MAPPING_TARGET_VARIABLE,
        TILE_INTERFACE_PAIRS_VARIABLE,
    ]

    def run(self, state_in: State, **_kwargs: str) -> tuple[ViewsUpdate, MetricsUpdate]:
        """Solve the assignment and publish the proposal with its stub metrics.

        Parameters
        ----------
        state_in : State
            The state carrying the placement view.
        **_kwargs : str
            Unused.

        Returns
        -------
        tuple[ViewsUpdate, MetricsUpdate]
            The mapping and reconnection views and the distances before and
            after.

        Raises
        ------
        GDSFlowError
            If the mapping is on for a tile without a `ConfigMem.csv` or
            without its bus pairs, which means a super tile or a tile without
            configuration bits.
        """
        if not self.config[CONFIG_MAPPING_VARIABLE.name]:
            info(f"'{CONFIG_MAPPING_VARIABLE.name}' is off: skipping '{self.id}'...")
            return {}, {}
        if (csv := self.config[CONFIG_MEM_CSV_VARIABLE.name]) is None:
            raise GDSFlowError(
                f"{CONFIG_MAPPING_VARIABLE.name} needs {CONFIG_MEM_CSV_VARIABLE.name}; "
                "a super tile or a tile without configuration bits has no "
                "configuration memory to map."
            )
        if (pairs_path := self.config[TILE_INTERFACE_PAIRS_VARIABLE.name]) is None:
            raise GDSFlowError(
                f"{CONFIG_MAPPING_VARIABLE.name} needs "
                f"{TILE_INTERFACE_PAIRS_VARIABLE.name} to name the frame chains."
            )
        current_csv = Path(self.config[CONFIG_MAPPING_TARGET_VARIABLE.name] or csv)
        lines = FrameLines.from_pairs(read_bus_pairs(Path(pairs_path)))

        placement = Placement.from_json(Path(state_in[PLACEMENT_FORMAT]))
        grid = frame_grid(placement, lines)
        current = ConfigMem.from_csv(
            current_csv,
            frame_bits_per_row=grid.frame_bits_per_row,
            max_frames_per_col=grid.max_frames_per_col,
        )
        pins = latch_pins(placement, lines)
        proposal, moved = solve_config_mapping(placement, current, lines)

        design = self.config["DESIGN_NAME"]
        out = Path(self.step_dir) / f"{design}.{CONFIG_MEM_FORMAT.extension}"
        proposal.to_csv(out)
        reconnect = Path(self.step_dir) / f"{design}.{RECONNECT_FORMAT.extension}"
        reconnect.write_text(
            json.dumps(reconnections(pins, current.bit_at, proposal, lines), indent=1)
        )
        placed = current.config_bits - len(moved.unplaced_bits)
        info(
            f"Frame net stub length {moved.stub_before:.1f} um -> "
            f"{moved.stub_after:.1f} um over {placed} placed latches; "
            f"proposal written to {out}"
        )
        metrics: MetricsUpdate = {
            "fabulous__config_mapping__stub_before": moved.stub_before,
            "fabulous__config_mapping__stub_after": moved.stub_after,
            "fabulous__config_mapping__unplaced_bits": len(moved.unplaced_bits),
            # The loop stops when a proposal repeats the mapping it was made
            # from, which only this step can see without re-reading the files.
            "fabulous__config_mapping__unchanged": int(
                proposal.bit_at == current.bit_at
            ),
        }
        return {
            CONFIG_MEM_FORMAT: LibrelanePath(str(out)),
            RECONNECT_FORMAT: LibrelanePath(str(reconnect)),
        }, metrics

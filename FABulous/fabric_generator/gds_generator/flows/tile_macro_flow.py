"""Tile optimisation flows for FABulous fabric generation."""

from pathlib import Path
from typing import Any

from librelane.config.variable import Variable
from librelane.flows.classic import Classic
from librelane.flows.flow import Flow
from librelane.flows.sequential import SequentialFlow
from librelane.logging.logger import warn
from librelane.state.state import State
from librelane.steps import odb as Odb
from librelane.steps import openroad as OpenROAD
from librelane.steps.step import Step

from FABulous.fabric_generator.gds_generator.flows.flow_define import (
    check_steps,
    classic_gating_config_vars,
    physical_steps,
    prep_steps,
    write_out_steps,
)
from FABulous.fabric_generator.gds_generator.helper import (
    get_routing_obstructions,
    round_die_area,
)
from FABulous.fabric_generator.gds_generator.steps.add_buffer import AddBuffers
from FABulous.fabric_generator.gds_generator.steps.custom_pdn import CustomGeneratePDN
from FABulous.fabric_generator.gds_generator.steps.tile_IO_placement import (
    FABulousTileIOPlacement,
)
from FABulous.fabric_generator.gds_generator.steps.tile_optimisation import (
    TileOptimisation,
)

subs = {
    # Disable STA
    "OpenROAD.STAPrePNR*": None,
    "OpenROAD.STAMidPNR*": None,
    "OpenROAD.STAPostPNR*": None,
    # IO placement
    "Odb.CustomIOPlacement": FABulousTileIOPlacement,
    # Power
    "OpenROAD.GeneratePDN": CustomGeneratePDN,
    "OpenROAD.Resize*": None,
    "OpenROAD.RepairDesign*": None,
    "+OpenROAD.GlobalPlacement": AddBuffers,
}

configs = Classic.config_vars + [
    Variable(
        "FABULOUS_TILE_DIR",
        Path,
        "Path to the tile directory where the CSV file is located.",
    ),
    Variable(
        "FABULOUS_TILE_LOGICAL_WIDTH", int, "The logical width of the tile.", default=1
    ),
    Variable(
        "FABULOUS_TILE_LOGICAL_HEIGHT",
        int,
        "The logical height of the tile.",
        default=1,
    ),
]


@Flow.factory.register()
class FABulousTileVerilogMarcoFlow(SequentialFlow):
    """A tile optimisation flow for FABulous fabric generation from Verilog."""

    Steps = (
        prep_steps
        + [
            TileOptimisation,
            OpenROAD.FillInsertion,
            Odb.CellFrequencyTables,
            OpenROAD.RCX,
            OpenROAD.IRDropReport,
        ]
        + write_out_steps
        + check_steps
    )

    config_vars = configs

    gating_config_vars = classic_gating_config_vars

    def run(
        self,
        initial_state: State,
        *args: Any,  # noqa: ANN401
        **kwargs: dict,
    ) -> tuple[State, list[Step]]:
        """Run the FABulous tile optimisation flow."""
        self.config = round_die_area(self.config)
        if (
            "ROUTING_OBSTRUCTIONS" not in self.config
            or self.config["ROUTING_OBSTRUCTIONS"] is None
        ):
            self.config = self.config.copy(
                ROUTING_OBSTRUCTIONS=get_routing_obstructions(self.config)
            )
        return super().run(initial_state, *args, **kwargs)


@Flow.factory.register()
class FABulousTileVerilogMarcoFlowClassic(SequentialFlow):
    """Classic LibreLane flow for FABulous fabric generation from Verilog."""

    Steps = prep_steps + physical_steps + write_out_steps + check_steps
    Substitutions = subs
    config_vars = configs
    gating_config_vars = classic_gating_config_vars

    def run(
        self,
        initial_state: State,
        *args: Any,  # noqa: ANN401
        **kwargs: dict,
    ) -> tuple[State, list[Step]]:
        """Run the no optimisation FABulous verilog tile flow."""
        self.config = round_die_area(self.config)
        if (
            "ROUTING_OBSTRUCTIONS" not in self.config
            or self.config["ROUTING_OBSTRUCTIONS"] is None
        ):
            self.config = self.config.copy(
                ROUTING_OBSTRUCTIONS=get_routing_obstructions(self.config)
            )
        return super().run(initial_state, *args, **kwargs)


@Flow.factory.register()
class FABulousTileVHDLMarcoFlowClassic(SequentialFlow):
    """Classic LibreLane flow for FABulous fabric generation from VHDL."""

    Steps = prep_steps + physical_steps + write_out_steps + check_steps
    Substitutions = subs
    config_vars = configs
    gating_config_vars = classic_gating_config_vars

    def run(
        self,
        initial_state: State,
        *args: Any,  # noqa: ANN401
        **kwargs: dict,
    ) -> tuple[State, list[Step]]:  # noqa: ANN401
        """Run the FABulous tile VHDL flow."""
        warn("Linting and equivalence checking for VHDL files is disabled")
        round_die_area(self.config)
        if (
            "ROUTING_OBSTRUCTIONS" not in self.config
            or self.config["ROUTING_OBSTRUCTIONS"] is None
        ):
            self.config = self.config.copy(
                ROUTING_OBSTRUCTIONS=get_routing_obstructions(self.config)
            )
        return super().run(initial_state, *args, **kwargs)

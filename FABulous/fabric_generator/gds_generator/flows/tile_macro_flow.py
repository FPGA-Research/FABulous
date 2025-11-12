"""Tile optimisation flows for FABulous fabric generation."""

from pathlib import Path
from typing import Any
from FABulous.fabric_definition.Tile import Tile
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
from FABulous.fabric_generator.gds_generator.gen_io_pin_config_yaml import (
    generate_IO_pin_order_config,
)
from FABulous.FABulous_settings import get_context
from FABulous.fabric_definition.SuperTile import SuperTile

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
    Variable("FABULOUS_TILE_LOGICAL_WIDTH", int, "The logical width of the tile."),
    Variable("FABULOUS_TILE_LOGICAL_HEIGHT", int, "The logical height of the tile."),
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

    def __init__(
        self, tile_type: Tile | SuperTile, io_pin_config: Path, **config_overrides: dict
    ) -> None:
        tile_dir = tile_type.tileDir
        tile_name = tile_type.name

        # Build file list
        file_list = [str(f) for f in tile_dir.glob("**/*.v") if "macro" not in f.parts]
        if models_pack := get_context().models_pack:
            file_list.append(str(models_pack.resolve()))

        # Load base config
        tile_config_overrides = {}
        if (proj_dir / "Tile" / "include" / "gds_config.yaml").exists():
            tile_config_overrides.update(
                yaml.safe_load(
                    (proj_dir / "Tile" / "include" / "gds_config.yaml").read_text(
                        encoding="utf-8"
                    )
                )
            )

        gds_config_file = tile_dir / "gds_config.yaml"
        if gds_config_file.exists():
            tile_config_overrides.update(
                yaml.safe_load(gds_config_file.read_text(encoding="utf-8"))
            )

        # Apply die area override if provided
        if die_area is not None:
            tile_config_overrides["DIE_AREA"] = die_area

        # Determine logical dimensions
        if isinstance(tile_type, SuperTile):
            logical_width = tile_type.max_width
            logical_height = tile_type.max_height
        else:
            logical_width = 1
            logical_height = 1

        # Build tile configuration
        tile_config_dict = {
            "DESIGN_NAME": tile_name,
            "FABULOUS_IO_PIN_ORDER_CFG": out_file,
            "FABULOUS_TILE_DIR": str(tile_dir),
            "VERILOG_FILES": file_list,
            "FABULOUS_TILE_LOGICAL_WIDTH": logical_width,
            "FABULOUS_TILE_LOGICAL_HEIGHT": logical_height,
            "FABULOUS_OPT_MODE": opt_mode,
            "FABULOUS_FABRIC": fabric,
            "FABULOUS_PROJ_DIR": str(proj_dir),
        }

        # Add IO constraints if provided
        if io_min_width is not None:
            tile_config_dict["FABULOUS_IO_MIN_WIDTH"] = io_min_width
        if io_min_height is not None:
            tile_config_dict["FABULOUS_IO_MIN_HEIGHT"] = io_min_height

        # Add run directory override if provided

        # Add extra config if provided
        if extra_config:
            tile_config_dict.update(extra_config)

    def run(
        self,
        initial_state: State,
        *args: Any,  # noqa: ANN401
        **kwargs: dict,
    ) -> tuple[State, list[Step]]:
        """Run the FABulous tile optimisation flow."""

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
        ) and self.config["ROUTING_OBSTRUCTIONS"] is not False:
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
        ) and self.config["ROUTING_OBSTRUCTIONS"] is not False:
            self.config = self.config.copy(
                ROUTING_OBSTRUCTIONS=get_routing_obstructions(self.config)
            )
        return super().run(initial_state, *args, **kwargs)

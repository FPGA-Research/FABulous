"""Tile optimisation flows for FABulous fabric generation."""

from decimal import Decimal
from os.path import exists
from pathlib import Path
from typing import Any

import yaml
from librelane.config.variable import Variable
from librelane.flows.classic import Classic
from librelane.flows.flow import Flow, FlowException
from librelane.flows.sequential import SequentialFlow
from librelane.logging.logger import err, warn
from librelane.state.state import State
from librelane.steps import odb as Odb
from librelane.steps import openroad as OpenROAD
from librelane.steps.step import Step

from FABulous.fabric_definition.SuperTile import SuperTile
from FABulous.fabric_definition.Tile import Tile
from FABulous.fabric_generator.gds_generator.flows.flow_define import (
    check_steps,
    classic_gating_config_vars,
    physical_steps,
    prep_steps,
    write_out_steps,
)
from FABulous.fabric_generator.gds_generator.helper import (
    get_offset,
    get_pitch,
    get_routing_obstructions,
    round_die_area,
)
from FABulous.fabric_generator.gds_generator.steps.add_buffer import AddBuffers
from FABulous.fabric_generator.gds_generator.steps.custom_pdn import CustomGeneratePDN
from FABulous.fabric_generator.gds_generator.steps.tile_IO_placement import (
    FABulousTileIOPlacement,
)
from FABulous.fabric_generator.gds_generator.steps.tile_optimisation import (
    OptMode,
    TileOptimisation,
)
from FABulous.FABulous_settings import get_context

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
        "FABULOUS_IGNORE_DEFAULT_DIE_AREA",
        bool,
        "When is true will ignore the provided die area and "
        "use the default one instead.",
        default=False,
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

    def __init__(
        self,
        tile_type: Tile | SuperTile,
        io_pin_config: Path,
        opt_mode: OptMode,
        base_config_path: Path | None = None,
        override_config_path: Path | None = None,
        design_dir: Path | None = None,
        **custom_config_overrides: dict,
    ) -> None:
        # Build file list
        file_list = [
            str(f)
            for f in tile_type.tileDir.parent.glob("**/*.v")
            if "macro" not in f.parts
        ]
        if models_pack := get_context().models_pack:
            file_list.append(str(models_pack.resolve()))

        # Determine logical dimensions
        if isinstance(tile_type, SuperTile):
            logical_width = tile_type.max_width
            logical_height = tile_type.max_height
        else:
            logical_width = 1
            logical_height = 1

        # Build tile configuration
        tile_config_dict = {
            "DESIGN_NAME": tile_type.name,
            "FABULOUS_IO_PIN_ORDER_CFG": str(io_pin_config),
            "VERILOG_FILES": file_list,
            "FABULOUS_OPT_MODE": opt_mode,
        }

        # Load base config
        if base_config_path is not None and base_config_path.exists():
            tile_config_dict.update(
                yaml.safe_load(base_config_path.read_text(encoding="utf-8"))
            )

        if override_config_path is not None and override_config_path.exists():
            tile_config_dict.update(
                yaml.safe_load(override_config_path.read_text(encoding="utf-8"))
            )

        tile_config_dict.update(**custom_config_overrides)
        if "FABULOUS_OPT_MODE" in tile_config_dict:
            tile_config_dict["FABULOUS_OPT_MODE"] = OptMode(
                tile_config_dict["FABULOUS_OPT_MODE"]
            )
        default_design_dir = tile_type.tileDir.parent / "macro" / opt_mode.value
        default_design_dir.mkdir(parents=True, exist_ok=True)
        super().__init__(
            tile_config_dict,
            name=tile_type.name,
            design_dir=design_dir or default_design_dir,
            pdk=get_context().pdk,
            pdk_root=str(get_context().pdk_root.resolve().parent),
        )
        self.config = self.config.copy(
            FABULOUS_TILE_LOGICAL_WIDTH=logical_width,
            FABULOUS_TILE_LOGICAL_HEIGHT=logical_height,
        )
        x_pitch, y_pitch = get_pitch(self.config)
        x_spacing, y_spacing = get_offset(self.config)
        min_x, min_y = tile_type.get_min_die_area(
            x_pitch,
            y_pitch,
            self.config.get("IO_PIN_V_THINKNESS_MULT", Decimal(1)),
            self.config.get("IO_PIN_H_THINKNESS_MULT", Decimal(1)),
            x_pitch,
            y_pitch,
        )
        if opt_mode != OptMode.NO_OPT:
            if (
                self.config["FABULOUS_IGNORE_DEFAULT_DIE_AREA"]
                or self.config.get("DIE_AREA") is None
            ):
                self.config = self.config.copy(DIE_AREA=(0, 0, min_x, min_y))
            else:
                die_area = self.config.get("DIE_AREA")
                if die_area is None:
                    raise ValueError("DIE_AREA metric not found in state.")
                _, _, width, height = die_area
                width = Decimal(width)
                height = Decimal(height)
                if width < min_x or height < min_y:
                    raise FlowException(
                        f"DIE_AREA ({width}, {height}) is smaller than the "
                        f"minimum required area ({min_x}, {min_y}) for the "
                        f"tile {tile_type.name}. Please update the DIE_AREA "
                    )
        else:
            if not self.config.get("DIE_AREA"):
                err("If not using any optimisatin, DIE_AREA must be set.")
                raise FlowException("Invalid DIE_AREA configuration.")

        self.config = round_die_area(self.config)
        if (
            "ROUTING_OBSTRUCTIONS" not in self.config
            or self.config["ROUTING_OBSTRUCTIONS"] is None
        ) and self.config["ROUTING_OBSTRUCTIONS"] is not False:
            self.config = self.config.copy(
                ROUTING_OBSTRUCTIONS=get_routing_obstructions(self.config)
            )


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

"""Tile size optimisation step for FABulous fabric generator."""

import datetime
from decimal import Decimal
from enum import StrEnum
from pathlib import Path
from typing import cast

from librelane.config.variable import Variable
from librelane.logging.logger import info
from librelane.state.design_format import DesignFormat
from librelane.state.state import State
from librelane.steps import checker as Checker
from librelane.steps import odb as Odb
from librelane.steps import openroad as OpenROAD
from librelane.steps.step import MetricsUpdate, Step, ViewsUpdate

from FABulous.fabric_generator.gds_generator.helper import round_up_decimal
from FABulous.fabric_generator.gds_generator.steps.add_buffer import AddBuffers
from FABulous.fabric_generator.gds_generator.steps.auto_diode import (
    AutoEcoDiodeInsertion,
)
from FABulous.fabric_generator.gds_generator.steps.custom_pdn import CustomGeneratePDN
from FABulous.fabric_generator.gds_generator.steps.tile_IO_placement import (
    FABulousTileIOPlacement,
)
from FABulous.fabric_generator.gds_generator.steps.while_step import WhileStep


class OptMode(StrEnum):
    """Optimisation modes for tile size finding."""

    FIND_MIN_WIDTH = "find_min_width"
    FIND_MIN_HEIGHT = "find_min_height"
    BALANCE = "balance"
    LARGE = "large"


var = [
    Variable(
        "FABULOUS_OPTIMISATION_WIDTH_STEP_COUNT",
        int,
        "The number of placement sites by which the tile size reduces in each "
        "iteration. The actual reduction in DBU is this count multiplied by the PDK "
        "site dimensions.",
        default=4,
    ),
    Variable(
        "FABULOUS_OPTIMISATION_HEIGHT_STEP_COUNT",
        int,
        "The number of placement sites by which the tile size reduces in each "
        "iteration. The actual reduction in DBU is this count multiplied by the PDK "
        "site dimensions.",
        default=1,
    ),
    Variable(
        "FABULOUS_OPT_MODE",
        OptMode,
        "Optimisation mode to use. Options are: "
        " - 'find_min_width': default, finds minimal width by increasing from "
        "initial guess. "
        " - 'find_min_height': finds minimal height by increasing from initial guess. "
        " - 'balance': finds minimal area by starting from square bounding box and "
        "increasing alternatingly. "
        " - 'large': finds minimal area by starting from square bounding box and "
        "increasing both dimensions.",
        default=OptMode.FIND_MIN_WIDTH,
    ),
    Variable(
        "FABULOUS_OPT_RELAX",
        bool,
        "When True, increases dimensions instead of reducing (relaxation mode). "
        "When False, reduces dimensions for area minimization. "
        "The OptMode still controls which dimension changes (width/height/both). "
        "Default: False (area minimization)",
        default=False,
    ),
    Variable(
        "IGNORE_ANTENNA_VIOLATIONS",
        bool,
        "If True, antenna violations are ignored during tile optimisation. "
        "Default is False.",
        default=False,
    ),
    Variable(
        "IGNORE_DEFAULT_DIE_AREA",
        bool,
        "If True, default die area is ignored and using instance area for "
        "initial sizing. "
        "Default is False.",
        default=False,
    ),
]


@Step.factory.register()
class TileOptimisation(WhileStep):
    """Tile size optimisation step."""

    id = "FABulous.TileOptimisation"
    name = "Tile Optimisation"

    inputs = [DesignFormat.NETLIST]

    Steps = [
        OpenROAD.Floorplan,
        OpenROAD.DumpRCValues,
        Odb.CheckMacroAntennaProperties,
        Odb.SetPowerConnections,
        Odb.ManualMacroPlacement,
        OpenROAD.CutRows,
        OpenROAD.TapEndcapInsertion,
        Odb.AddPDNObstructions,
        CustomGeneratePDN,  # Custom PDN default pdn_cfg.tcl
        Odb.RemovePDNObstructions,
        Odb.AddRoutingObstructions,
        OpenROAD.GlobalPlacementSkipIO,
        FABulousTileIOPlacement,  # Replace with FABulous IO Placement
        Odb.ApplyDEFTemplate,
        OpenROAD.GlobalPlacement,
        AddBuffers,  # Add Buffers after Global Placement
        Odb.WriteVerilogHeader,
        Checker.PowerGridViolations,
        Odb.ManualGlobalPlacement,
        OpenROAD.DetailedPlacement,
        OpenROAD.CTS,
        OpenROAD.GlobalRouting,
        OpenROAD.CheckAntennas,
        Odb.DiodesOnPorts,
        OpenROAD.RepairAntennas,
        OpenROAD.DetailedRouting,
        AutoEcoDiodeInsertion,
        Odb.RemoveRoutingObstructions,
        OpenROAD.CheckAntennas,
        Checker.TrDRC,
        Odb.ReportDisconnectedPins,
        Checker.DisconnectedPins,
        Odb.ReportWireLength,
        Checker.WireLength,
    ]

    config_vars = var

    max_iterations = 20

    last_working_state: State | None = None

    raise_on_failure: bool = False

    break_next_iteration: bool = False

    def condition(self, state: State) -> bool:
        """Loop condition."""
        if state.metrics.get("route__drc_errors") is None:
            return True

        checklist = []
        if not self.config["IGNORE_ANTENNA_VIOLATIONS"]:
            checklist.append("antenna__violating__pins")
            checklist.append("antenna__violating__nets")

        checklist.append("route__drc_errors")
        for i in checklist:
            if (v := state.metrics.get(i)) and cast("int", v) > 0:
                return True

        return False

    def post_iteration_callback(
        self, post_iteration: State, full_iter_completed: bool
    ) -> State:
        """Save state if iteration completed successfully."""
        if full_iter_completed:
            self.last_working_state = post_iteration.copy()
            return post_iteration

        die_bbox = post_iteration.metrics.get("design__die__bbox", "0 0 0 0").split(" ")
        core_bbox = post_iteration.metrics.get("design__core__bbox", "0 0 0 0").split(
            " "
        )

        # Convert bbox string components to Decimal,
        # compute per-component absolute differences
        die_vals = list(map(Decimal, die_bbox))
        core_vals = list(map(Decimal, core_bbox))
        if post_iteration.metrics.get(
            "design__core__area", 0
        ) < post_iteration.metrics.get("design__instance__area", 0):
            extra = tuple(abs(a - b) for a, b in zip(die_vals, core_vals, strict=True))
            # Update config DIE_AREA to make core area at least equal to instance area
            self.config = self.config.copy(
                DIE_AREA=(
                    Decimal(0),
                    Decimal(0),
                    die_vals[2] + extra[0] + extra[2],
                    die_vals[3] + extra[1] + extra[3],
                )
            )
            return post_iteration

        if post_iteration.metrics.get("route__drc_errors") is None:
            # cannot get route error, likely floor plane problem, relax die area
            match self.config["FABULOUS_OPT_MODE"]:
                case OptMode.FIND_MIN_WIDTH:
                    self.config = self.config.copy(
                        DIE_AREA=(
                            Decimal(0),
                            Decimal(0),
                            die_vals[2],
                            die_vals[3] * Decimal(1.1),
                        )
                    )
                case OptMode.FIND_MIN_HEIGHT:
                    self.config = self.config.copy(
                        DIE_AREA=(
                            Decimal(0),
                            Decimal(0),
                            die_vals[2] * Decimal(1.1),
                            die_vals[3],
                        )
                    )
                case _:
                    self.config = self.config.copy(
                        DIE_AREA=(
                            Decimal(0),
                            Decimal(0),
                            die_vals[2] * Decimal(1.05),
                            die_vals[3] * Decimal(1.05),
                        )
                    )
            return post_iteration

        return post_iteration

    def pre_iteration_callback(self, pre_iteration: State) -> State:
        """Pre iteration callback."""
        die_area_raw: tuple[Decimal, Decimal, Decimal, Decimal] = self.config.get(
            "DIE_AREA", None
        )
        if die_area_raw is None:
            raise ValueError("DIE_AREA metric not found in state.")

        print(die_area_raw)
        _, _, width, height = die_area_raw

        # Get PDK site dimensions from metrics (if available)
        site_width_dbu = Decimal(
            pre_iteration.metrics.get("pdk__site_width", Decimal(1))
        )
        site_height_dbu = Decimal(
            pre_iteration.metrics.get("pdk__site_height", Decimal(1))
        )

        # Calculate step size based on PDK site dimensions
        width_step_count = self.config["FABULOUS_OPTIMISATION_WIDTH_STEP_COUNT"]
        height_step_count = self.config["FABULOUS_OPTIMISATION_HEIGHT_STEP_COUNT"]
        width_step = site_width_dbu * width_step_count
        height_step = site_height_dbu * height_step_count

        instance_area = Decimal(pre_iteration.metrics.get("design__instance__area", 0))
        new_height: Decimal
        new_width: Decimal

        if height == 0:
            height = instance_area.sqrt() / 2

        if width == 0:
            width = instance_area.sqrt() / 2

        match self.config["FABULOUS_OPT_MODE"]:
            case OptMode.FIND_MIN_WIDTH:
                if width == 0 or width * height < instance_area:
                    new_width, new_height = (instance_area / height, height)
                else:
                    new_width, new_height = (width + width_step, height)
            case OptMode.FIND_MIN_HEIGHT:
                # Initialize height based on instance area if not yet set properly
                if height == 0 or width * height < instance_area:
                    new_width, new_height = (width, instance_area / width)
                else:
                    new_width, new_height = (width, height + height_step)
            case OptMode.BALANCE:
                # Initialize to square bounding box if not yet set properly
                if width == 0 or height == 0 or width * height < instance_area:
                    initial_side = instance_area.sqrt()
                    new_width, new_height = (initial_side, initial_side)
                else:
                    if height > width:
                        new_width, new_height = (width + width_step, height)
                    else:
                        new_width, new_height = (width, height + height_step)
            case OptMode.LARGE:
                # Initialize to square bounding box if not yet set properly
                if width == 0 or height == 0 or width * height < instance_area:
                    initial_side = instance_area.sqrt()
                    new_width, new_height = (initial_side, initial_side)
                else:
                    new_width, new_height = (width + width_step, height + height_step)
            case _:
                raise ValueError(
                    f"Unknown FABULOUS_OPT_MODE: {self.config['FABULOUS_OPT_MODE']}"
                )

        die_area = (
            Decimal(0),
            Decimal(0),
            round_up_decimal(new_width, Decimal(site_width_dbu)),
            round_up_decimal(new_height, Decimal(site_height_dbu)),
        )
        self.config = self.config.copy(DIE_AREA=die_area)

        if p := self.get_current_iteration_dir():
            (p / "config.json").write_text(self.config.dumps())

        return pre_iteration

    def post_loop_callback(self, state: State) -> State:  # noqa: ARG002
        """Post loop callback."""
        if self.last_working_state is not None:
            return self.last_working_state
        raise RuntimeError("No working state found after tile optimisation.")

    def mid_iteration_break(self, state: State, step: type[Step]) -> bool:
        """Mid iteration callback."""
        if isinstance(step, Checker.TrDRC):
            if self.config["IGNORE_ANTENNA_VIOLATIONS"]:
                return cast("int", state.metrics.get("route__drc_errors")) > 0

            return (cast("int", state.metrics.get("antenna__violating__nets")) > 0) or (
                cast("int", state.metrics.get("antenna__violating__pins")) > 0
                or cast("int", state.metrics.get("route__drc_errors")) > 0
            )

        return False

    def run(
        self,
        state_in: State,
        **_kwargs: dict,
    ) -> tuple[ViewsUpdate, MetricsUpdate]:
        """Run the tile optimisation step."""
        t = datetime.datetime.now()
        if self.config["IGNORE_ANTENNA_VIOLATIONS"]:
            info("Ignoring antenna violations during tile optimisation.")
            self.config = self.config.copy(ERROR_ON_TR_DRC=False)
        if self.config["IGNORE_DEFAULT_DIE_AREA"]:
            self.config = self.config.copy(
                DIE_AREA=(Decimal(0), Decimal(0), Decimal(0), Decimal(0))
            )
        result = super().run(state_in, **_kwargs)
        (Path(self.step_dir) / "runtime.txt").write_text(
            str(datetime.datetime.now() - t)
        )
        return result

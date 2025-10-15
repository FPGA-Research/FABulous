"""Tile size optimisation step for FABulous fabric generator."""

from enum import StrEnum
from typing import cast

from librelane.config.variable import Variable
from librelane.state.design_format import DesignFormat
from librelane.state.state import State
from librelane.steps import checker as Checker
from librelane.steps import odb as Odb
from librelane.steps import openroad as OpenROAD
from librelane.steps.step import Step

from FABulous.fabric_generator.gds_generator.steps.add_buffer import AddBuffers
from FABulous.fabric_generator.gds_generator.steps.custom_pdn import CustomGeneratePDN
from FABulous.fabric_generator.gds_generator.steps.round_die_area import (
    RoundDieArea,
)
from FABulous.fabric_generator.gds_generator.steps.tile_IO_placement import (
    FABulousTileIOPlacement,
)
from FABulous.fabric_generator.gds_generator.steps.while_step import WhileStep


class OptMode(StrEnum):
    """Optimisation modes for tile size reduction."""

    FIX_HEIGHT = "fix_height"
    FIX_WIDTH = "fix_width"
    BALANCED = "balanced"
    AGGRESSIVE = "aggressive"


var = [
    Variable(
        "FABULOUS_OPTIMISATION_STEP_COUNT",
        int,
        "The number of placement sites by which the tile size reduces in each "
        "iteration. The actual reduction in DBU is this count multiplied by the PDK "
        "site dimensions.",
        default=5,
    ),
    Variable(
        "FABULOUS_OPT_MODE",
        OptMode,
        "Optimisation mode to use. Options are: "
        " - 'fix_height': default, keeps height constant and reduces width. "
        " - 'fix_width': keeps width constant and reduces height. "
        " - 'balanced': alternate width and height reduction. "
        " - 'aggressive': reduces both height and width at the same time.",
        default=OptMode.FIX_HEIGHT,
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
]


@Step.factory.register()
class TileOptimisation(WhileStep):
    """Tile size optimisation step."""

    id = "FABulous.TileOptimisation"
    name = "Tile Optimisation"

    inputs = [DesignFormat.NETLIST]

    Steps = [
        RoundDieArea,
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
        Odb.RemoveRoutingObstructions,
        OpenROAD.CheckAntennas,
        Checker.TrDRC,
        Odb.ReportDisconnectedPins,
        Checker.DisconnectedPins,
        Odb.ReportWireLength,
        Checker.WireLength,
    ]

    config_vars = var

    max_iterations = 5

    last_working_state: State | None = None

    def condition(self, state: State) -> bool:
        """Loop condition."""
        for i in [
            "antenna__violating__pins",
            "antenna__violating__nets",
            "route__antenna_violation__count",
            "route__drc_errors",
        ]:
            if v := state.metrics.get(i):
                if cast("int", v) > 0:
                    return False
            else:
                return True

        return True

    def post_iteration_callback(
        self, post_iteration: State, full_iter_completed: bool
    ) -> State:
        """Save state if iteration completed successfully."""
        if full_iter_completed:
            self.last_working_state = post_iteration.copy()
        return post_iteration

    def pre_iteration_callback(self, pre_iteration: State) -> State:
        """Pre iteration callback."""
        die_area_raw: tuple[int, int, int, int] = self.config.get("DIE_AREA", None)
        _, _, width, height = die_area_raw
        die_area = (width, height)
        if die_area is None:
            raise ValueError("DIE_AREA metric not found in state.")

        # Get PDK site dimensions from metrics (if available)
        site_width_dbu = int(pre_iteration.metrics.get("pdk__site_width", 1))
        site_height_dbu = int(pre_iteration.metrics.get("pdk__site_height", 1))

        # Calculate step size based on PDK site dimensions
        step_count = self.config["FABULOUS_OPTIMISATION_STEP_COUNT"]
        width_step = site_width_dbu * step_count
        height_step = site_height_dbu * step_count

        # Determine direction: relaxation (+) or minimization (-)
        direction = 1 if self.config["FABULOUS_OPT_RELAX"] else -1

        match self.config["FABULOUS_OPT_MODE"]:
            case OptMode.FIX_HEIGHT:
                die_area = (
                    0,
                    0,
                    width + (direction * width_step),
                    height,
                )
            case OptMode.FIX_WIDTH:
                die_area = (
                    0,
                    0,
                    width,
                    height + (direction * height_step),
                )
            case OptMode.BALANCED:
                if (
                    width > height  # Adjust the larger dimension first
                ):
                    die_area = (
                        0,
                        0,
                        width + (direction * width_step),
                        height,
                    )
                else:
                    die_area = (
                        0,
                        0,
                        width,
                        height + (direction * height_step),
                    )
            case OptMode.AGGRESSIVE:
                die_area = (
                    0,
                    0,
                    width + (direction * width_step),
                    height + (direction * height_step),
                )
            case _:
                raise ValueError(
                    f"Unknown FABULOUS_OPT_MODE: {self.config['FABULOUS_OPT_MODE']}"
                )
        self.config = self.config.copy(DIE_AREA=die_area)

        return pre_iteration

    def post_loop_callback(self, state: State) -> State:  # noqa: ARG002
        """Post loop callback."""
        if self.last_working_state is not None:
            return self.last_working_state
        raise RuntimeError("No working state found after tile optimisation.")

    def mid_iteration_break(self, state: State, step: type[Step]) -> bool:
        """Mid iteration callback."""
        if isinstance(step, Checker.TrDRC):
            return (cast("int", state.metrics.get("antenna__violating__nets")) > 0) or (
                cast("int", state.metrics.get("antenna__violating__pins")) > 0
                or cast("int", state.metrics.get("route__drc_errors")) > 0
            )

        return False

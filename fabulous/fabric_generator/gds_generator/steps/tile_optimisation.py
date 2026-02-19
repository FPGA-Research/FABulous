"""Tile size optimisation step for FABulous fabric generator."""

from decimal import Decimal
from enum import StrEnum
from typing import cast

from librelane.config.variable import Variable
from librelane.logging.logger import info
from librelane.state.design_format import DesignFormat
from librelane.state.state import State
from librelane.steps import checker as Checker
from librelane.steps import odb as Odb
from librelane.steps import openroad as OpenROAD
from librelane.steps.step import MetricsUpdate, Step, ViewsUpdate

from fabulous.fabric_generator.gds_generator.helper import (
    get_pitch,
    get_routing_obstructions,
    round_up_decimal,
)
from fabulous.fabric_generator.gds_generator.steps.add_buffer import AddBuffers
from fabulous.fabric_generator.gds_generator.steps.custom_pdn import CustomGeneratePDN
from fabulous.fabric_generator.gds_generator.steps.tile_IO_placement import (
    FABulousTileIOPlacement,
)
from fabulous.fabric_generator.gds_generator.steps.while_step import WhileStep


class OptMode(StrEnum):
    """Optimisation modes for tile size finding."""

    FIND_MIN_WIDTH = "find_min_width"
    FIND_MIN_HEIGHT = "find_min_height"
    BALANCE = "balance"
    LARGE = "large"
    NO_OPT = "no_opt"

    @classmethod
    def _missing_(cls, value: object) -> "OptMode":
        """Look up an OptMode member case-insensitively."""
        if isinstance(value, str):
            value_lower = value.lower()
            for member in cls:
                if member.value == value_lower:
                    return member

        if value is None:
            return cls.NO_OPT

        raise ValueError(f"{value!r} is not a valid {cls.__name__}")


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
        " - 'no-opt': Disable optimisation.",
        default=OptMode.BALANCE,
    ),
    Variable(
        "IGNORE_ANTENNA_VIOLATIONS",
        bool,
        "If True, antenna violations are ignored during tile optimisation. "
        "Default is False.",
        default=False,
    ),
    Variable(
        "FABULOUS_PIN_MIN_WIDTH",
        Decimal,
        "Minimum tile width based on pin requirements.",
        default=Decimal(0),
    ),
    Variable(
        "FABULOUS_PIN_MIN_HEIGHT",
        Decimal,
        "Minimum tile height based on pin requirements.",
        default=Decimal(0),
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

    to_change_width: bool = False

    iter_count: int = 0

    last_core_area: Decimal | None = None

    last_drc_errors: int = 0

    def condition(self, state: State) -> bool:
        """Loop condition."""
        if state.metrics.get("route__drc_errors") is None:
            return True

        metrics_to_check = ["route__drc_errors"]
        if not self.config["IGNORE_ANTENNA_VIOLATIONS"]:
            metrics_to_check.extend(
                ["antenna__violating__pins", "antenna__violating__nets"]
            )

        return any(cast("int", state.metrics.get(m, 0)) > 0 for m in metrics_to_check)

    def post_iteration_callback(
        self, post_iteration: State, full_iter_completed: bool
    ) -> State:
        """Save state if iteration completed successfully."""
        # Capture core area for the next iteration's scaling check.
        # The WhileStep resets state each iteration, so we persist this
        # on the instance to carry it across resets.
        if (ca := post_iteration.metrics.get("design__core__area")) is not None:
            self.last_core_area = Decimal(ca)

        self.last_drc_errors = cast(
            "int", post_iteration.metrics.get("route__drc_errors", 0)
        )

        if full_iter_completed:
            self.last_working_state = post_iteration.copy()
            return post_iteration

        self.to_change_width = not self.to_change_width
        self.iter_count += 1
        return post_iteration

    def _refresh_routing_obstructions(self) -> None:
        """Clear and recompute routing obstructions from current config.

        The two-step process is required because get_routing_obstructions reads
        ROUTING_OBSTRUCTIONS from config and appends edge obstructions. Clearing
        first prevents stale obstructions from accumulating across iterations.
        """
        self.config = self.config.copy(ROUTING_OBSTRUCTIONS=None)
        self.config = self.config.copy(
            ROUTING_OBSTRUCTIONS=get_routing_obstructions(self.config)
        )

    def pre_iteration_callback(self, pre_iteration: State) -> State:
        """Pre iteration callback."""
        if self.config["FABULOUS_OPT_MODE"] == OptMode.NO_OPT:
            self.config = self.config.copy(DRT_OPT_ITERS=64)
            self._refresh_routing_obstructions()
            return pre_iteration

        die_area_raw: tuple[Decimal, Decimal, Decimal, Decimal] = self.config.get(
            "DIE_AREA", None
        )
        if die_area_raw is None:
            raise ValueError("DIE_AREA metric not found in state.")

        _, _, width, height = die_area_raw

        site_width = Decimal(pre_iteration.metrics.get("pdk__site_width", Decimal(1)))
        site_height = Decimal(pre_iteration.metrics.get("pdk__site_height", Decimal(1)))
        x_pitch, y_pitch = get_pitch(self.config)

        width_step = site_width * self.config["FABULOUS_OPTIMISATION_WIDTH_STEP_COUNT"]
        height_step = (
            site_height * self.config["FABULOUS_OPTIMISATION_HEIGHT_STEP_COUNT"]
        )

        # Diode insertion on ports adds cells that need extra area.
        # Scale both step sizes so the optimiser grows the tile faster
        # to accommodate the additional diode cells.
        diode_on_ports: str = self.config.get("DIODE_ON_PORTS", "none")
        if diode_on_ports == "both":
            width_step += site_width * 8
            height_step += site_height * 8
        elif diode_on_ports in ("in", "out"):
            width_step += site_width * 4
            height_step += site_height * 4

        instance_area = Decimal(pre_iteration.metrics.get("design__instance__area", 0))
        if self.last_core_area is not None:
            core_area = self.last_core_area
        else:
            # First iteration: no actual core area yet. Estimate core area
            # from die area minus floorplan margins (site insets on each side)
            # so the overshoot scaling triggers when cells barely fit.
            sites_per_side_x = 6
            margin_x = Decimal(2) * site_width * sites_per_side_x
            margin_y = Decimal(2) * site_height
            core_area = (width - margin_x) * (height - margin_y)

        new_width, new_height = self._compute_new_dimensions(
            width,
            height,
            width_step,
            height_step,
            instance_area,
            core_area,
        )

        die_area = (
            Decimal(0),
            Decimal(0),
            round_up_decimal(new_width, x_pitch),
            round_up_decimal(new_height, y_pitch),
        )
        self.config = self.config.copy(
            DRT_OPT_ITERS=5 + self.iter_count,
            DIE_AREA=die_area,
        )
        self._refresh_routing_obstructions()

        if p := self.get_current_iteration_dir():
            (p / "config.json").write_text(self.config.dumps())

        return pre_iteration

    def _compute_new_dimensions(
        self,
        width: Decimal,
        height: Decimal,
        width_step: Decimal,
        height_step: Decimal,
        instance_area: Decimal,
        core_area: Decimal,
    ) -> tuple[Decimal, Decimal]:
        """Compute the next tile dimensions based on the optimisation mode.

        First ensures the die can accommodate the instance area by scaling
        the non-optimised dimension (directional modes) or both dimensions
        proportionally (balanced/large modes). Then applies the iterative
        growth step. Finally, for directional modes, if the previous
        iteration had DRC violations the non-optimised dimension is boosted
        proportionally to the violation count so that extreme aspect ratios
        self-correct without a hard cap.
        """
        opt_mode = self.config["FABULOUS_OPT_MODE"]

        # Scale up proportionally if instance area exceeds the placeable
        # core area.  Using sqrt on both dimensions keeps aspect ratios
        # reasonable regardless of optimisation mode.  Directional
        # exploration is handled by the iterative step below.
        if core_area > 0 and instance_area > core_area:
            scale = (instance_area / core_area).sqrt()
            width *= scale
            height *= scale

        # Apply iterative step
        match opt_mode:
            case OptMode.FIND_MIN_WIDTH:
                width += width_step
            case OptMode.FIND_MIN_HEIGHT:
                height += height_step
            case OptMode.BALANCE:
                if self.to_change_width:
                    width += width_step
                else:
                    height += height_step
            case OptMode.LARGE:
                width += width_step
                height += height_step
            case _:
                raise ValueError(f"Unknown FABULOUS_OPT_MODE: {opt_mode}")

        # Adaptive scaling: if the previous iteration had DRC violations,
        # also grow the non-optimised dimension. The boost is proportional
        # to the violation count (violations / 1000), so a tile with 17k
        # violations gets a ~17x step boost while a tile with 50 violations
        # gets almost nothing. This lets extreme aspect ratios self-correct
        # without imposing a hard cap.
        if self.last_drc_errors > 0:
            boost = Decimal(self.last_drc_errors) / Decimal(1000)
            if opt_mode == OptMode.FIND_MIN_WIDTH:
                height += height_step * boost
            elif opt_mode == OptMode.FIND_MIN_HEIGHT:
                width += width_step * boost

        return width, height

    def post_loop_callback(self, state: State) -> State:  # noqa: ARG002
        """Post loop callback."""
        if self.last_working_state is None:
            if self.config["FABULOUS_OPT_MODE"] == OptMode.NO_OPT:
                raise RuntimeError(
                    "Fail to find a clean state after the physical implementation"
                )
            raise RuntimeError("No working state found after tile optimisation.")

        result = self.last_working_state

        # Update config with actual die area so downstream steps
        # (e.g. Magic/KLayout stream-out) use the correct boundary.
        die_bbox_str = result.metrics.get("design__die__bbox")
        if die_bbox_str is not None:
            new_die_area = tuple(Decimal(x) for x in die_bbox_str.split())
            old_die_area = self.config.get("DIE_AREA")
            if (
                old_die_area is None
                or tuple(Decimal(x) for x in old_die_area) != new_die_area
            ):
                info(
                    f"Updating DIE_AREA from {old_die_area} to {new_die_area} "
                    "based on TileOptimisation output."
                )
                self.config = self.config.copy(DIE_AREA=new_die_area)

        return result

    def mid_iteration_break(self, state: State, step: type[Step]) -> bool:
        """Mid iteration callback."""
        if not isinstance(step, Checker.TrDRC):
            return False

        metrics_to_check = ["route__drc_errors"]
        if not self.config["IGNORE_ANTENNA_VIOLATIONS"]:
            metrics_to_check.extend(
                [
                    "antenna__violating__nets",
                    "antenna__violating__pins",
                ]
            )

        return any(cast("int", state.metrics.get(m, 0)) > 0 for m in metrics_to_check)

    def run(
        self,
        state_in: State,
        **_kwargs: dict,
    ) -> tuple[ViewsUpdate, MetricsUpdate]:
        """Run the tile optimisation step."""
        if self.config["IGNORE_ANTENNA_VIOLATIONS"]:
            info("Ignoring antenna violations during tile optimisation.")
            self.config = self.config.copy(ERROR_ON_TR_DRC=False)
        if self.config["FABULOUS_OPT_MODE"] == OptMode.NO_OPT:
            self.max_iterations = 1
        return super().run(state_in, **_kwargs)

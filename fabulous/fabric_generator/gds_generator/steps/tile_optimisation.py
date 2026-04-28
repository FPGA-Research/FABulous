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
    Variable(
        "FABULOUS_TILE_LOGICAL_WIDTH",
        int,
        "Supertile logical column count; 1 for regular tiles. Used to lock the "
        "balance-mode aspect ratio to logical_w:logical_h (square cells).",
        default=1,
    ),
    Variable(
        "FABULOUS_TILE_LOGICAL_HEIGHT",
        int,
        "Supertile logical row count; 1 for regular tiles. Paired with "
        "FABULOUS_TILE_LOGICAL_WIDTH for aspect locking.",
        default=1,
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

    clean_probes: list[list[float]] = []

    raise_on_failure: bool = False

    iter_count: int = 0

    last_core_area: Decimal | None = None

    # Binary-search state for directional modes.
    bracket_low: Decimal | None = None

    bracket_high: Decimal | None = None

    bracket_cap: Decimal | None = None

    bracket_exhausted: bool = False

    def _is_directional(self) -> bool:
        """Return True when the current mode is FIND_MIN_WIDTH or FIND_MIN_HEIGHT."""
        return self.config["FABULOUS_OPT_MODE"] in (
            OptMode.FIND_MIN_WIDTH,
            OptMode.FIND_MIN_HEIGHT,
        )

    def _directional_target(
        self, die_area: tuple[Decimal, Decimal, Decimal, Decimal]
    ) -> Decimal:
        """Return the axis value being minimised in the current directional mode."""
        _, _, w, h = die_area
        if self.config["FABULOUS_OPT_MODE"] == OptMode.FIND_MIN_WIDTH:
            return Decimal(w)
        return Decimal(h)

    def condition(self, state: State) -> bool:
        """Loop condition."""
        if self._is_directional():
            if self.bracket_exhausted:
                return False
            if self.bracket_high is not None and self.bracket_low is not None:
                # Converged when the gap between largest-fail and smallest-success
                # is within one pitch on the target axis.
                x_pitch, y_pitch = get_pitch(self.config)
                if self.config["FABULOUS_OPT_MODE"] == OptMode.FIND_MIN_WIDTH:
                    pitch = x_pitch
                else:
                    pitch = y_pitch
                if self.bracket_high - self.bracket_low <= pitch:
                    return False
            return True

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

        # DRC and antenna clean design as sample for the later optimisation.
        if full_iter_completed:
            die_bbox = post_iteration.metrics.get("design__die__bbox")
            if die_bbox is not None:
                self.clean_probes.append([float(v) for v in die_bbox.split()])

        if self._is_directional():
            target = self._directional_target(self.config["DIE_AREA"])
            if full_iter_completed:
                # Smallest-so-far working target axis; keep the best working state.
                if self.bracket_high is None or target < self.bracket_high:
                    self.bracket_high = target
                    self.last_working_state = post_iteration.copy()
            elif self.bracket_low is None or target > self.bracket_low:
                self.bracket_low = target
            return post_iteration

        if full_iter_completed:
            self.last_working_state = post_iteration.copy()
            return post_iteration

        self.iter_count += 1
        return post_iteration

    def _refresh_routing_obstructions(self) -> None:
        """Clear and recompute routing obstructions from current config.

        The two-step process is required because get_routing_obstructions reads
        ROUTING_OBSTRUCTIONS from config and appends edge obstructions. Clearing first
        prevents stale obstructions from accumulating across iterations.
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
            margin_x = Decimal(2) * site_width
            margin_y = Decimal(2) * site_height
            core_area = (width - margin_x) * (height - margin_y)

        if self._is_directional():
            new_width, new_height = self._compute_binary_search_dimensions(
                width, height
            )
        else:
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
        """Compute the next BALANCE / LARGE tile dimensions.

        Scales both axes proportionally when the core cannot hold the instance area,
        then applies the per-iteration step. Directional modes are handled separately
        by ``_compute_binary_search_dimensions``.
        """
        opt_mode = self.config["FABULOUS_OPT_MODE"]

        # Ensure the die can physically hold the instance area before the
        # iterative step nudges it.
        if core_area > 0 and instance_area > core_area:
            scale = (instance_area / core_area).sqrt()
            width *= scale
            height *= scale

        logical_w = Decimal(self.config.get("FABULOUS_TILE_LOGICAL_WIDTH", 1))
        logical_h = Decimal(self.config.get("FABULOUS_TILE_LOGICAL_HEIGHT", 1))
        is_supertile = logical_w * logical_h > Decimal(1)

        match opt_mode:
            case OptMode.BALANCE:
                if is_supertile:
                    cell_step = max(width_step / logical_w, height_step / logical_h)
                    width += cell_step * logical_w
                    height += cell_step * logical_h
                elif width <= height:
                    width += width_step
                else:
                    height += height_step
            case OptMode.LARGE:
                width += width_step
                height += height_step
            case _:
                raise ValueError(f"Unknown FABULOUS_OPT_MODE: {opt_mode}")

        return width, height

    def _compute_binary_search_dimensions(
        self,
        width: Decimal,
        height: Decimal,
    ) -> tuple[Decimal, Decimal]:
        """Compute the next DIE_AREA for FIND_MIN_WIDTH / FIND_MIN_HEIGHT.

        Two-phase search on the target axis while holding the other axis at its
        smart-init value:

        - **Bracketing (exponential)**: while no working point has been seen, double
          the target axis each iteration. If doubling would exceed ``bracket_cap``,
          mark the search exhausted — the aspect is likely infeasible.
        - **Bisecting**: once at least one working point has been seen, bisect
          between ``bracket_low`` (largest failing) and ``bracket_high`` (smallest
          working). When only ``bracket_high`` exists (very first iter worked),
          bisect between the pin-floor and ``bracket_high`` to push even smaller.

        The non-target axis is kept at its incoming value so the mode stays true to
        "minimise this one axis".
        """
        target_is_width = self.config["FABULOUS_OPT_MODE"] == OptMode.FIND_MIN_WIDTH
        current_target = width if target_is_width else height
        non_target = height if target_is_width else width

        pin_floor = Decimal(
            self.config.get(
                "FABULOUS_PIN_MIN_WIDTH"
                if target_is_width
                else "FABULOUS_PIN_MIN_HEIGHT",
                0,
            )
        )

        x_pitch, y_pitch = get_pitch(self.config)
        pitch = x_pitch if target_is_width else y_pitch

        if self.bracket_high is None:
            next_target = current_target * Decimal(2)
            if self.bracket_cap is not None and next_target > self.bracket_cap:
                if current_target >= self.bracket_cap:
                    self.bracket_exhausted = True
                    next_target = current_target
                else:
                    next_target = self.bracket_cap
        elif self.bracket_low is None:
            next_target = (pin_floor + self.bracket_high) / Decimal(2)
            if next_target <= pin_floor or self.bracket_high - pin_floor <= pitch:
                next_target = self.bracket_high
                self.bracket_low = pin_floor
        else:
            next_target = (self.bracket_low + self.bracket_high) / Decimal(2)

        if target_is_width:
            return next_target, non_target
        return non_target, next_target

    def post_loop_callback(self, state: State) -> State:  # noqa: ARG002
        """Post loop callback."""
        if self.last_working_state is None:
            if self.config["FABULOUS_OPT_MODE"] == OptMode.NO_OPT:
                raise RuntimeError(
                    "Fail to find a clean state after the physical implementation"
                )
            raise RuntimeError("No working state found after tile optimisation.")

        # State.metrics is an immutable dict; rebuild the state with an added
        # clean_probes entry rather than mutating in place.
        from librelane.common import GenericImmutableDict

        last = self.last_working_state
        result = State(
            last,
            metrics=GenericImmutableDict(
                last.metrics,
                overrides={"fabulous__clean_probes": list(self.clean_probes)},
            ),
        )

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
        self.clean_probes = []
        if self.config["IGNORE_ANTENNA_VIOLATIONS"]:
            info("Ignoring antenna violations during tile optimisation.")
            self.config = self.config.copy(ERROR_ON_TR_DRC=False)
        if self.config["FABULOUS_OPT_MODE"] == OptMode.NO_OPT:
            self.max_iterations = 1
            return super().run(state_in, **_kwargs)

        opt_mode = self.config["FABULOUS_OPT_MODE"]
        pin_w = Decimal(self.config.get("FABULOUS_PIN_MIN_WIDTH", 0))
        pin_h = Decimal(self.config.get("FABULOUS_PIN_MIN_HEIGHT", 0))
        instance_area = Decimal(state_in.metrics.get("design__instance__area", 0))

        # Short-circuit directional modes whose pin floor already comfortably
        # covers the instance area - iterating would only produce a tall/narrow
        # bbox at the pin floor anyway.
        if self._is_directional() and (
            pin_w > 0 and pin_h > 0 and pin_w * pin_h >= instance_area * Decimal("1.3")
        ):
            info(
                f"Pin-min area ({pin_w}x{pin_h}) already comfortably covers "
                f"instance area ({instance_area}); short-circuiting "
                f"{opt_mode.value} to 1 iter."
            )
            self.max_iterations = 1
            return super().run(state_in, **_kwargs)

        # Size the first iteration's die so it can hold the synth-reported
        # stdcell area at 100% utilisation. Buffer/CTS/routing slack is earned
        # by subsequent while-loop iterations. Per mode:
        #   FIND_MIN_WIDTH:  keep h = pin_min_h, widen to fit the cells.
        #   FIND_MIN_HEIGHT: keep w = pin_min_w, grow h to fit the cells.
        #   BALANCE / LARGE: square bbox sized to hold the cells.
        if instance_area > 0 and pin_w > 0 and pin_h > 0:
            logical_w = Decimal(self.config.get("FABULOUS_TILE_LOGICAL_WIDTH", 1))
            logical_h = Decimal(self.config.get("FABULOUS_TILE_LOGICAL_HEIGHT", 1))
            match opt_mode:
                case OptMode.FIND_MIN_WIDTH:
                    init_h = pin_h
                    init_w = max(pin_w, instance_area / init_h)
                case OptMode.FIND_MIN_HEIGHT:
                    init_w = pin_w
                    init_h = max(pin_h, instance_area / init_w)
                case _:  # BALANCE, LARGE — target square cells, aspect = W:H.
                    cell_side = (instance_area / (logical_w * logical_h)).sqrt()
                    init_w = logical_w * cell_side
                    init_h = logical_h * cell_side
                    # Respect pin floor; if forced up on one axis, scale the
                    # other to keep logical aspect.
                    if pin_w > init_w:
                        init_w = pin_w
                        init_h = max(init_h, init_w * logical_h / logical_w)
                    if pin_h > init_h:
                        init_h = pin_h
                        init_w = max(init_w, init_h * logical_w / logical_h)

            x_pitch, y_pitch = get_pitch(self.config)
            init_w = round_up_decimal(init_w, x_pitch)
            init_h = round_up_decimal(init_h, y_pitch)

            die_area = self.config.get("DIE_AREA")
            current_w = Decimal(die_area[2]) if die_area else Decimal(0)
            current_h = Decimal(die_area[3]) if die_area else Decimal(0)

            # Grow per-axis only so a user-supplied DIE_AREA override on the
            # non-target axis is preserved.
            new_w = max(current_w, init_w)
            new_h = max(current_h, init_h)
            if new_w > current_w or new_h > current_h:
                info(
                    f"Smart init DIE_AREA for {opt_mode.value}: "
                    f"{current_w}x{current_h} -> {new_w}x{new_h} "
                    f"(instance_area={instance_area})"
                )
                self.config = self.config.copy(
                    DIE_AREA=(Decimal(0), Decimal(0), new_w, new_h)
                )

        # Cap exponential growth at 4x the init target: beyond that the
        # aspect is effectively infeasible at the pin floor on the other axis.
        if self._is_directional():
            die_area = self.config.get("DIE_AREA")
            if die_area is not None:
                _, _, w, h = die_area
                if self.config["FABULOUS_OPT_MODE"] == OptMode.FIND_MIN_WIDTH:
                    self.bracket_cap = Decimal(w) * Decimal(4)
                else:
                    self.bracket_cap = Decimal(h) * Decimal(4)

        return super().run(state_in, **_kwargs)

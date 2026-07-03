"""Tests for TileAreaOptimisation step."""

# for testing private methods
# ruff: noqa: SLF001

from decimal import Decimal
from pathlib import Path

import pytest
from librelane.config.config import Config
from librelane.flows.flow import FlowException
from librelane.state.state import State
from pytest_mock import MockerFixture

from fabulous.fabric_generator.gds_generator.steps.tile_area_opt import (
    OptMode,
    TileAreaOptimisation,
)


class TestTileOptimisation:
    """Test suite for TileOptimisation step."""

    def test_condition_returns_true_on_drc_errors(
        self, mock_config: Config, mock_state: State
    ) -> None:
        """Test condition returns True when DRC errors exist."""
        mock_state.metrics["route__drc_errors"] = 5

        step = TileAreaOptimisation(mock_config)
        step.config = mock_config
        assert step.condition(mock_state) is True

    def test_condition_returns_true_on_antenna_violations(
        self, mock_config: Config, mock_state: State
    ) -> None:
        """Test condition returns True when antenna violations exist."""
        mock_state.metrics["route__drc_errors"] = 0
        mock_state.metrics["antenna__violating__nets"] = 2

        step = TileAreaOptimisation(mock_config)
        step.config = mock_config
        assert step.condition(mock_state) is True

    def test_condition_returns_false_when_no_errors(
        self, mock_config: Config, mock_state: State
    ) -> None:
        """Test condition returns False when no errors exist."""
        mock_state.metrics["route__drc_errors"] = 0
        mock_state.metrics["antenna__violating__nets"] = 0
        mock_state.metrics["antenna__violating__pins"] = 0

        # Non-directional modes terminate on clean DRC. Directional modes use a
        # bracket-based termination and ignore DRC when no bracket is set, so
        # pin the mode here.
        mock_config = mock_config.copy(FABULOUS_OPT_MODE=OptMode.BALANCE)
        step = TileAreaOptimisation(mock_config)
        step.config = mock_config
        assert step.condition(mock_state) is False

    def test_pre_iteration_callback_find_min_width_mode(
        self,
        mocker: MockerFixture,
        mock_config: Config,
        mock_state: State,
        tmp_path: Path,
    ) -> None:
        """Test pre_iteration_callback in find_min_width mode."""
        # Mock get_pitch to return reasonable pitch values
        mocker.patch(
            "fabulous.fabric_generator.gds_generator.steps.tile_area_opt.get_pitch",
            return_value=(Decimal("0.46"), Decimal("2.72")),
        )
        # Mock get_routing_obstructions to avoid config key errors
        mocker.patch(
            "fabulous.fabric_generator.gds_generator.steps.tile_area_opt.get_routing_obstructions",
            return_value=[],
        )

        mock_config = mock_config.copy(FABULOUS_OPT_MODE=OptMode.FIND_MIN_WIDTH)
        mock_config = mock_config.copy(
            DIE_AREA=(Decimal(0), Decimal(0), Decimal(100), Decimal(100))
        )
        mock_config = mock_config.copy(LEFT_MARGIN_MULT=Decimal(0))
        mock_config = mock_config.copy(RIGHT_MARGIN_MULT=Decimal(0))
        mock_config = mock_config.copy(BOTTOM_MARGIN_MULT=Decimal(0))
        mock_config = mock_config.copy(TOP_MARGIN_MULT=Decimal(0))

        step = TileAreaOptimisation(mock_config)
        step.step_dir = str(tmp_path)
        step.config = mock_config
        step.iter_count = 0
        step.pre_iteration_callback(mock_state)

        # DIE_AREA should be updated
        new_die_area = step.config["DIE_AREA"]
        assert new_die_area is not None
        assert new_die_area[2] >= Decimal(100)

    def test_post_loop_callback_returns_working_state(
        self, mock_config: Config, mock_state: State
    ) -> None:
        """Test post_loop_callback returns a state derived from the last working one.

        The result is a freshly constructed ``State`` so the ``fabulous__clean_probes``
        metric can be added onto an immutable metrics dict — identity comparison
        against ``mock_state`` no longer holds, but the original metrics must still be
        visible on the returned state.
        """
        step = TileAreaOptimisation(mock_config)
        step.config = mock_config
        step.last_working_state = State(metrics=mock_state.metrics)
        step.clean_probes = []

        result = step.post_loop_callback(mock_state)

        assert result.metrics["route__drc_errors"] == 0
        assert result.metrics["fabulous__clean_probes"] == []

    def test_post_loop_callback_raises_error_without_working_state(
        self, mock_config: Config, mock_state: State
    ) -> None:
        """Test post_loop_callback raises error if no working state found."""
        step = TileAreaOptimisation(mock_config)
        step.config = mock_config
        step.last_working_state = None

        with pytest.raises(RuntimeError, match="No working state found"):
            step.post_loop_callback(mock_state)

    def test_run_ignores_antenna_violations_when_configured(
        self, mocker: MockerFixture, mock_config: Config, mock_state: State
    ) -> None:
        """Test run method with IGNORE_ANTENNA_VIOLATIONS enabled."""
        mock_config = mock_config.copy(IGNORE_ANTENNA_VIOLATIONS=True)

        step = TileAreaOptimisation(mock_config)
        step.config = mock_config
        _mock_run = mocker.patch(
            "fabulous.fabric_generator.gds_generator.steps.tile_area_opt.WhileStep.run",
            return_value=({}, {}),
        )

        step.run(mock_state)

        # ERROR_ON_TR_DRC should be set to False
        assert step.config["ERROR_ON_TR_DRC"] is False

    def test_mid_iteration_break_on_drc_errors(
        self, mock_config: Config, mock_state: State
    ) -> None:
        """Test mid_iteration_break returns True on DRC errors."""
        from fabulous.fabric_generator.gds_generator.steps.tile_area_opt import (
            Checker,
        )

        mock_state.metrics["route__drc_errors"] = 5
        mock_config = mock_config.copy(IGNORE_ANTENNA_VIOLATIONS=True)

        step = TileAreaOptimisation(mock_config)
        step.config = mock_config

        result = step.mid_iteration_break(mock_state, Checker.TrDRC())

        assert result is True


class TestSupertileDieAreaGridAlignment:
    """BALANCE/LARGE die-area sizing must keep every logical division on-grid.

    A super tile is split into ``FABULOUS_TILE_LOGICAL_WIDTH`` equal physical
    divisions during IO placement; each division origin must land on the routing
    grid, so ``width / logical_width`` must be a multiple of the track pitch (and
    likewise for height). Rounding only the total dimension to the pitch leaves
    per-division boundaries off-grid for multi-column/row super tiles, producing
    the ``[DRT-0416] offgrid pin shape`` failure seen on unusually shaped tiles.
    """

    def test_pre_iteration_keeps_divisions_on_grid(
        self,
        mocker: MockerFixture,
        mock_config: Config,
        mock_state: State,
        tmp_path: Path,
    ) -> None:
        # 2-wide super tile. Chosen so the naive "round the whole width to pitch"
        # lands on 10.5 (an odd multiple of 0.5), whose half 5.25 is off-grid.
        mocker.patch(
            "fabulous.fabric_generator.gds_generator.steps.tile_area_opt.get_pitch",
            return_value=(Decimal("0.5"), Decimal("0.5")),
        )
        mocker.patch(
            "fabulous.fabric_generator.gds_generator.steps.tile_area_opt.get_routing_obstructions",
            return_value=[],
        )

        cfg = mock_config.copy(
            FABULOUS_OPT_MODE=OptMode.BALANCE,
            FABULOUS_TILE_LOGICAL_WIDTH=2,
            FABULOUS_TILE_LOGICAL_HEIGHT=1,
            FABULOUS_OPTIMISATION_WIDTH_STEP_COUNT=2,
            FABULOUS_OPTIMISATION_HEIGHT_STEP_COUNT=1,
            DIE_AREA=(Decimal(0), Decimal(0), Decimal(10), Decimal(10)),
        )
        mock_state.metrics["pdk__site_width"] = Decimal("0.1")
        mock_state.metrics["pdk__site_height"] = Decimal("0.1")
        mock_state.metrics["design__instance__area"] = 0

        step = TileAreaOptimisation(cfg)
        step.step_dir = str(tmp_path)
        step.config = cfg
        step.iter_count = 0

        step.pre_iteration_callback(mock_state)

        width = step.config["DIE_AREA"][2]
        # Per-division boundary must be a multiple of the 0.5 track pitch.
        assert (width / Decimal(2)) % Decimal("0.5") == 0

    def test_run_smart_init_keeps_divisions_on_grid(
        self, mocker: MockerFixture, mock_config: Config, mock_state: State
    ) -> None:
        # BALANCE smart-init seeds a square-cell die from the instance area.
        # instance_area 52.02 over a 2x1 super tile gives init_w = 2*sqrt(26.01)
        # = 10.2, which the naive rounding pushes to 10.5 (off-grid per division).
        mocker.patch(
            "fabulous.fabric_generator.gds_generator.steps.tile_area_opt.get_pitch",
            return_value=(Decimal("0.5"), Decimal("0.5")),
        )
        mocker.patch(
            "fabulous.fabric_generator.gds_generator.steps.tile_area_opt.WhileStep.run",
            return_value=({}, {}),
        )

        cfg = mock_config.copy(
            FABULOUS_OPT_MODE=OptMode.BALANCE,
            FABULOUS_TILE_LOGICAL_WIDTH=2,
            FABULOUS_TILE_LOGICAL_HEIGHT=1,
            FABULOUS_PIN_MIN_WIDTH=Decimal(1),
            FABULOUS_PIN_MIN_HEIGHT=Decimal(1),
            DIE_AREA=(Decimal(0), Decimal(0), Decimal(1), Decimal(1)),
        )
        mock_state.metrics["design__instance__area"] = Decimal("52.02")

        step = TileAreaOptimisation(cfg)
        step.config = cfg

        step.run(mock_state)

        width = step.config["DIE_AREA"][2]
        assert (width / Decimal(2)) % Decimal("0.5") == 0


class TestRunUserFixedSmartInit:
    """``run`` smart-init for directional modes with a user-locked axis.

    When ``FABULOUS_IGNORE_DEFAULT_DIE_AREA`` is False the user has supplied a
    DIE_AREA whose non-minimised axis must be held constant, while the minimised
    axis is seeded from the synthesised instance area so the bracket search
    starts somewhere feasible.
    """

    def _prepare(
        self,
        mocker: MockerFixture,
        config: Config,
        die_area: tuple[Decimal, Decimal, Decimal, Decimal],
    ) -> TileAreaOptimisation:
        mocker.patch(
            "fabulous.fabric_generator.gds_generator.steps.tile_area_opt.get_pitch",
            return_value=(Decimal("0.5"), Decimal("0.5")),
        )
        mocker.patch(
            "fabulous.fabric_generator.gds_generator.steps.tile_area_opt.WhileStep.run",
            return_value=({}, {}),
        )
        cfg = config.copy(FABULOUS_IGNORE_DEFAULT_DIE_AREA=False, DIE_AREA=die_area)
        step = TileAreaOptimisation(cfg)
        step.config = cfg
        return step

    def test_find_min_width_locks_height_and_seeds_width(
        self, mocker: MockerFixture, mock_config: Config, mock_state: State
    ) -> None:
        # Tiny start width, fixed height 100; instance area 5000 needs ~50 width.
        step = self._prepare(
            mocker,
            mock_config.copy(FABULOUS_OPT_MODE=OptMode.FIND_MIN_WIDTH),
            (Decimal(0), Decimal(0), Decimal(1), Decimal(100)),
        )
        mock_state.metrics["design__instance__area"] = 5000

        step.run(mock_state)

        die = step.config["DIE_AREA"]
        assert die[3] == Decimal(100)  # height locked to the user value
        assert die[2] >= Decimal(50)  # width seeded to hold the cells

    def test_find_min_height_locks_width_and_seeds_height(
        self, mocker: MockerFixture, mock_config: Config, mock_state: State
    ) -> None:
        step = self._prepare(
            mocker,
            mock_config.copy(FABULOUS_OPT_MODE=OptMode.FIND_MIN_HEIGHT),
            (Decimal(0), Decimal(0), Decimal(100), Decimal(1)),
        )
        mock_state.metrics["design__instance__area"] = 5000

        step.run(mock_state)

        die = step.config["DIE_AREA"]
        assert die[2] == Decimal(100)  # width locked to the user value
        assert die[3] >= Decimal(50)  # height seeded to hold the cells

    def test_user_fixed_height_not_grown_by_pin_floor(
        self, mocker: MockerFixture, mock_config: Config, mock_state: State
    ) -> None:
        # A larger pin floor must not override the user-locked fixed axis.
        step = self._prepare(
            mocker,
            mock_config.copy(
                FABULOUS_OPT_MODE=OptMode.FIND_MIN_WIDTH,
                FABULOUS_PIN_MIN_WIDTH=Decimal(1),
                FABULOUS_PIN_MIN_HEIGHT=Decimal(500),
            ),
            (Decimal(0), Decimal(0), Decimal(10), Decimal(100)),
        )
        mock_state.metrics["design__instance__area"] = 5000

        step.run(mock_state)

        assert step.config["DIE_AREA"][3] == Decimal(100)

    def test_zero_locked_axis_raises_clear_error(
        self, mocker: MockerFixture, mock_config: Config, mock_state: State
    ) -> None:
        # A user DIE_AREA whose locked axis is zero must raise a clear error
        # instead of a decimal.DivisionByZero from the smart-init seeding.
        step = self._prepare(
            mocker,
            mock_config.copy(FABULOUS_OPT_MODE=OptMode.FIND_MIN_WIDTH),
            (Decimal(0), Decimal(0), Decimal(10), Decimal(0)),
        )
        mock_state.metrics["design__instance__area"] = 5000

        with pytest.raises(FlowException):
            step.run(mock_state)


class TestOptModeMissing:
    """``OptMode._missing_`` is the entry point for tolerant string lookups.

    The CSV / config layer hands us strings with arbitrary case and the explicit
    sentinel ``None``; this method maps both onto canonical members.
    """

    def test_uppercase_string_matches_lowercase_member(self) -> None:
        # The enum values are lowercase but config files commonly upper-case.
        assert OptMode("BALANCE") is OptMode.BALANCE
        assert OptMode("Find_Min_Width") is OptMode.FIND_MIN_WIDTH

    def test_none_maps_to_no_opt(self) -> None:
        # A missing config key surfaces as None; treat it as "do not optimise"
        # rather than raising, so the flow can be opted out cleanly.
        assert OptMode(None) is OptMode.NO_OPT

    def test_unknown_string_raises(self) -> None:
        with pytest.raises(ValueError, match="not a valid OptMode"):
            OptMode("not_a_real_mode")


class TestDirectionalHelpers:
    """``_is_directional`` and ``_directional_target`` drive bracket-based search."""

    def test_is_directional_true_for_min_width_and_min_height(
        self, mock_config: Config
    ) -> None:
        for mode in (OptMode.FIND_MIN_WIDTH, OptMode.FIND_MIN_HEIGHT):
            cfg = mock_config.copy(FABULOUS_OPT_MODE=mode)
            step = TileAreaOptimisation(cfg)
            step.config = cfg
            assert step._is_directional() is True

    def test_is_directional_false_for_balance_and_no_opt(
        self, mock_config: Config
    ) -> None:
        for mode in (OptMode.BALANCE, OptMode.LARGE, OptMode.NO_OPT):
            cfg = mock_config.copy(FABULOUS_OPT_MODE=mode)
            step = TileAreaOptimisation(cfg)
            step.config = cfg
            assert step._is_directional() is False

    def test_directional_target_returns_w_for_find_min_width(
        self, mock_config: Config
    ) -> None:
        cfg = mock_config.copy(FABULOUS_OPT_MODE=OptMode.FIND_MIN_WIDTH)
        step = TileAreaOptimisation(cfg)
        step.config = cfg
        # die_area is (x0, y0, w, h); FIND_MIN_WIDTH targets w.
        assert step._directional_target(
            (Decimal(0), Decimal(0), Decimal("12.5"), Decimal("99.9"))
        ) == Decimal("12.5")

    def test_directional_target_returns_h_for_find_min_height(
        self, mock_config: Config
    ) -> None:
        cfg = mock_config.copy(FABULOUS_OPT_MODE=OptMode.FIND_MIN_HEIGHT)
        step = TileAreaOptimisation(cfg)
        step.config = cfg
        assert step._directional_target(
            (Decimal(0), Decimal(0), Decimal("12.5"), Decimal("99.9"))
        ) == Decimal("99.9")


class TestComputeNewDimensions:
    """``_compute_new_dimensions`` covers BALANCE / LARGE / supertile-aspect logic."""

    def test_balance_grows_smaller_axis(self, mock_config: Config) -> None:
        # BALANCE on a non-supertile (logical=1x1) grows the smaller axis only.
        cfg = mock_config.copy(FABULOUS_OPT_MODE=OptMode.BALANCE)
        cfg = cfg.copy(FABULOUS_TILE_LOGICAL_WIDTH=1, FABULOUS_TILE_LOGICAL_HEIGHT=1)
        step = TileAreaOptimisation(cfg)
        step.config = cfg

        # width (5) <= height (10) -> width grows by width_step.
        new_w, new_h = step._compute_new_dimensions(
            width=Decimal(5),
            height=Decimal(10),
            width_step=Decimal(2),
            height_step=Decimal(3),
            instance_area=Decimal(0),
            core_area=Decimal(100),
        )
        assert new_w == Decimal(7)
        assert new_h == Decimal(10)

        # When height < width, height grows.
        new_w, new_h = step._compute_new_dimensions(
            width=Decimal(20),
            height=Decimal(10),
            width_step=Decimal(2),
            height_step=Decimal(3),
            instance_area=Decimal(0),
            core_area=Decimal(100),
        )
        assert new_w == Decimal(20)
        assert new_h == Decimal(13)

    def test_large_grows_both_axes(self, mock_config: Config) -> None:
        cfg = mock_config.copy(FABULOUS_OPT_MODE=OptMode.LARGE)
        step = TileAreaOptimisation(cfg)
        step.config = cfg

        new_w, new_h = step._compute_new_dimensions(
            width=Decimal(5),
            height=Decimal(10),
            width_step=Decimal(2),
            height_step=Decimal(3),
            instance_area=Decimal(0),
            core_area=Decimal(100),
        )
        assert new_w == Decimal(7)
        assert new_h == Decimal(13)

    def test_instance_area_overflow_scales_both_axes(self, mock_config: Config) -> None:
        # When instance area > core area, both axes scale by sqrt(ratio)
        # *before* the per-axis step is applied.
        cfg = mock_config.copy(FABULOUS_OPT_MODE=OptMode.LARGE)
        step = TileAreaOptimisation(cfg)
        step.config = cfg

        # ratio = 400/100 = 4 -> scale = 2.
        new_w, new_h = step._compute_new_dimensions(
            width=Decimal(10),
            height=Decimal(10),
            width_step=Decimal(0),
            height_step=Decimal(0),
            instance_area=Decimal(400),
            core_area=Decimal(100),
        )
        # 10 * 2 + 0 = 20 on both axes.
        assert new_w == Decimal(20)
        assert new_h == Decimal(20)

    def test_supertile_balance_locks_aspect_to_logical(
        self, mock_config: Config
    ) -> None:
        # 2x1 supertile: logical aspect 2:1 must be preserved when growing.
        cfg = mock_config.copy(FABULOUS_OPT_MODE=OptMode.BALANCE)
        cfg = cfg.copy(FABULOUS_TILE_LOGICAL_WIDTH=2, FABULOUS_TILE_LOGICAL_HEIGHT=1)
        step = TileAreaOptimisation(cfg)
        step.config = cfg

        # cell_step = max(width_step/2, height_step/1) = max(2, 3) = 3
        # width  += 3 * 2 = 6 -> 16
        # height += 3 * 1 = 3 -> 13
        new_w, new_h = step._compute_new_dimensions(
            width=Decimal(10),
            height=Decimal(10),
            width_step=Decimal(4),
            height_step=Decimal(3),
            instance_area=Decimal(0),
            core_area=Decimal(100),
        )
        assert new_w == Decimal(16)
        assert new_h == Decimal(13)

    def test_unknown_mode_raises(self, mock_config: Config) -> None:
        cfg = mock_config.copy(FABULOUS_OPT_MODE=OptMode.NO_OPT)
        step = TileAreaOptimisation(cfg)
        step.config = cfg
        with pytest.raises(ValueError, match="Unknown FABULOUS_OPT_MODE"):
            step._compute_new_dimensions(
                width=Decimal(1),
                height=Decimal(1),
                width_step=Decimal(0),
                height_step=Decimal(0),
                instance_area=Decimal(0),
                core_area=Decimal(1),
            )


class TestComputeBinarySearchDimensions:
    """``_compute_binary_search_dimensions`` is the bracket-based axis search.

    Phase 1 (bracketing): no working point yet — double the target axis until
    we hit ``bracket_cap``.
    Phase 2 (bisecting): once a working point exists, bisect between the
    largest failure and the smallest success.
    """

    def _setup(
        self, mocker: MockerFixture, mock_config: Config, mode: OptMode
    ) -> TileAreaOptimisation:
        # get_pitch is read inside the helper to compute pitch on the target axis.
        mocker.patch(
            "fabulous.fabric_generator.gds_generator.steps.tile_area_opt.get_pitch",
            return_value=(Decimal("0.5"), Decimal("0.5")),
        )
        cfg = mock_config.copy(FABULOUS_OPT_MODE=mode)
        cfg = cfg.copy(FABULOUS_PIN_MIN_WIDTH=Decimal(1))
        cfg = cfg.copy(FABULOUS_PIN_MIN_HEIGHT=Decimal(1))
        step = TileAreaOptimisation(cfg)
        step.config = cfg
        return step

    def test_doubles_target_when_no_bracket_set(
        self, mocker: MockerFixture, mock_config: Config
    ) -> None:
        step = self._setup(mocker, mock_config, OptMode.FIND_MIN_WIDTH)
        # No bracket_high yet -> target axis (width) doubles.
        new_w, new_h = step._compute_binary_search_dimensions(
            width=Decimal(10), height=Decimal(50)
        )
        assert new_w == Decimal(20)
        # Non-target axis is preserved.
        assert new_h == Decimal(50)

    def test_caps_target_at_bracket_cap(
        self, mocker: MockerFixture, mock_config: Config
    ) -> None:
        step = self._setup(mocker, mock_config, OptMode.FIND_MIN_HEIGHT)
        step.bracket_cap = Decimal(15)
        # Doubling 10 -> 20 would exceed cap=15, so clamp to 15. Width preserved.
        new_w, new_h = step._compute_binary_search_dimensions(
            width=Decimal(7), height=Decimal(10)
        )
        assert new_w == Decimal(7)
        assert new_h == Decimal(15)

    def test_marks_exhausted_when_at_cap(
        self, mocker: MockerFixture, mock_config: Config
    ) -> None:
        step = self._setup(mocker, mock_config, OptMode.FIND_MIN_WIDTH)
        step.bracket_cap = Decimal(10)
        # Already at cap -> doubling would exceed AND current >= cap, so
        # mark exhausted and keep current.
        new_w, new_h = step._compute_binary_search_dimensions(
            width=Decimal(10), height=Decimal(20)
        )
        assert step.bracket_exhausted is True
        assert new_w == Decimal(10)
        assert new_h == Decimal(20)

    def test_bisects_between_low_and_high(
        self, mocker: MockerFixture, mock_config: Config
    ) -> None:
        step = self._setup(mocker, mock_config, OptMode.FIND_MIN_WIDTH)
        step.bracket_low = Decimal(10)
        step.bracket_high = Decimal(20)
        # Bisecting between low=10 and high=20 should land on the midpoint 15.
        new_w, new_h = step._compute_binary_search_dimensions(
            width=Decimal(99), height=Decimal(7)
        )
        assert new_w == Decimal(15)
        assert new_h == Decimal(7)

    def test_bisects_between_pin_floor_and_high(
        self, mocker: MockerFixture, mock_config: Config
    ) -> None:
        # Only bracket_high is set (first iter worked) -> bisect between pin
        # floor and bracket_high.
        step = self._setup(mocker, mock_config, OptMode.FIND_MIN_WIDTH)
        step.config = step.config.copy(FABULOUS_PIN_MIN_WIDTH=Decimal(2))
        step.bracket_high = Decimal(10)
        step.bracket_low = None
        new_w, _ = step._compute_binary_search_dimensions(
            width=Decimal(50), height=Decimal(50)
        )
        # (2 + 10) / 2 = 6.
        assert new_w == Decimal(6)

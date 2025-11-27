"""Tests for TileOptimisation step."""

from decimal import Decimal
from pathlib import Path

import pytest
from librelane.config.config import Config
from librelane.state.state import State
from pytest_mock import MockerFixture, MockFixture

from fabulous.fabric_generator.gds_generator.steps.tile_optimisation import (
    OptMode,
    TileOptimisation,
)


class TestTileOptimisation:
    """Test suite for TileOptimisation step."""

    def test_condition_returns_true_on_drc_errors(
        self, mock_config: Config, mock_state: State
    ):
        """Test condition returns True when DRC errors exist."""
        mock_state.metrics["route__drc_errors"] = 5

        step = TileOptimisation(mock_config)
        step.config = mock_config
        assert step.condition(mock_state) is True

    def test_condition_returns_true_on_antenna_violations(
        self, mock_config: Config, mock_state: State
    ):
        """Test condition returns True when antenna violations exist."""
        mock_state.metrics["route__drc_errors"] = 0
        mock_state.metrics["antenna__violating__nets"] = 2

        step = TileOptimisation(mock_config)
        step.config = mock_config
        assert step.condition(mock_state) is True

    def test_condition_returns_false_when_no_errors(
        self, mock_config: Config, mock_state: State
    ) -> None:
        """Test condition returns False when no errors exist."""
        mock_state.metrics["route__drc_errors"] = 0
        mock_state.metrics["antenna__violating__nets"] = 0
        mock_state.metrics["antenna__violating__pins"] = 0

        step = TileOptimisation(mock_config)
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
            "fabulous.fabric_generator.gds_generator.steps.tile_optimisation.get_pitch",
            return_value=(Decimal("0.46"), Decimal("2.72")),
        )
        # Mock get_routing_obstructions to avoid config key errors
        mocker.patch(
            "fabulous.fabric_generator.gds_generator.steps.tile_optimisation.get_routing_obstructions",
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

        step = TileOptimisation(mock_config)
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
        """Test post_loop_callback returns the last working state."""
        step = TileOptimisation(mock_config)
        step.last_working_state = mock_state

        result = step.post_loop_callback(mock_state)

        assert result == mock_state

    def test_post_loop_callback_raises_error_without_working_state(
        self, mock_config: Config, mock_state: State
    ) -> None:
        """Test post_loop_callback raises error if no working state found."""
        step = TileOptimisation(mock_config)
        step.config = mock_config
        step.last_working_state = None

        with pytest.raises(RuntimeError, match="No working state found"):
            step.post_loop_callback(mock_state)

    def test_run_ignores_antenna_violations_when_configured(
        self, mocker: MockerFixture, mock_config: Config, mock_state: State
    ) -> None:
        """Test run method with IGNORE_ANTENNA_VIOLATIONS enabled."""
        mock_config = mock_config.copy(IGNORE_ANTENNA_VIOLATIONS=True)

        step = TileOptimisation(mock_config)
        step.config = mock_config
        mock_run = mocker.patch(
            "fabulous.fabric_generator.gds_generator.steps.tile_optimisation.WhileStep.run",
            return_value=({}, {}),
        )

        step.run(mock_state)

        # ERROR_ON_TR_DRC should be set to False
        assert step.config["ERROR_ON_TR_DRC"] is False

    def test_mid_iteration_break_on_drc_errors(
        self, mock_config: Config, mock_state: State, mocker: MockFixture
    ) -> None:
        """Test mid_iteration_break returns True on DRC errors."""
        from fabulous.fabric_generator.gds_generator.steps.tile_optimisation import (
            Checker,
        )

        mock_state.metrics["route__drc_errors"] = 5
        mock_config = mock_config.copy(IGNORE_ANTENNA_VIOLATIONS=True)

        step = TileOptimisation(mock_config)
        step.config = mock_config

        result = step.mid_iteration_break(mock_state, Checker.TrDRC())

        assert result is True

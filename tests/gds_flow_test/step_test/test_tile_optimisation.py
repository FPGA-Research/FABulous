"""Tests for TileOptimisation step."""

from decimal import Decimal

from pathlib import Path
import pytest
from pytest_mock import MockFixture, MockerFixture

from FABulous.fabric_generator.gds_generator.steps.tile_optimisation import (
    OptMode,
    TileOptimisation,
)
from librelane.config.config import Config
from librelane.state.state import State


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

    def test_post_iteration_callback_handles_insufficient_core(
        self, mock_config: Config, mock_state: State
    ) -> None:
        """Test that insufficient core area updates die area."""
        mock_state.metrics["design__core__area"] = 500
        mock_state.metrics["design__instance__area__stdcell"] = 1000
        mock_state.metrics["design__die__bbox"] = "0 0 100 100"
        mock_state.metrics["design__core__bbox"] = "10 10 90 90"

        step = TileOptimisation(mock_config)
        step.config = mock_config
        step.post_iteration_callback(mock_state, full_iter_completed=False)

        # DIE_AREA should be updated
        assert step.config["DIE_AREA"] is not None

    def test_pre_iteration_callback_find_min_width_mode(
        self, mock_config: Config, mock_state: State, tmp_path: Path
    ) -> None:
        """Test pre_iteration_callback in find_min_width mode."""
        mock_config = mock_config.copy(FABULOUS_OPT_MODE=OptMode.FIND_MIN_WIDTH)
        mock_config = mock_config.copy(
            DIE_AREA=(Decimal(0), Decimal(0), Decimal(100), Decimal(100))
        )

        step = TileOptimisation(mock_config)
        step.step_dir = str(tmp_path)
        step.config = mock_config
        step.pre_iteration_callback(mock_state)

        # DIE_AREA should be updated
        new_die_area = step.config["DIE_AREA"]
        assert new_die_area is not None
        assert new_die_area[2] >= Decimal(100)

    def test_pre_iteration_callback_respects_min_constraints(
        self, mock_config: Config, mock_state: State, tmp_path: Path
    ) -> None:
        """Test that pre_iteration_callback respects minimum width/height."""
        mock_config = mock_config.copy(FABULOUS_IO_MIN_WIDTH=Decimal(200))
        mock_config = mock_config.copy(FABULOUS_IO_MIN_HEIGHT=Decimal(150))
        mock_config = mock_config.copy(
            DIE_AREA=(Decimal(0), Decimal(0), Decimal(100), Decimal(100))
        )

        step = TileOptimisation(mock_config)
        step.step_dir = str(tmp_path)
        step.config = mock_config

        step.pre_iteration_callback(mock_state)

        new_die_area = step.config["DIE_AREA"]
        assert new_die_area[2] >= Decimal(200)
        assert new_die_area[3] >= Decimal(150)

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
            "FABulous.fabric_generator.gds_generator.steps.tile_optimisation.WhileStep.run",
            return_value=({}, {}),
        )

        step.run(mock_state)

        # ERROR_ON_TR_DRC should be set to False
        assert step.config["ERROR_ON_TR_DRC"] is False

    def test_run_validates_min_dimensions_when_ignoring_default_area(
        self, mock_config: Config, mock_state: State
    ) -> None:
        """Test run validates dimensions when IGNORE_DEFAULT_DIE_AREA is True."""
        mock_config = mock_config.copy(IGNORE_DEFAULT_DIE_AREA=True)
        mock_config = mock_config.copy(FABULOUS_IO_MIN_WIDTH=Decimal(0))

        step = TileOptimisation(mock_config)
        step.config = mock_config

        with pytest.raises(ValueError, match="FABULOUS_IO_MIN_WIDTH"):
            step.run(mock_state)

    def test_mid_iteration_break_on_drc_errors(
        self, mock_config: Config, mock_state: State, mocker: MockFixture
    ) -> None:
        """Test mid_iteration_break returns True on DRC errors."""
        from FABulous.fabric_generator.gds_generator.steps.tile_optimisation import (
            Checker,
        )

        mock_state.metrics["route__drc_errors"] = 5
        mock_config = mock_config.copy(IGNORE_ANTENNA_VIOLATIONS=True)

        step = TileOptimisation(mock_config)
        step.config = mock_config

        result = step.mid_iteration_break(mock_state, Checker.TrDRC())

        assert result is True

    def test_has_correct_steps_sequence(self) -> None:
        """Test that TileOptimisation includes expected step sequence."""
        from FABulous.fabric_generator.gds_generator.steps.add_buffer import (
            AddBuffers,
        )
        from FABulous.fabric_generator.gds_generator.steps.custom_pdn import (
            CustomGeneratePDN,
        )
        from FABulous.fabric_generator.gds_generator.steps.tile_IO_placement import (
            FABulousTileIOPlacement,
        )

        # Check some key steps are in the sequence
        assert AddBuffers in TileOptimisation.Steps
        assert CustomGeneratePDN in TileOptimisation.Steps
        assert FABulousTileIOPlacement in TileOptimisation.Steps

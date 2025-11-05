"""Tests for TileOptimisation step."""

from decimal import Decimal

import pytest

from FABulous.fabric_generator.gds_generator.steps.tile_optimisation import (
    OptMode,
    TileOptimisation,
)


class TestTileOptimisation:
    """Test suite for TileOptimisation step."""

    def test_step_registration(self):
        """Test that TileOptimisation is properly registered."""
        assert TileOptimisation.id == "FABulous.TileOptimisation"
        assert TileOptimisation.name == "Tile Optimisation"

    def test_config_vars_defined(self):
        """Test that config variables are properly defined."""
        config_var_names = [var.name for var in TileOptimisation.config_vars]
        assert "FABULOUS_OPTIMISATION_WIDTH_STEP_COUNT" in config_var_names
        assert "FABULOUS_OPTIMISATION_HEIGHT_STEP_COUNT" in config_var_names
        assert "FABULOUS_OPT_MODE" in config_var_names
        assert "FABULOUS_OPT_RELAX" in config_var_names
        assert "IGNORE_ANTENNA_VIOLATIONS" in config_var_names
        assert "IGNORE_DEFAULT_DIE_AREA" in config_var_names
        assert "FABULOUS_IO_MIN_WIDTH" in config_var_names
        assert "FABULOUS_IO_MIN_HEIGHT" in config_var_names

    def test_opt_mode_enum_values(self):
        """Test OptMode enum has correct values."""
        assert OptMode.FIND_MIN_WIDTH == "find_min_width"
        assert OptMode.FIND_MIN_HEIGHT == "find_min_height"
        assert OptMode.BALANCE == "balance"
        assert OptMode.LARGE == "large"

    def test_condition_returns_true_on_drc_errors(self, mock_config, mock_state):
        """Test condition returns True when DRC errors exist."""
        mock_state.metrics["route__drc_errors"] = 5

        step = TileOptimisation(mock_config)
        assert step.condition(mock_state) is True

    def test_condition_returns_true_on_antenna_violations(
        self, mock_config, mock_state
    ):
        """Test condition returns True when antenna violations exist."""
        mock_config["IGNORE_ANTENNA_VIOLATIONS"] = False
        mock_state.metrics["route__drc_errors"] = 0
        mock_state.metrics["antenna__violating__nets"] = 2

        step = TileOptimisation(mock_config)
        assert step.condition(mock_state) is True

    def test_condition_returns_false_when_no_errors(self, mock_config, mock_state):
        """Test condition returns False when no errors exist."""
        mock_state.metrics["route__drc_errors"] = 0
        mock_state.metrics["antenna__violating__nets"] = 0
        mock_state.metrics["antenna__violating__pins"] = 0

        step = TileOptimisation(mock_config)
        assert step.condition(mock_state) is False

    def test_post_iteration_callback_saves_working_state(self, mock_config, mock_state):
        """Test that successful iteration saves state."""
        step = TileOptimisation(mock_config)

        result = step.post_iteration_callback(mock_state, full_iter_completed=True)

        assert step.last_working_state == mock_state
        assert result == mock_state

    def test_post_iteration_callback_handles_insufficient_core(
        self, mock_config, mock_state
    ):
        """Test that insufficient core area updates die area."""
        mock_state.metrics["design__core__area"] = 500
        mock_state.metrics["design__instance__area__stdcell"] = 1000
        mock_state.metrics["design__die__bbox"] = "0 0 100 100"
        mock_state.metrics["design__core__bbox"] = "10 10 90 90"

        step = TileOptimisation(mock_config)
        step.post_iteration_callback(mock_state, full_iter_completed=False)

        # DIE_AREA should be updated
        assert step.config["DIE_AREA"] is not None

    def test_pre_iteration_callback_find_min_width_mode(
        self, mock_config, mock_state, tmp_path
    ):
        """Test pre_iteration_callback in find_min_width mode."""
        mock_config["FABULOUS_OPT_MODE"] = OptMode.FIND_MIN_WIDTH
        mock_config["DIE_AREA"] = (Decimal(0), Decimal(0), Decimal(100), Decimal(100))

        step = TileOptimisation(mock_config)
        step.step_dir = str(tmp_path)

        step.pre_iteration_callback(mock_state)

        # DIE_AREA should be updated
        new_die_area = step.config["DIE_AREA"]
        assert new_die_area is not None
        assert new_die_area[2] >= Decimal(100)

    def test_pre_iteration_callback_respects_min_constraints(
        self, mock_config, mock_state, tmp_path
    ):
        """Test that pre_iteration_callback respects minimum width/height."""
        mock_config["FABULOUS_IO_MIN_WIDTH"] = Decimal(200)
        mock_config["FABULOUS_IO_MIN_HEIGHT"] = Decimal(150)
        mock_config["DIE_AREA"] = (Decimal(0), Decimal(0), Decimal(100), Decimal(100))

        step = TileOptimisation(mock_config)
        step.step_dir = str(tmp_path)

        step.pre_iteration_callback(mock_state)

        new_die_area = step.config["DIE_AREA"]
        assert new_die_area[2] >= Decimal(200)
        assert new_die_area[3] >= Decimal(150)

    def test_post_loop_callback_returns_working_state(self, mock_config, mock_state):
        """Test post_loop_callback returns the last working state."""
        step = TileOptimisation(mock_config)
        step.last_working_state = mock_state

        result = step.post_loop_callback(mock_state)

        assert result == mock_state

    def test_post_loop_callback_raises_error_without_working_state(
        self, mock_config, mock_state
    ):
        """Test post_loop_callback raises error if no working state found."""
        step = TileOptimisation(mock_config)
        step.last_working_state = None

        with pytest.raises(RuntimeError, match="No working state found"):
            step.post_loop_callback(mock_state)

    def test_run_ignores_antenna_violations_when_configured(
        self, mocker, mock_config, mock_state
    ):
        """Test run method with IGNORE_ANTENNA_VIOLATIONS enabled."""
        mock_config["IGNORE_ANTENNA_VIOLATIONS"] = True

        step = TileOptimisation(mock_config)

        mock_run = mocker.patch(
            "FABulous.fabric_generator.gds_generator.steps.tile_optimisation.WhileStep.run",
            return_value=({}, {}),
        )

        step.run(mock_state)

        # ERROR_ON_TR_DRC should be set to False
        assert step.config["ERROR_ON_TR_DRC"] is False

    def test_run_validates_min_dimensions_when_ignoring_default_area(
        self, mock_config, mock_state
    ):
        """Test run validates dimensions when IGNORE_DEFAULT_DIE_AREA is True."""
        mock_config["IGNORE_DEFAULT_DIE_AREA"] = True
        mock_config["FABULOUS_IO_MIN_WIDTH"] = Decimal(0)

        step = TileOptimisation(mock_config)

        with pytest.raises(ValueError, match="FABULOUS_IO_MIN_WIDTH"):
            step.run(mock_state)

    def test_mid_iteration_break_on_drc_errors(self, mock_config, mock_state, mocker):
        """Test mid_iteration_break returns True on DRC errors."""
        from FABulous.fabric_generator.gds_generator.steps.tile_optimisation import (
            Checker,
        )

        mock_state.metrics["route__drc_errors"] = 5
        mock_config["IGNORE_ANTENNA_VIOLATIONS"] = True

        step = TileOptimisation(mock_config)

        # Create a mock step class
        mock_step_class = mocker.MagicMock()
        mock_step_class.__bases__ = (Checker.TrDRC,)

        result = step.mid_iteration_break(mock_state, Checker.TrDRC)

        assert result is True

    def test_has_correct_steps_sequence(self):
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

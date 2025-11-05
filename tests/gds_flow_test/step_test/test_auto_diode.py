"""Tests for AutoEcoDiodeInsertion step."""

import pytest

from FABulous.fabric_generator.gds_generator.steps.auto_diode import (
    AutoEcoDiodeInsertion,
)


class TestAutoEcoDiodeInsertion:
    """Test suite for AutoEcoDiodeInsertion step."""

    def test_step_registration(self):
        """Test that AutoEcoDiodeInsertion is properly registered."""
        assert AutoEcoDiodeInsertion.id == "FABulous.AutoDiode"
        assert AutoEcoDiodeInsertion.name == "FABulous Auto Diode Insertion"

    def test_config_vars_defined(self):
        """Test that config variables are properly defined."""
        config_var_names = [var.name for var in AutoEcoDiodeInsertion.config_vars]
        assert "AUTO_ECO_DIODE_INSERT_MODE" in config_var_names

    def test_config_var_default(self):
        """Test config variable default value."""
        var_defaults = {
            var.name: var.default for var in AutoEcoDiodeInsertion.config_vars
        }
        assert var_defaults["AUTO_ECO_DIODE_INSERT_MODE"] == "all"

    def test_parse_diodes_all_mode(self, mock_config, mock_antenna_report):
        """Test parsing diodes in 'all' mode."""
        mock_config["AUTO_ECO_DIODE_INSERT_MODE"] = "all"
        step = AutoEcoDiodeInsertion(mock_config)
        step.step_dir = "/tmp/test"

        diodes = step.parse_diodes(mock_antenna_report)

        assert len(diodes) == 3
        assert all(hasattr(d, "target") for d in diodes)

    def test_parse_diodes_ratio_mode(self, mock_config, mock_antenna_report):
        """Test parsing diodes in 'ratio' mode."""
        mock_config["AUTO_ECO_DIODE_INSERT_MODE"] = "ratio"
        step = AutoEcoDiodeInsertion(mock_config)
        step.step_dir = "/tmp/test"

        diodes = step.parse_diodes(mock_antenna_report)

        # Only pins with partial > required should be included
        assert len(diodes) == 2  # net1 and net2 have partial > required

    def test_parse_diodes_empty_report(self, mock_config):
        """Test parsing empty antenna report."""
        mock_config["AUTO_ECO_DIODE_INSERT_MODE"] = "all"
        step = AutoEcoDiodeInsertion(mock_config)
        step.step_dir = "/tmp/test"

        empty_report = """╔═══════════════════╗
║  Antenna Report   ║
╠═══════════════════╣
╚═══════════════════╝
Summary: 0 violations found
"""
        diodes = step.parse_diodes(empty_report)
        assert len(diodes) == 0

    def test_condition_done_enough(self, mock_config, mock_state):
        """Test condition returns False when done_enough is True."""
        step = AutoEcoDiodeInsertion(mock_config)
        step.done_enough = True

        assert not step.condition(mock_state)

    def test_condition_not_done(self, mock_config, mock_state):
        """Test condition returns True when not done."""
        step = AutoEcoDiodeInsertion(mock_config)
        step.done_enough = False

        assert step.condition(mock_state)

    def test_pre_iteration_callback_first_iteration(
        self, mocker, mock_config, mock_state, tmp_path, mock_antenna_report
    ):
        """Test pre_iteration_callback on first iteration."""
        step = AutoEcoDiodeInsertion(mock_config)
        step.current_iteration = 0
        step.step_dir = str(tmp_path)

        # Create pre-check directory and report
        pre_check_dir = tmp_path / "pre-check" / "reports"
        pre_check_dir.mkdir(parents=True)
        (pre_check_dir / "antenna_summary.rpt").write_text(mock_antenna_report)

        # Mock CheckAntennas
        mock_instance = mocker.MagicMock()
        mock_check_antennas = mocker.patch(
            "FABulous.fabric_generator.gds_generator.steps.auto_diode.OpenROAD.CheckAntennas",
            return_value=mock_instance,
        )

        new_state = step.pre_iteration_callback(mock_state)

        assert step.config["INSERT_ECO_DIODES"] is not None

    def test_post_iteration_callback_success(self, mock_config, mock_state):
        """Test post_iteration_callback on successful iteration."""
        step = AutoEcoDiodeInsertion(mock_config)
        step.current_iteration = 0
        step.previous_state = mock_state

        new_state = step.post_iteration_callback(mock_state, full_iteration=True)

        assert step.current_iteration == 1
        assert step.previous_state == mock_state
        assert new_state == mock_state

    def test_post_iteration_callback_failure(self, mock_config, mock_state):
        """Test post_iteration_callback raises error on failure."""
        step = AutoEcoDiodeInsertion(mock_config)

        with pytest.raises(RuntimeError, match="Fail to insert ECO diodes"):
            step.post_iteration_callback(mock_state, full_iteration=False)

    def test_post_loop_callback_with_violations_all_mode(self, mock_config, mock_state):
        """Test post_loop_callback raises error when violations remain in 'all' mode."""
        mock_config["AUTO_ECO_DIODE_INSERT_MODE"] = "all"
        mock_state.metrics["antenna__violating__nets"] = 2
        mock_state.metrics["antenna__violating__pins"] = 3

        step = AutoEcoDiodeInsertion(mock_config)

        with pytest.raises(RuntimeError, match="Antenna violations remain"):
            step.post_loop_callback(mock_state)

    def test_post_loop_callback_no_violations(self, mock_config, mock_state):
        """Test post_loop_callback succeeds when no violations remain."""
        mock_config["AUTO_ECO_DIODE_INSERT_MODE"] = "all"
        mock_state.metrics["antenna__violating__nets"] = 0
        mock_state.metrics["antenna__violating__pins"] = 0

        step = AutoEcoDiodeInsertion(mock_config)

        result = step.post_loop_callback(mock_state)
        assert result == mock_state

    def test_run_skip_when_mode_none(self, mocker, mock_config, mock_state):
        """Test run skips processing when mode is 'none'."""
        mock_config["AUTO_ECO_DIODE_INSERT_MODE"] = "none"

        mock_run = mocker.patch(
            "FABulous.fabric_generator.gds_generator.steps.auto_diode.WhileStep.run"
        )

        step = AutoEcoDiodeInsertion(mock_config)
        views_update, metrics_update = step.run(mock_state)

        assert views_update == {}
        assert metrics_update == {}
        mock_run.assert_not_called()

    def test_run_processes_when_mode_not_none(self, mocker, mock_config, mock_state):
        """Test run processes when mode is not 'none'."""
        mock_config["AUTO_ECO_DIODE_INSERT_MODE"] = "all"

        mock_run = mocker.patch(
            "FABulous.fabric_generator.gds_generator.steps.auto_diode.WhileStep.run",
            return_value=({}, {}),
        )

        step = AutoEcoDiodeInsertion(mock_config)
        step.previous_state = mock_state
        views_update, metrics_update = step.run(mock_state)

        mock_run.assert_called_once()
        assert step.previous_state == mock_state

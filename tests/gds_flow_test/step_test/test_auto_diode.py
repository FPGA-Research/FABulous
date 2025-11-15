"""Tests for AutoEcoDiodeInsertion step."""

import pytest
from librelane.config.config import Config
from librelane.state.state import State
from pytest_mock import MockFixture
from pathlib import Path

from pytest_mock.plugin import MockerFixture

from FABulous.fabric_generator.gds_generator.steps.auto_diode import (
    AutoEcoDiodeInsertion,
)


class TestAutoEcoDiodeInsertion:
    """Test suite for AutoEcoDiodeInsertion step."""

    def test_parse_diodes(
        self, mock_config: Config, mock_state: State, mock_antenna_report: str
    ) -> None:
        """Test parsing diodes in 'all' mode."""
        step = AutoEcoDiodeInsertion(mock_config, mock_state)
        step.step_dir = "/tmp/test"
        step.config = mock_config
        diodes = step.parse_diodes(mock_antenna_report)

        assert len(diodes) == 20
        assert all(hasattr(d, "target") for d in diodes)

    def test_parse_diodes_empty_report(
        self, mock_config: Config, mock_state: State
    ) -> None:
        """Test parsing empty antenna report."""
        step = AutoEcoDiodeInsertion(mock_config, mock_state)
        step.step_dir = "/tmp/test"

        empty_report = """"""
        diodes = step.parse_diodes(empty_report)
        assert len(diodes) == 0

    def test_condition_done_enough(
        self, mock_config: Config, mock_state: State
    ) -> None:
        """Test condition returns False when done_enough is True."""
        step = AutoEcoDiodeInsertion(mock_config, mock_state)
        step.done_enough = True

        assert not step.condition(mock_state)

    def test_condition_not_done(self, mock_config: Config, mock_state: State) -> None:
        """Test condition returns True when not done."""
        step = AutoEcoDiodeInsertion(mock_config, mock_state)
        step.done_enough = False

        assert step.condition(mock_state)

    def test_pre_iteration_callback_first_iteration(
        self,
        mocker: MockFixture,
        mock_config: Config,
        mock_state: State,
        tmp_path: Path,
        mock_antenna_report: str,
    ) -> None:
        """Test pre_iteration_callback on first iteration."""
        step = AutoEcoDiodeInsertion(mock_config, mock_state)
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
        step.config = mock_config
        step.previous_state = mock_state
        new_state = step.pre_iteration_callback(mock_state)

        assert step.config["INSERT_ECO_DIODES"] != []

    def test_post_iteration_callback_success(
        self, mock_config: Config, mock_state: State
    ) -> None:
        """Test post_iteration_callback on successful iteration."""
        step = AutoEcoDiodeInsertion(mock_config, mock_state)
        step.current_iteration = 0
        step.previous_state = mock_state

        new_state = step.post_iteration_callback(mock_state, full_iteration=True)

        assert step.current_iteration == 1
        assert step.previous_state == mock_state
        assert new_state == mock_state

    def test_post_iteration_callback_failure(
        self, mock_config: Config, mock_state: State
    ):
        """Test post_iteration_callback raises error on failure."""
        step = AutoEcoDiodeInsertion(mock_config, mock_state)

        with pytest.raises(RuntimeError, match="Fail to insert ECO diodes"):
            step.post_iteration_callback(mock_state, full_iteration=False)

    def test_post_loop_callback_with_violations_all_mode(
        self, mocker: MockerFixture, mock_config: Config, mock_state: State
    ) -> None:
        """Test post_loop_callback raises error when violations remain in 'all' mode."""
        mock_config = mock_config.copy(AUTO_ECO_DIODE_INSERT_MODE="all")
        mock_state.metrics["antenna__violating__nets"] = 2
        mock_state.metrics["antenna__violating__pins"] = 3

        step = AutoEcoDiodeInsertion(mock_config, mock_state)
        step.config = mock_config
        with pytest.raises(RuntimeError, match="Antenna violations remain"):
            step.post_loop_callback(mock_state)

    def test_post_loop_callback_no_violations(
        self, mocker: MockerFixture, mock_config: Config, mock_state: State
    ) -> None:
        """Test post_loop_callback succeeds when no violations remain."""
        mock_config = mock_config.copy(AUTO_ECO_DIODE_INSERT_MODE="all")
        mock_state.metrics["antenna__violating__nets"] = 0
        mock_state.metrics["antenna__violating__pins"] = 0

        step = AutoEcoDiodeInsertion(mock_config, mock_state)
        step.config = mock_config
        result = step.post_loop_callback(mock_state)
        assert result == mock_state

    def test_run_skip_when_mode_none(
        self, mocker: MockFixture, mock_config: Config, mock_state: State
    ) -> None:
        """Test run skips processing when mode is 'none'."""
        mock_config = mock_config.copy(AUTO_ECO_DIODE_INSERT_MODE="none")

        mock_run = mocker.patch(
            "FABulous.fabric_generator.gds_generator.steps.while_step.WhileStep.run",
            return_value=({}, {}),
        )

        step = AutoEcoDiodeInsertion(mock_config, mock_state)
        step.config = mock_config
        views_update, metrics_update = step.run(mock_state)

        assert views_update == {}
        assert metrics_update == {}
        mock_run.assert_not_called()

    def test_run_processes_when_mode_not_none(
        self, mocker: MockFixture, mock_config: Config, mock_state: State
    ) -> None:
        """Test run processes when mode is not 'none'."""
        mock_config = mock_config.copy(AUTO_ECO_DIODE_INSERT_MODE="all")

        mock_run = mocker.patch(
            "FABulous.fabric_generator.gds_generator.steps.auto_diode.WhileStep.run",
            return_value=({}, {}),
        )

        step = AutoEcoDiodeInsertion(mock_config, mock_state)
        step.config = mock_config
        step.previous_state = mock_state
        views_update, metrics_update = step.run(mock_state)

        mock_run.assert_called_once()
        assert step.previous_state == mock_state

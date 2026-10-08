"""Tests for AutoEcoDiodeInsertion step."""

from pathlib import Path

import pytest
from librelane.config.config import Config
from librelane.state.state import State
from pytest_mock import MockerFixture

from fabulous.fabric_generator.gds_generator.steps.auto_diode import (
    AutoEcoDiodeInsertion,
)

# Sink pins of `mock_antenna_report` whose partial antenna ratio exceeds the
# required one; the remaining rows are below their limit.
OVER_LIMIT_PINS = {
    "_3249_/A",
    "_3194_/A",
    "_1193_/A",
    "_1525_/A2",
    "_1896_/A1",
    "_3223_/A",
    "_3246_/A",
    "_3248_/A",
    "_3254_/A",
    "_1180_/A",
    "_1322_/A0",
    "_1525_/A0",
    "_3171_/A",
    "_3238_/A",
    "_3201_/A",
    "_3191_/A",
    "_3252_/A",
    "_3251_/A",
    "_3247_/A",
    "_3245_/A",
}
UNDER_LIMIT_PINS = {"_1216_/A1", "_1271_/A0", "_1333_/A2", "_1455_/A0", "_3154_/A"}


class TestAutoEcoDiodeInsertion:
    """Test suite for AutoEcoDiodeInsertion step."""

    @pytest.mark.parametrize(
        ("mode", "expected_targets"),
        [
            pytest.param("ratio", OVER_LIMIT_PINS, id="ratio"),
            pytest.param("all", OVER_LIMIT_PINS | UNDER_LIMIT_PINS, id="all"),
        ],
    )
    def test_parse_diodes(
        self,
        mock_config: Config,
        mock_state: State,
        mock_antenna_report: str,
        mode: str,
        expected_targets: set[str],
    ) -> None:
        """`ratio` targets only over-limit sinks; `all` targets every reported sink."""
        step = AutoEcoDiodeInsertion(mock_config, mock_state)
        step.config = mock_config.copy(AUTO_ECO_DIODE_INSERT_MODE=mode)

        diodes = step.parse_diodes(mock_antenna_report)

        assert len(diodes) == len(expected_targets)
        assert {d.target for d in diodes} == expected_targets

    def test_parse_diodes_empty_report(
        self, mock_config: Config, mock_state: State
    ) -> None:
        """Test parsing empty antenna report."""
        step = AutoEcoDiodeInsertion(mock_config, mock_state)
        step.step_dir = "/tmp/test"

        empty_report = """"""
        diodes = step.parse_diodes(empty_report)
        assert len(diodes) == 0

    @pytest.mark.parametrize(
        ("done_enough", "keep_looping"),
        [
            pytest.param(False, True, id="inserting"),
            pytest.param(True, False, id="done"),
        ],
    )
    def test_condition_follows_done_enough(
        self,
        mock_config: Config,
        mock_state: State,
        done_enough: bool,
        keep_looping: bool,
    ) -> None:
        """The loop runs until `done_enough`; remaining violations do not matter."""
        mock_state.metrics["antenna__violating__nets"] = 100
        mock_state.metrics["antenna__violating__pins"] = 100
        step = AutoEcoDiodeInsertion(mock_config, mock_state)
        step.done_enough = done_enough

        assert step.condition(mock_state) is keep_looping

    def test_pre_iteration_callback_first_iteration(
        self,
        mocker: MockerFixture,
        mock_config: Config,
        mock_state: State,
        tmp_path: Path,
        mock_antenna_report: str,
    ) -> None:
        """Iteration 0 runs its own antenna check and queues a diode per violation."""
        step = AutoEcoDiodeInsertion(mock_config, mock_state)
        step.current_iteration = 0
        step.step_dir = str(tmp_path)
        step.config = mock_config
        step.previous_state = mocker.MagicMock()

        pre_check_dir = tmp_path / "pre-check" / "reports"
        pre_check_dir.mkdir(parents=True)
        (pre_check_dir / "antenna_summary.rpt").write_text(mock_antenna_report)
        check_antennas = mocker.patch(
            "fabulous.fabric_generator.gds_generator.steps.auto_diode.OpenROAD.CheckAntennas"
        )

        new_state = step.pre_iteration_callback(mock_state)

        check_antennas.assert_called_once_with(mock_config, mock_state)
        check_antennas.return_value.start.assert_called_once_with(
            step_dir=str(tmp_path / "pre-check")
        )
        assert {d.target for d in step.config["INSERT_ECO_DIODES"]} == OVER_LIMIT_PINS
        assert step.done_enough is False
        assert new_state is step.previous_state

    def test_pre_iteration_callback_later_iteration_with_clean_report(
        self,
        mocker: MockerFixture,
        mock_config: Config,
        mock_state: State,
        tmp_path: Path,
    ) -> None:
        """A later iteration reads the previous check; an empty report ends the loop."""
        step = AutoEcoDiodeInsertion(mock_config, mock_state)
        step.current_iteration = 2
        step.step_dir = str(tmp_path)
        step.config = mock_config
        step.previous_state = mocker.MagicMock()

        report_dir = tmp_path / "iter_1" / "1-openroad-checkantennas" / "reports"
        report_dir.mkdir(parents=True)
        (report_dir / "antenna_summary.rpt").write_text("")
        check_antennas = mocker.patch(
            "fabulous.fabric_generator.gds_generator.steps.auto_diode.OpenROAD.CheckAntennas"
        )

        new_state = step.pre_iteration_callback(mock_state)

        check_antennas.assert_not_called()
        assert step.config["INSERT_ECO_DIODES"] == []
        assert step.done_enough is True
        assert new_state is step.previous_state

    def test_post_iteration_callback_success(
        self, mocker: MockerFixture, mock_config: Config, mock_state: State
    ) -> None:
        """A full iteration records its state, advances and counts its diodes."""
        step = AutoEcoDiodeInsertion(mock_config, mock_state)
        step.current_iteration = 0
        step.previous_state = mock_state
        step.config = mock_config.copy(INSERT_ECO_DIODES=[1, 2, 3])
        post_state = mocker.MagicMock()

        new_state = step.post_iteration_callback(post_state, full_iteration=True)

        assert step.current_iteration == 1
        assert step.previous_state is post_state
        assert new_state is post_state
        assert step.total_diodes_inserted == 3

    def test_post_iteration_callback_failure(
        self, mock_config: Config, mock_state: State
    ) -> None:
        """Test post_iteration_callback raises error on failure."""
        step = AutoEcoDiodeInsertion(mock_config, mock_state)

        with pytest.raises(RuntimeError, match="Fail to insert ECO diodes"):
            step.post_iteration_callback(mock_state, full_iteration=False)

    @pytest.mark.parametrize(
        ("mode", "violating_nets", "violating_pins", "raises"),
        [
            pytest.param("all", 2, 0, True, id="all-nets-remain"),
            pytest.param("all", 0, 2, True, id="all-pins-remain"),
            pytest.param("all", 0, 0, False, id="all-clean"),
            pytest.param("ratio", 5, 5, False, id="ratio-tolerates"),
        ],
    )
    def test_post_loop_callback(
        self,
        mock_config: Config,
        mock_state: State,
        mode: str,
        violating_nets: int,
        violating_pins: int,
        raises: bool,
    ) -> None:
        """Only `all` mode fails when violations remain; otherwise the state passes."""
        mock_state.metrics["antenna__violating__nets"] = violating_nets
        mock_state.metrics["antenna__violating__pins"] = violating_pins
        step = AutoEcoDiodeInsertion(mock_config, mock_state)
        step.config = mock_config.copy(AUTO_ECO_DIODE_INSERT_MODE=mode)

        if raises:
            with pytest.raises(RuntimeError, match="Antenna violations remain"):
                step.post_loop_callback(mock_state)
        else:
            assert step.post_loop_callback(mock_state) is mock_state

    def test_run_skip_when_mode_none(
        self, mocker: MockerFixture, mock_config: Config, mock_state: State
    ) -> None:
        """Test run skips processing when mode is 'none'."""
        mock_config = mock_config.copy(AUTO_ECO_DIODE_INSERT_MODE="none")

        mock_run = mocker.patch(
            "fabulous.fabric_generator.gds_generator.steps.while_step.WhileStep.run",
            return_value=({}, {}),
        )

        step = AutoEcoDiodeInsertion(mock_config, mock_state)
        step.config = mock_config
        views_update, metrics_update = step.run(mock_state)

        assert views_update == {}
        assert metrics_update == {}
        mock_run.assert_not_called()

    def test_run_processes_when_mode_not_none(
        self, mocker: MockerFixture, mock_config: Config, mock_state: State
    ) -> None:
        """The loop runs from the input state and reports the diodes it inserted."""
        mock_run = mocker.patch(
            "fabulous.fabric_generator.gds_generator.steps.auto_diode.WhileStep.run",
            return_value=({"view": "data"}, {}),
        )
        step = AutoEcoDiodeInsertion(mock_config, mock_state)
        step.config = mock_config.copy(AUTO_ECO_DIODE_INSERT_MODE="all")
        step.total_diodes_inserted = 7

        views_update, metrics_update = step.run(mock_state)

        mock_run.assert_called_once_with(mock_state)
        assert step.previous_state is mock_state
        assert views_update == {"view": "data"}
        assert metrics_update == {"auto_diode_inserted_total": 7}

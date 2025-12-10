"""Tests for ConditionalMagicDRC step."""

from fabulous.backend.gds.steps.condition_magic_drc import (
    ConditionalMagicDRC,
)
from librelane.config.config import Config
from librelane.state.state import State

from pytest_mock import MockFixture


class test_ConditionalMagicDRC:
    def test_run_skips_when_no_violations(
        self, mock_config: Config, mock_state: State
    ) -> None:
        """Test run method skips processing when no KLayout DRC errors."""
        mock_state.metrics["klayout__drc_error__count"] = 0

        step = ConditionalMagicDRC(mock_config)
        views_update, metrics_update = step.run(mock_state)

        assert views_update == {}
        assert metrics_update == {}

    def test_run_continues_when_violations_exist(
        self, mocker: MockFixture, mock_config: Config, mock_state: State
    ) -> None:
        """Test run method continues processing when KLayout DRC errors exist."""
        mock_state.metrics["klayout__drc_error__count"] = 5

        step = ConditionalMagicDRC(mock_config)

        mock_run = mocker.patch(
            "fabulous.backend.gds.steps.condition_magic_drc.DRC.run",
            return_value=({"view": "data"}, {"metric": 1}),
        )

        views_update, metrics_update = step.run(mock_state)

        mock_run.assert_called_once_with(mock_state)
        assert views_update == {"view": "data"}
        assert metrics_update == {"metric": 1}

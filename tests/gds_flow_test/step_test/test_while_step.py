"""Tests for WhileStep base class."""

import pytest
from librelane.config.config import Config
from librelane.state.state import State
from librelane.steps.step import Step
from pytest_mock import MockerFixture

from fabulous.fabric_generator.gds_generator.steps.while_step import WhileStep


class CustomError(Exception):
    """Marker exception used to exercise propagate_exceptions handling."""


class _InnerStep(Step):
    """Minimal sub-step whose `start` is patched per-test."""

    id = "Test.Inner"
    name = "Inner"
    inputs = []  # noqa: RUF012
    outputs = []  # noqa: RUF012
    config_vars = []  # noqa: RUF012

    def run(self, state_in: State, **kwargs: dict) -> tuple[dict, dict]:  # noqa: D102, ARG002
        return {}, {}


class TestWhileStep:
    """Test suite for WhileStep base class."""

    def test_condition_default(self, mock_config: Config, mock_state: State) -> None:
        """Test that condition returns True by default.

        Also validates that default class attributes are set correctly, as they affect
        the condition behavior.
        """
        step = WhileStep(mock_config)

        # Verify default class attributes are set (tests actual behavior dependency)
        assert WhileStep.max_iterations == 10, "max_iterations should default to 10"
        assert WhileStep.raise_on_failure is True, (
            "raise_on_failure should default to True"
        )
        assert WhileStep.break_on_failure is True, (
            "break_on_failure should default to True"
        )

        # Test the actual condition behavior
        assert step.condition(mock_state) is True

    def test_mid_iteration_break_default(
        self, mock_config: Config, mock_state: State, mocker: MockerFixture
    ) -> None:
        """Test that mid_iteration_break returns False by default."""
        mock_step_class = mocker.MagicMock()
        step = WhileStep(mock_config)
        assert step.mid_iteration_break(mock_state, mock_step_class) is False

    def test_post_loop_callback_default(
        self, mock_config: Config, mock_state: State
    ) -> None:
        """Test that post_loop_callback returns state unchanged by default."""
        step = WhileStep(mock_config)
        result = step.post_loop_callback(mock_state)
        assert result == mock_state

    def test_pre_iteration_callback_default(
        self, mock_config: Config, mock_state: State
    ) -> None:
        """Test that pre_iteration_callback returns state unchanged by default."""
        step = WhileStep(mock_config)
        result = step.pre_iteration_callback(mock_state)
        assert result == mock_state

    def test_post_iteration_callback_default(
        self, mock_config: Config, mock_state: State
    ) -> None:
        """Test that post_iteration_callback returns state unchanged by default."""
        step = WhileStep(mock_config)
        result = step.post_iteration_callback(mock_state, True)
        assert result == mock_state

    def test_get_current_iteration_dir_none_initially(
        self, mock_config: Config
    ) -> None:
        """Test that current iteration directory is None initially."""
        step = WhileStep(mock_config)
        assert step.get_current_iteration_dir() is None

    def test_propagate_exceptions_reraises_over_break(
        self,
        mock_config: Config,
        mock_state: State,
        mocker: MockerFixture,
        tmp_path,  # noqa: ANN001
    ) -> None:
        """An exception in propagate_exceptions re-raises even when break_on_failure.

        propagate_exceptions must win over break_on_failure (and raise_on_failure
        being False), which would otherwise swallow the error via `break`.
        """

        class PropagatingWhileStep(WhileStep):
            Steps = [_InnerStep]  # noqa: RUF012
            outputs = []  # noqa: RUF012
            propagate_exceptions = (CustomError,)
            raise_on_failure = False
            break_on_failure = True
            max_iterations = 1

        mocker.patch.object(_InnerStep, "start", side_effect=CustomError("boom"))

        step = PropagatingWhileStep(mock_config)
        step.config = mock_config
        step.step_dir = str(tmp_path)
        step.toolbox = mocker.MagicMock()
        step.name = "PropagatingWhileStep"

        with pytest.raises(CustomError):
            step.run(mock_state)

    def test_break_on_failure_swallows_when_not_propagated(
        self,
        mock_config: Config,
        mock_state: State,
        mocker: MockerFixture,
        tmp_path,  # noqa: ANN001
    ) -> None:
        """With empty propagate_exceptions, break_on_failure swallows the error."""

        class SwallowingWhileStep(WhileStep):
            Steps = [_InnerStep]  # noqa: RUF012
            outputs = []  # noqa: RUF012
            propagate_exceptions = ()
            raise_on_failure = False
            break_on_failure = True
            max_iterations = 1

        mocker.patch.object(_InnerStep, "start", side_effect=CustomError("boom"))

        step = SwallowingWhileStep(mock_config)
        step.config = mock_config
        step.step_dir = str(tmp_path)
        step.toolbox = mocker.MagicMock()
        step.name = "SwallowingWhileStep"

        # Should complete without raising because break_on_failure breaks the loop.
        views_update, metrics_update = step.run(mock_state)
        assert views_update == {}
        assert metrics_update == {}

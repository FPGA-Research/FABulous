"""Tests for WhileStep base class."""

from fabulous.backend.gds.steps.while_step import WhileStep


class TestWhileStep:
    """Test suite for WhileStep base class."""

    def test_condition_default(self, mock_config, mock_state):
        """Test that condition returns True by default.

        Also validates that default class attributes are set correctly,
        as they affect the condition behavior.
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

    def test_mid_iteration_break_default(self, mock_config, mock_state, mocker):
        """Test that mid_iteration_break returns False by default."""
        mock_step_class = mocker.MagicMock()
        step = WhileStep(mock_config)
        assert step.mid_iteration_break(mock_state, mock_step_class) is False

    def test_post_loop_callback_default(self, mock_config, mock_state):
        """Test that post_loop_callback returns state unchanged by default."""
        step = WhileStep(mock_config)
        result = step.post_loop_callback(mock_state)
        assert result == mock_state

    def test_pre_iteration_callback_default(self, mock_config, mock_state):
        """Test that pre_iteration_callback returns state unchanged by default."""
        step = WhileStep(mock_config)
        result = step.pre_iteration_callback(mock_state)
        assert result == mock_state

    def test_post_iteration_callback_default(self, mock_config, mock_state):
        """Test that post_iteration_callback returns state unchanged by default."""
        step = WhileStep(mock_config)
        result = step.post_iteration_callback(mock_state, True)
        assert result == mock_state

    def test_get_current_iteration_dir_none_initially(self, mock_config):
        """Test that current iteration directory is None initially."""
        step = WhileStep(mock_config)
        assert step.get_current_iteration_dir() is None

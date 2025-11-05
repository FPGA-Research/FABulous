"""Tests for WhileStep base class."""

from FABulous.fabric_generator.gds_generator.steps.while_step import WhileStep


class TestWhileStep:
    """Test suite for WhileStep base class."""

    def test_default_max_iterations(self):
        """Test that max_iterations has a default value."""
        assert WhileStep.max_iterations == 10

    def test_default_raise_on_failure(self):
        """Test that raise_on_failure defaults to True."""
        assert WhileStep.raise_on_failure is True

    def test_default_break_on_failure(self):
        """Test that break_on_failure defaults to True."""
        assert WhileStep.break_on_failure is True

    def test_condition_default(self, mock_config, mock_state):
        """Test that condition returns True by default."""
        step = WhileStep(mock_config)
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

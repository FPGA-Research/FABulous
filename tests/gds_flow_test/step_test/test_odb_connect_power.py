"""Tests for FABulousPower (ODB power connection) step.

This step has custom get_command() logic that adds the metal layer parameter.
"""

from librelane.config.config import Config
from librelane.state.state import State

from FABulous.fabric_generator.gds_generator.steps.odb_connect_power import (
    FABulousPower,
)


class TestFABulousPower:
    """Test suite for FABulousPower step - focuses on metal layer parameter."""

    def test_get_script_path(self, mock_config: Config, mock_state: State) -> None:
        """Test that get_script_path returns the correct script path."""
        step = FABulousPower(mock_config, mock_state)
        script_path = step.get_script_path()
        assert (
            "FABulous/fabric_generator/gds_generator/script/odb_power.py" in script_path
        )

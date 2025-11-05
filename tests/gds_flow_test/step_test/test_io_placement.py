"""Tests for FABulousTileIOPlacement and FABulousFabricIOPlacement steps."""

from librelane.config.config import Config
from librelane.state.state import State

from FABulous.fabric_generator.gds_generator.steps.fabric_IO_placement import (
    FABulousFabricIOPlacement,
)
from FABulous.fabric_generator.gds_generator.steps.tile_IO_placement import (
    FABulousTileIOPlacement,
)


class TestFABulousTileIOPlacement:
    """Test suite for FABulousTileIOPlacement step."""

    def test_get_script_path(self, mock_config: Config, mock_state: State):
        """Test that script path is correctly generated."""
        step = FABulousTileIOPlacement(mock_config, mock_state)
        script_path = step.get_script_path()
        assert (
            "FABulous/fabric_generator/gds_generator/script/tile_io_place.py"
            in script_path
        )


class TestFABulousFabricIOPlacement:
    """Test suite for FABulousFabricIOPlacement step."""

    def test_get_script_path(self, mock_config: Config, mock_state: State):
        """Test that script path is correctly generated."""
        step = FABulousFabricIOPlacement(mock_config)
        script_path = step.get_script_path()
        assert (
            "FABulous/fabric_generator/gds_generator/script/fabric_io_place.py"
            in script_path
        )

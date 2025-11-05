"""Tests for FABulousTileIOPlacement and FABulousFabricIOPlacement steps."""

from FABulous.fabric_generator.gds_generator.steps.fabric_IO_placement import (
    FABulousFabricIOPlacement,
)
from FABulous.fabric_generator.gds_generator.steps.tile_IO_placement import (
    FABulousTileIOPlacement,
)


class TestFABulousTileIOPlacement:
    """Test suite for FABulousTileIOPlacement step."""

    def test_get_script_path(self, mock_config):
        """Test that script path is correctly generated."""
        step = FABulousTileIOPlacement(mock_config)
        script_path = step.get_script_path()

        assert script_path.endswith("tile_io_place.py")
        assert "FABulous" in script_path
        assert "gds_generator" in script_path


class TestFABulousFabricIOPlacement:
    """Test suite for FABulousFabricIOPlacement step."""

    def test_get_script_path(self, mock_config):
        """Test that script path is correctly generated."""
        step = FABulousFabricIOPlacement(mock_config)
        script_path = step.get_script_path()

        assert script_path.endswith("fabric_io_place.py")
        assert "FABulous" in script_path
        assert "gds_generator" in script_path

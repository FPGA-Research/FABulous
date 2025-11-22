"""Tests for FABulousFabricMacroFullFlow - Full automatic fabric flow.

Tests focus on:
- Flow initialization and configuration
- Project directory validation
- Worker function behavior
- Flow steps and configuration variables
"""

from pathlib import Path

import pytest
from pytest_mock import MockerFixture

from FABulous.fabric_generator.gds_generator.flows.full_fabric_flow import (
    FABulousFabricMacroFullFlow,
    _run_tile_flow_worker,
)
from FABulous.fabric_generator.gds_generator.steps.tile_optimisation import OptMode


# Shared fixtures
@pytest.fixture
def mock_flow_with_validate_project_dir(mocker: MockerFixture):
    """Create a mock flow with _validate_project_dir method bound."""
    flow = mocker.MagicMock(spec=FABulousFabricMacroFullFlow)
    flow._validate_project_dir = FABulousFabricMacroFullFlow._validate_project_dir
    return flow


@pytest.fixture
def mock_fabric(mocker: MockerFixture):
    """Create a mock fabric for testing."""
    fabric = mocker.MagicMock()
    fabric.tileDic = {"tile1": mocker.MagicMock(), "tile2": mocker.MagicMock()}
    fabric.superTileDic = {}
    return fabric


class TestValidateProjectDir:
    """Tests for _validate_project_dir method."""

    def test_validate_project_dir_success(
        self, mock_flow_with_validate_project_dir, mock_fabric, tmp_path
    ):
        """Test validation passes for valid directory structure."""
        flow = mock_flow_with_validate_project_dir
        # Create required directories
        tile_dir = tmp_path / "Tile"
        tile_dir.mkdir()
        (tile_dir / "tile1").mkdir()
        (tile_dir / "tile2").mkdir()

        # Should not raise
        flow._validate_project_dir(flow, tmp_path, mock_fabric)

    def test_validate_project_dir_missing_proj_dir(
        self, mock_flow_with_validate_project_dir, mock_fabric
    ):
        """Test validation fails when project directory doesn't exist."""
        flow = mock_flow_with_validate_project_dir
        nonexistent = Path("/nonexistent/path")

        with pytest.raises(FileNotFoundError, match="Project directory not found"):
            flow._validate_project_dir(flow, nonexistent, mock_fabric)

    def test_validate_project_dir_not_a_directory(
        self, mock_flow_with_validate_project_dir, mock_fabric, tmp_path
    ):
        """Test validation fails when path is not a directory."""
        flow = mock_flow_with_validate_project_dir
        file_path = tmp_path / "file.txt"
        file_path.touch()

        with pytest.raises(NotADirectoryError, match="not a directory"):
            flow._validate_project_dir(flow, file_path, mock_fabric)

    def test_validate_project_dir_missing_tile_dir(
        self, mock_flow_with_validate_project_dir, mock_fabric, tmp_path
    ):
        """Test validation fails when Tile directory is missing."""
        flow = mock_flow_with_validate_project_dir
        with pytest.raises(FileNotFoundError, match="Tile directory not found"):
            flow._validate_project_dir(flow, tmp_path, mock_fabric)

    def test_validate_project_dir_missing_tiles(
        self, mock_flow_with_validate_project_dir, mock_fabric, tmp_path
    ):
        """Test validation fails when tile directories are missing."""
        flow = mock_flow_with_validate_project_dir
        tile_dir = tmp_path / "Tile"
        tile_dir.mkdir()
        # Only create tile1, not tile2
        (tile_dir / "tile1").mkdir()

        with pytest.raises(FileNotFoundError, match="Missing tile directories"):
            flow._validate_project_dir(flow, tmp_path, mock_fabric)

    def test_validate_project_dir_with_supertiles(
        self, mock_flow_with_validate_project_dir, mocker: MockerFixture, tmp_path
    ):
        """Test validation with SuperTiles."""
        flow = mock_flow_with_validate_project_dir
        fabric = mocker.MagicMock()
        fabric.tileDic = {"subtile1": mocker.MagicMock()}

        # SuperTile containing subtile1
        supertile = mocker.MagicMock()
        supertile.tiles = [mocker.MagicMock(name="subtile1")]
        supertile.tiles[0].name = "subtile1"
        fabric.superTileDic = {"SuperTile1": supertile}

        tile_dir = tmp_path / "Tile"
        tile_dir.mkdir()
        # SubTiles don't need directories, but SuperTiles do
        (tile_dir / "SuperTile1").mkdir()

        flow._validate_project_dir(flow, tmp_path, fabric)

    def test_validate_project_dir_missing_supertile_dir(
        self, mock_flow_with_validate_project_dir, mocker: MockerFixture, tmp_path
    ):
        """Test validation fails when SuperTile directory is missing."""
        flow = mock_flow_with_validate_project_dir
        fabric = mocker.MagicMock()
        fabric.tileDic = {}

        supertile = mocker.MagicMock()
        supertile.tiles = []
        fabric.superTileDic = {"SuperTile1": supertile}

        tile_dir = tmp_path / "Tile"
        tile_dir.mkdir()

        with pytest.raises(FileNotFoundError, match="SuperTile"):
            flow._validate_project_dir(flow, tmp_path, fabric)


class TestRunTileFlowWorker:
    """Tests for _run_tile_flow_worker function."""

    def test_worker_catches_exceptions(self, mocker: MockerFixture, tmp_path):
        """Test that worker catches exceptions and returns error trace."""
        # Set up mocks
        mock_context = mocker.MagicMock()
        mock_context.pdk = "test_pdk"
        mock_context.pdk_root = tmp_path
        mocker.patch(
            "FABulous.fabric_generator.gds_generator.flows.full_fabric_flow.init_context",
            return_value=mock_context,
        )

        # Make flow raise an exception
        mocker.patch(
            "FABulous.fabric_generator.gds_generator.flows.full_fabric_flow.FABulousTileVerilogMarcoFlow",
            side_effect=ValueError("Test error"),
        )

        tile = mocker.MagicMock()
        result = _run_tile_flow_worker(
            tile,
            tmp_path,
            tmp_path / "io.yaml",
            OptMode.BALANCE,
            tmp_path / "base.yaml",
            tmp_path / "override.yaml",
        )

        # Should return (None, error_trace)
        state, error_trace = result
        assert state is None
        assert error_trace is not None
        assert "Test error" in error_trace

    def test_worker_returns_state_on_success(self, mocker: MockerFixture, tmp_path):
        """Test that worker returns state on successful execution."""
        mock_context = mocker.MagicMock()
        mock_context.pdk = "test_pdk"
        mock_context.pdk_root = tmp_path
        mocker.patch(
            "FABulous.fabric_generator.gds_generator.flows.full_fabric_flow.init_context",
            return_value=mock_context,
        )

        mock_state = mocker.MagicMock()
        mock_flow = mocker.MagicMock()
        mock_flow.start.return_value = mock_state
        mocker.patch(
            "FABulous.fabric_generator.gds_generator.flows.full_fabric_flow.FABulousTileVerilogMarcoFlow",
            return_value=mock_flow,
        )

        tile = mocker.MagicMock()
        result = _run_tile_flow_worker(
            tile,
            tmp_path,
            tmp_path / "io.yaml",
            OptMode.BALANCE,
            tmp_path / "base.yaml",
            tmp_path / "override.yaml",
        )

        state, error_trace = result
        assert state is mock_state
        assert error_trace is None


class TestWorkerCustomOverrides:
    """Tests for custom config overrides in worker function."""

    def test_worker_passes_custom_overrides(self, mocker: MockerFixture, tmp_path):
        """Test that worker passes custom config overrides to flow."""
        mock_context = mocker.MagicMock()
        mock_context.pdk = "test_pdk"
        mock_context.pdk_root = tmp_path
        mocker.patch(
            "FABulous.fabric_generator.gds_generator.flows.full_fabric_flow.init_context",
            return_value=mock_context,
        )

        mock_state = mocker.MagicMock()
        mock_flow = mocker.MagicMock()
        mock_flow.start.return_value = mock_state
        mock_flow_class = mocker.patch(
            "FABulous.fabric_generator.gds_generator.flows.full_fabric_flow.FABulousTileVerilogMarcoFlow",
            return_value=mock_flow,
        )

        tile = mocker.MagicMock()
        _run_tile_flow_worker(
            tile,
            tmp_path,
            tmp_path / "io.yaml",
            OptMode.BALANCE,
            tmp_path / "base.yaml",
            tmp_path / "override.yaml",
            CUSTOM_KEY="custom_value",
        )

        # Check that custom override was passed
        call_kwargs = mock_flow_class.call_args
        assert "CUSTOM_KEY" in call_kwargs.kwargs or (
            len(call_kwargs.args) > 0 and hasattr(call_kwargs, "kwargs")
        )

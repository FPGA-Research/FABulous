"""Shared fixtures for GDS flow tests.

Provides mock PDK fixtures and common test utilities for testing
FABulousTileVerilogMacroFlow and FABulousFabricMacroFlow.
"""

from decimal import Decimal
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

import pytest
import yaml
from librelane.config.config import Config
from librelane.config.variable import Instance, Macro, Orientation
from pytest_mock import MockerFixture

from fabulous.fabric_definition.supertile import SuperTile
from fabulous.fabric_definition.tile import Tile

# PDK track info content for realistic routing grid
TRACKS_INFO_CONTENT: str = """M1 X 0 0.28
M1 Y 0 0.28
M2 X 0.14 0.56
M2 Y 0 0.56
M3 X 0 0.28
M3 Y 0 0.28
M4 X 0.14 0.56
M4 Y 0 0.56
"""


@pytest.fixture
def mock_pdk_root(tmp_path: Path) -> dict[str, Any]:
    """Create a minimal but realistic mock PDK directory structure.

    Returns a dictionary with:
    - pdk_root: Path to PDK root directory
    - pdk: PDK name (sky130A)
    - tracks_file: Path to tracks info file
    - config_vars: Dict of PDK config variables
    """
    pdk_name: str = "sky130A"
    pdk_dir: Path = tmp_path / "pdk" / pdk_name
    pdk_dir.mkdir(parents=True)

    # Create tracks info file
    tracks_file: Path = pdk_dir / "tracks.info"
    tracks_file.write_text(TRACKS_INFO_CONTENT)

    return {
        "pdk_root": tmp_path / "pdk",
        "pdk": pdk_name,
        "tracks_file": tracks_file,
        "config_vars": {
            "FP_TRACKS_INFO": str(tracks_file),
            "IO_PIN_V_LAYER": "M1",
            "IO_PIN_H_LAYER": "M2",
            "RT_MAX_LAYER": "M4",
        },
    }


@pytest.fixture
def mock_config_load(
    mocker: MockerFixture, mock_pdk_root: dict[str, Any], tmp_path: Path
) -> None:
    """Mock Config.load to return a properly structured Config.

    This fixture patches librelane.config.config.Config.load to avoid PDK
    validation while providing realistic config values.
    """

    def _mock_load(
        *args: Any,  # noqa: ANN401
        **kwargs: Any,  # noqa: ANN401
    ) -> tuple[Config, str]:
        # Config.load is called with keyword arguments:
        # Config.load(config_in=..., design_dir=..., pdk=..., etc.)
        config: Any = kwargs.get("config_in", args[0] if args else {})

        # It can be a dict or a Config object
        config_dict: dict[str, Any]
        if isinstance(config, dict):
            config_dict = dict(config)
        elif hasattr(config, "to_dict"):
            config_dict = config.to_dict()
        elif hasattr(config, "keys"):
            config_dict = dict(config)
        else:
            config_dict = {}

        design_dir: str = kwargs.get("design_dir", str(tmp_path / "design"))

        # Add required PDK config variables (don't override existing)
        for key, value in mock_pdk_root["config_vars"].items():
            if key not in config_dict:
                config_dict[key] = value

        # Add default values for FABulous-specific configs (don't override existing)
        defaults: dict[str, Any] = {
            "DESIGN_DIR": design_dir,
            "FABULOUS_IGNORE_DEFAULT_DIE_AREA": False,
            "ROUTING_OBSTRUCTIONS": None,
            "FABULOUS_TILE_LOGICAL_WIDTH": 1,
            "FABULOUS_TILE_LOGICAL_HEIGHT": 1,
        }

        for key, value in defaults.items():
            if key not in config_dict:
                config_dict[key] = value

        return Config(config_dict), design_dir

    mocker.patch("librelane.config.config.Config.load", side_effect=_mock_load)


@pytest.fixture
def mock_tile(mocker: MockerFixture, tmp_path: Path) -> MagicMock:
    """Create a mock Tile object with realistic attributes."""
    tile_dir: Path = tmp_path / "tiles" / "test_tile"
    tile_dir.mkdir(parents=True)

    # Create a Verilog file for the tile
    verilog_file: Path = tile_dir.parent / "test.v"
    verilog_file.write_text("module TestTile(); endmodule")

    mock: MagicMock = mocker.MagicMock(spec=Tile)
    mock.name = "TestTile"
    mock.tileDir = tile_dir
    mock.get_min_die_area.return_value = (Decimal("100.0"), Decimal("100.0"))

    return mock


@pytest.fixture
def mock_supertile(mocker: MockerFixture, tmp_path: Path) -> MagicMock:
    """Create a mock SuperTile object with realistic attributes."""
    tile_dir: Path = tmp_path / "tiles" / "test_supertile"
    tile_dir.mkdir(parents=True)

    # Create a Verilog file for the supertile
    verilog_file: Path = tile_dir.parent / "test.v"
    if not verilog_file.exists():
        verilog_file.write_text("module TestSuperTile(); endmodule")

    mock: MagicMock = mocker.MagicMock(spec=SuperTile)
    mock.name = "TestSuperTile"
    mock.tileDir = tile_dir
    mock.max_width = 4
    mock.max_height = 3
    mock.get_min_die_area.return_value = (Decimal("200.0"), Decimal("150.0"))

    return mock


@pytest.fixture
def io_pin_config(tmp_path: Path) -> Path:
    """Create a temporary IO pin config file."""
    config_path: Path = tmp_path / "io_pins.yaml"
    config_path.write_text(yaml.dump({"pins": []}))
    return config_path


@pytest.fixture
def base_config_file(tmp_path: Path) -> Path:
    """Create a base config file for testing config merging."""
    config_path: Path = tmp_path / "base_config.yaml"
    config_path.write_text(
        yaml.dump(
            {
                "BASE_VAR": "base_value",
                "OVERRIDE_ME": "base",
                "PDN_CONFIG": "base_pdn",
            }
        )
    )
    return config_path


@pytest.fixture
def override_config_file(tmp_path: Path) -> Path:
    """Create an override config file for testing config merging."""
    config_path: Path = tmp_path / "override_config.yaml"
    config_path.write_text(
        yaml.dump({"OVERRIDE_ME": "override", "OVERRIDE_VAR": "override_value"})
    )
    return config_path


@pytest.fixture
def mock_fabric(mocker: MockerFixture) -> MagicMock:
    """Create a minimal mock Fabric object for testing."""
    fabric: MagicMock = mocker.MagicMock()
    fabric.name = "TestFabric"
    fabric.numberOfRows = 2
    fabric.numberOfColumns = 2
    fabric.superTileDic = {}
    return fabric


def create_macro(instances: dict[str, Instance]) -> Macro:
    """Helper function to create a valid Macro object for testing.

    Parameters
    ----------
    instances : dict
        Dictionary mapping instance names to Instance objects.

    Returns
    -------
    Macro
        A Macro object with the given instances and empty file lists.
    """
    return Macro(
        gds=[Path("dummy.gds")],
        lef=[Path("dummy.lef")],
        vh=[],
        nl=[],
        pnl=[],
        spef={},
        instances=instances,
    )


def create_instance(
    x: Decimal, y: Decimal, orientation: Orientation = Orientation.N
) -> Instance:
    """Helper function to create an Instance object.

    Parameters
    ----------
    x : Decimal
        X coordinate of the instance location.
    y : Decimal
        Y coordinate of the instance location.
    orientation : Orientation
        Instance orientation (default: N).

    Returns
    -------
    Instance
        An Instance object at the specified location.
    """
    return Instance(location=(x, y), orientation=orientation)

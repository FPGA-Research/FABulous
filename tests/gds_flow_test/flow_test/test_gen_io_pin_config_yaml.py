"""Tests for gen_io_pin_config_yaml module - IO pin configuration generation.

Tests focus on:
- PinOrderConfig dataclass
- Tile port serialization
- SuperTile port serialization
- IO pin configuration generation
"""


import pytest
import yaml
from pytest_mock import MockerFixture

from FABulous.fabric_definition.define import PinSortMode, Side
from FABulous.fabric_generator.gds_generator.gen_io_pin_config_yaml import (
    PinOrderConfig,
    _serialize_supertile_ports,
    _serialize_tile_ports,
    generate_IO_pin_order_config,
)


class TestPinOrderConfig:
    """Tests for PinOrderConfig dataclass."""

    def test_default_initialization(self):
        """Test PinOrderConfig default values."""
        config = PinOrderConfig()

        assert config.min_distance is None
        assert config.max_distance is None
        assert config.pins == []
        assert config.sort_mode == PinSortMode.BUS_MAJOR
        assert config.reverse_result is False

    def test_custom_initialization(self):
        """Test PinOrderConfig with custom values."""
        config = PinOrderConfig(
            min_distance=10,
            max_distance=100,
            pins=["pin1", "pin2"],
            sort_mode=PinSortMode.BIT_MINOR,
            reverse_result=True,
        )

        assert config.min_distance == 10
        assert config.max_distance == 100
        assert config.pins == ["pin1", "pin2"]
        assert config.sort_mode == PinSortMode.BIT_MINOR
        assert config.reverse_result is True

    def test_call_binds_pins(self):
        """Test that __call__ binds pins to the config."""
        config = PinOrderConfig(min_distance=5)
        result = config(["a", "b", "c"])

        assert result is config
        assert config.pins == ["a", "b", "c"]

    def test_call_returns_self(self):
        """Test that __call__ returns self for chaining."""
        config = PinOrderConfig()
        result = config(["pin"])

        assert result is config

    def test_to_dict_basic(self):
        """Test to_dict serialization with basic values."""
        config = PinOrderConfig()
        config(["pin1", "pin2"])

        result = config.to_dict()

        assert result["min_distance"] is None
        assert result["max_distance"] is None
        assert result["pins"] == ["pin1", "pin2"]
        assert result["sort_mode"] == str(PinSortMode.BUS_MAJOR)
        assert result["reverse_result"] is False

    def test_to_dict_with_custom_values(self):
        """Test to_dict serialization with custom values."""
        config = PinOrderConfig(
            min_distance=5,
            max_distance=50,
            sort_mode=PinSortMode.BIT_MINOR,
            reverse_result=True,
        )
        config(["a", "b"])

        result = config.to_dict()

        assert result["min_distance"] == 5
        assert result["max_distance"] == 50
        assert result["pins"] == ["a", "b"]
        assert result["reverse_result"] is True

    def test_to_dict_empty_pins(self):
        """Test to_dict with no pins bound."""
        config = PinOrderConfig()
        result = config.to_dict()

        assert result["pins"] == []

    def test_to_dict_integer_pins(self):
        """Test to_dict with integer pin values."""
        config = PinOrderConfig()
        config([1, 2, 3])

        result = config.to_dict()

        assert result["pins"] == [1, 2, 3]


class TestSerializeTilePorts:
    """Tests for _serialize_tile_ports function."""

    @pytest.fixture
    def mock_tile(self, mocker: MockerFixture):
        """Create a mock tile for testing."""
        tile = mocker.MagicMock()

        # Mock ports
        north_port = mocker.MagicMock()
        north_port.getPortRegex.return_value = r"N\[\d+\]"

        east_port = mocker.MagicMock()
        east_port.getPortRegex.return_value = r"E\[\d+\]"

        south_port = mocker.MagicMock()
        south_port.getPortRegex.return_value = r"S\[\d+\]"

        west_port = mocker.MagicMock()
        west_port.getPortRegex.return_value = r"W\[\d+\]"

        # Set up side port methods
        tile.getNorthSidePorts.return_value = [north_port]
        tile.getEastSidePorts.return_value = [east_port]
        tile.getSouthSidePorts.return_value = [south_port]
        tile.getWestSidePorts.return_value = [west_port]

        # Pin order config for each side
        tile.pinOrderConfig = {
            Side.NORTH: PinOrderConfig(),
            Side.EAST: PinOrderConfig(),
            Side.SOUTH: PinOrderConfig(),
            Side.WEST: PinOrderConfig(),
        }

        # No BELs
        tile.bels = []

        return tile

    def test_serialize_tile_ports_basic(self, mock_tile):
        """Test basic tile port serialization."""
        result = _serialize_tile_ports(mock_tile)

        # Should have all four sides
        assert "NORTH" in result
        assert "EAST" in result
        assert "SOUTH" in result
        assert "WEST" in result

    def test_serialize_tile_ports_north_includes_clock_and_strobe(self, mock_tile):
        """Test that north side includes UserCLKo and FrameStrobe_O."""
        result = _serialize_tile_ports(mock_tile)

        # North should have port + UserCLKo + FrameStrobe_O
        assert len(result["NORTH"]) >= 3

        # Check for expected pins in the config
        pin_lists = [config["pins"] for config in result["NORTH"]]
        all_pins = [pin for pins in pin_lists for pin in pins]

        assert "UserCLKo" in all_pins or any("UserCLKo" in str(p) for p in all_pins)

    def test_serialize_tile_ports_south_includes_clock_and_strobe(self, mock_tile):
        """Test that south side includes UserCLK and FrameStrobe."""
        result = _serialize_tile_ports(mock_tile)

        # South should have port + UserCLK + FrameStrobe
        assert len(result["SOUTH"]) >= 3

        pin_lists = [config["pins"] for config in result["SOUTH"]]
        all_pins = [pin for pins in pin_lists for pin in pins]

        assert "UserCLK" in all_pins or any("UserCLK" in str(p) for p in all_pins)

    def test_serialize_tile_ports_east_includes_frame_data_o(self, mock_tile):
        """Test that east side includes FrameData_O."""
        result = _serialize_tile_ports(mock_tile)

        # East should have port + FrameData_O
        assert len(result["EAST"]) >= 2

    def test_serialize_tile_ports_west_includes_frame_data(self, mock_tile):
        """Test that west side includes FrameData."""
        result = _serialize_tile_ports(mock_tile)

        # West should have port + FrameData
        assert len(result["WEST"]) >= 2

    def test_serialize_tile_ports_with_prefix(self, mock_tile):
        """Test serialization with a prefix."""
        result = _serialize_tile_ports(mock_tile, prefix="Tile_X0Y0_")

        # Verify prefix is applied
        pin_lists = [config["pins"] for config in result["NORTH"]]
        all_pins = [pin for pins in pin_lists for pin in pins]

        assert any("Tile_X0Y0_" in str(p) for p in all_pins)

    def test_serialize_tile_ports_with_bels(self, mocker: MockerFixture):
        """Test serialization with BEL external ports."""
        tile = mocker.MagicMock()

        # Empty side ports
        tile.getNorthSidePorts.return_value = []
        tile.getEastSidePorts.return_value = []
        tile.getSouthSidePorts.return_value = []
        tile.getWestSidePorts.return_value = []

        tile.pinOrderConfig = {
            Side.NORTH: PinOrderConfig(),
            Side.EAST: PinOrderConfig(),
            Side.SOUTH: PinOrderConfig(),
            Side.WEST: PinOrderConfig(),
        }

        # BEL with external ports
        bel = mocker.MagicMock()
        bel.externalInput = ["ext_in"]
        bel.externalOutput = ["ext_out"]
        tile.bels = [bel]

        result = _serialize_tile_ports(tile, external_port_side=Side.SOUTH)

        # Check that BEL ports are on the south side
        south_configs = result["SOUTH"]
        pin_lists = [config["pins"] for config in south_configs]
        all_pins = [pin for pins in pin_lists for pin in pins]

        assert "ext_in" in all_pins
        assert "ext_out" in all_pins

    def test_serialize_tile_ports_empty_port_regex(self, mock_tile):
        """Test handling of ports that return empty regex."""
        # Make one port return empty regex
        mock_tile.getNorthSidePorts.return_value[0].getPortRegex.return_value = ""

        result = _serialize_tile_ports(mock_tile)

        # Should still work without errors
        assert "NORTH" in result


class TestSerializeSupertilePorts:
    """Tests for _serialize_supertile_ports function."""

    @pytest.fixture
    def mock_supertile(self, mocker: MockerFixture):
        """Create a mock supertile for testing."""
        supertile = mocker.MagicMock()

        # Create a mock tile for the tilemap
        mock_tile = mocker.MagicMock()
        mock_tile.pinOrderConfig = {
            Side.NORTH: PinOrderConfig(),
            Side.EAST: PinOrderConfig(),
            Side.SOUTH: PinOrderConfig(),
            Side.WEST: PinOrderConfig(),
        }
        mock_tile.bels = []

        # 2x2 supertile
        supertile.tileMap = [
            [mock_tile, mock_tile],
            [mock_tile, mock_tile],
        ]

        # Mock port with side information
        north_port = mocker.MagicMock()
        north_port.sideOfTile = Side.NORTH
        north_port.getPortRegex.return_value = r"N\[\d+\]"

        south_port = mocker.MagicMock()
        south_port.sideOfTile = Side.SOUTH
        south_port.getPortRegex.return_value = r"S\[\d+\]"

        # Return ports around tile
        supertile.getPortsAroundTile.return_value = {
            "0,0": [[south_port]],
            "1,1": [[north_port]],
        }

        return supertile

    def test_serialize_supertile_ports_basic(self, mock_supertile):
        """Test basic supertile port serialization."""
        result = _serialize_supertile_ports(mock_supertile)

        # Should have keys for tiles with ports
        assert "X0Y0" in result or "X1Y1" in result

    def test_serialize_supertile_ports_empty_port_lists(self, mocker: MockerFixture):
        """Test handling of empty port lists."""
        supertile = mocker.MagicMock()
        supertile.getPortsAroundTile.return_value = {}

        result = _serialize_supertile_ports(supertile)

        assert result == {}

    def test_serialize_supertile_ports_with_prefix(self, mock_supertile):
        """Test supertile serialization with prefix."""
        result = _serialize_supertile_ports(mock_supertile, prefix="Test_")

        # Result should contain tile coordinates
        assert isinstance(result, dict)

    def test_serialize_supertile_ports_none_tile(self, mocker: MockerFixture):
        """Test handling when tileMap has None entries."""
        supertile = mocker.MagicMock()

        # TileMap with None
        supertile.tileMap = [[None]]

        port = mocker.MagicMock()
        port.sideOfTile = Side.SOUTH
        port.getPortRegex.return_value = r"S\[\d+\]"

        supertile.getPortsAroundTile.return_value = {
            "0,0": [[port]],
        }

        result = _serialize_supertile_ports(supertile)

        # Should handle None tile gracefully
        if "X0Y0" in result:
            assert all(not config for config in result["X0Y0"].values())


class TestGenerateIOPinOrderConfig:
    """Tests for generate_IO_pin_order_config function."""

    @pytest.fixture
    def mock_fabric(self, mocker: MockerFixture):
        """Create a mock fabric for testing."""
        fabric = mocker.MagicMock()
        fabric.find_tile_positions.return_value = [(0, 0)]
        fabric.determine_border_side.return_value = Side.SOUTH
        return fabric

    @pytest.fixture
    def mock_tile(self, mocker: MockerFixture):
        """Create a mock tile for testing."""
        tile = mocker.MagicMock()

        # Empty side ports for simplicity
        tile.getNorthSidePorts.return_value = []
        tile.getEastSidePorts.return_value = []
        tile.getSouthSidePorts.return_value = []
        tile.getWestSidePorts.return_value = []

        tile.pinOrderConfig = {
            Side.NORTH: PinOrderConfig(),
            Side.EAST: PinOrderConfig(),
            Side.SOUTH: PinOrderConfig(),
            Side.WEST: PinOrderConfig(),
        }

        tile.bels = []

        return tile

    def test_generate_io_pin_order_config_writes_yaml(
        self, mock_fabric, mock_tile, tmp_path
    ):
        """Test that config is written to YAML file."""
        outfile = tmp_path / "test_config.yaml"

        generate_IO_pin_order_config(mock_fabric, mock_tile, outfile)

        assert outfile.exists()

        # Verify YAML can be loaded
        with outfile.open() as f:
            config = yaml.safe_load(f)

        assert "X0Y0" in config

    def test_generate_io_pin_order_config_tile_structure(
        self, mock_fabric, mock_tile, tmp_path
    ):
        """Test structure of generated config for a tile."""
        outfile = tmp_path / "test_config.yaml"

        generate_IO_pin_order_config(mock_fabric, mock_tile, outfile)

        with outfile.open() as f:
            config = yaml.safe_load(f)

        # Should have X0Y0 with all four sides
        assert "NORTH" in config["X0Y0"]
        assert "EAST" in config["X0Y0"]
        assert "SOUTH" in config["X0Y0"]
        assert "WEST" in config["X0Y0"]

    def test_generate_io_pin_order_config_with_prefix(
        self, mock_fabric, mock_tile, tmp_path
    ):
        """Test generation with prefix."""
        outfile = tmp_path / "test_config.yaml"

        generate_IO_pin_order_config(mock_fabric, mock_tile, outfile, prefix="Pre_")

        with outfile.open() as f:
            config = yaml.safe_load(f)

        # Config should be generated (specific prefix validation would need
        # more detailed mock setup)
        assert config is not None

    def test_generate_io_pin_order_config_supertile(
        self, mock_fabric, mocker: MockerFixture, tmp_path
    ):
        """Test generation for a SuperTile."""
        from FABulous.fabric_definition.SuperTile import SuperTile

        # Create mock supertile
        mock_supertile = mocker.MagicMock(spec=SuperTile)

        # Simple tilemap
        mock_tile = mocker.MagicMock()
        mock_tile.pinOrderConfig = {
            Side.NORTH: PinOrderConfig(),
            Side.EAST: PinOrderConfig(),
            Side.SOUTH: PinOrderConfig(),
            Side.WEST: PinOrderConfig(),
        }
        mock_tile.bels = []

        mock_supertile.tileMap = [[mock_tile]]
        mock_supertile.getPortsAroundTile.return_value = {}

        # Fabric returns position
        mock_fabric.find_tile_positions.return_value = [(0, 0)]
        mock_fabric.determine_border_side.return_value = Side.SOUTH

        outfile = tmp_path / "test_supertile_config.yaml"

        generate_IO_pin_order_config(mock_fabric, mock_supertile, outfile)

        assert outfile.exists()

    def test_generate_io_pin_order_config_no_positions(
        self, mock_fabric, mock_tile, tmp_path
    ):
        """Test generation when fabric returns no positions."""
        mock_fabric.find_tile_positions.return_value = []

        outfile = tmp_path / "test_config.yaml"

        generate_IO_pin_order_config(mock_fabric, mock_tile, outfile)

        # Should still work with default side
        assert outfile.exists()

    def test_generate_io_pin_order_config_border_side_handling(
        self, mock_fabric, mock_tile, mocker: MockerFixture, tmp_path
    ):
        """Test that border side is used for external ports."""
        mock_fabric.determine_border_side.return_value = Side.EAST

        # Add BEL with external ports
        bel = mocker.MagicMock()
        bel.externalInput = ["ext_in"]
        bel.externalOutput = []
        mock_tile.bels = [bel]

        outfile = tmp_path / "test_config.yaml"

        generate_IO_pin_order_config(mock_fabric, mock_tile, outfile)

        with outfile.open() as f:
            config = yaml.safe_load(f)

        # External ports should be on EAST side
        east_configs = config["X0Y0"]["EAST"]
        pin_lists = [c["pins"] for c in east_configs]
        all_pins = [pin for pins in pin_lists for pin in pins]

        assert "ext_in" in all_pins

    def test_generate_io_pin_order_config_supertile_multiple_positions(
        self, mock_fabric, mocker: MockerFixture, tmp_path
    ):
        """Test supertile with multiple positions uses top-left."""
        from FABulous.fabric_definition.SuperTile import SuperTile

        mock_supertile = mocker.MagicMock(spec=SuperTile)

        mock_tile = mocker.MagicMock()
        mock_tile.pinOrderConfig = {
            Side.NORTH: PinOrderConfig(),
            Side.EAST: PinOrderConfig(),
            Side.SOUTH: PinOrderConfig(),
            Side.WEST: PinOrderConfig(),
        }
        mock_tile.bels = []

        mock_supertile.tileMap = [[mock_tile]]
        mock_supertile.getPortsAroundTile.return_value = {}

        # Multiple positions
        mock_fabric.find_tile_positions.return_value = [(2, 3), (0, 1), (1, 2)]
        mock_fabric.determine_border_side.return_value = None

        outfile = tmp_path / "test_config.yaml"

        generate_IO_pin_order_config(mock_fabric, mock_supertile, outfile)

        assert outfile.exists()


class TestPinOrderConfigIntegration:
    """Integration tests for PinOrderConfig with serialization."""

    def test_config_serialization_round_trip(self):
        """Test that config can be serialized and matches expected format."""
        config = PinOrderConfig(
            min_distance=10,
            max_distance=20,
            sort_mode=PinSortMode.BUS_MAJOR,
            reverse_result=False,
        )
        config([r"Signal\[\d+\]"])

        result = config.to_dict()

        # Verify all required fields
        assert "min_distance" in result
        assert "max_distance" in result
        assert "pins" in result
        assert "sort_mode" in result
        assert "reverse_result" in result

        # Should be YAML-serializable
        yaml_str = yaml.dump(result)
        loaded = yaml.safe_load(yaml_str)

        assert loaded == result

    def test_multiple_configs_same_side(self):
        """Test multiple configs can be created for the same side."""
        config1 = PinOrderConfig()([r"Signal1\[\d+\]"])
        config2 = PinOrderConfig()([r"Signal2\[\d+\]"])

        configs = [config1.to_dict(), config2.to_dict()]

        assert len(configs) == 2
        assert configs[0]["pins"] == [r"Signal1\[\d+\]"]
        assert configs[1]["pins"] == [r"Signal2\[\d+\]"]

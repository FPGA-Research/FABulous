"""Tests for gen_io_pin_config_yaml module - IO pin configuration generation.

Tests focus on:
- PinOrderConfig dataclass
- Tile port serialization
- Composite tile port serialization
- IO pin configuration generation
"""

from pathlib import Path

import pytest
import yaml
from pytest_mock import MockerFixture

from fabulous.fabric_definition.define import PinSortMode, Side
from fabulous.fabric_definition.fabric import Fabric
from fabulous.fabric_definition.tile import Tile
from fabulous.fabric_generator.gds_generator.gen_io_pin_config_yaml import (
    PinOrderConfig,
    _serialize_supertile_ports,
    _serialize_tile_ports,
    generate_IO_pin_order_config,
)


class TestPinOrderConfig:
    """Tests for PinOrderConfig dataclass."""

    def test_default_initialization(self) -> None:
        """Test PinOrderConfig default values."""
        config = PinOrderConfig()

        assert config.min_distance is None
        assert config.max_distance is None
        assert config.pins == []
        assert config.sort_mode == PinSortMode.BUS_MAJOR
        assert config.reverse_result is False

    def test_custom_initialization(self) -> None:
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

    def test_call_binds_pins(self) -> None:
        """Test that __call__ binds pins to the config."""
        config = PinOrderConfig(min_distance=5)
        result = config(["a", "b", "c"])

        assert result is config
        assert config.pins == ["a", "b", "c"]

    def test_call_returns_self(self) -> None:
        """Test that __call__ returns self for chaining."""
        config = PinOrderConfig()
        result = config(["pin"])

        assert result is config

    def test_to_dict_basic(self) -> None:
        """Test to_dict serialization with basic values."""
        config = PinOrderConfig()
        config(["pin1", "pin2"])

        result = config.to_dict()

        assert result["min_distance"] is None
        assert result["max_distance"] is None
        assert result["pins"] == ["pin1", "pin2"]
        assert result["sort_mode"] == str(PinSortMode.BUS_MAJOR)
        assert result["reverse_result"] is False

    def test_to_dict_with_custom_values(self) -> None:
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

    def test_to_dict_empty_pins(self) -> None:
        """Test to_dict with no pins bound."""
        config = PinOrderConfig()
        result = config.to_dict()

        assert result["pins"] == []

    def test_to_dict_integer_pins(self) -> None:
        """Test to_dict with integer pin values."""
        config = PinOrderConfig()
        config([1, 2, 3])

        result = config.to_dict()

        assert result["pins"] == [1, 2, 3]


class TestSerializeTilePorts:
    """Tests for _serialize_tile_ports function."""

    @pytest.fixture
    def mock_tile(self, mocker: MockerFixture) -> Tile:
        """Create a mock tile for testing."""
        tile = mocker.MagicMock(spec=Tile)
        tile.is_composite = False

        # Mock ports
        north_port = mocker.MagicMock()
        north_port.get_port_regex.return_value = r"N\[\d+\]"

        east_port = mocker.MagicMock()
        east_port.get_port_regex.return_value = r"E\[\d+\]"

        south_port = mocker.MagicMock()
        south_port.get_port_regex.return_value = r"S\[\d+\]"

        west_port = mocker.MagicMock()
        west_port.get_port_regex.return_value = r"W\[\d+\]"

        # Set up side port methods
        side_ports = {
            Side.NORTH: [north_port],
            Side.EAST: [east_port],
            Side.SOUTH: [south_port],
            Side.WEST: [west_port],
        }
        tile.get_port_on_side.side_effect = lambda side, _io=None: side_ports[side]

        # Pin order config for each side
        tile.pin_order_config = {
            Side.NORTH: PinOrderConfig(),
            Side.EAST: PinOrderConfig(),
            Side.SOUTH: PinOrderConfig(),
            Side.WEST: PinOrderConfig(),
        }

        # No BELs
        tile.bels = []

        return tile

    def test_serialize_tile_ports_basic(self, mock_tile: Tile) -> None:
        """Test basic tile port serialization."""
        result = _serialize_tile_ports(mock_tile)

        # Should have all four sides
        assert "NORTH" in result
        assert "EAST" in result
        assert "SOUTH" in result
        assert "WEST" in result

    def test_serialize_tile_ports_north_includes_clock_and_strobe(
        self, mock_tile: Tile
    ) -> None:
        """Test that north side includes UserCLKo and FrameStrobe_O."""
        result = _serialize_tile_ports(mock_tile)

        # North should have port + UserCLKo + FrameStrobe_O
        assert len(result["NORTH"]) >= 3

        # Check for expected pins in the config
        pin_lists = [config["pins"] for config in result["NORTH"]]
        all_pins = [pin for pins in pin_lists for pin in pins]

        assert "UserCLKo" in all_pins or any("UserCLKo" in str(p) for p in all_pins)

    def test_serialize_tile_ports_south_includes_clock_and_strobe(
        self, mock_tile: Tile
    ) -> None:
        """Test that south side includes UserCLK and FrameStrobe."""
        result = _serialize_tile_ports(mock_tile)

        # South should have port + UserCLK + FrameStrobe
        assert len(result["SOUTH"]) >= 3

        pin_lists = [config["pins"] for config in result["SOUTH"]]
        all_pins = [pin for pins in pin_lists for pin in pins]

        assert "UserCLK" in all_pins or any("UserCLK" in str(p) for p in all_pins)

    def test_serialize_tile_ports_east_includes_frame_data_o(
        self, mock_tile: Tile
    ) -> None:
        """Test that east side includes FrameData_O."""
        result = _serialize_tile_ports(mock_tile)

        # East should have port + FrameData_O
        assert len(result["EAST"]) >= 2

    def test_serialize_tile_ports_west_includes_frame_data(
        self, mock_tile: Tile
    ) -> None:
        """Test that west side includes FrameData."""
        result = _serialize_tile_ports(mock_tile)

        # West should have port + FrameData
        assert len(result["WEST"]) >= 2

    def test_serialize_tile_ports_with_prefix(self, mock_tile: Tile) -> None:
        """Test serialization with a prefix."""
        result = _serialize_tile_ports(mock_tile, prefix="Tile_X0Y0_")

        # Verify prefix is applied
        pin_lists = [config["pins"] for config in result["NORTH"]]
        all_pins = [pin for pins in pin_lists for pin in pins]

        assert any("Tile_X0Y0_" in str(p) for p in all_pins)

    def test_serialize_tile_ports_with_bels(self, mocker: MockerFixture) -> None:
        """Test serialization with BEL external ports."""
        tile = mocker.MagicMock()

        # Empty side ports
        tile.get_port_on_side.return_value = []

        tile.pin_order_config = {
            Side.NORTH: PinOrderConfig(),
            Side.EAST: PinOrderConfig(),
            Side.SOUTH: PinOrderConfig(),
            Side.WEST: PinOrderConfig(),
        }

        # BEL with external ports
        bel = mocker.MagicMock()
        bel.external_input = ["ext_in"]
        bel.external_output = ["ext_out"]
        tile.bels = [bel]

        result = _serialize_tile_ports(tile, external_port_side=Side.SOUTH)

        # Check that BEL ports are on the south side
        south_configs = result["SOUTH"]
        pin_lists = [config["pins"] for config in south_configs]
        all_pins = [pin for pins in pin_lists for pin in pins]

        assert "ext_in" in all_pins
        assert "ext_out" in all_pins

    def test_serialize_tile_ports_empty_port_regex(self, mock_tile: Tile) -> None:
        """Test handling of ports that return empty regex."""
        # Make one port return empty regex
        mock_tile.get_port_on_side(Side.NORTH)[0].get_port_regex.return_value = ""

        result = _serialize_tile_ports(mock_tile)

        # Should still work without errors
        assert "NORTH" in result


class TestSerializeSupertilePorts:
    """Tests for _serialize_supertile_ports function."""

    @pytest.fixture
    def mock_supertile(self, mocker: MockerFixture) -> Tile:
        """Create a mock composite tile for testing."""
        supertile = mocker.MagicMock(spec=Tile)
        supertile.is_composite = True
        supertile.bels = []

        # Create a mock tile for the tilemap
        mock_tile = mocker.MagicMock()
        mock_tile.pin_order_config = {
            Side.NORTH: PinOrderConfig(),
            Side.EAST: PinOrderConfig(),
            Side.SOUTH: PinOrderConfig(),
            Side.WEST: PinOrderConfig(),
        }
        mock_tile.bels = []

        # 2x2 supertile
        supertile.tile_map = [
            [mock_tile, mock_tile],
            [mock_tile, mock_tile],
        ]

        # Mock port with side information
        north_port = mocker.MagicMock()
        north_port.side_of_tile = Side.NORTH
        north_port.get_port_regex.return_value = r"N\[\d+\]"

        south_port = mocker.MagicMock()
        south_port.side_of_tile = Side.SOUTH
        south_port.get_port_regex.return_value = r"S\[\d+\]"

        # Return ports around tile
        supertile.get_ports_around_tile.return_value = {
            "0,0": [[south_port]],
            "1,1": [[north_port]],
        }

        return supertile

    def test_serialize_supertile_ports_basic(self, mock_supertile: Tile) -> None:
        """Test basic supertile port serialization."""
        result = _serialize_supertile_ports(mock_supertile)

        # Should have keys for tiles with ports
        assert "X0Y0" in result or "X1Y1" in result

    def test_serialize_supertile_ports_empty_port_lists(
        self, mocker: MockerFixture
    ) -> None:
        """Test handling of empty port lists."""
        supertile = mocker.MagicMock()
        supertile.bels = []
        supertile.get_ports_around_tile.return_value = {}

        result = _serialize_supertile_ports(supertile)

        assert result == {}

    def test_serialize_supertile_ports_with_prefix(self, mock_supertile: Tile) -> None:
        """Test supertile serialization with prefix."""
        result = _serialize_supertile_ports(mock_supertile, prefix="Test_")

        # Result should contain tile coordinates
        assert isinstance(result, dict)

    def test_frame_signals_on_perimeter_sides_without_routing_ports(
        self, mocker: MockerFixture
    ) -> None:
        """Frame-chain signals must appear on every perimeter side even when that
        side carries no routing wires.

        Regression: W2_IO is a 1-wide 2-tall supertile where NORTH/WEST of the
        top tile and SOUTH/WEST of the bottom tile have no routing ports.  The
        old code only emitted frame signals inside the routing-port loop, so
        those sides were silently omitted from the YAML, causing the GDS flow
        to fail with "not found in config but found in design" errors.
        """
        supertile = mocker.MagicMock(spec=Tile)
        supertile.is_composite = True
        supertile.bels = []

        def _tile() -> Tile:
            t = mocker.MagicMock()
            t.pin_order_config = {s: PinOrderConfig() for s in Side}
            return t

        tile_top = _tile()
        tile_bot = _tile()
        # 1-wide, 2-tall layout — tile_top above tile_bot
        supertile.tile_map = [[tile_top], [tile_bot]]

        # tile_top (0,0): only EAST has routing ports; NORTH and WEST do not
        east_port_top = mocker.MagicMock()
        east_port_top.side_of_tile = Side.EAST
        east_port_top.get_port_regex.return_value = r"Tile_X0Y0_E1BEG\[\d+\]"

        # tile_bot (0,1): only EAST has routing ports; SOUTH and WEST do not
        east_port_bot = mocker.MagicMock()
        east_port_bot.side_of_tile = Side.EAST
        east_port_bot.get_port_regex.return_value = r"Tile_X0Y1_E1BEG\[\d+\]"

        # get_ports_around_tile() mirrors the real function:
        #   tile_top (0,0) perimeter: NORTH, EAST, WEST  (SOUTH is interior)
        #   tile_bot (0,1) perimeter: EAST, SOUTH, WEST  (NORTH is interior)
        # Empty lists represent perimeter sides with no routing ports.
        supertile.get_ports_around_tile.return_value = {
            "0,0": [[], [east_port_top], []],  # NORTH=[], EAST=[port], WEST=[]
            "0,1": [[east_port_bot], [], []],  # EAST=[port], SOUTH=[], WEST=[]
        }

        result = _serialize_supertile_ports(supertile)

        def pins_for(tile_key: str, side: str) -> list[str]:
            return [p for entry in result[tile_key][side] for p in entry["pins"]]

        # ── tile_top (X0Y0) ──────────────────────────────────────────────────
        # EAST: routing port present + FrameData_O
        east_top = pins_for("X0Y0", "EAST")
        assert any(r"E1BEG" in p for p in east_top), "routing port missing from EAST"
        assert any("FrameData_O" in p for p in east_top), (
            "FrameData_O missing from EAST"
        )

        # NORTH: no routing port, but FrameStrobe_O must still be present
        north_top = pins_for("X0Y0", "NORTH")
        assert any("FrameStrobe_O" in p for p in north_top), (
            "FrameStrobe_O missing from NORTH of top tile (no routing ports there)"
        )

        # WEST: no routing port, but FrameData must still be present
        west_top = pins_for("X0Y0", "WEST")
        assert any("FrameData" in p and "FrameData_O" not in p for p in west_top), (
            "FrameData missing from WEST of top tile (no routing ports there)"
        )

        # ── tile_bot (X0Y1) ──────────────────────────────────────────────────
        east_bot = pins_for("X0Y1", "EAST")
        assert any("FrameData_O" in p for p in east_bot), (
            "FrameData_O missing from EAST"
        )

        # SOUTH: no routing port, but FrameStrobe must still be present
        south_bot = pins_for("X0Y1", "SOUTH")
        assert any(
            "FrameStrobe" in p and "FrameStrobe_O" not in p for p in south_bot
        ), "FrameStrobe missing from SOUTH of bottom tile (no routing ports there)"

        # WEST: no routing port, but FrameData must still be present
        west_bot = pins_for("X0Y1", "WEST")
        assert any("FrameData" in p and "FrameData_O" not in p for p in west_bot), (
            "FrameData missing from WEST of bottom tile (no routing ports there)"
        )

        # ── interior sides must not carry frame signals ───────────────────────
        # tile_top SOUTH and tile_bot NORTH are shared interior sides
        south_top = pins_for("X0Y0", "SOUTH")
        assert not any("Frame" in p for p in south_top), (
            "interior SOUTH of top tile must not have frame signals"
        )
        north_bot = pins_for("X0Y1", "NORTH")
        assert not any("Frame" in p for p in north_bot), (
            "interior NORTH of bottom tile must not have frame signals"
        )

    def test_serialize_supertile_ports_none_tile(self, mocker: MockerFixture) -> None:
        """Test handling when tile_map has None entries."""
        supertile = mocker.MagicMock()
        supertile.bels = []

        # TileMap with None
        supertile.tile_map = [[None]]

        port = mocker.MagicMock()
        port.side_of_tile = Side.SOUTH
        port.get_port_regex.return_value = r"S\[\d+\]"

        supertile.get_ports_around_tile.return_value = {
            "0,0": [[port]],
        }

        result = _serialize_supertile_ports(supertile)

        # Should handle None tile gracefully
        if "X0Y0" in result:
            assert all(not config for config in result["X0Y0"].values())


class TestGenerateIOPinOrderConfig:
    """Tests for generate_IO_pin_order_config function."""

    @pytest.fixture
    def mock_fabric(self, mocker: MockerFixture) -> Fabric:
        """Create a mock fabric for testing."""
        fabric = mocker.MagicMock(spec=Fabric)
        fabric.find_tile_positions.return_value = [(0, 0)]
        fabric.determine_border_side.return_value = Side.SOUTH
        return fabric

    @pytest.fixture
    def mock_tile(self, mocker: MockerFixture) -> Tile:
        """Create a mock tile for testing."""
        tile = mocker.MagicMock(spec=Tile)
        tile.is_composite = False

        # Empty side ports for simplicity
        tile.get_port_on_side.return_value = []

        tile.pin_order_config = {
            Side.NORTH: PinOrderConfig(),
            Side.EAST: PinOrderConfig(),
            Side.SOUTH: PinOrderConfig(),
            Side.WEST: PinOrderConfig(),
        }

        tile.bels = []

        return tile

    def test_generate_io_pin_order_config_writes_yaml(
        self, mock_tile: Tile, tmp_path: Path
    ) -> None:
        """Test that config is written to YAML file."""
        outfile = tmp_path / "test_config.yaml"

        generate_IO_pin_order_config(mock_tile, outfile)

        assert outfile.exists()

        # Verify YAML can be loaded
        with outfile.open() as f:
            config = yaml.safe_load(f)

        assert "X0Y0" in config

    def test_generate_io_pin_order_config_tile_structure(
        self, mock_tile: Tile, tmp_path: Path
    ) -> None:
        """Test structure of generated config for a tile."""
        outfile = tmp_path / "test_config.yaml"

        generate_IO_pin_order_config(mock_tile, outfile)

        with outfile.open() as f:
            config = yaml.safe_load(f)

        # Should have X0Y0 with all four sides
        assert "NORTH" in config["X0Y0"]
        assert "EAST" in config["X0Y0"]
        assert "SOUTH" in config["X0Y0"]
        assert "WEST" in config["X0Y0"]

    def test_generate_io_pin_order_config_with_prefix(
        self, mock_tile: Tile, tmp_path: Path
    ) -> None:
        """Test generation with prefix."""
        outfile = tmp_path / "test_config.yaml"

        generate_IO_pin_order_config(mock_tile, outfile, prefix="Pre_")

        with outfile.open() as f:
            config = yaml.safe_load(f)

        # Config should be generated (specific prefix validation would need
        # more detailed mock setup)
        assert config is not None

    def test_generate_io_pin_order_config_supertile(
        self, mocker: MockerFixture, tmp_path: Path
    ) -> None:
        """Test generation for a composite tile."""
        # Create mock composite tile
        mock_supertile = mocker.MagicMock(spec=Tile)
        mock_supertile.is_composite = True
        mock_supertile.bels = []

        # Simple tilemap
        mock_tile = mocker.MagicMock(spec=Tile)
        mock_tile.pin_order_config = {
            Side.NORTH: PinOrderConfig(),
            Side.EAST: PinOrderConfig(),
            Side.SOUTH: PinOrderConfig(),
            Side.WEST: PinOrderConfig(),
        }
        mock_tile.bels = []

        mock_supertile.tile_map = [[mock_tile]]
        mock_supertile.get_ports_around_tile.return_value = {}

        outfile = tmp_path / "test_supertile_config.yaml"

        generate_IO_pin_order_config(mock_supertile, outfile)

        assert outfile.exists()

    def test_generate_io_pin_order_config_defaults_external_side_to_south(
        self, mock_tile: Tile, mocker: MockerFixture, tmp_path: Path
    ) -> None:
        """Test generation uses SOUTH for external ports by default."""
        bel = mocker.MagicMock()
        bel.external_input = ["ext_in"]
        bel.external_output = []
        mock_tile.bels = [bel]

        outfile = tmp_path / "test_config.yaml"

        generate_IO_pin_order_config(mock_tile, outfile)

        with outfile.open() as f:
            config = yaml.safe_load(f)

        south_configs = config["X0Y0"]["SOUTH"]
        pin_lists = [c["pins"] for c in south_configs]
        all_pins = [pin for pins in pin_lists for pin in pins]

        assert "ext_in" in all_pins

    def test_generate_io_pin_order_config_without_fabric_uses_external_side(
        self, mock_tile: Tile, mocker: MockerFixture, tmp_path: Path
    ) -> None:
        """Test generation without fabric placement context."""
        bel = mocker.MagicMock()
        bel.external_input = ["ext_in"]
        bel.external_output = []
        mock_tile.bels = [bel]

        outfile = tmp_path / "test_config.yaml"

        generate_IO_pin_order_config(
            mock_tile,
            outfile,
            external_port_side=Side.EAST,
        )

        with outfile.open() as f:
            config = yaml.safe_load(f)

        east_configs = config["X0Y0"]["EAST"]
        pin_lists = [c["pins"] for c in east_configs]
        all_pins = [pin for pins in pin_lists for pin in pins]

        assert "ext_in" in all_pins

    def test_generate_io_pin_order_config_external_side_handling(
        self,
        mock_tile: Tile,
        mocker: MockerFixture,
        tmp_path: Path,
    ) -> None:
        """Test that explicit external side is used for external ports."""
        bel = mocker.MagicMock()
        bel.external_input = ["ext_in"]
        bel.external_output = []
        mock_tile.bels = [bel]

        outfile = tmp_path / "test_config.yaml"

        generate_IO_pin_order_config(
            mock_tile,
            outfile,
            external_port_side=Side.EAST,
        )

        with outfile.open() as f:
            config = yaml.safe_load(f)

        # External ports should be on EAST side
        east_configs = config["X0Y0"]["EAST"]
        pin_lists = [c["pins"] for c in east_configs]
        all_pins = [pin for pins in pin_lists for pin in pins]

        assert "ext_in" in all_pins

    def test_generate_io_pin_order_config_supertile_uses_fabric_border_side(
        self, mocker: MockerFixture, tmp_path: Path
    ) -> None:
        """Composite subtile sides come from fabric placement when given."""
        mock_supertile = mocker.MagicMock(spec=Tile)
        mock_supertile.is_composite = True
        mock_supertile.bels = []

        mock_tile = mocker.MagicMock(spec=Tile)
        mock_tile.pin_order_config = {
            Side.NORTH: PinOrderConfig(),
            Side.EAST: PinOrderConfig(),
            Side.SOUTH: PinOrderConfig(),
            Side.WEST: PinOrderConfig(),
        }
        bel = mocker.MagicMock()
        bel.external_input = ["ext_in"]
        bel.external_output = []
        mock_tile.bels = [bel]

        mock_supertile.tile_map = [[mock_tile]]
        mock_supertile.get_ports_around_tile.return_value = {"0,0": [[]]}

        mock_fabric = mocker.MagicMock(spec=Fabric)
        mock_fabric.find_tile_positions.return_value = [(2, 0)]
        mock_fabric.determine_border_side.return_value = Side.EAST

        outfile = tmp_path / "test_config.yaml"

        generate_IO_pin_order_config(
            mock_supertile,
            outfile,
            fabric=mock_fabric,
        )

        with outfile.open() as f:
            config = yaml.safe_load(f)

        east_configs = config["X0Y0"]["EAST"]
        pin_lists = [c["pins"] for c in east_configs]
        all_pins = [pin for pins in pin_lists for pin in pins]

        assert "ext_in" in all_pins

    def test_generate_io_pin_order_config_multirow_maps_subtile_to_fabric_y(
        self, mocker: MockerFixture, tmp_path: Path
    ) -> None:
        """Each sub-tile's border side must come from its true fabric cell.

        ``tile_map`` is stored top-first (row 0 is north) while the fabric grid is
        bottom-first (y=0 is south). For a 1-wide, 2-tall composite placed with
        bottom-left origin ``(1, 0)`` the top sub-tile (``st_y=0``) physically
        sits at fabric ``y=1`` (NORTH border) and the bottom sub-tile
        (``st_y=1``) at fabric ``y=0`` (SOUTH border). Its BEL external port must
        therefore land on NORTH for the top tile and SOUTH for the bottom tile.

        The old code added the top-first ``st_y`` directly to ``base_y``, so the
        top sub-tile queried fabric ``y=0`` (SOUTH) and the bottom one ``y=1``
        (NORTH) — i.e. the two sub-tiles received each other's border side.
        """

        def _subtile(ext_name: str) -> Tile:
            t = mocker.MagicMock(spec=Tile)
            t.pin_order_config = {s: PinOrderConfig() for s in Side}
            bel = mocker.MagicMock()
            bel.external_input = [ext_name]
            bel.external_output = []
            t.bels = [bel]
            return t

        tile_top = _subtile("top_ext")
        tile_bot = _subtile("bot_ext")

        mock_supertile = mocker.MagicMock(spec=Tile)
        mock_supertile.is_composite = True
        mock_supertile.bels = []
        # 1-wide, 2-tall: tile_map[0] is the north (top) row.
        mock_supertile.tile_map = [[tile_top], [tile_bot]]
        mock_supertile.max_height = 2

        def _ports_around() -> dict:
            return {"0,0": [[]], "0,1": [[]]}

        mock_supertile.get_ports_around_tile.side_effect = _ports_around

        mock_fabric = mocker.MagicMock(spec=Fabric)
        # Covered cells are bottom-first; min() over them gives base (1, 0).
        mock_fabric.find_tile_positions.return_value = [(1, 0), (1, 1)]

        def _border(_x: int, y: int) -> Side:
            # y=1 is the north border, y=0 is the south border.
            return Side.NORTH if y == 1 else Side.SOUTH

        mock_fabric.determine_border_side.side_effect = _border

        outfile = tmp_path / "test_config.yaml"

        generate_IO_pin_order_config(
            mock_supertile,
            outfile,
            fabric=mock_fabric,
        )

        with outfile.open() as f:
            config = yaml.safe_load(f)

        def pins_for(tile_key: str, side: str) -> list[str]:
            return [p for entry in config[tile_key][side] for p in entry["pins"]]

        # Top sub-tile (X0Y0) physically borders NORTH -> its external port there.
        assert "top_ext" in pins_for("X0Y0", "NORTH"), (
            "top sub-tile external port must land on its true (NORTH) border"
        )
        assert "top_ext" not in pins_for("X0Y0", "SOUTH"), (
            "top sub-tile must not be assigned the bottom tile's SOUTH border"
        )
        # Bottom sub-tile (X0Y1) physically borders SOUTH.
        assert "bot_ext" in pins_for("X0Y1", "SOUTH"), (
            "bottom sub-tile external port must land on its true (SOUTH) border"
        )
        assert "bot_ext" not in pins_for("X0Y1", "NORTH"), (
            "bottom sub-tile must not be assigned the top tile's NORTH border"
        )

    def test_generate_io_pin_order_config_supertile_without_fabric(
        self, mocker: MockerFixture, tmp_path: Path
    ) -> None:
        """Test composite tile generation without fabric placement context."""
        mock_supertile = mocker.MagicMock(spec=Tile)
        mock_supertile.is_composite = True
        mock_supertile.bels = []

        mock_tile = mocker.MagicMock(spec=Tile)
        mock_tile.pin_order_config = {
            Side.NORTH: PinOrderConfig(),
            Side.EAST: PinOrderConfig(),
            Side.SOUTH: PinOrderConfig(),
            Side.WEST: PinOrderConfig(),
        }
        bel = mocker.MagicMock()
        bel.external_input = ["ext_in"]
        bel.external_output = []
        mock_tile.bels = [bel]

        mock_supertile.tile_map = [[mock_tile]]
        mock_supertile.get_ports_around_tile.return_value = {"0,0": [[]]}

        outfile = tmp_path / "test_config.yaml"

        generate_IO_pin_order_config(
            mock_supertile,
            outfile,
            external_port_side=Side.EAST,
        )

        with outfile.open() as f:
            config = yaml.safe_load(f)

        east_configs = config["X0Y0"]["EAST"]
        pin_lists = [c["pins"] for c in east_configs]
        all_pins = [pin for pins in pin_lists for pin in pins]

        assert "ext_in" in all_pins


class TestPinOrderConfigIntegration:
    """Integration tests for PinOrderConfig with serialization."""

    def test_config_serialization_round_trip(self) -> None:
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

    def test_multiple_configs_same_side(self) -> None:
        """Test multiple configs can be created for the same side."""
        config1 = PinOrderConfig()([r"Signal1\[\d+\]"])
        config2 = PinOrderConfig()([r"Signal2\[\d+\]"])

        configs = [config1.to_dict(), config2.to_dict()]

        assert len(configs) == 2
        assert configs[0]["pins"] == [r"Signal1\[\d+\]"]
        assert configs[1]["pins"] == [r"Signal2\[\d+\]"]

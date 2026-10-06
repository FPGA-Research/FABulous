"""Tests for gen_io_pin_config_yaml module - IO pin configuration generation.

Tests focus on:
- PinOrderConfig serialisation
- Tile port serialization
- SuperTile port serialization
- IO pin configuration generation
"""

from pathlib import Path

import pytest
import yaml
from pytest_mock import MockerFixture

from fabulous.fabric_definition.define import IO, PinSortMode, Side
from fabulous.fabric_definition.fabric import Fabric
from fabulous.fabric_definition.port import TilePort
from fabulous.fabric_definition.supertile import SuperTile
from fabulous.fabric_definition.tile import Tile
from fabulous.fabric_generator.gds_generator.gen_io_pin_config_yaml import (
    PinOrderConfig,
    _serialize_supertile_ports,
    _serialize_tile_ports,
    generate_IO_pin_order_config,
)
from tests.conftest import make_empty_tile


def _port(name: str, side: Side, wire_count: int = 4) -> TilePort:
    """A real routing port; one wire gives a bare name, more an indexed regex."""
    horizontal = side in (Side.EAST, Side.WEST)
    return TilePort(
        name=name,
        io_direction=IO.OUTPUT,
        width=wire_count,
        side_of_tile=side,
        x_offset=1 if horizontal else 0,
        y_offset=0 if horizontal else 1,
        wire_count=wire_count,
    )


def _pins_by_side(
    port_dict: dict[str, list[dict]],
) -> dict[str, list[list[str | int]]]:
    """Reduce a serialised side mapping to the pin lists of its entries."""
    return {
        side: [entry["pins"] for entry in entries]
        for side, entries in port_dict.items()
    }


class TestPinOrderConfig:
    """Tests for PinOrderConfig."""

    def test_call_binds_pins(self) -> None:
        """Test that __call__ binds pins to the config."""
        config = PinOrderConfig(min_distance=5)
        result = config(["a", "b", "c"])

        assert result is config
        assert config.pins == ["a", "b", "c"]

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
    """Tests for _serialize_tile_ports function on a real tile."""

    @pytest.fixture
    def tile(self) -> Tile:
        """A tile with one routing port per side; the WEST one is a single wire."""
        return make_empty_tile(
            "T",
            ports=[
                _port("N2BEG", Side.NORTH),
                _port("E2BEG", Side.EAST),
                _port("S2BEG", Side.SOUTH),
                _port("W1BEG", Side.WEST, wire_count=1),
            ],
            pinOrderConfig={side: PinOrderConfig() for side in Side},
        )

    @pytest.mark.parametrize(
        ("user_clk_side", "prefix", "expected_pins"),
        [
            pytest.param(
                Side.SOUTH,
                "",
                {
                    "NORTH": [
                        [r"N2BEG\[\d+\]"],
                        ["UserCLKo"],
                        [r"FrameStrobe_O\[\d+\]"],
                    ],
                    "EAST": [[r"E2BEG\[\d+\]"], [r"FrameData_O\[\d+\]"]],
                    "SOUTH": [[r"S2BEG\[\d+\]"], ["UserCLK"], [r"FrameStrobe\[\d+\]"]],
                    "WEST": [["W1BEG"], [r"FrameData\[\d+\]"]],
                },
                id="clock_south",
            ),
            pytest.param(
                Side.WEST,
                "",
                {
                    "NORTH": [[r"N2BEG\[\d+\]"], [r"FrameStrobe_O\[\d+\]"]],
                    "EAST": [
                        [r"E2BEG\[\d+\]"],
                        ["UserCLKo"],
                        [r"FrameData_O\[\d+\]"],
                    ],
                    "SOUTH": [[r"S2BEG\[\d+\]"], [r"FrameStrobe\[\d+\]"]],
                    "WEST": [["W1BEG"], ["UserCLK"], [r"FrameData\[\d+\]"]],
                },
                id="clock_west",
            ),
            pytest.param(
                Side.SOUTH,
                "Tile_X0Y0_",
                {
                    "NORTH": [
                        [r"Tile_X0Y0_N2BEG\[\d+\]"],
                        ["Tile_X0Y0_UserCLKo"],
                        [r"Tile_X0Y0_FrameStrobe_O\[\d+\]"],
                    ],
                    "EAST": [
                        [r"Tile_X0Y0_E2BEG\[\d+\]"],
                        [r"Tile_X0Y0_FrameData_O\[\d+\]"],
                    ],
                    "SOUTH": [
                        [r"Tile_X0Y0_S2BEG\[\d+\]"],
                        ["Tile_X0Y0_UserCLK"],
                        [r"Tile_X0Y0_FrameStrobe\[\d+\]"],
                    ],
                    "WEST": [["Tile_X0Y0_W1BEG"], [r"Tile_X0Y0_FrameData\[\d+\]"]],
                },
                id="prefixed",
            ),
        ],
    )
    def test_serialize_tile_ports_appends_clock_and_frame_signals(
        self,
        tile: Tile,
        user_clk_side: Side,
        prefix: str,
        expected_pins: dict[str, list[list[str]]],
    ) -> None:
        """UserCLK enters on `user_clk_side` and UserCLKo leaves opposite it.

        Routing ports come first on their side; the prefix reaches every pin.
        """
        result = _serialize_tile_ports(tile, prefix=prefix, user_clk_side=user_clk_side)

        assert _pins_by_side(result) == expected_pins

    def test_serialize_tile_ports_with_bels(
        self, tile: Tile, mocker: MockerFixture
    ) -> None:
        """A BEL's external inputs and outputs form one prefixed entry on its side."""
        tile.bels = [
            mocker.MagicMock(externalInput=["ext_in"], externalOutput=["ext_out"])
        ]

        result = _serialize_tile_ports(tile, prefix="P_", external_port_side=Side.EAST)

        assert _pins_by_side(result)["EAST"] == [
            [r"P_E2BEG\[\d+\]"],
            [r"P_FrameData_O\[\d+\]"],
            ["P_ext_in", "P_ext_out"],
        ]

    def test_serialize_tile_ports_empty_port_regex(self, mocker: MockerFixture) -> None:
        """A port with an empty regex is dropped, the frame signals stay."""
        tile = mocker.MagicMock(spec=Tile)
        empty_port = mocker.MagicMock()
        empty_port.get_port_regex.return_value = ""
        east_port = mocker.MagicMock()
        east_port.get_port_regex.return_value = r"E2BEG\[\d+\]"
        tile.getNorthSidePorts.return_value = [empty_port]
        tile.getEastSidePorts.return_value = [east_port]
        tile.getSouthSidePorts.return_value = []
        tile.getWestSidePorts.return_value = []
        tile.pinOrderConfig = {side: PinOrderConfig() for side in Side}
        tile.bels = []

        result = _serialize_tile_ports(tile)

        # Sides whose port still has a regex are unaffected.
        assert _pins_by_side(result) == {
            "NORTH": [["UserCLKo"], [r"FrameStrobe_O\[\d+\]"]],
            "EAST": [[r"E2BEG\[\d+\]"], [r"FrameData_O\[\d+\]"]],
            "SOUTH": [["UserCLK"], [r"FrameStrobe\[\d+\]"]],
            "WEST": [[r"FrameData\[\d+\]"]],
        }


def _subtile(mocker: MockerFixture) -> Tile:
    """A sub-tile stand-in carrying only what supertile serialisation reads."""
    return mocker.MagicMock(pinOrderConfig={s: PinOrderConfig() for s in Side}, bels=[])


class TestSerializeSupertilePorts:
    """Tests for _serialize_supertile_ports function."""

    @pytest.fixture
    def mock_supertile(self, mocker: MockerFixture) -> SuperTile:
        """A 2x2 supertile with a SOUTH port on X0Y0 and a NORTH port on X1Y1.

        X0Y0 has NORTH and WEST on the perimeter, X1Y1 has EAST and SOUTH.
        """
        supertile = mocker.MagicMock(spec=SuperTile)
        supertile.bels = []
        tile = _subtile(mocker)
        supertile.tileMap = [[tile, tile], [tile, tile]]
        supertile.get_ports_around_tile.return_value = {
            "0,0": [[_port("S2BEG", Side.SOUTH)]],
            "1,1": [[_port("N2BEG", Side.NORTH)]],
        }
        return supertile

    @pytest.mark.parametrize("prefix", ["", "Test_"])
    def test_serialize_supertile_ports(
        self, mock_supertile: SuperTile, prefix: str
    ) -> None:
        """Each sub-tile carries its routing ports plus its perimeter clock and
        frame pins, all prefixed with `Tile_X<x>Y<y>_` and then `prefix`."""
        p0 = f"Tile_X0Y0_{prefix}"
        p1 = f"Tile_X1Y1_{prefix}"

        result = _serialize_supertile_ports(mock_supertile, prefix=prefix)

        assert {key: _pins_by_side(sides) for key, sides in result.items()} == {
            "X0Y0": {
                "NORTH": [[f"{p0}UserCLKo"], [rf"{p0}FrameStrobe_O\[\d+\]"]],
                "EAST": [],
                "SOUTH": [[rf"{p0}S2BEG\[\d+\]"]],
                "WEST": [[rf"{p0}FrameData\[\d+\]"]],
            },
            "X1Y1": {
                "NORTH": [[rf"{p1}N2BEG\[\d+\]"]],
                "EAST": [[rf"{p1}FrameData_O\[\d+\]"]],
                "SOUTH": [[f"{p1}UserCLK"], [rf"{p1}FrameStrobe\[\d+\]"]],
                "WEST": [],
            },
        }

    def test_serialize_supertile_ports_empty_port_lists(
        self, mocker: MockerFixture
    ) -> None:
        """Test handling of empty port lists."""
        supertile = mocker.MagicMock()
        supertile.bels = []
        supertile.get_ports_around_tile.return_value = {}

        result = _serialize_supertile_ports(supertile)

        assert result == {}

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
        supertile = mocker.MagicMock(spec=SuperTile)
        supertile.bels = []
        # 1-wide, 2-tall layout: X0Y0 above X0Y1.
        supertile.tileMap = [[_subtile(mocker)], [_subtile(mocker)]]
        # get_ports_around_tile() mirrors the real function: one list per
        # perimeter side, empty where the side has no routing ports.
        #   X0Y0 perimeter: NORTH, EAST, WEST  (SOUTH is interior)
        #   X0Y1 perimeter: EAST, SOUTH, WEST  (NORTH is interior)
        supertile.get_ports_around_tile.return_value = {
            "0,0": [[], [_port("E1BEG", Side.EAST)], []],
            "0,1": [[_port("E1BEG", Side.EAST)], [], []],
        }

        result = _serialize_supertile_ports(supertile)

        assert {key: _pins_by_side(sides) for key, sides in result.items()} == {
            "X0Y0": {
                "NORTH": [["Tile_X0Y0_UserCLKo"], [r"Tile_X0Y0_FrameStrobe_O\[\d+\]"]],
                "EAST": [
                    [r"Tile_X0Y0_E1BEG\[\d+\]"],
                    [r"Tile_X0Y0_FrameData_O\[\d+\]"],
                ],
                "SOUTH": [],
                "WEST": [[r"Tile_X0Y0_FrameData\[\d+\]"]],
            },
            "X0Y1": {
                "NORTH": [],
                "EAST": [
                    [r"Tile_X0Y1_E1BEG\[\d+\]"],
                    [r"Tile_X0Y1_FrameData_O\[\d+\]"],
                ],
                "SOUTH": [["Tile_X0Y1_UserCLK"], [r"Tile_X0Y1_FrameStrobe\[\d+\]"]],
                "WEST": [[r"Tile_X0Y1_FrameData\[\d+\]"]],
            },
        }

    def test_serialize_supertile_ports_none_tile(self, mocker: MockerFixture) -> None:
        """Test handling when tileMap has None entries."""
        supertile = mocker.MagicMock()
        supertile.bels = []

        # TileMap with None
        supertile.tileMap = [[None]]

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


def _load_pins(outfile: Path) -> dict[str, dict[str, list[list[str]]]]:
    """Load a generated pin-order YAML reduced to pin lists per side."""
    config = yaml.safe_load(outfile.read_text())
    return {key: _pins_by_side(sides) for key, sides in config.items()}


class TestGenerateIOPinOrderConfig:
    """Tests for generate_IO_pin_order_config function."""

    @pytest.fixture
    def tile(self) -> Tile:
        """A real tile without routing ports or BELs."""
        return make_empty_tile(
            "T", pinOrderConfig={side: PinOrderConfig() for side in Side}
        )

    def test_generate_io_pin_order_config_tile_structure(
        self, tile: Tile, tmp_path: Path
    ) -> None:
        """Test structure of generated config for a tile."""
        outfile = tmp_path / "test_config.yaml"

        generate_IO_pin_order_config(tile, outfile)

        # The tile has no routing ports and no BELs, so only the clock and
        # frame-chain signals are emitted, one side each.
        assert _load_pins(outfile) == {
            "X0Y0": {
                "NORTH": [["UserCLKo"], [r"FrameStrobe_O\[\d+\]"]],
                "EAST": [[r"FrameData_O\[\d+\]"]],
                "SOUTH": [["UserCLK"], [r"FrameStrobe\[\d+\]"]],
                "WEST": [[r"FrameData\[\d+\]"]],
            }
        }

    def test_generate_io_pin_order_config_with_prefix(
        self, tile: Tile, tmp_path: Path
    ) -> None:
        """Test generation with prefix."""
        outfile = tmp_path / "test_config.yaml"

        generate_IO_pin_order_config(tile, outfile, prefix="Pre_")

        assert _load_pins(outfile)["X0Y0"]["NORTH"] == [
            ["Pre_UserCLKo"],
            [r"Pre_FrameStrobe_O\[\d+\]"],
        ]

    @pytest.mark.parametrize(
        ("external_side_kwargs", "ext_side"),
        [
            pytest.param({}, "SOUTH", id="default_south"),
            pytest.param({"external_port_side": Side.EAST}, "EAST", id="explicit_east"),
        ],
    )
    def test_generate_io_pin_order_config_tile_external_side(
        self,
        tile: Tile,
        mocker: MockerFixture,
        tmp_path: Path,
        external_side_kwargs: dict[str, Side],
        ext_side: str,
    ) -> None:
        """BEL external ports land on the requested side only."""
        tile.bels = [mocker.MagicMock(externalInput=["ext_in"], externalOutput=[])]
        outfile = tmp_path / "test_config.yaml"
        expected: dict[str, list[list[str]]] = {
            "NORTH": [["UserCLKo"], [r"FrameStrobe_O\[\d+\]"]],
            "EAST": [[r"FrameData_O\[\d+\]"]],
            "SOUTH": [["UserCLK"], [r"FrameStrobe\[\d+\]"]],
            "WEST": [[r"FrameData\[\d+\]"]],
        }
        expected[ext_side].append(["ext_in"])

        generate_IO_pin_order_config(tile, outfile, **external_side_kwargs)

        assert _load_pins(outfile) == {"X0Y0": expected}

    def test_generate_io_pin_order_config_supertile(
        self, mocker: MockerFixture, tmp_path: Path
    ) -> None:
        """Test generation for a SuperTile."""
        # Create mock supertile
        mock_supertile = mocker.MagicMock(spec=SuperTile)
        mock_supertile.bels = []

        # Simple tilemap
        mock_tile = mocker.MagicMock(spec=Tile)
        mock_tile.pinOrderConfig = {
            Side.NORTH: PinOrderConfig(),
            Side.EAST: PinOrderConfig(),
            Side.SOUTH: PinOrderConfig(),
            Side.WEST: PinOrderConfig(),
        }
        mock_tile.bels = []

        mock_supertile.tileMap = [[mock_tile]]
        mock_supertile.get_ports_around_tile.return_value = {}

        outfile = tmp_path / "test_supertile_config.yaml"

        generate_IO_pin_order_config(mock_supertile, outfile)

        assert outfile.exists()

    def test_generate_io_pin_order_config_supertile_uses_fabric_border_side(
        self, mocker: MockerFixture, tmp_path: Path
    ) -> None:
        """SuperTile subtile sides come from fabric placement when given."""
        mock_supertile = mocker.MagicMock(spec=SuperTile)
        mock_supertile.bels = []

        mock_tile = mocker.MagicMock(spec=Tile)
        mock_tile.pinOrderConfig = {
            Side.NORTH: PinOrderConfig(),
            Side.EAST: PinOrderConfig(),
            Side.SOUTH: PinOrderConfig(),
            Side.WEST: PinOrderConfig(),
        }
        bel = mocker.MagicMock()
        bel.externalInput = ["ext_in"]
        bel.externalOutput = []
        mock_tile.bels = [bel]

        mock_supertile.tileMap = [[mock_tile]]
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

    def test_generate_io_pin_order_config_supertile_without_fabric(
        self, mocker: MockerFixture, tmp_path: Path
    ) -> None:
        """Test SuperTile generation without fabric placement context."""
        mock_supertile = mocker.MagicMock(spec=SuperTile)
        mock_supertile.bels = []

        mock_tile = mocker.MagicMock(spec=Tile)
        mock_tile.pinOrderConfig = {
            Side.NORTH: PinOrderConfig(),
            Side.EAST: PinOrderConfig(),
            Side.SOUTH: PinOrderConfig(),
            Side.WEST: PinOrderConfig(),
        }
        bel = mocker.MagicMock()
        bel.externalInput = ["ext_in"]
        bel.externalOutput = []
        mock_tile.bels = [bel]

        mock_supertile.tileMap = [[mock_tile]]
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

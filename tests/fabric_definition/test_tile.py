"""Tests for Tile methods — notably pin-count and min-die-area computation."""

from decimal import Decimal
from pathlib import Path

import pytest

from fabulous.fabric_definition.bel import Bel
from fabulous.fabric_definition.define import IO, Direction, Side
from fabulous.fabric_definition.port import BelPort, TilePort
from fabulous.fabric_definition.switch_matrix import SwitchMatrix
from fabulous.fabric_definition.tile import Tile
from tests.conftest import make_yosys_module


def _mk_tile(ports: list[TilePort]) -> Tile:
    """Construct a Tile with only ports_info set — enough for get_port_count tests."""
    return Tile(
        name="T",
        ports=ports,
        bels=[],
        tile_dir=Path(),
        matrix_dir=Path(),
        switch_matrix=SwitchMatrix.from_connections(matrix_file=Path(), connections={}),
        gen_ios=[],
        userCLK=False,
    )


def _directional_ports(
    direction: str,
    src: str,
    dst: str,
    wires: int,
    x_offset: int = 0,
    y_offset: int = -1,
) -> list[TilePort]:
    """Mirror parse_port_line: one OUTPUT port on ``side``, one INPUT on opposite."""
    side = Side[direction]
    return [
        TilePort(
            name=src,
            io_direction=IO.OUTPUT,
            width=wires,
            side_of_tile=side,
            wire_direction=Direction[direction],
            source_name=src,
            x_offset=x_offset,
            y_offset=y_offset,
            destination_name=dst,
            wire_count=wires,
        ),
        TilePort(
            name=dst,
            io_direction=IO.INPUT,
            width=wires,
            side_of_tile=side.opposite,
            wire_direction=Direction[direction],
            source_name=src,
            x_offset=x_offset,
            y_offset=y_offset,
            destination_name=dst,
            wire_count=wires,
        ),
    ]


class TestGetPortCount:
    """``get_port_count`` must return physical pin count, not 2× the wire count."""

    def test_single_direction_counts_once_per_wire(self) -> None:
        # One NORTH wire produces N1BEG on N edge and N1END on S edge.
        # Each edge should report exactly wire_count pins, not 2× wire_count.
        tile = _mk_tile(_directional_ports("NORTH", "N1BEG", "N1END", 4))
        assert tile.get_port_count(Side.NORTH) == 4
        assert tile.get_port_count(Side.SOUTH) == 4

    def test_distance_multiplies_wire_count(self) -> None:
        # N4 wire with distance 4 and wire_count=4 expands to 16 physical pins
        # per edge in "all" mode (4 tiles of passthrough × 4 wires).
        tile = _mk_tile(_directional_ports("NORTH", "N4BEG", "N4END", 4, y_offset=-4))
        assert tile.get_port_count(Side.NORTH) == 16
        assert tile.get_port_count(Side.SOUTH) == 16

    def test_opposite_directions_sum_on_shared_edge(self) -> None:
        # A north-going wire (N1BEG on N edge) and a south-going wire
        # (S1END on N edge, received from north neighbor) both contribute
        # physical pins to the N edge.
        ports = _directional_ports("NORTH", "N1BEG", "N1END", 4) + _directional_ports(
            "SOUTH", "S1BEG", "S1END", 4, y_offset=1
        )
        tile = _mk_tile(ports)
        assert tile.get_port_count(Side.NORTH) == 8  # 4 N1BEG + 4 S1END
        assert tile.get_port_count(Side.SOUTH) == 8  # 4 N1END + 4 S1BEG

    def test_null_ports_excluded(self) -> None:
        # GND/VCC-like ports with NULL source count only the non-NULL side.
        port = TilePort(
            name="VCC",
            io_direction=IO.INPUT,
            width=1,
            side_of_tile=Side.ANY,
            wire_direction=Direction.JUMP,
            source_name="NULL",
            x_offset=0,
            y_offset=0,
            destination_name="VCC",
            wire_count=1,
        )
        tile = _mk_tile([port])
        assert tile.get_port_count(Side.ANY) == 1


class TestGetMinDieArea:
    """``get_min_die_area`` derives pin-limited min dimensions from get_port_count."""

    def test_pin_min_reflects_physical_pins_only(self) -> None:
        # Without the double-count bug, 4 wires on N should produce pin_min_w
        # of roughly (4 + frame_strobe_width)·thickness_mult·pitch + offset·pitch.
        ports = _directional_ports("NORTH", "N1BEG", "N1END", 4)
        tile = _mk_tile(ports)
        pitch = Decimal("0.5")
        thickness = Decimal(2)
        mw, _ = tile.get_min_die_area(
            x_pitch=pitch,
            y_pitch=pitch,
            x_pin_thickness_mult=thickness,
            y_pin_thickness_mult=thickness,
            frame_data_width=0,
            frame_strobe_width=0,
            edge_offset=2,
        )
        # 4 pins × 2 thickness + 2 offset = 10 tracks × 0.5 pitch = 5.0 um
        assert mw == Decimal("5.0")


def _tport(name: str, io: IO, side: Side = Side.NORTH) -> TilePort:
    """Build a minimal TilePort for hierarchy/query tests."""
    return TilePort(
        name=name,
        io_direction=io,
        width=1,
        side_of_tile=side,
        source_name=name,
        destination_name=name,
        wire_count=1,
    )


def _simple_tile(
    name: str = "T",
    ports: list[TilePort] | None = None,
    bels: list[Bel] | None = None,
) -> Tile:
    """Build a simple (non-composite) Tile."""
    return Tile(
        name=name,
        ports=ports or [],
        bels=bels or [],
        tile_dir=Path(),
        matrix_dir=Path(),
        gen_ios=[],
        userCLK=False,
        switch_matrix=SwitchMatrix.from_connections(matrix_file=Path(), connections={}),
    )


def _composite_tile(name: str, tileMap: list[list[str | None]]) -> Tile:
    """Build a composite Tile carrying a tileMap."""
    return Tile(
        name=name,
        ports=[],
        bels=[],
        tile_dir=Path(),
        matrix_dir=Path(),
        gen_ios=[],
        userCLK=False,
        switch_matrix=SwitchMatrix.from_connections(matrix_file=Path(), connections={}),
        tileMap=tileMap,
    )


class TestSubTiles:
    """Tests for sub-tile layout queries added by the tile model extension."""

    def test_get_sub_tiles_simple(self) -> None:
        """A simple tile reports itself as its only sub-tile."""
        assert _simple_tile(name="T1").get_sub_tiles() == ["T1"]

    def test_get_sub_tiles_composite(self) -> None:
        """A composite tile flattens non-None tileMap entries."""
        tile = _composite_tile("C", [["T0", "T1"], ["T2", None]])
        assert tile.get_sub_tiles() == ["T0", "T1", "T2"]

    def test_sub_tile_offset_simple_self(self) -> None:
        """A simple tile is at offset (0, 0)."""
        assert _simple_tile(name="M").get_sub_tile_offset("M") == (0, 0)

    def test_sub_tile_offset_simple_missing(self) -> None:
        """Requesting an unknown sub-tile raises."""
        with pytest.raises(ValueError, match="not found in tile"):
            _simple_tile(name="M").get_sub_tile_offset("Other")

    def test_sub_tile_offset_composite(self) -> None:
        """Composite offsets use y=0 at the top row, matching get_master_offset."""
        tile = _composite_tile("C", [["T0", "T1"], ["T2", "T3"]])
        assert tile.get_sub_tile_offset("T0") == (0, 0)
        assert tile.get_sub_tile_offset("T1") == (1, 0)
        assert tile.get_sub_tile_offset("T2") == (0, 1)

    def test_part_of_tile(self) -> None:
        """part_of_tile reflects sub-tile membership."""
        tile = _composite_tile("C", [["T0", "T1"], ["T2", "T3"]])
        assert tile.part_of_tile("T2") is True
        assert tile.part_of_tile("X") is False

    def test_is_root_tile(self) -> None:
        """The bottom-left sub-tile is the root tile."""
        assert _simple_tile(name="M").is_root_tile("M") is True
        tile = _composite_tile("C", [["T0", "T1"], ["T2", "T3"]])
        assert tile.is_root_tile("T2") is True
        assert tile.is_root_tile("T0") is False


class TestPortQueries:
    """Tests for port lookup/filter helpers added by the tile model extension."""

    def test_find_port_by_name(self) -> None:
        """find_port_by_name matches by name and returns None when absent."""
        port = _tport("p", IO.INPUT)
        tile = _simple_tile(ports=[port])
        assert tile.find_port_by_name("p") is port
        assert tile.find_port_by_name("absent") is None

    def test_is_port_in_tile(self) -> None:
        """is_port_in_tile checks membership by port name."""
        port = _tport("p", IO.INPUT)
        tile = _simple_tile(ports=[port])
        assert tile.is_port_in_tile(port) is True
        assert tile.is_port_in_tile(_tport("other", IO.INPUT)) is False

    def test_input_ports_sorted(self) -> None:
        """get_tile_input_ports returns only inputs, sorted by name."""
        tile = _simple_tile(
            ports=[
                _tport("b_in", IO.INPUT),
                _tport("a_in", IO.INPUT),
                _tport("an_out", IO.OUTPUT, Side.SOUTH),
            ]
        )
        names = [p.name for p in tile.get_tile_input_ports()]
        assert names == ["a_in", "b_in"]

    def test_output_ports_sorted(self) -> None:
        """get_tile_output_ports returns only outputs, sorted by name."""
        tile = _simple_tile(
            ports=[
                _tport("z_out", IO.OUTPUT, Side.SOUTH),
                _tport("a_out", IO.OUTPUT, Side.SOUTH),
                _tport("an_in", IO.INPUT),
            ]
        )
        names = [p.name for p in tile.get_tile_output_ports()]
        assert names == ["a_out", "z_out"]

    def test_port_grouped_by_side(self) -> None:
        """get_tile_port_grouped buckets ports by tile side."""
        north = _tport("n", IO.INPUT, Side.NORTH)
        south = _tport("s", IO.OUTPUT, Side.SOUTH)
        tile = _simple_tile(ports=[north, south])
        grouped = tile.get_tile_port_grouped()
        assert north in grouped[Side.NORTH]
        assert south in grouped[Side.SOUTH]


class TestTileProperties:
    """Tests for the new grouping properties and config_bits alias."""

    def test_ports_property_simple(self) -> None:
        """For a simple tile, ports groups everything under the tile name."""
        port = _tport("p", IO.INPUT)
        tile = _simple_tile(name="T1", ports=[port])
        assert tile.ports == {"T1": [port]}

    def test_bel_groups_property_simple(self) -> None:
        """For a simple tile, bel_groups groups everything under the tile name."""
        tile = _simple_tile(name="T1")
        assert tile.bel_groups == {"T1": []}

    def test_config_bits_alias(self) -> None:
        """config_bits mirrors globalConfigBits."""
        tile = _simple_tile()
        assert tile.config_bits == tile.globalConfigBits


class TestBelQueries:
    """Tests for BEL lookup helpers added by the tile model extension."""

    def test_get_unique_bel_type_dedups_by_name(self) -> None:
        """Duplicate BEL names collapse to the first occurrence."""
        bel1 = Bel(
            src=Path("L.v"), prefix="A", module=make_yosys_module(), module_name="L"
        )
        bel2 = Bel(
            src=Path("L.v"), prefix="B", module=make_yosys_module(), module_name="L"
        )
        tile = _simple_tile(bels=[bel1, bel2])
        unique = tile.get_unique_bel_type()
        assert len(unique) == 1
        assert unique[0] is bel1

    def test_get_bel_by_bel_port(self) -> None:
        """get_bel_by_bel_port finds the BEL that owns a port."""
        port = BelPort(name="A", io_direction=IO.INPUT, width=1)
        bel = Bel(
            src=Path("L.v"),
            prefix="",
            module=make_yosys_module({"A": (IO.INPUT, 1)}),
            module_name="L",
        )
        tile = _simple_tile(bels=[bel])
        assert tile.get_bel_by_bel_port(port) is bel

    def test_get_bel_shared_port_dedups(self) -> None:
        """get_bel_shared_port returns unique shared ports across BELs."""
        bel = Bel(
            src=Path("L.v"),
            prefix="",
            module=make_yosys_module(
                {"Q": (IO.OUTPUT, 1), "clk": (IO.INPUT, 1)},
                port_attributes={"clk": {"SHARED_PORT": 1}},
            ),
            module_name="L",
        )
        tile = _simple_tile(bels=[bel])
        names = [p.name for p in tile.get_bel_shared_port()]
        assert "clk" in names

    def test_serialize_returns_dict(self) -> None:
        """serialize produces a dict including config_bits."""
        tile = _simple_tile(name="T1")
        data = tile.serialize()
        assert isinstance(data, dict)
        assert "config_bits" in data

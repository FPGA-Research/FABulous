"""Tests for Tile methods — notably pin-count and min-die-area computation."""

from decimal import Decimal

from fabulous.fabric_definition.define import IO, Direction, Side
from fabulous.fabric_definition.port import Port
from fabulous.fabric_definition.tile import Tile


def _mk_tile(ports: list[Port]) -> Tile:
    """Construct a Tile with only portsInfo set — enough for get_port_count tests."""
    return Tile(
        name="T",
        ports=ports,
        bels=[],
        tileDir=None,
        matrixDir=None,
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
) -> list[Port]:
    """Mirror parsePortLine: one OUTPUT port on ``side``, one INPUT on opposite."""
    side = Side[direction]
    return [
        Port(
            Direction[direction],
            src,
            x_offset,
            y_offset,
            dst,
            wires,
            src,
            IO.OUTPUT,
            side,
        ),
        Port(
            Direction[direction],
            src,
            x_offset,
            y_offset,
            dst,
            wires,
            dst,
            IO.INPUT,
            side.opposite,
        ),
    ]


class TestGetPortCount:
    """``get_port_count`` must return physical pin count, not 2× the wire count."""

    def test_single_direction_counts_once_per_wire(self) -> None:
        # One NORTH wire produces N1BEG on N edge and N1END on S edge.
        # Each edge should report exactly wireCount pins, not 2× wireCount.
        tile = _mk_tile(_directional_ports("NORTH", "N1BEG", "N1END", 4))
        assert tile.get_port_count(Side.NORTH) == 4
        assert tile.get_port_count(Side.SOUTH) == 4

    def test_distance_multiplies_wire_count(self) -> None:
        # N4 wire with distance 4 and wireCount=4 expands to 16 physical pins
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
        port = Port(
            Direction.JUMP,
            "NULL",
            0,
            0,
            "VCC",
            1,
            "VCC",
            IO.INPUT,
            Side.ANY,
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

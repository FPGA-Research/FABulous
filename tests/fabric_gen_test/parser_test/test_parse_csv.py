"""Tests for parsing tile port lines from CSV fabric definitions."""

import pytest

from fabulous.custom_exception import InvalidPortType, InvalidSwitchMatrixDefinition
from fabulous.fabric_definition.define import IO, Direction, Side
from fabulous.fabric_generator.parser.parse_csv import parse_port_line

# (kind, OUTPUT/start side, INPUT/end side, unit x_offset, unit y_offset) with a
# canonical bottom-left unit offset for the direction (north is +y, east is +x).
DIRECTIONAL_CASES = [
    ("NORTH", Side.NORTH, Side.SOUTH, 0, 1),
    ("SOUTH", Side.SOUTH, Side.NORTH, 0, -1),
    ("EAST", Side.EAST, Side.WEST, 1, 0),
    ("WEST", Side.WEST, Side.EAST, -1, 0),
]


class TestDirectionalPorts:
    """NORTH/SOUTH/EAST/WEST lines produce an OUTPUT/INPUT port pair."""

    @pytest.mark.parametrize(
        ("kind", "startSide", "endSide", "x_off", "y_off"), DIRECTIONAL_CASES
    )
    def test_two_ports_with_expected_io_and_sides(
        self, kind: str, startSide: Side, endSide: Side, x_off: int, y_off: int
    ) -> None:
        ports, commonWirePair = parse_port_line(f"{kind},N1BEG,{x_off},{y_off},N1END,4")

        assert len(ports) == 2
        output, input_ = ports

        assert output.io_direction is IO.OUTPUT
        assert output.name == "N1BEG"
        assert output.side_of_tile is startSide

        assert input_.io_direction is IO.INPUT
        assert input_.name == "N1END"
        assert input_.side_of_tile is endSide

        assert commonWirePair == ("N1BEG", "N1END")

    @pytest.mark.parametrize(
        ("kind", "x_off", "y_off"), [(c[0], c[3], c[4]) for c in DIRECTIONAL_CASES]
    )
    def test_shared_attributes_carry_through(
        self, kind: str, x_off: int, y_off: int
    ) -> None:
        ports, _ = parse_port_line(f"{kind},N2BEG,{x_off * 2},{y_off * 2},N2END,8")

        for port in ports:
            assert port.wire_direction is Direction[kind]
            assert port.source_name == "N2BEG"
            assert port.destination_name == "N2END"
            assert port.x_offset == x_off * 2
            assert port.y_offset == y_off * 2
            assert port.wire_count == 8

    @pytest.mark.parametrize(
        ("kind", "x_off", "y_off"), [(c[0], c[3], c[4]) for c in DIRECTIONAL_CASES]
    )
    def test_legacy_top_first_offset_is_normalized(
        self, kind: str, x_off: int, y_off: int
    ) -> None:
        """Legacy top-first offsets parse to the same bottom-left model.

        Pre-bottom-left fabric definitions authored NORTH/SOUTH with the
        opposite y sign. The direction token is authoritative, so the sign is
        derived from it and the authored one is ignored, leaving existing
        projects readable without change.
        """
        # Feed the sign-flipped (legacy) offset; expect the canonical one back.
        ports, _ = parse_port_line(f"{kind},N1BEG,{-x_off},{-y_off},N1END,4")

        for port in ports:
            assert port.x_offset == x_off
            assert port.y_offset == y_off

    @pytest.mark.parametrize(
        "bad_line",
        ["NORTH,N1BEG,1,1,N1END,4", "EAST,E1BEG,1,1,E1END,4"],
    )
    def test_diagonal_cardinal_wire_rejected(self, bad_line: str) -> None:
        """A cardinal wire with a non-zero orthogonal offset is rejected."""
        with pytest.raises(InvalidSwitchMatrixDefinition):
            parse_port_line(bad_line)

    def test_null_destination_keeps_name_and_pairs(self) -> None:
        ports, commonWirePair = parse_port_line("SOUTH,S4BEG,0,4,NULL,4")

        assert ports[1].name == "NULL"
        assert commonWirePair == ("S4BEG", "NULL")


class TestJumpPorts:
    """JUMP lines stay within a tile, so both ports sit on Side.ANY."""

    def test_two_ports_on_any_side(self) -> None:
        ports, _ = parse_port_line("JUMP,J_SR_BEG,0,0,J_SR_END,1")

        assert len(ports) == 2
        output, input_ = ports

        assert output.io_direction is IO.OUTPUT
        assert output.name == "J_SR_BEG"
        assert input_.io_direction is IO.INPUT
        assert input_.name == "J_SR_END"

        assert all(p.wire_direction is Direction.JUMP for p in ports)
        assert all(p.side_of_tile is Side.ANY for p in ports)

    def test_no_common_wire_pair(self) -> None:
        _, commonWirePair = parse_port_line("JUMP,J_SR_BEG,0,0,J_SR_END,1")

        assert commonWirePair is None


class TestUnknownPortType:
    """Lines that are not a known wire direction are rejected."""

    @pytest.mark.parametrize("kind", ["BEL", "MATRIX", "north", "FOO"])
    def test_raises_invalid_port_type(self, kind: str) -> None:
        with pytest.raises(InvalidPortType, match="Unknown port type"):
            parse_port_line(f"{kind},SRC_BEG,0,0,DST_END,1")


class TestPortNameTrailingDigit:
    """A declared port name must not end in a digit.

    Trailing digits are reserved for the index that wire expansion appends
    (``N1BEG`` -> `N1BEG0`, `N1BEG1` ...). A declared name that already
    ends in a digit (e.g. ``X0_Y4_2_X0_Y3``) becomes ambiguous once the index
    is appended, because downstream the trailing digits are read back as a bit
    index. Reject such names at the parsing boundary.
    """

    @pytest.mark.parametrize("kind", ["NORTH", "SOUTH", "EAST", "WEST", "JUMP"])
    def test_source_name_ending_in_digit_raises(self, kind: str) -> None:
        line = f"{kind},X0_Y4_2_X0_Y3,0,0,DST_END,1"
        with pytest.raises(InvalidPortType, match="digit"):
            parse_port_line(line)

    @pytest.mark.parametrize("kind", ["NORTH", "SOUTH", "EAST", "WEST", "JUMP"])
    def test_destination_name_ending_in_digit_raises(self, kind: str) -> None:
        line = f"{kind},SRC_BEG,0,0,X0_Y4_2_X0_Y3,1"
        with pytest.raises(InvalidPortType, match="digit"):
            parse_port_line(line)

    def test_single_trailing_digit_raises(self) -> None:
        with pytest.raises(InvalidPortType, match="digit"):
            parse_port_line("JUMP,BUS3,0,0,J_END,1")

    @pytest.mark.parametrize(
        "line",
        [
            "JUMP,J_SR_BEG,0,0,J_SR_END,1",
            "NORTH,N1BEG,0,-1,N1END,4",
            "SOUTH,S4BEG,0,4,NULL,4",
            "NORTH,NULL,0,-1,N1END,4",
        ],
    )
    def test_valid_names_do_not_raise(self, line: str) -> None:
        ports, _ = parse_port_line(line)
        assert ports

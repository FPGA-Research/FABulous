"""Tests for parsing tile port lines from CSV fabric definitions."""

import pytest

from fabulous.custom_exception import InvalidPortType
from fabulous.fabric_definition.define import IO, Direction, Side
from fabulous.fabric_generator.parser.parse_csv import parsePortLine

# (kind, physical side of the OUTPUT/start port, physical side of the INPUT/end port)
DIRECTIONAL_CASES = [
    ("NORTH", Side.NORTH, Side.SOUTH),
    ("SOUTH", Side.SOUTH, Side.NORTH),
    ("EAST", Side.EAST, Side.WEST),
    ("WEST", Side.WEST, Side.EAST),
]


class TestDirectionalPorts:
    """NORTH/SOUTH/EAST/WEST lines produce an OUTPUT/INPUT port pair."""

    @pytest.mark.parametrize(("kind", "startSide", "endSide"), DIRECTIONAL_CASES)
    def test_two_ports_with_expected_io_and_sides(
        self, kind: str, startSide: Side, endSide: Side
    ) -> None:
        ports, commonWirePair = parsePortLine(f"{kind},N1BEG,0,-1,N1END,4")

        assert len(ports) == 2
        output, input_ = ports

        assert output.inOut is IO.OUTPUT
        assert output.name == "N1BEG"
        assert output.sideOfTile is startSide

        assert input_.inOut is IO.INPUT
        assert input_.name == "N1END"
        assert input_.sideOfTile is endSide

        assert commonWirePair == ("N1BEG", "N1END")

    @pytest.mark.parametrize("kind", [c[0] for c in DIRECTIONAL_CASES])
    def test_shared_attributes_carry_through(self, kind: str) -> None:
        ports, _ = parsePortLine(f"{kind},N2BEG,0,-2,N2END,8")

        for port in ports:
            assert port.wireDirection is Direction[kind]
            assert port.sourceName == "N2BEG"
            assert port.destinationName == "N2END"
            assert port.xOffset == 0
            assert port.yOffset == -2
            assert port.wireCount == 8

    def test_null_destination_keeps_name_and_pairs(self) -> None:
        ports, commonWirePair = parsePortLine("SOUTH,S4BEG,0,4,NULL,4")

        assert ports[1].name == "NULL"
        assert commonWirePair == ("S4BEG", "NULL")


class TestJumpPorts:
    """JUMP lines stay within a tile, so both ports sit on Side.ANY."""

    def test_two_ports_on_any_side(self) -> None:
        ports, _ = parsePortLine("JUMP,J_SR_BEG,0,0,J_SR_END,1")

        assert len(ports) == 2
        output, input_ = ports

        assert output.inOut is IO.OUTPUT
        assert output.name == "J_SR_BEG"
        assert input_.inOut is IO.INPUT
        assert input_.name == "J_SR_END"

        assert all(p.wireDirection is Direction.JUMP for p in ports)
        assert all(p.sideOfTile is Side.ANY for p in ports)

    def test_no_common_wire_pair(self) -> None:
        _, commonWirePair = parsePortLine("JUMP,J_SR_BEG,0,0,J_SR_END,1")

        assert commonWirePair is None


class TestUnknownPortType:
    """Lines that are not a known wire direction are rejected."""

    @pytest.mark.parametrize("kind", ["BEL", "MATRIX", "north", "FOO"])
    def test_raises_invalid_port_type(self, kind: str) -> None:
        with pytest.raises(InvalidPortType, match="Unknown port type"):
            parsePortLine(f"{kind},SRC_BEG,0,0,DST_END,1")


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
            parsePortLine(line)

    @pytest.mark.parametrize("kind", ["NORTH", "SOUTH", "EAST", "WEST", "JUMP"])
    def test_destination_name_ending_in_digit_raises(self, kind: str) -> None:
        line = f"{kind},SRC_BEG,0,0,X0_Y4_2_X0_Y3,1"
        with pytest.raises(InvalidPortType, match="digit"):
            parsePortLine(line)

    def test_single_trailing_digit_raises(self) -> None:
        with pytest.raises(InvalidPortType, match="digit"):
            parsePortLine("JUMP,BUS3,0,0,J_END,1")

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
        ports, _ = parsePortLine(line)
        assert ports

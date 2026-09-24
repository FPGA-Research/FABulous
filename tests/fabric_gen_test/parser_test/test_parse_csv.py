"""Tests for parsing tile port lines from CSV fabric definitions."""

from pathlib import Path

import pytest

from fabulous.custom_exception import (
    InvalidFabricParameter,
    InvalidPortType,
    InvalidSupertileDefinition,
    InvalidTileDefinition,
)
from fabulous.fabric_definition.define import IO, Direction, Side
from fabulous.fabric_generator.parser.parse_csv import (
    parse_port_line,
    parseFabricCSV,
    parseSupertilesCSV,
    parseTilesCSV,
)
from fabulous.fabulous_settings import init_context
from tests.conftest import make_empty_tile

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
        ports, commonWirePair = parse_port_line(f"{kind},N1BEG,0,-1,N1END,4")

        assert len(ports) == 2
        output, input_ = ports

        assert output.io_direction is IO.OUTPUT
        assert output.name == "N1BEG"
        assert output.side_of_tile is startSide

        assert input_.io_direction is IO.INPUT
        assert input_.name == "N1END"
        assert input_.side_of_tile is endSide

        assert commonWirePair == ("N1BEG", "N1END")

    @pytest.mark.parametrize("kind", [c[0] for c in DIRECTIONAL_CASES])
    def test_shared_attributes_carry_through(self, kind: str) -> None:
        ports, _ = parse_port_line(f"{kind},N2BEG,0,-2,N2END,8")

        for port in ports:
            assert port.wire_direction is Direction[kind]
            assert port.source_name == "N2BEG"
            assert port.destination_name == "N2END"
            assert port.x_offset == 0
            assert port.y_offset == -2
            assert port.wire_count == 8

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


class TestUserCLKDirection:
    """`UserCLKDirection` in the Parameters block sets `Fabric.userCLKSide`."""

    @staticmethod
    def _set_direction(project: Path, value: str) -> Path:
        csv = project / "fabric.csv"
        csv.write_text(
            csv.read_text().replace(
                "ParametersBegin,", f"ParametersBegin,\nUserCLKDirection,{value},", 1
            )
        )
        return csv

    @pytest.mark.parametrize(
        ("value", "side"),
        [
            ("S2N", Side.SOUTH),
            ("N2S", Side.NORTH),
            ("W2E", Side.WEST),
            ("E2W", Side.EAST),
        ],
    )
    def test_direction_maps_to_entry_side(
        self, project: Path, value: str, side: Side
    ) -> None:
        init_context(project)
        fabric = parseFabricCSV(str(self._set_direction(project, value)))
        assert fabric.userCLKSide is side

    def test_default_is_south(self, project: Path) -> None:
        init_context(project)
        assert parseFabricCSV(str(project / "fabric.csv")).userCLKSide is Side.SOUTH

    def test_invalid_direction_raises(self, project: Path) -> None:
        init_context(project)
        with pytest.raises(InvalidFabricParameter, match="UP"):
            parseFabricCSV(str(self._set_direction(project, "UP")))


class TestDeprecatedHeader:
    """Column 3 of a `TILE`/`SuperTILE` header is empty or `DEPRECATED`."""

    @staticmethod
    def _tile_csv(project: Path, header: str) -> Path:
        csv = project / "Tile" / "N_term_single" / "N_term_single.csv"
        _, body = csv.read_text().split("\n", 1)
        csv.write_text(f"{header}\n{body}")
        return csv

    @staticmethod
    def _supertile_csv(tmp_path: Path, header: str) -> Path:
        csv = tmp_path / "ST.csv"
        csv.write_text(f"{header}\nT0\nT1\nEndSuperTILE\n")
        return csv

    @pytest.mark.parametrize(
        ("header", "deprecated"),
        [
            ("TILE,N_term_single,DEPRECATED,,", True),
            ("TILE,N_term_single,,,", False),
            ("TILE,N_term_single", False),
        ],
    )
    def test_tile_marker_sets_flag(
        self, project: Path, header: str, deprecated: bool
    ) -> None:
        init_context(project)
        tiles, _ = parseTilesCSV(self._tile_csv(project, header))
        assert [tile.deprecated for tile in tiles] == [deprecated]

    @pytest.mark.parametrize(
        ("header", "deprecated"),
        [("SuperTILE,ST,DEPRECATED,,", True), ("SuperTILE,ST,,,", False)],
    )
    def test_supertile_marker_sets_flag(
        self, tmp_path: Path, header: str, deprecated: bool
    ) -> None:
        tiles = {name: make_empty_tile(name) for name in ("T0", "T1")}
        (supertile,) = parseSupertilesCSV(self._supertile_csv(tmp_path, header), tiles)
        assert supertile.deprecated is deprecated

    def test_unknown_tile_marker_raises(self, project: Path) -> None:
        init_context(project)
        csv = self._tile_csv(project, "TILE,N_term_single,OBSOLETE,,")
        with pytest.raises(InvalidTileDefinition, match="OBSOLETE"):
            parseTilesCSV(csv)

    def test_unknown_supertile_marker_raises(self, tmp_path: Path) -> None:
        tiles = {name: make_empty_tile(name) for name in ("T0", "T1")}
        csv = self._supertile_csv(tmp_path, "SuperTILE,ST,OBSOLETE,,")
        with pytest.raises(InvalidSupertileDefinition, match="OBSOLETE"):
            parseSupertilesCSV(csv, tiles)

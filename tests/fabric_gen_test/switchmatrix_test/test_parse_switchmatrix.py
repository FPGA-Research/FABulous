"""Unit tests for parse_switchmatrix parser functions."""

from pathlib import Path

import pytest

from fabulous.custom_exception import InvalidListFileDefinition, InvalidSwitchMatrixDefinition
from fabulous.fabric_generator.parser.parse_switchmatrix import (
    expandListPorts,
    parseList,
    parseMatrix,
)


class TestExpandListPorts:
    """Tests for expandListPorts."""

    def test_simple_port(self) -> None:
        """Plain port name is returned as a single-element list."""
        assert expandListPorts("N1BEG0") == ["N1BEG0"]

    def test_alternatives_expansion(self) -> None:
        """[A|B] syntax expands into two separate port names."""
        assert expandListPorts("N[1|2]BEG0") == ["N1BEG0", "N2BEG0"]

    def test_multiple_alternatives(self) -> None:
        """[A|B|C] expands into three entries."""
        assert expandListPorts("[E|N|S]1BEG0") == ["E1BEG0", "N1BEG0", "S1BEG0"]

    def test_multiplier(self) -> None:
        """'{N}' repeats the port N times and is stripped from the name."""
        assert expandListPorts("CLK{3}") == ["CLK", "CLK", "CLK"]

    def test_multiplier_stripped_from_name(self) -> None:
        """The multiplier annotation is not included in the resulting port name."""
        result = expandListPorts("PORT{2}")
        assert all(r == "PORT" for r in result)

    def test_spaces_stripped(self) -> None:
        """Spaces are removed from port names."""
        assert expandListPorts(" N1BEG0 ") == ["N1BEG0"]

    def test_mismatched_square_bracket_raises(self) -> None:
        """Unbalanced '[' raises ValueError."""
        with pytest.raises(ValueError, match="mismatched brackets"):
            expandListPorts("N[1BEG0")

    def test_mismatched_curly_bracket_raises(self) -> None:
        """Unbalanced '{' raises ValueError."""
        with pytest.raises(ValueError, match="mismatched brackets"):
            expandListPorts("N1BEG{3")

    def test_no_multiplier_returns_single(self) -> None:
        """Port without multiplier returns a single entry."""
        assert expandListPorts("GND") == ["GND"]

    def test_recursive_expansion(self) -> None:
        """Nested alternatives expand correctly via recursion."""
        result = expandListPorts("X[A|B]Y[0|1]")
        # First '[' matched: XAY[0|1] and XBY[0|1], then each expands further
        assert result == ["XAY0", "XAY1", "XBY0", "XBY1"]


class TestParseMatrix:
    """Tests for parseMatrix."""

    def test_basic_connections(self, tmp_path: Path) -> None:
        """Connections marked with '1' are returned as destination lists."""
        f = tmp_path / "tile_matrix.csv"
        f.write_text("MyTile,DEST0,DEST1\nSRC0,1,0\nSRC1,0,1\n")
        result = parseMatrix(f, "MyTile")
        assert result == {"SRC0": ["DEST0"], "SRC1": ["DEST1"]}

    def test_multiple_connections_per_source(self, tmp_path: Path) -> None:
        """A source connected to multiple destinations is collected correctly."""
        f = tmp_path / "tile_matrix.csv"
        f.write_text("T,D0,D1,D2\nSRC,1,0,1\n")
        assert parseMatrix(f, "T") == {"SRC": ["D0", "D2"]}

    def test_no_connections(self, tmp_path: Path) -> None:
        """Source with no '1' bits maps to an empty list."""
        f = tmp_path / "tile_matrix.csv"
        f.write_text("T,D0,D1\nSRC,0,0\n")
        assert parseMatrix(f, "T") == {"SRC": []}

    def test_comments_stripped(self, tmp_path: Path) -> None:
        """Lines with '#' comments are ignored."""
        f = tmp_path / "tile_matrix.csv"
        f.write_text("T,D0 # header comment\nSRC,1 # row comment\n")
        result = parseMatrix(f, "T")
        assert "SRC" in result

    def test_empty_rows_skipped(self, tmp_path: Path) -> None:
        """Blank lines do not produce entries in the result."""
        f = tmp_path / "tile_matrix.csv"
        f.write_text("T,D0\n\nSRC,1\n\n")
        assert list(parseMatrix(f, "T").keys()) == ["SRC"]

    def test_tile_name_mismatch_raises(self, tmp_path: Path) -> None:
        """Mismatched tile name in CSV header raises InvalidSwitchMatrixDefinition."""
        f = tmp_path / "tile_matrix.csv"
        f.write_text("WrongTile,D0\nSRC,1\n")
        with pytest.raises(InvalidSwitchMatrixDefinition):
            parseMatrix(f, "MyTile")


class TestParseList:
    """Tests for parseList."""

    def test_basic_pair(self, tmp_path: Path) -> None:
        """A simple source,sink line is returned as a tuple pair."""
        f = tmp_path / "test.list"
        f.write_text("N1BEG0,E1END0\n")
        assert parseList(f) == [("N1BEG0", "E1END0")]

    def test_collect_source(self, tmp_path: Path) -> None:
        """collect='source' groups sinks by source."""
        f = tmp_path / "test.list"
        f.write_text("SRC,SINK0\nSRC,SINK1\n")
        assert parseList(f, "source") == {"SRC": ["SINK0", "SINK1"]}

    def test_collect_sink(self, tmp_path: Path) -> None:
        """collect='sink' groups sources by sink."""
        f = tmp_path / "test.list"
        f.write_text("SRC0,SINK\nSRC1,SINK\n")
        assert parseList(f, "sink") == {"SINK": ["SRC0", "SRC1"]}

    def test_comments_stripped(self, tmp_path: Path) -> None:
        """Lines starting with '#' are ignored."""
        f = tmp_path / "test.list"
        f.write_text("# comment\nA,B\n")
        assert parseList(f) == [("A", "B")]

    def test_blank_lines_skipped(self, tmp_path: Path) -> None:
        """Blank lines do not produce entries."""
        f = tmp_path / "test.list"
        f.write_text("\nA,B\n\nC,D\n")
        assert parseList(f) == [("A", "B"), ("C", "D")]

    def test_duplicates_removed(self, tmp_path: Path) -> None:
        """Duplicate pairs appear only once, first occurrence wins."""
        f = tmp_path / "test.list"
        f.write_text("A,B\nA,B\n")
        assert parseList(f) == [("A", "B")]

    def test_expansion_with_alternatives(self, tmp_path: Path) -> None:
        """'[A|B]' syntax expands both source and sink into multiple pairs."""
        f = tmp_path / "test.list"
        f.write_text("[X|Y]BEG,[X|Y]END\n")
        assert parseList(f) == [("XBEG", "XEND"), ("YBEG", "YEND")]

    def test_include_directive(self, tmp_path: Path) -> None:
        """INCLUDE loads pairs from a referenced file."""
        included = tmp_path / "other.list"
        included.write_text("A,B\n")
        f = tmp_path / "test.list"
        f.write_text("INCLUDE,other.list\n")
        assert parseList(f) == [("A", "B")]

    def test_file_not_found_raises(self, tmp_path: Path) -> None:
        """Missing file raises FileNotFoundError."""
        with pytest.raises(FileNotFoundError):
            parseList(tmp_path / "nonexistent.list")

    def test_invalid_format_raises(self, tmp_path: Path) -> None:
        """Lines with more or fewer than two fields raise InvalidListFileDefinition."""
        f = tmp_path / "test.list"
        f.write_text("A,B,C\n")
        with pytest.raises(InvalidListFileDefinition):
            parseList(f)

    def test_mismatched_expansion_count_raises(self, tmp_path: Path) -> None:
        """Unequal source/sink expansion counts raise InvalidListFileDefinition."""
        f = tmp_path / "test.list"
        f.write_text("[A|B|C]END,[X|Y]END\n")
        with pytest.raises(InvalidListFileDefinition):
            parseList(f)

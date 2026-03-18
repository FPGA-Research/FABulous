"""Unit tests for parse_switchmatrix parser functions."""

from pathlib import Path

import pytest

from fabulous.custom_exception import InvalidListFileDefinition, InvalidSwitchMatrixDefinition
from fabulous.fabric_generator.parser.parse_switchmatrix import (
    expandListPorts,
    parseList,
    parseMatrix,
)


@pytest.mark.parametrize(
    ("case", "expected_result", "expected_error"),
    [
        pytest.param("N1BEG0", ["N1BEG0"], None, id="simple_port"),
        pytest.param("GND", ["GND"], None, id="no_multiplier"),
        pytest.param(" N1BEG0 ", ["N1BEG0"], None, id="spaces_stripped"),
        pytest.param("N[1|2]BEG0", ["N1BEG0", "N2BEG0"], None, id="two_alternatives"),
        pytest.param("[E|N|S]1BEG0", ["E1BEG0", "N1BEG0", "S1BEG0"], None, id="three_alternatives"),
        pytest.param("CLK{3}", ["CLK", "CLK", "CLK"], None, id="multiplier"),
        pytest.param("PORT{2}", ["PORT", "PORT"], None, id="multiplier_stripped_from_name"),
        pytest.param(
            "X[A|B]Y[0|1]",
            ["XAY0", "XAY1", "XBY0", "XBY1"],
            None,
            id="recursive_expansion",
        ),
        pytest.param("N[1BEG0", None, "mismatched brackets", id="mismatched_square_bracket"),
        pytest.param("N1BEG{3", None, "mismatched brackets", id="mismatched_curly_bracket"),
    ],
)
def test_expand_list_ports(
    case: str, expected_result: list[str] | None, expected_error: str | None
) -> None:
    """Test expandListPorts for valid expansions and error conditions."""
    if expected_error:
        with pytest.raises(ValueError, match=expected_error):
            expandListPorts(case)
    else:
        assert expandListPorts(case) == expected_result


@pytest.mark.parametrize(
    ("content", "tile_name", "expected_result", "expected_error"),
    [
        pytest.param(
            "MyTile,DEST0,DEST1\nSRC0,1,0\nSRC1,0,1\n",
            "MyTile",
            {"SRC0": ["DEST0"], "SRC1": ["DEST1"]},
            None,
            id="basic_connections",
        ),
        pytest.param(
            "T,D0,D1,D2\nSRC,1,0,1\n",
            "T",
            {"SRC": ["D0", "D2"]},
            None,
            id="multiple_destinations_per_source",
        ),
        pytest.param(
            "T,D0,D1\nSRC,0,0\n",
            "T",
            {"SRC": []},
            None,
            id="no_connections",
        ),
        pytest.param(
            "T,D0 # header comment\nSRC,1 # row comment\n",
            "T",
            None,
            None,
            id="comments_stripped",
        ),
        pytest.param(
            "T,D0\n\nSRC,1\n\n",
            "T",
            None,
            None,
            id="blank_lines_skipped",
        ),
        pytest.param(
            "WrongTile,D0\nSRC,1\n",
            "MyTile",
            None,
            InvalidSwitchMatrixDefinition,
            id="tile_name_mismatch",
        ),
    ],
)
def test_parse_matrix(
    tmp_path: Path,
    content: str,
    tile_name: str,
    expected_result: dict | None,
    expected_error: type | None,
) -> None:
    """Test parseMatrix for valid connection parsing and error conditions."""
    f = tmp_path / "tile_matrix.csv"
    f.write_text(content)

    if expected_error:
        with pytest.raises(expected_error):
            parseMatrix(f, tile_name)
    else:
        result = parseMatrix(f, tile_name)
        if expected_result is not None:
            assert result == expected_result
        else:
            assert isinstance(result, dict)


@pytest.mark.parametrize(
    ("files", "collect", "expected_result", "expected_error"),
    [
        pytest.param(
            {"test.list": "N1BEG0,E1END0\n"},
            "pair",
            [("N1BEG0", "E1END0")],
            None,
            id="basic_pair",
        ),
        pytest.param(
            {"test.list": "SRC,SINK0\nSRC,SINK1\n"},
            "source",
            {"SRC": ["SINK0", "SINK1"]},
            None,
            id="collect_source",
        ),
        pytest.param(
            {"test.list": "SRC0,SINK\nSRC1,SINK\n"},
            "sink",
            {"SINK": ["SRC0", "SRC1"]},
            None,
            id="collect_sink",
        ),
        pytest.param(
            {"test.list": "# comment\nA,B\n"},
            "pair",
            [("A", "B")],
            None,
            id="comments_stripped",
        ),
        pytest.param(
            {"test.list": "\nA,B\n\nC,D\n"},
            "pair",
            [("A", "B"), ("C", "D")],
            None,
            id="blank_lines_skipped",
        ),
        pytest.param(
            {"test.list": "A,B\nA,B\n"},
            "pair",
            [("A", "B")],
            None,
            id="duplicates_removed",
        ),
        pytest.param(
            {"test.list": "[X|Y]BEG,[X|Y]END\n"},
            "pair",
            [("XBEG", "XEND"), ("YBEG", "YEND")],
            None,
            id="alternatives_expansion",
        ),
        pytest.param(
            {"test.list": "INCLUDE,other.list\n", "other.list": "A,B\n"},
            "pair",
            [("A", "B")],
            None,
            id="include_directive",
        ),
        pytest.param(
            {},
            "pair",
            None,
            FileNotFoundError,
            id="file_not_found",
        ),
        pytest.param(
            {"test.list": "A,B,C\n"},
            "pair",
            None,
            InvalidListFileDefinition,
            id="invalid_format",
        ),
        pytest.param(
            {"test.list": "[A|B|C]END,[X|Y]END\n"},
            "pair",
            None,
            InvalidListFileDefinition,
            id="mismatched_expansion_count",
        ),
    ],
)
def test_parse_list(
    tmp_path: Path,
    files: dict[str, str],
    collect: str,
    expected_result: list | dict | None,
    expected_error: type | None,
) -> None:
    """Test parseList for valid pair parsing and error conditions."""
    for name, content in files.items():
        (tmp_path / name).write_text(content)

    main_file = tmp_path / "test.list"

    if expected_error:
        with pytest.raises(expected_error):
            parseList(main_file, collect)
    else:
        assert parseList(main_file, collect) == expected_result

"""Unit tests for switch-matrix and wire/port parser functions."""

from pathlib import Path

import pytest

from fabulous.custom_exception import (
    InvalidListFileDefinition,
    InvalidSwitchMatrixDefinition,
)
from fabulous.fabric_definition.bel import Bel
from fabulous.fabric_definition.define import IO, Direction, Side
from fabulous.fabric_definition.port import TilePort
from fabulous.fabric_definition.tile import Tile
from fabulous.fabric_generator.parser.parse_csv import validate_composite_tile_matrix
from fabulous.fabric_generator.parser.parse_switchmatrix import (
    expandListPorts,
    parseList,
    parseMatrix,
)
from tests.conftest import make_empty_tile, make_muladd_bel


@pytest.mark.parametrize(
    ("case", "expected_result", "expected_error"),
    [
        pytest.param("N1BEG0", ["N1BEG0"], None, id="simple_port"),
        pytest.param("GND", ["GND"], None, id="no_multiplier"),
        pytest.param(" N1BEG0 ", ["N1BEG0"], None, id="spaces_stripped"),
        pytest.param("N[1|2]BEG0", ["N1BEG0", "N2BEG0"], None, id="two_alternatives"),
        pytest.param(
            "[E|N|S]1BEG0",
            ["E1BEG0", "N1BEG0", "S1BEG0"],
            None,
            id="three_alternatives",
        ),
        pytest.param("CLK{3}", ["CLK", "CLK", "CLK"], None, id="multiplier"),
        pytest.param(
            "PORT{2}", ["PORT", "PORT"], None, id="multiplier_stripped_from_name"
        ),
        pytest.param(
            "X[A|B]Y[0|1]",
            ["XAY0", "XAY1", "XBY0", "XBY1"],
            None,
            id="recursive_expansion",
        ),
        pytest.param(
            "N[1BEG0", None, "mismatched brackets", id="mismatched_square_bracket"
        ),
        pytest.param(
            "N1BEG{3", None, "mismatched brackets", id="mismatched_curly_bracket"
        ),
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
    ("content", "preserve_list_order", "expected_result", "expected_error"),
    [
        pytest.param(
            "MyTile,DEST0,DEST1\nSRC0,1,0\nSRC1,0,1\n",
            False,
            {"SRC0": ["DEST0"], "SRC1": ["DEST1"]},
            None,
            id="basic_connections",
        ),
        pytest.param(
            "T,D0,D1,D2\nSRC,1,0,1\n",
            False,
            {"SRC": ["D0", "D2"]},
            None,
            id="multiple_destinations_per_source",
        ),
        pytest.param(
            "T,D0,D1\nSRC,0,0\n",
            False,
            {"SRC": []},
            None,
            id="no_connections",
        ),
        pytest.param(
            "T,D0 # header comment\nSRC,1 # row comment\n",
            False,
            None,
            None,
            id="comments_stripped",
        ),
        pytest.param(
            "T,D0\n\nSRC,1\n\n",
            False,
            None,
            None,
            id="blank_lines_skipped",
        ),
        pytest.param(
            # The top-left header cell is a label only and is never validated,
            # so a mismatching name parses like any other.
            "WrongTile,D0\nSRC,1\n",
            False,
            {"SRC": ["D0"]},
            None,
            id="header_label_not_validated",
        ),
        pytest.param(
            "T,D0,D1,D2,D3\nSRC,1,2,3,4\n",
            True,
            {"SRC": ["D3", "D2", "D1", "D0"]},
            None,
            id="preserve_order_msb_first",
        ),
        pytest.param(
            # Without the flag every non-zero cell is a plain 1, so the inputs
            # fall back to CSV-column order.
            "T,D0,D1,D2,D3\nSRC,1,2,3,4\n",
            False,
            {"SRC": ["D0", "D1", "D2", "D3"]},
            None,
            id="legacy_read_uses_column_order",
        ),
        pytest.param(
            "T,D0,D1,D2\nSRC,0,foo,1\n",
            True,
            None,
            InvalidSwitchMatrixDefinition,
            id="non_integer_cell_value",
        ),
    ],
)
def test_parse_matrix(
    tmp_path: Path,
    content: str,
    preserve_list_order: bool,
    expected_result: dict | None,
    expected_error: type | None,
) -> None:
    """Test parseMatrix for valid connection parsing and error conditions."""
    f = tmp_path / "tile_matrix.csv"
    f.write_text(content)

    if expected_error:
        with pytest.raises(expected_error):
            parseMatrix(f, preserve_list_order)
    else:
        result = parseMatrix(f, preserve_list_order)
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


def test_parse_list_warns_on_duplicates(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """Duplicate connections are de-duplicated but reported."""
    f = tmp_path / "dup.list"
    f.write_text("A,B\nA,C\nA,B\n")
    assert parseList(f, "pair") == [("A", "B"), ("A", "C")]
    assert "ignoring 1 duplicate" in caplog.text


def _jump_port(name: str, in_out: IO, wire_count: int = 1) -> TilePort:
    """Build a regular (JUMP-direction) tile port for composite-matrix tests."""
    return TilePort(
        name=name,
        io_direction=in_out,
        width=wire_count,
        side_of_tile=Side.ANY,
        wire_direction=Direction.JUMP,
        source_name=name if in_out == IO.OUTPUT else "NULL",
        x_offset=0,
        y_offset=0,
        destination_name=name if in_out == IO.INPUT else "NULL",
        wire_count=wire_count,
    )


class TestCompositeTileMatrixValidation:
    """``validate_composite_tile_matrix`` rejects names that aren't real ports/pins.

    A composite tile's wrapper switch matrix may only reference sub-tile ports
    (sub-tile-qualified), wrapper-BEL pins, or constants; anything else (a typo
    like ``asdfasd``) is rejected.
    """

    def _sub_tiles_and_bels(self) -> tuple[list[Tile], list[Bel]]:
        # DSP_bot exposes operand A (output toward the matrix) and result Q
        # (input back from the matrix); the wrapper BEL has one input/output pin.
        bot = make_empty_tile(
            "DSP_bot",
            [
                _jump_port("A", IO.OUTPUT, wire_count=1),
                _jump_port("Q", IO.INPUT, wire_count=1),
            ],
            pin_order_config={},
        )
        bel = make_muladd_bel([("SUPER_A0", IO.INPUT), ("SUPER_Q0", IO.OUTPUT)])
        return [bot], [bel]

    def test_valid_connections_pass(self) -> None:
        sub_tiles, bels = self._sub_tiles_and_bels()
        connections = {
            "SUPER_A0": ["DSP_bot_A0"],  # forward: sub-tile output -> BEL input
            "DSP_bot_Q0": ["SUPER_Q0", "GND0", "VCC0"],  # reverse + constants
        }
        validate_composite_tile_matrix(
            "DSP", sub_tiles, bels, connections, Path("composite_matrix.list")
        )

    def test_unknown_source_rejected(self) -> None:
        sub_tiles, bels = self._sub_tiles_and_bels()
        connections = {"DSP_bot_Q0": ["SUPER_Q0", "GND0", "asdfasd"]}
        with pytest.raises(InvalidSwitchMatrixDefinition, match="asdfasd"):
            validate_composite_tile_matrix(
                "DSP", sub_tiles, bels, connections, Path("composite_matrix.list")
            )

    def test_unknown_sink_rejected(self) -> None:
        sub_tiles, bels = self._sub_tiles_and_bels()
        connections = {"SUPER_ZZ9": ["DSP_bot_A0"]}
        with pytest.raises(InvalidSwitchMatrixDefinition, match="SUPER_ZZ9"):
            validate_composite_tile_matrix(
                "DSP", sub_tiles, bels, connections, Path("composite_matrix.list")
            )

    def test_constant_as_sink_rejected(self) -> None:
        sub_tiles, bels = self._sub_tiles_and_bels()
        connections = {"GND0": ["DSP_bot_A0"]}
        with pytest.raises(InvalidSwitchMatrixDefinition, match="GND0"):
            validate_composite_tile_matrix(
                "DSP", sub_tiles, bels, connections, Path("composite_matrix.list")
            )

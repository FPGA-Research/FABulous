"""Unit tests for switch-matrix and wire/port parser functions."""

from pathlib import Path

import pytest

from fabulous.custom_exception import (
    InvalidListFileDefinition,
    InvalidPortType,
    InvalidSwitchMatrixDefinition,
)
from fabulous.fabric_definition.define import IO, Direction
from fabulous.fabric_definition.supertile import SuperTile
from fabulous.fabric_generator.parser.parse_csv import (
    parsePortLine,
    validate_super_tile_matrix,
)
from fabulous.fabric_generator.parser.parse_switchmatrix import (
    expandListPorts,
    parseList,
    parseMatrix,
)
from tests.conftest import make_empty_tile, make_muladd_bel, sjump_port


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
    ("content", "expected_result", "expected_error"),
    [
        pytest.param(
            "MyTile,DEST0,DEST1\nSRC0,1,0\nSRC1,0,1\n",
            {"SRC0": ["DEST0"], "SRC1": ["DEST1"]},
            None,
            id="basic_connections",
        ),
        pytest.param(
            "T,D0,D1,D2\nSRC,1,0,1\n",
            {"SRC": ["D0", "D2"]},
            None,
            id="multiple_destinations_per_source",
        ),
        pytest.param(
            "T,D0,D1\nSRC,0,0\n",
            {"SRC": []},
            None,
            id="no_connections",
        ),
        pytest.param(
            "T,D0 # header comment\nSRC,1 # row comment\n",
            None,
            None,
            id="comments_stripped",
        ),
        pytest.param(
            "T,D0\n\nSRC,1\n\n",
            None,
            None,
            id="blank_lines_skipped",
        ),
        pytest.param(
            "T,D0,D1,D2,D3\nSRC,1,2,3,4\n",
            {"SRC": ["D3", "D2", "D1", "D0"]},
            None,
            id="preserve_order_msb_first",
        ),
        pytest.param(
            "T,D0,D1,D2\nSRC,0,foo,1\n",
            None,
            InvalidSwitchMatrixDefinition,
            id="non_integer_cell_value",
        ),
    ],
)
def test_parse_matrix(
    tmp_path: Path,
    content: str,
    expected_result: dict | None,
    expected_error: type | None,
) -> None:
    """Test parseMatrix with preserve_list_order, honouring the cell encoding.

    The parametrized cases encode mux-input positions, so they are read with
    `preserve_list_order=True`; the legacy (treat-as-1, column-order) read is
    covered separately in `test_parse_matrix_legacy_column_order`.
    """
    f = tmp_path / "tile_matrix.csv"
    f.write_text(content)

    if expected_error:
        with pytest.raises(expected_error):
            parseMatrix(f, preserve_list_order=True)
    else:
        result = parseMatrix(f, preserve_list_order=True)
        if expected_result is not None:
            assert result == expected_result
        else:
            assert isinstance(result, dict)


def test_parse_matrix_legacy_column_order(tmp_path: Path) -> None:
    """Without preserve_list_order, every entry is treated as 1 (column order)."""
    f = tmp_path / "m.csv"
    # Cell magnitudes would put SRC in D3..D0 order, but the legacy read ignores
    # them and returns the mux inputs in CSV-column order instead.
    f.write_text("T,D0,D1,D2,D3\nSRC,1,2,3,4\n")
    assert parseMatrix(f, preserve_list_order=False) == {
        "SRC": ["D0", "D1", "D2", "D3"]
    }
    assert parseMatrix(f, preserve_list_order=True) == {"SRC": ["D3", "D2", "D1", "D0"]}


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


class TestParseSJumpPortLine:
    """`parsePortLine` accepts the two one-way SJUMP forms, rejects the rest.

    An SJUMP line is a one-way connection between a basic tile and its supertile
    BEL, so exactly one of source/destination must be NULL and the line carries
    no spatial offset.
    """

    def test_output_form(self) -> None:
        ports, common = parsePortLine("SJUMP,A,0,0,NULL,8")
        assert common is None
        assert len(ports) == 1
        (port,) = ports
        assert port.wireDirection == Direction.SJUMP
        assert port.inOut == IO.OUTPUT
        assert port.name == "A"
        assert (port.xOffset, port.yOffset) == (0, 0)

    def test_input_form(self) -> None:
        (port,), common = parsePortLine("SJUMP,NULL,0,0,Q,8")
        assert common is None
        assert port.inOut == IO.INPUT
        assert port.name == "Q"

    def test_both_non_null_rejected(self) -> None:
        with pytest.raises(InvalidPortType, match="exactly one of source"):
            parsePortLine("SJUMP,A,0,0,Q,8")

    def test_both_null_rejected(self) -> None:
        with pytest.raises(InvalidPortType, match="exactly one of source"):
            parsePortLine("SJUMP,NULL,0,0,NULL,8")

    def test_nonzero_offset_rejected(self) -> None:
        with pytest.raises(InvalidPortType, match="offset must be 0,0"):
            parsePortLine("SJUMP,A,1,0,NULL,8")
        with pytest.raises(InvalidPortType, match="offset must be 0,0"):
            parsePortLine("SJUMP,NULL,0,-1,Q,8")


class TestSuperTileMatrixValidation:
    """`validate_super_tile_matrix` rejects names that aren't real ports/pins.

    The supertile switch matrix may only reference BEL pins, child-tile SJUMP
    wires, or constants; anything else (a typo like `asdfasd`) is rejected.
    """

    def _supertile(self) -> SuperTile:
        # DSP_bot drives operand A0 up to the BEL and reads result Q0 back.
        bot = make_empty_tile(
            "DSP_bot",
            [
                sjump_port("A", IO.OUTPUT, wireCount=1),
                sjump_port("Q", IO.INPUT, wireCount=1),
            ],
            pinOrderConfig={},
        )
        bel = make_muladd_bel([("SUPER_A0", IO.INPUT), ("SUPER_Q0", IO.OUTPUT)])
        return SuperTile(
            name="DSP",
            tile_dir=Path(),
            tiles=[bot],
            tileMap=[[bot]],
            bels=[bel],
        )

    def test_port_name_sets(self) -> None:
        sources, sinks = self._supertile().get_matrix_port_names()
        # sources: child OUTPUT SJUMP wire + BEL output
        assert sources == {"DSP_bot_A0", "SUPER_Q0"}
        # sinks: BEL input + child INPUT SJUMP wire
        assert sinks == {"SUPER_A0", "DSP_bot_Q0"}

    @pytest.mark.parametrize(
        ("connections", "error_match"),
        [
            pytest.param(
                {
                    "SUPER_A0": ["DSP_bot_A0"],  # forward: child output -> BEL input
                    "DSP_bot_Q0": ["SUPER_Q0", "GND0", "VCC0"],  # reverse + consts
                },
                None,
                id="valid",
            ),
            pytest.param(
                {"DSP_bot_Q0": ["SUPER_Q0", "GND0", "asdfasd"]},
                "asdfasd",
                id="unknown_source",
            ),
            pytest.param({"SUPER_ZZ9": ["DSP_bot_A0"]}, "SUPER_ZZ9", id="unknown_sink"),
            pytest.param({"GND0": ["DSP_bot_A0"]}, "GND0", id="constant_as_sink"),
        ],
    )
    def test_validate_super_tile_matrix(
        self, connections: dict[str, list[str]], error_match: str | None
    ) -> None:
        st = self._supertile()
        path = Path("supertile_matrix.list")
        if error_match is None:
            validate_super_tile_matrix(st, connections, path)
        else:
            with pytest.raises(InvalidSwitchMatrixDefinition, match=error_match):
                validate_super_tile_matrix(st, connections, path)

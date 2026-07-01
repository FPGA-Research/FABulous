"""Tests for switch matrix list/csv conversion helpers in gen_helper."""

from pathlib import Path

from fabulous.fabric_generator.gen_fabric.gen_helper import (
    bootstrap_matrix_from_list,
    csv_to_list,
    list_to_csv,
)
from fabulous.fabric_generator.parser.parse_switchmatrix import parseList, parseMatrix
from tests.fabric_gen_test.conftest import create_switchmatrix_list


class TestBootstrapMatrixFromList:
    """``bootstrap_matrix_from_list`` derives a blank grid from a .list file."""

    def test_derives_ports_in_first_appearance_order(self, tmp_path: Path) -> None:
        list_file = tmp_path / "m.list"
        create_switchmatrix_list(
            list_file,
            [("A0", "B0"), ("A1", "B1"), ("A0", "B2")],
        )
        out = tmp_path / "m.csv"

        bootstrap_matrix_from_list(list_file, out, "MYTILE")

        lines = out.read_text().strip().split("\n")
        assert lines[0] == "MYTILE,B0,B1,B2"
        assert lines[1] == "A0,0,0,0"
        assert lines[2] == "A1,0,0,0"
        assert len(lines) == 3


class TestCsvToList:
    """``csv_to_list`` turns a switch matrix CSV back into a .list file."""

    def test_writes_one_pair_per_line_and_skips_comments(self, tmp_path: Path) -> None:
        # A CSV in the exact shape list_to_csv emits: per-row "#,count" columns,
        # a spurious empty-source row, and a trailing "#" column-count row.
        csv_file = tmp_path / "m.csv"
        csv_file.write_text(
            "TILE,B0,B1,B2\nA0,0,0,1,#,1\nA1,1,0,0,#,1\n,0,0,0,#,0\n#,1,0,1,0\n"
        )
        out = tmp_path / "m.list"

        csv_to_list(csv_file, out)

        lines = out.read_text().splitlines()
        assert lines[0] == "# TILE"
        assert lines[1:] == ["A0,B2", "A1,B0"]

    def test_single_input_destination_stays_plain(self, tmp_path: Path) -> None:
        csv_file = tmp_path / "m.csv"
        csv_file.write_text("TILE,B0,B1\nA0,0,1\n")
        out = tmp_path / "m.list"

        csv_to_list(csv_file, out)

        assert out.read_text().splitlines()[1] == "A0,B1"

    def test_destination_with_no_sources_emits_no_line(self, tmp_path: Path) -> None:
        # A named row whose cells are all zero is a destination with no sources;
        # it must not produce a dangling line.
        csv_file = tmp_path / "m.csv"
        csv_file.write_text("TILE,B0,B1\nA0,0,1\nZ,0,0\n")
        out = tmp_path / "m.list"

        csv_to_list(csv_file, out)

        assert out.read_text().splitlines()[1:] == ["A0,B1"]

    def test_mux_inputs_emitted_compact_in_magnitude_order(
        self, tmp_path: Path
    ) -> None:
        # A0 is a mux: B0 has value 2, B2 has value 1. The magnitude is the
        # 1-based .list position, so the input order is B2 (1) then B0 (2),
        # which is the reverse of column order (B0, B2).
        csv_file = tmp_path / "m.csv"
        csv_file.write_text("TILE,B0,B1,B2\nA0,2,0,1\n")
        out = tmp_path / "m.list"

        csv_to_list(csv_file, out)

        assert out.read_text().splitlines()[1] == "A0{2},[B2|B0]"


class TestStandaloneListToCSV:
    """bootstrap_matrix_from_list + list_to_csv is the standalone list->csv path."""

    def _convert(
        self, tmp_path: Path, connections: list[tuple[str, str]], preserve: bool
    ) -> dict[str, list[str]]:
        list_file = tmp_path / "m.list"
        create_switchmatrix_list(list_file, connections)
        csv_file = tmp_path / "m.csv"
        bootstrap_matrix_from_list(list_file, csv_file, "TILE")
        list_to_csv(list_file, csv_file, preserve)
        return parseMatrix(csv_file, "TILE")

    def test_parses_back_to_same_connections(self, tmp_path: Path) -> None:
        connections = [("A0", "B0"), ("A1", "B1"), ("A0", "B2")]
        parsed = self._convert(tmp_path, connections, preserve=False)
        assert parsed == {"A0": ["B0", "B2"], "A1": ["B1"]}

    def test_preserve_order_recovers_list_order(self, tmp_path: Path) -> None:
        # Without preservation, parseMatrix falls back to column order.
        connections = [("A0", "B0"), ("A0", "B1"), ("A0", "B2")]
        default = self._convert(tmp_path, connections, preserve=False)
        assert default == {"A0": ["B0", "B1", "B2"]}

        # With preservation, the per-row index encodes list order so the last
        # .list entry sorts first (highest value).
        preserved = self._convert(tmp_path, connections, preserve=True)
        assert preserved == {"A0": ["B2", "B1", "B0"]}


class TestRoundTrip:
    """A .list survives list -> csv -> list conversion."""

    def test_connection_set_preserved(self, tmp_path: Path) -> None:
        connections = [("A0", "B0"), ("A1", "B1"), ("A0", "B2")]
        list_file = tmp_path / "m.list"
        create_switchmatrix_list(list_file, connections)

        csv_file = tmp_path / "m.csv"
        bootstrap_matrix_from_list(list_file, csv_file, "TILE")
        list_to_csv(list_file, csv_file)

        back = tmp_path / "back.list"
        csv_to_list(csv_file, back)

        assert set(parseList(back)) == set(connections)

    def test_preserve_order_round_trips_mux_input_order(self, tmp_path: Path) -> None:
        # A1's .list order (B1 then B0) is the reverse of its CSV column order
        # (B0, B1), so the order only survives if csv_to_list honours the
        # per-cell magnitude rather than walking columns left to right.
        connections = [("A0", "B0"), ("A1", "B1"), ("A0", "B1"), ("A1", "B0")]
        list_file = tmp_path / "m.list"
        create_switchmatrix_list(list_file, connections)

        csv_file = tmp_path / "m.csv"
        bootstrap_matrix_from_list(list_file, csv_file, "TILE")
        list_to_csv(list_file, csv_file, preserveListOrder=True)

        back = tmp_path / "back.list"
        csv_to_list(csv_file, back)

        by_source = parseList(back, "source")
        assert by_source["A0"] == ["B0", "B1"]
        assert by_source["A1"] == ["B1", "B0"]
        assert "A1{2},[B1|B0]" in back.read_text().splitlines()

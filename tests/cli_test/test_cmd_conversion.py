"""Tests for the list_to_csv / csv_to_list switch matrix conversion commands."""

from pathlib import Path

from pytest_mock import MockerFixture

from fabulous.fabric_generator.gen_fabric.gen_helper import bootstrap_matrix_from_list
from fabulous.fabric_generator.parser.parse_switchmatrix import parseList, parseMatrix
from fabulous.fabulous_cli.fabulous_cli import FABulous_CLI
from tests.cli_test.conftest import TILE
from tests.conftest import run_cmd
from tests.fabric_gen_test.conftest import create_switchmatrix_list


def _write_csv(path: Path) -> None:
    """Write a switch matrix CSV in the shape list_to_csv emits (# metadata)."""
    path.write_text(
        "TILE,B0,B1,B2\nA0,0,0,1,#,1\nA1,1,0,0,#,1\n,0,0,0,#,0\n#,1,0,1,0\n"
    )


class TestCsvToList:
    def test_converts_with_explicit_output(
        self, cli: FABulous_CLI, tmp_path: Path
    ) -> None:
        csv_file = tmp_path / "m.csv"
        _write_csv(csv_file)
        out = tmp_path / "out.list"

        run_cmd(cli, f"csv_to_list {csv_file} {out}")

        assert cli.exit_code == 0
        assert out.read_text().splitlines()[1:] == ["A0,B2", "A1,B0"]

    def test_default_output_swaps_suffix(
        self, cli: FABulous_CLI, tmp_path: Path
    ) -> None:
        csv_file = tmp_path / "m.csv"
        _write_csv(csv_file)

        run_cmd(cli, f"csv_to_list {csv_file}")

        assert cli.exit_code == 0
        assert (tmp_path / "m.list").exists()


class TestListToCsv:
    def test_standalone_parses_back(self, cli: FABulous_CLI, tmp_path: Path) -> None:
        list_file = tmp_path / "m.list"
        create_switchmatrix_list(list_file, [("A0", "B0"), ("A1", "B1"), ("A0", "B2")])
        csv_file = tmp_path / "m.csv"

        run_cmd(cli, f"list_to_csv {list_file} {csv_file}")

        assert cli.exit_code == 0
        assert parseMatrix(csv_file, "m") == {"A0": ["B0", "B2"], "A1": ["B1"]}

    def test_default_output_swaps_suffix(
        self, cli: FABulous_CLI, tmp_path: Path
    ) -> None:
        list_file = tmp_path / "m.list"
        create_switchmatrix_list(list_file, [("A0", "B0")])

        run_cmd(cli, f"list_to_csv {list_file}")

        assert cli.exit_code == 0
        assert (tmp_path / "m.csv").exists()

    def test_standalone_derives_tile_name_without_switch_matrix_suffix(
        self, cli: FABulous_CLI, tmp_path: Path
    ) -> None:
        # Switch matrix lists are named <TILE>_switch_matrix.list; the standalone
        # path strips that suffix for the CSV tile name. parseMatrix raises unless
        # the header's first cell matches, so passing "LUT4AB" proves the strip.
        list_file = tmp_path / "LUT4AB_switch_matrix.list"
        create_switchmatrix_list(list_file, [("A0", "B0")])
        csv_file = tmp_path / "out.csv"

        run_cmd(cli, f"list_to_csv {list_file} {csv_file}")

        assert cli.exit_code == 0
        assert parseMatrix(csv_file, "LUT4AB") == {"A0": ["B0"]}

    def test_standalone_does_not_bootstrap_from_tile(
        self, cli: FABulous_CLI, tmp_path: Path, mocker: MockerFixture
    ) -> None:
        boot = mocker.patch(
            "fabulous.fabulous_cli.cmd_conversion.bootstrap_switch_matrix"
        )
        list_file = tmp_path / "m.list"
        create_switchmatrix_list(list_file, [("A0", "B0")])

        run_cmd(cli, f"list_to_csv {list_file} {tmp_path / 'm.csv'}")

        boot.assert_not_called()

    def test_with_tile_bootstraps_from_fabric(
        self, cli: FABulous_CLI, tmp_path: Path, mocker: MockerFixture
    ) -> None:
        list_file = tmp_path / "m.list"
        create_switchmatrix_list(list_file, [("A0", "B0")])
        csv_file = tmp_path / "m.csv"
        boot = mocker.patch(
            "fabulous.fabulous_cli.cmd_conversion.bootstrap_switch_matrix",
            side_effect=lambda tile, path: bootstrap_matrix_from_list(
                list_file, path, tile.name
            ),
        )

        run_cmd(cli, f"list_to_csv {list_file} {csv_file} --tile {TILE}")

        assert cli.exit_code == 0
        boot.assert_called_once()
        assert boot.call_args.args[0].name == TILE

    def test_preserve_order_flag(self, cli: FABulous_CLI, tmp_path: Path) -> None:
        list_file = tmp_path / "m.list"
        create_switchmatrix_list(list_file, [("A0", "B0"), ("A0", "B1"), ("A0", "B2")])
        csv_file = tmp_path / "m.csv"

        run_cmd(cli, f"list_to_csv {list_file} {csv_file} --preserve-order")

        assert cli.exit_code == 0
        # preserved per-row index makes the last .list entry sort first
        assert parseMatrix(csv_file, "m") == {"A0": ["B2", "B1", "B0"]}

    def test_with_tile_requires_loaded_fabric(
        self, cli: FABulous_CLI, tmp_path: Path
    ) -> None:
        cli.fabricLoaded = False
        list_file = tmp_path / "m.list"
        create_switchmatrix_list(list_file, [("A0", "B0")])

        run_cmd(cli, f"list_to_csv {list_file} {tmp_path / 'm.csv'} --tile {TILE}")

        assert cli.exit_code != 0


def test_round_trip_through_cli(cli: FABulous_CLI, tmp_path: Path) -> None:
    connections = [("A0", "B0"), ("A1", "B1"), ("A0", "B2")]
    list_file = tmp_path / "m.list"
    create_switchmatrix_list(list_file, connections)
    csv_file = tmp_path / "m.csv"
    back = tmp_path / "back.list"

    run_cmd(cli, f"list_to_csv {list_file} {csv_file}")
    run_cmd(cli, f"csv_to_list {csv_file} {back}")

    assert set(parseList(back)) == set(connections)

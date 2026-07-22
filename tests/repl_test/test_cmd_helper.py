"""Tests for the HelperCommandSet inspection commands (print_bel, print_tile)."""

import pytest

from fabulous.fabulous_repl.fabulous_repl import FABulousREPL
from tests.conftest import normalize_and_check_for_errors, run_cmd
from tests.repl_test.conftest import TILE


def _complete_names(repl: FABulousREPL, command: str, dest: str) -> list[str]:
    """Return the completion candidates for a CommandSet command's argument.

    Pulls the completer off the built parser and calls it with the owning
    CommandSet as `self` (what cmd2 passes at completion time), so the test
    exercises the real completer wiring.
    """
    parser = repl.command_parsers.get(getattr(repl, f"do_{command}"))
    action = next(a for a in parser._actions if a.dest == dest)  # noqa: SLF001
    cmd_set = repl.find_commandset_for_command(command)
    return list(action.get_completer()(cmd_set))


def test_print_tile_logs_object(
    cli: FABulousREPL, caplog: pytest.LogCaptureFixture
) -> None:
    """print_tile logs the resolved tile object without error."""
    run_cmd(cli, f"print_tile {TILE}")
    log = normalize_and_check_for_errors(caplog.text)
    assert any(TILE in line for line in log)
    assert cli.exit_code == 0


def test_print_bel_logs_object(
    cli: FABulousREPL, caplog: pytest.LogCaptureFixture
) -> None:
    """print_bel logs the resolved bel object without error."""
    bel_name = next(iter(cli.fabulousAPI.getBels())).name
    run_cmd(cli, f"print_bel {bel_name}")
    normalize_and_check_for_errors(caplog.text)
    assert cli.exit_code == 0


def test_print_tile_not_found(
    cli: FABulousREPL, caplog: pytest.LogCaptureFixture
) -> None:
    """print_tile on an unknown tile fails with an informative error."""
    run_cmd(cli, "print_tile DOES_NOT_EXIST")
    assert cli.exit_code == 1
    assert "not found" in caplog.text


def test_print_bel_not_found(
    cli: FABulousREPL, caplog: pytest.LogCaptureFixture
) -> None:
    """print_bel on an unknown bel fails with an informative error."""
    run_cmd(cli, "print_bel DOES_NOT_EXIST")
    assert cli.exit_code == 1
    assert "not found" in caplog.text


def test_tile_completer_returns_tile_names(cli: FABulousREPL) -> None:
    """The tile completer offers tile names (strings), reaching app state via _cmd."""
    names = _complete_names(cli, "print_tile", "tile")
    assert TILE in names
    assert all(isinstance(n, str) for n in names)


def test_bel_completer_returns_bel_names(cli: FABulousREPL) -> None:
    """The bel completer offers bel names (strings), reaching app state via _cmd."""
    names = _complete_names(cli, "print_bel", "bel")
    expected = {bel.name for bel in cli.fabulousAPI.getBels()}
    assert set(names) == expected
    assert all(isinstance(n, str) for n in names)

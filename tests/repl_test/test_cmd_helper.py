"""Tests for the HelperCommandSet inspection commands (print_bel, print_tile)."""

import pytest

from fabulous.fabulous_repl.fabulous_repl import FABulousREPL
from tests.conftest import run_cmd
from tests.repl_test.conftest import TILE


def _complete_names(repl: FABulousREPL, command: str, dest: str) -> list[str]:
    """Return the completion candidates for a CommandSet command's argument.

    Pulls the completer off the built parser and calls it with the owning
    CommandSet as ``self`` (what cmd2 passes at completion time), so the test
    exercises the real completer wiring.
    """
    parser = repl.command_parsers.get(getattr(repl, f"do_{command}"))
    action = next(a for a in parser._actions if a.dest == dest)  # noqa: SLF001
    cmd_set = repl.find_commandset_for_command(command)
    return list(action.get_completer()(cmd_set))


def test_print_tile_logs_object(
    cli: FABulousREPL, caplog: pytest.LogCaptureFixture
) -> None:
    """print_tile logs the pretty-printed tile object it resolved."""
    caplog.clear()
    run_cmd(cli, f"print_tile {TILE}")

    assert cli.exit_code == 0
    assert caplog.records[-1].message.startswith(f"\nTile(name='{TILE}',\n")


def test_print_bel_logs_object(
    cli: FABulousREPL, caplog: pytest.LogCaptureFixture
) -> None:
    """print_bel logs the pretty-printed bel object it resolved."""
    bel_name = "LUT4c_frame_config_dffesr"
    caplog.clear()
    run_cmd(cli, f"print_bel {bel_name}")

    assert cli.exit_code == 0
    message = caplog.records[-1].message
    assert message.startswith("\nBel(src=")
    assert f"\n    name='{bel_name}',\n" in message


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
    """The tile completer offers the fabric's tile names, reaching app state via _cmd.

    Supertiles (`DSP`) are offered as their sub-tiles only, although print_tile
    accepts the supertile name too.
    """
    names = _complete_names(cli, "print_tile", "tile")
    assert sorted(names) == [
        "DSP_bot",
        "DSP_top",
        "LUT4AB",
        "N_term_DSP",
        "N_term_RAM_IO",
        "N_term_single",
        "N_term_single2",
        "RAM_IO",
        "RegFile",
        "S_term_DSP",
        "S_term_RAM_IO",
        "S_term_single",
        "S_term_single2",
        "W_IO",
    ]


def test_bel_completer_returns_bel_names(cli: FABulousREPL) -> None:
    """The bel completer offers every bel module of the fabric, via _cmd."""
    names = _complete_names(cli, "print_bel", "bel")
    assert set(names) == {
        "Config_access",
        "IO_1_bidirectional_frame_config_pass",
        "InPass4_frame_config_mux",
        "LUT4c_frame_config_dffesr",
        "MULADD",
        "MUX8LUT_frame_config_mux",
        "OutPass4_frame_config_mux",
        "RegFile_32x4",
    }

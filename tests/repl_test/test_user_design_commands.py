"""Tests for the deprecated user-design commands.

Each one is a shim that rewrites its legacy arguments into a `compile_design`
invocation, so the contract worth pinning is the command string it forwards.
"""

import pytest
from pytest_mock import MockerFixture

from fabulous.fabulous_repl.fabulous_repl import FABulousREPL

SYNTH_CASES = [
    (
        "a.v -nofsm -noflatten",
        'compile_design a.v --synth-only --synth-extra-args "-lut 4 -nofsm -noflatten"',
    ),
    (
        "a.v b.v -top mytop -lut 6 -extra-plib p1.v -extra-plib p2.v",
        "compile_design a.v b.v --synth-only -top mytop "
        '--synth-extra-args "-lut 6 -extra-plib p1.v -extra-plib p2.v"',
    ),
    (
        "a.v -carry ha -json out.json",
        "compile_design a.v --synth-only -json out.json "
        '--synth-extra-args "-lut 4 -carry ha"',
    ),
]

FORWARD_CASES = [
    ("place_and_route", "x.json", "compile_design x.json --pnr-only"),
    ("gen_bitStream_binary", "x.fasm", "compile_design x.fasm --bitgen-only"),
    ("run_FABulous_bitstream", "x.v", "compile_design x.v"),
]


@pytest.mark.parametrize(("args", "expected"), SYNTH_CASES)
def test_synthesis_translation(
    cli: FABulousREPL, mocker: MockerFixture, args: str, expected: str
) -> None:
    """Legacy synthesis flags are folded into --synth-extra-args."""
    spy = mocker.patch.object(cli, "onecmd_plus_hooks")
    cli.get_command_func("synthesis")(args)
    spy.assert_called_once_with(expected)


@pytest.mark.parametrize(("command", "args", "expected"), FORWARD_CASES)
def test_deprecated_forwarding(
    cli: FABulousREPL, mocker: MockerFixture, command: str, args: str, expected: str
) -> None:
    """Each deprecated stage command forwards to the matching compile mode."""
    spy = mocker.patch.object(cli, "onecmd_plus_hooks")
    cli.get_command_func(command)(args)
    spy.assert_called_once_with(expected)

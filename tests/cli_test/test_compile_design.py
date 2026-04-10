"""Tests for FABulous CLI compile_design command."""

import argparse

import pytest
from pytest_mock import MockerFixture

from fabulous.fabulous_cli.fabulous_cli import FABulous_CLI
from tests.conftest import run_cmd


def _make_default_args(**overrides) -> argparse.Namespace:
    """Return a Namespace with all compile_design arguments set to defaults."""
    defaults = dict(
        files=[],
        top="top_wrapper",
        json=None,
        synth_only=False,
        pnr_only=False,
        bitgen_only=False,
        synth_extra_args="",
        yosys_extra_args="",
        nextpnr_extra_args="",
        yosys_synth_help=False,
        nextpnr_help=False,
    )
    defaults.update(overrides)
    return argparse.Namespace(**defaults)


@pytest.fixture
def compile_cli(
    cli: FABulous_CLI,
    mocker: MockerFixture,
) -> FABulous_CLI:
    """Extend the standard cli fixture with compile-specific project files.

    Creates Test/compile.Taskfile.yml, .FABulous/pips.txt, bel.txt and a design
    file so that do_compile_design can find everything it needs.

    run_task and get_context are patched on the module under test.
    """
    fab_dir = cli.projectDir / ".FABulous"
    test_dir = cli.projectDir / "Test"
    test_dir.mkdir(exist_ok=True)
    (test_dir / "compile.Taskfile.yml").write_text(
        "tasks:\n  compile-yosys: {}\n  compile-nextpnr: {}\n  compile-bitgen: {}\n"
    )
    (fab_dir / "pips.txt").write_text("")
    (fab_dir / "bel.txt").write_text("")

    user_design = cli.projectDir / "user_design"
    user_design.mkdir(exist_ok=True)
    (user_design / "top_wrapper.v").write_text("")
    (user_design / "my_design.v").write_text("")

    mock_ctx = mocker.MagicMock()
    mock_ctx.yosys_path = "/usr/bin/yosys"
    mock_ctx.nextpnr_path = "/usr/bin/nextpnr-generic"
    mocker.patch(
        "fabulous.fabulous_cli.cmd_compile_design.get_context",
        return_value=mock_ctx,
    )

    return cli


# ---------------------------------------------------------------------------
# Task dispatch
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("cli_flags", "expected_tasks"),
    [
        ("", ["compile-design"]),
        ("--synth-only", ["compile-yosys"]),
        ("--pnr-only", ["compile-nextpnr"]),
        ("--bitgen-only", ["compile-bitgen"]),
    ],
    ids=["full", "synth-only", "pnr-only", "bitgen-only"],
)
def test_compile_design_task_dispatch(
    compile_cli: FABulous_CLI,
    mocker: MockerFixture,
    cli_flags: str,
    expected_tasks: list[str],
) -> None:
    """Verify the correct task(s) are called for each flag combination."""
    design_file = compile_cli.projectDir / "user_design" / "my_design.v"
    mock_run_task = mocker.patch("fabulous.fabulous_cli.cmd_compile_design.run_task")

    run_cmd(compile_cli, f"compile_design {design_file} {cli_flags}")
    print(mock_run_task.call_args_list)
    assert mock_run_task.call_count == len(expected_tasks)
    actual_tasks = [c.args[0] for c in mock_run_task.call_args_list]
    assert actual_tasks == expected_tasks
    for call in mock_run_task.call_args_list:
        assert call.kwargs.get("taskfile") == "compile.Taskfile.yml"


# ---------------------------------------------------------------------------
# Task variables
# ---------------------------------------------------------------------------


def test_compile_design_task_vars(
    compile_cli: FABulous_CLI, mocker: MockerFixture
) -> None:
    """Verify all expected task variables are passed with correct values."""
    design_file = compile_cli.projectDir / "user_design" / "my_design.v"
    mock_run_task = mocker.patch("fabulous.fabulous_cli.cmd_compile_design.run_task")

    run_cmd(compile_cli, f"compile_design {design_file}")

    task_vars = mock_run_task.call_args.args[2]

    assert "synth_fabulous" in task_vars["SYNTH_CMD"]
    assert "-top top_wrapper" in task_vars["SYNTH_CMD"]
    assert task_vars["JSON_FILE"].endswith(".json")
    assert str(design_file) in task_vars["DESIGN_FILES"]
    assert task_vars["FASM_FILE"].endswith(".fasm")
    assert task_vars["LOG_FILE"].endswith("_npnr_log.txt")
    assert task_vars["YOSYS_PATH"] == "/usr/bin/yosys"
    assert task_vars["NEXTPNR_PATH"] == "/usr/bin/nextpnr-generic"
    assert str(compile_cli.projectDir) in task_vars["FAB_PROJ_ROOT"]
    assert "top_wrapper.v" in task_vars["TOP_WRAPPER_FILE"]


def test_compile_design_task_dir(
    compile_cli: FABulous_CLI, mocker: MockerFixture
) -> None:
    """Verify run_task is called with Test as the task directory."""
    design_file = compile_cli.projectDir / "user_design" / "my_design.v"
    mock_run_task = mocker.patch("fabulous.fabulous_cli.cmd_compile_design.run_task")

    run_cmd(compile_cli, f"compile_design {design_file}")

    task_dir = mock_run_task.call_args.args[1]
    assert task_dir == compile_cli.projectDir / "Test"


def test_compile_design_auto_includes_custom_prims(
    compile_cli: FABulous_CLI, mocker: MockerFixture
) -> None:
    """Verify custom_prims.v is auto-included in SYNTH_CMD when present."""
    design_file = compile_cli.projectDir / "user_design" / "my_design.v"
    custom_prims = compile_cli.projectDir / "user_design" / "custom_prims.v"
    custom_prims.write_text("")

    mock_run_task = mocker.patch("fabulous.fabulous_cli.cmd_compile_design.run_task")

    run_cmd(compile_cli, f"compile_design {design_file}")

    task_vars = mock_run_task.call_args.args[2]
    assert f"-extra-plib {custom_prims}" in task_vars["SYNTH_CMD"]


def test_compile_design_no_custom_prims(
    compile_cli: FABulous_CLI, mocker: MockerFixture
) -> None:
    """Verify SYNTH_CMD has no -extra-plib when custom_prims.v is absent."""
    design_file = compile_cli.projectDir / "user_design" / "my_design.v"
    custom_prims = compile_cli.projectDir / "user_design" / "custom_prims.v"
    custom_prims.unlink(missing_ok=True)

    mock_run_task = mocker.patch("fabulous.fabulous_cli.cmd_compile_design.run_task")

    run_cmd(compile_cli, f"compile_design {design_file}")

    task_vars = mock_run_task.call_args.args[2]
    assert "-extra-plib" not in task_vars["SYNTH_CMD"]


def test_compile_design_extra_args(
    compile_cli: FABulous_CLI, mocker: MockerFixture
) -> None:
    """Verify all extra args are forwarded correctly to task variables."""
    design_file = compile_cli.projectDir / "user_design" / "my_design.v"
    mock_run_task = mocker.patch("fabulous.fabulous_cli.cmd_compile_design.run_task")

    run_cmd(
        compile_cli,
        f"compile_design {design_file}"
        ' --synth-extra-args "-nofsm -extra-plib prims.v"'
        " --yosys-extra-args verbose_flag"
        " --nextpnr-extra-args seed42",
    )

    task_vars = mock_run_task.call_args.args[2]
    assert "-nofsm -extra-plib prims.v" in task_vars["SYNTH_CMD"]
    assert task_vars["YOSYS_EXTRA_ARGS"] == "verbose_flag"
    assert task_vars["NEXTPNR_EXTRA_ARGS"] == "seed42"


@pytest.mark.parametrize(
    "verbose, debug, expected",
    [
        (False, False, ""),
        (True, False, "--verbose"),
        (False, True, "--verbose"),
        (True, True, "--verbose"),
    ],
    ids=["quiet", "verbose", "debug", "verbose+debug"],
)
def test_compile_design_nextpnr_verbose(
    compile_cli: FABulous_CLI,
    mocker: MockerFixture,
    verbose: bool,
    debug: bool,
    expected: str,
) -> None:
    """Verify NEXTPNR_VERBOSE is set based on CLI verbose/debug flags."""
    design_file = compile_cli.projectDir / "user_design" / "my_design.v"
    compile_cli.verbose = verbose
    compile_cli.debug = debug
    mock_run_task = mocker.patch("fabulous.fabulous_cli.cmd_compile_design.run_task")

    run_cmd(compile_cli, f"compile_design {design_file}")

    task_vars = mock_run_task.call_args.args[2]
    assert task_vars["NEXTPNR_VERBOSE"] == expected


# ---------------------------------------------------------------------------
# Tool help flags
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "flag, expected_in_args",
    [
        ("--yosys-synth-help", "help synth_fabulous"),
        ("--nextpnr-help", "--help"),
    ],
    ids=["yosys", "nextpnr"],
)
def test_compile_design_tool_help(
    compile_cli: FABulous_CLI,
    mocker: MockerFixture,
    flag: str,
    expected_in_args: str,
) -> None:
    """Verify --yosys-synth-help and --nextpnr-help call the tool and skip tasks."""
    design_file = compile_cli.projectDir / "user_design" / "my_design.v"
    mock_run_task = mocker.patch("fabulous.fabulous_cli.cmd_compile_design.run_task")
    mock_subprocess = mocker.patch(
        "fabulous.fabulous_cli.cmd_compile_design.subprocess.run"
    )

    run_cmd(compile_cli, f"compile_design {design_file} {flag}")

    mock_run_task.assert_not_called()
    mock_subprocess.assert_called_once()
    assert expected_in_args in mock_subprocess.call_args.args[0]


# ---------------------------------------------------------------------------
# Error paths
# ---------------------------------------------------------------------------


def test_compile_design_no_taskfile(
    compile_cli: FABulous_CLI, mocker: MockerFixture
) -> None:
    """Verify FileNotFoundError when compile.Taskfile.yml is absent."""
    design_file = compile_cli.projectDir / "user_design" / "my_design.v"
    (compile_cli.projectDir / "Test" / "compile.Taskfile.yml").unlink()
    mocker.patch("fabulous.fabulous_cli.cmd_compile_design.run_task")

    from fabulous.fabulous_cli.cmd_compile_design import do_compile_design

    args = _make_default_args(files=[design_file])
    with pytest.raises(FileNotFoundError, match="compile.Taskfile.yml"):
        do_compile_design.__wrapped__(compile_cli, args)


def test_compile_design_nonexistent_file(
    compile_cli: FABulous_CLI, mocker: MockerFixture
) -> None:
    """Verify the command logs an error and does not call run_task for missing files."""
    mock_run_task = mocker.patch("fabulous.fabulous_cli.cmd_compile_design.run_task")
    bogus = compile_cli.projectDir / "user_design" / "does_not_exist.v"

    run_cmd(compile_cli, f"compile_design {bogus}")

    mock_run_task.assert_not_called()

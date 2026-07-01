"""Tests for FABulous CLI compile_design command."""

import argparse
from pathlib import Path

import pytest
from pytest_mock import MockerFixture

from fabulous.fabulous_repl.fabulous_repl import FABulousREPL
from tests.conftest import run_cmd


def _make_default_args(**overrides) -> argparse.Namespace:  # noqa: ANN003
    """Return a Namespace with all compile_design arguments set to defaults."""
    defaults = dict(
        files=[],
        top="top_wrapper",
        json=None,
        fasm=None,
        log=None,
        bin=None,
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
    cli: FABulousREPL,
    mocker: MockerFixture,
) -> FABulousREPL:
    """Extend the standard cli fixture with compile-specific project files.

    Creates Test/Taskfile.yml and a design file so that do_compile_design can find
    everything it needs. get_context is patched on the module under test.
    """
    test_dir = cli.projectDir / "Test"
    test_dir.mkdir(exist_ok=True)
    (test_dir / "Taskfile.yml").write_text(
        "tasks:\n"
        "  build-test-design: {}\n"
        "  run-yosys: {}\n"
        "  run-nextpnr: {}\n"
        "  run-bitgen: {}\n"
    )

    user_design = cli.projectDir / "user_design"
    user_design.mkdir(exist_ok=True)
    (user_design / "top_wrapper.v").write_text("")
    (user_design / "my_design.v").write_text("")

    mock_ctx = mocker.MagicMock()
    mock_ctx.yosys_path = "/usr/bin/yosys"
    mock_ctx.nextpnr_path = "/usr/bin/nextpnr-generic"
    mocker.patch(
        "fabulous.fabulous_repl.cmd_compile_design.get_context",
        return_value=mock_ctx,
    )

    return cli


@pytest.mark.parametrize(
    ("cli_flags", "expected_tasks"),
    [
        ("", ["build-test-design"]),
        ("--synth-only", ["run-yosys"]),
        ("--pnr-only", ["run-nextpnr"]),
        ("--bitgen-only", ["run-bitgen"]),
    ],
    ids=["full", "synth-only", "pnr-only", "bitgen-only"],
)
def test_compile_design_task_dispatch(
    compile_cli: FABulousREPL,
    mocker: MockerFixture,
    cli_flags: str,
    expected_tasks: list[str],
) -> None:
    """Verify the correct task(s) are called for each flag combination."""
    design_file = compile_cli.projectDir / "user_design" / "my_design.v"
    mock_run_task = mocker.patch("fabulous.fabulous_repl.cmd_compile_design.run_task")

    run_cmd(compile_cli, f"compile_design {design_file} {cli_flags}")
    assert mock_run_task.call_count == len(expected_tasks)
    actual_tasks = [c.args[0] for c in mock_run_task.call_args_list]
    assert actual_tasks == expected_tasks
    for call in mock_run_task.call_args_list:
        assert "taskfile" not in call.kwargs


def test_compile_design_task_vars(
    compile_cli: FABulousREPL, mocker: MockerFixture
) -> None:
    """Verify all expected task variables are passed with correct values."""
    design_file = compile_cli.projectDir / "user_design" / "my_design.v"
    mock_run_task = mocker.patch("fabulous.fabulous_repl.cmd_compile_design.run_task")

    run_cmd(compile_cli, f"compile_design {design_file}")

    task_vars = mock_run_task.call_args.args[2]

    assert task_vars["DESIGN"] == "my_design"
    assert task_vars["TOP_WRAPPER"] == "top_wrapper"
    assert str(design_file) in task_vars["DESIGN_FILES"]
    assert task_vars["JSON_FILE"].endswith(".json")
    assert task_vars["FASM_FILE"].endswith(".fasm")
    assert task_vars["BIN_FILE"].endswith(".bin")
    assert task_vars["LOG_FILE"].endswith("_npnr_log.txt")
    assert task_vars["YOSYS_PATH"] == "/usr/bin/yosys"
    assert task_vars["NEXTPNR_PATH"] == "/usr/bin/nextpnr-generic"
    assert task_vars["FAB_PROJ_ROOT"] == str(compile_cli.projectDir)
    assert "top_wrapper.v" in task_vars["TOP_WRAPPER_FILE"]
    assert task_vars["SYNTH_EXTRA_ARGS"] == ""
    assert task_vars["YOSYS_EXTRA_ARGS"] == ""
    assert task_vars["NEXTPNR_EXTRA_ARGS"] == ""


def test_compile_design_default_paths_chain_from_json(
    compile_cli: FABulousREPL, mocker: MockerFixture
) -> None:
    """Verify FASM/BIN/LOG default paths are derived from JSON_FILE."""
    design_file = compile_cli.projectDir / "user_design" / "my_design.v"
    mock_run_task = mocker.patch("fabulous.fabulous_repl.cmd_compile_design.run_task")

    run_cmd(compile_cli, f"compile_design {design_file}")

    task_vars = mock_run_task.call_args.args[2]
    json_path = Path(task_vars["JSON_FILE"])
    assert Path(task_vars["FASM_FILE"]) == json_path.with_suffix(".fasm")
    assert Path(task_vars["BIN_FILE"]) == json_path.with_suffix(".fasm").with_suffix(
        ".bin"
    )
    assert (
        Path(task_vars["LOG_FILE"])
        == json_path.parent / f"{json_path.stem}_npnr_log.txt"
    )


def test_compile_design_task_dir(
    compile_cli: FABulousREPL, mocker: MockerFixture
) -> None:
    """Verify run_task is called with Test as the task directory."""
    design_file = compile_cli.projectDir / "user_design" / "my_design.v"
    mock_run_task = mocker.patch("fabulous.fabulous_repl.cmd_compile_design.run_task")

    run_cmd(compile_cli, f"compile_design {design_file}")

    task_dir = mock_run_task.call_args.args[1]
    assert task_dir == compile_cli.projectDir / "Test"


def test_compile_design_extra_args(
    compile_cli: FABulousREPL, mocker: MockerFixture
) -> None:
    """Verify all extra args are forwarded verbatim to task variables."""
    design_file = compile_cli.projectDir / "user_design" / "my_design.v"
    mock_run_task = mocker.patch("fabulous.fabulous_repl.cmd_compile_design.run_task")

    run_cmd(
        compile_cli,
        f"compile_design {design_file}"
        ' --synth-extra-args "-nofsm -extra-plib prims.v"'
        " --yosys-extra-args verbose_flag"
        " --nextpnr-extra-args seed42",
    )

    task_vars = mock_run_task.call_args.args[2]
    assert task_vars["SYNTH_EXTRA_ARGS"] == "-nofsm -extra-plib prims.v"
    assert task_vars["YOSYS_EXTRA_ARGS"] == "verbose_flag"
    assert task_vars["NEXTPNR_EXTRA_ARGS"] == "seed42"


@pytest.mark.parametrize(
    ("verbose", "debug", "expected"),
    [
        (False, False, ""),
        (True, False, "--verbose"),
        (False, True, "--verbose"),
        (True, True, "--verbose"),
    ],
    ids=["quiet", "verbose", "debug", "verbose+debug"],
)
def test_compile_design_nextpnr_verbose(
    compile_cli: FABulousREPL,
    mocker: MockerFixture,
    verbose: bool,
    debug: bool,
    expected: str,
) -> None:
    """Verify NEXTPNR_VERBOSE is set based on CLI verbose/debug flags."""
    design_file = compile_cli.projectDir / "user_design" / "my_design.v"
    compile_cli.verbose = verbose
    compile_cli.debug = debug
    mock_run_task = mocker.patch("fabulous.fabulous_repl.cmd_compile_design.run_task")

    run_cmd(compile_cli, f"compile_design {design_file}")

    task_vars = mock_run_task.call_args.args[2]
    assert task_vars["NEXTPNR_VERBOSE"] == expected


def test_compile_design_top_override(
    compile_cli: FABulousREPL, mocker: MockerFixture
) -> None:
    """Verify -top propagates to the TOP_WRAPPER task var."""
    design_file = compile_cli.projectDir / "user_design" / "my_design.v"
    mock_run_task = mocker.patch("fabulous.fabulous_repl.cmd_compile_design.run_task")

    run_cmd(compile_cli, f"compile_design {design_file} -top my_top")

    task_vars = mock_run_task.call_args.args[2]
    assert task_vars["TOP_WRAPPER"] == "my_top"


@pytest.mark.parametrize(
    ("flag", "filename", "task_var"),
    [
        ("-json", "custom.json", "JSON_FILE"),
        ("-fasm", "custom.fasm", "FASM_FILE"),
        ("-bin", "custom.bin", "BIN_FILE"),
        ("-log", "custom_log.txt", "LOG_FILE"),
    ],
    ids=["json", "fasm", "bin", "log"],
)
def test_compile_design_relative_output_override(
    compile_cli: FABulousREPL,
    mocker: MockerFixture,
    flag: str,
    filename: str,
    task_var: str,
) -> None:
    """Relative output paths resolve against projectDir."""
    design_file = compile_cli.projectDir / "user_design" / "my_design.v"
    mock_run_task = mocker.patch("fabulous.fabulous_repl.cmd_compile_design.run_task")

    run_cmd(compile_cli, f"compile_design {design_file} {flag} {filename}")

    task_vars = mock_run_task.call_args.args[2]
    expected = (compile_cli.projectDir / filename).resolve()
    assert task_vars[task_var] == str(expected)


@pytest.mark.parametrize(
    ("flag", "filename", "task_var"),
    [
        ("-json", "abs.json", "JSON_FILE"),
        ("-fasm", "abs.fasm", "FASM_FILE"),
        ("-bin", "abs.bin", "BIN_FILE"),
        ("-log", "abs.log", "LOG_FILE"),
    ],
    ids=["json", "fasm", "bin", "log"],
)
def test_compile_design_absolute_output_override(
    compile_cli: FABulousREPL,
    mocker: MockerFixture,
    tmp_path: Path,
    flag: str,
    filename: str,
    task_var: str,
) -> None:
    """Absolute output paths are preserved unchanged."""
    design_file = compile_cli.projectDir / "user_design" / "my_design.v"
    abs_path = tmp_path / filename
    mock_run_task = mocker.patch("fabulous.fabulous_repl.cmd_compile_design.run_task")

    run_cmd(compile_cli, f"compile_design {design_file} {flag} {abs_path}")

    task_vars = mock_run_task.call_args.args[2]
    assert task_vars[task_var] == str(abs_path)


@pytest.mark.parametrize(
    ("flag", "expected_in_args"),
    [
        ("--yosys-synth-help", "help synth_fabulous"),
        ("--nextpnr-help", "--help"),
    ],
    ids=["yosys", "nextpnr"],
)
def test_compile_design_tool_help(
    compile_cli: FABulousREPL,
    mocker: MockerFixture,
    flag: str,
    expected_in_args: str,
) -> None:
    """Verify --yosys-synth-help and --nextpnr-help call the tool and skip tasks."""
    design_file = compile_cli.projectDir / "user_design" / "my_design.v"
    mock_run_task = mocker.patch("fabulous.fabulous_repl.cmd_compile_design.run_task")
    mock_subprocess = mocker.patch(
        "fabulous.fabulous_repl.cmd_compile_design.subprocess.run"
    )

    run_cmd(compile_cli, f"compile_design {design_file} {flag}")

    mock_run_task.assert_not_called()
    mock_subprocess.assert_called_once()
    assert expected_in_args in mock_subprocess.call_args.args[0]


def test_compile_design_no_taskfile(
    compile_cli: FABulousREPL, mocker: MockerFixture
) -> None:
    """Verify FileNotFoundError when Test/Taskfile.yml is absent."""
    design_file = compile_cli.projectDir / "user_design" / "my_design.v"
    (compile_cli.projectDir / "Test" / "Taskfile.yml").unlink()
    mocker.patch("fabulous.fabulous_repl.cmd_compile_design.run_task")

    from fabulous.fabulous_repl.cmd_compile_design import do_compile_design

    args = _make_default_args(files=[design_file])
    with pytest.raises(FileNotFoundError, match="Taskfile.yml"):
        do_compile_design.__wrapped__(compile_cli, args)


def test_compile_design_nonexistent_file(
    compile_cli: FABulousREPL, mocker: MockerFixture
) -> None:
    """Verify the command logs an error and does not call run_task for missing files."""
    mock_run_task = mocker.patch("fabulous.fabulous_repl.cmd_compile_design.run_task")
    bogus = compile_cli.projectDir / "user_design" / "does_not_exist.v"

    run_cmd(compile_cli, f"compile_design {bogus}")

    mock_run_task.assert_not_called()

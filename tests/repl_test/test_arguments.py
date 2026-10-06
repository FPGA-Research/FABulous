"""Test module for FABulous CLI argument processing and functionality.

This module contains comprehensive tests for the FABulous command-line interface,
covering project creation, script execution, command-line flags, and error handling.
"""

import io
import os
import sys
import tarfile
from collections.abc import Callable
from importlib.metadata import version
from pathlib import Path
from subprocess import CompletedProcess, run
from typing import Self

import pytest
import typer
from dotenv import dotenv_values, set_key
from loguru import logger
from packaging.version import Version
from pytest_mock import MockerFixture

from fabulous.fabulous import main
from fabulous.fabulous_api import FABulous_API
from fabulous.fabulous_repl import FABulousREPL
from fabulous.fabulous_repl.helper import setup_logger
from fabulous.fabulous_settings import init_context, reset_context


@pytest.fixture(autouse=True)
def stub_fabric_loading(monkeypatch: pytest.MonkeyPatch) -> None:
    """Skip the real fabric load for every test in this module."""

    def stub(*_args: object) -> None:
        raise RuntimeError("Fabric loading is stubbed out in the argument tests")

    monkeypatch.setattr(FABulous_API, "loadFabric", stub)


@pytest.mark.parametrize(
    (
        "argv",
        "writer_lang",
        "expected_code",
    ),
    [
        pytest.param(
            ["FABulous", "create-project", "{project}"], None, 0, id="typer-no-writer"
        ),
        pytest.param(
            ["FABulous", "c", "{project}"], None, 0, id="typer-no-writer-alias"
        ),
        pytest.param(["FABulous", "create-project"], None, 2, id="typer-no-project"),
        pytest.param(
            ["FABulous", "--createProject", "{project}"], None, 0, id="legacy-no-writer"
        ),
        pytest.param(["FABulous", "--createProject"], None, 2, id="legacy-no-project"),
        pytest.param(
            ["FABulous", "-w", "vhdl", "--createProject", "{project}"],
            "vhdl",
            0,
            id="legacy-writer",
        ),
        pytest.param(
            ["FABulous", "create-project", "-w", "vhdl", "{project}"],
            "vhdl",
            0,
            id="typer-writer",
        ),
        pytest.param(
            ["FABulous", "create-project", "-w", "invalid", "{project}"],
            "vhdl",
            2,
            id="typer-invalid-writer",
        ),
        pytest.param(
            ["FABulous", "-w", "invalid", "--createProject", "{project}"],
            "vhdl",
            2,
            id="legacy-invalid-writer",
        ),
        pytest.param(
            ["FABulous", "-w", "VERILOG", "--createProject", "{project}"],
            "verilog",
            0,
            id="case-insensitive-legacy",
        ),
        pytest.param(
            ["FABulous", "create-project", "{project}", "-w", "VERILOG"],
            "verilog",
            0,
            id="case-insensitive-typer",
        ),
    ],
)
def test_create_project(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    writer_lang: str,
    argv: list[str],
    expected_code: int,
) -> None:
    project_dir = tmp_path / "test_prj"

    test_argv = [i.replace("{project}", str(project_dir)) for i in argv]

    monkeypatch.setattr(sys, "argv", test_argv)
    with pytest.raises(SystemExit) as exc_info:
        main()
    assert exc_info.value.code == expected_code

    if expected_code == 0:
        # Success path: verify project + writer recorded
        assert project_dir.exists()
        env_text = (project_dir / ".FABulous" / ".env").read_text().lower()
        if writer_lang == "vhdl":
            assert writer_lang in env_text
        else:
            assert "verilog" in env_text


@pytest.mark.parametrize(
    ("argv", "start_dir", "expected_code", "expected_dispatch", "expected_out"),
    [
        pytest.param(
            ["FABulous", "{project}", "--FABulousScript", "{file}"],
            None,
            0,
            ["run_script {file}", "help"],
            None,
            id="fab-legacy",
        ),
        pytest.param(
            ["FABulous", "-p", "{project}", "script", "-t", "fabulous", "{file}"],
            None,
            0,
            ["run_script {file}", "help"],
            None,
            id="fab-typer",
        ),
        pytest.param(
            ["FABulous", "--FABulousScript", "{file}"],
            "project",
            0,
            ["run_script {file}", "help"],
            None,
            id="fab-cwd-project",
        ),
        pytest.param(
            ["FABulous", "-p", "{project}", "script", "{missing}"],
            None,
            2,
            None,
            None,
            id="fab-nonexistent",
        ),
        pytest.param(
            ["FABulous", "-p", "{project}", "script", "-t", "unknown", "{file}"],
            None,
            2,
            None,
            None,
            id="type-invalid",
        ),
        pytest.param(
            ["FABulous", "{project}", "--TCLScript", "{tcl}"],
            None,
            0,
            ["run_tcl {tcl}"],
            "Hello from TCL\n",
            id="tcl-legacy",
        ),
        pytest.param(
            ["FABulous", "-p", "{project}", "script", "{tcl}"],
            None,
            0,
            ["run_tcl {tcl}"],
            "Hello from TCL\n",
            id="tcl-typer",
        ),
        pytest.param(
            ["FABulous", "--FABulousScript", "{file}"],
            "nonproject",
            1,
            None,
            "not a valid FABulous project",
            id="fab-cwd-nonproject",
        ),
    ],
)
def test_script_execution(
    tmp_path: Path,
    project: Path,
    monkeypatch: pytest.MonkeyPatch,
    mocker: MockerFixture,
    capfd: pytest.CaptureFixture[str],
    argv: list[str],
    start_dir: str | None,
    expected_code: int,
    expected_dispatch: list[str] | None,
    expected_out: str | None,
) -> None:
    """The script runs through `run_script` or `run_tcl` and its commands execute.

    `None` for `expected_dispatch` means the REPL is never started.
    """
    fab_script = tmp_path / "test_script.fab"
    fab_script.write_text("# Test FABulous script\nhelp\n")
    tcl_script = tmp_path / "test_script.tcl"
    tcl_script.write_text(
        '# TCL script with FABulous commands\nputs "Hello from TCL"\n'
    )
    missing = tmp_path / "missing_script.fab"
    spy = mocker.spy(FABulousREPL, "onecmd_plus_hooks")

    def fill(template: str) -> str:
        return (
            template.replace("{project}", str(project))
            .replace("{file}", str(fab_script.resolve()))
            .replace("{tcl}", str(tcl_script.resolve()))
            .replace("{missing}", str(missing))
        )

    if start_dir == "project":
        monkeypatch.chdir(project)
    elif start_dir == "nonproject":
        nonproj = tmp_path / "nonproj"
        nonproj.mkdir()
        monkeypatch.chdir(nonproj)

    monkeypatch.setattr(sys, "argv", [fill(arg) for arg in argv])
    with pytest.raises(SystemExit) as exc_info:
        main()

    assert exc_info.value.code == expected_code
    dispatched = [call.args[1] for call in spy.call_args_list]
    if expected_dispatch is None:
        assert dispatched == []
    else:
        assert dispatched == ["load_fabric", *map(fill, expected_dispatch)]
    if expected_out is not None:
        assert expected_out in capfd.readouterr().out


@pytest.mark.parametrize(
    ("argv_builder", "expected_code"),
    [
        pytest.param(
            lambda prj, log: [
                "FABulous",
                str(prj),
                "--commands",
                "help",
                "-log",
                str(log),
            ],
            0,
            id="legacy",
        ),
        pytest.param(
            lambda prj, log: [
                "FABulous",
                "-p",
                str(prj),
                "--log",
                str(log),
                "run",
                "help",
            ],
            0,
            id="typer",
        ),
    ],
)
def test_logging_file_creation(
    tmp_path: Path,
    project: Path,
    monkeypatch: pytest.MonkeyPatch,
    argv_builder: Callable[[Path, Path], list[str]],
    expected_code: int,
) -> None:
    """The log file receives the run's INFO records in both styles."""
    log_file = tmp_path / "cli_test.log"
    test_args = argv_builder(project, log_file)
    monkeypatch.setattr(sys, "argv", test_args)

    with pytest.raises(SystemExit) as exc_info:
        main()

    assert exc_info.value.code == expected_code
    log_lines = log_file.read_text().splitlines()
    assert f"INFO: Setting current working directory to: {project}" in log_lines
    assert 'INFO: Commands "help" executed successfully' in log_lines


class _FakeStream(io.StringIO):
    """Stream with a chosen tty status, which is what loguru reads to pick colour."""

    def __init__(self, *, is_tty: bool) -> None:
        super().__init__()
        self._is_tty = is_tty

    def isatty(self) -> bool:
        """Report the chosen tty status.

        Returns
        -------
        bool
            True when the stream should be treated as a terminal.
        """
        return self._is_tty


@pytest.mark.parametrize(
    ("is_tty", "expect_escapes"),
    [
        pytest.param(True, True, id="terminal"),
        pytest.param(False, False, id="redirected"),
    ],
)
def test_stdout_colour_follows_tty(
    monkeypatch: pytest.MonkeyPatch, is_tty: bool, expect_escapes: bool
) -> None:
    """Markup becomes escape codes on a terminal and plain text when redirected."""
    monkeypatch.delenv("FABULOUS_TESTING", raising=False)
    stream = _FakeStream(is_tty=is_tty)
    monkeypatch.setattr(sys, "stdout", stream)

    setup_logger(0, False)
    logger.warning("check the colour")
    written = stream.getvalue()

    assert "check the colour" in written
    assert ("\x1b" in written) is expect_escapes


def test_log_file_is_an_extra_sink(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The log file takes the same records as stdout, without the colour."""
    monkeypatch.delenv("FABULOUS_TESTING", raising=False)
    stream = _FakeStream(is_tty=True)
    monkeypatch.setattr(sys, "stdout", stream)
    log_file = tmp_path / "extra.log"

    setup_logger(0, False, log_file)
    logger.warning("to both")
    logger.remove()

    assert "\x1b" in stream.getvalue()
    assert "to both" in stream.getvalue()
    assert log_file.read_text() == "WARNING | to both\n"


@pytest.mark.parametrize(
    ("argv", "verbose_format"),
    [
        pytest.param(
            ["FABulous", "{project}", "--commands", "help"], False, id="legacy-quiet"
        ),
        pytest.param(
            ["FABulous", "{project}", "--commands", "help", "-v"],
            True,
            id="legacy-v",
        ),
        pytest.param(
            ["FABulous", "{project}", "--commands", "help", "-vv"],
            True,
            id="legacy-vv",
        ),
        pytest.param(["FABulous", "-p", "{project}", "run", "help"], False, id="quiet"),
        pytest.param(
            ["FABulous", "-p", "{project}", "-v", "run", "help"], True, id="typer-v"
        ),
        pytest.param(
            ["FABulous", "-p", "{project}", "-vv", "run", "help"], True, id="typer-vv"
        ),
        pytest.param(
            ["FABulous", "-p", "{project}", "run", "help", "-v"],
            True,
            id="typer-v-after-command",
        ),
    ],
)
def test_verbose_mode(
    project: Path,
    monkeypatch: pytest.MonkeyPatch,
    capfd: pytest.CaptureFixture[str],
    argv: list[str],
    verbose_format: bool,
) -> None:
    """`-v` switches stdout records to the module:function:line format."""
    # FABULOUS_TESTING forces the plain format whatever the verbosity.
    monkeypatch.delenv("FABULOUS_TESTING")
    test_args = [arg.replace("{project}", str(project)) for arg in argv]
    monkeypatch.setattr(sys, "argv", test_args)

    with pytest.raises(SystemExit) as exc_info:
        main()

    assert exc_info.value.code == 0
    out = capfd.readouterr().out
    assert ("[fabulous.fabulous:run_cmd:" in out) is verbose_format


@pytest.mark.parametrize(
    ("argv", "debug_records"),
    [
        pytest.param(
            ["FABulous", "{project}", "--commands", "help"], False, id="legacy-quiet"
        ),
        pytest.param(
            ["FABulous", "{project}", "--commands", "help", "--debug"],
            True,
            id="legacy",
        ),
        pytest.param(["FABulous", "-p", "{project}", "run", "help"], False, id="quiet"),
        pytest.param(
            ["FABulous", "-p", "{project}", "--debug", "run", "help"],
            True,
            id="typer",
        ),
    ],
)
def test_debug_mode(
    project: Path,
    monkeypatch: pytest.MonkeyPatch,
    capfd: pytest.CaptureFixture[str],
    argv: list[str],
    debug_records: bool,
) -> None:
    """`--debug` lowers the stdout sink to DEBUG in both legacy and Typer forms."""
    test_args = [arg.replace("{project}", str(project)) for arg in argv]
    monkeypatch.setattr(sys, "argv", test_args)

    with pytest.raises(SystemExit) as exc_info:
        main()

    assert exc_info.value.code == 0
    out_lines = capfd.readouterr().out.splitlines()
    # the DEBUG sink writes to capfd's stream, which closes before teardown logs
    logger.remove()
    assert any(line.startswith("DEBUG: ") for line in out_lines) is debug_records


@pytest.mark.parametrize(
    ("flag", "expected"),
    [
        ("-vv", {"verbose": True, "debug": False}),
        ("--debug", {"verbose": False, "debug": True}),
    ],
    ids=["vv", "debug"],
)
def test_start_flags_reach_repl(
    project: Path,
    monkeypatch: pytest.MonkeyPatch,
    flag: str,
    expected: dict[str, bool],
) -> None:
    """`-vv` and `--debug` on the command line configure the started REPL."""
    started: dict[str, bool] = {}

    def record_cmdloop(repl: FABulousREPL) -> None:
        started.update(verbose=repl.verbose, debug=repl.debug)

    monkeypatch.setattr(FABulousREPL, "cmdloop", record_cmdloop)
    monkeypatch.setattr(sys, "argv", ["FABulous", "-p", str(project), flag, "start"])

    with pytest.raises(SystemExit):
        main()

    assert started == expected


@pytest.mark.parametrize(
    ("argv_base", "commands_or_script", "expected_count", "search_text"),
    [
        pytest.param(
            ["FABulous", "--force", "{project}", "--commands"],
            "load_fabric non_existent",
            1,
            "non_existent",
            id="single-command",
        ),
        pytest.param(
            ["FABulous", "--force", "{project}", "--commands"],
            "load_fabric non_exist; load_fabric non_exist",
            2,
            "non_exist",
            id="multiple-commands",
        ),
        pytest.param(
            ["FABulous", "--force", "{project}", "--FABulousScript"],
            "load_fabric non_exist.csv\nload_fabric non_exist.csv\n",
            3,
            "INFO: Loading fabric",
            id="script",
        ),
        pytest.param(
            ["FABulous", "-p", "{project}", "run", "--force"],
            "load_fabric non_existent",
            1,
            "non_existent",
            id="single-command",
        ),
    ],
)
def test_force_flag(
    project: Path,
    tmp_path: Path,
    argv_base: list[str],
    commands_or_script: str,
    expected_count: int,
    search_text: str,
) -> None:
    """Test force flag functionality with different scenarios."""

    # Replace project placeholder
    argv = [arg.replace("{project}", str(project)) for arg in argv_base]

    # Handle script vs commands
    if "--FABulousScript" in argv:
        # Create script file
        script_file = tmp_path / "test.fs"
        with script_file.open("w") as f:
            f.write(commands_or_script)
        argv.append(str(script_file))
    else:
        # Add commands and force flag
        argv.append(commands_or_script)

    result = run(argv, capture_output=True, text=True)

    assert result.stdout.count(search_text) == expected_count
    assert result.returncode == 1


@pytest.mark.parametrize(
    ("argv", "expected_requests", "expected_code", "expected_dest"),
    [
        pytest.param(
            ["FABulous", "{project}", "--install_oss_cad_suite"],
            2,
            0,
            "{project}",
            id="legacy",
        ),
        pytest.param(
            ["FABulous", "install", "oss-cad-suite", "{project}"],
            2,
            0,
            "{project}",
            id="typer-project",
        ),
        pytest.param(
            ["FABulous", "install", "oss-cad-suite"],
            2,
            0,
            "{user_dir}",
            id="default-dir",
        ),
        pytest.param(
            ["FABulous", "install", "oss-cad-suite", "{install_dir}"],
            2,
            0,
            "{install_dir}",
            id="explicit-dir",
        ),
        pytest.param(
            ["FABulous", "install", "oss-cad-suite", "{install_dir}"],
            1,
            1,
            None,
            id="error",
        ),
    ],
)
def test_install_oss_cad_suite(
    project: Path,
    tmp_path: Path,
    mocker: MockerFixture,
    monkeypatch: pytest.MonkeyPatch,
    argv: list[str],
    expected_requests: int,
    expected_code: int,
    expected_dest: str | None,
) -> None:
    """The suite is extracted into the chosen directory and recorded globally.

    Network and archive access are mocked; `expected_dest` of `None` means the
    install fails before anything is extracted or recorded.
    """
    install_dir = tmp_path / "oss"
    tmp_user_dir = tmp_path / "user_config"

    def fill(template: str) -> str:
        return (
            template.replace("{project}", str(project))
            .replace("{install_dir}", str(install_dir))
            .replace("{user_dir}", str(tmp_user_dir))
        )

    test_argv = [fill(s) for s in argv]
    # install_oss_cad_suite appends to PATH in place
    monkeypatch.setenv("PATH", os.environ["PATH"])
    extracted_to: list[str] = []

    # Common network and archive mocks
    class MockRequestOK:
        status_code = 200

        def json(self) -> dict:
            return {
                "assets": [
                    {
                        "name": ".tar.gz x64 linux darwin windows arm64",
                        "browser_download_url": "./something.tgz",
                    }
                ]
            }

        def iter_content(self, chunk_size: int = 1024) -> list:  # noqa: ARG002
            return []

    class MockRequestFail:
        status_code = 500

        def json(self) -> dict:  # noqa: D401
            # Not used in fail path
            return {}

    # Mock tarfile
    class MockTarFile:
        def __enter__(self) -> Self:
            return self

        def __exit__(self, *_args: object) -> None:
            pass

        def extractall(self, path: str) -> None:
            extracted_to.append(str(path))

    def mock_open(*_args: object, **_kwargs: object) -> MockTarFile:
        return MockTarFile()

    monkeypatch.setattr(tarfile, "open", mock_open)

    if expected_dest is None:
        m = mocker.patch("requests.get", return_value=MockRequestFail())
    else:
        m = mocker.patch("requests.get", side_effect=[MockRequestOK(), MockRequestOK()])

    monkeypatch.setattr("fabulous.fabulous.FAB_USER_CONFIG_DIR", tmp_user_dir)

    monkeypatch.setattr(sys, "argv", test_argv)
    with pytest.raises(SystemExit) as exc_info:
        main()

    assert exc_info.value.code == expected_code
    assert m.call_count == expected_requests
    # tests/conftest.py points the global config dir at tmp_path/.fabulous
    global_env = dotenv_values(tmp_path / ".fabulous" / ".env")
    if expected_dest is None:
        assert extracted_to == []
        assert "FAB_OSS_CAD_SUITE" not in global_env
    else:
        dest = Path(fill(expected_dest))
        assert extracted_to == [str(dest)]
        assert global_env["FAB_OSS_CAD_SUITE"] == str(dest / "oss-cad-suite")


def test_script_mutually_exclusive(
    tmp_path: Path, project: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Test that FABulous script and TCL script are mutually exclusive."""
    # Create both script types
    fab_script = tmp_path / "test.fab"
    fab_script.write_text("help\n")
    tcl_script = tmp_path / "test.tcl"
    tcl_script.write_text("puts hello\n")

    test_args = [
        "FABulous",
        str(project),
        "--FABulousScript",
        str(fab_script),
        "--TCLScript",
        str(tcl_script),
    ]
    monkeypatch.setattr(sys, "argv", test_args)

    # Try to use both - should fail
    with pytest.raises(SystemExit) as exc_info:
        main()

    assert exc_info.value.code != 0


@pytest.mark.parametrize(
    ("global_dotenv", "project_dotenv", "env_var", "user_dir", "expected_dir"),
    [
        pytest.param(
            "global_dotenv_file",
            None,
            None,
            None,
            "global_dotenv_dir",
            id="global-only",
        ),
        pytest.param(
            "global_dotenv_file",
            "project_dotenv_file",
            None,
            None,
            "project_dotenv_dir",
            id="project-overrides-global",
        ),
        pytest.param(
            "global_dotenv_file",
            "project_dotenv_file",
            "env_var_dir",
            None,
            "env_var_dir",
            id="env-overrides-project-global",
        ),
        pytest.param(
            "global_dotenv_file",
            "project_dotenv_file",
            "env_var_dir",
            "user_provided_dir",
            "user_provided_dir",
            id="user-overrides-all",
        ),
        pytest.param(
            None,
            "project_dotenv_fallback_file",
            None,
            None,
            "default_dir",
            id="project-fallback",
        ),
    ],
)
def test_project_dir_precedence(
    project_directories: dict[str, Path],
    global_dotenv: str | None,
    project_dotenv: str | None,
    env_var: str | None,
    user_dir: str | None,
    expected_dir: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Deterministic precedence test using init_context directly (no CLI)."""
    dirs = project_directories
    reset_context()
    monkeypatch.delenv("FAB_PROJ_DIR", raising=False)

    if env_var:
        monkeypatch.setenv("FAB_PROJ_DIR", str(dirs[env_var]))

    global_file = dirs[global_dotenv] if global_dotenv else None
    project_file = dirs[project_dotenv] if project_dotenv else None
    user_directory = dirs[user_dir] if user_dir else None

    settings = init_context(
        project_dir=user_directory,
        global_dot_env=global_file,
        project_dot_env=project_file,
    )
    assert settings.proj_dir.resolve() == dirs[expected_dir].resolve()


@pytest.mark.parametrize(
    ("argv", "chdir_flag", "expected_code"),
    [
        pytest.param(
            ["FABulous", "-p", "{project}", "update-project-version"],
            False,
            0,
            id="explicit-success",
        ),
        pytest.param(
            ["FABulous", "-p", "{project}", "update-project-version"],
            False,
            1,
            id="explicit-failure",
        ),
        pytest.param(["FABulous", "update-project-version"], True, 0, id="cwd-success"),
        pytest.param(
            ["FABulous", "{project}", "--update-project-version"],
            False,
            0,
            id="legacy",
        ),
    ],
)
def test_update_project_version_cases(
    project: Path,
    monkeypatch: pytest.MonkeyPatch,
    mocker: MockerFixture,
    argv: list[str],
    chdir_flag: bool,
    expected_code: int,
) -> None:
    """The command updates the resolved project and maps the result to the exit code."""
    test_argv = [s.replace("{project}", str(project)) for s in argv]
    update = mocker.patch(
        "fabulous.fabulous.update_project_version", return_value=not expected_code
    )
    monkeypatch.setattr(sys, "argv", test_argv)
    if chdir_flag:
        monkeypatch.chdir(project)
    with pytest.raises(SystemExit) as exc_info:
        main()
    assert exc_info.value.code == expected_code
    update.assert_called_once_with(project)


@pytest.mark.parametrize(
    ("argv", "expected_code", "chdir_flag"),
    [
        pytest.param(
            ["FABulous", "-p", "{project}", "s"], 0, False, id="alias-explicit"
        ),
        pytest.param(["FABulous", "s"], 0, True, id="alias-only"),
        pytest.param(["FABulous", "start"], 0, True, id="full-command"),
        pytest.param(["FABulous", "start"], 1, False, id="full-command-no-cwd"),
        pytest.param(["FABulous", "{project}"], 0, False, id="legacy-project-only"),
    ],
)
def test_start(
    project: Path,
    monkeypatch: pytest.MonkeyPatch,
    mocker: MockerFixture,
    argv: list[str],
    expected_code: int,
    chdir_flag: bool,
) -> None:
    """`start`, its alias and the bare legacy form run the REPL loop on the project."""
    started_in: list[Path] = []
    mocker.patch.object(
        FABulousREPL,
        "cmdloop",
        autospec=True,
        side_effect=lambda repl: started_in.append(repl.projectDir),
    )

    test_args = [s.replace("{project}", str(project)) for s in argv]
    monkeypatch.setattr(sys, "argv", test_args)

    if chdir_flag:
        monkeypatch.chdir(project)

    with pytest.raises(SystemExit) as exc_info:
        main()

    assert exc_info.value.code == expected_code
    assert started_in == ([project] if expected_code == 0 else [])


@pytest.mark.parametrize(
    ("argv", "expected_code", "expected_out"),
    [
        pytest.param(["FABulous", "--version"], 0, "{version}", id="version"),
        pytest.param(["FABulous", "--help"], 0, None, id="help"),
        pytest.param(["FABulous"], 2, None, id="no-args"),
        pytest.param(
            ["FABulous", "--version", "run", "/", "help"],
            0,
            "{version}",
            id="version-eager",
        ),
        pytest.param(["FABulous", "--bogus"], 2, None, id="unknown-option"),
        pytest.param(["FABulous", "unknown"], 1, None, id="unknown-command"),
    ],
)
def test_global_parser_behaviors(
    argv: list[str],
    expected_code: int,
    expected_out: str | None,
    monkeypatch: pytest.MonkeyPatch,
    capfd: pytest.CaptureFixture[str],
) -> None:
    """Global flags exit with the right code; `--version` prints only the version."""
    monkeypatch.setattr(sys, "argv", argv)
    with pytest.raises(SystemExit) as exc_info:
        main()
    assert exc_info.value.code == expected_code
    if expected_out is not None:
        package_version = Version(version("FABulous-FPGA")).base_version
        assert capfd.readouterr().out == f"FABulous CLI {package_version}\n"


@pytest.mark.parametrize(
    ("argv", "use_cwd", "expected_code", "expected_dispatch"),
    [
        pytest.param(
            ["FABulous", "-p", "{project}", "run"], False, 0, [], id="run-none"
        ),
        pytest.param(
            ["FABulous", "-p", "{project}", "run", "help"],
            False,
            0,
            ["help"],
            id="run-single-explicit",
        ),
        pytest.param(
            ["FABulous", "run", "help"], True, 0, ["help"], id="run-single-cwd"
        ),
        # Only "; " separates commands; a bare ";" is cmd2's statement terminator.
        pytest.param(
            ["FABulous", "-p", "{project}", "run", "help;help"],
            False,
            0,
            ["help;help"],
            id="run-multi-no-space",
        ),
        pytest.param(
            ["FABulous", "-p", "{project}", "run", "help;  help"],
            False,
            0,
            ["help", "help"],
            id="run-multi-spaces",
        ),
        pytest.param(
            ["FABulous", "-p", "{project}", "r", "help"],
            False,
            0,
            ["help"],
            id="run-alias-r",
        ),
        pytest.param(
            ["FABulous", "-p", "{project}", "run", "help;"],
            False,
            0,
            ["help;"],
            id="trailing-semi-noop",
        ),
        pytest.param(
            ["FABulous", "-p", "{project}", "run", "help; load_fabric non_exist"],
            False,
            1,
            ["help", "load_fabric non_exist"],
            id="mixed-success-fail",
        ),
        pytest.param(
            [
                "FABulous",
                "{project}",
                "--commands",
                "load_fabric non_exist; load_fabric non_exist",
            ],
            False,
            1,
            ["load_fabric non_exist"],
            id="stop-on-first-error",
        ),
        pytest.param(
            ["FABulous", "{project}", "--commands", "help; help"],
            False,
            0,
            ["help", "help"],
            id="legacy-multi",
        ),
        pytest.param(
            ["FABulous", "{project}", "--commands", ""],
            False,
            0,
            None,
            id="empty-commands",
        ),
    ],
)
def test_run_variants(
    project: Path,
    monkeypatch: pytest.MonkeyPatch,
    mocker: MockerFixture,
    argv: list[str],
    use_cwd: bool,
    expected_code: int,
    expected_dispatch: list[str] | None,
) -> None:
    """`run` and legacy `--commands` dispatch each command in order.

    The REPL first runs `load_fabric` (stubbed to fail in this module), which
    must not abort the user's commands. `None` means no REPL is started.
    """
    spy = mocker.spy(FABulousREPL, "onecmd_plus_hooks")
    test_argv = [s.replace("{project}", str(project)) for s in argv]
    if use_cwd:
        monkeypatch.chdir(project)
    monkeypatch.setattr(sys, "argv", test_argv)
    with pytest.raises(SystemExit) as exec_info:
        main()
    assert exec_info.value.code == expected_code
    dispatched = [call.args[1] for call in spy.call_args_list]
    if expected_dispatch is None:
        assert dispatched == []
    else:
        assert dispatched == ["load_fabric", *expected_dispatch]


@pytest.mark.parametrize(
    ("argv", "expected_loads"),
    [
        pytest.param(
            ["FABulous", "-gde", "{global}", "run", "help"],
            [("global", "global_dotenv_file")],
            id="short-gde",
        ),
        pytest.param(
            ["FABulous", "-pde", "{project}", "run", "help"],
            [("project", "project_dotenv_file")],
            id="short-pde",
        ),
        pytest.param(
            ["FABulous", "-gde", "{global}", "-pde", "{project}", "run", "help"],
            [("global", "global_dotenv_file"), ("project", "project_dotenv_file")],
            id="both-short",
        ),
    ],
)
def test_short_dotenv_flags(
    project_directories: dict[str, Path],
    argv: list[str],
    expected_loads: list[tuple[str, str]],
) -> None:
    """The short dotenv flags (-gde, -pde) load the .env file they point at."""
    dirs = project_directories
    command = [
        arg.replace("{global}", str(dirs["global_dotenv_file"])).replace(
            "{project}", str(dirs["project_dotenv_file"])
        )
        for arg in argv
    ]

    result = run(
        command,
        capture_output=True,
        text=True,
        cwd=str(dirs["default_dir"]),
    )

    assert result.returncode == 0
    for kind, dotenv_key in expected_loads:
        assert f"Loading {kind} .env file from {dirs[dotenv_key]}" in result.stdout


@pytest.mark.parametrize(
    ("subcmd", "expected_code"),
    [
        pytest.param(["script"], 0, id="script"),
        pytest.param(["run"], 0, id="run"),
        pytest.param(["start"], 0, id="start"),
        pytest.param(["create-project"], 0, id="create-project"),
        pytest.param(["install"], 0, id="install"),
        pytest.param(["install", "oss-cad-suite"], 0, id="install-oss-cad-suite"),
        pytest.param(["install", "fabulator"], 0, id="install-fabulator"),
        pytest.param(["install", "nix"], 0, id="install-nix"),
        pytest.param(["update-project-version"], 0, id="update-project-version"),
    ],
)
def test_subcommand_help(
    monkeypatch: pytest.MonkeyPatch, subcmd: list[str], expected_code: int
) -> None:
    argv = ["FABulous", *subcmd, "--help"]
    monkeypatch.setattr(sys, "argv", argv)
    with pytest.raises(SystemExit) as exc_info:
        main()
    assert exc_info.value.code == expected_code


# ============================================================================
# Additional Tests for Missing Coverage
# ============================================================================


def test_validate_project_directory_success(project: Path) -> None:
    """Test validate_project_directory with valid project."""
    from fabulous.fabulous import validate_project_directory

    result = validate_project_directory(str(project))
    assert result == project


def test_validate_project_directory_invalid(tmp_path: Path) -> None:
    """Test validate_project_directory with invalid project."""
    from fabulous.fabulous import validate_project_directory

    invalid_dir = tmp_path / "not_a_project"
    invalid_dir.mkdir()

    with pytest.raises(ValueError, match="not a valid FABulous project"):
        validate_project_directory(str(invalid_dir))


def test_non_project_cwd_without_p_flag_exits_with_code_1(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capfd: pytest.CaptureFixture[str],
) -> None:
    """Running FABulous in a non-project CWD without -p exits with code 1."""
    reset_context()
    non_project = tmp_path / "not_a_project"
    non_project.mkdir()

    monkeypatch.chdir(non_project)
    monkeypatch.setattr(sys, "argv", ["FABulous", "start"])

    with pytest.raises(SystemExit) as exc_info:
        main()

    assert exc_info.value.code == 1
    captured = capfd.readouterr().out
    assert "not a valid FABulous project" in captured


def test_log_settings_validation_error_messages(
    tmp_path: Path,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """_log_settings_validation_error produces user-friendly error messages."""
    from pydantic import ValidationError

    from fabulous.fabulous_settings import (
        FABulousSettings,
        _log_settings_validation_error,
    )

    invalid_dir = tmp_path / "not_a_project"
    invalid_dir.mkdir()

    with pytest.raises(ValidationError) as exc_info:
        FABulousSettings(proj_dir=invalid_dir)

    _log_settings_validation_error(exc_info.value, invalid_dir)

    assert "Failed to initialize project settings" in caplog.text
    assert "not a valid FABulous project" in caplog.text


@pytest.mark.parametrize(
    ("package_ver", "project_ver", "should_exit", "expected_error"),
    [
        pytest.param(
            "2.0.0", "1.0.0", False, "Major version mismatch!", id="package-newer-major"
        ),
        pytest.param(
            "1.0.0", "2.0.0", True, "Version incompatible!", id="package-older"
        ),
        pytest.param("1.0.0", "1.0.0", False, None, id="same-version"),
        pytest.param("1.1.0", "1.0.0", False, None, id="same-major-newer-minor"),
    ],
)
def test_check_version_compatibility_cases(
    project: Path,
    package_ver: str,
    project_ver: str,
    should_exit: bool,
    expected_error: str | None,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """An older package aborts; a different major version is reported as an error."""
    from fabulous.fabulous import check_version_compatibility

    reset_context()
    set_key(project / ".FABulous" / ".env", "FAB_PROJ_VERSION", project_ver)
    init_context(project_dir=project)
    monkeypatch.setattr("fabulous.fabulous.version", lambda _: package_ver)
    caplog.clear()

    if should_exit:
        with pytest.raises(typer.Exit):
            check_version_compatibility()
    else:
        check_version_compatibility()

    errors = [r.message for r in caplog.records if r.levelname == "ERROR"]
    if expected_error is None:
        assert errors == []
    else:
        assert len(errors) == 1
        assert errors[0].startswith(expected_error)


@pytest.mark.parametrize(
    "command",
    [["start"], ["run", "help"], ["script", "{script}"]],
    ids=["start", "run", "script"],
)
def test_newer_project_version_blocks_repl(
    project: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    mocker: MockerFixture,
    command: list[str],
) -> None:
    """A project newer than the package exits 1 before the REPL runs anything."""
    script_file = tmp_path / "test.fab"
    script_file.write_text("help\n")
    set_key(project / ".FABulous" / ".env", "FAB_PROJ_VERSION", "99.0.0")
    monkeypatch.setattr("fabulous.fabulous.version", lambda _: "1.0.0")
    dispatch = mocker.spy(FABulousREPL, "onecmd_plus_hooks")
    # not a MagicMock: cmd2 scans the class for subcommand markers and a mock
    # answers every attribute lookup
    looped: list[FABulousREPL] = []
    monkeypatch.setattr(FABulousREPL, "cmdloop", looped.append)
    argv = [arg.replace("{script}", str(script_file)) for arg in command]
    monkeypatch.setattr(sys, "argv", ["FABulous", "-p", str(project), *argv])

    with pytest.raises(SystemExit) as exc_info:
        main()

    assert exc_info.value.code == 1
    dispatch.assert_not_called()
    assert looped == []


@pytest.mark.parametrize(
    ("script_content", "expected_code", "expected_dispatch"),
    [
        pytest.param("help\n", 0, ["help"], id="simple-command"),
        pytest.param(
            "# Comment\nhelp\nload_fabric test.csv\n",
            1,
            ["help", "load_fabric test.csv"],
            id="comment-skipped-last-line-fails",
        ),
        pytest.param(
            "load_fabric test.csv\nhelp\n",
            1,
            ["load_fabric test.csv"],
            id="failing-line-aborts",
        ),
        pytest.param("", 0, [], id="empty-script"),
    ],
)
def test_script_execution_with_content(
    tmp_path: Path,
    project: Path,
    monkeypatch: pytest.MonkeyPatch,
    mocker: MockerFixture,
    script_content: str,
    expected_code: int,
    expected_dispatch: list[str],
) -> None:
    """A FABulous script runs line by line, skips comments and stops at a failure."""
    script_file = tmp_path / "test.fab"
    script_file.write_text(script_content)
    spy = mocker.spy(FABulousREPL, "onecmd_plus_hooks")

    test_args = [
        "FABulous",
        "-p",
        str(project),
        "script",
        "-t",
        "fabulous",
        str(script_file),
    ]
    monkeypatch.setattr(sys, "argv", test_args)

    with pytest.raises(SystemExit) as exc_info:
        main()

    assert exc_info.value.code == expected_code
    dispatched = [call.args[1] for call in spy.call_args_list]
    assert dispatched == [
        "load_fabric",
        f"run_script {script_file.resolve()}",
        *expected_dispatch,
    ]


@pytest.mark.parametrize(
    ("suffix", "type_flag", "expected_command"),
    [
        pytest.param(".tcl", [], "run_tcl", id="tcl-default"),
        pytest.param(".fab", [], "run_script", id="fab-default"),
        pytest.param(".fs", [], "run_script", id="fs-default"),
        pytest.param(".tcl", ["-t", "tcl"], "run_tcl", id="tcl-explicit-tcl"),
        pytest.param(".fab", ["-t", "tcl"], "run_tcl", id="fab-explicit-tcl"),
        pytest.param(".tcl", ["-t", "fabulous"], "run_script", id="tcl-explicit-fab"),
        pytest.param(".txt", ["-t", "fabulous"], "run_script", id="txt-explicit-fab"),
    ],
)
def test_script_type_dispatch(
    tmp_path: Path,
    project: Path,
    monkeypatch: pytest.MonkeyPatch,
    mocker: MockerFixture,
    suffix: str,
    type_flag: list[str],
    expected_command: str,
) -> None:
    """`--type` decides which REPL command runs the script file."""
    script_file = tmp_path / f"test{suffix}"
    script_file.write_text("help\n")
    spy = mocker.spy(FABulousREPL, "onecmd_plus_hooks")

    test_args = [
        "FABulous",
        "-p",
        str(project),
        "script",
        *type_flag,
        str(script_file),
    ]
    monkeypatch.setattr(sys, "argv", test_args)

    with pytest.raises(SystemExit) as exc_info:
        main()

    assert exc_info.value.code == 0
    dispatched = [call.args[1] for call in spy.call_args_list]
    # run_script feeds each line back through onecmd_plus_hooks; TCL calls do_help.
    script_lines = ["help"] if expected_command == "run_script" else []
    assert dispatched == [
        "load_fabric",
        f"{expected_command} {script_file.resolve()}",
        *script_lines,
    ]


def test_script_unknown_extension_needs_type(
    tmp_path: Path,
    project: Path,
    monkeypatch: pytest.MonkeyPatch,
    mocker: MockerFixture,
    capfd: pytest.CaptureFixture[str],
) -> None:
    """An extension with no known script type fails before the REPL runs."""
    script_file = tmp_path / "test.txt"
    script_file.write_text("help\n")
    spy = mocker.spy(FABulousREPL, "onecmd_plus_hooks")
    monkeypatch.setattr(
        sys, "argv", ["FABulous", "-p", str(project), "script", str(script_file)]
    )

    with pytest.raises(SystemExit) as exc_info:
        main()

    assert exc_info.value.code == 1
    spy.assert_not_called()
    assert "Pass --type fabulous or --type tcl." in capfd.readouterr().out


def test_main_function_exception_handling(
    monkeypatch: pytest.MonkeyPatch,
    mocker: MockerFixture,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """An unexpected exception from the app is logged and exits with code 1."""
    mocker.patch("fabulous.fabulous.app", side_effect=RuntimeError("boom"))
    monkeypatch.setattr(sys, "argv", ["FABulous", "--help"])

    with pytest.raises(SystemExit) as exc_info:
        main()

    assert exc_info.value.code == 1
    assert [(r.levelname, r.message) for r in caplog.records] == [
        ("ERROR", "Unexpected error: boom")
    ]


def test_legacy_logging_default_filename(project: Path) -> None:
    """Using legacy -log without path should create FABulous.log in CWD."""
    result = run(
        [
            "FABulous",
            str(project),
            "--commands",
            "help",
            "-log",  # triggers default const filename
        ],
        capture_output=True,
        text=True,
        cwd=str(project),
    )
    assert result.returncode == 0
    log_file = Path(project) / "FABulous.log"
    assert log_file.exists()
    assert log_file.stat().st_size > 0


def test_global_option_after_subcommand(project: Path) -> None:
    """A global option placed after the subcommand is moved before it (exit 0)."""
    result = run(
        [
            "FABulous",
            "-p",
            str(project),
            "run",
            "help",
            "--debug",
        ],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0


def test_start_invalid_project() -> None:
    """A non-existent `-p` directory is a usage error raised by the option parser."""
    invalid = "/nonexistent/path/does/not/exist"
    result = run(
        [
            "FABulous",
            "-p",
            invalid,
            "start",
        ],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 2
    assert "Invalid value for '--project-dir'" in result.stderr


NIX_CONF = (
    "extra-experimental-features = nix-command flakes\n"
    "extra-substituters = https://nix-cache.fossi-foundation.org\n"
    "extra-trusted-public-keys = nix-cache.fossi-foundation.org:"
    "3+K59iFwXqKsL7BNu6Guy0v+uTlwsxYQxjspXzqLYQs="
)


@pytest.mark.parametrize(
    ("existing_conf", "expected_conf"),
    [
        pytest.param(None, NIX_CONF, id="no-config"),
        pytest.param("", NIX_CONF, id="empty-config"),
        pytest.param("already exists\n", "already exists\n", id="user-config-kept"),
    ],
)
def test_install_nix(
    monkeypatch: pytest.MonkeyPatch,
    mocker: MockerFixture,
    tmp_path: Path,
    existing_conf: str | None,
    expected_conf: str,
) -> None:
    """The installer runs and the binary cache is configured unless the user has one."""
    mocker.patch("pathlib.Path.home", return_value=tmp_path)
    mocker.patch("shutil.which", return_value=None)
    run_mock = mocker.patch(
        "subprocess.run", return_value=CompletedProcess(args=[], returncode=0)
    )
    config_path = tmp_path / ".config" / "nix" / "nix.conf"
    if existing_conf is not None:
        config_path.parent.mkdir(parents=True)
        config_path.write_text(existing_conf)
    monkeypatch.setattr(sys, "argv", ["FABulous", "install", "nix"])

    with pytest.raises(SystemExit) as exc_info:
        main()

    assert exc_info.value.code == 0
    run_mock.assert_called_once_with(
        "curl -L https://nixos.org/nix/install | sh", shell=True, check=True
    )
    assert config_path.read_text() == expected_conf


def test_install_nix_skip(
    monkeypatch: pytest.MonkeyPatch,
    mocker: MockerFixture,
) -> None:
    """An installed Nix skips the installer entirely."""
    mocker.patch("shutil.which", return_value="/nix/store/fake/bin/nix")
    run_mock = mocker.patch("subprocess.run")
    monkeypatch.setattr(sys, "argv", ["FABulous", "install", "nix"])

    with pytest.raises(SystemExit) as exc_info:
        main()

    assert exc_info.value.code == 0
    run_mock.assert_not_called()

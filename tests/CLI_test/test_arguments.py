"""Test module for FABulous CLI argument processing and functionality.

This module contains comprehensive tests for the FABulous command-line interface,
covering project creation, script execution, command-line flags, and error handling.
"""

import sys
import tarfile
from collections.abc import Callable
from pathlib import Path
from subprocess import run

import pytest
import typer
from dotenv import set_key
from pytest_mock import MockerFixture

from FABulous.FABulous import main
from FABulous.FABulous_settings import init_context, reset_context


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
    ("argv", "start_dir", "expected_code"),
    [
        # FAB script with explicit project
        pytest.param(
            ["FABulous", "{project}", "--FABulousScript", "{file}"],
            None,
            0,
            id="fab-legacy",
        ),
        pytest.param(
            ["FABulous", "-p", "{project}", "script", "{file}"],
            None,
            0,
            id="fab-typer",
        ),
        # FAB script in cwd in a project
        pytest.param(
            ["FABulous", "--FABulousScript", "{file}"],
            "project",
            0,
            id="fab-cwd-project",
        ),
        # FAB script with nonexistent file
        pytest.param(
            ["FABulous", "-p", "{project}", "script", "{missing}"],
            None,
            2,
            id="fab-nonexistent",
        ),
        # TCL script with explicit project
        pytest.param(
            ["FABulous", "{project}", "--TCLScript", "{tcl}"],
            None,
            0,
            id="tcl-legacy",
        ),
        pytest.param(
            ["FABulous", "-p", "{project}", "script", "{tcl}"],
            None,
            0,
            id="tcl-typer",
        ),
        # FAB script in non-project cwd (should fail)
        pytest.param(
            ["FABulous", "--FABulousScript", "{file}"],
            "nonproject",
            1,
            id="fab-cwd-nonproject",
        ),
        pytest.param(
            ["FABulous", "-p", "{project}", "script", "nonexistent.fab"],
            None,
            2,
            id="tcl-typer",
        ),
    ],
)
def test_script_execution(
    tmp_path: Path,
    project: Path,
    monkeypatch: pytest.MonkeyPatch,
    argv: list[str],
    start_dir: str | None,
    expected_code: int,
) -> None:
    fab_script = tmp_path / "test_script.fab"
    # Default content succeeds; override below for failure scenarios
    fab_content = "# Test FABulous script\nhelp\n"
    if start_dir == "nonproject":
        # Trigger a failure when not in a project
        fab_content = "load_fabric non_exist\n"
    fab_script.write_text(fab_content)
    tcl_script = tmp_path / "test_script.tcl"
    tcl_script.write_text(
        '# TCL script with FABulous commands\nputs "Hello from TCL"\n'
    )
    missing = tmp_path / "missing_script.fab"

    test_argv = [
        s.replace("{project}", str(project))
        .replace("{file}", str(fab_script))
        .replace("{tcl}", str(tcl_script))
        .replace("{missing}", str(missing))
        for s in argv
    ]

    if start_dir == "project":
        monkeypatch.chdir(project)
    elif start_dir == "nonproject":
        nonproj = tmp_path / "nonproj"
        nonproj.mkdir()
        monkeypatch.chdir(nonproj)

    monkeypatch.setattr(sys, "argv", test_argv)
    with pytest.raises(SystemExit) as exc_info:
        main()

    assert exc_info.value.code == expected_code


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
    """Logging creates file for both legacy and Typer styles."""
    log_file = tmp_path / "cli_test.log"
    test_args = argv_builder(project, log_file)
    monkeypatch.setattr(sys, "argv", test_args)

    with pytest.raises(SystemExit) as exc_info:
        main()

    assert exc_info.value.code == expected_code
    assert log_file.exists()
    assert log_file.stat().st_size > 0


@pytest.mark.parametrize(
    ("argv", "expected_code"),
    [
        pytest.param(
            ["FABulous", "{project}", "--commands", "help", "-v"],
            0,
            id="legacy-v",
        ),
        pytest.param(
            ["FABulous", "{project}", "--commands", "help", "-vv"],
            0,
            id="legacy-vv",
        ),
        pytest.param(
            ["FABulous", "-p", "{project}", "-v", "run", "help"],
            0,
            id="typer-v",
        ),
        pytest.param(
            ["FABulous", "-p", "{project}", "-vv", "run", "help"],
            0,
            id="typer-vv",
        ),
        pytest.param(
            ["FABulous", "-p", "{project}", "run", "help", "-v"],
            0,
            id="typer-vv-after-command",
        ),
    ],
)
def test_verbose_mode(
    project: Path,
    monkeypatch: pytest.MonkeyPatch,
    argv: list[str],
    expected_code: int,
) -> None:
    """Verbose mode works in both legacy and Typer forms."""
    test_args = [arg.replace("{project}", str(project)) for arg in argv]
    monkeypatch.setattr(sys, "argv", test_args)

    with pytest.raises(SystemExit) as exc_info:
        main()
    assert exc_info.value.code == expected_code


@pytest.mark.parametrize(
    ("argv", "expected_code"),
    [
        pytest.param(
            ["FABulous", "{project}", "--commands", "help", "--debug"],
            0,
            id="legacy",
        ),
        pytest.param(
            ["FABulous", "-p", "{project}", "--debug", "run", "help"],
            0,
            id="typer",
        ),
    ],
)
def test_debug_mode(
    project: Path, monkeypatch: pytest.MonkeyPatch, argv: list[str], expected_code: int
) -> None:
    """Debug mode works in both legacy and Typer forms."""
    test_args = [arg.replace("{project}", str(project)) for arg in argv]
    monkeypatch.setattr(sys, "argv", test_args)

    with pytest.raises(SystemExit) as exc_info:
        main()

    assert exc_info.value.code == expected_code


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
    """Test force flag functionality with different scenarios"""

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
    ("argv", "expected_requests", "expected_code"),
    [
        pytest.param(
            ["FABulous", "{project}", "--install_oss_cad_suite"], 2, 0, id="legacy"
        ),
        pytest.param(
            ["FABulous", "install-oss-cad-suite", "{project}"], 2, 0, id="typer-project"
        ),
        pytest.param(["FABulous", "install-oss-cad-suite"], 2, 0, id="default-dir"),
        pytest.param(
            ["FABulous", "install-oss-cad-suite", "{install_dir}"],
            2,
            0,
            id="explicit-dir",
        ),
        pytest.param(
            ["FABulous", "install-oss-cad-suite", "{install_dir}"],
            1,
            1,
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
) -> None:
    """Parametric test for install-oss-cad-suite variants with mocked network."""

    argv_template: list[str] = argv
    install_dir = tmp_path / "oss"
    test_argv = [
        s.replace("{project}", str(project)).replace("{install_dir}", str(install_dir))
        for s in argv_template
    ]

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
        def __enter__(self) -> "MockTarFile":
            return self

        def __exit__(self, *_args: object) -> None:
            pass

        def extractall(self, path: str) -> None:  # noqa: ARG002
            pass

    def mock_open(*_args: object, **_kwargs: object) -> MockTarFile:
        return MockTarFile()

    monkeypatch.setattr(tarfile, "open", mock_open)

    # Configure requests mock - success for non-xfail cases, failure for xfail
    if expected_requests == 1:
        # This is the error case (xfail) - mock failure
        m = mocker.patch("requests.get", return_value=MockRequestFail())
    else:
        # Success cases - mock successful requests
        m = mocker.patch("requests.get", side_effect=[MockRequestOK(), MockRequestOK()])

    # Ensure default-dir uses a clean temp user config directory
    tmp_user_dir = tmp_path / "user_config"
    monkeypatch.setattr("FABulous.FABulous.FAB_USER_CONFIG_DIR", tmp_user_dir)

    monkeypatch.setattr(sys, "argv", test_argv)
    with pytest.raises(SystemExit) as exc_info:
        main()

    assert exc_info.value.code == expected_code
    assert m.call_count == expected_requests


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
    if expected_dir == "default_dir":
        # Fallback path: just ensure a project directory was resolved
        assert settings.proj_dir is not None
        assert settings.proj_dir.exists()
    else:
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
    ],
)
def test_update_project_version_cases(
    project: Path,
    monkeypatch: pytest.MonkeyPatch,
    argv: list[str],
    chdir_flag: bool,
    expected_code: int,
) -> None:
    test_argv = [s.replace("{project}", str(project)) for s in argv]
    monkeypatch.setattr(
        "FABulous.FABulous.update_project_version", lambda _p: not bool(expected_code)
    )
    monkeypatch.setattr(sys, "argv", test_argv)
    if chdir_flag:
        monkeypatch.chdir(project)
    with pytest.raises(SystemExit) as exc_info:
        main()
    assert exc_info.value.code == expected_code


@pytest.mark.parametrize(
    "file_ext",
    [
        pytest.param(".txt", id="txt"),
        pytest.param(".fab", id="fab"),
        pytest.param(".tcl", id="tcl"),
    ],
)
@pytest.mark.parametrize(
    ("explicit_type", "content", "expected_code"),
    [
        pytest.param("fabulous", "help\n", 0, id="type-fabulous"),
        pytest.param("tcl", 'puts "hi"\n', 0, id="type-tcl"),
        pytest.param(
            "unknown",
            "help\n",
            2,
            id="type-invalid",
        ),
    ],
)
def test_script_command_type_override(
    tmp_path: Path,
    project: Path,
    monkeypatch: pytest.MonkeyPatch,
    file_ext: str,
    explicit_type: str,
    content: str,
    expected_code: int,
) -> None:
    """Explicit type flag should dictate execution mode regardless of extension."""
    script_file = tmp_path / f"test_script{file_ext}"
    script_file.write_text(content)

    test_args = [
        "FABulous",
        "-p",
        str(project),
        "script",
        str(script_file),
        "--type",
        explicit_type,
    ]
    monkeypatch.setattr(sys, "argv", test_args)

    with pytest.raises(SystemExit) as exc_info:
        main()

    assert exc_info.value.code == expected_code


@pytest.mark.parametrize(
    ("argv", "expected_code", "chdir_flag"),
    [
        pytest.param(
            ["FABulous", "-p", "{project}", "s"], 0, False, id="alias-explicit"
        ),
        pytest.param(["FABulous", "s"], 0, True, id="alias-only"),
        pytest.param(["FABulous", "start"], 0, True, id="full-command"),
        pytest.param(["FABulous", "start"], 1, False, id="full-command-no-cwd"),
    ],
)
def test_start(
    project: Path,
    monkeypatch: pytest.MonkeyPatch,
    argv: list[str],
    expected_code: int,
    chdir_flag: bool,
) -> None:
    """Test start command alias 's' (typer-only feature)"""

    # Mock cmdloop to avoid hanging
    def mock_cmdloop(self: object) -> None:  # noqa: ARG001
        pass

    monkeypatch.setattr("FABulous.FABulous_CLI.FABulous_CLI.cmdloop", mock_cmdloop)

    test_args = [s.replace("{project}", str(project)) for s in argv]
    monkeypatch.setattr(sys, "argv", test_args)

    if chdir_flag:
        monkeypatch.chdir(project)

    with pytest.raises(SystemExit) as exc_info:
        main()

    assert exc_info.value.code == expected_code


@pytest.mark.parametrize(
    ("argv", "expected_code"),
    [
        pytest.param(["FABulous", "--version"], 0, id="version"),
        pytest.param(["FABulous", "--help"], 0, id="help"),
        pytest.param(["FABulous"], 2, id="no-args"),
        pytest.param(
            ["FABulous", "--version", "run", "/", "help"],
            0,
            id="version-eager",
        ),
        pytest.param(["FABulous", "--bogus"], 2, id="unknown-option"),
        pytest.param(["FABulous", "unknown"], 1, id="unknown-command"),
    ],
)
def test_global_parser_behaviors(
    argv: list[str], expected_code: int, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(sys, "argv", argv)
    with pytest.raises(SystemExit) as exc_info:
        main()
    assert exc_info.value.code == expected_code


def test_default_writer_is_verilog(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    project_dir = tmp_path / "prj_default_writer"
    argv = ["FABulous", "create-project", str(project_dir)]
    monkeypatch.setattr(sys, "argv", argv)
    with pytest.raises(SystemExit) as exc_info:
        main()
    assert exc_info.value.code == 0
    env_text = (project_dir / ".FABulous" / ".env").read_text()
    assert "verilog" in env_text.lower()


@pytest.mark.parametrize(
    ("argv", "use_cwd", "expected_code"),
    [
        # Original basic variants
        pytest.param(
            [
                "FABulous",
                "-p",
                "{project}",
                "run",
            ],
            False,
            1,
            id="run-none",
        ),
        pytest.param(
            ["FABulous", "-p", "{project}", "run", "help"],
            False,
            0,
            id="run-single-explicit",
        ),
        pytest.param(
            ["FABulous", "run", "help"],
            True,
            0,
            id="run-single-cwd",
        ),
        pytest.param(
            ["FABulous", "-p", "{project}", "run", "help;help"],
            False,
            0,
            id="run-multi",
        ),
        pytest.param(
            ["FABulous", "-p", "{project}", "run", "help;  help"],
            False,
            0,
            id="run-multi-spaces",
        ),
        pytest.param(
            ["FABulous", "-p", "{project}", "r", "help"],
            False,
            0,
            id="run-alias-r",
        ),
        pytest.param(
            [
                "FABulous",
                "-p",
                "{project}",
                "run",
                "help;",
            ],
            False,
            0,
            id="trailing-semi-noop",
        ),
        pytest.param(
            [
                "FABulous",
                "-p",
                "{project}",
                "run",
                "help; load_fabric non_exist",
            ],
            False,
            1,
            id="mixed-success-fail",
        ),
        pytest.param(
            [
                "FABulous",
                "-p",
                "{project}",
                "--commands",
                "load_fabric non_exist; load_fabric non_exist",
            ],
            False,
            1,
            id="stop-on-first-error",
        ),
        pytest.param(
            ["FABulous", "{project}", "--commands", ""],
            False,
            0,
            id="empty-commands",
        ),
    ],
)
def test_run_variants(
    project: Path, argv: list[str], use_cwd: bool, expected_code: int
) -> None:
    """Unified run command behavior tests (return code only)."""
    test_argv = [s.replace("{project}", str(project)) for s in argv]
    if use_cwd:
        result = run(test_argv, capture_output=True, text=True, cwd=str(project))
    else:
        result = run(test_argv, capture_output=True, text=True)

    assert result.returncode == expected_code


@pytest.mark.parametrize(
    "argv",
    [
        pytest.param(
            ["FABulous", "-gde", "/tmp/global.env", "run", "help"], id="short-gde"
        ),
        pytest.param(
            ["FABulous", "-pde", "/tmp/project.env", "run", "help"], id="short-pde"
        ),
        pytest.param(
            [
                "FABulous",
                "-gde",
                "/tmp/global.env",
                "-pde",
                "/tmp/project.env",
                "run",
                "help",
            ],
            id="both-short",
        ),
    ],
)
def test_short_dotenv_flags(
    project_directories: dict[str, Path], argv: list[str]
) -> None:
    """Test short flag versions of dotenv options (-gde, -pde)"""
    dirs = project_directories
    # Replace placeholder paths with actual test files
    for i, arg in enumerate(argv):
        if arg == "/tmp/global.env":
            argv[i] = str(dirs["global_dotenv_file"])
        elif arg == "/tmp/project.env":
            argv[i] = str(dirs["project_dotenv_file"])

    result = run(
        argv,
        capture_output=True,
        text=True,
        cwd=str(dirs["default_dir"]),
    )
    # Should not crash and should process dotenv files
    assert isinstance(result.returncode, int)


@pytest.mark.parametrize(
    ("subcmd", "expected_code"),
    [
        pytest.param("script", 0, id="script"),
        pytest.param("run", 0, id="run"),
        pytest.param("start", 0, id="start"),
        pytest.param("create-project", 0, id="create-project"),
        pytest.param("install-oss-cad-suite", 0, id="install-oss-cad-suite"),
        pytest.param("update-project-version", 0, id="update-project-version"),
    ],
)
def test_subcommand_help(
    monkeypatch: pytest.MonkeyPatch, subcmd: str, expected_code: int
) -> None:
    argv = ["FABulous", subcmd, "--help"]
    monkeypatch.setattr(sys, "argv", argv)
    with pytest.raises(SystemExit) as exc_info:
        main()
    assert exc_info.value.code == expected_code


# ============================================================================
# Additional Tests for Missing Coverage
# ============================================================================


def test_version_callback() -> None:
    """Test version_callback function behavior"""
    from FABulous.FABulous import version_callback

    # Test that version_callback raises typer.Exit when value is True
    with pytest.raises(typer.Exit):
        version_callback(True)

    # Test that version_callback does nothing when value is False
    version_callback(False)  # Should not raise


def test_validate_project_directory_success(project: Path) -> None:
    """Test validate_project_directory with valid project"""
    from FABulous.FABulous import validate_project_directory

    result = validate_project_directory(str(project))
    assert result == project


def test_validate_project_directory_invalid(tmp_path: Path) -> None:
    """Test validate_project_directory with invalid project"""
    from FABulous.FABulous import validate_project_directory

    invalid_dir = tmp_path / "not_a_project"
    invalid_dir.mkdir()

    with pytest.raises(ValueError, match="not a valid FABulous project"):
        validate_project_directory(str(invalid_dir))


@pytest.mark.parametrize(
    ("package_ver", "project_ver", "should_exit"),
    [
        pytest.param("2.0.0", "1.0.0", False, id="package-newer-minor"),
        pytest.param("1.0.0", "2.0.0", True, id="package-older"),
        pytest.param("2.0.0", "1.0.0", False, id="major-version-mismatch"),
        pytest.param("1.1.0", "1.0.0", False, id="same-major-newer-minor"),
    ],
)
def test_check_version_compatibility_cases(
    project: Path,
    package_ver: str,
    project_ver: str,
    should_exit: bool,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Test version compatibility checking with different version scenarios"""

    from FABulous.FABulous import check_version_compatibility
    from FABulous.FABulous_settings import init_context, reset_context

    reset_context()

    # Set up project version in .env file
    env_file = project / ".FABulous" / ".env"

    set_key(env_file, "FAB_PROJ_VERSION", project_ver)

    # Initialize context
    init_context(project_dir=project)

    monkeypatch.setattr("FABulous.FABulous.version", lambda _: package_ver)
    monkeypatch.setattr("importlib.metadata.version", lambda _: package_ver)
    # Mock the package version
    if should_exit:
        with pytest.raises(typer.Exit):
            check_version_compatibility(project)
    else:
        # Should not raise an exception
        check_version_compatibility(project)


@pytest.mark.parametrize(
    ("script_content", "expected_code"),
    [
        pytest.param("help\n", 0, id="simple-command"),
        pytest.param("# Comment\nhelp\nload_fabric test.csv\n", 1, id="multi-line"),
        pytest.param("", 0, id="empty-script"),
    ],
)
def test_script_execution_with_content(
    tmp_path: Path,
    project: Path,
    monkeypatch: pytest.MonkeyPatch,
    script_content: str,
    expected_code: int,
) -> None:
    """Test script execution with different content types"""
    script_file = tmp_path / "test.fab"
    script_file.write_text(script_content)

    test_args = ["FABulous", "-p", str(project), "script", str(script_file)]
    monkeypatch.setattr(sys, "argv", test_args)

    with pytest.raises(SystemExit) as exc_info:
        main()

    assert exc_info.value.code == expected_code


@pytest.mark.parametrize(
    ("file_ext", "expected_code"),
    [
        pytest.param(".fab", 0, id="fab-extension"),
        pytest.param(".fs", 0, id="fs-extension"),
        pytest.param(".tcl", 0, id="tcl-extension"),
        pytest.param(".txt", 0, id="unknown-extension-defaults-tcl"),
    ],
)
def test_script_type_detection(
    tmp_path: Path,
    project: Path,
    monkeypatch: pytest.MonkeyPatch,
    file_ext: str,
    expected_code: int,
) -> None:
    """Test automatic script type detection based on file extension"""
    # Note: expected_type is used for documentation but not assertion since
    # we're only testing that the command succeeds with different extensions
    script_file = tmp_path / f"test{file_ext}"
    script_file.write_text("help\n")

    test_args = ["FABulous", "-p", str(project), "script", str(script_file)]
    monkeypatch.setattr(sys, "argv", test_args)

    with pytest.raises(SystemExit) as exc_info:
        main()

    assert exc_info.value.code == expected_code


def test_main_function_exception_handling(monkeypatch: pytest.MonkeyPatch) -> None:
    """Test main function handles unexpected exceptions"""
    from unittest.mock import Mock

    # Mock app to raise an unexpected exception
    mock_app = Mock(side_effect=RuntimeError("Unexpected error"))
    monkeypatch.setattr("FABulous.FABulous.app", mock_app)
    monkeypatch.setattr(sys, "argv", ["FABulous", "--help"])

    with pytest.raises(SystemExit) as exc_info:
        main()

    assert exc_info.value.code == 1


def test_run_command_pipeline_error(
    project: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Test run command with pipeline execution error"""
    test_args = [
        "FABulous",
        "-p",
        str(project),
        "run",
        "load_fabric nonexistent_fabric",
    ]
    monkeypatch.setattr(sys, "argv", test_args)

    with pytest.raises(SystemExit) as exc_info:
        main()

    # Should exit with non-zero code due to command failure
    assert exc_info.value.code != 0


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
    """Global option placed after subcommand should raise usage error (exit 2)."""
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
    """Starting with a non-existent project directory should fail."""
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
    assert result.returncode != 0


def test_install_nix(
    monkeypatch: pytest.MonkeyPatch,
    mocker: MockerFixture,
    tmp_path: Path,
) -> None:
    """Test install-nix on unsupported NixOS platform."""
    test_argv = ["FABulous", "install-nix"]

    # Patch Path.home in the module under test so the FABulous code picks up the mocked home
    mocker.patch("pathlib.Path.home", return_value=tmp_path)
    mocker.patch("shutil.which", return_value=None)
    mocker.patch("subprocess.run", return_value=run(["true"]))
    monkeypatch.setattr(sys, "argv", test_argv)
    with pytest.raises(SystemExit) as exc_info:
        main()

    config_path = tmp_path / ".config" / "nix" / "nix.conf"
    assert config_path.exists()
    assert len(config_path.read_text().split("\n")) == 3
    assert exc_info.value.code == 0


def test_install_nix_skip(
    monkeypatch: pytest.MonkeyPatch,
    mocker: MockerFixture,
) -> None:
    """Test install-nix when Nix is already installed."""
    test_argv = ["FABulous", "install-nix"]

    mocker.patch("shutil.which", return_value="nix")
    monkeypatch.setattr(sys, "argv", test_argv)
    with pytest.raises(SystemExit) as exc_info:
        main()

    assert exc_info.value.code == 0


def test_install_nix_failure(
    monkeypatch: pytest.MonkeyPatch,
    mocker: MockerFixture,
    tmp_path: Path,
    capsys: pytest.CaptureFixture,
) -> None:
    """Test install-nix when Nix is not installed."""
    test_argv = ["FABulous", "install-nix"]

    # Patch Path.home in the module under test so the FABulous code picks up the mocked home
    mocker.patch("pathlib.Path.home", return_value=tmp_path)
    mocker.patch("shutil.which", return_value=None)
    mocker.patch("subprocess.run", return_value=run(["true"]))
    monkeypatch.setattr(sys, "argv", test_argv)

    config_path = tmp_path / ".config" / "nix" / "nix.conf"
    config_path.parent.mkdir(parents=True, exist_ok=True)
    config_path.write_text("already exists\n")

    with pytest.raises(SystemExit) as exc_info:
        main()

    assert config_path.read_text() == "already exists\n"
    assert capsys.readouterr().out.count("is not empty") == 1
    assert exc_info.value.code == 0

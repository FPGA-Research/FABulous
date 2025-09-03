"""Test configuration and shared fixtures for FABulous CLI tests.

This module provides pytest fixtures and utility functions for testing the FABulous
command-line interface. It includes test project setup, environment configuration,
logger management, and common test utilities.
"""

from pathlib import Path

import pytest
from _pytest.logging import LogCaptureFixture
from dotenv import set_key
from loguru import logger

from FABulous.FABulous_CLI.FABulous_CLI import FABulous_CLI
from FABulous.FABulous_CLI.helper import create_project


def normalize(block: str) -> list[str]:
    """Normalize a block of text to perform comparison.

    Strip newlines from the very beginning and very end, then split into separate lines and strip trailing whitespace
    from each line.
    """
    assert isinstance(block, str)
    block = block.strip("\n")
    return [line.rstrip() for line in block.splitlines()]


def run_cmd(app: FABulous_CLI, cmd: str) -> None:
    """Execute a command in the FABulous CLI application.

    This utility function runs a command through the CLI's command processing system.

    Parameters
    ----------
    app : FABulous_CLI
        The FABulous CLI application instance to run the command on.
    cmd : str
        The command string to execute.

    """
    app.onecmd_plus_hooks(cmd)


def normalize_and_check_for_errors(caplog_text: str) -> list[str]:
    """Normalize log text and check for error messages.

    This function normalizes log text using the normalize function and then
    checks for any ERROR-level messages. If errors are found, an assertion
    error is raised.

    Parameters
    ----------
    caplog_text : str
        The captured log text to check for errors.

    Returns
    -------
    list[str]
        The normalized log lines.

    Raises
    ------
    AssertionError
        If any ERROR-level messages are found in the log.

    """
    log = normalize(caplog_text)
    assert not any("ERROR" in line for line in log), "Error found in log messages"
    return log


TILE = "LUT4AB"


@pytest.fixture
def cli(tmp_path: Path) -> Generator[FABulous_CLI]:
    """Create a configured FABulous CLI instance for testing.

    This fixture creates a temporary test project and initializes a FABulous
    CLI instance with the fabric loaded and ready for testing. It handles
    project creation, environment setup, and initial fabric loading.

    Parameters
    ----------
    tmp_path : Path
        Pytest temporary directory path.

    Yields
    ------
    FABulous_CLI
        A configured CLI instance with loaded fabric ready for testing.

    """
    projectDir = tmp_path / "test_project"
    os.environ["FAB_PROJ_DIR"] = str(projectDir)
    create_project(projectDir)
    setup_logger(0, False)
    cli = FABulous_CLI(
        writerType="verilog", projectDir=projectDir, enteringDir=tmp_path
    )
    cli.debug = True
    run_cmd(cli, "load_fabric")
    yield cli
    os.environ.pop("FAB_ROOT", None)
    os.environ.pop("FAB_PROJ_DIR", None)


@pytest.fixture
def project(tmp_path: Path) -> Generator[Path]:
def project(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Create a test project directory for testing.

    This fixture creates a temporary FABulous project with all necessary
    files and configuration for testing purposes.

    Parameters
    ----------
    tmp_path : Path
        Pytest temporary directory path.

    Yields
    ------
    Path
        Path to the created test project directory.

    """
    project_dir = tmp_path / "test_project"
    monkeypatch.setenv("FAB_PROJ_DIR", str(project_dir))
    create_project(project_dir)
    return project_dir


@pytest.fixture
def project_directories(tmp_path: Path) -> dict[str, Path]:
    """Fixture that creates test directories and .env files for project directory
    precedence tests."""
    # Create multiple project directories for testing
    user_provided_dir = tmp_path / "user_provided_project"
    env_var_dir = tmp_path / "env_var_project"
    project_dotenv_dir = tmp_path / "project_dotenv_project"
    global_dotenv_dir = tmp_path / "global_dotenv_project"
    default_dir = tmp_path / "default_project"

    # Create all directories with .FABulous folders
    for project_dir in [
        user_provided_dir,
        env_var_dir,
        project_dotenv_dir,
        global_dotenv_dir,
        default_dir,
    ]:
        project_dir.mkdir()
        (project_dir / ".FABulous").mkdir()
        env_file = project_dir / ".FABulous" / ".env"
        env_file.touch()
        set_key(env_file, "FAB_PROJ_LANG", "verilog")
        set_key(env_file, "FAB_PROJ_VERSION", "1.0.0")
        set_key(env_file, "FAB_MODEL_PACK", str(project_dir / "model_pack.v"))

    # Create project-specific .env file for testing
    project_dotenv_file = tmp_path / "project_specific.env"
    project_dotenv_file.touch()
    set_key(project_dotenv_file, "FAB_PROJ_DIR", str(project_dotenv_dir))

    # Create project-specific .env file that doesn't set FAB_PROJ_DIR (for
    # fallback tests)
    project_dotenv_fallback_file = tmp_path / "project_fallback.env"
    project_dotenv_fallback_file.touch()
    set_key(project_dotenv_fallback_file, "FAB_PROJ_LANG", "verilog")

    # Create global .env file for testing
    global_dotenv_file = tmp_path / "global.env"
    global_dotenv_file.touch()
    set_key(global_dotenv_file, "FAB_PROJ_DIR", str(global_dotenv_dir))

    return {
        "user_provided_dir": user_provided_dir,
        "env_var_dir": env_var_dir,
        "project_dotenv_dir": project_dotenv_dir,
        "global_dotenv_dir": global_dotenv_dir,
        "default_dir": default_dir,
        "project_dotenv_file": project_dotenv_file,
        "project_dotenv_fallback_file": project_dotenv_fallback_file,
        "global_dotenv_file": global_dotenv_file,
    }


def caplog(caplog: LogCaptureFixture) -> Generator[LogCaptureFixture]:
    """Configure log capturing for tests with loguru integration.

    This fixture sets up proper log capturing that works with loguru logger,
    ensuring that log messages are captured correctly during tests and cleaned
    up afterwards.

    Parameters
    ----------
    caplog : LogCaptureFixture
        Pytest's log capture fixture.

    Yields
    ------
    LogCaptureFixture
        The configured log capture fixture ready for use in tests.

    """
    handler_id = logger.add(
        caplog.handler,
        format="{message}",
        level=0,
        filter=lambda record: record["level"].no >= caplog.handler.level,
        enqueue=False,  # Set to 'True' if your test is spawning child processes.
    )
    yield caplog
    logger.remove(handler_id)

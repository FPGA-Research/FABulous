"""Global pytest configuration and fixtures for all FABulous tests."""

import os
from collections.abc import Generator
from pathlib import Path

import pytest
from pyfakefs import fake_filesystem
from _pytest.logging import LogCaptureFixture
from loguru import logger

from FABulous.FABulous_CLI.FABulous_CLI import FABulous_CLI
from FABulous.FABulous_CLI.helper import create_project, setup_logger
from FABulous.FABulous_settings import init_context, reset_context


def pytest_addoption(parser: pytest.Parser) -> None:  # type: ignore[name-defined]
    """Add command line option to include slow tests explicitly.

    Usage: pytest --runslow
    Without this flag, tests marked with @pytest.mark.slow are skipped via addopts filter.
    """
    parser.addoption(
        "--runslow",
        action="store_true",
        default=False,
        help="run tests marked as slow (overrides default '-m not slow')",
    )


def pytest_configure(config: pytest.Config) -> None:  # type: ignore[name-defined]
    # If --runslow is given, remove the '-m not slow' filter so slow tests run.
    if (
        config.getoption("runslow")
        and getattr(config.option, "markexpr", None) == "not slow"
    ):
        config.option.markexpr = ""


def normalize(block: str) -> list[str]:
    """Normalize a block of text to perform comparison.

    Strip newlines from the very beginning and very end, then split into
    separate lines and strip trailing whitespace from each line.
    """
    assert isinstance(block, str)
    block = block.strip("\n")
    return [line.rstrip() for line in block.splitlines()]


def run_cmd(app: FABulous_CLI, cmd: str) -> None:
    """Run a command in the given FABulous_CLI instance."""
    app.onecmd_plus_hooks(cmd)


def normalize_and_check_for_errors(caplog_text: str) -> list[str]:
    """Normalize a block of text and check for errors."""
    log = normalize(caplog_text)
    assert not any("ERROR" in line for line in log), "Error found in log messages"
    return log


@pytest.fixture(autouse=True)
def fabulous_test_environment(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """Set up global test environment for FABulous tests."""
    fabulous_root = str(Path(__file__).resolve().parent.parent / "FABulous")

    for i in os.environ:
        monkeypatch.delenv(i[0], raising=False)

    # Set test environment using monkeypatch for automatic cleanup
    monkeypatch.setenv("FAB_ROOT", fabulous_root)
    monkeypatch.setenv("FABULOUS_TESTING", "TRUE")
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(Path, "home", lambda _: tmp_path)
    (tmp_path / ".ciel" / "ihp-sg13g2").mkdir(parents=True, exist_ok=True)
    setup_logger(0, False)

    return


@pytest.fixture
def cli(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> FABulous_CLI:
    """Create a FABulous CLI instance for testing with a temporary project."""
    project_dir = tmp_path / "test_project"
    monkeypatch.setenv("FAB_PROJ_DIR", str(project_dir))
    create_project(project_dir)
    init_context(project_dir)
    cli = FABulous_CLI(
        "verilog",
        force=False,
        interactive=False,
        verbose=False,
        debug=True,
    )
    cli.debug = True
    run_cmd(cli, "load_fabric")
    return cli


@pytest.fixture(autouse=True)
def cleanup_logger() -> Generator[None]:
    """Ensure logger is properly cleaned up.

    Run after each test to prevent 'logging to closed file' errors when tests exit
    quickly.
    """
    yield
    # Remove all logger handlers to prevent logging to closed files
    # This handles cleanup for both regular logging and caplog fixtures
    logger.remove()


@pytest.fixture
def caplog(caplog: LogCaptureFixture) -> LogCaptureFixture:
    """Caplog fixture that integrates with loguru."""
    logger.add(
        caplog.handler,
        format="{message}",
        level=0,
        filter=lambda record: record["level"].no >= caplog.handler.level,
        enqueue=False,  # Set to 'True' if your test is spawning child processes.
    )
    return caplog
    # No need to remove specific handler - cleanup_logger removes all handlers


@pytest.fixture
def project(tmp_path: Path) -> Generator[Path]:
    project_dir = tmp_path / "test_project"
    create_project(project_dir)
    yield project_dir

    # Cleanup
    reset_context()  # Reset context after each test to avoid state leakage

"""Global pytest configuration and fixtures for all FABulous tests."""

import os
from collections.abc import Callable, Generator
from pathlib import Path

import pytest
from _pytest.logging import LogCaptureFixture
from loguru import logger

import fabulous.fabulous
import fabulous.fabulous_settings
from fabulous.fabric_definition.define import HDLType
from fabulous.fabulous_cli.fabulous_cli import FABulous_CLI
from fabulous.fabulous_cli.helper import create_project, setup_logger
from fabulous.fabulous_settings import init_context, reset_context


def pytest_addoption(parser: pytest.Parser) -> None:  # type: ignore[name-defined]
    """Add command line option to include slow tests explicitly.

    Usage: pytest --runslow
    Without this flag, tests marked with @pytest.mark.slow are skipped via
    addopts filter.
    """
    parser.addoption(
        "--runslow",
        action="store_true",
        default=False,
        help="run tests marked as slow (overrides default '-m not slow')",
    )


def pytest_configure(config: pytest.Config) -> None:  # type: ignore[name-defined]
    if (
        config.getoption("runslow")
        and getattr(config.option, "markexpr", None) == "not slow"
    ):
        config.option.markexpr = ""


def normalize(block: str) -> list[str]:
    """Normalize a block of text to perform comparison.

    Strip newlines from the very beginning and very end, then split into separate lines
    and strip trailing whitespace from each line.
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
def fabulous_test_environment(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> Generator[None]:
    """Set up global test environment for FABulous tests."""
    fabulous_root = str(Path(__file__).resolve().parent.parent / "FABulous")

    for key in list(os.environ.keys()):
        if key.startswith("FAB_"):
            monkeypatch.delenv(key, raising=False)

    fake_user_config_dir = tmp_path / ".fabulous"

    monkeypatch.setenv("FAB_ROOT", fabulous_root)
    monkeypatch.setenv("FABULOUS_TESTING", "TRUE")
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(Path, "home", lambda _: tmp_path)
    monkeypatch.setattr(
        fabulous.fabulous_settings, "FAB_USER_CONFIG_DIR", fake_user_config_dir
    )
    monkeypatch.setattr(fabulous.fabulous, "FAB_USER_CONFIG_DIR", fake_user_config_dir)
    monkeypatch.setattr(
        fabulous.fabulous_settings.ciel.manage,
        "enable",
        lambda *_args, **_kwargs: None,
    )
    monkeypatch.setattr(
        fabulous.fabulous_settings,
        "get_ciel_home",
        lambda: str(tmp_path / ".ciel"),
    )
    (tmp_path / ".ciel" / "ihp-sg13g2").mkdir(parents=True, exist_ok=True)
    setup_logger(0, False)

    yield

    reset_context()


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


@pytest.fixture
def project_factory(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> Callable[..., Path]:
    """Return a callable that creates a FABulous project in a temp directory.

    The returned callable accepts `lang` to choose Verilog vs VHDL and an optional
    `name` for the directory (default `test_project`). It also chdirs into the temp
    directory and sets `FAB_PROJ_DIR` via monkeypatch so context lookups resolve to the
    newly created project.
    """

    def _create(lang: HDLType = HDLType.VERILOG, name: str = "test_project") -> Path:
        project_dir = tmp_path / name
        monkeypatch.chdir(tmp_path)
        monkeypatch.setenv("FAB_PROJ_DIR", str(project_dir))
        create_project(project_dir, lang=lang)
        return project_dir

    return _create


@pytest.fixture
def project(project_factory: Callable[..., Path]) -> Path:
    """Verilog FABulous project in a temp directory."""
    return project_factory()


@pytest.fixture
def project_vhdl(project_factory: Callable[..., Path]) -> Path:
    """VHDL FABulous project in a temp directory."""
    return project_factory(lang=HDLType.VHDL)

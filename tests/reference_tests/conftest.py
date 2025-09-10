"""Pytest configuration and fixtures for reference testing."""

from pathlib import Path

import pytest

from FABulous.FABulous_CLI.helper import clone_git_repo
from tests.reference_tests.reference_projects_test import load_reference_projects_config


# Session-level configuration storage
class SessionConfig:
    """Centralized configuration that can be modified during session start."""

    def __init__(self) -> None:
        self.projects_dir: Path
        self.projects_conf: Path
        self.repo_url: str
        self.download_projects: bool
        self.verbose: bool


# global session config instance
_session_config = SessionConfig()


@pytest.fixture(scope="session")
def config_path() -> Path:
    """Get the reference projects config path from session config."""
    if _session_config.projects_conf is None:
        raise RuntimeError(
            "Session config not initialized. This should be set in pytest_configure."
        )
    return _session_config.projects_conf


@pytest.fixture(scope="session")
def projects_dir() -> Path:
    """Get the projects directory from session config."""
    if _session_config.projects_dir is None:
        raise RuntimeError(
            "Session config not initialized. This should be set in pytest_configure."
        )
    return _session_config.projects_dir


@pytest.fixture
def reference_projects_config(config_path: Path) -> list:
    """Load reference projects from config file."""
    if not config_path.exists():
        raise FileNotFoundError(f"Config file not found: {config_path}")

    return load_reference_projects_config(config_path)


def pytest_configure(config: pytest.Config) -> None:
    """Configure pytest with custom markers and initialize session config."""
    global _session_config

    # Initialize session config from CLI parameters (before test collection)
    _session_config.repo_url = config.getoption("--repo-url")
    _session_config.projects_dir = Path(config.getoption("--projects-dir"))
    _session_config.projects_conf = Path(
        config.getoption("--reference-projects-config")
    )
    _session_config.download_projects = config.getoption("--download-projects")
    _session_config.verbose = config.getoption("-v") > 0

    if _session_config.download_projects and (
        not clone_git_repo(_session_config.repo_url, _session_config.projects_dir)
    ):
        raise AssertionError("Could not set up reference projects")

    if not _session_config.projects_conf.exists():
        raise FileNotFoundError(
            f"Reference projects config file not found: {_session_config.projects_conf}"
        )


def pytest_addoption(parser: pytest.Parser) -> None:
    """Add custom command line options."""
    parser.addoption(
        "--download-projects",
        action="store_true",
        default=True,
        help="Download or update reference projects before running tests",
    )
    parser.addoption(
        "--repo-url",
        action="store",
        default="https://github.com/FPGA-Research/FABulous-demo-projects.git",
        help="GitHub repository URL for reference projects",
    )
    parser.addoption(
        "--projects-dir",
        action="store",
        default=str(Path(__file__).parent / "FABulous-demo-projects"),
        help="Local directory for reference projects",
    )
    parser.addoption(
        "--reference-projects-config",
        action="store",
        default=str(
            Path(__file__).parent
            / "FABulous-demo-projects"
            / "reference_projects_config.yaml"
        ),
        help="Reference projects configuration file path",
    )

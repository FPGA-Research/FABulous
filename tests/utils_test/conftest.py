"""Fixtures for all utils tests."""

from collections.abc import Generator
from pathlib import Path

import pytest

from FABulous.FABulous_CLI.helper import create_project
from FABulous.FABulous_settings import init_context, reset_context


@pytest.fixture(autouse=True)
def project(tmp_path: Path) -> Generator[Path]:
    """Create and initialize a temporary FABulous project directory."""
    project_dir = tmp_path / "project"
    create_project(project_dir)
    init_context(project_dir)
    yield project_dir
    reset_context()

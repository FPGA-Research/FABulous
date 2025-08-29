""" Pytest configuration for CLI tests. """

import os
from collections.abc import Generator
from pathlib import Path

import pytest

from FABulous.FABulous_CLI.helper import create_project

TILE = "LUT4AB"


@pytest.fixture
def project(tmp_path: Path) -> Generator[Path]:
    """Create a temporary FABulous project directory."""
    project_dir = tmp_path / "test_project"
    os.environ["FAB_PROJ_DIR"] = str(project_dir)
    create_project(project_dir)
    yield project_dir
    os.environ.pop("FAB_PROJ_DIR", None)

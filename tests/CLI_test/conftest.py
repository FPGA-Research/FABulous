"""Pytest configuration for CLI tests."""

from pathlib import Path

import pytest

from FABulous.FABulous_CLI.helper import create_project

TILE = "LUT4AB"


@pytest.fixture
def project(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Create a temporary FABulous project directory."""
    project_dir = tmp_path / "test_project"
    monkeypatch.setenv("FAB_PROJ_DIR", str(project_dir))
    create_project(project_dir)
    return project_dir

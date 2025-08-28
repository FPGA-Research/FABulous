"""Pytest configuration for CLI tests."""

import os
from collections.abc import Generator
from pathlib import Path

import pytest

from FABulous.FABulous_CLI.FABulous_CLI import FABulous_CLI
from FABulous.FABulous_CLI.helper import create_project, setup_logger
from tests.conftest import run_cmd

TILE = "LUT4AB"


@pytest.fixture
def cli(tmp_path: Path) -> Generator[FABulous_CLI]:
    projectDir = tmp_path / "test_project"
    os.environ["FAB_PROJ_DIR"] = str(projectDir)
    create_project(projectDir)
    setup_logger(0, False)
    cli = FABulous_CLI(writerType="verilog", projectDir=projectDir, enteringDir=tmp_path)
    cli.debug = True
    run_cmd(cli, "load_fabric")
    yield cli
    os.environ.pop("FAB_ROOT", None)
    os.environ.pop("FAB_PROJ_DIR", None)


@pytest.fixture
def project(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Create a temporary FABulous project directory."""
    project_dir = tmp_path / "test_project"
    monkeypatch.setenv("FAB_PROJ_DIR", str(project_dir))
    create_project(project_dir)
    return project_dir

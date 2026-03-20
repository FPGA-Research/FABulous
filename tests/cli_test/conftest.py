"""Pytest configuration for CLI tests."""

import subprocess
from pathlib import Path

import pytest
from dotenv import set_key
from pytest_mock import MockerFixture

from fabulous.fabulous_cli.fabulous_cli import FABulous_CLI
from fabulous.fabulous_cli.helper import create_project
from tests.conftest import run_cmd

TILE = "LUT4AB"

MOCK_COMPLETED_PROCESS = subprocess.CompletedProcess(args=[], returncode=0)


@pytest.fixture
def project(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Create a temporary FABulous project directory."""
    monkeypatch.chdir(tmp_path)
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

        # create an empty models pack file
        models_pack_file = project_dir / "models_pack.v"
        models_pack_file.touch()
        set_key(env_file, "FAB_PROJ_LANG", "verilog")
        set_key(env_file, "FAB_PROJ_VERSION", "1.0.0")
        set_key(env_file, "FAB_MODELS_PACK", str(models_pack_file))
        set_key(env_file, "FAB_PROJ_DIR", str(project_dir))

    # Create project-specific .env file for testing
    project_dotenv_file = tmp_path / "project_specific.env"
    project_dotenv_file.touch()
    set_key(project_dotenv_file, "FAB_PROJ_DIR", str(project_dotenv_dir))

    # Create project-specific .env file that doesn't set FAB_PROJ_DIR (for
    # fallback tests)
    project_dotenv_fallback_file = tmp_path / "project_fallback.env"
    project_dotenv_fallback_file.touch()
    set_key(project_dotenv_fallback_file, "FAB_PROJ_LANG", "verilog")
    set_key(project_dotenv_fallback_file, "FAB_PROJ_DIR", str(default_dir))

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


@pytest.fixture
def simulation_mock(cli: FABulous_CLI, mocker: MockerFixture) -> None:
    """Prepare a CLI instance for simulation tests.

    Mocks subprocess.run, generates the fabric, creates the required design artifacts
    (.json, .fasm, .bin), and runs bitstream generation.
    """
    mocker.patch("subprocess.run", return_value=MOCK_COMPLETED_PROCESS)
    run_cmd(cli, "run_FABulous_fabric")

    user_design = cli.projectDir / "user_design"
    for suffix in (".json", ".fasm", ".bin"):
        (user_design / f"sequential_16bit_en{suffix}").touch()

    run_cmd(cli, "run_FABulous_bitstream ./user_design/sequential_16bit_en.v")


def find_task_calls() -> list[list[str]]:
    """Return the command lists from subprocess calls that invoked ``task``.

    Must be called while ``subprocess.run`` is patched by ``simulation_mock``.
    """
    mock = subprocess.run  # already patched by simulation_mock
    assert hasattr(mock, "call_args_list"), "subprocess.run is not mocked"
    return [
        c.args[0]
        for c in mock.call_args_list
        if c.args and isinstance(c.args[0], (list, tuple)) and c.args[0][0] == "task"
    ]

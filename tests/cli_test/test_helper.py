"""Tests for FABulous CLI helper functions."""

import subprocess
from pathlib import Path

import pytest
from pytest_mock import MockerFixture

from fabulous.custom_exception import EnvironmentNotSet
from fabulous.fabric_definition.define import HDLType
from fabulous.fabulous_cli.helper import (
    create_project,
    run_task,
    update_project_version,
)


def test_create_project(tmp_path: Path) -> None:
    """Test creating a Verilog project."""
    # Test Verilog project creation
    project_dir = tmp_path / "test_project_verilog"
    create_project(project_dir)

    # Check if directories exist
    assert project_dir.exists()
    assert (project_dir / ".FABulous").exists()

    # Check if .env file exists and contains correct content
    env_file = project_dir / ".FABulous" / ".env"
    assert env_file.exists()
    env_content = env_file.read_text()
    assert "FAB_PROJ_LANG='verilog'" in env_content
    assert "FAB_PROJ_VERSION=" in env_content
    assert "FAB_PROJ_VERSION_CREATED=" in env_content
    assert "FAB_PDK='ihp-sg13g2'" in env_content

    # Check if template files were copied
    assert any(project_dir.glob("**/*.v")), (
        "No Verilog files found in project directory"
    )


def test_create_project_vhdl(tmp_path: Path) -> None:
    """Test creating a VHDL project."""
    # Test VHDL project creation
    project_dir = tmp_path / "test_project_vhdl"
    create_project(project_dir, lang=HDLType.VHDL)

    # Check if directories exist
    assert project_dir.exists()
    assert (project_dir / ".FABulous").exists()

    # Check if .env file exists and contains correct content
    env_file = project_dir / ".FABulous" / ".env"
    assert env_file.exists()
    assert "FAB_PROJ_LANG='vhdl'" in env_file.read_text()
    assert "FAB_PROJ_VERSION=" in env_file.read_text()
    assert "FAB_PROJ_VERSION_CREATED=" in env_file.read_text()

    # Check if template files were copied
    assert any(project_dir.glob("**/*.vhdl")), (
        "No VHDL files found in project directory"
    )


def test_update_project_version_success(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Test successful project version update."""
    env_dir = tmp_path / "proj" / ".FABulous"
    env_dir.mkdir(parents=True)
    env_file = env_dir / ".env"
    env_file.write_text("FAB_PROJ_VERSION=1.2.3\n")

    # Patch version() to return compatible version
    monkeypatch.setattr("fabulous.fabulous_cli.helper.version", lambda _: "1.2.4")

    assert update_project_version(tmp_path / "proj") is True
    assert "FAB_PROJ_VERSION='1.2.4'" in env_file.read_text()


def test_update_project_version_missing_version(tmp_path: Path) -> None:
    """Test version update when version is missing from `.env` file."""
    env_dir = tmp_path / "proj" / ".FABulous"
    env_dir.mkdir(parents=True)
    env_file = env_dir / ".env"
    env_file.write_text("FAB_PROJ_LANG=verilog\n")

    assert update_project_version(tmp_path / "proj") is False


def test_update_project_version_major_mismatch(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Test version update when major versions don't match."""

    env_dir = tmp_path / "proj" / ".FABulous"
    env_dir.mkdir(parents=True)
    env_file = env_dir / ".env"
    env_file.write_text("FAB_PROJ_VERSION=1.2.3\n")

    monkeypatch.setattr("fabulous.fabulous_cli.helper.version", lambda _: "2.0.0")

    assert update_project_version(tmp_path / "proj") is False


# --- run_task tests ---


def test_run_task_basic(tmp_path: Path, mocker: MockerFixture) -> None:
    """Test run_task calls subprocess.run with correct arguments."""
    mocker.patch("shutil.which", return_value="/usr/bin/task")
    m = mocker.patch("subprocess.run")

    run_task("run-simulation", task_dir=tmp_path)

    m.assert_called_once_with(
        ["task", "run-simulation"],
        cwd=tmp_path,
        check=True,
    )


def test_run_task_with_vars(tmp_path: Path, mocker: MockerFixture) -> None:
    """Test run_task passes variables as VAR=value arguments."""
    mocker.patch("shutil.which", return_value="/usr/bin/task")
    m = mocker.patch("subprocess.run")

    run_task(
        "run-simulation",
        task_dir=tmp_path,
        task_vars={"WAVEFORM_TYPE": "vcd", "EXTRA_IVERILOG_FLAGS": "-DFOO"},
    )

    call_args = m.call_args.args[0]
    assert call_args[0] == "task"
    assert call_args[1] == "run-simulation"
    assert "WAVEFORM_TYPE=vcd" in call_args
    assert "EXTRA_IVERILOG_FLAGS=-DFOO" in call_args


def test_run_task_verbose(tmp_path: Path, mocker: MockerFixture) -> None:
    """Test run_task adds --verbose flag when verbose is True."""
    mocker.patch("shutil.which", return_value="/usr/bin/task")
    m = mocker.patch("subprocess.run")

    run_task("run-simulation", task_dir=tmp_path, verbose=True)

    call_args = m.call_args.args[0]
    assert "--verbose" in call_args


def test_run_task_not_installed(tmp_path: Path, mocker: MockerFixture) -> None:
    """Test run_task raises EnvironmentNotSet when task binary is missing."""
    mocker.patch("shutil.which", return_value=None)

    with pytest.raises(EnvironmentNotSet, match="task"):
        run_task("run-simulation", task_dir=tmp_path)


def test_run_task_propagates_subprocess_error(
    tmp_path: Path, mocker: MockerFixture
) -> None:
    """Test run_task propagates CalledProcessError from subprocess."""
    mocker.patch("shutil.which", return_value="/usr/bin/task")
    mocker.patch(
        "subprocess.run",
        side_effect=subprocess.CalledProcessError(1, "task"),
    )

    with pytest.raises(subprocess.CalledProcessError):
        run_task("run-simulation", task_dir=tmp_path)


# --- Taskfile.yml creation tests ---


def test_create_project_verilog_has_taskfile(tmp_path: Path) -> None:
    """Test that Verilog project creation includes Taskfile.yml."""
    project_dir = tmp_path / "test_project_taskfile_v"
    create_project(project_dir)

    taskfile = project_dir / "Test" / "Taskfile.yml"
    assert taskfile.exists(), "Taskfile.yml not found in Verilog project"

    content = taskfile.read_text()
    assert "iverilog" in content, "Verilog Taskfile should reference iverilog"
    assert "WAVEFORM_TYPE" in content, "Verilog Taskfile should have WAVEFORM_TYPE var"
    assert "EXTRA_IVERILOG_FLAGS" in content


def test_create_project_vhdl_has_taskfile(tmp_path: Path) -> None:
    """Test that VHDL project creation includes Taskfile.yml."""
    project_dir = tmp_path / "test_project_taskfile_vhdl"
    create_project(project_dir, lang=HDLType.VHDL)

    taskfile = project_dir / "Test" / "Taskfile.yml"
    assert taskfile.exists(), "Taskfile.yml not found in VHDL project"

    content = taskfile.read_text()
    assert "ghdl" in content, "VHDL Taskfile should reference ghdl"
    assert "GHDL_FLAGS" in content, "VHDL Taskfile should have GHDL_FLAGS var"
    assert "EXTRA_GHDL_FLAGS" in content

"""Tests for FABulous CLI helper functions."""

import shutil
import subprocess
from pathlib import Path

import pytest
from pytest_mock import MockerFixture

from fabulous.custom_exception import EnvironmentNotSet
from fabulous.fabric_definition.define import HDLType
from fabulous.fabulous_repl.fabulous_repl import FABulousREPL
from fabulous.fabulous_repl.helper import (
    create_project,
    register_tile_in_fabric_csv,
    run_task,
    update_project_version,
)
from tests.conftest import normalize_and_check_for_errors, run_cmd


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
    monkeypatch.setattr("fabulous.fabulous_repl.helper.version", lambda _: "1.2.4")

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

    monkeypatch.setattr("fabulous.fabulous_repl.helper.version", lambda _: "2.0.0")

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


def test_run_task_with_taskfile(tmp_path: Path, mocker: MockerFixture) -> None:
    """Test run_task passes --taskfile when a custom taskfile name is given."""
    mocker.patch("shutil.which", return_value="/usr/bin/task")
    m = mocker.patch("subprocess.run")

    run_task(
        "compile-yosys",
        task_dir=tmp_path,
        taskfile="compile.Taskfile.yml",
    )

    call_args = m.call_args.args[0]
    assert "--taskfile" in call_args
    idx = call_args.index("--taskfile")
    assert call_args[idx + 1] == "compile.Taskfile.yml"


def test_run_task_without_taskfile(tmp_path: Path, mocker: MockerFixture) -> None:
    """Test run_task omits --taskfile when taskfile is None (default)."""
    mocker.patch("shutil.which", return_value="/usr/bin/task")
    m = mocker.patch("subprocess.run")

    run_task("run-simulation", task_dir=tmp_path)

    call_args = m.call_args.args[0]
    assert "--taskfile" not in call_args


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
    assert "nvc" in content, "VHDL Taskfile should reference nvc"
    assert "GHDL_GLOBAL_FLAGS" in content, (
        "VHDL Taskfile should have GHDL_GLOBAL_FLAGS var"
    )
    assert "EXTRA_GHDL_FLAGS" in content
    assert "EXTRA_NVC_FLAGS" in content


def test_create_project_has_compile_taskfile(tmp_path: Path) -> None:
    """Test that project creation includes compile.Taskfile.yml."""
    project_dir = tmp_path / "test_project_compile"
    create_project(project_dir)

    compile_taskfile = project_dir / "Test" / "compile.Taskfile.yml"
    assert compile_taskfile.exists(), "compile.Taskfile.yml not found in Test/"

    content = compile_taskfile.read_text()
    assert "compile-yosys" in content
    assert "compile-nextpnr" in content
    assert "compile-bitgen" in content


def test_register_tile_in_fabric_csv(tmp_path: Path) -> None:
    """register_tile_in_fabric_csv appends Tile entry before ParametersEnd."""
    csv_path = tmp_path / "fabric.csv"
    csv_path.write_text("Tile,./Tile/LUT4AB/LUT4AB.csv,\nParametersEnd\n")

    dst_dir = tmp_path / "Tile" / "MY_TILE"
    dst_dir.mkdir(parents=True)
    (dst_dir / "MY_TILE.csv").touch()

    register_tile_in_fabric_csv(csv_path, dst_dir)

    csv_text = csv_path.read_text(encoding="utf-8")
    assert f"Tile,./{Path('Tile', 'MY_TILE', 'MY_TILE.csv')!s}" in csv_text


@pytest.mark.parametrize("src_kind", ["name", "absolute", "external"])
def test_clone_tile_various_src(
    src_kind: str,
    cli: FABulousREPL,
    caplog: pytest.LogCaptureFixture,
    tmp_path: Path,
) -> None:
    """Clone a tile into Tile/ using different source specifications."""
    if src_kind == "name":
        run_cmd(cli, "clone_tile LUT4AB MY_TILE")
    elif src_kind == "absolute":
        src_path = str((cli.projectDir / "Tile" / "LUT4AB").resolve())
        run_cmd(cli, f"clone_tile {src_path} MY_TILE")
    else:
        external_src = tmp_path / "external" / "LUT4AB"
        shutil.copytree(cli.projectDir / "Tile" / "LUT4AB", external_src)
        run_cmd(cli, f"clone_tile {external_src} MY_TILE")

    normalize_and_check_for_errors(caplog.text)

    dst_dir = cli.projectDir / "Tile" / "MY_TILE"
    assert dst_dir.is_dir()
    assert (dst_dir / "MY_TILE.csv").exists()
    assert not (dst_dir / "LUT4AB.csv").exists()

    csv_content = (dst_dir / "MY_TILE.csv").read_text(encoding="utf-8")
    assert "MY_TILE" in csv_content
    assert "LUT4AB" not in csv_content

    fabric_csv = cli.csvFile.read_text(encoding="utf-8")
    assert f"Tile,./{Path('Tile', 'MY_TILE', 'MY_TILE.csv')!s}" in fabric_csv

    lines = fabric_csv.splitlines()
    tile_idx = next(i for i, ln in enumerate(lines) if "MY_TILE" in ln)
    params_end_idx = next(
        i for i, ln in enumerate(lines) if ln.strip().startswith("ParametersEnd")
    )
    assert tile_idx < params_end_idx


def test_clone_supertile_creates_subtile_and_supertile_entries(
    cli: FABulousREPL, caplog: pytest.LogCaptureFixture
) -> None:
    """Cloning a supertile adds Tile entries for sub-tiles and a Supertile entry."""
    run_cmd(cli, "clone_tile DSP MY_DSP")
    normalize_and_check_for_errors(caplog.text)

    csv_text = cli.csvFile.read_text(encoding="utf-8")
    assert (
        f"Tile,./{Path('Tile', 'MY_DSP', 'MY_DSP_bot', 'MY_DSP_bot.csv')!s}" in csv_text
    )
    assert (
        f"Tile,./{Path('Tile', 'MY_DSP', 'MY_DSP_top', 'MY_DSP_top.csv')!s}" in csv_text
    )
    assert f"Supertile,./{Path('Tile', 'MY_DSP', 'MY_DSP.csv')!s}" in csv_text


@pytest.mark.parametrize(
    ("cmd", "error_fragment"),
    [
        ("clone_tile NONEXISTENT MY_TILE", "NONEXISTENT"),
        ("clone_tile LUT4AB LUT4AB_copy", "already exists"),
        ("clone_tile EMPTY_DIR MY_TILE", "not a valid FABulous tile"),
        ("clone_tile LUT4AB my-tile", "not a valid tile name"),
        ("clone_tile LUT4AB 1TILE", "not a valid tile name"),
    ],
)
def test_clone_tile_error_cases(
    cli: FABulousREPL,
    caplog: pytest.LogCaptureFixture,
    cmd: str,
    error_fragment: str,
) -> None:
    """Error cases log an ERROR with an informative message."""
    if "LUT4AB_copy" in cmd:
        (cli.projectDir / "Tile" / "LUT4AB_copy").mkdir(parents=True)
    if "EMPTY_DIR" in cmd:
        (cli.projectDir / "Tile" / "EMPTY_DIR").mkdir(parents=True)

    run_cmd(cli, cmd)

    assert "ERROR" in caplog.text
    assert error_fragment in caplog.text


def test_clone_tile_dst_absolute_path(
    cli: FABulousREPL, caplog: pytest.LogCaptureFixture, tmp_path: Path
) -> None:
    """Cloning to an absolute path places the tile outside the Tile directory."""
    dst_path = (tmp_path / "external_tiles" / "MY_TILE").resolve()
    run_cmd(cli, f"clone_tile LUT4AB {dst_path}")
    normalize_and_check_for_errors(caplog.text)

    assert dst_path.is_dir()
    assert (dst_path / "MY_TILE.csv").exists()

    csv_text = cli.csvFile.read_text(encoding="utf-8")
    expected_rel = dst_path.relative_to(cli.projectDir.resolve(), walk_up=True)
    assert f"Tile,./{Path(expected_rel, 'MY_TILE.csv')!s}" in csv_text


def test_clone_tile_dst_path_with_separator(
    cli: FABulousREPL, caplog: pytest.LogCaptureFixture
) -> None:
    """A dst argument containing a path separator is treated as a path, not a name."""
    dst_path = cli.projectDir / "Tile" / "subdir" / "MY_TILE"
    run_cmd(cli, f"clone_tile LUT4AB {dst_path}")
    normalize_and_check_for_errors(caplog.text)

    assert dst_path.is_dir()
    assert (dst_path / "MY_TILE.csv").exists()

    csv_text = cli.csvFile.read_text(encoding="utf-8")
    assert f"Tile,./{Path('Tile', 'subdir', 'MY_TILE', 'MY_TILE.csv')!s}" in csv_text


def test_clone_tile_no_register_skips_fabric_csv(
    cli: FABulousREPL, caplog: pytest.LogCaptureFixture
) -> None:
    """--no-register clones the tile directory but leaves fabric.csv unchanged."""
    csv_before = cli.csvFile.read_text(encoding="utf-8")

    run_cmd(cli, "clone_tile LUT4AB MY_TILE --no-register")
    normalize_and_check_for_errors(caplog.text)

    dst_dir = cli.projectDir / "Tile" / "MY_TILE"
    assert dst_dir.is_dir()
    assert (dst_dir / "MY_TILE.csv").exists()

    csv_after = cli.csvFile.read_text(encoding="utf-8")
    assert csv_after == csv_before
    assert "MY_TILE" not in csv_after

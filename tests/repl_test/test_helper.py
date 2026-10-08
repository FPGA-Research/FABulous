"""Tests for FABulous CLI helper functions."""

import shutil
import subprocess
from importlib import resources
from importlib.metadata import version
from pathlib import Path

import pytest
from dotenv import dotenv_values
from pytest_mock import MockerFixture, MockType

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


@pytest.mark.parametrize(
    ("lang", "suffix"),
    [(HDLType.VERILOG, "v"), (HDLType.VHDL, "vhdl")],
    ids=["verilog", "vhdl"],
)
def test_create_project(tmp_path: Path, lang: HDLType, suffix: str) -> None:
    """The project gets its settings, its language's templates and Taskfiles."""
    project_dir = tmp_path / "test_project"
    create_project(project_dir, lang=lang)

    package_version = version("FABulous-FPGA")
    assert dotenv_values(project_dir / ".FABulous" / ".env") == {
        "FAB_PROJ_LANG": str(lang),
        "FAB_PROJ_VERSION": package_version,
        "FAB_PROJ_VERSION_CREATED": package_version,
        "FAB_MODELS_PACK": str(Path("..") / "Fabric" / f"models_pack.{suffix}"),
        "FAB_PDK": "ihp-sg13g2",
    }

    # tile CSVs name the BEL sources of the chosen language
    lut4ab_dir = project_dir / "Tile" / "LUT4AB"
    tile_csv = (lut4ab_dir / "LUT4AB.csv").read_text()
    assert "{HDL_SUFFIX}" not in tile_csv
    assert f"LUT4c_frame_config_dffesr.{suffix}" in tile_csv
    assert (lut4ab_dir / f"LUT4c_frame_config_dffesr.{suffix}").is_file()

    package_files = resources.files("fabulous.fabric_files")
    lang_taskfile = package_files / f"FABulous_project_template_{lang}" / "Test"
    common_taskfile = package_files / "FABulous_project_template_common" / "Test"
    assert (project_dir / "Test" / "Taskfile.yml").read_text() == (
        lang_taskfile / "Taskfile.yml"
    ).read_text()
    assert (project_dir / "Test" / "compile.Taskfile.yml").read_text() == (
        common_taskfile / "compile.Taskfile.yml"
    ).read_text()


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
    assert env_file.read_text() == "FAB_PROJ_VERSION=1.2.3\n"


# --- run_task tests ---


@pytest.fixture
def subprocess_run_with_task_on_path(tmp_path: Path, mocker: MockerFixture) -> MockType:
    """Mock `subprocess.run` with `task` on PATH and none beside the interpreter."""
    mocker.patch("sys.executable", str(tmp_path / "python"))
    mocker.patch(
        "shutil.which",
        side_effect=lambda _, path=None: None if path else "/usr/bin/task",
    )
    return mocker.patch("subprocess.run")


@pytest.mark.parametrize(
    ("task_vars", "verbose", "taskfile", "expected_tail"),
    [
        (None, False, None, []),
        (
            {"WAVEFORM_TYPE": "vcd", "EXTRA_IVERILOG_FLAGS": "-DFOO"},
            False,
            None,
            ["WAVEFORM_TYPE=vcd", "EXTRA_IVERILOG_FLAGS=-DFOO"],
        ),
        (None, True, None, ["--verbose"]),
        (None, False, "compile.Taskfile.yml", ["--taskfile", "compile.Taskfile.yml"]),
        (
            {"DESIGN": "top"},
            True,
            "compile.Taskfile.yml",
            ["--taskfile", "compile.Taskfile.yml", "--verbose", "DESIGN=top"],
        ),
    ],
    ids=["bare", "vars", "verbose", "taskfile", "all"],
)
def test_run_task_command_line(
    tmp_path: Path,
    subprocess_run_with_task_on_path: MockType,
    task_vars: dict[str, str] | None,
    verbose: bool,
    taskfile: str | None,
    expected_tail: list[str],
) -> None:
    """`run_task` builds `task <name> [--taskfile F] [--verbose] [K=V...]`."""
    run_task(
        "run-simulation",
        task_dir=tmp_path,
        task_vars=task_vars,
        verbose=verbose,
        taskfile=taskfile,
    )

    subprocess_run_with_task_on_path.assert_called_once_with(
        ["/usr/bin/task", "run-simulation", *expected_tail],
        cwd=tmp_path,
        check=True,
    )


def test_run_task_not_installed(tmp_path: Path, mocker: MockerFixture) -> None:
    """Test run_task raises EnvironmentNotSet when task binary is missing."""
    mocker.patch("sys.executable", str(tmp_path / "python"))
    mocker.patch("shutil.which", return_value=None)

    with pytest.raises(EnvironmentNotSet, match="task"):
        run_task("run-simulation", task_dir=tmp_path)


def test_run_task_prefers_interpreter_local_binary(
    tmp_path: Path, mocker: MockerFixture
) -> None:
    """Test run_task uses the `task` shipped next to the interpreter.

    `uv tool install` leaves the environment's script directory off PATH, so the
    bundled binary must be found without it.
    """
    local = tmp_path / "task"
    local.touch(mode=0o755)
    mocker.patch("sys.executable", str(tmp_path / "python"))
    m = mocker.patch("subprocess.run")

    run_task("run-simulation", task_dir=tmp_path)

    assert m.call_args.args[0][0] == str(local)


def test_run_task_propagates_subprocess_error(
    tmp_path: Path, subprocess_run_with_task_on_path: MockType
) -> None:
    """Test run_task propagates CalledProcessError from subprocess."""
    subprocess_run_with_task_on_path.side_effect = subprocess.CalledProcessError(
        1, "task"
    )

    with pytest.raises(subprocess.CalledProcessError):
        run_task("run-simulation", task_dir=tmp_path)


def test_register_tile_in_fabric_csv(tmp_path: Path) -> None:
    """register_tile_in_fabric_csv appends Tile entry before ParametersEnd."""
    csv_path = tmp_path / "fabric.csv"
    csv_path.write_text("Tile,./Tile/LUT4AB/LUT4AB.csv,\nParametersEnd\n")

    dst_dir = tmp_path / "Tile" / "MY_TILE"
    dst_dir.mkdir(parents=True)
    (dst_dir / "MY_TILE.csv").touch()

    register_tile_in_fabric_csv(csv_path, dst_dir)

    # the entry copies the column count of the existing Tile rows
    assert csv_path.read_text(encoding="utf-8") == (
        "Tile,./Tile/LUT4AB/LUT4AB.csv,\n"
        f"Tile,./{Path('Tile', 'MY_TILE', 'MY_TILE.csv')!s},\n"
        "ParametersEnd\n"
    )


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
    """Error cases fail with an informative ERROR and clone or register nothing."""
    if "LUT4AB_copy" in cmd:
        (cli.projectDir / "Tile" / "LUT4AB_copy").mkdir(parents=True)
    if "EMPTY_DIR" in cmd:
        (cli.projectDir / "Tile" / "EMPTY_DIR").mkdir(parents=True)
    tiles_before = sorted(p.name for p in (cli.projectDir / "Tile").iterdir())
    csv_before = cli.csvFile.read_text(encoding="utf-8")

    run_cmd(cli, cmd)

    errors = [r.message for r in caplog.records if r.levelname == "ERROR"]
    assert len(errors) == 1
    assert error_fragment in errors[0]
    assert sorted(p.name for p in (cli.projectDir / "Tile").iterdir()) == tiles_before
    assert cli.csvFile.read_text(encoding="utf-8") == csv_before
    assert cli.exit_code == 1


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

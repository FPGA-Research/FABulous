"""Tests for the clone_tile CLI command."""

import shutil
from pathlib import Path

import pytest

from fabulous.fabulous_cli.fabulous_cli import FABulous_CLI
from tests.conftest import normalize_and_check_for_errors, run_cmd


def test_clone_simple_tile_creates_directory(
    cli: FABulous_CLI, caplog: pytest.LogCaptureFixture
) -> None:
    """Cloning a simple tile creates a new directory with renamed files.

    Parameters
    ----------
    cli : FABulous_CLI
        CLI instance with a loaded fabric.
    caplog : pytest.LogCaptureFixture
        Loguru-integrated log capture.
    """
    run_cmd(cli, "clone_tile LUT4AB MY_TILE")
    normalize_and_check_for_errors(caplog.text)

    dst_dir = cli.projectDir / "Tile" / "MY_TILE"
    assert dst_dir.is_dir()

    assert (dst_dir / "MY_TILE.csv").exists()
    assert not (dst_dir / "LUT4AB.csv").exists()


def test_clone_simple_tile_replaces_content(
    cli: FABulous_CLI, caplog: pytest.LogCaptureFixture
) -> None:
    """Cloning a simple tile replaces src name with dst name inside text files.

    Parameters
    ----------
    cli : FABulous_CLI
        CLI instance with a loaded fabric.
    caplog : pytest.LogCaptureFixture
        Loguru-integrated log capture.
    """
    run_cmd(cli, "clone_tile LUT4AB MY_TILE")
    normalize_and_check_for_errors(caplog.text)

    dst_dir = cli.projectDir / "Tile" / "MY_TILE"
    csv_content = (dst_dir / "MY_TILE.csv").read_text(encoding="utf-8")
    assert "MY_TILE" in csv_content
    assert "LUT4AB" not in csv_content


def test_clone_simple_tile_updates_fabric_csv(
    cli: FABulous_CLI, caplog: pytest.LogCaptureFixture
) -> None:
    """Cloning a simple tile appends a Tile entry to fabric.csv.

    Parameters
    ----------
    cli : FABulous_CLI
        CLI instance with a loaded fabric.
    caplog : pytest.LogCaptureFixture
        Loguru-integrated log capture.
    """
    run_cmd(cli, "clone_tile LUT4AB MY_TILE")
    normalize_and_check_for_errors(caplog.text)

    csv_text = cli.csvFile.read_text(encoding="utf-8")
    assert "Tile,./Tile/MY_TILE/MY_TILE.csv" in csv_text


def test_clone_tile_entry_before_parameters_end(
    cli: FABulous_CLI, caplog: pytest.LogCaptureFixture
) -> None:
    """New tile entry is inserted before ParametersEnd in fabric.csv.

    Parameters
    ----------
    cli : FABulous_CLI
        CLI instance with a loaded fabric.
    caplog : pytest.LogCaptureFixture
        Loguru-integrated log capture.
    """
    run_cmd(cli, "clone_tile LUT4AB MY_TILE")
    normalize_and_check_for_errors(caplog.text)

    lines = cli.csvFile.read_text(encoding="utf-8").splitlines()
    tile_idx = next(i for i, ln in enumerate(lines) if "MY_TILE" in ln)
    params_end_idx = next(
        i for i, ln in enumerate(lines) if ln.strip().startswith("ParametersEnd")
    )
    assert tile_idx < params_end_idx


def test_clone_supertile_creates_subtile_and_supertile_entries(
    cli: FABulous_CLI, caplog: pytest.LogCaptureFixture
) -> None:
    """Cloning a supertile adds Tile entries for sub-tiles and a Supertile entry.

    Parameters
    ----------
    cli : FABulous_CLI
        CLI instance with a loaded fabric.
    caplog : pytest.LogCaptureFixture
        Loguru-integrated log capture.
    """
    run_cmd(cli, "clone_tile DSP MY_DSP")
    normalize_and_check_for_errors(caplog.text)

    csv_text = cli.csvFile.read_text(encoding="utf-8")
    assert "Tile,./Tile/MY_DSP/MY_DSP_bot/MY_DSP_bot.csv" in csv_text
    assert "Tile,./Tile/MY_DSP/MY_DSP_top/MY_DSP_top.csv" in csv_text
    assert "Supertile,./Tile/MY_DSP/MY_DSP.csv" in csv_text


def test_clone_tile_src_not_found_logs_error(
    cli: FABulous_CLI, caplog: pytest.LogCaptureFixture
) -> None:
    """An error is logged when the source tile directory does not exist.

    Parameters
    ----------
    cli : FABulous_CLI
        CLI instance with a loaded fabric.
    caplog : pytest.LogCaptureFixture
        Loguru-integrated log capture.
    """
    run_cmd(cli, "clone_tile NONEXISTENT MY_TILE")

    assert "ERROR" in caplog.text
    assert "NONEXISTENT" in caplog.text


def test_clone_tile_dst_exists_logs_error(
    cli: FABulous_CLI, caplog: pytest.LogCaptureFixture
) -> None:
    """An error is logged when the destination tile directory already exists.

    Parameters
    ----------
    cli : FABulous_CLI
        CLI instance with a loaded fabric.
    caplog : pytest.LogCaptureFixture
        Loguru-integrated log capture.
    """
    dst_dir = cli.projectDir / "Tile" / "LUT4AB_copy"
    dst_dir.mkdir(parents=True)

    run_cmd(cli, "clone_tile LUT4AB LUT4AB_copy")

    assert "ERROR" in caplog.text
    assert "already exists" in caplog.text


def test_clone_tile_by_absolute_path(
    cli: FABulous_CLI, caplog: pytest.LogCaptureFixture
) -> None:
    """Cloning by absolute path uses the directory's base name for renaming.

    Parameters
    ----------
    cli : FABulous_CLI
        CLI instance with a loaded fabric.
    caplog : pytest.LogCaptureFixture
        Loguru-integrated log capture.
    """
    src_path = str((cli.projectDir / "Tile" / "LUT4AB").resolve())
    run_cmd(cli, f"clone_tile {src_path} MY_TILE")
    normalize_and_check_for_errors(caplog.text)

    dst_dir = cli.projectDir / "Tile" / "MY_TILE"
    assert dst_dir.is_dir()
    assert (dst_dir / "MY_TILE.csv").exists()
    assert not (dst_dir / "LUT4AB.csv").exists()

    csv_text = cli.csvFile.read_text(encoding="utf-8")
    assert "Tile,./Tile/MY_TILE/MY_TILE.csv" in csv_text


def test_clone_tile_by_relative_path(
    cli: FABulous_CLI, caplog: pytest.LogCaptureFixture, tmp_path: Path
) -> None:
    """Cloning by relative path resolves against cwd, not the project Tile/ directory.

    Parameters
    ----------
    cli : FABulous_CLI
        CLI instance with a loaded fabric.
    caplog : pytest.LogCaptureFixture
        Loguru-integrated log capture.
    tmp_path : Path
        Pytest temporary directory (used as cwd in tests).
    """
    # Copy LUT4AB to a location outside the project's Tile/ dir
    external_src = tmp_path / "external" / "LUT4AB"
    shutil.copytree(cli.projectDir / "Tile" / "LUT4AB", external_src)

    run_cmd(cli, f"clone_tile {external_src} MY_TILE")
    normalize_and_check_for_errors(caplog.text)

    dst_dir = cli.projectDir / "Tile" / "MY_TILE"
    assert dst_dir.is_dir()
    assert (dst_dir / "MY_TILE.csv").exists()

    csv_text = cli.csvFile.read_text(encoding="utf-8")
    assert "Tile,./Tile/MY_TILE/MY_TILE.csv" in csv_text


def test_clone_tile_dst_absolute_path(
    cli: FABulous_CLI, caplog: pytest.LogCaptureFixture, tmp_path: Path
) -> None:
    """Cloning to an absolute path places the tile outside the project Tile/ directory.

    Parameters
    ----------
    cli : FABulous_CLI
        CLI instance with a loaded fabric.
    caplog : pytest.LogCaptureFixture
        Loguru-integrated log capture.
    tmp_path : Path
        Pytest temporary directory.
    """
    dst_path = str((tmp_path / "external_tiles" / "MY_TILE").resolve())
    run_cmd(cli, f"clone_tile LUT4AB {dst_path}")
    normalize_and_check_for_errors(caplog.text)

    dst_dir = Path(dst_path)
    assert dst_dir.is_dir()
    assert (dst_dir / "MY_TILE.csv").exists()

    # fabric.csv entry should be a relative path from project root to dst
    csv_text = cli.csvFile.read_text(encoding="utf-8")
    expected_rel = Path(dst_path).relative_to(cli.projectDir, walk_up=True)
    assert f"Tile,./{expected_rel}/MY_TILE.csv" in csv_text


def test_clone_tile_dst_path_with_separator(
    cli: FABulous_CLI, caplog: pytest.LogCaptureFixture
) -> None:
    """A dst argument containing a path separator is treated as a path, not a name.

    Parameters
    ----------
    cli : FABulous_CLI
        CLI instance with a loaded fabric.
    caplog : pytest.LogCaptureFixture
        Loguru-integrated log capture.
    """
    dst_path = cli.projectDir / "Tile" / "subdir" / "MY_TILE"
    run_cmd(cli, f"clone_tile LUT4AB {dst_path}")
    normalize_and_check_for_errors(caplog.text)

    assert dst_path.is_dir()
    assert (dst_path / "MY_TILE.csv").exists()

    csv_text = cli.csvFile.read_text(encoding="utf-8")
    assert "Tile,./Tile/subdir/MY_TILE/MY_TILE.csv" in csv_text

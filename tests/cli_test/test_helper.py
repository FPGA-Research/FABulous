"""Tests for FABulous CLI helper functions."""

from pathlib import Path

import pytest
from pytest_mock import MockerFixture

from fabulous.fabric_definition.define import HDLType
from fabulous.fabulous_cli.helper import create_project, update_project_version


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
    assert "FAB_PROJ_LANG='verilog'" in env_file.read_text()
    assert "VERSION=" in env_file.read_text()
    assert "FAB_PROJ_VERSION=" in env_file.read_text()
    assert "FAB_PROJ_VERSION_CREATED=" in env_file.read_text()

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


@pytest.mark.parametrize(
    ("resolver_behavior", "expect_hash"),
    [
        ("abc123def456resolved", True),
        (None, False),
        (SystemExit(1), False),
    ],
    ids=["resolver_returns_hash", "resolver_returns_none", "resolver_sysexit"],
)
def test_create_project_pdk_hash_behavior(
    tmp_path: Path,
    mocker: MockerFixture,
    resolver_behavior: str | None | BaseException,
    expect_hash: bool,
) -> None:
    """Test create_project FAB_PDK_HASH behavior for resolver outcomes."""
    if isinstance(resolver_behavior, BaseException):
        mocker.patch(
            "fabulous.fabulous_cli.helper.get_pdk_hash",
            side_effect=resolver_behavior,
        )
    else:
        mocker.patch(
            "fabulous.fabulous_cli.helper.get_pdk_hash",
            return_value=resolver_behavior,
        )

    project_dir = tmp_path / "test_project_pdk_hash_behavior"
    create_project(project_dir)

    env_file = project_dir / ".FABulous" / ".env"
    assert env_file.exists()
    env_content = env_file.read_text()
    if expect_hash:
        assert "FAB_PDK_HASH='abc123def456resolved'" in env_content
    else:
        assert "FAB_PDK_HASH" not in env_content


def test_create_project_warns_when_pdk_not_in_ciel(
    tmp_path: Path, mocker: MockerFixture, caplog: pytest.LogCaptureFixture
) -> None:
    """Test warning when ihp-sg13g2 dir is missing inside ciel home."""
    # Make ciel home exist but without ihp-sg13g2 subdirectory
    ciel_home = tmp_path / ".ciel_empty"
    ciel_home.mkdir()
    mocker.patch(
        "fabulous.fabulous_cli.helper.get_ciel_home",
        return_value=str(ciel_home),
    )
    project_dir = tmp_path / "test_project_no_pdk"
    create_project(project_dir)

    env_file = project_dir / ".FABulous" / ".env"
    assert "FAB_PDK" not in env_file.read_text()
    assert any("IHP SG13G2 PDK not found" in r.message for r in caplog.records)


def test_create_project_warns_when_ciel_home_missing(
    tmp_path: Path, mocker: MockerFixture, caplog: pytest.LogCaptureFixture
) -> None:
    """Test warning when ciel home directory does not exist."""
    mocker.patch(
        "fabulous.fabulous_cli.helper.get_ciel_home",
        return_value=str(tmp_path / "nonexistent_ciel"),
    )
    project_dir = tmp_path / "test_project_no_ciel"
    create_project(project_dir)

    env_file = project_dir / ".FABulous" / ".env"
    assert "FAB_PDK" not in env_file.read_text()
    assert any("Cannot find ciel home" in r.message for r in caplog.records)


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

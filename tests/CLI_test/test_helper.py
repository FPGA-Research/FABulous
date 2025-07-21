import pytest

from FABulous.FABulous_CLI.helper import create_project, update_project_version


def test_create_project(tmp_path):
    # Test Verilog project creation
    project_dir = tmp_path / "test_project_verilog"
    create_project(project_dir)

    # Check if directories exist
    assert project_dir.exists()
    assert (project_dir / ".FABulous").exists()

    # Check if .env file exists and contains correct content
    env_file = project_dir / ".FABulous" / ".env"
    assert env_file.exists()
    assert "FAB_PROJ_LANG=verilog" in env_file.read_text()
    assert "VERSION=" in env_file.read_text()

    # Check if template files were copied
    assert any(project_dir.glob("**/*.v")), "No Verilog files found in project directory"


def test_create_project_vhdl(tmp_path):
    # Test VHDL project creation
    project_dir = tmp_path / "test_project_vhdl"
    create_project(project_dir, lang="vhdl")

    # Check if directories exist
    assert project_dir.exists()
    assert (project_dir / ".FABulous").exists()

    # Check if .env file exists and contains correct content
    env_file = project_dir / ".FABulous" / ".env"
    assert env_file.exists()
    assert "FAB_PROJ_LANG=vhdl" in env_file.read_text()
    assert "VERSION=" in env_file.read_text()

    # Check if template files were copied
    assert any(project_dir.glob("**/*.vhdl")), "No VHDL files found in project directory"


def test_create_project_existing_dir(tmp_path):
    # Test creating project in existing directory
    project_dir = tmp_path / "existing_dir"
    project_dir.mkdir()

    with pytest.raises(SystemExit):
        create_project(project_dir)


def test_update_project_version_success(tmp_path, monkeypatch):
    env_dir = tmp_path / "proj" / ".FABulous"
    env_dir.mkdir(parents=True)
    env_file = env_dir / ".env"
    env_file.write_text("VERSION=1.2.3\n")

    # Patch version() to return compatible version
    monkeypatch.setattr("FABulous.FABulous_CLI.helper.version", lambda _: "1.2.4")

    assert update_project_version(tmp_path / "proj") is True
    assert "VERSION='1.2.4'" in env_file.read_text()


def test_update_project_version_missing_version(tmp_path):
    env_dir = tmp_path / "proj" / ".FABulous"
    env_dir.mkdir(parents=True)
    env_file = env_dir / ".env"
    env_file.write_text("FAB_PROJ_LANG=verilog\n")

    assert update_project_version(tmp_path / "proj") is False


def test_update_project_version_major_mismatch(tmp_path, monkeypatch):
    env_dir = tmp_path / "proj" / ".FABulous"
    env_dir.mkdir(parents=True)
    env_file = env_dir / ".env"
    env_file.write_text("VERSION=1.2.3\n")

    monkeypatch.setattr("FABulous.FABulous_CLI.helper.version", lambda _: "2.0.0")

    assert update_project_version(tmp_path / "proj") is False


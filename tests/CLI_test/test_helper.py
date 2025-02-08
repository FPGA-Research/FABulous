import pytest

from FABulous.FABulous_CLI.helper import create_project


def test_create_project(tmp_path):
    # Test Verilog project creation
    project_dir = tmp_path / "test_project_verilog"
    create_project(str(project_dir))

    # Check if directories exist
    assert project_dir.exists()
    assert (project_dir / ".FABulous").exists()

    # Check if .env file exists and contains correct content
    env_file = project_dir / ".FABulous" / ".env"
    assert env_file.exists()
    assert env_file.read_text() == "FAB_PROJ_LANG=verilog\n"

    # Check if template files were copied
    assert any(
        project_dir.glob("**/*.v")
    ), "No Verilog files found in project directory"


def test_create_project_vhdl(tmp_path):
    # Test VHDL project creation
    project_dir = tmp_path / "test_project_vhdl"
    create_project(str(project_dir), type="vhdl")

    # Check if directories exist
    assert project_dir.exists()
    assert (project_dir / ".FABulous").exists()

    # Check if .env file exists and contains correct content
    env_file = project_dir / ".FABulous" / ".env"
    assert env_file.exists()
    assert env_file.read_text() == "FAB_PROJ_LANG=vhdl\n"

    # Check if template files were copied
    assert any(
        project_dir.glob("**/*.vhdl")
    ), "No VHDL files found in project directory"


def test_create_project_existing_dir(tmp_path):
    # Test creating project in existing directory
    project_dir = tmp_path / "existing_dir"
    project_dir.mkdir()

    with pytest.raises(SystemExit):
        create_project(str(project_dir))
        create_project(str(project_dir))

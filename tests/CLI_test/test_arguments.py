import os
import sys
import tarfile
from pathlib import Path
from subprocess import run

import pytest
from pytest_mock import MockerFixture

from FABulous.FABulous import main


def test_create_project(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Test project creation  to mock sys.argv"""
    # Mock sys.argv
    test_args = ["FABulous", "--createProject", str(tmp_path / "test_prj")]
    monkeypatch.setattr(sys, "argv", test_args)

    # Run main function
    with pytest.raises(SystemExit) as exc_info:
        main()

    # Verify project was created
    project_dir = tmp_path / "test_prj"
    assert project_dir.exists()
    assert (project_dir / ".FABulous").exists()
    assert exc_info.value.code == 0


def test_create_project_existing_dir(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture
) -> None:
    """Test project creation with existing directory"""
    existing_dir = tmp_path / "existing_dir"
    existing_dir.mkdir()

    test_args = ["FABulous", "--createProject", str(existing_dir)]
    monkeypatch.setattr(sys, "argv", test_args)

    # Expect SystemExit due to existing directory
    with pytest.raises(SystemExit) as exc_info:
        main()

    # Check that it exits with non-zero code
    assert exc_info.value.code != 0

    # Check captured output for error message
    captured = capsys.readouterr()
    assert "already exists" in captured.out


def test_create_project_with_no_name(monkeypatch: pytest.MonkeyPatch) -> None:
    """Test project creation with missing name argument"""
    test_args = ["FABulous", "--createProject"]
    monkeypatch.setattr(sys, "argv", test_args)

    # Expect SystemExit due to missing required argument
    with pytest.raises(SystemExit) as exc_info:
        main()

    # Should exit with non-zero code
    assert exc_info.value.code != 0


def test_fabulous_script(tmp_path: Path, project: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Test FABulous script execution"""
    # Create a test FABulous script file
    script_file = tmp_path / "test_script.fab"
    script_file.write_text("# Test FABulous script\nhelp\n")

    test_args = ["FABulous", str(project), "--FABulousScript", str(script_file)]
    monkeypatch.setattr(sys, "argv", test_args)

    with pytest.raises(SystemExit) as exc_info:
        main()
    # If no exception is raised, the test passes
    assert exc_info.value.code == 0


def test_fabulous_script_nonexistent_file(tmp_path: Path, project: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Test FABulous script with nonexistent file"""
    nonexistent_script = tmp_path / "nonexistent_script.fab"

    test_args = ["FABulous", str(project), "--FABulousScript", str(nonexistent_script)]
    monkeypatch.setattr(sys, "argv", test_args)

    with pytest.raises(SystemExit) as exc_info:
        main()

    assert exc_info.value.code != 0


@pytest.mark.skip("Skipping test for no project directory as it is passing due to state leaking")
def test_fabulous_script_with_no_project_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Test FABulous script with no project directory"""
    script_file = tmp_path / "test_script.fab"
    script_file.write_text("# Test FABulous script\n")

    test_args = ["FABulous", "--FABulousScript", str(script_file)]
    monkeypatch.setattr(sys, "argv", test_args)

    with pytest.raises(SystemExit) as exc_info:
        main()

    assert exc_info.value.code == 0


def test_tcl_script_execution(tmp_path: Path, project: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Test TCL script execution on a valid project"""
    # Create a TCL script
    tcl_script = tmp_path / "test_script.tcl"
    tcl_script.write_text('# TCL script with FABulous commands\nputs "Hello from TCL"\n')

    test_args = ["FABulous", str(project), "--TCLScript", str(tcl_script)]
    monkeypatch.setattr(sys, "argv", test_args)

    with pytest.raises(SystemExit) as exc_info:
        main()

    assert exc_info.value.code == 0
    # If no exception is raised, the test passes


def test_commands_execution(project: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Test direct command execution with -p/--commands"""
    test_args = ["FABulous", str(project), "--commands", "help; help"]
    monkeypatch.setattr(sys, "argv", test_args)

    with pytest.raises(SystemExit) as exc_info:
        main()
    assert exc_info.value.code == 0


def test_create_project_with_vhdl_writer(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Test project creation with VHDL writer"""
    project_dir = tmp_path / "test_vhdl_project"

    test_args = ["FABulous", "--createProject", str(project_dir), "--writer", "vhdl"]
    monkeypatch.setattr(sys, "argv", test_args)

    with pytest.raises(SystemExit) as exc_info:
        main()

    assert exc_info.value.code == 0
    assert project_dir.exists()
    assert (project_dir / ".FABulous").exists()
    assert "vhdl" in (project_dir / ".FABulous" / ".env").read_text()


def test_create_project_with_verilog_writer(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Test project creation with Verilog writer"""
    project_dir = tmp_path / "test_verilog_project"

    test_args = ["FABulous", "--createProject", str(project_dir), "--writer", "verilog"]
    monkeypatch.setattr(sys, "argv", test_args)

    with pytest.raises(SystemExit) as exc_info:
        main()

    assert exc_info.value.code == 0
    assert project_dir.exists()
    assert (project_dir / ".FABulous").exists()
    assert "verilog" in (project_dir / ".FABulous" / ".env").read_text()


def test_logging_functionality(tmp_path: Path, project: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Test log file creation and output"""
    log_file = tmp_path / "test.log"

    test_args = ["FABulous", str(project), "--commands", "help", "-log", str(log_file)]
    monkeypatch.setattr(sys, "argv", test_args)

    with pytest.raises(SystemExit) as exc_info:
        main()

    assert exc_info.value.code == 0
    assert log_file.exists()
    assert log_file.stat().st_size > 0  # Check if log file is not empty


def test_verbose_mode(project: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Test verbose mode execution"""
    test_args = ["FABulous", str(project), "--commands", "help", "-v"]
    monkeypatch.setattr(sys, "argv", test_args)

    with pytest.raises(SystemExit) as exc_info:
        main()
    assert exc_info.value.code == 0


def test_debug_mode(project: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Test debug mode functionality"""
    test_args = ["FABulous", str(project), "--commands", "help", "--debug"]
    monkeypatch.setattr(sys, "argv", test_args)

    with pytest.raises(SystemExit) as exc_info:
        main()

    assert exc_info.value.code == 0


def test_force_flag(project: Path, tmp_path: Path) -> None:
    """Test force flag functionality"""

    # Run with force flag
    result = run(
        [
            "FABulous",
            str(project),
            "--commands",
            "load_fabric non_existent",
            "--force",
        ],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 1

    # force flag with multiple commands
    result = run(
        [
            "FABulous",
            str(project),
            "--commands",
            "load_fabric non_exist; load_fabric non_exist",
            "--force",
        ],
        capture_output=True,
        text=True,
    )

    assert result.stdout.count("non_exist") == 2
    assert result.returncode == 1

    # force flag with FABulous script
    with (tmp_path / "test.fs").open("w") as f:
        f.write("load_fabric non_exist.csv\n")
        f.write("load_fabric non_exist.csv\n")

    result = run(
        [
            "FABulous",
            str(project),
            "--FABulousScript",
            str(tmp_path / "test.fs"),
            "--force",
        ],
        capture_output=True,
        text=True,
    )

    assert result.stdout.count("INFO: Loading fabric") == 3
    assert result.returncode == 1


def test_install_oss_cad_suite(project: Path, mocker: MockerFixture, monkeypatch: pytest.MonkeyPatch) -> None:
    """Test oss-cad-suite installation"""

    # Test installation (may fail if network unavailable, but should handle gracefully)
    class MockRequest:
        status_code = 200

        def json(self) -> dict:
            return {
                "assets": [
                    {
                        "name": ".tar.gz x64 linux darwin windows arm64",
                        "browser_download_url": "./something.tgz",
                    }
                ]
            }

        def iter_content(self, chunk_size: int = 1024) -> list:  # noqa: ARG002
            return []

    class MockTarFile:
        def __enter__(self) -> "MockTarFile":
            return self

        def __exit__(self, *args: object) -> None:
            pass

        def extractall(self, path: str) -> None:
            pass

    def mock_open(*_args: object, **_kwargs: object) -> MockTarFile:
        return MockTarFile()

    monkeypatch.setattr(tarfile, "open", mock_open)
    m = mocker.patch("requests.get", return_value=MockRequest())  # Mock network request for testing

    test_args = ["FABulous", str(project), "--install_oss_cad_suite"]
    monkeypatch.setattr(sys, "argv", test_args)
    with pytest.raises(SystemExit) as exc_info:
        main()

    assert exc_info.value.code == 0, "Installation should succeed without errors"
    assert m.call_count == 2


def test_script_mutually_exclusive(tmp_path: Path, project: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Test that FABulous script and TCL script are mutually exclusive"""
    # Create both script types
    fab_script = tmp_path / "test.fab"
    fab_script.write_text("help\n")
    tcl_script = tmp_path / "test.tcl"
    tcl_script.write_text("puts hello\n")

    test_args = [
        "FABulous",
        str(project),
        "--FABulousScript",
        str(fab_script),
        "--TCLScript",
        str(tcl_script),
    ]
    monkeypatch.setattr(sys, "argv", test_args)

    # Try to use both - should fail
    with pytest.raises(SystemExit) as exc_info:
        main()

    assert exc_info.value.code != 0


def test_invalid_project_directory(monkeypatch: pytest.MonkeyPatch) -> None:
    """Test error handling for invalid project directory"""
    invalid_dir = "/nonexistent/path/to/project"

    test_args = ["FABulous", invalid_dir, "--commands", "help"]
    monkeypatch.setattr(sys, "argv", test_args)

    with pytest.raises(SystemExit) as exc_info:
        main()

    assert exc_info.value.code != 0


def test_project_without_fabulous_folder(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture
) -> None:
    """Test error handling for directory without .FABulous folder"""
    regular_dir = tmp_path / "regular_directory"
    regular_dir.mkdir()

    test_args = ["FABulous", str(regular_dir), "--commands", "help"]
    monkeypatch.setattr(sys, "argv", test_args)

    with pytest.raises(SystemExit) as exc_info:
        main()

    assert exc_info.value.code != 0
    captured = capsys.readouterr()
    assert "not a FABulous project" in captured.out


def test_nonexistent_script_file(project: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Test error handling for nonexistent script files"""

    # Try to run nonexistent FABulous script
    test_args = [
        "FABulous",
        str(project),
        "--FABulousScript",
        "/nonexistent/script.fab",
    ]
    monkeypatch.setattr(sys, "argv", test_args)

    with pytest.raises(SystemExit) as exc_info:
        main()
    assert exc_info.value.code != 0

    # Try to run nonexistent TCL script
    test_args = ["FABulous", str(project), "--TCLScript", "/nonexistent/script.tcl"]
    monkeypatch.setattr(sys, "argv", test_args)

    with pytest.raises(SystemExit) as exc_info:
        main()
    assert exc_info.value.code != 0


def test_empty_commands(project: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Test handling of empty command string"""
    test_args = ["FABulous", str(project), "--commands", ""]
    monkeypatch.setattr(sys, "argv", test_args)

    with pytest.raises(SystemExit) as exc_info:
        main()

    assert exc_info.value.code == 0


def test_create_project_with_invalid_writer(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Test project creation with an invalid writer"""
    project_dir = tmp_path / "test_invalid_writer_project"

    test_args = [
        "FABulous",
        "--createProject",
        str(project_dir),
        "--writer",
        "invalid_writer",
    ]
    monkeypatch.setattr(sys, "argv", test_args)

    with pytest.raises(SystemExit) as exc_info:
        main()

    assert exc_info.value.code != 0


def test_project_directory_priority_order(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Test that project directory priority order is followed:
    1. User provided argument (highest priority)
    2. Environment variables (FAB_PROJ_DIR)
    3. Project .env file (handled by setup functions)
    4. Global .env file (handled by setup functions)
    5. Default value - current working directory (lowest priority)
    """
    # Create multiple project directories for testing
    user_provided_dir = tmp_path / "user_provided_project"
    env_var_dir = tmp_path / "env_var_project"
    default_dir = tmp_path / "default_project"

    # Create all directories with .FABulous folders
    for project_dir in [user_provided_dir, env_var_dir, default_dir]:
        project_dir.mkdir()
        (project_dir / ".FABulous").mkdir()
        (project_dir / ".FABulous" / ".env").write_text("FAB_PROJ_LANG=verilog\n")
        (project_dir / ".FABulous" / ".env").write_text("VERSION=1.0.0\n")

    # Test 1: User provided argument should take highest priority over environment variable
    monkeypatch.setenv("FAB_PROJ_DIR", str(env_var_dir))
    monkeypatch.chdir(default_dir)

    result = run(
        ["FABulous", str(user_provided_dir), "--commands", "help"],
        capture_output=True,
        text=True,
    )

    # The log should show the user provided directory being used
    assert f"INFO: Setting current working directory to: {str(user_provided_dir)}" in result.stdout

    # Test 2: Environment variable should be used when no user argument provided
    env_with_fab_proj = os.environ.copy()
    env_with_fab_proj["FAB_PROJ_DIR"] = str(env_var_dir)

    result = run(
        ["FABulous", "--commands", "help"],
        capture_output=True,
        text=True,
        env=env_with_fab_proj,
    )
    # Should use the environment variable directory
    assert f"INFO: Setting current working directory to: {str(env_var_dir)}" in result.stdout

    # Test 3: Default directory (cwd) should be used when no argument or env var
    env_without_fab_proj = os.environ.copy()
    env_without_fab_proj.pop("FAB_PROJ_DIR", None)

    result = run(
        ["FABulous", "--commands", "help"],
        capture_output=True,
        text=True,
        cwd=str(default_dir),
        env=env_without_fab_proj,
    )

    assert f"INFO: Setting current working directory to: {str(default_dir)}" in result.stdout


def test_command_flag_with_stop_on_first_error(project: Path) -> None:
    """Test that using --commands with multiple commands raises an error on the first failure"""
    # Run with multiple commands, where the first one fails
    result = run(
        [
            "FABulous",
            str(project),
            "--commands",
            "load_fabric non_exist; load_fabric non_exist",
        ],
        capture_output=True,
        text=True,
    )

    assert result.stdout.count("non_exist") == 1
    assert result.returncode == 1

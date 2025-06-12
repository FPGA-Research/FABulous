from subprocess import run
import os


def test_create_project(tmp_path):
    result = run(
        ["FABulous", "--createProject", str(tmp_path / "test_prj")],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0


def test_create_project_existing_dir(tmp_path):
    existing_dir = tmp_path / "existing_dir"
    existing_dir.mkdir()
    result = run(
        ["FABulous", "--createProject", str(existing_dir)],
        capture_output=True,
        text=True,
    )
    assert "already exists" in result.stdout
    assert result.returncode != 0


def test_create_project_with_no_name():
    result = run(["FABulous", "--createProject"], capture_output=True, text=True)
    assert result.returncode != 0


def test_fabulous_script(tmp_path, project):
    # Create a test FABulous script file
    script_file = tmp_path / "test_script.fab"
    script_file.write_text("# Test FABulous script\nhelp\n")

    result = run(
        ["FABulous", str(project), "--FABulousScript", str(script_file)],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0


def test_fabulous_script_nonexistent_file(tmp_path, project):
    nonexistent_script = tmp_path / "nonexistent_script.fab"

    result = run(
        ["FABulous", str(project), "--FABulousScript", str(nonexistent_script)],
        capture_output=True,
        text=True,
    )
    assert result.returncode != 0


def test_fabulous_script_with_no_project_dir(tmp_path):
    script_file = tmp_path / "test_script.fab"
    script_file.write_text("# Test FABulous script\n")

    result = run(
        ["FABulous", "--FABulousScript", str(script_file)],
        capture_output=True,
        text=True,
    )
    assert result.returncode != 0


def test_tcl_script_execution(tmp_path, project):
    """Test TCL script execution on a valid project"""

    # Create a TCL script
    tcl_script = tmp_path / "test_script.tcl"
    tcl_script.write_text(
        '# TCL script with FABulous commands\nputs "Hello from TCL"\n'
    )

    # Run TCL script
    result = run(
        ["FABulous", str(project), "--TCLScript", str(tcl_script)],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0


def test_commands_execution(tmp_path, project):
    """Test direct command execution with -p/--commands"""
    # Run commands directly
    result = run(
        ["FABulous", str(project), "--commands", "help; help"],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0


def test_create_project_with_vhdl_writer(tmp_path):
    """Test project creation with VHDL writer"""
    project_dir = tmp_path / "test_vhdl_project"

    result = run(
        ["FABulous", "--createProject", str(project_dir), "--writer", "vhdl"],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0
    assert project_dir.exists()
    assert (project_dir / ".FABulous").exists()
    assert "vhdl" in (project_dir / ".FABulous" / ".env").read_text()


def test_create_project_with_verilog_writer(tmp_path):
    """Test project creation with Verilog writer"""
    project_dir = tmp_path / "test_verilog_project"

    result = run(
        ["FABulous", "--createProject", str(project_dir), "--writer", "verilog"],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0
    assert project_dir.exists()
    assert (project_dir / ".FABulous").exists()
    assert "verilog" in (project_dir / ".FABulous" / ".env").read_text()


def test_logging_functionality(tmp_path, project):
    """Test log file creation and output"""
    log_file = tmp_path / "test.log"

    # Run with logging using commands instead of script to avoid file handling issues
    result = run(
        ["FABulous", str(project), "--commands", "help", "-log", str(log_file)],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0
    assert log_file.exists()
    assert log_file.stat().st_size > 0  # Check if log file is not empty


def test_verbose_mode(project):
    """Test verbose mode execution"""

    # Run with verbose mode
    result = run(
        ["FABulous", str(project), "--commands", "help", "-v"],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0


def test_force_flag(project, tmp_path):
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

    with open(tmp_path / "test.fs", "w") as f:
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


def test_debug_mode(project):
    """Test debug mode functionality"""

    # Run with debug mode
    result = run(
        ["FABulous", str(project), "--commands", "help", "--debug"],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0


def test_install_oss_cad_suite(project, mocker):
    """Test oss-cad-suite installation"""

    # Test installation (may fail if network unavailable, but should handle gracefully)
    class MockRequest:
        status_code = 200

        def iter_content(self, chunk_size=1024):
            return []

    mocker.patch(
        "requests.get", return_value=MockRequest()
    )  # Mock network request for testing
    result = run(
        ["FABulous", str(project), "--install_oss_cad_suite"],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0


def test_script_mutually_exclusive(tmp_path, project):
    """Test that FABulous script and TCL script are mutually exclusive"""

    # Create both script types
    fab_script = tmp_path / "test.fab"
    fab_script.write_text("help\n")
    tcl_script = tmp_path / "test.tcl"
    tcl_script.write_text("puts hello\n")

    # Try to use both - should fail
    result = run(
        [
            "FABulous",
            str(project),
            "--FABulousScript",
            str(fab_script),
            "--TCLScript",
            str(tcl_script),
        ],
        capture_output=True,
        text=True,
    )
    assert result.returncode != 0


def test_invalid_project_directory():
    """Test error handling for invalid project directory"""
    invalid_dir = "/nonexistent/path/to/project"

    result = run(
        ["FABulous", invalid_dir, "--commands", "help"], capture_output=True, text=True
    )
    assert result.returncode != 0


def test_project_without_fabulous_folder(tmp_path):
    """Test error handling for directory without .FABulous folder"""
    regular_dir = tmp_path / "regular_directory"
    regular_dir.mkdir()

    result = run(
        ["FABulous", str(regular_dir), "--commands", "help"],
        capture_output=True,
        text=True,
    )
    assert result.returncode != 0
    assert "not a FABulous project" in result.stdout


def test_nonexistent_script_file(project):
    """Test error handling for nonexistent script files"""

    # Try to run nonexistent FABulous script - FABulous handles this gracefully
    result = run(
        ["FABulous", str(project), "--FABulousScript", "/nonexistent/script.fab"],
        capture_output=True,
        text=True,
    )
    # FABulous appears to handle missing script files gracefully and still executes successfully
    assert result.returncode == 1

    # Try to run nonexistent TCL script
    result = run(
        ["FABulous", str(project), "--TCLScript", "/nonexistent/script.tcl"],
        capture_output=True,
        text=True,
    )
    # Check that it at least attempts to handle the missing file
    assert "nonexistent" in result.stdout or "Problem" in result.stderr


def test_empty_commands(project):
    """Test handling of empty command string"""
    # Run with empty commands
    result = run(
        ["FABulous", str(project), "--commands", ""], capture_output=True, text=True
    )
    # Should handle gracefully
    assert result.returncode == 0


def test_create_project_with_invalid_writer(tmp_path, project):
    """Test project creation with an invalid writer"""
    project_dir = tmp_path / "test_invalid_writer_project"

    result = run(
        ["FABulous", "--createProject", str(project_dir), "--writer", "invalid_writer"],
        capture_output=True,
        text=True,
    )
    assert result.returncode != 0


def test_create_project_with_install_oss_cad_suite(tmp_path):
    """Test project creation with install_oss_cad_suite flag"""
    project_dir = tmp_path / "test_install_oss_cad_suite_project"

    result = run(
        ["FABulous", "--createProject", str(project_dir), "--install_oss_cad_suite"],
        capture_output=True,
        text=True,
    )
    assert result.returncode != 0


def test_project_directory_priority_order(tmp_path, monkeypatch, mocker):
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

    # Test 1: User provided argument should take highest priority over environment variable
    monkeypatch.setenv("FAB_PROJ_DIR", str(env_var_dir))
    monkeypatch.chdir(default_dir)

    result = run(
        ["FABulous", str(user_provided_dir), "--commands", "help"],
        capture_output=True,
        text=True,
    )

    # The log should show the user provided directory being used
    assert (
        f"INFO: Setting current working directory to: {str(user_provided_dir)}"
        in result.stdout
    )

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
    assert (
        f"INFO: Setting current working directory to: {str(env_var_dir)}"
        in result.stdout
    )

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

    assert (
        f"INFO: Setting current working directory to: {str(default_dir)}"
        in result.stdout
    )


def test_command_flag_with_stop_on_first_error(project):
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

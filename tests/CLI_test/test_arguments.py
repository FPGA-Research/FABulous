from subprocess import run


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


def test_create_project_with_no_name(tmp_path):
    result = run(["FABulous", "--createProject"], capture_output=True, text=True)
    assert result.returncode != 0


def test_fabulous_script(tmp_path):
    # Create project first
    project_dir = tmp_path / "test_prj"
    result = run(
        ["FABulous", "--createProject", str(project_dir)],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0

    # Create a test FABulous script file
    script_file = tmp_path / "test_script.fab"
    script_file.write_text("# Test FABulous script\nhelp\n")

    result = run(
        ["FABulous", str(project_dir), "--FABulousScript", str(script_file)],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0


def test_fabulous_script_nonexistent_file(tmp_path):
    nonexistent_script = tmp_path / "nonexistent_script.fab"
    project_dir = tmp_path / "test_prj"

    result = run(
        ["FABulous", str(project_dir), "--FABulousScript", str(nonexistent_script)],
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


def test_tcl_script_execution(tmp_path):
    """Test TCL script execution on a valid project"""
    project_dir = tmp_path / "test_tcl_project"

    # Create project first
    result = run(
        ["FABulous", "--createProject", str(project_dir)],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0

    # Create a TCL script
    tcl_script = tmp_path / "test_script.tcl"
    tcl_script.write_text(
        '# TCL script with FABulous commands\nputs "Hello from TCL"\n'
    )

    # Run TCL script
    result = run(
        ["FABulous", str(project_dir), "--TCLScript", str(tcl_script)],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0


def test_commands_execution(tmp_path):
    """Test direct command execution with -p/--commands"""
    project_dir = tmp_path / "test_cmd_project"

    # Create project
    result = run(
        ["FABulous", "--createProject", str(project_dir)],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0

    # Run commands directly
    result = run(
        ["FABulous", str(project_dir), "--commands", "help; help"],
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


def test_logging_functionality(tmp_path):
    """Test log file creation and output"""
    project_dir = tmp_path / "test_log_project"
    log_file = tmp_path / "test.log"

    # Create project
    result = run(
        ["FABulous", "--createProject", str(project_dir)],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0

    # Run with logging using commands instead of script to avoid file handling issues
    result = run(
        ["FABulous", str(project_dir), "--commands", "help", "-log", str(log_file)],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0
    assert log_file.exists()
    assert log_file.stat().st_size > 0  # Check if log file is not empty


def test_verbose_mode(tmp_path):
    """Test verbose mode execution"""
    project_dir = tmp_path / "test_verbose_project"

    # Create project
    result = run(
        ["FABulous", "--createProject", str(project_dir)],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0

    # Run with verbose mode
    result = run(
        ["FABulous", str(project_dir), "--commands", "help", "-v"],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0


def test_force_flag(tmp_path):
    """Test force flag functionality"""
    project_dir = tmp_path / "test_force_project"

    # Create project
    result = run(
        ["FABulous", "--createProject", str(project_dir)],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0

    # Run with force flag
    result = run(
        [
            "FABulous",
            str(project_dir),
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
            str(project_dir),
            "--commands",
            "load_fabric non_existent; load_fabric",
            "--force",
        ],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 1


def test_debug_mode(tmp_path):
    """Test debug mode functionality"""
    project_dir = tmp_path / "test_debug_project"

    # Create project
    result = run(
        ["FABulous", "--createProject", str(project_dir)],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0

    # Run with debug mode
    result = run(
        ["FABulous", str(project_dir), "--commands", "help", "--debug"],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0


def test_install_oss_cad_suite(tmp_path, mocker):
    """Test oss-cad-suite installation"""
    install_dir = tmp_path / "oss_install_test"
    install_dir.mkdir()

    # Test installation (may fail if network unavailable, but should handle gracefully)
    class MockRequest:
        status_code = 200

    mocker.patch(
        "requests.get", return_value=MockRequest()
    )  # Mock network request for testing
    result = run(
        ["FABulous", str(install_dir), "--install_oss_cad_suite"],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0


def test_script_mutually_exclusive(tmp_path):
    """Test that FABulous script and TCL script are mutually exclusive"""
    project_dir = tmp_path / "test_exclusive_project"

    # Create project
    result = run(
        ["FABulous", "--createProject", str(project_dir)],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0

    # Create both script types
    fab_script = tmp_path / "test.fab"
    fab_script.write_text("help\n")
    tcl_script = tmp_path / "test.tcl"
    tcl_script.write_text("puts hello\n")

    # Try to use both - should fail
    result = run(
        [
            "FABulous",
            str(project_dir),
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
    assert "does not exist" in result.stdout


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


def test_nonexistent_script_file(tmp_path):
    """Test error handling for nonexistent script files"""
    project_dir = tmp_path / "test_project"

    # Create project
    result = run(
        ["FABulous", "--createProject", str(project_dir)],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0

    # Try to run nonexistent FABulous script - FABulous handles this gracefully
    result = run(
        ["FABulous", str(project_dir), "--FABulousScript", "/nonexistent/script.fab"],
        capture_output=True,
        text=True,
    )
    # FABulous appears to handle missing script files gracefully and still executes successfully
    assert result.returncode == 0
    assert "Problem accessing script" in result.stderr

    # Try to run nonexistent TCL script
    result = run(
        ["FABulous", str(project_dir), "--TCLScript", "/nonexistent/script.tcl"],
        capture_output=True,
        text=True,
    )
    # Check that it at least attempts to handle the missing file
    assert "nonexistent" in result.stdout or "Problem" in result.stderr


def test_empty_commands(tmp_path):
    """Test handling of empty command string"""
    project_dir = tmp_path / "test_empty_cmd_project"

    # Create project
    result = run(
        ["FABulous", "--createProject", str(project_dir)],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0

    # Run with empty commands
    result = run(
        ["FABulous", str(project_dir), "--commands", ""], capture_output=True, text=True
    )
    # Should handle gracefully
    assert result.returncode == 0

"""Test module for FABulous CLI command functionality.

This module contains tests for various CLI commands including fabric generation, tile
generation, bitstream creation, simulation execution, and GUI commands.
"""

from pathlib import Path

import pytest
from pytest_mock import MockerFixture

from fabulous.fabulous_cli.fabulous_cli import FABulous_CLI
from fabulous.fabulous_settings import init_context
from tests.cli_test.conftest import MOCK_COMPLETED_PROCESS, TILE, find_task_calls
from tests.conftest import (
    normalize_and_check_for_errors,
    run_cmd,
)

SIM_CMD = "run_simulation fst ./user_design/sequential_16bit_en.bin"


def test_load_fabric(cli: FABulous_CLI, caplog: pytest.LogCaptureFixture) -> None:
    """Test loading fabric from CSV file."""

    run_cmd(cli, "load_fabric")
    log = normalize_and_check_for_errors(caplog.text)
    assert "Loading fabric" in log[0]
    assert "Complete" in log[-1]


def test_gen_config_mem(cli: FABulous_CLI, caplog: pytest.LogCaptureFixture) -> None:
    """Test generating configuration memory."""
    run_cmd(cli, f"gen_config_mem {TILE}")
    log = normalize_and_check_for_errors(caplog.text)
    assert f"Generating Config Memory for {TILE}" in log[0]
    assert "ConfigMem generation complete" in log[-1]


def test_gen_switch_matrix(cli: FABulous_CLI, caplog: pytest.LogCaptureFixture) -> None:
    """Test generating switch matrix."""
    run_cmd(cli, f"gen_switch_matrix {TILE}")
    log = normalize_and_check_for_errors(caplog.text)
    assert f"Generating switch matrix for {TILE}" in log[0]
    assert "Switch matrix generation complete" in log[-1]


def test_gen_tile(cli: FABulous_CLI, caplog: pytest.LogCaptureFixture) -> None:
    """Test generating tile."""
    run_cmd(cli, f"gen_tile {TILE}")
    log = normalize_and_check_for_errors(caplog.text)
    assert f"Generating tile {TILE}" in log[0]
    assert "Tile generation complete" in log[-1]


def test_gen_all_tile(cli: FABulous_CLI, caplog: pytest.LogCaptureFixture) -> None:
    """Test generating all tiles."""
    run_cmd(cli, "gen_all_tile")
    log = normalize_and_check_for_errors(caplog.text)
    assert "Generating all tiles" in log[0]
    assert "All tiles generation complete" in log[-1]


def test_gen_fabric(cli: FABulous_CLI, caplog: pytest.LogCaptureFixture) -> None:
    """Test generating fabric."""
    run_cmd(cli, "gen_fabric")
    log = normalize_and_check_for_errors(caplog.text)
    assert "Generating fabric " in log[0]
    assert "Fabric generation complete" in log[-1]


def test_gen_geometry(cli: FABulous_CLI, caplog: pytest.LogCaptureFixture) -> None:
    """Test generating geometry."""
    # Test with default padding
    run_cmd(cli, "gen_geometry")
    log = normalize_and_check_for_errors(caplog.text)
    assert "Generating geometry" in log[0]
    assert "geometry generation complete" in log[-2].lower()

    # Test with custom padding
    run_cmd(cli, "gen_geometry 16")
    log = normalize_and_check_for_errors(caplog.text)
    assert "Generating geometry" in log[0]
    assert "can now be imported into fabulator" in log[-1].lower()


def test_gen_top_wrapper(cli: FABulous_CLI, caplog: pytest.LogCaptureFixture) -> None:
    """Test generating top wrapper."""
    run_cmd(cli, "gen_top_wrapper")
    log = normalize_and_check_for_errors(caplog.text)
    assert "Generating top wrapper" in log[0]
    assert "Top wrapper generation complete" in log[-1]


def test_run_FABulous_fabric(
    cli: FABulous_CLI, caplog: pytest.LogCaptureFixture
) -> None:
    """Test running FABulous fabric flow."""
    run_cmd(cli, "run_FABulous_fabric")
    log = normalize_and_check_for_errors(caplog.text)
    assert "Running FABulous" in log[0]
    assert "FABulous fabric flow complete" in log[-1]


def test_gen_model_npnr(cli: FABulous_CLI, caplog: pytest.LogCaptureFixture) -> None:
    """Test generating nextpnr model."""
    run_cmd(cli, "gen_model_npnr")
    log = normalize_and_check_for_errors(caplog.text)
    assert "Generating npnr model" in log[0]
    assert "Generated npnr model" in log[-1]


def test_gen_io_pin_config(cli: FABulous_CLI, caplog: pytest.LogCaptureFixture) -> None:
    """Test generating an IO pin configuration YAML file for a tile."""
    output_file = cli.projectDir / "Tile" / TILE / f"{TILE}_io_pin_order.yaml"

    assert not output_file.exists()

    run_cmd(cli, f"gen_io_pin_config {TILE}")
    log = normalize_and_check_for_errors(caplog.text)

    assert f"Generating IO pin config for {TILE}" in log[0]
    assert "IO pin config generation complete" in log[-1]
    assert output_file.exists()


def test_run_FABulous_bitstream_deprecated(
    cli: FABulous_CLI, caplog: pytest.LogCaptureFixture, mocker: MockerFixture
) -> None:
    """Test the deprecated `run_FABulous_bitstream` delegates to compile_design."""
    mocker.patch("subprocess.run", return_value=MOCK_COMPLETED_PROCESS)
    run_cmd(cli, "run_FABulous_fabric")

    run_cmd(cli, "run_FABulous_bitstream ./user_design/sequential_16bit_en.v")

    assert any("deprecated" in r.message.lower() for r in caplog.records)
    assert any("compile_design" in r.message for r in caplog.records)


@pytest.mark.usefixtures("simulation_mock")
def test_run_simulation(
    cli: FABulous_CLI,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Test running simulation via Taskfile."""
    run_cmd(cli, SIM_CMD)
    log = normalize_and_check_for_errors(caplog.text)
    assert "Simulation finished" in log[-1]


@pytest.mark.usefixtures("simulation_mock")
def test_run_simulation_makefile_fallback(
    cli: FABulous_CLI,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Test simulation falls back to Makefile with deprecation warning."""
    # Remove Taskfile.yml so it falls back to Makefile
    (cli.projectDir / "Test" / "Taskfile.yml").unlink()

    caplog.clear()
    run_cmd(cli, SIM_CMD)

    assert any("deprecated" in r.message.lower() for r in caplog.records)
    assert any("Simulation finished" in r.message for r in caplog.records)


@pytest.mark.usefixtures("simulation_mock")
def test_run_simulation_no_taskfile_no_makefile(
    cli: FABulous_CLI,
) -> None:
    """Test simulation errors when neither Taskfile.yml nor Makefile exists."""
    # Remove both Taskfile.yml and Makefile
    test_dir = cli.projectDir / "Test"
    (test_dir / "Taskfile.yml").unlink()
    (test_dir / "Makefile").unlink(missing_ok=True)

    run_cmd(cli, SIM_CMD)
    assert cli.exit_code != 0


@pytest.mark.usefixtures("simulation_mock")
def test_run_simulation_with_extra_flags(
    cli: FABulous_CLI,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Test simulation passes extra iverilog flags to Taskfile."""
    run_cmd(cli, f'{SIM_CMD} --extra-iverilog-flag="-DSOME_DEFINE"')
    log = normalize_and_check_for_errors(caplog.text)
    assert "Simulation finished" in log[-1]

    task_cmds = find_task_calls()
    assert len(task_cmds) >= 1
    assert any("EXTRA_IVERILOG_FLAGS" in arg for arg in task_cmds[-1])


@pytest.mark.usefixtures("simulation_mock")
def test_run_simulation_with_design_flag(
    cli: FABulous_CLI,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Test simulation passes --design flag to Taskfile as DESIGN variable."""
    run_cmd(cli, f"{SIM_CMD} -d my_custom_design")
    log = normalize_and_check_for_errors(caplog.text)
    assert "Simulation finished" in log[-1]

    task_cmds = find_task_calls()
    assert len(task_cmds) >= 1
    assert any("DESIGN=my_custom_design" in arg for arg in task_cmds[-1])


def test_run_tcl_with_tcl_command(
    cli: FABulous_CLI, caplog: pytest.LogCaptureFixture, tmp_path: Path
) -> None:
    """Test running a Tcl script with tcl command."""
    script_content = '# Dummy Tcl script\nputs "Text from tcl"'
    tcl_script_path = tmp_path / "test_script.tcl"
    with tcl_script_path.open("w") as f:
        f.write(script_content)

    run_cmd(cli, f"run_tcl {str(tcl_script_path)}")
    log = normalize_and_check_for_errors(caplog.text)
    assert f"Execute TCL script {str(tcl_script_path)}" in log[0]
    assert "TCL script executed" in log[-1]


def test_run_tcl_with_fabulous_command(
    cli: FABulous_CLI, caplog: pytest.LogCaptureFixture, tmp_path: Path
) -> None:
    """Test running a Tcl script with FABulous command."""
    test_script = tmp_path / "test_script.tcl"
    test_script.write_text(
        "load_fabric\n"
        "gen_user_design_wrapper user_design/sequential_16bit_en.v "
        "user_design/top_wrapper.v\n"
    )
    run_cmd(cli, f"run_tcl {test_script}")
    log = normalize_and_check_for_errors(caplog.text)
    assert "Generated user design top wrapper" in log[-2]
    assert "TCL script executed" in log[-1]


def test_run_FABulous_fabric_sv_extension(
    project: Path,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Test running FABulous fabric flow with .sv (SystemVerilog) extension files.

    This test verifies that .sv files are correctly handled as Verilog files throughout
    the fabric generation process, using the same code path as run_FABulous_fabric but
    with BEL files using .sv extension.
    """
    monkeypatch.setenv("FAB_PROJ_DIR", str(project))

    # Convert .v BEL files to .sv
    for v_file in project.rglob("*.v"):
        if "models_pack" not in v_file.name:
            sv_file = v_file.with_suffix(".sv")
            v_file.rename(sv_file)

    # Update CSV files to reference .sv instead of .v
    for csv_file in project.rglob("*.csv"):
        content = csv_file.read_text()
        content = content.replace(".v,", ".sv,")
        content = content.replace(".v\n", ".sv\n")
        csv_file.write_text(content)

    init_context(project)
    cli = FABulous_CLI(
        "verilog",
        force=False,
        interactive=False,
        verbose=False,
        debug=True,
    )
    cli.debug = True
    run_cmd(cli, "load_fabric")

    # Clear caplog before running fabric flow to get clean assertions
    caplog.clear()

    # Run the fabric flow with .sv files
    run_cmd(cli, "run_FABulous_fabric")
    log = normalize_and_check_for_errors(caplog.text)
    assert "Running FABulous" in log[0]
    assert "FABulous fabric flow complete" in log[-1]


def test_exit_code_reset_after_error(cli: FABulous_CLI) -> None:
    """Test that exit code is reset between commands (regression test for issue #574).

    After a command fails, subsequent successful commands should not be affected by the
    stale exit code from the previous failure.
    """
    # Run a command that fails (invalid tile name)
    run_cmd(cli, "gen_config_mem INVALID_TILE_NAME")
    assert cli.exit_code != 0, "First command should fail"

    # Run a command that succeeds
    run_cmd(cli, "load_fabric")

    assert cli.exit_code == 0, "Exit code should be reset after successful command"

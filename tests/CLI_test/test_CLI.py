"""Test module for FABulous CLI command functionality.

This module contains tests for various CLI commands including fabric generation,
tile generation, bitstream creation, and simulation execution.
"""

from pathlib import Path

import pytest
from pytest_mock import MockerFixture

from FABulous.FABulous_CLI.FABulous_CLI import FABulous_CLI
from tests.CLI_test.conftest import TILE
from tests.conftest import (
    normalize_and_check_for_errors,
    run_cmd,
)


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


def test_run_FABulous_bitstream(
    cli: FABulous_CLI, caplog: pytest.LogCaptureFixture, mocker: MockerFixture
) -> None:
    """Test the `run_FABulous_bitstream` command."""

    class MockCompletedProcess:
        returncode = 0

    m = mocker.patch("subprocess.run", return_value=MockCompletedProcess())
    run_cmd(cli, "run_FABulous_fabric")
    Path(cli.projectDir / "user_design" / "sequential_16bit_en.json").touch()
    Path(cli.projectDir / "user_design" / "sequential_16bit_en.fasm").touch()
    run_cmd(cli, "run_FABulous_bitstream ./user_design/sequential_16bit_en.v")
    log = normalize_and_check_for_errors(caplog.text)
    assert "bitstream generation complete" in log[-1]
    assert m.call_count == 2


def test_run_simulation(
    cli: FABulous_CLI,
    caplog: pytest.LogCaptureFixture,
    mocker: MockerFixture,
) -> None:
    """Test running simulation."""

    class MockCompletedProcess:
        returncode = 0

    m = mocker.patch("subprocess.run", return_value=MockCompletedProcess())
    run_cmd(cli, "run_FABulous_fabric")
    Path(cli.projectDir / "user_design" / "sequential_16bit_en.json").touch()
    Path(cli.projectDir / "user_design" / "sequential_16bit_en.fasm").touch()
    Path(cli.projectDir / "user_design" / "sequential_16bit_en.bin").touch()
    run_cmd(cli, "run_FABulous_bitstream ./user_design/sequential_16bit_en.v")
    run_cmd(cli, "run_simulation fst ./user_design/sequential_16bit_en.bin")
    log = normalize_and_check_for_errors(caplog.text)
    assert "Simulation finished" in log[-1]
    assert m.call_count == 4


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


def test_multi_command_stop(cli: FABulous_CLI, mocker: MockerFixture) -> None:
    """Test that multi-command execution stops on first error without force flag."""
    m = mocker.patch("subprocess.run", side_effect=RuntimeError("Mocked error"))
    run_cmd(cli, "run_FABulous_bitstream ./user_design/sequential_16bit_en.v")

    m.assert_called_once()


def test_multi_command_force(cli: FABulous_CLI, mocker: MockerFixture) -> None:
    """Test that multi-command execution continues on error when force flag is set."""
    m = mocker.patch("subprocess.run", side_effect=RuntimeError("Mocked error"))
    cli.force = True
    run_cmd(cli, "run_FABulous_bitstream ./user_design/sequential_16bit_en.v")

    assert m.call_count == 1

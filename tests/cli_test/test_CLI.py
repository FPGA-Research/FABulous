"""Test module for FABulous CLI command functionality.

This module contains tests for various CLI commands including fabric generation,
tile generation, bitstream creation, simulation execution, and GUI commands.
"""

import argparse
import time
from pathlib import Path

import pytest
from pytest_mock import MockerFixture

from fabulous.fabulous_cli.fabulous_cli import FABulous_CLI
from tests.cli_test.conftest import TILE
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


def test_start_openroad_gui(
    cli: FABulous_CLI, caplog: pytest.LogCaptureFixture, mocker: MockerFixture
) -> None:
    """Test starting OpenROAD GUI."""

    class MockCompletedProcess:
        returncode = 0

    m = mocker.patch("subprocess.run", return_value=MockCompletedProcess())
    m2 = mocker.patch(
        "fabulous.fabulous_cli.fabulous_cli.FABulous_CLI._get_file_path",
        return_value="dummy.odb",
    )
    run_cmd(cli, "start_openroad_gui")
    log = normalize_and_check_for_errors(caplog.text)
    assert "Start OpenROAD GUI with odb: dummy.odb" in log[-1]
    assert m.call_count == 1


def test_start_klayout_gui(
    cli: FABulous_CLI, caplog: pytest.LogCaptureFixture, mocker: MockerFixture
) -> None:
    """Test starting OpenROAD GUI."""

    class MockCompletedProcess:
        returncode = 0

    m = mocker.patch("subprocess.run", return_value=MockCompletedProcess())
    m2 = mocker.patch(
        "fabulous.fabulous_cli.fabulous_cli.FABulous_CLI._get_file_path",
        return_value="dummy.gds",
    )
    run_cmd(cli, "start_klayout_gui")
    log = normalize_and_check_for_errors(caplog.text)
    assert "Start klayout GUI with gds: dummy.gds" in log[-2]
    assert m.call_count == 1


def test_start_gui_with_file_provided(
    cli: FABulous_CLI, caplog: pytest.LogCaptureFixture, mocker: MockerFixture
) -> None:
    """Test starting GUI when file is provided directly."""

    class MockCompletedProcess:
        returncode = 0

    m = mocker.patch("subprocess.run", return_value=MockCompletedProcess())
    run_cmd(cli, "start_openroad_gui provided.odb")
    log = normalize_and_check_for_errors(caplog.text)
    assert "Start OpenROAD GUI with odb: provided.odb" in log[-1]
    assert m.call_count == 1

    m = mocker.patch("subprocess.run", return_value=MockCompletedProcess())
    run_cmd(cli, "start_klayout_gui provided.gds")
    log = normalize_and_check_for_errors(caplog.text)
    assert "Start klayout GUI with gds: provided.gds" in log[-2]
    assert m.call_count == 1


class TestGetFilePath:
    """Tests for _get_file_path helper method."""

    @pytest.fixture
    def mock_cli(self, tmp_path: Path, mocker: MockerFixture) -> FABulous_CLI:
        """Create a mock CLI instance with project directory."""
        # Create a minimal CLI mock
        cli = mocker.MagicMock(spec=FABulous_CLI)
        cli.projectDir = tmp_path
        cli._get_file_path = FABulous_CLI._get_file_path.__get__(cli, FABulous_CLI)
        return cli

    def test_get_latest_file_from_fabric(
        self, mock_cli: FABulous_CLI, tmp_path: Path
    ) -> None:
        """Test getting latest file from Fabric directory."""
        # Create Fabric directory with ODB files
        fabric_dir = tmp_path / "Fabric"
        fabric_dir.mkdir()
        file1 = fabric_dir / "old.odb"
        file2 = fabric_dir / "new.odb"
        file1.touch()
        file2.touch()

        # Make file2 newer
        time.sleep(0.01)
        file2.touch()

        args = argparse.Namespace(last_run=True, fabric=True, tile=None)
        result = mock_cli._get_file_path(args, "odb")

        assert result == str(file2)

    def test_get_latest_file_from_tile(
        self, mock_cli: FABulous_CLI, tmp_path: Path
    ) -> None:
        """Test getting latest file from specific Tile directory."""
        # Create Tile directory with ODB files
        tile_dir = tmp_path / "Tile" / "LUT4AB"
        tile_dir.mkdir(parents=True)
        file1 = tile_dir / "design.odb"
        file1.touch()

        args = argparse.Namespace(last_run=True, fabric=False, tile="LUT4AB")
        result = mock_cli._get_file_path(args, "odb")

        assert result == str(file1)

    def test_get_file_raises_on_no_files(
        self, mock_cli: FABulous_CLI, tmp_path: Path
    ) -> None:
        """Test that FileNotFoundError is raised when no files exist."""
        # Create empty directory
        fabric_dir = tmp_path / "Fabric"
        fabric_dir.mkdir()

        args = argparse.Namespace(last_run=True, fabric=True, tile=None)

        with pytest.raises(FileNotFoundError, match="No .odb files found"):
            mock_cli._get_file_path(args, "odb")

    def test_get_latest_from_project_root(
        self, mock_cli: FABulous_CLI, tmp_path: Path
    ) -> None:
        """Test getting latest file from project root."""
        # Create ODB file in root
        file1 = tmp_path / "design.odb"
        file1.touch()

        args = argparse.Namespace(last_run=True, fabric=False, tile=None)
        result = mock_cli._get_file_path(args, "odb")

        assert result == str(file1)

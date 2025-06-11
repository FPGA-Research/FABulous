from pathlib import Path

from tests.conftest import (
    TILE,
    normalize_and_check_for_errors,
    run_cmd,
)


def test_load_fabric(cli, caplog):
    """Test loading fabric from CSV file"""
    run_cmd(cli, "load_fabric")
    log = normalize_and_check_for_errors(caplog.text)
    assert "Loading fabric" in log[0]
    assert "Complete" in log[-1]


def test_gen_config_mem(cli, caplog):
    """Test generating configuration memory"""
    run_cmd(cli, f"gen_config_mem {TILE}")
    log = normalize_and_check_for_errors(caplog.text)
    assert f"Generating Config Memory for {TILE}" in log[0]
    assert "ConfigMem generation complete" in log[-1]


def test_gen_switch_matrix(cli, caplog):
    """Test generating switch matrix"""
    run_cmd(cli, f"gen_switch_matrix {TILE}")
    log = normalize_and_check_for_errors(caplog.text)
    assert f"Generating switch matrix for {TILE}" in log[0]
    assert "Switch matrix generation complete" in log[-1]


def test_gen_tile(cli, caplog):
    """Test generating tile"""
    run_cmd(cli, f"gen_tile {TILE}")
    log = normalize_and_check_for_errors(caplog.text)
    assert f"Generating tile {TILE}" in log[0]
    assert "Tile generation complete" in log[-1]


def test_gen_all_tile(cli, caplog):
    """Test generating all tiles"""
    run_cmd(cli, "gen_all_tile")
    log = normalize_and_check_for_errors(caplog.text)
    assert "Generating all tiles" in log[0]
    assert "All tiles generation complete" in log[-1]


def test_gen_fabric(cli, caplog):
    """Test generating fabric"""
    run_cmd(cli, "gen_fabric")
    log = normalize_and_check_for_errors(caplog.text)
    assert "Generating fabric " in log[0]
    assert "Fabric generation complete" in log[-1]


def test_gen_geometry(cli, caplog):
    """Test generating geometry"""

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


def test_gen_top_wrapper(cli, caplog):
    """Test generating top wrapper"""
    run_cmd(cli, "gen_top_wrapper")
    log = normalize_and_check_for_errors(caplog.text)
    assert "Generating top wrapper" in log[0]
    assert "Top wrapper generation complete" in log[-1]


def test_run_FABulous_fabric(cli, caplog):
    """Test running FABulous fabric flow"""
    run_cmd(cli, "run_FABulous_fabric")
    log = normalize_and_check_for_errors(caplog.text)
    assert "Running FABulous" in log[0]
    assert "FABulous fabric flow complete" in log[-1]


def test_gen_model_npnr(cli, caplog):
    """Test generating Nextpnr model"""
    run_cmd(cli, "gen_model_npnr")
    log = normalize_and_check_for_errors(caplog.text)
    assert "Generating npnr model" in log[0]
    assert "Generated npnr model" in log[-1]


def test_run_FABulous_bitstream(cli, caplog, mocker):
    """Test the run_FABulous_bitstream command"""
    m = mocker.patch("subprocess.run", side_effect=RuntimeError("Mocked error"))
    run_cmd(cli, "run_FABulous_fabric")
    Path(cli.projectDir / "user_design" / "sequential_16bit_en.json").touch()
    Path(cli.projectDir / "user_design" / "sequential_16bit_en.fasm").touch()
    run_cmd(cli, "run_FABulous_bitstream ./user_design/sequential_16bit_en.v")
    log = normalize_and_check_for_errors(caplog.text)
    assert "Bitstream generated" in log[-1]
    assert m.call_count == 3


def test_run_simulation(cli, caplog, mocker):
    """Test running simulation"""
    m = mocker.patch("subprocess.run", side_effect=RuntimeError("Mocked error"))
    run_cmd(cli, "run_FABulous_fabric")
    Path(cli.projectDir / "user_design" / "sequential_16bit_en.json").touch()
    Path(cli.projectDir / "user_design" / "sequential_16bit_en.fasm").touch()
    Path(cli.projectDir / "user_design" / "sequential_16bit_en.bin").touch()
    run_cmd(cli, "run_FABulous_bitstream ./user_design/sequential_16bit_en.v")
    run_cmd(cli, "run_simulation fst ./user_design/sequential_16bit_en.bin")
    log = normalize_and_check_for_errors(caplog.text)
    assert "Simulation finished" in log[-1]
    assert m.call_count == 5


def test_run_tcl(cli, caplog, tmp_path):
    """Test running a Tcl script"""
    script_content = '# Dummy Tcl script\nputs "Text from tcl"'
    tcl_script_path = tmp_path / "test_script.tcl"
    with open(tcl_script_path, "w") as f:
        f.write(script_content)

    run_cmd(cli, f"run_tcl {str(tcl_script_path)}")
    log = normalize_and_check_for_errors(caplog.text)
    assert f"Execute TCL script {str(tcl_script_path)}" in log[0]
    assert "TCL script executed" in log[-1]


def test_multi_command_stop(cli, mocker):
    m = mocker.patch("subprocess.run", side_effect=RuntimeError("Mocked error"))
    run_cmd(cli, "run_FABulous_bitstream ./user_design/sequential_16bit_en.v")

    m.assert_called_once()

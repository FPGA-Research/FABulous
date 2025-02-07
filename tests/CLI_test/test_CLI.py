from tests.CLI_test.conftest import run_cmd


def test_load_fabric(cli, capsys):
    """Test loading fabric from CSV file"""
    # Test with default fabric.csv
    stdout, stderr = run_cmd(cli, "load_fabric")
    print(stdout)
    print(stderr)
    assert "Loading fabric" in stderr
    assert "Complete" in stderr

    # # Test with non-existent file
    # captured = syscap(cli, "load_fabric nonexistent.csv")
    # assert "error" in captured.err.lower()


def test_gen_config_mem(cli, syscap):
    """Test generating configuration memory"""
    # First load fabric
    syscap(cli, "load_fabric")

    # Test with valid tile
    captured = syscap(cli, "gen_config_mem CLB")
    assert "Generating Config Memory for CLB" in captured.err
    assert "complete" in captured.err.lower()

    # Test with invalid tile
    captured = syscap(cli, "gen_config_mem INVALID_TILE")
    assert "error" in captured.err.lower()


def test_gen_switch_matrix(cli):
    """Test generating switch matrix"""
    run_cmd(cli, "load_fabric")
    stdout, stderr = run_cmd(cli, "gen_switch_matrix CLB")
    assert any("Generating switch matrix for CLB" in line for line in stderr)
    assert any("complete" in line.lower() for line in stderr)


def test_gen_tile(cli):
    """Test generating tile"""
    run_cmd(cli, "load_fabric")
    stdout, stderr = run_cmd(cli, "gen_tile CLB")
    assert any("Generating tile CLB" in line for line in stderr)
    assert any("Generated tile CLB" in line for line in stderr)


def test_gen_all_tile(cli):
    """Test generating all tiles"""
    run_cmd(cli, "load_fabric")
    stdout, stderr = run_cmd(cli, "gen_all_tile")
    assert any("Generating all tiles" in line for line in stderr)
    assert any("Generated all tiles" in line for line in stderr)


def test_gen_fabric(cli):
    """Test generating fabric"""
    run_cmd(cli, "load_fabric")
    stdout, stderr = run_cmd(cli, "gen_fabric")
    assert any("Generating fabric" in line for line in stderr)
    assert any("complete" in line.lower() for line in stderr)


def test_gen_geometry(cli):
    """Test generating geometry"""
    run_cmd(cli, "load_fabric")

    # Test with default padding
    stdout, stderr = run_cmd(cli, "gen_geometry")
    assert any("Generating geometry" in line for line in stderr)
    assert any("complete" in line.lower() for line in stderr)

    stdout, stderr = run_cmd(cli, "gen_geometry 16")
    assert any("Generating geometry" in line for line in stderr)
    assert any("complete" in line.lower() for line in stderr)

    # Test with custom padding
    stdout, stderr = run_cmd(cli, "gen_geometry 16")
    assert any("Generating geometry" in line for line in stderr)
    assert any("complete" in line.lower() for line in stderr)

    # Test with invalid padding
    stdout, stderr = run_cmd(cli, "gen_geometry 100")
    assert any("error" in line.lower() for line in stderr)


def test_gen_bitstream_spec(cli):
    """Test generating bitstream specification"""
    run_cmd(cli, "load_fabric")
    stdout, stderr = run_cmd(cli, "gen_bitStream_spec")
    assert any("Generating bitstream specification" in line for line in stderr)
    assert any("Generated bitstream specification" in line for line in stderr)


def test_gen_top_wrapper(cli):
    """Test generating top wrapper"""
    run_cmd(cli, "load_fabric")
    stdout, stderr = run_cmd(cli, "gen_top_wrapper")
    assert any("Generating top wrapper" in line for line in stderr)
    assert any("Generated top wrapper" in line for line in stderr)


def test_gen_model_npnr(cli):
    """Test generating Nextpnr model"""
    run_cmd(cli, "load_fabric")
    stdout, stderr = run_cmd(cli, "gen_model_npnr")
    assert any("Generating npnr model" in line for line in stderr)
    assert any("Generated npnr model" in line for line in stderr)


def test_run_simulation(cli, syscap, tmp_path):
    """Test running simulation"""
    syscap(cli, "load_fabric")
    # Create a mock bitstream file
    bitstream = tmp_path / "test.bin"
    bitstream.write_bytes(b"mock bitstream")

    # Test FST format
    captured = syscap(cli, f"run_simulation fst {bitstream}")
    assert "Running simulation" in captured.err

    # Test VCD format
    captured = syscap(cli, f"run_simulation vcd {bitstream}")
    assert "Running simulation" in captured.err

    # Test with invalid file
    captured = syscap(cli, "run_simulation fst nonexistent.bin")
    assert "error" in captured.err.lower()


def test_run_FABulous_bitstream(cli, tmp_path):
    """Test running full FABulous bitstream flow"""
    run_cmd(cli, "load_fabric")
    # Create a mock Verilog file
    verilog = tmp_path / "test.v"
    verilog.write_text("module test(); endmodule")

    stdout, stderr = run_cmd(cli, f"run_FABulous_bitstream {verilog}")
    assert any("Running FABulous" in line for line in stdout)


def test_run_tcl(cli, tmp_path):
    """Test running TCL script"""
    # Create a mock TCL script
    tcl_script = tmp_path / "test.tcl"
    tcl_script.write_text('puts "Hello from TCL"')

    stdout, stderr = run_cmd(cli, f"run_tcl {tcl_script}")
    assert any("Execute TCL script" in line for line in stdout)
    assert any("TCL script executed" in line for line in stdout)

    # Test with invalid file
    stdout, stderr = run_cmd(cli, "run_tcl nonexistent.tcl")
    assert any("error" in line.lower() for line in stdout)


def test_place_and_route(cli, tmp_path):
    """Test place and route functionality"""
    run_cmd(cli, "load_fabric")
    # Create a mock JSON file
    json_file = tmp_path / "test.json"
    json_file.write_text("{}")

    stdout, stderr = run_cmd(cli, f"place_and_route {json_file}")
    assert any("Running Placement and Routing" in line for line in stdout)

    # Test with invalid file
    stdout, stderr = run_cmd(cli, "place_and_route nonexistent.json")
    assert any("error" in line.lower() for line in stdout)


def test_gen_bitstream_binary(cli, tmp_path):
    """Test generating bitstream binary"""
    run_cmd(cli, "load_fabric")
    # Create a mock FASM file
    fasm_file = tmp_path / "test.fasm"
    fasm_file.write_text("mock fasm")

    stdout, stderr = run_cmd(cli, f"gen_bitStream_binary {fasm_file}")
    assert any("Generating Bitstream" in line for line in stdout)

    # Test with invalid file
    stdout, stderr = run_cmd(cli, "gen_bitStream_binary nonexistent.fasm")
    assert any("error" in line.lower() for line in stdout)

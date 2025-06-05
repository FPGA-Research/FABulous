from subprocess import run
import os


def test_run_verilog_simulation_CIL(tmp_path):
    project_dir = tmp_path / "demo"
    result = run(["FABulous", "-c", str(project_dir)])
    assert result.returncode == 0

    result = run(
        ["FABulous", str(project_dir), "-fs", "./demo/FABulous.tcl"], cwd=tmp_path
    )
    assert result.returncode == 0


def test_run_verilog_simulation_makefile(tmp_path):
    project_dir = tmp_path / "demo"
    result = run(["FABulous", "-c", str(project_dir)])
    assert result.returncode == 0

    result = run(["make", "FAB_sim"], cwd=project_dir / "Test")
    assert result.returncode == 0


def test_run_vhdl_simulation_makefile(tmp_path):
    project_dir = tmp_path / "demo_vhdl"
    result = run(["FABulous", "-c", str(project_dir), "-w", "vhdl"])
    assert result.returncode == 0

    result = run(["make", "full_sim"], cwd=project_dir / "Test")
    assert result.returncode == 0

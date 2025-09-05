"""Integration tests for FABulous fabric generation."""

from pathlib import Path
from subprocess import run


def test_run_verilog_simulation_CLI(tmp_path: Path) -> None:
    """Test running Verilog simulation via CLI."""
    """Test running Verilog simulation via CLI."""
    project_dir = tmp_path / "demo"
    result = run(["FABulous", "-c", str(project_dir)])
    assert result.returncode == 0

    result = run(
        ["FABulous", str(project_dir), "-fs", "./demo/FABulous.tcl"], cwd=tmp_path
    )
    assert result.returncode == 0


def test_run_verilog_simulation_makefile(tmp_path: Path) -> None:
    """Test running Verilog simulation via Makefile."""
    """Test running Verilog simulation via Makefile."""
    project_dir = tmp_path / "demo"
    result = run(["FABulous", "-c", str(project_dir)])
    assert result.returncode == 0

    result = run(["make", "FAB_sim"], cwd=project_dir / "Test")
    assert result.returncode == 0


def test_run_vhdl_simulation_makefile(tmp_path: Path) -> None:
    """Test running VHDL simulation via Makefile."""
    """Test running VHDL simulation via Makefile."""
    project_dir = tmp_path / "demo_vhdl"
    result = run(["FABulous", "-c", str(project_dir), "-w", "vhdl"])
    assert result.returncode == 0

    result = run(["make", "FAB_sim"], cwd=project_dir / "Test")
    assert result.returncode == 0

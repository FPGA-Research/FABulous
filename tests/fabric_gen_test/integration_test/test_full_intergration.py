"""Integration tests for FABulous fabric generation."""

from collections.abc import Callable
from pathlib import Path
from subprocess import run

import pytest

from fabulous.fabric_definition.define import HDLType
from fabulous.fabulous_repl.fabulous_repl import FABulousREPL
from fabulous.fabulous_settings import init_context
from tests.conftest import run_cmd

_DESIGN_SUFFIX: dict[HDLType, str] = {HDLType.VERILOG: ".v", HDLType.VHDL: ".vhdl"}


@pytest.mark.parametrize("lang", [HDLType.VERILOG, HDLType.VHDL])
@pytest.mark.slow
def test_compile_and_simulate_demo(
    lang: HDLType, project_factory: Callable[..., Path]
) -> None:
    """Compile and simulate the demo design through the REPL."""
    project_dir = project_factory(lang=lang)
    init_context(project_dir)
    cli = FABulousREPL(
        str(lang), force=False, interactive=False, verbose=False, debug=True
    )
    run_cmd(cli, "load_fabric")
    run_cmd(cli, "run_FABulous_fabric")
    design = project_dir / "user_design" / f"sequential_16bit_en{_DESIGN_SUFFIX[lang]}"

    run_cmd(cli, f"compile_design {design}")
    assert cli.exit_code == 0, "compile_design failed"
    run_cmd(cli, f"run_simulation fst {design.with_suffix('.bin')}")
    assert cli.exit_code == 0, "run_simulation failed"


@pytest.mark.slow
def test_run_verilog_simulation_CLI(tmp_path: Path) -> None:
    """Test running Verilog simulation via CLI."""
    project_dir = tmp_path / "demo"
    result = run(["FABulous", "-c", str(project_dir)])
    assert result.returncode == 0

    result = run(
        ["FABulous", str(project_dir), "-fs", "./demo/FABulous.tcl"], cwd=tmp_path
    )
    assert result.returncode == 0


@pytest.mark.slow
def test_run_verilog_simulation_makefile(tmp_path: Path) -> None:
    """Test running Verilog simulation via Makefile."""
    project_dir = tmp_path / "demo"
    result = run(["FABulous", "-c", str(project_dir)])
    assert result.returncode == 0

    result = run(["task"], cwd=project_dir / "Test")
    assert result.returncode == 0


@pytest.mark.slow
def test_run_vhdl_simulation_makefile(tmp_path: Path) -> None:
    """Test running VHDL simulation via Makefile."""
    project_dir = tmp_path / "demo_vhdl"
    result = run(["FABulous", "-c", str(project_dir), "-w", "vhdl"])
    assert result.returncode == 0

    result = run(["task"], cwd=project_dir / "Test")
    assert result.returncode == 0

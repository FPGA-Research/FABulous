"""Integration tests for FABulous fabric generation."""

from collections.abc import Callable
from enum import StrEnum
from pathlib import Path
from subprocess import run

import pytest

from fabulous.fabric_definition.define import HDLType
from fabulous.fabulous_repl.fabulous_repl import FABulousREPL
from fabulous.fabulous_repl.helper import update_project_version
from fabulous.fabulous_settings import init_context
from tests.conftest import run_cmd

_DESIGN_SUFFIX: dict[HDLType, str] = {HDLType.VERILOG: ".v", HDLType.VHDL: ".vhdl"}


class ProjectLayout(StrEnum):
    """How the project under test came to be."""

    CURRENT = "current_project"
    PRE_REWORK = "pre_rework_project"
    UPGRADED = "upgraded_project"


@pytest.mark.parametrize("layout", list(ProjectLayout))
@pytest.mark.parametrize("lang", [HDLType.VERILOG, HDLType.VHDL])
@pytest.mark.slow
def test_compile_and_simulate_demo(
    lang: HDLType,
    layout: ProjectLayout,
    project_factory: Callable[..., Path],
    pre_rework_project_factory: Callable[..., Path],
) -> None:
    """Compile and simulate the demo design through the REPL.

    A pre-rework project is one created before the Yosys `synth_fabulous`
    rework; an upgraded one went through `update_project_version` after that.
    """
    match layout:
        case ProjectLayout.CURRENT:
            project_dir = project_factory(lang=lang)
        case ProjectLayout.PRE_REWORK:
            project_dir = pre_rework_project_factory(lang=lang)
        case ProjectLayout.UPGRADED:
            project_dir = pre_rework_project_factory(lang=lang)
            assert update_project_version(project_dir)
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


@pytest.mark.parametrize(
    "command",
    [["task", "run-yosys"], ["make", "run_yosys"]],
    ids=["task", "make"],
)
@pytest.mark.parametrize("lang", [HDLType.VERILOG, HDLType.VHDL])
@pytest.mark.slow
def test_hand_run_synthesis_after_upgrade(
    lang: HDLType,
    command: list[str],
    pre_rework_project_factory: Callable[..., Path],
) -> None:
    """Synthesis run by hand in `Test/` works once the project is upgraded."""
    project_dir = pre_rework_project_factory(lang=lang)
    assert update_project_version(project_dir)

    result = run(command, cwd=project_dir / "Test")

    assert result.returncode == 0
    assert (project_dir / "Test" / "build" / "sequential_16bit_en.json").is_file()


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

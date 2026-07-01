"""Gate-level (mixed-level) simulation of the demo FABulous user design.

The behavioural fabric wrapper ``eFPGA_top`` (with its configuration
controller) is kept, but the inner fabric core ``eFPGA`` and its tiles are
swapped for the post-place-and-route netlists hardened by the GDS / LibreLane
flow, linked against the PDK standard-cell models. The existing Verilog
``sequential_16bit_en_tb.v`` then drives the mixed-level DUT unchanged — the
exact same testbench the RTL ``run_simulation`` uses.

This mirrors the demo flow in the project ``FABulous.tcl`` (``load_fabric`` →
``run_FABulous_fabric`` → ``gen_user_design_wrapper`` → ``compile_design`` →
``run_simulation``), differing only in the final ``--gl`` step.

Marked ``@pytest.mark.gl`` and skipped from the default suite. Opt in with
``pytest --gl --gl-fabric-project=<path>`` and a Nix toolchain that provides
iverilog plus the PDK cell models (see the GL fixtures in this directory's
:mod:`conftest` for layout expectations).
"""

# cspell:words netlist iverilog pnr hdl

import shutil
from pathlib import Path
from typing import TYPE_CHECKING

import pytest

import fabulous.fabric_files as _fab_template_pkg
from tests.conftest import run_cmd

if TYPE_CHECKING:
    from fabulous.fabulous_repl.fabulous_repl import FABulousREPL

_DEMO_NAME = "sequential_16bit_en"
_DEMO_DESIGN = (
    Path(_fab_template_pkg.__file__).resolve().parent
    / "FABulous_project_template_verilog"
    / "user_design"
    / f"{_DEMO_NAME}.v"
)


@pytest.mark.gl
def test_gl_simulation_demo(
    cli: "FABulousREPL",
    pytestconfig: pytest.Config,
) -> None:
    """Compile the demo design and gate-level simulate it through ``--gl``.

    ``cli`` is bound to the per-test copy of the hardened project via the
    ``fabulous_project`` override, so the ``Fabric/macro/final_views`` netlists
    in that copy are what ``run_simulation --gl`` resolves.
    """
    project = cli.projectDir
    user_design_dir = project / "user_design"
    user_design_dir.mkdir(exist_ok=True)
    shutil.copy(_DEMO_DESIGN, user_design_dir / f"{_DEMO_NAME}.v")

    run_cmd(cli, "run_FABulous_fabric")
    run_cmd(
        cli,
        f"gen_user_design_wrapper user_design/{_DEMO_NAME}.v user_design/top_wrapper.v",
    )
    run_cmd(cli, f"compile_design user_design/{_DEMO_NAME}.v")

    bitstream = user_design_dir / f"{_DEMO_NAME}.bin"
    if not bitstream.exists():
        raise FileNotFoundError(f"compile_design did not produce {bitstream}")

    sim_lib_args = "".join(
        f" --gl-sim-libs {lib}" for lib in pytestconfig.getoption("gl_sim_libs")
    )
    run_cmd(cli, f"run_simulation --gl fst user_design/{_DEMO_NAME}.bin{sim_lib_args}")

    # run_cmd routes through cmd2, which swallows the CalledProcessError raised
    # when the Taskfile (iverilog/vvp) fails, so assert on the exit code and the
    # waveform artifact rather than relying on the command to propagate.
    assert cli.exit_code == 0, "run_simulation --gl reported a non-zero exit code"
    waveform = project / "Test" / "build" / f"{_DEMO_NAME}_gl.fst"
    if not waveform.exists():
        raise FileNotFoundError(
            f"gate-level simulation did not produce a waveform at {waveform}"
        )

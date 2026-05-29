"""Gate-level (GL) simulation of FABulous user designs.

The gate-level analogue of :mod:`test_designs_pattern`: it reuses the same
``@cocotb.test`` coroutines and the same bitstream-upload helper, but
simulates the post-PnR fabric netlist produced by LibreLane instead of the
behavioural Verilog FABulous emits.

The test is marked ``@pytest.mark.gl`` and is skipped from the default suite.
Opt in with ``pytest --rungl --gl-fabric-project=<path>`` (see the GL fixtures
in this directory's :mod:`conftest` for layout expectations).
"""

# cspell:words cocotb noqa netlist hdl pnr

from collections.abc import Callable
from pathlib import Path
from typing import TYPE_CHECKING

import pytest

from tests.fabric_gen_test.integration_test.conftest import (
    compile_user_design,
    stage_user_design,
)

if TYPE_CHECKING:
    from fabulous.fabulous_cli.fabulous_cli import FABulous_CLI
    from tests.fabric_gen_test.integration_test.conftest import GLSim

# The cocotb runner reuses the RTL test module — it owns the @cocotb.test
# coroutines — keeping GL and RTL coroutines in lockstep without a re-export
# shim.
_COCOTB_TEST_MODULE = Path(__file__).resolve().parent / "test_designs_pattern.py"


@pytest.mark.gl
@pytest.mark.parametrize(
    ("design_name", "testcase"),
    [
        pytest.param("passthrough", "cocotb_test_passthrough", id="passthrough"),
        pytest.param("addition", "cocotb_test_addition", id="addition"),
        pytest.param(
            "multiplication", "cocotb_test_multiplication", id="multiplication"
        ),
        pytest.param("all_ones", "cocotb_test_all_ones", id="all_ones"),
        pytest.param("all_zeros", "cocotb_test_all_zeros", id="all_zeros"),
        pytest.param("counter", "cocotb_test_counter", id="counter"),
        pytest.param("sys_reset", "cocotb_test_sys_reset", id="sys_reset"),
    ],
)
def test_design_pattern_gl(
    design_name: str,
    testcase: str,
    cli: "FABulous_CLI",
    gl_sim: "GLSim",
    cocotb_runner: Callable[..., None],
) -> None:
    """Compile a Verilog user design and simulate against the GL fabric netlist."""
    user_design, pcf = stage_user_design(cli.projectDir, design_name)
    bitstream = compile_user_design(cli, user_design, design_name, pcf)

    cocotb_runner(
        sources=gl_sim.sources,
        hdl_top_level=gl_sim.hdl_top,
        test_module_path=_COCOTB_TEST_MODULE,
        plusargs=[
            f"+FAB_BIT={bitstream}",
            f"+FAB_PCF={pcf}",
            f"+FAB_NUM_DATA_ROWS={cli.fabulousAPI.fabric.numberOfRows - 2}",
        ],
        testcase=testcase,
    )

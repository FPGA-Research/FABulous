"""Integration tests for FABulous user designs and the bitstream smoke flow."""

# cspell:words cocotb noqa

import random
import re
from collections.abc import Callable
from pathlib import Path

import cocotb
import pytest
from cocotb.clock import Clock
from cocotb.triggers import ClockCycles, Timer
from cocotb.types import Logic, LogicArray

from fabulous.fabric_definition.define import HDLType
from fabulous.fabulous_repl.fabulous_repl import FABulousREPL
from fabulous.fabulous_settings import init_context
from tests.conftest import run_cmd
from tests.fabric_gen_test.integration_test.conftest import (
    FabricClockedDUT,
    FabricConfigDUT,
    _collect_fabric_sources,
    compile_user_design,
    set_multiplexer_style,
    setup_fabric,
    stage_user_design,
)

_FABRIC_SUFFIX: dict[str, str] = {"verilog": ".v", "vhdl": ".vhdl"}

# Fabric → pad outputs; after bitstream upload these should leave X/Z.
_FABRIC_OUTPUT_RE = re.compile(
    r"^Tile_X(?P<tilex>\d+)Y(?P<tiley>\d+)_[A-Z]_I_top\d*$",
    re.IGNORECASE,
)

_THIS_FILE = Path(__file__).resolve()


@cocotb.test
async def cocotb_test_demo_bitstream_smoke(dut: FabricConfigDUT) -> None:
    """Replay the demo bitstream and assert fabric IO ports stay defined."""
    await setup_fabric(dut)
    await Timer(10, unit="ns")

    defined_outs = 0
    fabric_outputs = 0
    for element in dut:
        element_name: str = element._name  # noqa: SLF001
        if _FABRIC_OUTPUT_RE.match(element_name) is None:
            continue
        fabric_outputs += 1
        value = str(element.value)
        if not any(ch in value for ch in ("x", "X", "z", "Z")):
            defined_outs += 1
    assert fabric_outputs > 0, "No fabric `_I_top` ports found in DUT"
    assert defined_outs > 0, (
        f"Bitstream upload appears broken: {fabric_outputs} fabric output "
        "ports all still at X/Z"
    )


@cocotb.test
async def cocotb_test_passthrough(dut: FabricConfigDUT) -> None:
    """Drive random `a` values and assert `b == a`."""
    pcf = await setup_fabric(dut)

    width = len(pcf.signals["a"])

    for bit in range(width):
        for value in (0, 1):
            pcf.set("a", LogicArray.from_unsigned(0, width))
            pcf.set("a", Logic(value), index=bit)
            await Timer(10, unit="ns")
            observed = pcf.get("b").to_unsigned()
            expected = value << bit
            assert observed == expected, (
                f"passthrough bit {bit}={value}: expected b={expected:#x} "
                f"got b={observed:#x}"
            )

    for _ in range(16):
        value = random.randint(0, 2**width - 1)
        pcf.set("a", LogicArray.from_unsigned(value, width))
        await Timer(10, unit="ns")
        observed = pcf.get("b").to_unsigned()
        assert observed == value, f"passthrough mismatch: a={value:#x} b={observed:#x}"


@cocotb.test
async def cocotb_test_addition(dut: FabricConfigDUT) -> None:
    """Drive random `a, b` and assert `c == a + b`."""
    pcf = await setup_fabric(dut)

    a_width = len(pcf.signals["a"])
    b_width = len(pcf.signals["b"])
    for _ in range(32):
        val_a = random.randint(0, 2**a_width - 1)
        val_b = random.randint(0, 2**b_width - 1)
        pcf.set("a", LogicArray.from_unsigned(val_a, a_width))
        pcf.set("b", LogicArray.from_unsigned(val_b, b_width))
        await Timer(10, unit="ns")
        observed = pcf.get("c").to_unsigned()
        assert observed == val_a + val_b, (
            f"addition mismatch: a={val_a:#x} b={val_b:#x} "
            f"expected={val_a + val_b:#x} got={observed:#x}"
        )


@cocotb.test
async def cocotb_test_multiplication(dut: FabricConfigDUT) -> None:
    """Drive random `mult_a, mult_b` and assert `product == mult_a * mult_b`."""
    pcf = await setup_fabric(dut)

    a_width = len(pcf.signals["mult_a"])
    b_width = len(pcf.signals["mult_b"])
    for _ in range(32):
        val_a = random.randint(0, 2**a_width - 1)
        val_b = random.randint(0, 2**b_width - 1)
        pcf.set("mult_a", LogicArray.from_unsigned(val_a, a_width))
        pcf.set("mult_b", LogicArray.from_unsigned(val_b, b_width))
        await Timer(10, unit="ns")
        observed = pcf.get("product").to_unsigned()
        assert observed == val_a * val_b, (
            f"multiplication mismatch: a={val_a} b={val_b} "
            f"expected={val_a * val_b} got={observed}"
        )


@cocotb.test
async def cocotb_test_all_ones(dut: FabricConfigDUT) -> None:
    """Assert `all` reads back as all-ones after bitstream upload."""
    pcf = await setup_fabric(dut)

    width = len(pcf.signals["all"])
    expected = (1 << width) - 1
    observed = pcf.get("all").to_unsigned()
    assert observed == expected, (
        f"all_ones mismatch: expected {expected:#x} got {observed:#x}"
    )


@cocotb.test
async def cocotb_test_all_zeros(dut: FabricConfigDUT) -> None:
    """Assert `all` reads back as all-zeros after bitstream upload."""
    pcf = await setup_fabric(dut)

    observed = pcf.get("all").to_unsigned()
    assert observed == 0, f"all_zeros mismatch: expected 0 got {observed:#x}"


@cocotb.test
async def cocotb_test_counter(dut: FabricClockedDUT) -> None:
    """Reset, enable and count cycles, assert `d == cycles - 1`."""
    dut.UserCLK.value = 0
    pcf = await setup_fabric(dut)
    pcf.set("rst", Logic(1), index=0)
    pcf.set("ena", Logic(1), index=0)

    cocotb.start_soon(Clock(dut.UserCLK, 10, unit="ns").start())

    await ClockCycles(dut.UserCLK, 5)
    pcf.set("rst", Logic(0), index=0)
    pcf.set("ena", Logic(0), index=0)
    await ClockCycles(dut.UserCLK, 5)
    pcf.set("ena", Logic(1), index=0)

    num_cycles = 17
    await ClockCycles(dut.UserCLK, num_cycles)

    observed = pcf.get("d").to_unsigned()
    assert observed == num_cycles - 1, (
        f"counter mismatch: expected d={num_cycles - 1} got d={observed}"
    )


@cocotb.test
async def cocotb_test_sys_reset(dut: FabricClockedDUT) -> None:
    """Toggle rst, verify b latches the magic constant 0x7 then tracks a."""
    dut.UserCLK.value = 0
    pcf = await setup_fabric(dut)

    pcf.set("rst", Logic(1), index=0)
    pcf.set("a", LogicArray.from_unsigned(0x3, len(pcf.signals["a"])))

    cocotb.start_soon(Clock(dut.UserCLK, 10, unit="ns").start())

    await ClockCycles(dut.UserCLK, 5)
    observed = pcf.get("b").to_unsigned()
    assert observed == 0x7, f"sys_reset latch mismatch: expected 0x7 got {observed:#x}"

    pcf.set("rst", Logic(0), index=0)
    pcf.set("a", LogicArray.from_unsigned(0x5, len(pcf.signals["a"])))
    await ClockCycles(dut.UserCLK, 3)
    observed = pcf.get("b").to_unsigned()
    assert observed == 0x5, f"sys_reset follow mismatch: expected 0x5 got {observed:#x}"


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
@pytest.mark.parametrize("lang", ["verilog", "vhdl"])
@pytest.mark.parametrize("mux_style", ["custom", "generic"])
@pytest.mark.slow
def test_design_pattern(
    design_name: str,
    lang: str,
    mux_style: str,
    testcase: str,
    project_factory: Callable[..., Path],
    cocotb_runner: Callable[..., None],
) -> None:
    """Compile `design_name` for `lang` + `mux_style` and dispatch its cocotb test."""
    hdl_lang = HDLType(lang)
    project_dir = project_factory(lang=hdl_lang)
    set_multiplexer_style(project_dir, mux_style)
    # Bootstrap a lang-specific CLI inline. The global `cli` fixture is
    # verilog-only, so we can't reuse it across this test's lang parametrize.
    init_context(project_dir)
    cli = FABulousREPL(lang, force=False, interactive=False, verbose=False, debug=True)
    cli.debug = True
    run_cmd(cli, "load_fabric")

    user_design, pcf = stage_user_design(project_dir, design_name, lang=hdl_lang)
    run_cmd(cli, "run_FABulous_fabric")
    bitstream = compile_user_design(cli, user_design, design_name, pcf)

    cocotb_runner(
        sources=_collect_fabric_sources(project_dir, suffix=_FABRIC_SUFFIX[lang]),
        hdl_top_level="eFPGA",
        test_module_path=_THIS_FILE,
        plusargs=[
            f"+FAB_BIT={bitstream}",
            f"+FAB_PCF={pcf}",
            f"+FAB_NUM_DATA_ROWS={cli.fabulousAPI.fabric.numberOfRows - 2}",
        ],
        testcase=testcase,
    )

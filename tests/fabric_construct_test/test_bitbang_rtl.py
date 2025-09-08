"""RTL behavior validation for bitbang module using cocotb."""

import os
from pathlib import Path
from typing import Any, Protocol

import cocotb
import pytest
from cocotb.clock import Clock
from cocotb.triggers import RisingEdge

from tests.conftest import VERILOG_SOURCE_PATH, VHDL_SOURCE_PATH, CocotbRunner


class BitbangProtocol(Protocol):
    """Protocol defining the bitbang module interface."""

    # Inputs
    s_clk: Any  # Serial clock
    s_data: Any  # Serial data
    clk: Any  # System clock
    resetn: Any  # Reset (active low)

    # Outputs
    strobe: Any  # Data strobe output
    data: Any  # [31:0] Parallel data output
    active: Any  # Module active flag


def test_bitbang_verilog_rtl(cocotb_runner: CocotbRunner) -> None:
    """Test the bitbang module with Verilog source."""
    cocotb_runner(
        sources=[VERILOG_SOURCE_PATH / "Fabric" / "bitbang.v"],
        hdl_top_level="bitbang",
        test_module_path=Path(__file__),
    )


def test_bitbang_vhdl_rtl(cocotb_runner: CocotbRunner) -> None:
    """Test the bitbang module with VHDL source."""
    cocotb_runner(
        sources=[VHDL_SOURCE_PATH / "Fabric" / "bitbang.vhdl"],
        hdl_top_level="bitbang",
        test_module_path=Path(__file__),
    )


@pytest.mark.skip(reason="Cocotb test - run by simulation, not pytest")
@cocotb.test
async def test_bitbang_basic(dut: BitbangProtocol) -> None:
    """Test basic functionality of bitbang module."""
    # Start clock
    clock = Clock(dut.clk, 10, units="ns")
    cocotb.start_soon(clock.start())

    # Initialize inputs
    dut.s_clk.value = 0
    dut.s_data.value = 0
    dut.resetn.value = 0

    # Wait for reset
    await RisingEdge(dut.clk)
    await RisingEdge(dut.clk)
    dut.resetn.value = 1
    await RisingEdge(dut.clk)

    # Check initial state
    assert dut.strobe.value == 0, "strobe should be 0 initially"
    assert dut.active.value == 0, "active should be 0 initially"
    assert dut.data.value == 0, "data should be 0 initially"

    # Warm pipeline
    for _ in range(4):
        await RisingEdge(dut.clk)

    # Protocol: send data first, then ON pattern to latch it & assert active.
    test_data = 0x12345678
    await _send_serial_data_word(dut, test_data)
    # Now send ON pattern to latch
    await _send_serial_control_word(dut, 0xFAB1)
    for _ in range(16):
        await RisingEdge(dut.clk)
    assert dut.active.value == 1, "active should be 1 after ON_PATTERN"
    # Debug: capture internal shift register if accessible
    try:
        shifted = int(dut.serial_data.value)
        cocotb.log.info(
            f"DEBUG serial_data=0x{shifted:08x} latched_data=0x{int(dut.data.value):08x} expected=0x{test_data:08x}"
        )
    except AttributeError:
        cocotb.log.info("DEBUG serial_data not accessible")
        shifted = None
    if int(dut.data.value) != test_data:
        cocotb.log.warning(
            f"Data mismatch (expected 0x{test_data:08x} got 0x{int(dut.data.value):08x}); internal=0x{shifted:08x}"
            if shifted is not None
            else "Data mismatch"
        )
    # Deactivate
    await _send_serial_control_word(dut, 0xFAB0)
    for _ in range(16):
        await RisingEdge(dut.clk)
    assert dut.active.value == 0, "active should be 0 after OFF_PATTERN"
    await RisingEdge(dut.clk)

    test_words = [0x00000000, 0xFFFFFFFF, 0xAAAAAAAA, 0x55555555, 0x12345678]
    for i, word in enumerate(test_words):
        # Load new data first
        await _send_serial_data_word(dut, word)
        # Trigger latch
        await _send_serial_control_word(dut, 0xFAB1)
        for _ in range(16):
            await RisingEdge(dut.clk)
        assert int(dut.data.value) == word, (
            f"Word {i}: Expected data = 0x{word:08x}, got 0x{int(dut.data.value):08x}"
        )
    # Finally deactivate
    await _send_serial_control_word(dut, 0xFAB0)
    for _ in range(16):
        await RisingEdge(dut.clk)
    assert dut.active.value == 0


@pytest.mark.skip(reason="Cocotb test - run by simulation, not pytest")
@cocotb.test
async def test_bitbang_activation_deactivation(dut: BitbangProtocol) -> None:
    """Test bitbang activation and deactivation cycles."""
    # Start clock
    clock = Clock(dut.clk, 10, units="ns")
    cocotb.start_soon(clock.start())

    # Initialize and reset
    dut.s_clk.value = 0
    dut.s_data.value = 0
    dut.resetn.value = 0
    await RisingEdge(dut.clk)
    dut.resetn.value = 1
    await RisingEdge(dut.clk)

    # Test multiple activation/deactivation cycles
    for cycle in range(3):
        # Activate
        test_data = 0xDEADBEEF + cycle
        await _send_serial_data_word(dut, test_data)
        await _send_serial_control_word(dut, 0xFAB1)
        for _ in range(16):
            await RisingEdge(dut.clk)
        assert dut.active.value == 1, f"Cycle {cycle}: active not asserted"
        assert int(dut.data.value) == test_data, f"Cycle {cycle}: Data mismatch"
        await _send_serial_control_word(dut, 0xFAB0)
        for _ in range(16):
            await RisingEdge(dut.clk)
        assert dut.active.value == 0, f"Cycle {cycle}: inactive not cleared"


@pytest.mark.skip(reason="Cocotb test - run by simulation, not pytest")
@cocotb.test
async def test_bitbang_reset_behavior(dut: BitbangProtocol) -> None:
    """Test bitbang reset behavior."""
    # Start clock
    clock = Clock(dut.clk, 10, units="ns")
    cocotb.start_soon(clock.start())

    # Initialize
    dut.s_clk.value = 0
    dut.s_data.value = 0
    dut.resetn.value = 1
    await RisingEdge(dut.clk)

    # Activate and send data
    test_data = 0x12345678
    await _send_serial_data_word(dut, test_data)
    await _send_serial_control_word(dut, 0xFAB1)
    for _ in range(16):
        await RisingEdge(dut.clk)
    assert dut.active.value == 1, "Should be active"

    # Apply reset
    dut.resetn.value = 0
    await RisingEdge(dut.clk)
    await RisingEdge(dut.clk)

    # Check reset state
    assert dut.strobe.value == 0, "strobe should be 0 after reset"
    assert dut.active.value == 0, "active should be 0 after reset"
    assert dut.data.value == 0, "data should be 0 after reset"

    # Release reset and verify functionality
    dut.resetn.value = 1
    await RisingEdge(dut.clk)

    # Should be able to activate again
    await _send_serial_data_word(dut, test_data)
    await _send_serial_control_word(dut, 0xFAB1)
    for _ in range(16):
        await RisingEdge(dut.clk)
    assert dut.active.value == 1, "Should be active after reset recovery"


async def _send_serial_control_word(dut: BitbangProtocol, control_word: int) -> None:
    """Send a 16-bit control word via serial interface."""
    # Control sampled on rising edges (s_clk_sample[3]==1 & s_clk_sample[2]==0)
    debug = os.getenv("DEBUG_BITBANG") == "1"
    # Ensure starting low
    dut.s_clk.value = 0
    await RisingEdge(dut.clk)
    for bit_pos in range(15, -1, -1):  # MSB first
        bit_value = (control_word >> bit_pos) & 1
        dut.s_data.value = bit_value
        # Low phase (one cycle)
        dut.s_clk.value = 0
        await RisingEdge(dut.clk)
        # Rising edge -> control shift
        dut.s_clk.value = 1
        await RisingEdge(dut.clk)
        if debug:
            cocotb.log.info(f"CTRL bit {bit_pos}={bit_value}")
    # Leave clock low
    dut.s_clk.value = 0


async def _send_serial_data_word(dut: BitbangProtocol, data_word: int) -> None:
    """Send a 32-bit data word via serial interface."""
    # Data sampled on falling edges (s_clk_sample[3]==0 & s_clk_sample[2]==1)
    debug = os.getenv("DEBUG_BITBANG") == "1"
    # Start high so first transition to low is a falling edge after first cycle
    dut.s_clk.value = 1
    await RisingEdge(dut.clk)
    for bit_pos in range(31, -1, -1):  # MSB first
        bit_value = (data_word >> bit_pos) & 1
        dut.s_data.value = bit_value
        # High phase (one cycle)
        dut.s_clk.value = 1
        await RisingEdge(dut.clk)
        # Falling edge -> data shift
        dut.s_clk.value = 0
        await RisingEdge(dut.clk)
        if debug and (bit_pos % 8 == 0):
            cocotb.log.info(f"DATA bit {bit_pos}={bit_value}")
    # Leave clock low
    dut.s_clk.value = 0

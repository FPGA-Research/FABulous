"""RTL behavior validation for bitbang module using cocotb."""

from decimal import Decimal
from pathlib import Path
from typing import Any, Protocol

import cocotb
import pytest
from cocotb.clock import Clock
from cocotb.triggers import RisingEdge, Timer

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

    # Test case 1: Send ON_PATTERN (0xFAB1) to activate
    await _send_serial_control_word(dut, 0xFAB1)
    await Timer(Decimal(100), units="ps")  # Allow time for processing

    # Should be active now
    assert dut.active.value == 1, "active should be 1 after ON_PATTERN"

    # Test case 2: Send 32-bit data word
    test_data = 0x12345678
    await _send_serial_data_word(dut, test_data)
    await Timer(Decimal(100), units="ps")

    # Check that strobe was generated and data is correct
    assert dut.data.value == test_data, (
        f"Expected data = 0x{test_data:08x}, got 0x{dut.data.value:08x}"
    )

    # Test case 3: Send OFF_PATTERN (0xFAB0) to deactivate
    await _send_serial_control_word(dut, 0xFAB0)
    await Timer(Decimal(100), units="ps")

    # Should be inactive now
    assert dut.active.value == 0, "active should be 0 after OFF_PATTERN"


@pytest.mark.skip(reason="Cocotb test - run by simulation, not pytest")
@cocotb.test
async def test_bitbang_multiple_data(dut: BitbangProtocol) -> None:
    """Test bitbang with multiple data words."""
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

    # Activate with ON_PATTERN
    await _send_serial_control_word(dut, 0xFAB1)
    await Timer(Decimal(100), units="ps")
    assert dut.active.value == 1, "Should be active after ON_PATTERN"

    # Send multiple data words
    test_words = [0x00000000, 0xFFFFFFFF, 0xAAAAAAAA, 0x55555555, 0x12345678]

    for i, word in enumerate(test_words):
        await _send_serial_data_word(dut, word)
        await Timer(Decimal(100), units="ps")

        assert dut.data.value == word, (
            f"Word {i}: Expected data = 0x{word:08x}, got 0x{dut.data.value:08x}"
        )


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
        await _send_serial_control_word(dut, 0xFAB1)
        await Timer(Decimal(100), units="ps")
        assert dut.active.value == 1, (
            f"Cycle {cycle}: Should be active after ON_PATTERN"
        )

        # Send a test data word
        test_data = 0xDEADBEEF + cycle
        await _send_serial_data_word(dut, test_data)
        await Timer(Decimal(100), units="ps")
        assert dut.data.value == test_data, f"Cycle {cycle}: Data mismatch"

        # Deactivate
        await _send_serial_control_word(dut, 0xFAB0)
        await Timer(Decimal(100), units="ps")
        assert dut.active.value == 0, (
            f"Cycle {cycle}: Should be inactive after OFF_PATTERN"
        )


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
    await _send_serial_control_word(dut, 0xFAB1)
    await Timer(Decimal(100), units="ps")
    assert dut.active.value == 1, "Should be active"

    test_data = 0x12345678
    await _send_serial_data_word(dut, test_data)
    await Timer(Decimal(100), units="ps")

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
    await _send_serial_control_word(dut, 0xFAB1)
    await Timer(Decimal(100), units="ps")
    assert dut.active.value == 1, "Should be active after reset recovery"


async def _send_serial_control_word(dut: BitbangProtocol, control_word: int) -> None:
    """Send a 16-bit control word via serial interface."""
    # Send 16 bits, MSB first
    for bit_pos in range(15, -1, -1):
        bit_value = (control_word >> bit_pos) & 1

        # Set data
        dut.s_data.value = bit_value
        await Timer(Decimal(50), units="ps")

        # Clock rising edge (falling edge is used for control)
        dut.s_clk.value = 1
        await Timer(Decimal(50), units="ps")

        # Clock falling edge - control data is captured here
        dut.s_clk.value = 0
        await Timer(Decimal(50), units="ps")


async def _send_serial_data_word(dut: BitbangProtocol, data_word: int) -> None:
    """Send a 32-bit data word via serial interface."""
    # Send 32 bits, MSB first
    for bit_pos in range(31, -1, -1):
        bit_value = (data_word >> bit_pos) & 1

        # Set data
        dut.s_data.value = bit_value
        await Timer(Decimal(50), units="ps")

        # Clock rising edge - data is captured here
        dut.s_clk.value = 1
        await Timer(Decimal(50), units="ps")

        # Clock falling edge
        dut.s_clk.value = 0
        await Timer(Decimal(50), units="ps")

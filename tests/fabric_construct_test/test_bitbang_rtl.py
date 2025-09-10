"""RTL behavior validation for bitbang module using cocotb."""

import os
from pathlib import Path
from typing import Protocol

import cocotb
from cocotb.clock import Clock
from cocotb.handle import ModifiableObject
from cocotb.triggers import RisingEdge

from tests.conftest import VERILOG_SOURCE_PATH, VHDL_SOURCE_PATH, CocotbRunner


class BitbangProtocol(Protocol):
    """Protocol defining the bitbang module interface."""

    # Inputs
    s_clk: ModifiableObject  # Serial clock (handle)
    s_data: ModifiableObject  # Serial data (handle)
    clk: ModifiableObject  # System clock (handle)
    resetn: ModifiableObject  # Reset (active low) (handle)

    # Outputs
    strobe: ModifiableObject  # Data strobe output (handle)
    data: ModifiableObject  # [31:0] Parallel data output (handle)
    active: ModifiableObject  # Module active flag (handle)
    # Note: some simulators expose internal shift reg 'serial_data'; tests use getattr to access when present.


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


@cocotb.test
async def bitbang_basic_test(dut: BitbangProtocol) -> None:
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

    # Protocol: According to RTL, serial_data is sampled on s_clk rising edge, control on falling; send control last to latch
    test_data = 0x12345678
    await _send_serial_data_word(dut, test_data)
    # Now send ON pattern to latch
    await _send_serial_control_word(dut, 0xFAB1)
    for _ in range(64):
        await RisingEdge(dut.clk)
    assert int(dut.active) == 1, "active should be 1 after ON_PATTERN"
    # Allow a few more cycles for pipeline
    for _ in range(16):
        await RisingEdge(dut.clk)
    # Allow a few cycles for data to settle after latching
    for _ in range(8):
        await RisingEdge(dut.clk)
    # Ensure data changed from reset
    assert int(dut.data) != 0, "Data should be non-zero after ON pattern"
    # Deactivate
    await _send_serial_control_word(dut, 0xFAB0)
    for _ in range(16):
        await RisingEdge(dut.clk)
    assert dut.active.value == 0, "active should be 0 after OFF_PATTERN"
    await RisingEdge(dut.clk)

    test_words = [0x00000000, 0xFFFFFFFF, 0xAAAAAAAA, 0x55555555, 0x12345678]
    last_data = int(dut.data)
    for i, word in enumerate(test_words):
        # Load new data first
        await _send_serial_data_word(dut, word)
        # Trigger latch
        await _send_serial_control_word(dut, 0xFAB1)
        # Wait some cycles
        for _ in range(64):
            await RisingEdge(dut.clk)
        # Data should update from previous value
        assert int(dut.data) != last_data, f"Word {i}: data did not update"
        last_data = int(dut.data)
    # Finally deactivate
    await _send_serial_control_word(dut, 0xFAB0)
    for _ in range(16):
        await RisingEdge(dut.clk)
    assert dut.active.value == 0


@cocotb.test
async def bitbang_activation_deactivation_test(dut: BitbangProtocol) -> None:
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
        for _ in range(64):
            await RisingEdge(dut.clk)
        assert int(dut.active) == 1, f"Cycle {cycle}: active not asserted"
        # Allow settle
        for _ in range(8):
            await RisingEdge(dut.clk)
        # Data should be non-zero when active
        assert int(dut.data) != 0, f"Cycle {cycle}: Data should be non-zero"
        await _send_serial_control_word(dut, 0xFAB0)
        for _ in range(32):
            await RisingEdge(dut.clk)
        assert int(dut.active) == 0, f"Cycle {cycle}: inactive not cleared"


@cocotb.test
async def bitbang_reset_behavior_test(dut: BitbangProtocol) -> None:
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
    # Data sampled on rising edges (s_clk_sample[3]==0 & s_clk_sample[2]==1)
    debug = os.getenv("DEBUG_BITBANG") == "1"
    # Ensure starting low
    dut.s_clk.value = 0
    await RisingEdge(dut.clk)
    for bit_pos in range(31, -1, -1):  # MSB first
        bit_value = (data_word >> bit_pos) & 1
        dut.s_data.value = bit_value
        # Low phase (one cycle)
        dut.s_clk.value = 0
        await RisingEdge(dut.clk)
        # Rising edge -> data shift into serial_data
        dut.s_clk.value = 1
        await RisingEdge(dut.clk)
        if debug and (bit_pos % 8 == 0):
            cocotb.log.info(f"DATA bit {bit_pos}={bit_value}")
    # Leave clock low
    dut.s_clk.value = 0

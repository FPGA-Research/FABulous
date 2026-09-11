""""RTL behavior validation for ConfigFSM module using cocotb."""

from decimal import Decimal
from pathlib import Path
from typing import Protocol

import cocotb
from cocotb.clock import Clock
from cocotb.handle import LogicObject
from cocotb.triggers import RisingEdge, Timer

from tests.conftest import VERILOG_SOURCE_PATH, VHDL_SOURCE_PATH, CocotbRunner


async def _send_config_word(dut: "ConfigFSMProtocol", word: int) -> None:
    """Helper to send a configuration word with proper timing."""
    dut.write_data.value = word
    dut.write_strobe.value = 1
    await RisingEdge(dut.CLK)
    dut.write_strobe.value = 0
    await Timer(Decimal(100), units="ps")  # Allow propagation


class ConfigFSMProtocol(Protocol):
    """Protocol defining the ConfigFSM module interface."""

    # Inputs
    CLK: LogicObject  # System clock
    reset_n: LogicObject  # Reset (active low)
    write_data: LogicObject  # [31:0] Configuration write data
    write_strobe: LogicObject  # Configuration write strobe
    fsm_reset: LogicObject  # FSM reset signal

    # Outputs
    frame_address_register: LogicObject  # [FrameBitsPerRow-1:0] Frame address register
    long_frame_strobe: LogicObject  # Long frame strobe
    row_select: LogicObject  # [row_selectWidth-1:0] Row select


def test_ConfigFSM_verilog_rtl(cocotb_runner: CocotbRunner) -> None:
    """Test the ConfigFSM module with Verilog source."""
    cocotb_runner(
        sources=[VERILOG_SOURCE_PATH / "Fabric" / "ConfigFSM.v"],
        hdl_top_level="ConfigFSM",
        test_module_path=Path(__file__),
    )


def test_ConfigFSM_vhdl_rtl(cocotb_runner: CocotbRunner) -> None:
    """Test the ConfigFSM module with VHDL source."""
    cocotb_runner(
        sources=[VHDL_SOURCE_PATH / "Fabric" / "ConfigFSM.vhdl"],
        hdl_top_level="ConfigFSM",
        test_module_path=Path(__file__),
    )


@cocotb.test
async def cocotb_test_configfsm_basic(dut: ConfigFSMProtocol) -> None:
    """Test basic functionality of ConfigFSM."""
    # Start clock
    clock = Clock(dut.CLK, 10, units="ns")
    cocotb.start_soon(clock.start())

    # Initialize inputs (match desync test pattern exactly)
    dut.write_data.value = 0
    dut.write_strobe.value = 0
    dut.fsm_reset.value = 0
    dut.reset_n.value = 0

    # Wait for reset (same as desync test - 1 clock with reset_n=0)
    await RisingEdge(dut.CLK)
    dut.reset_n.value = 1
    await RisingEdge(dut.CLK)

    # Initialize FSM with fsm_reset rising edge
    dut.fsm_reset.value = 1
    await RisingEdge(dut.CLK)
    dut.fsm_reset.value = 0
    await RisingEdge(dut.CLK)

    # Check initial state
    assert int(dut.long_frame_strobe.value) == 0, "long_frame_strobe should be 0 initially"
    assert int(dut.frame_address_register.value) == 0, (
        "frame_address_register should be 0 initially"
    )

    # Step 1: Send sync pattern 0xFAB0FAB1 to enter synched state
    dut.write_data.value = 0xFAB0FAB1
    dut.write_strobe.value = 1
    await RisingEdge(dut.CLK)
    await Timer(Decimal(1), units="ps")  # Wait for NBA to complete
    dut.write_strobe.value = 0

    # Step 2: Send frame address (header) - this should latch into frame_address_register
    # NOTE: Bit 20 is the desync flag, so we must NOT set it (0x12345678 has bit 20 set!)
    frame_address = 0x12045678  # Address with bit 20 cleared (no desync)
    dut.write_data.value = frame_address
    dut.write_strobe.value = 1
    await RisingEdge(dut.CLK)
    await Timer(Decimal(1), units="ps")  # Wait for NBA to complete
    dut.write_strobe.value = 0
    await Timer(Decimal(1), units="ps")

    actual_value = int(dut.frame_address_register.value)
    assert actual_value == frame_address, (
        f"Expected frame_address_register = 0x{frame_address:08x}, "
        f"got 0x{actual_value:08x}"
    )

    # Test case 3: Send frame data (NumberOfRows times)
    # Default NumberOfRows is 16, so we need to send 16 data words
    number_of_rows = 16  # Default parameter value

    for i in range(number_of_rows):
        test_data = 0xA5A50000 + i
        dut.write_data.value = test_data
        dut.write_strobe.value = 1
        await RisingEdge(dut.CLK)
        dut.write_strobe.value = 0

        # Check row_select progression
        expected_row = number_of_rows - i
        assert int(dut.row_select.value) == expected_row, (
            f"Frame {i}: Expected row_select = {expected_row}, "
            f"got {int(dut.row_select.value)}"
        )

        # On the last frame, long_frame_strobe should be asserted
        if i == number_of_rows - 1:
            # long_frame_strobe should be high for 2 clock cycles after FrameStrobe
            await RisingEdge(dut.CLK)
            await Timer(Decimal(1), units="ps")  # Wait for NBA to complete
            assert int(dut.long_frame_strobe.value) == 1, (
                "long_frame_strobe should be high after last frame"
            )
            await RisingEdge(dut.CLK)
            await Timer(Decimal(1), units="ps")  # Wait for NBA to complete
            assert int(dut.long_frame_strobe.value) == 1, (
                "long_frame_strobe should stay high for 2 cycles"
            )
            await RisingEdge(dut.CLK)
            await Timer(Decimal(1), units="ps")  # Wait for NBA to complete
            assert int(dut.long_frame_strobe.value) == 0, (
                "long_frame_strobe should go low after 2 cycles"
            )


@cocotb.test
async def cocotb_test_configfsm_desync(dut: ConfigFSMProtocol) -> None:
    """Test desync functionality of ConfigFSM."""
    # Start clock
    clock = Clock(dut.CLK, 10, units="ns")
    cocotb.start_soon(clock.start())

    # Initialize and reset
    dut.write_data.value = 0
    dut.write_strobe.value = 0
    dut.fsm_reset.value = 0
    dut.reset_n.value = 0
    await RisingEdge(dut.CLK)
    dut.reset_n.value = 1
    await RisingEdge(dut.CLK)

    # Initialize FSM with fsm_reset rising edge
    dut.fsm_reset.value = 1
    await RisingEdge(dut.CLK)
    dut.fsm_reset.value = 0
    await RisingEdge(dut.CLK)

    # Enter synched state (32-bit pattern)
    dut.write_data.value = 0xFAB0FAB1
    dut.write_strobe.value = 1
    await RisingEdge(dut.CLK)
    dut.write_strobe.value = 0
    await Timer(Decimal(10), units="ps")

    # Send header with desync bit set (bit 20)
    desync_flag = 20  # Default parameter value
    header_with_desync = 0x12345678 | (1 << desync_flag)
    dut.write_data.value = header_with_desync
    dut.write_strobe.value = 1
    await RisingEdge(dut.CLK)
    dut.write_strobe.value = 0
    await Timer(Decimal(10), units="ps")

    # Should be back to unsynched state - test by trying to send data (32-bit value)
    dut.write_data.value = 0xDEADBEEF
    dut.write_strobe.value = 1
    await RisingEdge(dut.CLK)
    dut.write_strobe.value = 0
    await Timer(Decimal(10), units="ps")

    # Need sync pattern again to enter synched state
    dut.write_data.value = 0xFAB0FAB1
    dut.write_strobe.value = 1
    await RisingEdge(dut.CLK)
    dut.write_strobe.value = 0

    # Now should be able to send header normally
    normal_header = 0x11223344
    dut.write_data.value = normal_header
    dut.write_strobe.value = 1
    await RisingEdge(dut.CLK)
    dut.write_strobe.value = 0
    await Timer(Decimal(10), units="ps")

    assert int(dut.frame_address_register.value) == normal_header, (
        f"After desync recovery: Expected frame_address_register = 0x{normal_header:08x}, "
        f"got 0x{int(dut.frame_address_register.value):08x}"
    )


@cocotb.test
async def cocotb_test_configfsm_row_select_invalid(dut: ConfigFSMProtocol) -> None:
    """Test row_select behavior when write_strobe is inactive."""
    # Start clock
    clock = Clock(dut.CLK, 10, units="ns")
    cocotb.start_soon(clock.start())

    # Initialize and reset
    dut.write_data.value = 0
    dut.write_strobe.value = 0
    dut.fsm_reset.value = 0
    dut.reset_n.value = 0
    await RisingEdge(dut.CLK)
    dut.reset_n.value = 1
    await RisingEdge(dut.CLK)

    # Initialize FSM - not needed for this test but good practice
    dut.fsm_reset.value = 1
    await RisingEdge(dut.CLK)
    dut.fsm_reset.value = 0
    await RisingEdge(dut.CLK)

    # With write_strobe inactive, row_select should be all 1s (invalid)
    # row_selectWidth defaults to 5, so row_select should be 0b11111 = 31
    await Timer(Decimal(10), units="ps")
    expected_invalid_row = 0b11111  # All 1s for 5-bit width
    assert int(dut.row_select.value) == expected_invalid_row, (
        f"With write_strobe inactive: Expected row_select = {expected_invalid_row}, got {int(dut.row_select.value)}"
    )

    # Activate write_strobe and check row_select becomes valid
    dut.write_strobe.value = 1
    await Timer(Decimal(10), units="ps")
    # Should not be all 1s anymore
    assert int(dut.row_select.value) != expected_invalid_row, (
        f"With write_strobe active: row_select should not be {expected_invalid_row}, got {int(dut.row_select.value)}"
    )

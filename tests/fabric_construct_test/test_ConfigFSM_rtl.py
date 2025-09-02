"""RTL behavior validation for ConfigFSM module using cocotb."""

from decimal import Decimal
from pathlib import Path
from typing import Any, Protocol

import cocotb
import pytest
from cocotb.clock import Clock
from cocotb.triggers import RisingEdge, Timer

from tests.conftest import VERILOG_SOURCE_PATH, VHDL_SOURCE_PATH, CocotbRunner


class ConfigFSMProtocol(Protocol):
    """Protocol defining the ConfigFSM module interface."""

    # Inputs
    CLK: Any  # System clock
    resetn: Any  # Reset (active low)
    WriteData: Any  # [31:0] Configuration write data
    WriteStrobe: Any  # Configuration write strobe
    FSM_Reset: Any  # FSM reset signal

    # Outputs
    FrameAddressRegister: Any  # [FrameBitsPerRow-1:0] Frame address register
    LongFrameStrobe: Any  # Long frame strobe
    RowSelect: Any  # [RowSelectWidth-1:0] Row select


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


@pytest.mark.skip(reason="Cocotb test - run by simulation, not pytest")
@cocotb.test
async def test_configfsm_basic(dut: ConfigFSMProtocol) -> None:
    """Test basic functionality of ConfigFSM."""
    # Start clock
    clock = Clock(dut.CLK, 10, units="ns")
    cocotb.start_soon(clock.start())

    # Initialize inputs
    dut.WriteData.value = 0
    dut.WriteStrobe.value = 0
    dut.FSM_Reset.value = 0
    dut.resetn.value = 0

    # Wait for reset
    await RisingEdge(dut.CLK)
    await RisingEdge(dut.CLK)
    dut.resetn.value = 1
    await RisingEdge(dut.CLK)

    # Check initial state
    assert dut.LongFrameStrobe.value == 0, "LongFrameStrobe should be 0 initially"
    assert dut.FrameAddressRegister.value == 0, (
        "FrameAddressRegister should be 0 initially"
    )

    # Test case 1: Send sync pattern 0xFAB0FAB1 to enter synched state
    dut.WriteData.value = 0xFAB0FAB1
    dut.WriteStrobe.value = 1
    await RisingEdge(dut.CLK)
    dut.WriteStrobe.value = 0
    await Timer(Decimal(10), units="ps")

    # Test case 2: Send frame address (header)
    frame_address = 0x12345678
    dut.WriteData.value = frame_address
    dut.WriteStrobe.value = 1
    await RisingEdge(dut.CLK)
    dut.WriteStrobe.value = 0
    await Timer(Decimal(10), units="ps")

    # Check that FrameAddressRegister is set
    assert dut.FrameAddressRegister.value == frame_address, (
        f"Expected FrameAddressRegister = 0x{frame_address:08x}, got 0x{dut.FrameAddressRegister.value:08x}"
    )

    # Test case 3: Send frame data (NumberOfRows times)
    # Default NumberOfRows is 16, so we need to send 16 data words
    number_of_rows = 16  # Default parameter value

    for i in range(number_of_rows):
        test_data = 0xA5A50000 + i
        dut.WriteData.value = test_data
        dut.WriteStrobe.value = 1
        await RisingEdge(dut.CLK)
        dut.WriteStrobe.value = 0

        # Check RowSelect progression
        expected_row = number_of_rows - i
        assert dut.RowSelect.value == expected_row, (
            f"Frame {i}: Expected RowSelect = {expected_row}, got {dut.RowSelect.value}"
        )

        # On the last frame, LongFrameStrobe should be asserted
        if i == number_of_rows - 1:
            await Timer(Decimal(10), units="ps")
            # LongFrameStrobe should be high for 2 clock cycles
            await RisingEdge(dut.CLK)
            assert dut.LongFrameStrobe.value == 1, (
                "LongFrameStrobe should be high after last frame"
            )
            await RisingEdge(dut.CLK)
            assert dut.LongFrameStrobe.value == 1, (
                "LongFrameStrobe should stay high for 2 cycles"
            )
            await RisingEdge(dut.CLK)
            assert dut.LongFrameStrobe.value == 0, (
                "LongFrameStrobe should go low after 2 cycles"
            )


@pytest.mark.skip(reason="Cocotb test - run by simulation, not pytest")
@cocotb.test
async def test_configfsm_desync(dut: ConfigFSMProtocol) -> None:
    """Test desync functionality of ConfigFSM."""
    # Start clock
    clock = Clock(dut.CLK, 10, units="ns")
    cocotb.start_soon(clock.start())

    # Initialize and reset
    dut.WriteData.value = 0
    dut.WriteStrobe.value = 0
    dut.FSM_Reset.value = 0
    dut.resetn.value = 0
    await RisingEdge(dut.CLK)
    dut.resetn.value = 1
    await RisingEdge(dut.CLK)

    # Enter synched state
    dut.WriteData.value = 0xFAB0FAB1
    dut.WriteStrobe.value = 1
    await RisingEdge(dut.CLK)
    dut.WriteStrobe.value = 0
    await Timer(Decimal(10), units="ps")

    # Send header with desync bit set (bit 20)
    desync_flag = 20  # Default parameter value
    header_with_desync = 0x12345678 | (1 << desync_flag)
    dut.WriteData.value = header_with_desync
    dut.WriteStrobe.value = 1
    await RisingEdge(dut.CLK)
    dut.WriteStrobe.value = 0
    await Timer(Decimal(10), units="ps")

    # Should be back to unsynched state - test by trying to send data
    dut.WriteData.value = 0xDEADBEEF
    dut.WriteStrobe.value = 1
    await RisingEdge(dut.CLK)
    dut.WriteStrobe.value = 0
    await Timer(Decimal(10), units="ps")

    # Need sync pattern again to enter synched state
    dut.WriteData.value = 0xFAB0FAB1
    dut.WriteStrobe.value = 1
    await RisingEdge(dut.CLK)
    dut.WriteStrobe.value = 0

    # Now should be able to send header normally
    normal_header = 0x11223344
    dut.WriteData.value = normal_header
    dut.WriteStrobe.value = 1
    await RisingEdge(dut.CLK)
    dut.WriteStrobe.value = 0
    await Timer(Decimal(10), units="ps")

    assert dut.FrameAddressRegister.value == normal_header, (
        f"After desync recovery: Expected FrameAddressRegister = 0x{normal_header:08x}, "
        f"got 0x{dut.FrameAddressRegister.value:08x}"
    )


@pytest.mark.skip(reason="Cocotb test - run by simulation, not pytest")
@cocotb.test
async def test_configfsm_row_select_invalid(dut: ConfigFSMProtocol) -> None:
    """Test RowSelect behavior when WriteStrobe is inactive."""
    # Start clock
    clock = Clock(dut.CLK, 10, units="ns")
    cocotb.start_soon(clock.start())

    # Initialize and reset
    dut.WriteData.value = 0
    dut.WriteStrobe.value = 0
    dut.FSM_Reset.value = 0
    dut.resetn.value = 0
    await RisingEdge(dut.CLK)
    dut.resetn.value = 1
    await RisingEdge(dut.CLK)

    # With WriteStrobe inactive, RowSelect should be all 1s (invalid)
    # RowSelectWidth defaults to 5, so RowSelect should be 0b11111 = 31
    await Timer(Decimal(10), units="ps")
    expected_invalid_row = 0b11111  # All 1s for 5-bit width
    assert dut.RowSelect.value == expected_invalid_row, (
        f"With WriteStrobe inactive: Expected RowSelect = {expected_invalid_row}, got {dut.RowSelect.value}"
    )

    # Activate WriteStrobe and check RowSelect becomes valid
    dut.WriteStrobe.value = 1
    await Timer(Decimal(10), units="ps")
    # Should not be all 1s anymore
    assert dut.RowSelect.value != expected_invalid_row, (
        f"With WriteStrobe active: RowSelect should not be {expected_invalid_row}, got {dut.RowSelect.value}"
    )

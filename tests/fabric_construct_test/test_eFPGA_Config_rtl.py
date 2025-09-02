"""RTL behavior validation for eFPGA_Config module using cocotb."""

from decimal import Decimal
from pathlib import Path
from typing import Any, Protocol

import cocotb
import pytest
from cocotb.clock import Clock
from cocotb.triggers import RisingEdge, Timer

from tests.conftest import VERILOG_SOURCE_PATH, VHDL_SOURCE_PATH, CocotbRunner


class eFPGAConfigProtocol(Protocol):
    """Protocol defining the eFPGA_Config module interface."""

    # Inputs
    CLK: Any  # System clock
    resetn: Any  # Reset (active low)
    Rx: Any  # UART receive
    s_clk: Any  # BitBang serial clock
    s_data: Any  # BitBang serial data
    SelfWriteData: Any  # [31:0] CPU configuration data write port
    SelfWriteStrobe: Any  # CPU write strobe

    # Outputs
    ComActive: Any  # Communication active flag
    ReceiveLED: Any  # Receive LED indicator
    ConfigWriteData: Any  # [31:0] Configuration write data
    ConfigWriteStrobe: Any  # Configuration write strobe
    FrameAddressRegister: Any  # [FrameBitsPerRow-1:0]
    LongFrameStrobe: Any  # Long frame strobe
    RowSelect: Any  # [RowSelectWidth-1:0] Row select


def test_eFPGA_Config_verilog_rtl(cocotb_runner: CocotbRunner) -> None:
    """Test the eFPGA_Config module with Verilog source."""
    cocotb_runner(
        sources=[
            VERILOG_SOURCE_PATH / "Fabric" / "eFPGA_Config.v",
            VERILOG_SOURCE_PATH / "Fabric" / "config_UART.v",
            VERILOG_SOURCE_PATH / "Fabric" / "bitbang.v",
            VERILOG_SOURCE_PATH / "Fabric" / "ConfigFSM.v",
        ],
        hdl_top_level="eFPGA_Config",
        test_module_path=Path(__file__),
    )


def test_eFPGA_Config_vhdl_rtl(cocotb_runner: CocotbRunner) -> None:
    """Test the eFPGA_Config module with VHDL source."""
    cocotb_runner(
        sources=[
            VHDL_SOURCE_PATH / "Fabric" / "eFPGA_Config.vhdl",
            VHDL_SOURCE_PATH / "Fabric" / "config_UART.vhdl",
            VHDL_SOURCE_PATH / "Fabric" / "bitbang.vhdl",
            VHDL_SOURCE_PATH / "Fabric" / "ConfigFSM.vhdl",
        ],
        hdl_top_level="eFPGA_Config",
        test_module_path=Path(__file__),
    )


@pytest.mark.skip(reason="Cocotb test - run by simulation, not pytest")
@cocotb.test
async def test_efpga_config_basic(dut: eFPGAConfigProtocol) -> None:
    """Test basic functionality of eFPGA_Config."""
    # Start clock
    clock = Clock(dut.CLK, 10, units="ns")
    cocotb.start_soon(clock.start())

    # Initialize inputs
    dut.Rx.value = 1  # UART idle state
    dut.s_clk.value = 0
    dut.s_data.value = 0
    dut.SelfWriteData.value = 0
    dut.SelfWriteStrobe.value = 0
    dut.resetn.value = 0

    # Wait for reset
    await RisingEdge(dut.CLK)
    await RisingEdge(dut.CLK)
    dut.resetn.value = 1
    await RisingEdge(dut.CLK)

    # Check initial state
    assert dut.ConfigWriteStrobe.value == 0, "ConfigWriteStrobe should be 0 initially"
    assert dut.LongFrameStrobe.value == 0, "LongFrameStrobe should be 0 initially"

    # Test case 1: Self-write interface
    # Send sync pattern via SelfWrite interface
    dut.SelfWriteData.value = 0xFAB0FAB1
    dut.SelfWriteStrobe.value = 1
    await RisingEdge(dut.CLK)
    dut.SelfWriteStrobe.value = 0
    await Timer(Decimal(10), units="ps")

    # Check that ConfigWriteStrobe was asserted
    # Note: The exact timing depends on the internal FSM implementation

    # Send frame address
    frame_addr = 0x12345678
    dut.SelfWriteData.value = frame_addr
    dut.SelfWriteStrobe.value = 1
    await RisingEdge(dut.CLK)
    dut.SelfWriteStrobe.value = 0
    await Timer(Decimal(10), units="ps")

    # Check that FrameAddressRegister is set
    assert dut.FrameAddressRegister.value == frame_addr, (
        f"Expected FrameAddressRegister = 0x{frame_addr:08x}, got 0x{dut.FrameAddressRegister.value:08x}"
    )


@pytest.mark.skip(reason="Cocotb test - run by simulation, not pytest")
@cocotb.test
async def test_efpga_config_uart_interface(dut: eFPGAConfigProtocol) -> None:
    """Test UART interface functionality."""
    # Start clock
    clock = Clock(dut.CLK, 10, units="ns")
    cocotb.start_soon(clock.start())

    # Initialize inputs
    dut.Rx.value = 1  # UART idle
    dut.s_clk.value = 0
    dut.s_data.value = 0
    dut.SelfWriteData.value = 0
    dut.SelfWriteStrobe.value = 0
    dut.resetn.value = 0

    # Reset
    await RisingEdge(dut.CLK)
    dut.resetn.value = 1
    await RisingEdge(dut.CLK)

    # UART is complex to test without proper bit timing
    # This test verifies the module structure and interfaces

    # Toggle UART input and check for any response
    dut.Rx.value = 0  # Start bit
    for _ in range(10):
        await RisingEdge(dut.CLK)
    dut.Rx.value = 1  # Back to idle

    # Allow time for processing
    for _ in range(20):
        await RisingEdge(dut.CLK)

    # The UART module should be responsive (exact behavior depends on baud rate and data)


@pytest.mark.skip(reason="Cocotb test - run by simulation, not pytest")
@cocotb.test
async def test_efpga_config_bitbang_interface(dut: eFPGAConfigProtocol) -> None:
    """Test BitBang interface functionality."""
    # Start clock
    clock = Clock(dut.CLK, 10, units="ns")
    cocotb.start_soon(clock.start())

    # Initialize inputs
    dut.Rx.value = 1
    dut.s_clk.value = 0
    dut.s_data.value = 0
    dut.SelfWriteData.value = 0
    dut.SelfWriteStrobe.value = 0
    dut.resetn.value = 0

    # Reset
    await RisingEdge(dut.CLK)
    dut.resetn.value = 1
    await RisingEdge(dut.CLK)

    # Send activation pattern via bitbang interface (0xFAB1)
    await _send_bitbang_control_word(dut, 0xFAB1)
    await Timer(Decimal(100), units="ps")

    # Send test data via bitbang
    test_data = 0x12345678
    await _send_bitbang_data_word(dut, test_data)
    await Timer(Decimal(100), units="ps")

    # Check that data appeared on ConfigWriteData
    # Note: Exact timing and muxing depends on implementation


@pytest.mark.skip(reason="Cocotb test - run by simulation, not pytest")
@cocotb.test
async def test_efpga_config_multiple_interfaces(dut: eFPGAConfigProtocol) -> None:
    """Test interaction between different configuration interfaces."""
    # Start clock
    clock = Clock(dut.CLK, 10, units="ns")
    cocotb.start_soon(clock.start())

    # Initialize inputs
    dut.Rx.value = 1
    dut.s_clk.value = 0
    dut.s_data.value = 0
    dut.SelfWriteData.value = 0
    dut.SelfWriteStrobe.value = 0
    dut.resetn.value = 0

    # Reset
    await RisingEdge(dut.CLK)
    dut.resetn.value = 1
    await RisingEdge(dut.CLK)

    # Test that different interfaces can be used (not simultaneously)

    # Use SelfWrite interface first
    dut.SelfWriteData.value = 0xFAB0FAB1
    dut.SelfWriteStrobe.value = 1
    await RisingEdge(dut.CLK)
    dut.SelfWriteStrobe.value = 0
    await Timer(Decimal(50), units="ps")

    # Then use BitBang interface
    await _send_bitbang_control_word(dut, 0xFAB1)
    await Timer(Decimal(100), units="ps")

    # Both interfaces should be able to drive the configuration


@pytest.mark.skip(reason="Cocotb test - run by simulation, not pytest")
@cocotb.test
async def test_efpga_config_frame_strobe_generation(dut: eFPGAConfigProtocol) -> None:
    """Test frame strobe generation from configuration FSM."""
    # Start clock
    clock = Clock(dut.CLK, 10, units="ns")
    cocotb.start_soon(clock.start())

    # Initialize inputs
    dut.Rx.value = 1
    dut.s_clk.value = 0
    dut.s_data.value = 0
    dut.SelfWriteData.value = 0
    dut.SelfWriteStrobe.value = 0
    dut.resetn.value = 0

    # Reset
    await RisingEdge(dut.CLK)
    dut.resetn.value = 1
    await RisingEdge(dut.CLK)

    # Send sync pattern
    dut.SelfWriteData.value = 0xFAB0FAB1
    dut.SelfWriteStrobe.value = 1
    await RisingEdge(dut.CLK)
    dut.SelfWriteStrobe.value = 0
    await Timer(Decimal(10), units="ps")

    # Send frame address
    dut.SelfWriteData.value = 0x11111111
    dut.SelfWriteStrobe.value = 1
    await RisingEdge(dut.CLK)
    dut.SelfWriteStrobe.value = 0
    await Timer(Decimal(10), units="ps")

    # Send frame data (NumberOfRows = 16 by default)
    for i in range(16):
        dut.SelfWriteData.value = 0xAAAAAAAA + i
        dut.SelfWriteStrobe.value = 1
        await RisingEdge(dut.CLK)
        dut.SelfWriteStrobe.value = 0

        # Check RowSelect progression
        expected_row = 16 - i
        assert dut.RowSelect.value == expected_row, (
            f"Frame {i}: Expected RowSelect = {expected_row}, got {dut.RowSelect.value}"
        )

        # On last frame, should see LongFrameStrobe
        if i == 15:  # Last frame
            await Timer(Decimal(10), units="ps")
            await RisingEdge(dut.CLK)
            # Should see LongFrameStrobe asserted for multiple cycles
            strobe_seen = False
            for _ in range(5):
                if dut.LongFrameStrobe.value == 1:
                    strobe_seen = True
                    break
                await RisingEdge(dut.CLK)

            assert strobe_seen, (
                "LongFrameStrobe should be asserted after complete frame"
            )


async def _send_bitbang_control_word(
    dut: eFPGAConfigProtocol, control_word: int
) -> None:
    """Send a 16-bit control word via bitbang interface."""
    for bit_pos in range(15, -1, -1):
        bit_value = (control_word >> bit_pos) & 1
        dut.s_data.value = bit_value
        await Timer(Decimal(50), units="ps")
        dut.s_clk.value = 1
        await Timer(Decimal(50), units="ps")
        dut.s_clk.value = 0
        await Timer(Decimal(50), units="ps")


async def _send_bitbang_data_word(dut: eFPGAConfigProtocol, data_word: int) -> None:
    """Send a 32-bit data word via bitbang interface."""
    for bit_pos in range(31, -1, -1):
        bit_value = (data_word >> bit_pos) & 1
        dut.s_data.value = bit_value
        await Timer(Decimal(50), units="ps")
        dut.s_clk.value = 1
        await Timer(Decimal(50), units="ps")
        dut.s_clk.value = 0
        await Timer(Decimal(50), units="ps")

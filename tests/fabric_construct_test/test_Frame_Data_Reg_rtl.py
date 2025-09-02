"""RTL behavior validation for Frame_Data_Reg module using cocotb."""

from decimal import Decimal
from pathlib import Path
from typing import Any, Protocol

import cocotb
import pytest
from cocotb.clock import Clock
from cocotb.triggers import RisingEdge, Timer

from tests.conftest import VERILOG_SOURCE_PATH, VHDL_SOURCE_PATH, CocotbRunner


class FrameDataRegProtocol(Protocol):
    """Protocol defining the Frame_Data_Reg module interface."""

    # Inputs
    FrameData_I: Any  # [FrameBitsPerRow-1:0]
    RowSelect: Any  # [RowSelectWidth-1:0]
    CLK: Any

    # Outputs
    FrameData_O: Any  # [FrameBitsPerRow-1:0]


def test_Frame_Data_Reg_verilog_rtl(cocotb_runner: CocotbRunner) -> None:
    """Test the Frame_Data_Reg module with Verilog source."""
    cocotb_runner(
        sources=[VERILOG_SOURCE_PATH / "Fabric" / "Frame_Data_Reg.v"],
        hdl_top_level="Frame_Data_Reg",
        test_module_path=Path(__file__),
    )


def test_Frame_Data_Reg_vhdl_rtl(cocotb_runner: CocotbRunner) -> None:
    cocotb_runner(
        sources=[VHDL_SOURCE_PATH / "Fabric" / "Frame_Data_Reg.vhdl"],
        hdl_top_level="Frame_Data_Reg",
        test_module_path=Path(__file__),
    )


@pytest.mark.skip(reason="Cocotb test - run by simulation, not pytest")
@cocotb.test
async def test_frame_data_reg_basic(dut: FrameDataRegProtocol) -> None:
    """Test basic functionality of Frame_Data_Reg."""
    # Start clock
    clock = Clock(dut.CLK, 10, units="ns")
    cocotb.start_soon(clock.start())

    # Initialize inputs
    dut.FrameData_I.value = 0
    dut.RowSelect.value = 0

    # Wait for a few clock cycles to stabilize
    await RisingEdge(dut.CLK)
    await RisingEdge(dut.CLK)

    # Test case 1: RowSelect matches the configured Row (default Row = 1)
    test_data = 0xA5A5A5A5  # Test pattern
    dut.FrameData_I.value = test_data
    dut.RowSelect.value = 1  # This should match the Row parameter (default = 1)

    await RisingEdge(dut.CLK)
    await Timer(Decimal(10), units="ps")  # Small delay to allow propagation

    # Check that FrameData_O matches FrameData_I when RowSelect == Row
    assert dut.FrameData_O.value == test_data, (
        f"Expected FrameData_O = 0x{test_data:08x}, got 0x{dut.FrameData_O.value:08x} "
        f"when RowSelect ({dut.RowSelect.value}) matches Row"
    )

    # Test case 2: RowSelect does not match the configured Row
    dut.RowSelect.value = 2  # This should NOT match the Row parameter (default = 1)
    new_test_data = 0x5A5A5A5A
    dut.FrameData_I.value = new_test_data

    await RisingEdge(dut.CLK)
    await Timer(Decimal(10), units="ps")

    # FrameData_O should remain the same (previous value) when RowSelect != Row
    assert dut.FrameData_O.value == test_data, (
        f"Expected FrameData_O to remain 0x{test_data:08x}, got 0x{dut.FrameData_O.value:08x} "
        f"when RowSelect ({dut.RowSelect.value}) does not match Row"
    )

    # Test case 3: Multiple row select changes
    for row_val in [0, 3, 4, 1, 5]:
        pattern = 0x12345678 + row_val
        dut.FrameData_I.value = pattern
        dut.RowSelect.value = row_val

        await RisingEdge(dut.CLK)
        await Timer(Decimal(10), units="ps")

        expected = pattern if row_val == 1 else dut.FrameData_O.value
        actual = dut.FrameData_O.value
        assert actual == expected, (
            f"Row {row_val}: Expected FrameData_O = 0x{expected:08x}, got 0x{actual:08x}"
        )

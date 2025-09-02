"""RTL behavior validation for Frame_Data_Reg module using cocotb."""

from decimal import Decimal
from pathlib import Path
from typing import Protocol

import cocotb
from cocotb.clock import Clock
from cocotb.handle import LogicObject
from cocotb.triggers import RisingEdge, Timer

from tests.conftest import VERILOG_SOURCE_PATH, VHDL_SOURCE_PATH, CocotbRunner


class FrameDataRegProtocol(Protocol):
    """Protocol defining the Frame_Data_Reg module interface."""

    # Inputs
    FrameData_I: LogicObject  # [FrameBitsPerRow-1:0]
    RowSelect: LogicObject  # [RowSelectWidth-1:0]
    CLK: LogicObject

    # Outputs
    FrameData_O: LogicObject  # [FrameBitsPerRow-1:0]


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


@cocotb.test
async def cocotb_test_frame_data_reg_basic(dut: FrameDataRegProtocol) -> None:
    """Test basic functionality of Frame_Data_Reg."""
    # Start clock
    clock = Clock(dut.CLK, 10, unit="ns")
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
    dut.RowSelect.value = 1

    await RisingEdge(dut.CLK)
    await Timer(Decimal(1), unit="ps")  # Wait for NBA completion

    # Check that FrameData_O matches FrameData_I when RowSelect == Row
    assert int(dut.FrameData_O.value) == test_data, (
        f"Expected FrameData_O = 0x{test_data:08x}, got 0x{int(dut.FrameData_O.value):08x} "
        f"when RowSelect ({int(dut.RowSelect.value)}) matches Row"
    )

    # Test case 2: RowSelect does not match the configured Row
    dut.RowSelect.value = 2
    new_test_data = 0x5A5A5A5A
    dut.FrameData_I.value = new_test_data

    await RisingEdge(dut.CLK)
    await Timer(Decimal(1), unit="ps")  # Wait for NBA completion

    # FrameData_O should remain the same (previous value) when RowSelect != Row
    assert int(dut.FrameData_O.value) == test_data, (
        f"Expected FrameData_O to remain 0x{test_data:08x}, got 0x{int(dut.FrameData_O.value):08x} "
        f"when RowSelect ({int(dut.RowSelect.value)}) does not match Row"
    )

    # Test case 3: Multiple row select changes
    for row_val in [0, 3, 4, 1, 5]:
        pattern = 0x12345678 + row_val
        dut.FrameData_I.value = pattern
        dut.RowSelect.value = row_val

        await RisingEdge(dut.CLK)
        await Timer(Decimal(1), unit="ps")  # Wait for NBA completion

        expected = pattern if row_val == 1 else int(dut.FrameData_O.value)
        actual = int(dut.FrameData_O.value)
        assert actual == expected, (
            f"Row {row_val}: Expected FrameData_O = 0x{expected:08x}, got 0x{actual:08x}"
        )


@cocotb.test
async def cocotb_test_frame_data_reg_row_sweep(dut: FrameDataRegProtocol) -> None:
    """Test all valid RowSelect values to verify data latching only happens when RowSelect matches Row.

    This test sweeps through all valid RowSelect values (0-15 for default 5-bit width)
    and verifies that data is only latched when RowSelect matches the configured Row parameter (default=1).
    """
    # Start clock
    clock = Clock(dut.CLK, 10, unit="ns")
    cocotb.start_soon(clock.start())

    # Initialize inputs
    dut.FrameData_I.value = 0
    dut.RowSelect.value = 0

    # Wait for stabilization
    await RisingEdge(dut.CLK)
    await RisingEdge(dut.CLK)

    # The configured Row parameter (default is 1)
    configured_row = 1

    # Sweep through all valid RowSelect values (0-15 for 5-bit width)
    for row_select in range(16):
        # Create a unique test pattern for each row
        test_pattern = (0xABCD0000 | (row_select << 8) | row_select) & 0xFFFFFFFF

        dut.RowSelect.value = row_select
        dut.FrameData_I.value = test_pattern

        # Capture the output before the clock edge
        prev_output = int(dut.FrameData_O.value)

        await RisingEdge(dut.CLK)
        await Timer(Decimal(1), unit="ps")  # Wait for NBA completion

        current_output = int(dut.FrameData_O.value)

        if row_select == configured_row:
            # Data should be latched when RowSelect matches configured Row
            assert current_output == test_pattern, (
                f"RowSelect={row_select} (matches Row={configured_row}): "
                f"Expected FrameData_O = 0x{test_pattern:08x}, got 0x{current_output:08x}"
            )
        else:
            # Data should NOT be latched when RowSelect doesn't match
            assert current_output == prev_output, (
                f"RowSelect={row_select} (doesn't match Row={configured_row}): "
                f"FrameData_O should remain 0x{prev_output:08x}, got 0x{current_output:08x}"
            )


@cocotb.test
async def cocotb_test_frame_data_reg_bit_patterns(dut: FrameDataRegProtocol) -> None:
    """Test various bit patterns for FrameData_I to ensure all bits are correctly latched.

    Tests include:
    - Walking ones (single bit high, shifts across all positions)
    - Walking zeros (single bit low, shifts across all positions)
    - All ones (0xFFFFFFFF)
    - All zeros (0x00000000)
    - Alternating patterns (0xAAAAAAAA, 0x55555555)
    """
    # Start clock
    clock = Clock(dut.CLK, 10, unit="ns")
    cocotb.start_soon(clock.start())

    # Initialize inputs
    dut.FrameData_I.value = 0
    dut.RowSelect.value = 1  # Set to configured Row to enable latching

    # Wait for stabilization
    await RisingEdge(dut.CLK)
    await RisingEdge(dut.CLK)

    # Test patterns
    test_patterns = []

    # Walking ones pattern (single bit high)
    for bit_pos in range(32):
        test_patterns.append((1 << bit_pos, f"Walking ones bit {bit_pos}"))

    # Walking zeros pattern (single bit low)
    for bit_pos in range(32):
        test_patterns.append((0xFFFFFFFF ^ (1 << bit_pos), f"Walking zeros bit {bit_pos}"))

    # Common patterns
    test_patterns.extend([
        (0x00000000, "All zeros"),
        (0xFFFFFFFF, "All ones"),
        (0xAAAAAAAA, "Alternating 1010..."),
        (0x55555555, "Alternating 0101..."),
        (0xF0F0F0F0, "Nibble alternating 1111/0000"),
        (0x0F0F0F0F, "Nibble alternating 0000/1111"),
    ])

    for pattern, description in test_patterns:
        dut.FrameData_I.value = pattern

        await RisingEdge(dut.CLK)
        await Timer(Decimal(1), unit="ps")  # Wait for NBA completion

        actual_output = int(dut.FrameData_O.value)
        assert actual_output == pattern, (
            f"{description}: Expected FrameData_O = 0x{pattern:08x}, got 0x{actual_output:08x}"
        )


@cocotb.test
async def cocotb_test_frame_data_reg_edge_cases(dut: FrameDataRegProtocol) -> None:
    """Test edge cases including rapid RowSelect switching and maximum data values.

    Tests include:
    - Rapid RowSelect switching between matching and non-matching values
    - Back-to-back data writes when RowSelect matches
    - Maximum data value (0xFFFFFFFF)
    - RowSelect at boundary values (0, max=15)
    - Multiple consecutive clocks with same RowSelect value
    """
    # Start clock
    clock = Clock(dut.CLK, 10, unit="ns")
    cocotb.start_soon(clock.start())

    # Initialize inputs
    dut.FrameData_I.value = 0
    dut.RowSelect.value = 0

    # Wait for stabilization
    await RisingEdge(dut.CLK)
    await RisingEdge(dut.CLK)

    configured_row = 1

    # Test 1: Rapid RowSelect switching
    test_data_1 = 0xDEADBEEF
    dut.FrameData_I.value = test_data_1
    dut.RowSelect.value = configured_row

    await RisingEdge(dut.CLK)
    await Timer(Decimal(1), unit="ps")

    assert int(dut.FrameData_O.value) == test_data_1, (
        f"Rapid switch test 1: Expected 0x{test_data_1:08x}, got 0x{int(dut.FrameData_O.value):08x}"
    )

    # Immediately switch to non-matching row
    dut.RowSelect.value = 0
    test_data_2 = 0x12345678
    dut.FrameData_I.value = test_data_2

    await RisingEdge(dut.CLK)
    await Timer(Decimal(1), unit="ps")

    # Should still have old data
    assert int(dut.FrameData_O.value) == test_data_1, (
        f"Rapid switch test 2: Expected to hold 0x{test_data_1:08x}, got 0x{int(dut.FrameData_O.value):08x}"
    )

    # Test 2: Back-to-back data writes when RowSelect matches
    dut.RowSelect.value = configured_row

    back_to_back_patterns = [0x11111111, 0x22222222, 0x33333333, 0x44444444]
    for pattern in back_to_back_patterns:
        dut.FrameData_I.value = pattern

        await RisingEdge(dut.CLK)
        await Timer(Decimal(1), unit="ps")

        assert int(dut.FrameData_O.value) == pattern, (
            f"Back-to-back write: Expected 0x{pattern:08x}, got 0x{int(dut.FrameData_O.value):08x}"
        )

    # Test 3: Maximum data value
    max_value = 0xFFFFFFFF
    dut.FrameData_I.value = max_value
    dut.RowSelect.value = configured_row

    await RisingEdge(dut.CLK)
    await Timer(Decimal(1), unit="ps")

    assert int(dut.FrameData_O.value) == max_value, (
        f"Maximum value test: Expected 0x{max_value:08x}, got 0x{int(dut.FrameData_O.value):08x}"
    )

    # Test 4: RowSelect at boundary values
    # Test RowSelect = 0 (minimum)
    dut.RowSelect.value = 0
    boundary_data = 0xBBBBBBBB
    dut.FrameData_I.value = boundary_data

    await RisingEdge(dut.CLK)
    await Timer(Decimal(1), unit="ps")

    # Should not latch (RowSelect != configured_row)
    assert int(dut.FrameData_O.value) == max_value, (
        f"Boundary test (RowSelect=0): Expected to hold 0x{max_value:08x}, got 0x{int(dut.FrameData_O.value):08x}"
    )

    # Test RowSelect = 15 (maximum for 5-bit width)
    dut.RowSelect.value = 15
    boundary_data_2 = 0xCCCCCCCC
    dut.FrameData_I.value = boundary_data_2

    await RisingEdge(dut.CLK)
    await Timer(Decimal(1), unit="ps")

    # Should not latch (RowSelect != configured_row)
    assert int(dut.FrameData_O.value) == max_value, (
        f"Boundary test (RowSelect=15): Expected to hold 0x{max_value:08x}, got 0x{int(dut.FrameData_O.value):08x}"
    )

    # Test 5: Multiple consecutive clocks with same RowSelect value (matching)
    consecutive_data = 0x99999999
    dut.FrameData_I.value = consecutive_data
    dut.RowSelect.value = configured_row

    await RisingEdge(dut.CLK)
    await Timer(Decimal(1), unit="ps")

    assert int(dut.FrameData_O.value) == consecutive_data, (
        f"Consecutive clock 1: Expected 0x{consecutive_data:08x}, got 0x{int(dut.FrameData_O.value):08x}"
    )

    # Keep same inputs, clock again
    await RisingEdge(dut.CLK)
    await Timer(Decimal(1), unit="ps")

    assert int(dut.FrameData_O.value) == consecutive_data, (
        f"Consecutive clock 2: Expected 0x{consecutive_data:08x}, got 0x{int(dut.FrameData_O.value):08x}"
    )

    # Clock once more
    await RisingEdge(dut.CLK)
    await Timer(Decimal(1), unit="ps")

    assert int(dut.FrameData_O.value) == consecutive_data, (
        f"Consecutive clock 3: Expected 0x{consecutive_data:08x}, got 0x{int(dut.FrameData_O.value):08x}"
    )

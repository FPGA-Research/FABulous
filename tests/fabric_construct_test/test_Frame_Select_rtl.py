"""RTL behavior validation for Frame_Select module using cocotb."""

from decimal import Decimal
from pathlib import Path
from typing import Protocol

import cocotb
from cocotb.handle import LogicObject
from cocotb.triggers import Timer

# NOTE: cocotb-coverage integration prepared but not active due to environment dependency
from tests.conftest import VERILOG_SOURCE_PATH, VHDL_SOURCE_PATH, CocotbRunner


class FrameSelectProtocol(Protocol):
    """Protocol defining the Frame_Select module interface."""

    # Inputs
    FrameStrobe_I: LogicObject  # [MaxFramesPerCol-1:0]
    FrameSelect: LogicObject  # [FrameSelectWidth-1:0]
    FrameStrobe: LogicObject

    # Outputs
    FrameStrobe_O: LogicObject  # [MaxFramesPerCol-1:0]


def test_Frame_Select_verilog_rtl(cocotb_runner: CocotbRunner) -> None:
    """Test the Frame_Select module with Verilog source."""
    cocotb_runner(
        sources=[VERILOG_SOURCE_PATH / "Fabric" / "Frame_Select.v"],
        hdl_top_level="Frame_Select",
        test_module_path=Path(__file__),
    )


def test_Frame_Select_vhdl_rtl(cocotb_runner: CocotbRunner) -> None:
    """Test the Frame_Select module with VHDL source."""
    cocotb_runner(
        sources=[VHDL_SOURCE_PATH / "Fabric" / "Frame_Select.vhdl"],
        hdl_top_level="Frame_Select",
        test_module_path=Path(__file__),
    )


@cocotb.test
async def cocotb_test_frame_select_basic(dut: FrameSelectProtocol) -> None:
    """Test basic functionality of Frame_Select."""
    # Initialize inputs
    dut.FrameStrobe_I.value = 0
    dut.FrameSelect.value = 0
    dut.FrameStrobe.value = 0
    await Timer(Decimal(10), units="ps")

    # Check initial state - output should be 0
    assert int(dut.FrameStrobe_O.value) == 0, "FrameStrobe_O should be 0 initially"

    # Test case 1: FrameSelect matches Col parameter (default Col = 18)
    # Set test pattern on FrameStrobe_I
    test_pattern = 0xA5A5A  # 20-bit pattern for MaxFramesPerCol=20
    dut.FrameStrobe_I.value = test_pattern
    dut.FrameSelect.value = 18  # Should match default Col parameter
    dut.FrameStrobe.value = 1  # Enable strobe
    await Timer(Decimal(10), units="ps")

    # When FrameSelect matches Col and FrameStrobe is high, output should match input
    assert int(dut.FrameStrobe_O.value) == test_pattern, (
        f"Expected FrameStrobe_O = 0x{test_pattern:05x}, got 0x{int(dut.FrameStrobe_O.value):05x} "
        f"when FrameSelect ({int(dut.FrameSelect.value)}) matches Col"
    )

    # Test case 2: FrameSelect does not match Col parameter
    dut.FrameSelect.value = 17  # Should NOT match default Col parameter (18)
    await Timer(Decimal(10), units="ps")

    # Output should be 0 when FrameSelect != Col
    assert int(dut.FrameStrobe_O.value) == 0, (
        f"Expected FrameStrobe_O = 0, got 0x{int(dut.FrameStrobe_O.value):05x} "
        f"when FrameSelect ({int(dut.FrameSelect.value)}) does not match Col"
    )

    # Test case 3: FrameStrobe is low (disabled)
    dut.FrameSelect.value = 18  # Matches Col parameter
    dut.FrameStrobe.value = 0  # Disable strobe
    await Timer(Decimal(10), units="ps")

    # Output should be 0 when FrameStrobe is low, even if FrameSelect matches
    assert int(dut.FrameStrobe_O.value) == 0, (
        f"Expected FrameStrobe_O = 0, got 0x{int(dut.FrameStrobe_O.value):05x} when FrameStrobe is low"
    )

    # Test case 4: Different test patterns
    test_patterns = [0x00000, 0xFFFFF, 0x55555, 0xAAAAA, 0x12345]
    dut.FrameSelect.value = 18  # Match Col parameter
    dut.FrameStrobe.value = 1  # Enable strobe

    for pattern in test_patterns:
        dut.FrameStrobe_I.value = pattern
        await Timer(Decimal(10), units="ps")

        assert int(dut.FrameStrobe_O.value) == pattern, (
            f"Pattern 0x{pattern:05x}: Expected FrameStrobe_O = 0x{pattern:05x}, got 0x{int(dut.FrameStrobe_O.value):05x}"
        )


@cocotb.test
async def cocotb_test_frame_select_col_sweep(dut: FrameSelectProtocol) -> None:
    """Test Frame_Select with different FrameSelect values."""
    # Test pattern
    test_pattern = 0x12345
    dut.FrameStrobe_I.value = test_pattern
    dut.FrameStrobe.value = 1
    await Timer(Decimal(10), units="ps")

    # Test various FrameSelect values
    # Only FrameSelect = 18 (default Col) should pass through the pattern
    for frame_select in range(
        32
    ):  # Test wider range than FrameSelectWidth=5 (32 values)
        dut.FrameSelect.value = frame_select
        await Timer(Decimal(10), units="ps")

        expected = test_pattern if frame_select == 18 else 0
        actual = int(dut.FrameStrobe_O.value)
        assert actual == expected, (
            f"FrameSelect {frame_select}: Expected FrameStrobe_O = 0x{expected:05x}, got 0x{actual:05x}"
        )


@cocotb.test
async def cocotb_test_frame_select_bit_patterns(dut: FrameSelectProtocol) -> None:
    """Test Frame_Select with various bit patterns."""
    # Set up for matching condition
    dut.FrameSelect.value = 18  # Match default Col parameter
    dut.FrameStrobe.value = 1

    # Test individual bits
    max_frames = 20  # Default MaxFramesPerCol parameter
    for bit_pos in range(max_frames):
        pattern = 1 << bit_pos
        dut.FrameStrobe_I.value = pattern
        await Timer(Decimal(10), units="ps")

        assert int(dut.FrameStrobe_O.value) == pattern, (
            f"Bit {bit_pos}: Expected FrameStrobe_O = 0x{pattern:05x}, got 0x{int(dut.FrameStrobe_O.value):05x}"
        )

    # Test walking zeros (all bits high except one)
    all_ones = (1 << max_frames) - 1  # 20 bits all high
    for bit_pos in range(max_frames):
        pattern = all_ones & ~(1 << bit_pos)  # Clear one bit
        dut.FrameStrobe_I.value = pattern
        await Timer(Decimal(10), units="ps")

        assert int(dut.FrameStrobe_O.value) == pattern, (
            f"Walking zero bit {bit_pos}: Expected FrameStrobe_O = 0x{pattern:05x}, got 0x{int(dut.FrameStrobe_O.value):05x}"
        )


@cocotb.test
async def cocotb_test_frame_select_edge_cases(dut: FrameSelectProtocol) -> None:
    """Test Frame_Select edge cases."""
    # Test case 1: All zeros
    dut.FrameStrobe_I.value = 0
    dut.FrameSelect.value = 18  # Match Col
    dut.FrameStrobe.value = 1
    await Timer(Decimal(10), units="ps")

    assert int(dut.FrameStrobe_O.value) == 0, (
        "All zeros input should produce all zeros output"
    )

    # Test case 2: All ones (within MaxFramesPerCol)
    max_frames = 20  # Default MaxFramesPerCol
    all_ones = (1 << max_frames) - 1
    dut.FrameStrobe_I.value = all_ones
    await Timer(Decimal(10), units="ps")

    assert int(dut.FrameStrobe_O.value) == all_ones, (
        f"All ones input should produce all ones output: expected 0x{all_ones:05x}, got 0x{int(dut.FrameStrobe_O.value):05x}"
    )

    # Test case 3: Rapid FrameStrobe toggling
    test_pattern = 0x15555
    dut.FrameStrobe_I.value = test_pattern
    dut.FrameSelect.value = 18  # Match Col

    # Toggle FrameStrobe and check response
    dut.FrameStrobe.value = 0
    await Timer(Decimal(5), units="ps")
    assert int(dut.FrameStrobe_O.value) == 0, (
        "Output should be 0 when FrameStrobe is low"
    )

    dut.FrameStrobe.value = 1
    await Timer(Decimal(5), units="ps")
    assert int(dut.FrameStrobe_O.value) == test_pattern, (
        "Output should follow input when FrameStrobe is high"
    )

    dut.FrameStrobe.value = 0
    await Timer(Decimal(5), units="ps")
    assert int(dut.FrameStrobe_O.value) == 0, (
        "Output should be 0 when FrameStrobe goes low again"
    )

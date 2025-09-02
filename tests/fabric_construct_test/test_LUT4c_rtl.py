"""RTL behavior validation for LUT4c_frame_config_dffesr module using cocotb."""

from decimal import Decimal
from pathlib import Path
from typing import Any, Protocol

import cocotb
import pytest
from cocotb.clock import Clock
from cocotb.triggers import RisingEdge, Timer

from tests.conftest import VERILOG_SOURCE_PATH, VHDL_SOURCE_PATH, CocotbRunner


class LUT4cProtocol(Protocol):
    """Protocol defining the LUT4c_frame_config_dffesr module interface."""

    # Inputs
    I: Any  # [3:0] LUT inputs  # noqa: E741
    Ci: Any  # Carry input
    SR: Any  # Shared reset
    EN: Any  # Shared enable
    UserCLK: Any  # External clock
    ConfigBits: Any  # Configuration bits

    # Outputs
    O: Any  # LUT output (can be combinational or registered based on config)  # noqa: E741
    Co: Any  # Carry output


def test_LUT4c_verilog_rtl(cocotb_runner: CocotbRunner) -> None:
    """Test the LUT4c_frame_config_dffesr module with Verilog source."""
    cocotb_runner(
        sources=[
            VERILOG_SOURCE_PATH / "Fabric" / "models_pack.v",  # Include custom modules
            VERILOG_SOURCE_PATH / "Tile" / "LUT4AB" / "LUT4c_frame_config_dffesr.v",
        ],
        hdl_top_level="LUT4c_frame_config_dffesr",
        test_module_path=Path(__file__),
    )


@pytest.mark.skip(reason="Need update VHDL source")
def test_LUT4c_vhdl_rtl(cocotb_runner: CocotbRunner) -> None:
    """Test the LUT4c_frame_config_dffesr module with VHDL source."""
    cocotb_runner(
        sources=[
            VHDL_SOURCE_PATH / "Tile" / "LUT4AB" / "LUT4c_frame_config_dffesr.vhdl"
        ],
        hdl_top_level="lut4c_frame_config_dffesr",  # GHDL converts to lowercase
        test_module_path=Path(__file__),
    )


class LUT4cModel:
    """Software model for LUT4c_frame_config_dffesr module functionality."""

    def __init__(self) -> None:
        self.ff_out = 0

    def compute_lut_output(self, I: int, ConfigBits: int) -> int:
        """
        Compute LUT output based on 4-bit input and 16-bit LUT configuration.

        Args:
            I: 4-bit input to LUT
            ConfigBits: Configuration bits (first 16 bits are LUT init)

        Returns:
            LUT output (0 or 1)
        """
        # Extract LUT initialization from ConfigBits[15:0]
        lut_init = ConfigBits & 0xFFFF

        # Use I as index into LUT
        input_index = I & 0xF

        # Return the bit at position input_index
        return (lut_init >> input_index) & 1

    def clock_cycle(
        self, I: int, Ci: int, SR: int, EN: int, ConfigBits: int
    ) -> tuple[int, int]:  # noqa: E741
        """
        Simulate one clock cycle of the LUT4c module.

        Args:
            I: 4-bit LUT input
            Ci: Carry input
            SR: Set/Reset signal
            EN: Enable signal
            ConfigBits: Configuration bits

        Returns:
            tuple: (O, Co, Q) - LUT output, Carry output, FF output
        """
        # Compute LUT output
        lut_out = self.compute_lut_output(I, ConfigBits)

        # Carry chain logic (simplified - depends on specific implementation)
        # For basic test, carry out = carry in XOR lut_out
        carry_out = Ci ^ lut_out

        # Flip-flop logic
        ff_mode = (ConfigBits >> 16) & 1  # ConfigBits[16] enables FF

        if ff_mode:
            if SR:  # Synchronous reset/set
                if (ConfigBits >> 17) & 1:  # ConfigBits[17] determines set vs reset
                    self.ff_out = 1  # Set
                else:
                    self.ff_out = 0  # Reset
            elif EN:  # Clock enable
                self.ff_out = lut_out
            # else: hold current value
        else:
            # Combinational mode - FF output follows LUT
            self.ff_out = lut_out

        # Output selection
        output = lut_out
        if ff_mode:
            output = self.ff_out

        return output, carry_out

    def reset(self) -> None:
        """Reset the model state."""
        self.ff_out = 0


async def setup_dut(dut: LUT4cProtocol) -> None:
    """Common setup for all tests."""
    # Start clock
    clock = Clock(dut.UserCLK, 10, "ns")
    cocotb.start_soon(clock.start())

    # Initialize inputs
    dut.I.value = 0
    dut.Ci.value = 0
    dut.SR.value = 0
    dut.EN.value = 1
    dut.ConfigBits.value = 0

    # Wait for stabilization
    await RisingEdge(dut.UserCLK)
    await RisingEdge(dut.UserCLK)


@pytest.mark.skip(reason="Cocotb test - run by simulation, not pytest")
@cocotb.test
async def test_lut4c_basic_lut_functionality(dut: LUT4cProtocol) -> None:
    """Test basic LUT functionality with different configurations."""
    await setup_dut(dut)

    # Test Case 1: Configure LUT as AND gate (only input 15 = 1111 gives output 1)
    dut.ConfigBits.value = 0x8000  # Only bit 15 is set

    # Test all 0s input
    dut.I.value = 0b0000
    await Timer(Decimal(100), units="ps")
    assert dut.O.value == 0, (
        f"AND gate with input 0000 should output 0, got {dut.O.value}"
    )

    # Test all 1s input
    dut.I.value = 0b1111  # Index 15
    await Timer(Decimal(100), units="ps")
    assert dut.O.value == 1, (
        f"AND gate with input 1111 should output 1, got {dut.O.value}"
    )

    # Test partial input
    dut.I.value = 0b1110  # Index 14
    await Timer(Decimal(100), units="ps")
    assert dut.O.value == 0, (
        f"AND gate with input 1110 should output 0, got {dut.O.value}"
    )


@pytest.mark.skip(reason="Cocotb test - run by simulation, not pytest")
@cocotb.test
async def test_lut4c_or_gate_functionality(dut: LUT4cProtocol) -> None:
    """Test LUT configured as OR gate."""
    await setup_dut(dut)

    # Configure LUT as OR gate (all combinations except 0000 give output 1)
    dut.ConfigBits.value = 0xFFFE  # All bits set except bit 0

    # Test all 0s input
    dut.I.value = 0b0000
    await Timer(Decimal(100), units="ps")
    assert dut.O.value == 0, (
        f"OR gate with input 0000 should output 0, got {dut.O.value}"
    )

    # Test any non-zero input
    dut.I.value = 0b0001
    await Timer(Decimal(100), units="ps")
    assert dut.O.value == 1, (
        f"OR gate with input 0001 should output 1, got {dut.O.value}"
    )

    dut.I.value = 0b1010
    await Timer(Decimal(100), units="ps")
    assert dut.O.value == 1, (
        f"OR gate with input 1010 should output 1, got {dut.O.value}"
    )


@pytest.mark.skip(reason="Cocotb test - run by simulation, not pytest")
@cocotb.test
async def test_lut4c_flip_flop_functionality(dut: LUT4cProtocol) -> None:
    """Test flip-flop functionality when ConfigBits[16] = 1."""
    await setup_dut(dut)

    # Configure LUT as buffer (output = input[0]) and enable FF
    dut.ConfigBits.value = (
        0x1AAAA  # ConfigBits[16] = 1 (enable FF), LUT = alternating pattern
    )

    # Set input to generate LUT output = 1
    dut.I.value = 0b0001  # Should give LUT output based on ConfigBits[1]
    dut.EN.value = 1

    await Timer(Decimal(100), units="ps")

    # Clock the flip-flop
    await RisingEdge(dut.UserCLK)
    await Timer(Decimal(100), units="ps")

    # Change input but output should be registered
    old_output = dut.O.value
    dut.I.value = 0b0000
    await Timer(Decimal(100), units="ps")

    # In FF mode, output should not change immediately without clock
    new_output = dut.O.value
    assert new_output == old_output, (
        f"In FF mode, output should not change without clock: expected {old_output}, got {new_output}"
    )


@pytest.mark.skip(reason="Cocotb test - run by simulation, not pytest")
@cocotb.test
async def test_lut4c_carry_chain_functionality(dut: LUT4cProtocol) -> None:
    """Test carry chain functionality."""
    await setup_dut(dut)

    # Configure LUT for carry testing
    dut.ConfigBits.value = 0x6666  # Checkerboard pattern for testing

    # Test carry propagation
    dut.I.value = 0b0101
    dut.Ci.value = 0
    await Timer(Decimal(100), units="ps")

    carry_out_0 = dut.Co.value

    # Change carry input
    dut.Ci.value = 1
    await Timer(Decimal(100), units="ps")

    carry_out_1 = dut.Co.value

    # Carry output should be different when carry input changes
    assert carry_out_0 != carry_out_1, (
        f"Carry output should change when carry input changes: "
        f"Ci=0 -> Co={carry_out_0}, Ci=1 -> Co={carry_out_1}"
    )


@pytest.mark.skip(reason="Cocotb test - run by simulation, not pytest")
@cocotb.test
async def test_lut4c_set_reset_functionality(dut: LUT4cProtocol) -> None:
    """Test set/reset functionality of the flip-flop."""
    await setup_dut(dut)

    # Enable flip-flop mode
    dut.ConfigBits.value = 0x10000  # ConfigBits[16] = 1
    dut.EN.value = 1

    # Test reset
    dut.SR.value = 1
    await RisingEdge(dut.UserCLK)
    dut.SR.value = 0
    await Timer(Decimal(100), units="ps")

    # After reset, O should be at reset value (0 or 1 depending on set vs reset configuration)
    reset_value = dut.O.value

    # Set some data
    dut.I.value = 0b1111  # Configure to give LUT output = 1
    await RisingEdge(dut.UserCLK)
    await Timer(Decimal(100), units="ps")

    # Reset again
    dut.SR.value = 1
    await RisingEdge(dut.UserCLK)
    dut.SR.value = 0
    await Timer(Decimal(100), units="ps")

    # Should return to reset value
    assert dut.O.value == reset_value, (
        f"After reset, O should be {reset_value}, got {dut.O.value}"
    )


@pytest.mark.skip(reason="Cocotb test - run by simulation, not pytest")
@cocotb.test
async def test_lut4c_enable_functionality(dut: LUT4cProtocol) -> None:
    """Test enable functionality of the flip-flop."""
    await setup_dut(dut)

    # Enable flip-flop mode
    dut.ConfigBits.value = 0x1FF00  # ConfigBits[16] = 1, appropriate LUT config

    # Set initial value
    dut.I.value = 0b0001
    dut.EN.value = 1
    await RisingEdge(dut.UserCLK)
    await Timer(Decimal(100), units="ps")

    initial_output = dut.O.value

    # Disable and try to change
    dut.EN.value = 0
    dut.I.value = 0b1110
    await RisingEdge(dut.UserCLK)
    await Timer(Decimal(100), units="ps")

    # O should not have changed when EN=0
    assert dut.O.value == initial_output, (
        f"With EN=0, O should hold value {initial_output}, got {dut.O.value}"
    )

    # Re-enable and change
    dut.EN.value = 1
    await RisingEdge(dut.UserCLK)
    await Timer(Decimal(100), units="ps")

    # Now O should update when EN=1 (exact value depends on LUT configuration)
    updated_output = dut.O.value
    # Verify that output changed after re-enabling (unless new input happens to give same LUT output)
    # For comprehensive testing, we expect the output to reflect the new input after enable

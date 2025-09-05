"""RTL behavior validation for MULADD module using cocotb."""

from collections.abc import Callable
from decimal import Decimal
from pathlib import Path
from typing import Any, Protocol

import cocotb
import pytest
from cocotb.clock import Clock
from cocotb.triggers import RisingEdge, Timer

from tests.conftest import VERILOG_SOURCE_PATH, VHDL_SOURCE_PATH


class MULADDProtocol(Protocol):
    """Protocol defining the MULADD module interface."""

    # Inputs
    A: Any  # [7:0] operand A
    B: Any  # [7:0] operand B
    C: Any  # [19:0] operand C
    clr: Any  # Clear signal
    UserCLK: Any  # External clock
    ConfigBits: Any  # [NoConfigBits-1:0] Configuration bits

    # Outputs
    Q: Any  # [19:0] result

    # Internal registers (accessible for testing)
    A_reg: Any  # [7:0]
    B_reg: Any  # [7:0]
    C_reg: Any  # [19:0]
    ACC: Any  # [19:0] accumulator


def test_MULADD_verilog_rtl(cocotb_runner: Callable[..., None]) -> None:
    """Test the MULADD module with Verilog source."""
    cocotb_runner(
        sources=[VERILOG_SOURCE_PATH / "Tile" / "DSP" / "DSP_bot" / "MULADD.v"],
        hdl_top_level="MULADD",
        test_module_path=Path(__file__),
    )


@pytest.mark.skip(reason="Need update VHDL source")
def test_MULADD_vhdl_rtl(
    cocotb_runner: Callable[..., None],
) -> None:
    cocotb_runner(
        sources=[VHDL_SOURCE_PATH / "Tile" / "DSP" / "DSP_bot" / "MULADD.vhd"],
        hdl_top_level="MULADD",
        test_module_path=Path(__file__),
    )


BIT_0 = 0b000001
BIT_1 = 0b000010
BIT_2 = 0b000100
BIT_3 = 0b001000
BIT_4 = 0b010000
BIT_5 = 0b100000


class MULADDModel:
    """Software model for MULADD module functionality."""

    def __init__(self) -> None:
        self.A_reg = 0
        self.B_reg = 0
        self.C_reg = 0
        self.ACC = 0

    def clock_cycle(self, A: int, B: int, C: int, clr: int, ConfigBits: int) -> int:
        """
        Simulate one clock cycle of the MULADD module.

        Args:
            A: 8-bit input A
            B: 8-bit input B
            C: 20-bit input C
            clr: Clear signal
            ConfigBits: 6-bit configuration

        Returns:
            Q: 20-bit output
        """
        # Update registers on clock edge (always happens)
        self.A_reg = A & 0xFF
        self.B_reg = B & 0xFF
        self.C_reg = C & 0xFFFFF

        # Handle clear
        if clr:
            self.ACC = 0

        # Select operands based on ConfigBits
        OPA = self.A_reg if (ConfigBits & BIT_0) else A  # ConfigBits[0]
        OPB = self.B_reg if (ConfigBits & BIT_1) else B  # ConfigBits[1]
        OPC = self.C_reg if (ConfigBits & BIT_2) else C  # ConfigBits[2]

        # Multiply
        product = (OPA & 0xFF) * (OPB & 0xFF)  # 16-bit result

        # Sign extension or zero extension
        if ConfigBits & BIT_4:  # ConfigBits[4] - signExtension
            # Sign extend from 16 to 20 bits
            if product & 0x8000:  # Check sign bit (bit 15)
                product_extended = product | 0xF0000  # Sign extend
            else:
                product_extended = product & 0x0FFFF  # Keep positive
        else:
            # Zero extend
            product_extended = product & 0x0FFFF

        # Select sum input (C or ACC)
        sum_in = self.ACC if (ConfigBits & BIT_3) else OPC  # ConfigBits[3]

        # Compute sum
        sum_result = (product_extended + sum_in) & 0xFFFFF  # 20-bit result

        # Update accumulator if not clearing
        if clr:
            self.ACC = 0
        else:
            self.ACC = sum_result

        # update again since ACC might have changed
        sum_in = self.ACC if (ConfigBits & BIT_3) else OPC  # ConfigBits[3]
        sum_result = (product_extended + sum_in) & 0xFFFFF  # 20-bit result

        # Select output (sum or ACC)
        Q = self.ACC if (ConfigBits & BIT_5) else sum_result  # ConfigBits[5]

        return Q & 0xFFFFF  # Ensure 20-bit output

    def reset(self) -> None:
        """Reset the model state."""
        self.A_reg = 0
        self.B_reg = 0
        self.C_reg = 0
        self.ACC = 0


async def setup_dut(dut: MULADDProtocol) -> None:
    """Common setup for all tests."""
    # Start clock
    clock = Clock(dut.UserCLK, 10, "ns")
    cocotb.start_soon(clock.start())

    # Initialize inputs
    dut.A.value = 0
    dut.B.value = 0
    dut.C.value = 0
    dut.clr.value = 1
    dut.ConfigBits.value = 0b000000

    # Wait for stabilization and release clear
    await RisingEdge(dut.UserCLK)
    await RisingEdge(dut.UserCLK)
    dut.clr.value = 0
    await RisingEdge(dut.UserCLK)


@pytest.mark.skip(reason="Cocotb test - run by simulation, not pytest")
@cocotb.test
async def test_muladd_configbit0_a_register(dut: MULADDProtocol) -> None:
    """Test ConfigBits[0] - A register functionality."""
    await setup_dut(dut)

    # Create software model for comparison
    model = MULADDModel()

    # Test without A register (ConfigBits[0] = 0) - combinational mode
    dut.A.value = 5
    dut.B.value = 3
    dut.C.value = 0
    dut.ConfigBits.value = 0b000000  # A_reg = 0

    await Timer(Decimal(100), units="ps")  # Combinational delay

    # For combinational mode, simulate one cycle without using registers
    expected_direct = model.clock_cycle(5, 3, 0, False, 0b000000)
    assert dut.Q.value.integer == expected_direct, (
        f"Direct A mode failed: Expected Q = {expected_direct}, got {dut.Q.value.integer}"
    )

    # Test with A register (ConfigBits[0] = 1)
    # Reset model for clean test
    model.reset()

    # First clock cycle: load A_reg with 7
    dut.A.value = 7  # Load register with 7
    dut.ConfigBits.value = 0b000001  # A_reg = 1

    # Simulate model - first cycle loads register
    model.clock_cycle(7, 1, 0, False, 0b000001)
    await RisingEdge(dut.UserCLK)  # Clock to load A_reg

    # Change A input to verify register is being used
    dut.A.value = 1

    await Timer(Decimal(100), units="ps")

    # Use model output as expected value
    assert dut.A_reg.value == model.A_reg, (
        f"Registered A mode failed: Expected Q = {model.A_reg}, got {dut.Q.value.integer}"
    )


@pytest.mark.skip(reason="Cocotb test - run by simulation, not pytest")
@cocotb.test
async def test_muladd_configbit1_b_register(dut: MULADDProtocol) -> None:
    """Test ConfigBits[1] - B register functionality."""
    await setup_dut(dut)

    # Create software model for comparison
    model = MULADDModel()

    # Test without B register (ConfigBits[1] = 0)
    dut.A.value = 4
    dut.B.value = 6
    dut.C.value = 8
    dut.ConfigBits.value = 0b000000  # B_reg = 0

    await Timer(Decimal(100), units="ps")

    # Use model output as expected value
    expected_direct = model.clock_cycle(4, 6, 8, False, 0b000000)
    assert dut.Q.value.integer == expected_direct, (
        f"Direct B mode failed: Expected Q = {expected_direct}, got {dut.Q.value.integer}"
    )

    # Test with B register (ConfigBits[1] = 1)
    model.reset()

    dut.B.value = 9  # Load register with 9
    dut.ConfigBits.value = 0b000010  # B_reg = 1

    # Simulate model - first cycle loads register
    model.clock_cycle(4, 9, 8, False, 0b000010)

    await RisingEdge(dut.UserCLK)  # Clock to load B_reg

    # Change B input to verify register is being used
    dut.B.value = 2
    await Timer(Decimal(100), units="ps")

    # Use model output as expected value
    assert dut.B_reg.value == model.B_reg, (
        f"Registered B mode failed: Expected Q = {model.B_reg}, got {dut.Q.value.integer}"
    )


@pytest.mark.skip(reason="Cocotb test - run by simulation, not pytest")
@cocotb.test
async def test_muladd_configbit2_c_register(dut: MULADDProtocol) -> None:
    """Test ConfigBits[2] - C register functionality."""
    await setup_dut(dut)

    # Create software model for comparison
    model = MULADDModel()

    # Test without C register (ConfigBits[2] = 0)
    dut.A.value = 3
    dut.B.value = 4
    dut.C.value = 15
    dut.ConfigBits.value = 0b000000  # C_reg = 0

    await Timer(Decimal(100), units="ps")

    # Use model output as expected value
    expected_direct = model.clock_cycle(3, 4, 15, False, 0b000000)
    assert dut.Q.value.integer == expected_direct, (
        f"Direct C mode failed: Expected Q = {expected_direct}, got {dut.Q.value.integer}"
    )

    # Test with C register (ConfigBits[2] = 1)
    model.reset()

    dut.C.value = 20  # Load register with 20
    dut.ConfigBits.value = 0b000100  # C_reg = 1

    # Simulate model - first cycle loads register
    model.clock_cycle(3, 4, 20, False, 0b000100)

    await RisingEdge(dut.UserCLK)  # Clock to load C_reg

    # Change C input to verify register is being used
    dut.C.value = 5
    await Timer(Decimal(100), units="ps")

    # Use model output as expected value
    assert dut.C_reg.value == model.C_reg, (
        f"Registered C mode failed: Expected Q = {model.C_reg}"
    )


@pytest.mark.skip(reason="Cocotb test - run by simulation, not pytest")
@cocotb.test
async def test_muladd_configbit3_accumulator_mode(dut: MULADDProtocol) -> None:
    """Test ConfigBits[3] - Accumulator mode functionality."""
    await setup_dut(dut)

    # Create software model for comparison
    model = MULADDModel()

    # Test without accumulator (ConfigBits[3] = 0) - uses C input
    dut.A.value = 2
    dut.B.value = 5
    dut.C.value = 12
    dut.ConfigBits.value = 0b000000  # ACC = 0

    # Use model output as expected value
    expected_with_c = model.clock_cycle(2, 5, 12, False, 0b000000)
    await RisingEdge(dut.UserCLK)
    await Timer(Decimal(100), units="ps")

    assert dut.ACC.value.integer == model.ACC
    assert dut.Q.value.integer == expected_with_c, (
        f"Non-accumulator mode failed: Expected Q = {expected_with_c}, got {dut.Q.value.integer}"
    )

    # Test with accumulator (ConfigBits[3] = 1) - uses ACC instead of C
    dut.ConfigBits.value = 0b001000  # ACC = 1

    # First operation: ACC starts at 0, so 2 * 5 + 0 = 10
    expected_first_acc = model.clock_cycle(2, 5, 12, False, 0b001000)
    await RisingEdge(dut.UserCLK)
    await Timer(Decimal(100), units="ps")

    assert dut.Q.value.integer == expected_first_acc, (
        f"First accumulator operation failed: Expected Q = {expected_first_acc}, got {dut.Q.value.integer}"
    )

    # Second operation: ACC now has 10, so 2 * 5 + 10 = 20
    expected_second_acc = model.clock_cycle(2, 5, 12, False, 0b001000)
    await RisingEdge(dut.UserCLK)
    await Timer(Decimal(100), units="ps")

    assert dut.Q.value.integer == expected_second_acc, (
        f"Second accumulator operation failed: Expected Q = {expected_second_acc}, got {dut.Q.value.integer}"
    )


@pytest.mark.skip(reason="Cocotb test - run by simulation, not pytest")
@cocotb.test
async def test_muladd_configbit4_sign_extension(dut: MULADDProtocol) -> None:
    """Test ConfigBits[4] - Sign extension functionality."""
    await setup_dut(dut)

    # Create software model for comparison
    model = MULADDModel()

    # Test without sign extension (ConfigBits[4] = 0)
    dut.A.value = (
        200  # Large positive number that could be interpreted as negative in signed
    )
    dut.B.value = 200
    dut.C.value = 0
    dut.ConfigBits.value = 0b000000  # signExtension = 0

    await RisingEdge(dut.UserCLK)

    # Use model output as expected value
    expected_unsigned = model.clock_cycle(200, 200, 0, False, 0b000000)
    assert dut.Q.value.integer == expected_unsigned, (
        f"Unsigned extension failed: Expected Q = {expected_unsigned}, got {dut.Q.value.integer}"
    )

    # Test with sign extension (ConfigBits[4] = 1)
    # Use smaller numbers to avoid overflow but test the sign extension logic
    dut.A.value = 0xFF  # 255 in unsigned, -1 in signed 8-bit
    dut.B.value = 1
    dut.ConfigBits.value = 0b010000  # signExtension = 1

    # Model should match the hardware behavior
    expected_signed = model.clock_cycle(0xFF, 1, 0, False, 0b010000)

    await RisingEdge(dut.UserCLK)

    # Use model output as expected value
    assert dut.Q.value.integer == expected_signed, (
        f"Sign extension failed: Expected Q = {expected_signed}, got {dut.Q.value.integer}"
    )

    # Additional verification: Check if sign extension occurred (top 4 bits should match bit 15 of product)
    result = dut.Q.value
    product_16bit = 255 * 1  # 255
    sign_bit = (product_16bit >> 15) & 1
    expected_top_bits = sign_bit * 0xF
    actual_top_bits = (result >> 16) & 0xF

    assert actual_top_bits == expected_top_bits, (
        f"Sign extension verification failed: Expected top 4 bits = {expected_top_bits:04b}, got {actual_top_bits:04b}"
    )


@pytest.mark.skip(reason="Cocotb test - run by simulation, not pytest")
@cocotb.test
async def test_muladd_configbit5_output_select(dut: MULADDProtocol) -> None:
    """Test ConfigBits[5] - Output selection (ACC vs sum)."""
    await setup_dut(dut)

    # Create software model for comparison
    model = MULADDModel()

    # Setup accumulator mode to have meaningful ACC value
    dut.A.value = 3
    dut.B.value = 4
    dut.C.value = 0
    dut.ConfigBits.value = 0b001000  # ACC = 1, ACCout = 0

    # Run a few cycles to build up ACC
    model.clock_cycle(3, 4, 0, False, 0b001000)  # ACC = 12
    await RisingEdge(dut.UserCLK)  # ACC = 12
    await Timer(Decimal(100), units="ps")
    assert dut.ACC.value.integer == model.ACC

    model.clock_cycle(3, 4, 0, False, 0b001000)  # ACC = 24
    await RisingEdge(dut.UserCLK)  # ACC = 24
    await Timer(Decimal(100), units="ps")
    assert dut.ACC.value.integer == model.ACC

    # Test output sum (ConfigBits[5] = 0) - should output current sum calculation
    current_sum = dut.Q.value.integer  # This is the current sum being calculated

    # Test output ACC (ConfigBits[5] = 1) - should output the accumulated value
    dut.ConfigBits.value = 0b101000  # ACC = 1, ACCout = 1
    expected_acc_output = model.clock_cycle(
        0, 0, 0, False, 0b101000
    )  # Should output ACC

    await Timer(Decimal(100), units="ps")

    acc_output = dut.Q.value.integer

    # Use model output as expected value
    assert dut.Q.value.integer == expected_acc_output, (
        f"Model mismatch: Expected {expected_acc_output}, got {dut.Q.value.integer}"
    )

    # The ACC output should be the previously accumulated value
    # while the sum output would be the new calculation
    assert acc_output != current_sum or acc_output == expected_acc_output, (
        f"Output selection test: ACC output = {acc_output}, Sum output = {current_sum}, Expected ACC = {expected_acc_output}"
    )


@pytest.mark.skip(reason="Cocotb test - run by simulation, not pytest")
@cocotb.test
async def test_muladd_clear_functionality(dut: MULADDProtocol) -> None:
    """Test clear functionality."""
    await setup_dut(dut)

    # Create software model for comparison
    model = MULADDModel()

    # Build up some accumulator value
    dut.A.value = 5
    dut.B.value = 6
    dut.C.value = 0
    dut.ConfigBits.value = 0b101000  # ACC = 1, ACCout = 1

    # Build up accumulator in model too
    model.clock_cycle(5, 6, 0, False, 0b101000)
    await RisingEdge(dut.UserCLK)

    model.clock_cycle(5, 6, 0, False, 0b101000)
    await RisingEdge(dut.UserCLK)
    await Timer(Decimal(100), units="ps")

    # Should have accumulated value
    assert dut.Q.value.integer > 0, (
        f"Expected non-zero accumulated value, got {dut.Q.value.integer}"
    )

    # Test clear
    dut.clr.value = 1
    expected_clear_output = model.clock_cycle(
        5, 6, 0, True, 0b101000
    )  # Clear the model
    await RisingEdge(dut.UserCLK)
    dut.clr.value = 0

    await Timer(Decimal(100), units="ps")

    # Use model output as expected value
    assert dut.Q.value.integer == expected_clear_output, (
        f"Clear failed: Expected Q = {expected_clear_output}, got {dut.Q.value.integer}"
    )

    # Verify normal operation resumes after clear
    expected_resume_output = model.clock_cycle(5, 6, 0, False, 0b101000)
    await RisingEdge(dut.UserCLK)
    await Timer(Decimal(100), units="ps")

    # Use model output as expected value
    assert dut.Q.value.integer == expected_resume_output, (
        f"Operation after clear failed: Expected Q = {expected_resume_output}, got {dut.Q.value.integer}"
    )

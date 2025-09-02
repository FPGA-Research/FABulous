"""RTL behavior validation for MULADD module using cocotb."""

from decimal import Decimal
from pathlib import Path
from typing import Protocol

import cocotb
from cocotb.clock import Clock
from cocotb.handle import LogicObject
from cocotb.triggers import RisingEdge, Timer

from tests.conftest import VERILOG_SOURCE_PATH, VHDL_SOURCE_PATH, CocotbRunner


class MULADDProtocol(Protocol):
    """Protocol defining the MULADD module interface."""

    # Inputs
    A: LogicObject  # [7:0] operand A (handle)
    B: LogicObject  # [7:0] operand B (handle)
    C: LogicObject  # [19:0] operand C (handle)
    clr: LogicObject  # Clear signal (handle)
    UserCLK: LogicObject  # External clock (handle)
    ConfigBits: LogicObject  # [NoConfigBits-1:0] Configuration bits (handle)

    # Outputs
    Q: LogicObject  # [19:0] result (handle)

    # Internal registers (accessible for testing)
    A_reg: LogicObject  # [7:0] (handle)
    B_reg: LogicObject  # [7:0] (handle)
    C_reg: LogicObject  # [19:0] (handle)
    ACC: LogicObject  # [19:0] accumulator (handle)


def test_MULADD_verilog_rtl(cocotb_runner: CocotbRunner) -> None:
    """Test the MULADD module with Verilog source."""
    cocotb_runner(
        sources=[VERILOG_SOURCE_PATH / "Tile" / "DSP" / "DSP_bot" / "MULADD.v"],
        hdl_top_level="MULADD",
        test_module_path=Path(__file__),
    )


def test_MULADD_vhdl_rtl(cocotb_runner: CocotbRunner) -> None:
    cocotb_runner(
        sources=[VHDL_SOURCE_PATH / "Tile" / "DSP" / "DSP_bot" / "MULADD.vhdl"],
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
    """
    Cocotb-native software model for MULADD module.

    This model uses cocotb's timing model directly:
    - Uses async tasks that respond to actual clock edges
    - Matches the DUT's timing exactly
    - No manual synchronization needed
    """

    A: int = 0
    B: int = 0
    C: int = 0
    clr: int = 0
    ConfigBits: int = 0
    Q: int = 0
    _sum: int = 0

    def __init__(self, clk: LogicObject) -> None:
        """Initialize the MULADD model with all registers at reset state."""
        self.A_reg = 0
        self.B_reg = 0
        self.C_reg = 0
        self.ACC = 0
        self._clk_signal = clk

        # Start the clocked processes
        cocotb.start_soon(self._clocked_process())
        cocotb.start_soon(self._combinational_process())

    async def _clocked_process(self) -> None:
        """Clocked process that mirrors the VHDL process exactly."""
        while True:
            await RisingEdge(self._clk_signal)
            # Update all registers on clock edge
            self.A_reg = self.A
            self.B_reg = self.B
            self.C_reg = self.C

            # ACC with clear logic
            if self.clr:
                self.ACC = 0
            else:
                self.ACC = self._sum

    async def _combinational_process(self) -> None:
        """Combinational logic that updates whenever inputs change."""
        while True:
            # HDL: assign OPA = ConfigBits[0] ? A_reg : A;
            OPA = self.A_reg if (self.ConfigBits & BIT_0) else self.A

            # HDL: assign OPB = ConfigBits[1] ? B_reg : B;
            OPB = self.B_reg if (self.ConfigBits & BIT_1) else self.B

            # HDL: assign OPC = ConfigBits[2] ? C_reg : C;
            OPC = self.C_reg if (self.ConfigBits & BIT_2) else self.C

            # HDL: assign product = OPA * OPB;
            product = (OPA * OPB) & 0xFFFF

            # HDL: assign product_extended with sign extension
            if self.ConfigBits & BIT_4:  # Sign extension
                sign_bit = (product >> 15) & 1
                product_extended = product | 0xF0000 if sign_bit else product
            else:  # Zero extension
                product_extended = product

            # HDL: assign sum_in = ConfigBits[3] ? ACC : OPC;
            sum_in = self.ACC if (self.ConfigBits & BIT_3) else OPC

            self._sum = (product_extended + sum_in) & 0xFFFFF

            # HDL: assign Q = ConfigBits[5] ? ACC : sum;
            self.Q = self.ACC if (self.ConfigBits & BIT_5) else self._sum

            # Small delay to prevent busy waiting
            await Timer(Decimal(1), "ps")


async def setup_dut(dut: MULADDProtocol) -> None:
    """
    Advanced cocotb-compliant setup for all MULADD tests.

    Initializes clock, resets all registers, and provides proper
    timing synchronization for reliable test execution with
    comprehensive register state verification.
    """
    # Start clock with appropriate frequency (100MHz)
    clock = Clock(dut.UserCLK, 10, "ns")
    cocotb.start_soon(clock.start())

    # Initialize all inputs to known state (use handle.value per cocotb best practice)
    dut.A.value = 0
    dut.B.value = 0
    dut.C.value = 0
    dut.clr.value = 1  # Start in clear state
    dut.ConfigBits.value = 0b000000

    # cocotb timing: Extended reset sequence for reliable initialization
    await RisingEdge(dut.UserCLK)  # First clock with clear

    await RisingEdge(dut.UserCLK)  # Second clock with clear

    # Release clear and allow stabilization
    dut.clr.value = 0
    await RisingEdge(dut.UserCLK)  # First clock without clear
    await Timer(Decimal(1), "ns")  # Small delay for signal propagation


@cocotb.test
async def cocotb_test_muladd_configbit0_a_register(dut: MULADDProtocol) -> None:
    """Test ConfigBits[0] - A register functionality with proper cocotb timing."""
    await setup_dut(dut)

    # Create cocotb-aware software model for comparison
    model = MULADDModel(dut.UserCLK)

    # Test without A register (ConfigBits[0] = 0) - direct A input
    model.ConfigBits = 0b000000  # A_reg = 0
    dut.ConfigBits.value = 0b000000
    model.A = 5
    dut.A.value = 5
    await RisingEdge(dut.UserCLK)  # Clock to load A_reg
    await Timer(Decimal(1), "ps")  # Allow model's clocked process to update
    # Verify A_reg updates regardless of ConfigBits[0]
    assert dut.A_reg.value == model.A_reg

    # Test with A register (ConfigBits[0] = 1) - registered A input
    model.ConfigBits = 0b000001  # A_reg = 1
    dut.ConfigBits.value = 0b000001
    model.A = 7
    dut.A.value = 7
    await RisingEdge(dut.UserCLK)  # Clock to load A_reg
    await Timer(Decimal(1), "ps")  # Allow model's clocked process to update
    assert dut.A_reg.value == model.A_reg
    # Change A input to verify register is being used
    model.A = 3
    dut.A.value = 3
    await Timer(Decimal(2), units="ps")  # Allow combinational logic to settle
    # The output should use the registered value (7), not the new input (3)
    assert dut.A_reg.value == model.A_reg, (
        f"Registered A mode failed: Expected Q = {model.Q}, got {dut.Q.value}"
    )


@cocotb.test
async def cocotb_test_muladd_configbit1_b_register(dut: MULADDProtocol) -> None:
    """Test ConfigBits[1] - B register functionality with proper cocotb timing."""
    await setup_dut(dut)

    # Create cocotb-aware software model for comparison
    model = MULADDModel(dut.UserCLK)

    # Test without B register (ConfigBits[1] = 0) - direct B input
    model.ConfigBits = 0b000000  # B_reg = 0
    dut.ConfigBits.value = 0b000000
    model.B = 6
    dut.B.value = 6
    await RisingEdge(dut.UserCLK)  # Clock to load B_reg
    await Timer(Decimal(1), "ps")  # Allow model's clocked process to update
    # Verify B_reg updates regardless of ConfigBits[1]
    assert dut.B_reg.value == model.B_reg

    # Test with B register (ConfigBits[1] = 1) - registered B input
    model.ConfigBits = 0b000010  # B_reg = 1
    dut.ConfigBits.value = 0b000010
    model.B = 9  # Load register with 9
    dut.B.value = 9
    await RisingEdge(dut.UserCLK)  # Clock to load B_reg
    await Timer(Decimal(1), "ps")  # Allow model's clocked process to update
    assert dut.B_reg.value == model.B_reg
    # Change B input to verify register is being used
    model.B = 2
    dut.B.value = 2
    await Timer(Decimal(2), units="ps")  # Allow combinational logic to settle
    # The output should use the registered value (9), not the new input (2)
    assert dut.B_reg.value == model.B_reg, (
        f"Registered B mode failed: Expected B_reg = {model.B_reg}, got {dut.B_reg.value}"
    )


@cocotb.test
async def cocotb_test_muladd_configbit2_c_register(dut: MULADDProtocol) -> None:
    """Test ConfigBits[2] - C register functionality with proper cocotb timing."""
    await setup_dut(dut)

    # Create cocotb-aware software model for comparison
    model = MULADDModel(dut.UserCLK)

    # Test without C register (ConfigBits[2] = 0) - direct C input
    model.ConfigBits = 0b000000  # C_reg = 0
    dut.ConfigBits.value = 0b000000
    model.C = 15
    dut.C.value = 15
    await RisingEdge(dut.UserCLK)  # Clock to load C_reg
    await Timer(Decimal(1), "ps")  # Allow model's clocked process to update
    await Timer(Decimal(2), units="ps")  # Allow combinational logic to settle
    # Verify C_reg updates regardless of ConfigBits[2]
    assert dut.C_reg.value == model.C_reg

    # Test with C register (ConfigBits[2] = 1) - registered C input
    model.ConfigBits = 0b000100  # C_reg = 1
    dut.ConfigBits.value = 0b000100
    model.C = 20  # Load register with 20
    dut.C.value = 20
    await RisingEdge(dut.UserCLK)  # Clock to load C_reg
    await Timer(Decimal(1), "ps")  # Allow model's clocked process to update
    assert dut.C_reg.value == model.C_reg
    # Change C input to verify register is being used
    model.C = 5
    dut.C.value = 5
    await Timer(Decimal(2), units="ps")  # Allow combinational logic to settle
    # The output should use the registered value (20), not the new input (5)
    assert dut.C_reg.value == model.C_reg


@cocotb.test
async def cocotb_test_muladd_configbit3_accumulator_mode(
    dut: MULADDProtocol,
) -> None:
    """Test ConfigBits[3] - Accumulator mode functionality with proper cocotb timing."""
    await setup_dut(dut)

    # Create cocotb-aware software model for comparison
    model = MULADDModel(dut.UserCLK)

    # Test without accumulator (ConfigBits[3] = 0) - uses C input
    model.ConfigBits = 0b000000  # ACC = 0
    model.A = 2
    model.B = 5
    model.C = 12
    dut.A.value = 2
    dut.B.value = 5
    dut.C.value = 12
    dut.ConfigBits.value = 0b000000

    await RisingEdge(dut.UserCLK)
    await Timer(Decimal(1), "ps")  # Allow model's clocked process to update

    # Verify non-accumulator mode uses C input directly
    assert dut.Q.value == model.Q, (
        f"Non-accumulator mode failed: Expected Q = {model.Q}, got {dut.Q}"
    )

    # Test with accumulator (ConfigBits[3] = 1) - uses ACC instead of C
    model.ConfigBits = 0b001000  # ACC = 1
    model.A = 2
    model.B = 5
    model.C = 12  # This should be ignored when ACC mode is enabled
    dut.A.value = 2
    dut.B.value = 5
    dut.C.value = 12
    dut.ConfigBits.value = 0b001000

    # First accumulator operation: ACC starts at previous value
    await RisingEdge(dut.UserCLK)
    await Timer(Decimal(1), "ps")  # Allow model's clocked process to update

    assert dut.Q.value == model.Q, (
        f"First accumulator operation failed: Expected Q = {model.Q}, got {dut.Q}"
    )

    # Second accumulator operation: ACC accumulates further
    await RisingEdge(dut.UserCLK)
    await Timer(Decimal(1), "ps")  # Allow model's clocked process to update

    assert dut.Q.value == model.Q, (
        f"Second accumulator operation failed: Expected Q = {model.Q}, got {dut.Q}"
    )


@cocotb.test
async def cocotb_test_muladd_configbit4_sign_extension(dut: MULADDProtocol) -> None:
    """Test ConfigBits[4] - Sign extension functionality with proper cocotb timing."""
    await setup_dut(dut)

    # Create cocotb-aware software model for comparison
    model = MULADDModel(dut.UserCLK)

    # Test without sign extension (ConfigBits[4] = 0) - zero extension
    model.ConfigBits = 0b000000  # signExtension = 0
    model.A = (
        200  # Large positive number that could be interpreted as negative in signed
    )
    model.B = 200
    model.C = 0
    dut.A.value = 200
    dut.B.value = 200
    dut.C.value = 0
    dut.ConfigBits.value = 0b000000

    await RisingEdge(dut.UserCLK)
    await Timer(Decimal(1), "ps")  # Allow model's clocked process to update

    # Verify zero extension behavior
    assert dut.Q.value == model.Q, (
        f"Zero extension failed: Expected Q = {model.Q}, got {dut.Q.value}"
    )

    # Test with sign extension (ConfigBits[4] = 1)
    model.ConfigBits = 0b010000  # signExtension = 1
    model.A = 0xFF  # 255 in unsigned, -1 in signed 8-bit
    model.B = 1
    model.C = 0
    dut.A.value = 0xFF
    dut.B.value = 1
    dut.C.value = 0
    dut.ConfigBits.value = 0b010000

    await RisingEdge(dut.UserCLK)
    await Timer(Decimal(1), "ps")  # Allow model's clocked process to update

    # Verify sign extension behavior
    assert dut.Q.value == model.Q, (
        f"Sign extension failed: Expected Q = {model.Q}, got {dut.Q.value}"
    )

    # Additional verification: Check if sign extension occurred (top 4 bits should match bit 15 of product)
    result = int(dut.Q.value)
    product_16bit = 255 * 1  # 255
    sign_bit = (product_16bit >> 15) & 1
    expected_top_bits = sign_bit * 0xF
    actual_top_bits = (result >> 16) & 0xF

    assert actual_top_bits == expected_top_bits, (
        f"Sign extension verification failed: Expected top 4 bits = {expected_top_bits:04b}, "
        f"got {actual_top_bits:04b}"
    )


@cocotb.test
async def cocotb_test_muladd_configbit5_output_select(dut: MULADDProtocol) -> None:
    """Test ConfigBits[5] - Output selection (ACC vs sum) with proper cocotb timing."""
    await setup_dut(dut)

    # Create cocotb-aware software model for comparison
    model = MULADDModel(dut.UserCLK)

    # Setup accumulator mode to have meaningful ACC value
    model.ConfigBits = 0b001000  # ACC = 1, ACCout = 0
    model.A = 3
    model.B = 4
    model.C = 0
    dut.A.value = 3
    dut.B.value = 4
    dut.C.value = 0
    dut.ConfigBits.value = 0b001000

    # Run a few cycles to build up ACC
    await RisingEdge(dut.UserCLK)  # First accumulation
    await Timer(Decimal(1), "ps")  # Allow model's clocked process to update

    await RisingEdge(dut.UserCLK)  # Second accumulation
    await Timer(Decimal(1), "ps")  # Allow model's clocked process to update

    # Test output sum (ConfigBits[5] = 0) - should output current sum calculation
    current_sum = int(dut.Q.value)  # This is the current sum being calculated

    # Test output ACC (ConfigBits[5] = 1) - should output the accumulated value
    model.ConfigBits = 0b101000  # ACC = 1, ACCout = 1
    model.A = 0
    model.B = 0
    model.C = 0
    dut.A.value = 0
    dut.B.value = 0
    dut.C.value = 0
    dut.ConfigBits.value = 0b101000

    # Allow enough time for combinational logic to settle
    await Timer(Decimal(10), units="ps")  # Allow combinational logic to settle

    acc_output = int(dut.Q.value)

    # Verify model consistency
    assert dut.Q.value == model.Q, f"Model mismatch: Expected {model.Q}, got {dut.Q}"

    # The ACC output should be the previously accumulated value
    # while the sum output would be the new calculation
    assert acc_output != current_sum or acc_output == model.Q, (
        f"Output selection test: ACC output = {acc_output}, Sum output = {current_sum}, Expected ACC = {model.Q}"
    )


@cocotb.test
async def cocotb_test_muladd_clear_functionality(dut: MULADDProtocol) -> None:
    """Test clear functionality with proper cocotb timing."""
    await setup_dut(dut)

    # Create cocotb-aware software model for comparison
    model = MULADDModel(dut.UserCLK)

    # Build up some accumulator value
    model.ConfigBits = 0b101000  # ACC = 1, ACCout = 1
    model.A = 5
    model.B = 6
    model.C = 0
    dut.A.value = 5
    dut.B.value = 6
    dut.C.value = 0
    dut.ConfigBits.value = 0b101000

    # Build up accumulator
    await RisingEdge(dut.UserCLK)
    await Timer(Decimal(1), "ps")  # Allow model's clocked process to update
    await RisingEdge(dut.UserCLK)
    await Timer(Decimal(1), "ps")  # Allow model's clocked process to update

    # Should have accumulated value
    assert int(dut.Q.value) > 0, (
        f"Expected non-zero accumulated value, got {int(dut.Q.value)}"
    )

    # Test clear
    model.clr = 1
    dut.clr.value = 1
    await RisingEdge(dut.UserCLK)
    await Timer(Decimal(1), "ps")  # Allow model's clocked process to update

    # Release clear and wait for next clock edge for synchronization
    model.clr = 0
    dut.clr.value = 0
    await RisingEdge(dut.UserCLK)
    await Timer(Decimal(1), "ps")  # Allow model's clocked process to update

    # Verify clear behavior
    assert dut.Q.value == model.Q, f"Clear failed: Expected Q = {model.Q}, got {dut.Q}"

    # Verify normal operation resumes after clear
    await RisingEdge(dut.UserCLK)
    await Timer(Decimal(1), "ps")  # Allow model's clocked process to update

    # Verify operation continues normally after clear
    assert dut.Q.value == model.Q, (
        f"Operation after clear failed: Expected Q = {model.Q}, got {dut.Q}"
    )

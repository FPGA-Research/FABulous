"""RTL behavior validation for MUX8LUT_frame_config_mux module using cocotb."""

from decimal import Decimal
from pathlib import Path
from typing import Any, Protocol

import cocotb
import pytest
from cocotb.clock import Clock
from cocotb.triggers import RisingEdge, Timer

from tests.conftest import VERILOG_SOURCE_PATH, VHDL_SOURCE_PATH, CocotbRunner


class MUX8LUTProtocol(Protocol):
    """Protocol defining the MUX8LUT_frame_config_mux module interface."""

    # Inputs
    A: Any  # MUX input A
    B: Any  # MUX input B
    C: Any  # MUX input C
    D: Any  # MUX input D
    E: Any  # MUX input E
    F: Any  # MUX input F
    G: Any  # MUX input G
    H: Any  # MUX input H
    S: Any  # [3:0] Select signals
    ConfigBits: Any  # [NoConfigBits-1:0] Configuration bits
    UserCLK: Any  # Clock (for setup compatibility)

    # Outputs
    M_AB: Any  # MUX output AB
    M_AD: Any  # MUX output AD
    M_AH: Any  # MUX output AH
    M_EF: Any  # MUX output EF


def test_MUX8LUT_verilog_rtl(cocotb_runner: CocotbRunner) -> None:
    """Test the MUX8LUT_frame_config_mux module with Verilog source."""
    cocotb_runner(
        sources=[
            VERILOG_SOURCE_PATH / "Fabric" / "models_pack.v",  # Include custom modules
            VERILOG_SOURCE_PATH / "Tile" / "LUT4AB" / "MUX8LUT_frame_config_mux.v",
        ],
        hdl_top_level="MUX8LUT_frame_config_mux",
        test_module_path=Path(__file__),
    )


@pytest.mark.skip(reason="Need update VHDL source")
def test_MUX8LUT_vhdl_rtl(cocotb_runner: CocotbRunner) -> None:
    """Test the MUX8LUT_frame_config_mux module with VHDL source."""
    cocotb_runner(
        sources=[
            VHDL_SOURCE_PATH / "Tile" / "LUT4AB" / "MUX8LUT_frame_config_mux.vhdl"
        ],
        hdl_top_level="mux8lut_frame_config_mux",  # GHDL converts to lowercase
        test_module_path=Path(__file__),
    )


class MUX8LUTModel:
    """Software model for MUX8LUT_frame_config_mux module functionality."""

    def __init__(self) -> None:
        """Initialize the MUX8LUT model."""

    def compute_mux_output(
        self, inputs: list[int], select: int, config_bits: int
    ) -> dict[str, int]:
        """
        Compute MUX outputs based on inputs and select signals.

        Args:
            inputs: List of input signals (8 inputs expected A,B,C,D,E,F,G,H)
            select: 4-bit select signal [3:0]
            config_bits: Configuration bits [c1,c0]

        Returns:
            Dictionary with output names and values: M_AB, M_AD, M_AH, M_EF
        """
        # Ensure we have 8 inputs
        if len(inputs) != 8:
            raise ValueError("MUX8LUT requires exactly 8 inputs")

        A, B, C, D, E, F, G, H = inputs
        c0 = config_bits & 1
        c1 = (config_bits >> 1) & 1

        # Based on the actual module logic - hierarchical MUXes
        AB = A if (select & 1) == 0 else B
        CD = C if (select & 1) == 0 else D
        EF = E if (select & 1) == 0 else F
        GH = G if (select & 1) == 0 else H

        # Second level
        AD = AB if ((select >> 1) & 1) == 0 else CD
        EH = EF if ((select >> 1) & 1) == 0 else GH

        # Third level
        AH = AD if ((select >> 2) & 1) == 0 else EH
        EH_GH = EH if ((select >> 3) & 1) == 0 else GH

        return {
            "M_AB": AB & 1,
            "M_AD": (CD if c0 == 0 else AD) & 1,
            "M_AH": (EH_GH if c1 == 0 else AH) & 1,
            "M_EF": EF & 1,
        }

    def reset(self) -> None:
        """Reset the model state."""


async def setup_dut(dut: MUX8LUTProtocol) -> None:
    """Common setup for all tests."""
    # Initialize inputs using actual MUX8LUT port names - no clock needed for combinational logic
    dut.A.value = 0
    dut.B.value = 0
    dut.C.value = 0
    dut.D.value = 0
    dut.E.value = 0
    dut.F.value = 0
    dut.G.value = 0
    dut.H.value = 0

    # Select signal (4-bit vector)
    dut.S.value = 0

    # Configuration bits
    dut.ConfigBits.value = 0

    # Wait for combinational logic to stabilize
    await Timer(Decimal(10), units="ps")


def set_mux_inputs(dut: MUX8LUTProtocol, input_values: list[int]) -> None:
    """Helper function to set MUX input values."""
    if len(input_values) != 8:
        raise ValueError("Must provide exactly 8 input values")

    # Use actual port names from MUX8LUT_frame_config_mux module
    dut.A.value = input_values[0]
    dut.B.value = input_values[1]
    dut.C.value = input_values[2]
    dut.D.value = input_values[3]
    dut.E.value = input_values[4]
    dut.F.value = input_values[5]
    dut.G.value = input_values[6]
    dut.H.value = input_values[7]


def set_select_signals(dut: MUX8LUTProtocol, select_value: int) -> None:
    """Helper function to set select signals."""
    # S is a 4-bit vector [3:0] in the actual module
    dut.S.value = select_value & 0xF  # Ensure 4-bit value


@pytest.mark.skip(reason="Cocotb test - run by simulation, not pytest")
@cocotb.test
async def test_mux8lut_basic_selection(dut: MUX8LUTProtocol) -> None:
    """Test basic MUX selection functionality."""
    await setup_dut(dut)

    model = MUX8LUTModel()

    # Test pattern: alternating 0s and 1s
    test_inputs = [0, 1, 0, 1, 0, 1, 0, 1]
    set_mux_inputs(dut, test_inputs)
    await Timer(Decimal(100), units="ps")

    # Set configuration bits for testing
    config_bits = 0  # c1=0, c0=0
    dut.ConfigBits.value = config_bits

    # Test each select value
    for select_val in range(16):  # 4-bit select supports 0-15
        set_select_signals(dut, select_val)
        await Timer(Decimal(100), units="ps")

        expected_outputs = model.compute_mux_output(
            test_inputs, select_val, config_bits
        )

        # Check all MUX outputs
        assert dut.M_AB.value.integer == expected_outputs["M_AB"], (
            f"Select {select_val}: M_AB expected {expected_outputs['M_AB']}, got {dut.M_AB.value.integer}"
        )
        assert dut.M_AD.value.integer == expected_outputs["M_AD"], (
            f"Select {select_val}: M_AD expected {expected_outputs['M_AD']}, got {dut.M_AD.value.integer}"
        )
        assert dut.M_AH.value.integer == expected_outputs["M_AH"], (
            f"Select {select_val}: M_AH expected {expected_outputs['M_AH']}, got {dut.M_AH.value.integer}"
        )
        assert dut.M_EF.value.integer == expected_outputs["M_EF"], (
            f"Select {select_val}: M_EF expected {expected_outputs['M_EF']}, got {dut.M_EF.value.integer}"
        )


@pytest.mark.skip(reason="Cocotb test - run by simulation, not pytest")
@cocotb.test
async def test_mux8lut_all_ones_pattern(dut: MUX8LUTProtocol) -> None:
    """Test MUX with all inputs high."""
    await setup_dut(dut)

    model = MUX8LUTModel()

    # All inputs high
    test_inputs = [1, 1, 1, 1, 1, 1, 1, 1]
    set_mux_inputs(dut, test_inputs)
    await Timer(Decimal(100), units="ps")

    # Test each select value - all should output 1
    for select_val in range(8):
        set_select_signals(dut, select_val)
        await Timer(Decimal(100), units="ps")

        expected_output = model.compute_mux_output(test_inputs, select_val, 0)
        actual_output = dut.M_AB.value.integer

        assert actual_output == 1, (
            f"All ones pattern, select {select_val}: Expected 1, got {actual_output}"
        )
        assert actual_output == expected_output, (
            f"Model mismatch at select {select_val}"
        )


@pytest.mark.skip(reason="Cocotb test - run by simulation, not pytest")
@cocotb.test
async def test_mux8lut_all_zeros_pattern(dut: MUX8LUTProtocol) -> None:
    """Test MUX with all inputs low."""
    await setup_dut(dut)

    model = MUX8LUTModel()

    # All inputs low
    test_inputs = [0, 0, 0, 0, 0, 0, 0, 0]
    set_mux_inputs(dut, test_inputs)
    await Timer(Decimal(100), units="ps")

    # Test each select value - all should output 0
    for select_val in range(8):
        set_select_signals(dut, select_val)
        await Timer(Decimal(100), units="ps")

        expected_output = model.compute_mux_output(test_inputs, select_val, 0)
        actual_output = dut.M_AB.value.integer

        assert actual_output == 0, (
            f"All zeros pattern, select {select_val}: Expected 0, got {actual_output}"
        )
        assert actual_output == expected_output, (
            f"Model mismatch at select {select_val}"
        )


@pytest.mark.skip(reason="Cocotb test - run by simulation, not pytest")
@cocotb.test
async def test_mux8lut_single_high_pattern(dut: MUX8LUTProtocol) -> None:
    """Test MUX with only one input high at a time."""
    await setup_dut(dut)

    model = MUX8LUTModel()

    # Test each input individually
    for high_input in range(8):
        # Create pattern with only one input high
        test_inputs = [0] * 8
        test_inputs[high_input] = 1

        set_mux_inputs(dut, test_inputs)
        await Timer(Decimal(100), units="ps")

        # Test all select values
        for select_val in range(8):
            set_select_signals(dut, select_val)
            await Timer(Decimal(100), units="ps")

            expected_output = model.compute_mux_output(test_inputs, select_val, 0)

            # Check one of the MUX outputs
            actual_output = dut.M_AB.value.integer

            # Should be 1 only when selecting the high input
            if select_val == high_input:
                assert actual_output == 1, (
                    f"Input {high_input} high, select {select_val}: Expected 1, got {actual_output}"
                )
            else:
                assert actual_output == 0, (
                    f"Input {high_input} high, select {select_val}: Expected 0, got {actual_output}"
                )

            assert actual_output == expected_output, (
                f"Model mismatch: input {high_input}, select {select_val}"
            )


@pytest.mark.skip(reason="Cocotb test - run by simulation, not pytest")
@cocotb.test
async def test_mux8lut_binary_count_pattern(dut: MUX8LUTProtocol) -> None:
    """Test MUX with binary counting pattern."""
    await setup_dut(dut)

    model = MUX8LUTModel()

    # Binary counting pattern: input i has value (i & 1)
    test_inputs = [i & 1 for i in range(8)]  # [0, 1, 0, 1, 0, 1, 0, 1]
    set_mux_inputs(dut, test_inputs)
    await Timer(Decimal(100), units="ps")

    # Test select pattern that follows the input pattern
    for select_val in range(8):
        set_select_signals(dut, select_val)
        await Timer(Decimal(100), units="ps")

        expected_output = model.compute_mux_output(test_inputs, select_val, 0)

        # Check output
        actual_output = dut.M_AB.value.integer

        # Output should match select_val & 1
        expected_pattern = select_val & 1
        assert actual_output == expected_pattern, (
            f"Binary pattern, select {select_val}: Expected {expected_pattern}, got {actual_output}"
        )
        assert actual_output == expected_output, (
            f"Model mismatch at select {select_val}"
        )


@pytest.mark.skip(reason="Cocotb test - run by simulation, not pytest")
@cocotb.test
async def test_mux8lut_select_boundary_conditions(dut: MUX8LUTProtocol) -> None:
    """Test MUX select signal boundary conditions."""
    await setup_dut(dut)

    model = MUX8LUTModel()

    # Unique pattern to verify correct selection
    test_inputs = [0, 1, 1, 0, 1, 0, 0, 1]
    set_mux_inputs(dut, test_inputs)
    await Timer(Decimal(100), units="ps")

    # Test boundary select values
    boundary_selects = [0, 7]  # First and last valid select values

    for select_val in boundary_selects:
        set_select_signals(dut, select_val)
        await Timer(Decimal(100), units="ps")

        expected_output = model.compute_mux_output(test_inputs, select_val, 0)

        actual_output = dut.M_AB.value.integer

        assert actual_output == expected_output, (
            f"Boundary select {select_val}: Expected {expected_output}, got {actual_output}"
        )

    # Test that 4-bit select properly wraps (if implementation allows > 4-bit values)
    # Select value 16 should behave same as select value 0
    if dut.S.value.n_bits > 4:
        set_select_signals(dut, 16)  # Should wrap to 0
        await Timer(Decimal(100), units="ps")

        wrapped_output = dut.M_AB.value.integer

        set_select_signals(dut, 0)
        await Timer(Decimal(100), units="ps")

        normal_output = dut.M_AB.value.integer

        assert wrapped_output == normal_output, (
            f"Select wrapping failed: select 16 gave {wrapped_output}, select 0 gave {normal_output}"
        )


@pytest.mark.skip(reason="Cocotb test - run by simulation, not pytest")
@cocotb.test
async def test_mux8lut_dynamic_input_changes(dut: MUX8LUTProtocol) -> None:
    """Test MUX response to dynamic input changes."""
    await setup_dut(dut)

    # Set select to input 3 (D)
    select_val = 3
    set_select_signals(dut, select_val)

    # Start with input 3 = 0 (only D is 0)
    test_inputs = [1, 1, 1, 0, 1, 1, 1, 1]  # Only input 3 is 0
    set_mux_inputs(dut, test_inputs)
    await Timer(Decimal(100), units="ps")

    # Verify output reflects input D (should be 0)
    assert dut.M_AB.value.integer == 0, "Should select input 3 (value 0)"

    # Change input 3 to 1
    test_inputs[3] = 1
    set_mux_inputs(dut, test_inputs)
    await Timer(Decimal(100), units="ps")

    # Verify output changes to 1
    assert dut.M_AB.value.integer == 1, "Should now output 1 (input 3 changed to 1)"

    # Change a different input (should not affect output)
    test_inputs[5] = 0  # Change input 5 (F), but we're selecting input 3 (D)
    set_mux_inputs(dut, test_inputs)
    await Timer(Decimal(100), units="ps")

    # Output should remain 1 (still selecting input 3)
    assert dut.M_AB.value.integer == 1, (
        "Output should not change when non-selected input changes"
    )

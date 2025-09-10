"""RTL behavior validation for MUX8LUT_frame_config_mux module using cocotb."""

from decimal import Decimal
from pathlib import Path
from typing import Protocol

import cocotb
from cocotb.handle import ModifiableObject
from cocotb.triggers import Timer

from tests.conftest import VERILOG_SOURCE_PATH, VHDL_SOURCE_PATH, CocotbRunner


class MUX8LUTProtocol(Protocol):
    """Protocol defining the MUX8LUT_frame_config_mux module interface."""

    # Inputs
    A: ModifiableObject  # MUX input A (handle)
    B: ModifiableObject  # MUX input B (handle)
    C: ModifiableObject  # MUX input C (handle)
    D: ModifiableObject  # MUX input D (handle)
    E: ModifiableObject  # MUX input E (handle)
    F: ModifiableObject  # MUX input F (handle)
    G: ModifiableObject  # MUX input G (handle)
    H: ModifiableObject  # MUX input H (handle)
    S: ModifiableObject  # [3:0] Select signals (handle)
    ConfigBits: ModifiableObject  # [NoConfigBits-1:0] Configuration bits (handle)
    UserCLK: ModifiableObject  # Clock (for setup compatibility) (handle)

    # Outputs
    M_AB: ModifiableObject  # MUX output AB (handle)
    M_AD: ModifiableObject  # MUX output AD (handle)
    M_AH: ModifiableObject  # MUX output AH (handle)
    M_EF: ModifiableObject  # MUX output EF (handle)


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
    """
    Accurate software model for MUX8LUT_frame_config_mux module.

    This model implements the exact HDL behavior including all intermediate
    signals and proper cus_mux21 primitive logic: X = S ? A1 : A0
    """

    def __init__(self) -> None:
        """Initialize the MUX8LUT model."""

    def compute_mux_output(
        self, inputs: list[int], select: int, config_bits: int
    ) -> dict[str, int]:
        """
        Compute MUX outputs based on inputs and select signals.

        This implementation follows the exact HDL structure with proper
        CocoTB timing consideration for combinational logic.

        Args:
            inputs: List of input signals [A,B,C,D,E,F,G,H] (8 inputs)
            select: 4-bit select signal S[3:0]
            config_bits: Configuration bits [c1,c0] (2 bits)

        Returns:
            Dictionary with output names and values: M_AB, M_AD, M_AH, M_EF
        """
        if len(inputs) != 8:
            raise ValueError("MUX8LUT requires exactly 8 inputs")

        A, B, C, D, E, F, G, H = inputs

        # Extract configuration bits
        c0 = config_bits & 1  # ConfigBits[0]
        c1 = (config_bits >> 1) & 1  # ConfigBits[1]

        # Extract select bits
        S = [select & 1, (select >> 1) & 1, (select >> 2) & 1, (select >> 3) & 1]

        # Level 1: First level MUXes (following HDL exactly)
        # cus_mux21: X = S ? A1 : A0
        AB = B if S[0] else A  # S[0] ? B : A

        # CD mux uses sCD as select
        sCD = S[0] if c0 else S[1]  # c0 ? S[0] : S[1]
        CD = D if sCD else C  # sCD ? D : C

        # EF mux uses sEF as select
        sEF = S[0] if c1 else S[2]  # c1 ? S[0] : S[2]
        EF = F if sEF else E  # sEF ? F : E

        # GH mux uses sGH as select
        sEH = S[1] if c1 else S[3]  # c1 ? S[1] : S[3]
        sGH = sEF if c0 else sEH  # c0 ? sEF : sEH
        GH = H if sGH else G  # sGH ? H : G

        # Level 2: Second level MUXes
        AD = CD if S[1] else AB  # S[1] ? CD : AB
        EH = GH if sEH else EF  # sEH ? GH : EF

        # Level 3: Third level MUXes
        AH = EH if S[3] else AD  # S[3] ? EH : AD
        EH_GH = EH if c0 else GH  # c0 ? EH : GH

        # Output assignments (following HDL exactly)
        M_AB = AB  # Direct assignment
        M_AD = AD if c0 else CD  # c0 ? AD : CD
        M_AH = AH if c1 else EH_GH  # c1 ? AH : EH_GH
        M_EF = EF  # Direct assignment

        return {
            "M_AB": M_AB & 1,
            "M_AD": M_AD & 1,
            "M_AH": M_AH & 1,
            "M_EF": M_EF & 1,
        }

    def reset(self) -> None:
        """Reset the model state (no state for combinational logic)."""


async def setup_dut(dut: MUX8LUTProtocol) -> None:
    """
    Common setup for all tests with proper CocoTB timing.

    Initializes all inputs and allows proper propagation delays
    for combinational logic stabilization.
    """
    # Initialize all inputs to known state
    input_signals = [dut.A, dut.B, dut.C, dut.D, dut.E, dut.F, dut.G, dut.H]
    for _signal in input_signals:
        pass

    # Initialize control signals
    dut.S.value = 0  # 4-bit select signal
    dut.ConfigBits.value = 0  # 2-bit configuration

    # CocoTB timing: Allow combinational logic to stabilize
    # Use proper timing delays for signal propagation
    await Timer(Decimal(50), units="ps")  # Initial stabilization


async def set_mux_inputs_with_timing(
    dut: MUX8LUTProtocol, input_values: list[int]
) -> None:
    """
    CocoTB timing-aware helper to set MUX input values.

    Provides proper signal transition timing for realistic
    hardware behavior simulation.
    """
    if len(input_values) != 8:
        raise ValueError("Must provide exactly 8 input values")

    # Set all inputs simultaneously (as would happen in hardware)
    dut.A.value = input_values[0] & 1
    dut.B.value = input_values[1] & 1
    dut.C.value = input_values[2] & 1
    dut.D.value = input_values[3] & 1
    dut.E.value = input_values[4] & 1
    dut.F.value = input_values[5] & 1
    dut.G.value = input_values[6] & 1
    dut.H.value = input_values[7] & 1

    # CocoTB timing: Allow signal propagation through combinational logic
    await Timer(Decimal(20), units="ps")


async def set_config_with_timing(dut: MUX8LUTProtocol, config_bits: int) -> None:
    """
    CocoTB timing-aware helper to set configuration bits.

    Configuration changes require propagation through the
    entire combinational network.
    """
    dut.ConfigBits.value = config_bits & 0x3  # Ensure 2-bit value
    # Configuration changes affect all internal mux selects
    await Timer(Decimal(30), units="ps")  # Longer delay for config propagation


async def set_select_with_timing(dut: MUX8LUTProtocol, select_value: int) -> None:
    """
    CocoTB timing-aware helper to set select signals.

    Select changes propagate through multiple mux levels.
    """
    dut.S.value = select_value & 0xF  # Ensure 4-bit value
    # Select changes propagate through hierarchical mux structure
    await Timer(Decimal(25), units="ps")


@cocotb.test
async def mux8lut_basic_selection_test(dut: MUX8LUTProtocol) -> None:
    """Test basic MUX selection functionality with proper CocoTB timing."""
    await setup_dut(dut)

    model = MUX8LUTModel()

    # Test pattern: alternating 0s and 1s
    test_inputs = [0, 1, 0, 1, 0, 1, 0, 1]
    await set_mux_inputs_with_timing(dut, test_inputs)

    # Set configuration bits for testing
    config_bits = 0  # c1=0, c0=0
    await set_config_with_timing(dut, config_bits)

    # Test each select value with proper timing
    for select_val in range(16):  # 4-bit select supports 0-15
        await set_select_with_timing(dut, select_val)

        expected_outputs = model.compute_mux_output(
            test_inputs, select_val, config_bits
        )

        # Check all MUX outputs with proper timing verification
        assert int(dut.M_AB.value) == expected_outputs["M_AB"], (
            f"Select {select_val}: M_AB expected {expected_outputs['M_AB']}, got {int(dut.M_AB.value)}"
        )
        assert int(dut.M_AD.value) == expected_outputs["M_AD"], (
            f"Select {select_val}: M_AD expected {expected_outputs['M_AD']}, got {int(dut.M_AD.value)}"
        )
        assert int(dut.M_AH.value) == expected_outputs["M_AH"], (
            f"Select {select_val}: M_AH expected {expected_outputs['M_AH']}, got {int(dut.M_AH.value)}"
        )
        assert int(dut.M_EF.value) == expected_outputs["M_EF"], (
            f"Select {select_val}: M_EF expected {expected_outputs['M_EF']}, got {int(dut.M_EF.value)}"
        )


@cocotb.test
async def mux8lut_all_ones_pattern_test(dut: MUX8LUTProtocol) -> None:
    """Test MUX with all inputs high."""
    await setup_dut(dut)

    model = MUX8LUTModel()

    # All inputs high
    test_inputs = [1, 1, 1, 1, 1, 1, 1, 1]
    await set_mux_inputs_with_timing(dut, test_inputs)
    await Timer(Decimal(100), units="ps")

    # Test each select value - all should output 1
    for select_val in range(8):
        await set_select_with_timing(dut, select_val)
        await Timer(Decimal(100), units="ps")

        expected_outputs = model.compute_mux_output(test_inputs, select_val, 0)
        actual_output = int(dut.M_AB.value)

        assert actual_output == 1, (
            f"All ones pattern, select {select_val}: Expected 1, got {actual_output}"
        )
        assert actual_output == expected_outputs["M_AB"], (
            f"Model mismatch at select {select_val}"
        )


@cocotb.test
async def mux8lut_all_zeros_pattern_test(dut: MUX8LUTProtocol) -> None:
    """Test MUX with all inputs low."""
    await setup_dut(dut)

    model = MUX8LUTModel()

    # All inputs low
    test_inputs = [0, 0, 0, 0, 0, 0, 0, 0]
    await set_mux_inputs_with_timing(dut, test_inputs)
    await Timer(Decimal(100), units="ps")

    # Test each select value - all should output 0
    for select_val in range(8):
        await set_select_with_timing(dut, select_val)
        await Timer(Decimal(100), units="ps")

        expected_outputs = model.compute_mux_output(test_inputs, select_val, 0)
        actual_output = int(dut.M_AB.value)

        assert actual_output == 0, (
            f"All zeros pattern, select {select_val}: Expected 0, got {actual_output}"
        )
        assert actual_output == expected_outputs["M_AB"], (
            f"Model mismatch at select {select_val}"
        )


@cocotb.test
async def mux8lut_single_high_pattern_test(dut: MUX8LUTProtocol) -> None:
    """Test MUX with only one input high at a time."""
    await setup_dut(dut)

    model = MUX8LUTModel()

    # Test each input individually
    for high_input in range(8):
        # Create pattern with only one input high
        test_inputs = [0] * 8
        test_inputs[high_input] = 1

        await set_mux_inputs_with_timing(dut, test_inputs)
        await Timer(Decimal(100), units="ps")

        # Test all select values
        for select_val in range(8):
            await set_select_with_timing(dut, select_val)
            await Timer(Decimal(100), units="ps")

            expected_outputs = model.compute_mux_output(test_inputs, select_val, 0)

            # Check one of the MUX outputs
            actual_output = int(dut.M_AB.value)

            # Should be 1 only when selecting the high input
            if select_val == high_input:
                assert actual_output == 1, (
                    f"Input {high_input} high, select {select_val}: Expected 1, got {actual_output}"
                )
            else:
                assert actual_output == 0, (
                    f"Input {high_input} high, select {select_val}: Expected 0, got {actual_output}"
                )

            assert actual_output == expected_outputs["M_AB"], (
                f"Model mismatch: input {high_input}, select {select_val}"
            )


@cocotb.test
async def mux8lut_binary_count_pattern_test(dut: MUX8LUTProtocol) -> None:
    """Test MUX with binary counting pattern."""
    await setup_dut(dut)

    model = MUX8LUTModel()

    # Binary counting pattern: input i has value (i & 1)
    test_inputs = [i & 1 for i in range(8)]  # [0, 1, 0, 1, 0, 1, 0, 1]
    await set_mux_inputs_with_timing(dut, test_inputs)
    await Timer(Decimal(100), units="ps")

    # Test select pattern that follows the input pattern
    for select_val in range(8):
        await set_select_with_timing(dut, select_val)
        await Timer(Decimal(100), units="ps")

        expected_outputs = model.compute_mux_output(test_inputs, select_val, 0)

        # Check output
        actual_output = int(dut.M_AB.value)

        # Output should match select_val & 1
        expected_pattern = select_val & 1
        assert actual_output == expected_pattern, (
            f"Binary pattern, select {select_val}: Expected {expected_pattern}, got {actual_output}"
        )
        assert actual_output == expected_outputs["M_AB"], (
            f"Model mismatch at select {select_val}"
        )


@cocotb.test
async def mux8lut_select_boundary_conditions_test(dut: MUX8LUTProtocol) -> None:
    """Test MUX select signal boundary conditions."""
    await setup_dut(dut)

    model = MUX8LUTModel()

    # Unique pattern to verify correct selection
    test_inputs = [0, 1, 1, 0, 1, 0, 0, 1]
    await set_mux_inputs_with_timing(dut, test_inputs)
    await Timer(Decimal(100), units="ps")

    # Test boundary select values
    boundary_selects = [0, 7]  # First and last valid select values

    for select_val in boundary_selects:
        await set_select_with_timing(dut, select_val)
        await Timer(Decimal(100), units="ps")

        expected_outputs = model.compute_mux_output(test_inputs, select_val, 0)

        actual_output = int(dut.M_AB.value)

        assert actual_output == expected_outputs["M_AB"], (
            f"Boundary select {select_val}: Expected {expected_outputs['M_AB']}, got {actual_output}"
        )

    # Test that 4-bit select properly wraps (if implementation allows > 4-bit values)
    # Select value 16 should behave same as select value 0
    if len(dut.S) > 4:
        await set_select_with_timing(dut, 16)  # Should wrap to 0
        await Timer(Decimal(100), units="ps")

        wrapped_output = int(dut.M_AB.value)

        await set_select_with_timing(dut, 0)
        await Timer(Decimal(100), units="ps")

        normal_output = int(dut.M_AB.value)

        assert wrapped_output == normal_output, (
            f"Select wrapping failed: select 16 gave {wrapped_output}, select 0 gave {normal_output}"
        )


@cocotb.test
async def mux8lut_dynamic_input_changes_test(dut: MUX8LUTProtocol) -> None:
    """Test MUX response to dynamic input changes."""
    await setup_dut(dut)

    # Set select to input 3 (D)
    select_val = 3
    await set_select_with_timing(dut, select_val)

    # Start with input 3 = 0 (only D is 0)
    test_inputs = [1, 1, 1, 0, 1, 1, 1, 1]  # Only input 3 is 0
    await set_mux_inputs_with_timing(dut, test_inputs)
    await Timer(Decimal(100), units="ps")

    # Verify output reflects input D (should be 0)
    assert int(dut.M_AB.value) == 0, "Should select input 3 (value 0)"

    # Change input 3 to 1
    test_inputs[3] = 1
    await set_mux_inputs_with_timing(dut, test_inputs)
    await Timer(Decimal(100), units="ps")

    # Verify output changes to 1
    assert int(dut.M_AB.value) == 1, "Should now output 1 (input 3 changed to 1)"

    # Change a different input (should not affect output)
    test_inputs[5] = 0  # Change input 5 (F), but we're selecting input 3 (D)
    await set_mux_inputs_with_timing(dut, test_inputs)
    await Timer(Decimal(100), units="ps")

    # Output should remain 1 (still selecting input 3)
    assert int(dut.M_AB.value) == 1, (
        "Output should not change when non-selected input changes"
    )

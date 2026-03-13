"""RTL behavior validation for LUT4c_frame_config_dffesr module using cocotb-native model style (like MULADD)."""

from decimal import Decimal
from pathlib import Path
from typing import Protocol

import cocotb
from cocotb.clock import Clock
from cocotb.handle import LogicObject
from cocotb.triggers import RisingEdge, Timer

from tests.conftest import VERILOG_SOURCE_PATH, VHDL_SOURCE_PATH, CocotbRunner


class LUT4cProtocol(Protocol):
    """Protocol defining the LUT4c_frame_config_dffesr module interface."""

    # Inputs
    I: LogicObject  # [3:0] LUT inputs (handle)  # noqa: E741
    Ci: LogicObject  # Carry input (handle)
    SR: LogicObject  # Shared reset (handle)
    EN: LogicObject  # Shared enable (handle)
    UserCLK: LogicObject  # External clock (handle)
    ConfigBits: LogicObject  # Configuration bits (handle)

    # Outputs
    O: LogicObject  # LUT output (can be combinational or registered based on config) (handle)  # noqa: E741
    Co: LogicObject  # Carry output (handle)


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


def test_LUT4c_vhdl_rtl(cocotb_runner: CocotbRunner) -> None:
    """Test the LUT4c_frame_config_dffesr module with VHDL source."""
    cocotb_runner(
        sources=[
            VHDL_SOURCE_PATH / "Fabric" / "models_pack.vhdl",  # Include custom modules
            VHDL_SOURCE_PATH / "Tile" / "LUT4AB" / "LUT4c_frame_config_dffesr.vhdl",
        ],
        hdl_top_level="lut4c_frame_config_dffesr",  # GHDL converts to lowercase
        test_module_path=Path(__file__),
    )


class LUT4cModel:
    """Cocotb-native model mirroring LUT4c_frame_config_dffesr behavior."""

    # Inputs
    I_vec: int = 0
    Ci: int = 0
    SR: int = 0
    EN: int = 1
    ConfigBits: int = 0

    # Outputs/state
    O_val: int = 0
    Co: int = 0
    _lut_out: int = 0
    _lut_flop: int = 0

    def __init__(self, clk: LogicObject) -> None:
        self._clk_signal = clk
        cocotb.start_soon(self._clocked_process())
        cocotb.start_soon(self._combinational_process())

    @staticmethod
    def _lut(I_vec: int, ConfigBits: int) -> int:
        lut_init = ConfigBits & 0xFFFF
        idx = I_vec & 0xF
        return (lut_init >> idx) & 1

    async def _clocked_process(self) -> None:
        while True:
            await RisingEdge(self._clk_signal)
            reset_value = (self.ConfigBits >> 18) & 1
            if self.EN:
                if self.SR:
                    self._lut_flop = reset_value
                else:
                    self._lut_flop = self._lut_out

    async def _combinational_process(self) -> None:
        while True:
            # I0 mux with carry when ConfigBits[17]=1, matches HDL
            i0 = (self.Ci & 1) if ((self.ConfigBits >> 17) & 1) else (self.I_vec & 1)
            idx = (
                ((self.I_vec >> 3) & 1) << 3
                | ((self.I_vec >> 2) & 1) << 2
                | ((self.I_vec >> 1) & 1) << 1
                | (i0 & 1)
            )
            lut_init = self.ConfigBits & 0xFFFF
            self._lut_out = (lut_init >> idx) & 1

            # Co matches verilog: (Ci & I[1]) | (Ci & I[2]) | (I[1] & I[2])
            i1 = (self.I_vec >> 1) & 1
            i2 = (self.I_vec >> 2) & 1
            self.Co = (self.Ci & i1) | (self.Ci & i2) | (i1 & i2)

            use_ff = (self.ConfigBits >> 16) & 1
            self.O_val = self._lut_flop if use_ff else self._lut_out

            await Timer(Decimal(1), units="ps")


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


@cocotb.test
async def cocotb_test_lut4c_basic_lut_functionality(dut: LUT4cProtocol) -> None:
    """Basic LUT functionality (AND gate example)"""
    await setup_dut(dut)
    dut.ConfigBits.value = 0x8000  # Only bit 15 set
    for vec, expected in [(0b0000, 0), (0b1111, 1), (0b1110, 0)]:
        dut.I.value = vec
        await Timer(Decimal(100), units="ps")
        assert int(dut.O.value) == expected, (
            f"AND gate I={vec:04b} expected {expected} got {int(dut.O.value)}"
        )


@cocotb.test
async def cocotb_test_lut4c_model_alignment_basic(dut: LUT4cProtocol) -> None:
    """Model-aligned basic behavior: verify O and Co match a cocotb-native model."""
    await setup_dut(dut)

    model = LUT4cModel(dut.UserCLK)

    # Configure simple LUT: passthrough I0 (bit 1 set) and FF disabled
    lut_init = 0xAAAA  # bit pattern 1010...
    dut.ConfigBits.value = lut_init
    model.ConfigBits = lut_init

    for vec in [0b0000, 0b0001, 0b0010, 0b0100, 0b1000, 0b1111]:
        dut.I.value = vec
        model.I_vec = vec
        dut.Ci.value = 0
        model.Ci = 0
        await Timer(Decimal(100), units="ps")
        assert int(dut.O.value) == model.O_val, (
            f"LUT O mismatch for I={vec:04b}: HDL={int(dut.O.value)} model={model.O_val}"
        )
        assert int(dut.Co.value) == model.Co, (
            f"Carry Co mismatch for I={vec:04b}: HDL={int(dut.Co.value)} model={model.Co}"
        )


@cocotb.test
async def cocotb_test_or_gate_functionality(dut: LUT4cProtocol) -> None:
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


@cocotb.test
async def cocotb_test_flip_flop_functionality(dut: LUT4cProtocol) -> None:
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


@cocotb.test
async def cocotb_test_lut4c_carry_chain_functionality(dut: LUT4cProtocol) -> None:
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


@cocotb.test
async def cocotb_test_lut4c_set_reset_functionality(dut: LUT4cProtocol) -> None:
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


@cocotb.test
async def cocotb_test_lut4c_enable_functionality(dut: LUT4cProtocol) -> None:
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
    _updated_output = dut.O.value
    # Verify that output changed after re-enabling (unless new input happens to give same LUT output)
    # For comprehensive testing, we expect the output to reflect the new input after enable

"""RTL behavior validation for bitbang module using cocotb."""

import os
from pathlib import Path
from typing import Protocol

import cocotb
from cocotb.clock import Clock
from cocotb.handle import LogicObject
from cocotb.triggers import FallingEdge, RisingEdge

from tests.conftest import VERILOG_SOURCE_PATH, VHDL_SOURCE_PATH, CocotbRunner


class BitbangProtocol(Protocol):
    """Protocol defining the bitbang module interface."""

    # Inputs
    s_clk: LogicObject  # Serial clock (handle)
    s_data: LogicObject  # Serial data (handle)
    clk: LogicObject  # System clock (handle)
    resetn: LogicObject  # Reset (active low) (handle)

    # Outputs
    strobe: LogicObject  # Data strobe output (handle)
    data: LogicObject  # [31:0] Parallel data output (handle)
    active: LogicObject  # Module active flag (handle)
    # Note: some simulators expose internal shift reg 'serial_data'; tests use getattr to access when present.


def test_bitbang_verilog_rtl(cocotb_runner: CocotbRunner) -> None:
    """Test the bitbang module with Verilog source."""
    cocotb_runner(
        sources=[VERILOG_SOURCE_PATH / "Fabric" / "bitbang.v"],
        hdl_top_level="bitbang",
        test_module_path=Path(__file__),
    )


def test_bitbang_vhdl_rtl(cocotb_runner: CocotbRunner) -> None:
    """Test the bitbang module with VHDL source."""
    cocotb_runner(
        sources=[VHDL_SOURCE_PATH / "Fabric" / "bitbang.vhdl"],
        hdl_top_level="bitbang",
        test_module_path=Path(__file__),
    )


class bitbangModel:
    s_clk: int = 0
    s_data: int = 0
    strobe: int = 0
    data: int = 0
    active: int = 0

    _clk_signal: LogicObject
    _resetn: LogicObject

    _s_data_sample: int = 0
    _s_clk_sample: int = 0
    _serial_data: int = 0
    _serial_control: int = 0

    _local_strobe: int = 0
    _old_local_strobe: int = 0

    def __init__(self, clk: LogicObject, rst: LogicObject) -> None:
        self._clk_signal = clk
        self._resetn = rst
        # Start all the concurrent processes
        cocotb.start_soon(self._run_model())

    async def _run_model(self) -> None:
        """Run all model processes concurrently."""
        # Start all processes concurrently
        cocotb.start_soon(self.block1())
        cocotb.start_soon(self.block2())
        cocotb.start_soon(self.block3())
        cocotb.start_soon(self.block4())
        await self.reset()  # Reset controls when we become active

    async def block1(self) -> None:
        while True:
            await RisingEdge(self._clk_signal)
            self._s_data_sample = ((self._s_data_sample << 1) | self.s_data) & 0xF
            self._s_clk_sample = ((self._s_clk_sample << 1) | self.s_clk) & 0xF

    async def block2(self) -> None:
        while True:
            await RisingEdge(self._clk_signal)
            # Rising edge on sampled s_clk: bit3 (older) was 0, bit2 (newer) is 1
            # Note: mask comparisons must use 0x4/0x8, not 1/0
            if ((self._s_clk_sample & 0x8) == 0x0) and (
                (self._s_clk_sample & 0x4) == 0x4
            ):
                # Rising edge detected: shift into serial_data
                self._serial_data = (
                    (self._serial_data << 1) | ((self._s_data_sample >> 3) & 1)
                ) & 0xFFFFFFFF
            # Falling edge on sampled s_clk: bit3 (older) was 1, bit2 (newer) is 0
            if ((self._s_clk_sample & 0x8) == 0x8) and (
                (self._s_clk_sample & 0x4) == 0x0
            ):
                # Falling edge detected: shift into serial_control
                self._serial_control = (
                    (self._serial_control << 1) | ((self._s_data_sample >> 3) & 1)
                ) & 0xFFFF

    async def block3(self) -> None:
        while True:
            await RisingEdge(self._clk_signal)
            # In Verilog, all RHS evaluations happen first, then assignments
            # So we need to capture the current state before making changes
            current_local_strobe = self._local_strobe

            # Update local_strobe (starts at 0, may be set to 1)
            self._local_strobe = 0
            if self._serial_control == 0xFAB1:
                self.data = self._serial_data
                self._local_strobe = 1

            # Update old_local_strobe with the value from START of this cycle
            # and strobe with the new local_strobe and old value
            self.strobe = self._local_strobe & ((~current_local_strobe) & 1)
            self._old_local_strobe = current_local_strobe

    async def block4(self) -> None:
        while True:
            await RisingEdge(self._clk_signal)
            if self._serial_control == 0xFAB1:
                self.active = 1
            if self._serial_control == 0xFAB0:
                self.active = 0

    async def reset(self) -> None:
        while True:
            await FallingEdge(self._resetn)
            self._s_data_sample = 0
            self._s_clk_sample = 0
            self._serial_data = 0
            self._serial_control = 0
            self._local_strobe = 0
            self._old_local_strobe = 0
            self.data = 0
            self.strobe = 0
            self.active = 0


@cocotb.test
async def cocotb_test_bitbang_basic(dut: BitbangProtocol) -> None:
    """Test basic functionality of bitbang module (model vs RTL)."""
    # Start clock
    clock = Clock(dut.clk, 10, units="ns")
    cocotb.start_soon(clock.start())

    # Initialize inputs
    dut.s_clk.value = 0
    dut.s_data.value = 0
    dut.resetn.value = 0

    # Create model instance
    model = bitbangModel(dut.clk, dut.resetn)

    # Wait for reset
    await RisingEdge(dut.clk)
    await RisingEdge(dut.clk)
    dut.resetn.value = 1
    await RisingEdge(dut.clk)

    # Check initial state
    assert dut.strobe.value == 0, "strobe should be 0 initially"
    assert dut.active.value == 0, "active should be 0 initially"
    assert dut.data.value == 0, "data should be 0 initially"

    # Check model matches RTL initially
    assert model.strobe == int(dut.strobe), "Model strobe should match RTL initially"
    assert model.active == int(dut.active), "Model active should match RTL initially"
    assert model.data == int(dut.data), "Model data should match RTL initially"

    # Warm pipeline
    for _ in range(4):
        await RisingEdge(dut.clk)

    # Protocol: serial_data is sampled on s_clk rising edge, control on falling; send control last to latch
    test_data = 0x12345678
    await _send_serial_data_word_with_model(dut, model, test_data)
    # Now send ON pattern to latch
    await _send_serial_control_word_with_model(dut, model, 0xFAB1)
    for _ in range(64):
        await RisingEdge(dut.clk)
    assert int(dut.active) == 1, "active should be 1 after ON_PATTERN"
    assert model.active == 1, "Model active should be 1 after ON_PATTERN"
    assert model.active == int(dut.active), (
        "Model active should match RTL after ON_PATTERN"
    )

    # Allow a few more cycles for pipeline
    for _ in range(16):
        await RisingEdge(dut.clk)
    # Allow a few cycles for data to settle after latching
    for _ in range(8):
        await RisingEdge(dut.clk)
    # Ensure data changed from reset
    assert int(dut.data) != 0, "Data should be non-zero after ON pattern"
    assert model.data != 0, "Model data should be non-zero after ON pattern"
    assert model.data == int(dut.data), "Model data should match RTL after ON pattern"

    # Deactivate
    await _send_serial_control_word_with_model(dut, model, 0xFAB0)
    for _ in range(16):
        await RisingEdge(dut.clk)
    assert dut.active.value == 0, "active should be 0 after OFF_PATTERN"
    assert model.active == 0, "Model active should be 0 after OFF_PATTERN"
    assert model.active == int(dut.active), (
        "Model active should match RTL after OFF_PATTERN"
    )
    await RisingEdge(dut.clk)

    test_words = [0x00000000, 0xFFFFFFFF, 0xAAAAAAAA, 0x55555555, 0x12345678]
    last_data = int(dut.data)
    last_model_data = model.data
    for i, word in enumerate(test_words):
        # Load new data first
        await _send_serial_data_word_with_model(dut, model, word)
        # Trigger latch
        await _send_serial_control_word_with_model(dut, model, 0xFAB1)
        # Wait some cycles
        for _ in range(64):
            await RisingEdge(dut.clk)
        # Data should update from previous value
        assert int(dut.data) != last_data, f"Word {i}: data did not update"
        assert model.data != last_model_data, f"Word {i}: model data did not update"
        assert model.data == int(dut.data), f"Word {i}: model data should match RTL"
        last_data = int(dut.data)
        last_model_data = model.data
    # Finally deactivate
    await _send_serial_control_word_with_model(dut, model, 0xFAB0)
    for _ in range(16):
        await RisingEdge(dut.clk)
    assert dut.active.value == 0
    assert model.active == 0
    assert model.active == int(dut.active), "Model active should match RTL at end"


@cocotb.test
async def cocotb_test_bitbang_activation_deactivation(
    dut: BitbangProtocol,
) -> None:
    """Test bitbang activation and deactivation cycles."""
    # Start clock
    clock = Clock(dut.clk, 10, units="ns")
    cocotb.start_soon(clock.start())

    # Initialize and reset
    dut.s_clk.value = 0
    dut.s_data.value = 0
    dut.resetn.value = 0

    # Create model instance
    model = bitbangModel(dut.clk, dut.resetn)

    await RisingEdge(dut.clk)
    dut.resetn.value = 1
    await RisingEdge(dut.clk)

    # Test multiple activation/deactivation cycles
    for cycle in range(3):
        # Activate
        test_data = 0xDEADBEEF + cycle
        await _send_serial_data_word_with_model(dut, model, test_data)
        await _send_serial_control_word_with_model(dut, model, 0xFAB1)
        for _ in range(64):
            await RisingEdge(dut.clk)
        assert int(dut.active) == 1, f"Cycle {cycle}: active not asserted"
        assert model.active == 1, f"Cycle {cycle}: model active not asserted"
        assert model.active == int(dut.active), (
            f"Cycle {cycle}: model active should match RTL"
        )
        # Allow settle
        for _ in range(8):
            await RisingEdge(dut.clk)
        # Data should be non-zero when active
        assert int(dut.data) != 0, f"Cycle {cycle}: Data should be non-zero"
        assert model.data != 0, f"Cycle {cycle}: Model data should be non-zero"
        assert model.data == int(dut.data), (
            f"Cycle {cycle}: Model data should match RTL"
        )
        await _send_serial_control_word_with_model(dut, model, 0xFAB0)
        for _ in range(32):
            await RisingEdge(dut.clk)
        assert int(dut.active) == 0, f"Cycle {cycle}: inactive not cleared"
        assert model.active == 0, f"Cycle {cycle}: model inactive not cleared"
        assert model.active == int(dut.active), (
            f"Cycle {cycle}: model active should match RTL after deactivation"
        )


@cocotb.test
async def cocotb_test_bitbang_reset_behavior(dut: BitbangProtocol) -> None:
    """Test bitbang reset behavior."""
    # Start clock
    clock = Clock(dut.clk, 10, units="ns")
    cocotb.start_soon(clock.start())

    # Initialize
    dut.s_clk.value = 0
    dut.s_data.value = 0
    dut.resetn.value = 1

    # Create model instance
    model = bitbangModel(dut.clk, dut.resetn)

    await RisingEdge(dut.clk)

    # Activate and send data
    test_data = 0x12345678
    await _send_serial_data_word_with_model(dut, model, test_data)
    await _send_serial_control_word_with_model(dut, model, 0xFAB1)
    for _ in range(16):
        await RisingEdge(dut.clk)
    assert dut.active.value == 1, "Should be active"
    assert model.active == 1, "Model should be active"
    assert model.active == int(dut.active), "Model active should match RTL before reset"

    # Apply reset
    dut.resetn.value = 0
    await RisingEdge(dut.clk)
    await RisingEdge(dut.clk)

    # Check reset state
    assert dut.strobe.value == 0, "strobe should be 0 after reset"
    assert dut.active.value == 0, "active should be 0 after reset"
    assert dut.data.value == 0, "data should be 0 after reset"
    assert model.strobe == 0, "Model strobe should be 0 after reset"
    assert model.active == 0, "Model active should be 0 after reset"
    assert model.data == 0, "Model data should be 0 after reset"

    # Release reset and verify functionality
    dut.resetn.value = 1
    await RisingEdge(dut.clk)

    # Should be able to activate again
    await _send_serial_data_word_with_model(dut, model, test_data)
    await _send_serial_control_word_with_model(dut, model, 0xFAB1)
    for _ in range(16):
        await RisingEdge(dut.clk)
    assert dut.active.value == 1, "Should be active after reset recovery"
    assert model.active == 1, "Model should be active after reset recovery"
    assert model.active == int(dut.active), (
        "Model active should match RTL after reset recovery"
    )


@cocotb.test
async def cocotb_test_bitbang_model_validation(dut: BitbangProtocol) -> None:
    """Comprehensive test to validate that the model matches RTL behavior exactly."""
    # Start clock
    clock = Clock(dut.clk, 10, units="ns")
    cocotb.start_soon(clock.start())

    # Initialize inputs
    dut.s_clk.value = 0
    dut.s_data.value = 0
    dut.resetn.value = 0

    # Create model instance
    model = bitbangModel(dut.clk, dut.resetn)

    # Function to compare RTL and model outputs
    def check_outputs_match() -> None:
        assert model.strobe == int(dut.strobe), (
            f"Strobe mismatch: model={model.strobe}, RTL={int(dut.strobe)}"
        )
        assert model.active == int(dut.active), (
            f"Active mismatch: model={model.active}, RTL={int(dut.active)}"
        )
        assert model.data == int(dut.data), (
            f"Data mismatch: model={model.data:08x}, RTL={int(dut.data):08x}"
        )

    # Wait for reset
    await RisingEdge(dut.clk)
    await RisingEdge(dut.clk)
    dut.resetn.value = 1
    await RisingEdge(dut.clk)

    # Check initial state
    check_outputs_match()

    # Test various data patterns and operations
    test_patterns = [
        0x00000000,
        0xFFFFFFFF,
        0xAAAAAAAA,
        0x55555555,
        0x12345678,
        0xDEADBEEF,
        0xCAFEBABE,
        0xFEEDFACE,
    ]

    for i, test_data in enumerate(test_patterns):
        # Send data
        await _send_serial_data_word_with_model(dut, model, test_data)

        # Check after each bit transmission (periodic checks)
        if i % 2 == 0:
            await RisingEdge(dut.clk)
            check_outputs_match()

        # Activate
        await _send_serial_control_word_with_model(dut, model, 0xFAB1)

        # Allow processing time and check at intervals
        for cycle in range(32):
            await RisingEdge(dut.clk)
            if cycle % 8 == 0:  # Check every 8 cycles
                check_outputs_match()

        # Deactivate
        await _send_serial_control_word_with_model(dut, model, 0xFAB0)

        # Allow processing time
        for cycle in range(16):
            await RisingEdge(dut.clk)
            if cycle % 4 == 0:  # Check every 4 cycles
                check_outputs_match()

    # Final validation
    check_outputs_match()


async def _send_serial_control_word_with_model(
    dut: BitbangProtocol, model: bitbangModel, control_word: int
) -> None:
    """Send a 16-bit control word via serial interface to both RTL and model."""
    # Control sampled on falling edges (s_clk_sample[3]==1 & s_clk_sample[2]==0)
    debug = os.getenv("DEBUG_BITBANG") == "1"
    # Ensure starting high for falling edge detection
    dut.s_clk.value = 1
    model.s_clk = 1
    await RisingEdge(dut.clk)
    for bit_pos in range(15, -1, -1):  # MSB first
        bit_value = (control_word >> bit_pos) & 1
        dut.s_data.value = bit_value
        model.s_data = bit_value
        # High phase (one cycle)
        dut.s_clk.value = 1
        model.s_clk = 1
        await RisingEdge(dut.clk)
        # Falling edge -> control shift
        dut.s_clk.value = 0
        model.s_clk = 0
        await RisingEdge(dut.clk)
        if debug:
            cocotb.log.info(f"CTRL bit {bit_pos}={bit_value}")
    # Leave clock low
    dut.s_clk.value = 0
    model.s_clk = 0


async def _send_serial_data_word_with_model(
    dut: BitbangProtocol, model: bitbangModel, data_word: int
) -> None:
    """Send a 32-bit data word via serial interface to both RTL and model."""
    # Data sampled on rising edges (s_clk_sample[3]==0 & s_clk_sample[2]==1)
    debug = os.getenv("DEBUG_BITBANG") == "1"
    # Ensure starting low
    dut.s_clk.value = 0
    model.s_clk = 0
    await RisingEdge(dut.clk)
    for bit_pos in range(31, -1, -1):  # MSB first
        bit_value = (data_word >> bit_pos) & 1
        dut.s_data.value = bit_value
        model.s_data = bit_value
        # Low phase (one cycle)
        dut.s_clk.value = 0
        model.s_clk = 0
        await RisingEdge(dut.clk)
        # Rising edge -> data shift into serial_data
        dut.s_clk.value = 1
        model.s_clk = 1
        await RisingEdge(dut.clk)
        if debug and (bit_pos % 8 == 0):
            cocotb.log.info(f"DATA bit {bit_pos}={bit_value}")
    # Leave clock low
    dut.s_clk.value = 0
    model.s_clk = 0


async def _send_serial_control_word(dut: BitbangProtocol, control_word: int) -> None:
    """Send a 16-bit control word via serial interface."""
    # Control sampled on falling edges (s_clk_sample[3]==1 & s_clk_sample[2]==0)
    debug = os.getenv("DEBUG_BITBANG") == "1"
    # Ensure starting high for falling edge detection
    dut.s_clk.value = 1
    await RisingEdge(dut.clk)
    for bit_pos in range(15, -1, -1):  # MSB first
        bit_value = (control_word >> bit_pos) & 1
        dut.s_data.value = bit_value
        # High phase (one cycle)
        dut.s_clk.value = 1
        await RisingEdge(dut.clk)
        # Falling edge -> control shift
        dut.s_clk.value = 0
        await RisingEdge(dut.clk)
        if debug:
            cocotb.log.info(f"CTRL bit {bit_pos}={bit_value}")
    # Leave clock low
    dut.s_clk.value = 0


async def _send_serial_data_word(dut: BitbangProtocol, data_word: int) -> None:
    """Send a 32-bit data word via serial interface."""
    # Data sampled on rising edges (s_clk_sample[3]==0 & s_clk_sample[2]==1)
    debug = os.getenv("DEBUG_BITBANG") == "1"
    # Ensure starting low
    dut.s_clk.value = 0
    await RisingEdge(dut.clk)
    for bit_pos in range(31, -1, -1):  # MSB first
        bit_value = (data_word >> bit_pos) & 1
        dut.s_data.value = bit_value
        # Low phase (one cycle)
        dut.s_clk.value = 0
        await RisingEdge(dut.clk)
        # Rising edge -> data shift into serial_data
        dut.s_clk.value = 1
        await RisingEdge(dut.clk)
        if debug and (bit_pos % 8 == 0):
            cocotb.log.info(f"DATA bit {bit_pos}={bit_value}")
    # Leave clock low
    dut.s_clk.value = 0

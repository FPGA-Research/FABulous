"""RTL behavior validation for IO_1_bidirectional_frame_config_pass module using cocotb-native model (aligned with MULADD style)."""

from decimal import Decimal
from pathlib import Path
from typing import Protocol

import cocotb
from cocotb.clock import Clock
from cocotb.handle import LogicObject
from cocotb.triggers import RisingEdge, Timer

from tests.conftest import VERILOG_SOURCE_PATH, VHDL_SOURCE_PATH, CocotbRunner


class IOProtocol(Protocol):
    """Protocol defining the IO_1_bidirectional_frame_config_pass module interface."""

    # Inputs
    I: LogicObject  # from fabric to external pin (handle)  # noqa: E741
    T: LogicObject  # tristate control (handle)
    O_top: LogicObject  # from external pin to fabric (handle)
    UserCLK: LogicObject  # Clock (handle)

    # Outputs
    O: LogicObject  # from external pin to fabric (handle)  # noqa: E741
    Q: LogicObject  # from external pin to fabric (registered) (handle)
    I_top: LogicObject  # to external pin (handle)
    T_top: LogicObject  # tristate control to external pin (handle)


def test_IO_verilog_rtl(cocotb_runner: CocotbRunner) -> None:
    """Test the IO_1_bidirectional_frame_config_pass module with Verilog source."""
    cocotb_runner(
        sources=[
            VERILOG_SOURCE_PATH
            / "Tile"
            / "W_IO"
            / "IO_1_bidirectional_frame_config_pass.v"
        ],
        hdl_top_level="IO_1_bidirectional_frame_config_pass",
        test_module_path=Path(__file__),
    )


def test_IO_vhdl_rtl(cocotb_runner: CocotbRunner) -> None:
    """Test the IO_1_bidirectional_frame_config_pass module with VHDL source."""
    cocotb_runner(
        sources=[
            VHDL_SOURCE_PATH
            / "Tile"
            / "W_IO"
            / "IO_1_bidirectional_frame_config_pass.vhdl"
        ],
        hdl_top_level="io_1_bidirectional_frame_config_pass",  # GHDL converts to lowercase
        test_module_path=Path(__file__),
    )


class IOModel:
    """Cocotb-native model mirroring IO_1_bidirectional_frame_config_pass behavior."""

    # Inputs
    I_in: int = 0
    T: int = 1
    O_top: int = 0

    # Outputs
    I_top: int = 0
    T_top: int = 1
    O_int: int = 0
    Q: int = 0

    def __init__(self, clk: LogicObject) -> None:
        self._clk_signal = clk
        cocotb.start_soon(self._clocked_process())
        cocotb.start_soon(self._combinational_process())

    async def _clocked_process(self) -> None:
        while True:
            await RisingEdge(self._clk_signal)
            # Q registers O_top on clock edge
            self.Q = self.O_top & 1

    async def _combinational_process(self) -> None:
        while True:
            # Combinational behavior
            self.T_top = 0 if (self.T & 1) else 1  # T_top = ~T
            # When T=0: output mode, I drives I_top; When T=1: tri-state (we represent as 0)
            self.I_top = self.I_in & 1 if (self.T == 0) else 0
            # O reflects O_top always
            self.O_int = self.O_top & 1
            await Timer(Decimal(1), units="ps")


async def setup_dut(dut: IOProtocol) -> None:
    """Common setup for all tests."""
    # Start clock
    clock = Clock(dut.UserCLK, 10, "ns")
    cocotb.start_soon(clock.start())

    # Initialize inputs
    dut.I.value = 0
    dut.T.value = 1  # Start in input mode
    dut.O_top.value = 0

    # Wait for stabilization
    await RisingEdge(dut.UserCLK)
    await RisingEdge(dut.UserCLK)


@cocotb.test
async def cocotb_test_io_output_mode(dut: IOProtocol) -> None:
    """Test IO in output mode (T=0)."""
    await setup_dut(dut)

    model = IOModel(dut.UserCLK)

    # Test Case 1: Output mode with I=0
    dut.T.value = 0  # Enable output
    dut.I.value = 0  # Drive low
    await Timer(Decimal(100), units="ps")

    model.T = 0
    model.I_in = 0
    model.O_top = 0
    await Timer(Decimal(100), units="ps")
    assert int(dut.I_top.value) == model.I_top, (
        f"Output mode I=0: Expected I_top={model.I_top}, got {int(dut.I_top.value)}"
    )
    assert int(dut.T_top.value) == model.T_top, (
        f"Output mode I=0: Expected T_top={model.T_top}, got {int(dut.T_top.value)}"
    )

    # Test Case 2: Output mode with I=1
    dut.I.value = 1  # Drive high
    await Timer(Decimal(100), units="ps")

    model.I_in = 1
    await Timer(Decimal(100), units="ps")
    assert int(dut.I_top.value) == model.I_top, (
        f"Output mode I=1: Expected I_top={model.I_top}, got {int(dut.I_top.value)}"
    )
    assert int(dut.T_top.value) == model.T_top, (
        f"Output mode I=1: Expected T_top={model.T_top}, got {int(dut.T_top.value)}"
    )


@cocotb.test
async def cocotb_test_io_input_mode(dut: IOProtocol) -> None:
    """Test IO in input mode (T=1)."""
    await setup_dut(dut)

    model = IOModel(dut.UserCLK)

    # Test Case 1: Input mode with external signal low
    dut.T.value = 1  # Tristate/input mode
    dut.O_top.value = 0  # External drives low
    await Timer(Decimal(100), units="ps")

    model.T = 1
    model.O_top = 0
    await Timer(Decimal(100), units="ps")
    assert int(dut.T_top.value) == model.T_top, (
        f"Input mode O_top=0: Expected T_top={model.T_top}, got {int(dut.T_top.value)}"
    )
    assert int(dut.O.value) == model.O_int, (
        f"Input mode O_top=0: Expected O={model.O_int}, got {int(dut.O.value)}"
    )

    # Test Case 2: Input mode with external signal high
    dut.O_top.value = 1  # External drives high
    await Timer(Decimal(100), units="ps")

    model.O_top = 1
    await Timer(Decimal(100), units="ps")
    assert int(dut.T_top.value) == model.T_top, (
        f"Input mode O_top=1: Expected T_top={model.T_top}, got {int(dut.T_top.value)}"
    )
    assert int(dut.O.value) == model.O_int, (
        f"Input mode O_top=1: Expected O={model.O_int}, got {int(dut.O.value)}"
    )


@cocotb.test
async def cocotb_test_io_registered_input(dut: IOProtocol) -> None:
    """Test registered input functionality (Q output)."""
    await setup_dut(dut)

    model = IOModel(dut.UserCLK)

    # Set input mode
    dut.T.value = 1
    dut.O_top.value = 0
    await Timer(Decimal(100), units="ps")

    # Initial Q should be 0 (or previous state)
    _initial_q = int(dut.Q.value)

    # Change external input to 1
    dut.O_top.value = 1
    model.O_top = 1
    await RisingEdge(dut.UserCLK)
    await Timer(Decimal(100), units="ps")

    # Q should now reflect the registered input
    assert int(dut.Q.value) == 1, f"After clock, Q should be 1, got {int(dut.Q.value)}"

    # Change input back to 0 but Q should hold until next clock
    dut.O_top.value = 0
    await Timer(Decimal(100), units="ps")

    # Q should still be 1 (previous clocked value)
    assert int(dut.Q.value) == 1, (
        f"Q should hold previous value, got {int(dut.Q.value)}"
    )

    # Clock again to register new value
    model.O_top = 0
    await RisingEdge(dut.UserCLK)
    await Timer(Decimal(100), units="ps")

    assert int(dut.Q.value) == 0, (
        f"After second clock, Q should be 0, got {int(dut.Q.value)}"
    )


@cocotb.test
async def io_bidirectional_switching_test(dut: IOProtocol) -> None:
    """Test switching between input and output modes."""
    await setup_dut(dut)

    # No software model needed in this scenario

    # Start in output mode
    dut.T.value = 0
    dut.I.value = 1
    await Timer(Decimal(100), units="ps")

    # Should be driving output
    # HDL: T_top = ~T, so when T=0 (output), T_top=1
    assert int(dut.T_top.value) == 1, "Should be in output mode (T_top=~T=~0=1)"
    assert int(dut.I_top.value) == 1, "Should be driving I_top=1"

    # Switch to input mode
    dut.T.value = 1
    dut.O_top.value = 0  # External source drives 0
    await Timer(Decimal(100), units="ps")

    # Should be in tristate/input mode
    # HDL: T_top = ~T, so when T=1 (input), T_top=0
    assert int(dut.T_top.value) == 0, "Should be in input mode (T_top=~T=~1=0)"
    assert int(dut.O.value) == 0, "Should read O_top=0"

    # Switch back to output mode
    dut.T.value = 0
    dut.I.value = 0
    await Timer(Decimal(100), units="ps")

    # Should be driving again
    # HDL: T_top = ~T, so when T=0 (output), T_top=1
    assert int(dut.T_top.value) == 1, "Should be back in output mode (T_top=~T=~0=1)"
    assert int(dut.I_top.value) == 0, "Should be driving I_top=0"


@cocotb.test
async def cocotb_test_io_simultaneous_signals(dut: IOProtocol) -> None:
    """Test behavior with various signal combinations."""
    await setup_dut(dut)

    model = IOModel(dut.UserCLK)

    # Test matrix of input combinations
    test_cases = [
        {"I": 0, "T": 0, "O_top": 0, "desc": "Output mode, drive 0"},
        {"I": 1, "T": 0, "O_top": 0, "desc": "Output mode, drive 1"},
        {"I": 0, "T": 0, "O_top": 1, "desc": "Output mode, drive 0 (O_top ignored)"},
        {"I": 1, "T": 0, "O_top": 1, "desc": "Output mode, drive 1 (O_top ignored)"},
        {"I": 0, "T": 1, "O_top": 0, "desc": "Input mode, external 0"},
        {"I": 1, "T": 1, "O_top": 0, "desc": "Input mode, external 0 (I ignored)"},
        {"I": 0, "T": 1, "O_top": 1, "desc": "Input mode, external 1"},
        {"I": 1, "T": 1, "O_top": 1, "desc": "Input mode, external 1 (I ignored)"},
    ]

    for case in test_cases:
        dut.I.value = case["I"]
        dut.T.value = case["T"]
        dut.O_top.value = case["O_top"]
        await Timer(Decimal(100), units="ps")

        model.I_in = case["I"]
        model.T = case["T"]
        model.O_top = case["O_top"]
        await Timer(Decimal(100), units="ps")

        # Check T_top (direction control)
        assert int(dut.T_top.value) == model.T_top, (
            f"{case['desc']}: Expected T_top={model.T_top}, got {int(dut.T_top.value)}"
        )

        # Check O (internal input)
        assert int(dut.O.value) == model.O_int, (
            f"{case['desc']}: Expected O={model.O_int}, got {int(dut.O.value)}"
        )

        # In output mode, check I_top
        if case["T"] == 0:
            assert int(dut.I_top.value) == model.I_top, (
                f"{case['desc']}: Expected I_top={model.I_top}, got {int(dut.I_top.value)}"
            )


@cocotb.test
async def cocotb_test_io_clock_independence_combinational(dut: IOProtocol) -> None:
    """Test that combinational paths (I_top, T_top, O) are clock-independent."""
    await setup_dut(dut)

    # Test that combinational outputs change immediately, not on clock edge

    # Set initial state
    dut.T.value = 0
    dut.I.value = 0
    await Timer(Decimal(100), units="ps")

    initial_i_top = int(dut.I_top.value)

    # Change I and verify immediate response (before clock edge)
    dut.I.value = 1
    await Timer(Decimal(50), units="ps")  # Wait less than clock period

    # I_top should change immediately (combinational)
    assert int(dut.I_top.value) != initial_i_top, (
        "I_top should change immediately (combinational path)"
    )
    assert int(dut.I_top.value) == 1, f"Expected I_top=1, got {int(dut.I_top.value)}"

    # Test T control
    dut.T.value = 1  # Switch to input mode
    await Timer(Decimal(50), units="ps")

    # T_top should change immediately
    # HDL: T_top = ~T, so when T=1, T_top=0
    assert int(dut.T_top.value) == 0, (
        "T_top should change immediately to 0 (T_top=~T=~1=0)"
    )

    # Test O path
    dut.O_top.value = 1
    await Timer(Decimal(50), units="ps")

    # O should change immediately
    assert int(dut.O.value) == 1, "O should change immediately"

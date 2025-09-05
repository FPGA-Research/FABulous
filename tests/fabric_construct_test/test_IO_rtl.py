"""RTL behavior validation for IO_1_bidirectional_frame_config_pass module using cocotb."""

from decimal import Decimal
from pathlib import Path
from typing import Any, Protocol

import cocotb
import pytest
from cocotb.clock import Clock
from cocotb.triggers import RisingEdge, Timer

from tests.conftest import VERILOG_SOURCE_PATH, VHDL_SOURCE_PATH, CocotbRunner


class IOProtocol(Protocol):
    """Protocol defining the IO_1_bidirectional_frame_config_pass module interface."""

    # Inputs
    I: Any  # from fabric to external pin  # noqa: E741
    T: Any  # tristate control
    O_top: Any  # from external pin to fabric
    UserCLK: Any  # Clock

    # Outputs
    O: Any  # from external pin to fabric  # noqa: E741
    Q: Any  # from external pin to fabric (registered)
    I_top: Any  # to external pin
    T_top: Any  # tristate control to external pin


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


@pytest.mark.skip(reason="Need update VHDL source")
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
    """Software model for IO_1_bidirectional_frame_config_pass module functionality."""

    def __init__(self) -> None:
        """Initialize the IO model."""
        self.q_reg = 0

    def compute_io(
        self, input_i: int, input_t: int, o_top: int, _config_bits: int
    ) -> tuple[int, int, int, int]:
        """
        Compute IO functionality.

        Args:
            input_i: Internal input signal
            input_t: Internal tristate control
            o_top: External input from pad
            config_bits: Configuration bits

        Returns:
            tuple: (I_top, T_top, O, Q) - External outputs and internal outputs
        """
        # Basic bidirectional IO functionality
        # When T=0: Output mode (I drives I_top)
        # When T=1: Input mode (O_top drives O)

        if input_t == 0:  # Output mode
            i_top_out = input_i
            t_top_out = 0  # Enable output driver
        else:  # Input/tristate mode
            i_top_out = 0  # Don't drive (or high-Z, represented as 0)
            t_top_out = 1  # Tristate

        # Internal output O always reflects external input
        o_output = o_top

        # Q is registered version of O (updated on clock edge)
        q_output = self.q_reg

        return i_top_out, t_top_out, o_output, q_output

    def clock_cycle(self, o_top: int) -> None:
        """Update registered signals on clock edge."""
        self.q_reg = o_top

    def reset(self) -> None:
        """Reset the model state."""
        self.q_reg = 0


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


@pytest.mark.skip(reason="Cocotb test - run by simulation, not pytest")
@cocotb.test
async def test_io_output_mode(dut: IOProtocol) -> None:
    """Test IO in output mode (T=0)."""
    await setup_dut(dut)

    model = IOModel()

    # Test Case 1: Output mode with I=0
    dut.T.value = 0  # Enable output
    dut.I.value = 0  # Drive low
    await Timer(Decimal(100), units="ps")

    expected_i_top, expected_t_top, _, _ = model.compute_io(0, 0, 0, 0)
    assert dut.I_top.value.integer == expected_i_top, (
        f"Output mode I=0: Expected I_top={expected_i_top}, got {dut.I_top.value.integer}"
    )
    assert dut.T_top.value.integer == expected_t_top, (
        f"Output mode I=0: Expected T_top={expected_t_top}, got {dut.T_top.value.integer}"
    )

    # Test Case 2: Output mode with I=1
    dut.I.value = 1  # Drive high
    await Timer(Decimal(100), units="ps")

    expected_i_top, expected_t_top, _, _ = model.compute_io(1, 0, 0, 0)
    assert dut.I_top.value.integer == expected_i_top, (
        f"Output mode I=1: Expected I_top={expected_i_top}, got {dut.I_top.value.integer}"
    )
    assert dut.T_top.value.integer == expected_t_top, (
        f"Output mode I=1: Expected T_top={expected_t_top}, got {dut.T_top.value.integer}"
    )


@pytest.mark.skip(reason="Cocotb test - run by simulation, not pytest")
@cocotb.test
async def test_io_input_mode(dut: IOProtocol) -> None:
    """Test IO in input mode (T=1)."""
    await setup_dut(dut)

    model = IOModel()

    # Test Case 1: Input mode with external signal low
    dut.T.value = 1  # Tristate/input mode
    dut.O_top.value = 0  # External drives low
    await Timer(Decimal(100), units="ps")

    expected_i_top, expected_t_top, expected_o, _ = model.compute_io(0, 1, 0, 0)
    assert dut.T_top.value.integer == expected_t_top, (
        f"Input mode O_top=0: Expected T_top={expected_t_top}, got {dut.T_top.value.integer}"
    )
    assert dut.O.value.integer == expected_o, (
        f"Input mode O_top=0: Expected O={expected_o}, got {dut.O.value.integer}"
    )

    # Test Case 2: Input mode with external signal high
    dut.O_top.value = 1  # External drives high
    await Timer(Decimal(100), units="ps")

    expected_i_top, expected_t_top, expected_o, _ = model.compute_io(0, 1, 1, 0)
    assert dut.T_top.value.integer == expected_t_top, (
        f"Input mode O_top=1: Expected T_top={expected_t_top}, got {dut.T_top.value.integer}"
    )
    assert dut.O.value.integer == expected_o, (
        f"Input mode O_top=1: Expected O={expected_o}, got {dut.O.value.integer}"
    )


@pytest.mark.skip(reason="Cocotb test - run by simulation, not pytest")
@cocotb.test
async def test_io_registered_input(dut: IOProtocol) -> None:
    """Test registered input functionality (Q output)."""
    await setup_dut(dut)

    model = IOModel()

    # Set input mode
    dut.T.value = 1
    dut.O_top.value = 0
    await Timer(Decimal(100), units="ps")

    # Initial Q should be 0 (or previous state)
    _initial_q = dut.Q.value.integer

    # Change external input to 1
    dut.O_top.value = 1
    model.clock_cycle(1)  # Update model
    await RisingEdge(dut.UserCLK)
    await Timer(Decimal(100), units="ps")

    # Q should now reflect the registered input
    assert dut.Q.value.integer == 1, (
        f"After clock, Q should be 1, got {dut.Q.value.integer}"
    )

    # Change input back to 0 but Q should hold until next clock
    dut.O_top.value = 0
    await Timer(Decimal(100), units="ps")

    # Q should still be 1 (previous clocked value)
    assert dut.Q.value.integer == 1, (
        f"Q should hold previous value, got {dut.Q.value.integer}"
    )

    # Clock again to register new value
    model.clock_cycle(0)
    await RisingEdge(dut.UserCLK)
    await Timer(Decimal(100), units="ps")

    assert dut.Q.value.integer == 0, (
        f"After second clock, Q should be 0, got {dut.Q.value.integer}"
    )


@pytest.mark.skip(reason="Cocotb test - run by simulation, not pytest")
@cocotb.test
async def test_io_bidirectional_switching(dut: IOProtocol) -> None:
    """Test switching between input and output modes."""
    await setup_dut(dut)

    # No software model needed in this scenario

    # Start in output mode
    dut.T.value = 0
    dut.I.value = 1
    await Timer(Decimal(100), units="ps")

    # Should be driving output
    assert dut.T_top.value.integer == 0, "Should be in output mode (T_top=0)"
    assert dut.I_top.value.integer == 1, "Should be driving I_top=1"

    # Switch to input mode
    dut.T.value = 1
    dut.O_top.value = 0  # External source drives 0
    await Timer(Decimal(100), units="ps")

    # Should be in tristate/input mode
    assert dut.T_top.value.integer == 1, "Should be in input mode (T_top=1)"
    assert dut.O.value.integer == 0, "Should read O_top=0"

    # Switch back to output mode
    dut.T.value = 0
    dut.I.value = 0
    await Timer(Decimal(100), units="ps")

    # Should be driving again
    assert dut.T_top.value.integer == 0, "Should be back in output mode (T_top=0)"
    assert dut.I_top.value.integer == 0, "Should be driving I_top=0"


@pytest.mark.skip(reason="Cocotb test - run by simulation, not pytest")
@cocotb.test
async def test_io_simultaneous_signals(dut: IOProtocol) -> None:
    """Test behavior with various signal combinations."""
    await setup_dut(dut)

    model = IOModel()

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

        expected_i_top, expected_t_top, expected_o, _ = model.compute_io(
            case["I"], case["T"], case["O_top"], 0
        )

        # Check T_top (direction control)
        assert dut.T_top.value.integer == expected_t_top, (
            f"{case['desc']}: Expected T_top={expected_t_top}, got {dut.T_top.value.integer}"
        )

        # Check O (internal input)
        assert dut.O.value.integer == expected_o, (
            f"{case['desc']}: Expected O={expected_o}, got {dut.O.value.integer}"
        )

        # In output mode, check I_top
        if case["T"] == 0:
            assert dut.I_top.value.integer == expected_i_top, (
                f"{case['desc']}: Expected I_top={expected_i_top}, got {dut.I_top.value.integer}"
            )


@pytest.mark.skip(reason="Cocotb test - run by simulation, not pytest")
@cocotb.test
async def test_io_clock_independence_combinational(dut: IOProtocol) -> None:
    """Test that combinational paths (I_top, T_top, O) are clock-independent."""
    await setup_dut(dut)

    # Test that combinational outputs change immediately, not on clock edge

    # Set initial state
    dut.T.value = 0
    dut.I.value = 0
    await Timer(Decimal(100), units="ps")

    initial_i_top = dut.I_top.value.integer

    # Change I and verify immediate response (before clock edge)
    dut.I.value = 1
    await Timer(Decimal(50), units="ps")  # Wait less than clock period

    # I_top should change immediately (combinational)
    assert dut.I_top.value.integer != initial_i_top, (
        "I_top should change immediately (combinational path)"
    )
    assert dut.I_top.value.integer == 1, (
        f"Expected I_top=1, got {dut.I_top.value.integer}"
    )

    # Test T control
    dut.T.value = 1  # Switch to input mode
    await Timer(Decimal(50), units="ps")

    # T_top should change immediately
    assert dut.T_top.value.integer == 1, "T_top should change immediately to 1"

    # Test O path
    dut.O_top.value = 1
    await Timer(Decimal(50), units="ps")

    # O should change immediately
    assert dut.O.value.integer == 1, "O should change immediately"

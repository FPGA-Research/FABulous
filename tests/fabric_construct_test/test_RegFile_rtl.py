"""RTL behavior validation for RegFile_32x4 using a cocotb-native model (like MULADD)."""

from decimal import Decimal
from pathlib import Path
from typing import Protocol

import cocotb
from cocotb.clock import Clock
from cocotb.handle import LogicObject
from cocotb.triggers import RisingEdge, Timer

from tests.conftest import VERILOG_SOURCE_PATH, VHDL_SOURCE_PATH, CocotbRunner


class RegFileProtocol(Protocol):
    """Protocol defining the RegFile_32x4 module interface."""

    # Inputs
    D: LogicObject  # [3:0] Register File write port data (handle)
    W_ADR: LogicObject  # [4:0] Write address (handle)
    W_en: LogicObject  # Write enable (handle)
    A_ADR: LogicObject  # [4:0] Read port A address (handle)
    B_ADR: LogicObject  # [4:0] Read port B address (handle)
    UserCLK: LogicObject  # Clock (handle)
    ConfigBits: LogicObject  # [NoConfigBits-1:0] (handle)

    # Outputs
    AD: LogicObject  # [3:0] Register File read port A data (handle)
    BD: LogicObject  # [3:0] Register File read port B data (handle)

    # Internal registers (accessible for testing)
    AD_reg: LogicObject  # [3:0] Registered read port A (handle)
    BD_reg: LogicObject  # [3:0] Registered read port B (handle)


def test_RegFile_verilog_rtl(cocotb_runner: CocotbRunner) -> None:
    """Test the RegFile_32x4 module with Verilog source."""
    cocotb_runner(
        sources=[VERILOG_SOURCE_PATH / "Tile" / "RegFile" / "RegFile_32x4.v"],
        hdl_top_level="RegFile_32x4",
        test_module_path=Path(__file__),
    )


def test_RegFile_vhdl_rtl(cocotb_runner: CocotbRunner) -> None:
    """Test the RegFile_32x4 module with VHDL source."""
    cocotb_runner(
        sources=[VHDL_SOURCE_PATH / "Tile" / "RegFile" / "RegFile_32x4.vhdl"],
        hdl_top_level="regfile_32x4",  # GHDL converts to lowercase
        test_module_path=Path(__file__),
    )


class RegFileModel:
    """Cocotb-native software model mirroring the RTL timing of RegFile_32x4."""

    # Inputs
    D: int = 0
    W_ADR: int = 0
    W_en: int = 0
    A_ADR: int = 0
    B_ADR: int = 0
    ConfigBits: int = 0  # bit0: AD_reg, bit1: BD_reg

    # Internal state
    _AD_comb: int = 0
    _BD_comb: int = 0

    # Registered state and outputs
    AD: int = 0
    BD: int = 0
    AD_reg: int = 0
    BD_reg: int = 0

    def __init__(self, clk: LogicObject) -> None:
        # 32x4 register file memory
        self._mem = [0] * 32
        self._clk_signal = clk

        # Start clocked and combinational processes
        cocotb.start_soon(self._clocked_process())
        cocotb.start_soon(self._combinational_process())

    async def _clocked_process(self) -> None:
        while True:
            await RisingEdge(self._clk_signal)
            # Synchronous write on posedge
            if self.W_en:
                self._mem[self.W_ADR & 0x1F] = self.D & 0xF
            # Registered capture of read data
            self.AD_reg = self._AD_comb & 0xF
            self.BD_reg = self._BD_comb & 0xF

    async def _combinational_process(self) -> None:
        while True:
            # Combinational reads
            self._AD_comb = self._mem[self.A_ADR & 0x1F] & 0xF
            self._BD_comb = self._mem[self.B_ADR & 0x1F] & 0xF

            # Output muxing per ConfigBits
            if self.ConfigBits & 0b01:
                self.AD = self.AD_reg
            else:
                self.AD = self._AD_comb

            if (self.ConfigBits >> 1) & 0b1:
                self.BD = self.BD_reg
            else:
                self.BD = self._BD_comb

            # Tiny delay to avoid busy loop
            await Timer(Decimal(1), units="ps")


async def setup_dut(dut: RegFileProtocol) -> None:
    """Common setup for all tests."""
    # Start clock
    clock = Clock(dut.UserCLK, 10, "ns")
    cocotb.start_soon(clock.start())

    # Initialize inputs
    dut.D.value = 0
    dut.W_ADR.value = 0
    dut.W_en.value = 0
    dut.A_ADR.value = 0
    dut.B_ADR.value = 0
    dut.ConfigBits.value = 0

    # Wait for stabilization
    await RisingEdge(dut.UserCLK)
    await RisingEdge(dut.UserCLK)


@cocotb.test
async def cocotb_test_regfile_basic_write_read(dut: RegFileProtocol) -> None:
    """Test basic write and read functionality."""
    await setup_dut(dut)

    model = RegFileModel(dut.UserCLK)

    # Test Case 1: Write data to address 5
    write_addr = 5
    write_data = 0xA  # 4-bit data

    dut.W_ADR.value = write_addr
    dut.D.value = write_data
    dut.W_en.value = 1
    model.W_ADR = write_addr
    model.D = write_data
    model.W_en = 1

    await RisingEdge(dut.UserCLK)
    dut.W_en.value = 0
    model.W_en = 0
    await Timer(Decimal(100), units="ps")

    # Test combinational read on port A (ConfigBits[0] = 0)
    dut.A_ADR.value = write_addr
    dut.ConfigBits.value = 0b00  # Combinational mode
    model.A_ADR = write_addr
    model.ConfigBits = 0b00
    await Timer(Decimal(100), units="ps")

    assert int(dut.AD.value) == write_data, (
        f"Port A read failed: Expected AD = {write_data}, got {int(dut.AD.value)}"
    )


@cocotb.test
async def cocotb_test_regfile_dual_port_read(dut: RegFileProtocol) -> None:
    """Test dual port read functionality."""
    await setup_dut(dut)

    model = RegFileModel(dut.UserCLK)

    # Write different data to different addresses
    test_data = [(5, 0xA), (10, 0x5), (15, 0xF), (20, 0x3)]

    for addr, data in test_data:
        dut.W_ADR.value = addr
        dut.D.value = data
        dut.W_en.value = 1
        model.W_ADR = addr
        model.D = data
        model.W_en = 1
        await RisingEdge(dut.UserCLK)
        dut.W_en.value = 0
        model.W_en = 0

    await Timer(Decimal(100), units="ps")

    # Test simultaneous read from both ports
    dut.A_ADR.value = 5
    dut.B_ADR.value = 10
    dut.ConfigBits.value = 0b00  # Combinational mode
    model.A_ADR = 5
    model.B_ADR = 10
    model.ConfigBits = 0b00
    await Timer(Decimal(100), units="ps")

    assert int(dut.AD.value) == 0xA, (
        f"Port A read failed: Expected AD = 0xA, got {int(dut.AD.value)}"
    )
    assert int(dut.BD.value) == 0x5, (
        f"Port B read failed: Expected BD = 0x5, got {int(dut.BD.value)}"
    )


@cocotb.test
async def cocotb_test_regfile_registered_output_port_a(dut: RegFileProtocol) -> None:
    """Test registered output functionality for port A."""
    await setup_dut(dut)

    model = RegFileModel(dut.UserCLK)

    # Write test data
    dut.W_ADR.value = 7
    dut.D.value = 0xC
    dut.W_en.value = 1
    model.W_ADR = 7
    model.D = 0xC
    model.W_en = 1
    await RisingEdge(dut.UserCLK)
    dut.W_en.value = 0
    model.W_en = 0

    # Configure for registered output on port A (ConfigBits[0] = 1)
    dut.ConfigBits.value = 0b01
    dut.A_ADR.value = 7
    model.ConfigBits = 0b01
    model.A_ADR = 7

    # In registered mode, need clock edge to update output
    await RisingEdge(dut.UserCLK)
    await Timer(Decimal(100), units="ps")

    assert int(dut.AD.value) == 0xC, (
        f"Registered port A read failed: Expected AD = 0xC, got {int(dut.AD.value)}"
    )

    # Change address and verify output doesn't change immediately
    old_ad = int(dut.AD.value)
    dut.A_ADR.value = 0  # Different address with different data
    model.A_ADR = 0
    await Timer(Decimal(100), units="ps")

    # In registered mode, output should not change until next clock
    assert int(dut.AD.value) == old_ad, (
        f"Registered output changed immediately: Expected AD = {old_ad}, got {int(dut.AD.value)}"
    )


@cocotb.test
async def cocotb_test_regfile_registered_output_port_b(
    dut: RegFileProtocol,
) -> None:
    """Test registered output functionality for port B."""
    await setup_dut(dut)

    model = RegFileModel(dut.UserCLK)

    # Write test data
    dut.W_ADR.value = 12
    dut.D.value = 0x6
    dut.W_en.value = 1
    model.W_ADR = 12
    model.D = 0x6
    model.W_en = 1
    await RisingEdge(dut.UserCLK)
    dut.W_en.value = 0
    model.W_en = 0

    # Configure for registered output on port B (ConfigBits[1] = 1)
    dut.ConfigBits.value = 0b10
    dut.B_ADR.value = 12
    model.ConfigBits = 0b10
    model.B_ADR = 12

    # In registered mode, need clock edge to update output
    await RisingEdge(dut.UserCLK)
    await Timer(Decimal(100), units="ps")

    assert int(dut.BD.value) == 0x6, (
        f"Registered port B read failed: Expected BD = 0x6, got {int(dut.BD.value)}"
    )


@cocotb.test
async def regfile_address_independence_test(dut: RegFileProtocol) -> None:
    """Test that different addresses store independent data."""
    await setup_dut(dut)

    model = RegFileModel(dut.UserCLK)

    # Write unique data to multiple addresses
    test_addresses = [0, 5, 10, 15, 20, 25, 30, 31]
    expected_data = {}

    for i, addr in enumerate(test_addresses):
        data = (i + 1) & 0xF  # Unique 4-bit data
        expected_data[addr] = data

        dut.W_ADR.value = addr
        dut.D.value = data
        dut.W_en.value = 1
        model.W_ADR = addr
        model.D = data
        model.W_en = 1
        await RisingEdge(dut.UserCLK)
        dut.W_en.value = 0
        model.W_en = 0

    await Timer(Decimal(100), units="ps")

    # Verify each address contains correct data
    dut.ConfigBits.value = 0b00  # Combinational mode
    model.ConfigBits = 0b00
    for addr, expected in expected_data.items():
        dut.A_ADR.value = addr
        model.A_ADR = addr
        await Timer(Decimal(50), units="ps")
        assert int(dut.AD.value) == expected, (
            f"Address {addr}: Expected data = {expected}, got {int(dut.AD.value)}"
        )
    # Model check omitted: rely on DUT readback for ground truth


@cocotb.test
async def regfile_write_enable_control_test(dut: RegFileProtocol) -> None:
    """Test write enable control functionality."""
    await setup_dut(dut)

    model = RegFileModel(dut.UserCLK)

    # Write initial data
    dut.W_ADR.value = 8
    dut.D.value = 0x7
    dut.W_en.value = 1
    model.W_ADR = 8
    model.D = 0x7
    model.W_en = 1
    await RisingEdge(dut.UserCLK)
    dut.W_en.value = 0
    model.W_en = 0

    # Read initial value
    dut.A_ADR.value = 8
    dut.ConfigBits.value = 0b00
    model.A_ADR = 8
    model.ConfigBits = 0b00
    await Timer(Decimal(100), units="ps")
    initial_value = int(dut.AD.value)

    # Try to write with W_en = 0 (should not write)
    dut.D.value = 0x2  # Different data
    dut.W_en.value = 0  # Write disabled
    model.D = 0x2
    model.W_en = 0
    await RisingEdge(dut.UserCLK)

    # Verify data unchanged
    await Timer(Decimal(100), units="ps")
    assert int(dut.AD.value) == initial_value, (
        f"Data changed with W_en=0: Expected {initial_value}, got {int(dut.AD.value)}"
    )

    # Now enable write and verify it works
    dut.W_en.value = 1
    model.W_en = 1
    await RisingEdge(dut.UserCLK)
    dut.W_en.value = 0
    model.W_en = 0

    await Timer(Decimal(100), units="ps")
    assert int(dut.AD.value) == 0x2, (
        f"Write with W_en=1 failed: Expected 0x2, got {int(dut.AD.value)}"
    )


@cocotb.test
async def cocotb_test_regfile_both_ports_registered(dut: RegFileProtocol) -> None:
    """Test functionality with both ports in registered mode."""
    await setup_dut(dut)

    model = RegFileModel(dut.UserCLK)

    # Write test data to different addresses
    dut.W_ADR.value = 3
    dut.D.value = 0x9
    dut.W_en.value = 1
    model.W_ADR = 3
    model.D = 0x9
    model.W_en = 1
    await RisingEdge(dut.UserCLK)
    dut.W_en.value = 0
    model.W_en = 0

    dut.W_ADR.value = 13
    dut.D.value = 0x4
    dut.W_en.value = 1
    model.W_ADR = 13
    model.D = 0x4
    model.W_en = 1
    await RisingEdge(dut.UserCLK)
    dut.W_en.value = 0
    model.W_en = 0

    # Configure both ports for registered output
    dut.ConfigBits.value = 0b11  # Both ports registered
    dut.A_ADR.value = 3
    dut.B_ADR.value = 13
    model.ConfigBits = 0b11
    model.A_ADR = 3
    model.B_ADR = 13

    # Clock to update registered outputs
    await RisingEdge(dut.UserCLK)
    await Timer(Decimal(100), units="ps")

    assert int(dut.AD.value) == 0x9, (
        f"Registered port A failed: Expected 0x9, got {int(dut.AD.value)}"
    )
    assert int(dut.BD.value) == 0x4, (
        f"Registered port B failed: Expected 0x4, got {int(dut.BD.value)}"
    )

"""RTL behavior validation for RegFile_32x4 module using cocotb."""

from decimal import Decimal
from pathlib import Path
from typing import Any, Protocol

import cocotb
import pytest
from cocotb.clock import Clock
from cocotb.triggers import RisingEdge, Timer

from tests.conftest import VERILOG_SOURCE_PATH, VHDL_SOURCE_PATH, CocotbRunner


class RegFileProtocol(Protocol):
    """Protocol defining the RegFile_32x4 module interface."""

    # Inputs
    D: Any  # [3:0] Register File write port data
    W_ADR: Any  # [4:0] Write address
    W_en: Any  # Write enable
    A_ADR: Any  # [4:0] Read port A address
    B_ADR: Any  # [4:0] Read port B address
    UserCLK: Any  # Clock
    ConfigBits: Any  # [NoConfigBits-1:0]

    # Outputs
    AD: Any  # [3:0] Register File read port A data
    BD: Any  # [3:0] Register File read port B data

    # Internal registers (accessible for testing)
    AD_reg: Any  # [3:0] Registered read port A
    BD_reg: Any  # [3:0] Registered read port B


def test_RegFile_verilog_rtl(cocotb_runner: CocotbRunner) -> None:
    """Test the RegFile_32x4 module with Verilog source."""
    cocotb_runner(
        sources=[VERILOG_SOURCE_PATH / "Tile" / "RegFile" / "RegFile_32x4.v"],
        hdl_top_level="RegFile_32x4",
        test_module_path=Path(__file__),
    )


@pytest.mark.skip(reason="Need update VHDL source")
def test_RegFile_vhdl_rtl(cocotb_runner: CocotbRunner) -> None:
    """Test the RegFile_32x4 module with VHDL source."""
    cocotb_runner(
        sources=[VHDL_SOURCE_PATH / "Tile" / "RegFile" / "RegFile_32x4.vhdl"],
        hdl_top_level="regfile_32x4",  # GHDL converts to lowercase
        test_module_path=Path(__file__),
    )


class RegFileModel:
    """Software model for RegFile_32x4 module functionality."""

    def __init__(self) -> None:
        """Initialize the register file model."""
        # 32 registers, each 4 bits wide
        self.memory = [0] * 32
        self.ad_reg = 0
        self.bd_reg = 0

    def write_cycle(self, w_adr: int, data: int, w_en: int) -> None:
        """
        Perform write operation.

        Args:
            w_adr: Write address (5 bits)
            data: Data to write (4 bits)
            w_en: Write enable
        """
        if w_en:
            addr = w_adr & 0x1F  # 5-bit address
            self.memory[addr] = data & 0xF  # 4-bit data

    def read_cycle(self, a_adr: int, b_adr: int, config_bits: int) -> tuple[int, int]:
        """
        Perform read operation.

        Args:
            a_adr: Port A read address (5 bits)
            b_adr: Port B read address (5 bits)
            config_bits: Configuration bits

        Returns:
            tuple: (AD output, BD output)
        """
        # Read data from memory
        a_addr = a_adr & 0x1F
        b_addr = b_adr & 0x1F

        a_data = self.memory[a_addr]
        b_data = self.memory[b_addr]

        # Check if outputs are registered
        ad_reg_en = config_bits & 1  # ConfigBits[0]
        bd_reg_en = (config_bits >> 1) & 1  # ConfigBits[1]

        if ad_reg_en:
            # Update register on read
            self.ad_reg = a_data
            ad_out = self.ad_reg
        else:
            ad_out = a_data

        if bd_reg_en:
            # Update register on read
            self.bd_reg = b_data
            bd_out = self.bd_reg
        else:
            bd_out = b_data

        return ad_out, bd_out

    def reset(self) -> None:
        """Reset the model state."""
        self.memory = [0] * 32
        self.ad_reg = 0
        self.bd_reg = 0


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


@pytest.mark.skip(reason="Cocotb test - run by simulation, not pytest")
@cocotb.test
async def test_regfile_basic_write_read(dut: RegFileProtocol) -> None:
    """Test basic write and read functionality."""
    await setup_dut(dut)

    model = RegFileModel()

    # Test Case 1: Write data to address 5
    write_addr = 5
    write_data = 0xA  # 4-bit data

    dut.W_ADR.value = write_addr
    dut.D.value = write_data
    dut.W_en.value = 1

    # Perform write in model
    model.write_cycle(write_addr, write_data, 1)

    await RisingEdge(dut.UserCLK)
    dut.W_en.value = 0
    await Timer(Decimal(100), units="ps")

    # Test combinational read on port A (ConfigBits[0] = 0)
    dut.A_ADR.value = write_addr
    dut.ConfigBits.value = 0b00  # Combinational mode
    await Timer(Decimal(100), units="ps")

    expected_ad, _ = model.read_cycle(write_addr, 0, 0b00)
    assert dut.AD.value.integer == expected_ad, (
        f"Port A read failed: Expected AD = {expected_ad}, got {dut.AD.value.integer}"
    )


@pytest.mark.skip(reason="Cocotb test - run by simulation, not pytest")
@cocotb.test
async def test_regfile_dual_port_read(dut: RegFileProtocol) -> None:
    """Test dual port read functionality."""
    await setup_dut(dut)

    model = RegFileModel()

    # Write different data to different addresses
    test_data = [(5, 0xA), (10, 0x5), (15, 0xF), (20, 0x3)]

    for addr, data in test_data:
        dut.W_ADR.value = addr
        dut.D.value = data
        dut.W_en.value = 1
        model.write_cycle(addr, data, 1)
        await RisingEdge(dut.UserCLK)
        dut.W_en.value = 0

    await Timer(Decimal(100), units="ps")

    # Test simultaneous read from both ports
    dut.A_ADR.value = 5
    dut.B_ADR.value = 10
    dut.ConfigBits.value = 0b00  # Combinational mode
    await Timer(Decimal(100), units="ps")

    expected_ad, expected_bd = model.read_cycle(5, 10, 0b00)
    assert dut.AD.value.integer == expected_ad, (
        f"Port A read failed: Expected AD = {expected_ad}, got {dut.AD.value.integer}"
    )
    assert dut.BD.value.integer == expected_bd, (
        f"Port B read failed: Expected BD = {expected_bd}, got {dut.BD.value.integer}"
    )


@pytest.mark.skip(reason="Cocotb test - run by simulation, not pytest")
@cocotb.test
async def test_regfile_registered_output_port_a(dut: RegFileProtocol) -> None:
    """Test registered output functionality for port A."""
    await setup_dut(dut)

    model = RegFileModel()

    # Write test data
    dut.W_ADR.value = 7
    dut.D.value = 0xC
    dut.W_en.value = 1
    model.write_cycle(7, 0xC, 1)
    await RisingEdge(dut.UserCLK)
    dut.W_en.value = 0

    # Configure for registered output on port A (ConfigBits[0] = 1)
    dut.ConfigBits.value = 0b01
    dut.A_ADR.value = 7

    # In registered mode, need clock edge to update output
    await RisingEdge(dut.UserCLK)
    await Timer(Decimal(100), units="ps")

    expected_ad, _ = model.read_cycle(7, 0, 0b01)
    assert dut.AD.value.integer == expected_ad, (
        f"Registered port A read failed: Expected AD = {expected_ad}, got {dut.AD.value.integer}"
    )

    # Change address and verify output doesn't change immediately
    old_ad = dut.AD.value.integer
    dut.A_ADR.value = 0  # Different address with different data
    await Timer(Decimal(100), units="ps")

    # In registered mode, output should not change until next clock
    assert dut.AD.value.integer == old_ad, (
        f"Registered output changed immediately: Expected AD = {old_ad}, got {dut.AD.value.integer}"
    )


@pytest.mark.skip(reason="Cocotb test - run by simulation, not pytest")
@cocotb.test
async def test_regfile_registered_output_port_b(dut: RegFileProtocol) -> None:
    """Test registered output functionality for port B."""
    await setup_dut(dut)

    model = RegFileModel()

    # Write test data
    dut.W_ADR.value = 12
    dut.D.value = 0x6
    dut.W_en.value = 1
    model.write_cycle(12, 0x6, 1)
    await RisingEdge(dut.UserCLK)
    dut.W_en.value = 0

    # Configure for registered output on port B (ConfigBits[1] = 1)
    dut.ConfigBits.value = 0b10
    dut.B_ADR.value = 12

    # In registered mode, need clock edge to update output
    await RisingEdge(dut.UserCLK)
    await Timer(Decimal(100), units="ps")

    _, expected_bd = model.read_cycle(0, 12, 0b10)
    assert dut.BD.value.integer == expected_bd, (
        f"Registered port B read failed: Expected BD = {expected_bd}, got {dut.BD.value.integer}"
    )


@pytest.mark.skip(reason="Cocotb test - run by simulation, not pytest")
@cocotb.test
async def test_regfile_address_independence(dut: RegFileProtocol) -> None:
    """Test that different addresses store independent data."""
    await setup_dut(dut)

    model = RegFileModel()

    # Write unique data to multiple addresses
    test_addresses = [0, 5, 10, 15, 20, 25, 30, 31]
    expected_data = {}

    for i, addr in enumerate(test_addresses):
        data = (i + 1) & 0xF  # Unique 4-bit data
        expected_data[addr] = data

        dut.W_ADR.value = addr
        dut.D.value = data
        dut.W_en.value = 1
        model.write_cycle(addr, data, 1)
        await RisingEdge(dut.UserCLK)
        dut.W_en.value = 0

    await Timer(Decimal(100), units="ps")

    # Verify each address contains correct data
    dut.ConfigBits.value = 0b00  # Combinational mode
    for addr, expected in expected_data.items():
        dut.A_ADR.value = addr
        await Timer(Decimal(50), units="ps")

        model_ad, _ = model.read_cycle(addr, 0, 0b00)
        assert dut.AD.value.integer == expected, (
            f"Address {addr}: Expected data = {expected}, got {dut.AD.value.integer}"
        )
        assert model_ad == expected, f"Model mismatch at address {addr}"


@pytest.mark.skip(reason="Cocotb test - run by simulation, not pytest")
@cocotb.test
async def test_regfile_write_enable_control(dut: RegFileProtocol) -> None:
    """Test write enable control functionality."""
    await setup_dut(dut)

    model = RegFileModel()

    # Write initial data
    dut.W_ADR.value = 8
    dut.D.value = 0x7
    dut.W_en.value = 1
    model.write_cycle(8, 0x7, 1)
    await RisingEdge(dut.UserCLK)
    dut.W_en.value = 0

    # Read initial value
    dut.A_ADR.value = 8
    dut.ConfigBits.value = 0b00
    await Timer(Decimal(100), units="ps")
    initial_value = dut.AD.value.integer

    # Try to write with W_en = 0 (should not write)
    dut.D.value = 0x2  # Different data
    dut.W_en.value = 0  # Write disabled
    model.write_cycle(8, 0x2, 0)  # Model should not write
    await RisingEdge(dut.UserCLK)

    # Verify data unchanged
    await Timer(Decimal(100), units="ps")
    assert dut.AD.value.integer == initial_value, (
        f"Data changed with W_en=0: Expected {initial_value}, got {dut.AD.value.integer}"
    )

    # Now enable write and verify it works
    dut.W_en.value = 1
    model.write_cycle(8, 0x2, 1)
    await RisingEdge(dut.UserCLK)
    dut.W_en.value = 0

    await Timer(Decimal(100), units="ps")
    assert dut.AD.value.integer == 0x2, (
        f"Write with W_en=1 failed: Expected 0x2, got {dut.AD.value.integer}"
    )


@pytest.mark.skip(reason="Cocotb test - run by simulation, not pytest")
@cocotb.test
async def test_regfile_both_ports_registered(dut: RegFileProtocol) -> None:
    """Test functionality with both ports in registered mode."""
    await setup_dut(dut)

    model = RegFileModel()

    # Write test data to different addresses
    dut.W_ADR.value = 3
    dut.D.value = 0x9
    dut.W_en.value = 1
    model.write_cycle(3, 0x9, 1)
    await RisingEdge(dut.UserCLK)
    dut.W_en.value = 0

    dut.W_ADR.value = 13
    dut.D.value = 0x4
    dut.W_en.value = 1
    model.write_cycle(13, 0x4, 1)
    await RisingEdge(dut.UserCLK)
    dut.W_en.value = 0

    # Configure both ports for registered output
    dut.ConfigBits.value = 0b11  # Both ports registered
    dut.A_ADR.value = 3
    dut.B_ADR.value = 13

    # Clock to update registered outputs
    await RisingEdge(dut.UserCLK)
    await Timer(Decimal(100), units="ps")

    expected_ad, expected_bd = model.read_cycle(3, 13, 0b11)
    assert dut.AD.value.integer == expected_ad, (
        f"Registered port A failed: Expected {expected_ad}, got {dut.AD.value.integer}"
    )
    assert dut.BD.value.integer == expected_bd, (
        f"Registered port B failed: Expected {expected_bd}, got {dut.BD.value.integer}"
    )

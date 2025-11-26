"""RTL behavior validation for MUX8LUT_frame_config_mux module using cocotb."""

from decimal import Decimal
from pathlib import Path
from random import randint
from typing import Protocol

import cocotb
from cocotb.handle import LogicObject
from cocotb.triggers import Timer

from tests.conftest import VERILOG_SOURCE_PATH, VHDL_SOURCE_PATH, CocotbRunner


class MUX8LUTProtocol(Protocol):
    """Protocol defining the MUX8LUT_frame_config_mux module interface."""

    # Inputs
    A: LogicObject  # MUX input A (handle)
    B: LogicObject  # MUX input B (handle)
    C: LogicObject  # MUX input C (handle)
    D: LogicObject  # MUX input D (handle)
    E: LogicObject  # MUX input E (handle)
    F: LogicObject  # MUX input F (handle)
    G: LogicObject  # MUX input G (handle)
    H: LogicObject  # MUX input H (handle)
    S: LogicObject  # [3:0] Select signals (handle)
    ConfigBits: LogicObject  # [NoConfigBits-1:0] Configuration bits (handle)
    UserCLK: LogicObject  # Clock (for setup compatibility) (handle)

    # Outputs
    M_AB: LogicObject  # MUX output AB (handle)
    M_AD: LogicObject  # MUX output AD (handle)
    M_AH: LogicObject  # MUX output AH (handle)
    M_EF: LogicObject  # MUX output EF (handle)


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
            VHDL_SOURCE_PATH / "Tile" / "LUT4AB" / "MUX8LUT_frame_config_mux.vhdl",
            VHDL_SOURCE_PATH / "Fabric" / "models_pack.vhdl",  # Include custom modules
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

    _A = 0
    _B = 0
    _C = 0
    _D = 0
    _E = 0
    _F = 0
    _G = 0
    _H = 0
    _S = 0  # 4-bit select
    _ConfigBits = 0  # 2-bit configuration

    @property
    def A(self) -> int:
        """Input A."""
        return self._A

    @A.setter
    def A(self, value: int) -> None:
        self._A = value & 1  # Ensure single bit

    @property
    def B(self) -> int:
        """Input B."""
        return self._B

    @B.setter
    def B(self, value: int) -> None:
        self._B = value & 1  # Ensure single bit

    @property
    def C(self) -> int:
        """Input C."""
        return self._C

    @C.setter
    def C(self, value: int) -> None:
        self._C = value & 1  # Ensure single bit

    @property
    def D(self) -> int:
        """Input D."""
        return self._D

    @D.setter
    def D(self, value: int) -> None:
        self._D = value & 1  # Ensure single bit

    @property
    def E(self) -> int:
        """Input E."""
        return self._E

    @E.setter
    def E(self, value: int) -> None:
        self._E = value & 1  # Ensure single bit

    @property
    def F(self) -> int:
        """Input F."""
        return self._F

    @F.setter
    def F(self, value: int) -> None:
        self._F = value & 1  # Ensure single bit

    @property
    def G(self) -> int:
        """Input G."""
        return self._G

    @G.setter
    def G(self, value: int) -> None:
        self._G = value & 1  # Ensure single bit

    @property
    def H(self) -> int:
        """Input H."""
        return self._H

    @H.setter
    def H(self, value: int) -> None:
        self._H = value & 1  # Ensure single bit

    @property
    def S(self) -> int:
        """4-bit select signal."""
        return self._S

    @S.setter
    def S(self, value: int) -> None:
        self._S = value & 0xF  # Ensure 4-bit value

    @property
    def ConfigBits(self) -> int:
        """2-bit configuration bits."""
        return self._ConfigBits

    @ConfigBits.setter
    def ConfigBits(self, value: int) -> None:
        self._ConfigBits = value & 0x3  # Ensure 2-bit value

    @classmethod
    def mux2(cls, A: int, B: int, S: int) -> int:
        return B if (S & 1) else A

    @property
    def _S0(self) -> int:
        return self.S & 1

    @property
    def _S1(self) -> int:
        return (self.S >> 1) & 1

    @property
    def _S2(self) -> int:
        return (self.S >> 2) & 1

    @property
    def _S3(self) -> int:
        return (self.S >> 3) & 1

    @property
    def _c0(self) -> int:
        return self.ConfigBits & 1

    @property
    def _c1(self) -> int:
        return (self.ConfigBits >> 1) & 1

    @property
    def _AB(self) -> int:
        return self.mux2(self.A, self.B, self._S0)

    @property
    def _CD(self) -> int:
        return self.mux2(self.C, self.D, self._sCD)

    @property
    def _EF(self) -> int:
        return self.mux2(self.E, self.F, self._sEF)

    @property
    def _GH(self) -> int:
        return self.mux2(self.G, self.H, self._sGH)

    @property
    def _sCD(self) -> int:
        return self.mux2(self._S1, self._S0, self._c0)

    @property
    def _sEF(self) -> int:
        return self.mux2(self._S2, self._S0, self._c1)

    @property
    def _sGH(self) -> int:
        return self.mux2(self._sEH, self._sEF, self._c0)

    @property
    def _sEH(self) -> int:
        return self.mux2(self._S3, self._S1, self._c1)

    @property
    def _AD(self) -> int:
        return self.mux2(self._AB, self._CD, self._S1)

    @property
    def _EH(self) -> int:
        return self.mux2(self._EF, self._GH, self._sEH)

    @property
    def _AH(self) -> int:
        return self.mux2(self._AD, self._EH, self._S3)

    @property
    def _EH_GH(self) -> int:
        return self.mux2(self._GH, self._EH, self._c0)

    @property
    def M_AB(self) -> int:
        return self._AB

    @property
    def M_AD(self) -> int:
        return self.mux2(self._CD, self._AD, self._c0)

    @property
    def M_AH(self) -> int:
        return self.mux2(self._EH_GH, self._AH, self._c1)

    @property
    def M_EF(self) -> int:
        return self._EF


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


@cocotb.test
async def cocotb_test_mux8lut_selection(dut: MUX8LUTProtocol) -> None:
    """Test basic MUX selection functionality with proper CocoTB timing."""
    dut.A.value = 0
    dut.B.value = 1
    dut.C.value = 0
    dut.D.value = 1
    dut.E.value = 0
    dut.F.value = 1
    dut.G.value = 0
    dut.H.value = 1
    dut.ConfigBits.value = 0  # c1=0, c0=0
    dut.S.value = 0  # Select input A
    await Timer(Decimal(20), units="ps")  # Allow propagation
    assert int(dut.M_AB.value) == 0, f"M_AB expected 0, got {int(dut.M_AB.value)}"
    assert int(dut.M_AD.value) == 0, f"M_AD expected 0, got {int(dut.M_AD.value)}"
    assert int(dut.M_AH.value) == 0, f"M_AH expected 0, got {int(dut.M_AH.value)}"
    assert int(dut.M_EF.value) == 0, f"M_EF expected 0, got {int(dut.M_EF.value)}"

    model = MUX8LUTModel()

    for s in range(16):  # 4-bit select supports 0-15
        for c in range(4):  # 2-bit config supports 0-3
            # Set inputs in both DUT and model
            dut.A.value = model.A = randint(0, 1)
            dut.B.value = model.B = randint(0, 1)
            dut.C.value = model.C = randint(0, 1)
            dut.D.value = model.D = randint(0, 1)
            dut.E.value = model.E = randint(0, 1)
            dut.F.value = model.F = randint(0, 1)
            dut.G.value = model.G = randint(0, 1)
            dut.H.value = model.H = randint(0, 1)

            # Set select and config in both DUT and model
            dut.S.value = model.S = s
            dut.ConfigBits.value = model.ConfigBits = c

            # CocoTB timing: Allow signal propagation through combinational logic
            await Timer(Decimal(20), units="ps")

            # Check all MUX outputs
            assert int(dut.M_AB.value) == model.M_AB, (
                f"Select {s}, Config {c}: M_AB expected {model.M_AB}, got {int(dut.M_AB.value)}"
            )
            assert int(dut.M_AD.value) == model.M_AD, (
                f"Select {s}, Config {c}: M_AD expected {model.M_AD}, got {int(dut.M_AD.value)}"
            )
            assert int(dut.M_AH.value) == model.M_AH, (
                f"Select {s}, Config {c}: M_AH expected {model.M_AH}, got {int(dut.M_AH.value)}"
            )
            assert int(dut.M_EF.value) == model.M_EF, (
                f"Select {s}, Config {c}: M_EF expected {model.M_EF}, got {int(dut.M_EF.value)}"
            )

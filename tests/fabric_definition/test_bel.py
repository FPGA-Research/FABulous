"""Unit tests for the immutable, Yosys-backed Bel model."""

from dataclasses import FrozenInstanceError
from pathlib import Path

import pytest

from fabulous.custom_exception import InvalidBelDefinition
from fabulous.fabric_definition.bel import Bel
from fabulous.fabric_definition.define import IO, HDLType
from fabulous.fabric_definition.port import BelPort
from tests.conftest import make_yosys_module


class TestBelConstruction:
    """Tests for building a Bel from a Yosys module."""

    def test_name_and_language_from_source(self) -> None:
        """The name comes from the source stem and the language from the suffix."""
        bel = Bel(
            src=Path("mymod.v"),
            prefix="LUT",
            module=make_yosys_module({"A": (IO.INPUT, 1), "Q": (IO.OUTPUT, 1)}),
            module_name="lut4",
        )
        assert bel.name == "mymod"
        assert bel.language == "verilog"
        assert bel.filetype == HDLType.VERILOG

    def test_vhdl_source_and_prefixed_ports(self) -> None:
        """A VHDL source yields the VHDL file type and prefixed port names."""
        bel = Bel(
            src=Path("ff.vhd"),
            prefix="FF",
            module=make_yosys_module({"D": (IO.INPUT, 1), "Q": (IO.OUTPUT, 1)}),
            module_name="ff",
        )
        assert bel.language == "vhdl"
        assert bel.filetype == HDLType.VHDL
        assert [p.name for p in bel.inputs] == ["FFD"]
        assert [p.name for p in bel.outputs] == ["FFQ"]

    def test_config_bits_sum(self) -> None:
        """config_bits is the sum of all config port widths."""
        bel = Bel(
            src=Path("mod.v"),
            prefix="",
            module=make_yosys_module({"A": (IO.INPUT, 1)}, config_bits=5),
            module_name="mod",
        )
        assert bel.config_bits == 5

    def test_constant_bel_true_without_inputs(self) -> None:
        """A Bel with no inputs is a constant BEL."""
        bel = Bel(
            src=Path("mod.v"),
            prefix="",
            module=make_yosys_module({"Q": (IO.OUTPUT, 1)}),
            module_name="mod",
        )
        assert bel.constant_bel is True

    def test_constant_bel_false_with_inputs(self) -> None:
        """A Bel with inputs is not a constant BEL."""
        bel = Bel(
            src=Path("mod.v"),
            prefix="",
            module=make_yosys_module({"A": (IO.INPUT, 1)}),
            module_name="mod",
        )
        assert bel.constant_bel is False

    def test_param_override_in_name(self) -> None:
        """Parameter overrides are appended to the BEL name."""
        bel = Bel(
            src=Path("mymod.v"),
            prefix="",
            module=make_yosys_module({"Q": (IO.OUTPUT, 1)}),
            module_name="mod",
            param_override={"WIDTH": "8", "DEPTH": "256"},
        )
        assert bel.name == "mymod_WIDTH_8__DEPTH_256"

    def test_unknown_file_suffix_raises(self) -> None:
        """An unsupported source file suffix is rejected at construction."""
        with pytest.raises(ValueError, match="Unknown file type"):
            Bel(
                src=Path("mod.txt"),
                prefix="",
                module=make_yosys_module({"Q": (IO.OUTPUT, 1)}),
                module_name="mod",
            )

    def test_find_port_by_name(self) -> None:
        """find_port_by_name returns the matching port and raises when absent."""
        bel = Bel(
            src=Path("mod.v"),
            prefix="",
            module=make_yosys_module({"A": (IO.INPUT, 1)}),
            module_name="mod",
        )
        assert bel.find_port_by_name("A").name == "A"
        with pytest.raises(ValueError, match="not found"):
            bel.find_port_by_name("does_not_exist")


class TestBelImmutability:
    """Tests for the frozen, cached nature of a Bel."""

    def test_frozen_rejects_assignment(self) -> None:
        """A Bel is frozen and rejects attribute assignment."""
        bel = Bel(
            src=Path("mod.v"),
            prefix="",
            module=make_yosys_module({"A": (IO.INPUT, 1)}),
            module_name="mod",
        )
        with pytest.raises(FrozenInstanceError):
            bel.z = 5

    def test_derived_collections_are_cached(self) -> None:
        """Repeated access returns the same cached collection object."""
        bel = Bel(
            src=Path("mod.v"),
            prefix="",
            module=make_yosys_module({"A": (IO.INPUT, 1)}),
            module_name="mod",
        )
        assert bel.inputs is bel.inputs


class TestBelPortValidation:
    """Tests for port-validity checks raised during classification."""

    def test_external_inout_rejected(self) -> None:
        """A bidirectional external port is rejected on first port access."""
        bel = Bel(
            src=Path("mod.v"),
            prefix="",
            module=make_yosys_module(
                {"P": (IO.INOUT, 1)},
                port_attributes={"P": {"EXTERNAL": 1}},
            ),
            module_name="mod",
        )
        with pytest.raises(InvalidBelDefinition, match="External INOUT"):
            _ = bel.external_inputs


class TestBelClockPort:
    """Tests for the user clock port on a Bel."""

    def test_user_clk_builds_clock_port(self) -> None:
        """A UserCLK port surfaces as a clock BelPort and sets with_user_clock."""
        bel = Bel(
            src=Path("mod.v"),
            prefix="",
            module=make_yosys_module({"A": (IO.INPUT, 1)}, user_clk=True),
            module_name="mod",
        )
        assert bel.with_user_clock is True
        assert isinstance(bel.user_clk_port, BelPort)
        assert bel.user_clk_port.name == "UserCLK"
        assert bel.user_clk_port.is_clock is True
        assert bel.user_clk_port.is_global is False
        assert bel.user_clk_port.net == "UserCLK"
        assert bel.clock_ports == [bel.user_clk_port]

    def test_no_user_clk_leaves_none(self) -> None:
        """Without a UserCLK port the clock collection is empty."""
        bel = Bel(
            src=Path("mod.v"),
            prefix="",
            module=make_yosys_module({"A": (IO.INPUT, 1)}),
            module_name="mod",
        )
        assert bel.with_user_clock is False
        assert bel.user_clk_port is None
        assert bel.clock_ports == []

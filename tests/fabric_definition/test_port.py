"""Unit tests for the Port class hierarchy introduced by the bel/port migration."""

import pytest

from fabulous.fabric_definition.define import (
    IO,
    ClockEdge,
    FeatureType,
    FeatureValue,
    Side,
)
from fabulous.fabric_definition.port import (
    BelPort,
    ClockPort,
    ConfigPort,
    Port,
    SharedPort,
    TilePort,
)


class TestPort:
    """Tests for the base Port class."""

    def test_construct_valid(self) -> None:
        """A valid Port exposes its name, direction and width."""
        port = Port(name="A", io_direction=IO.INPUT, width=4)
        assert port.name == "A"
        assert port.io_direction == IO.INPUT
        assert port.width == 4

    def test_zero_width_raises(self) -> None:
        """A non-positive width is rejected."""
        with pytest.raises(ValueError, match="Width must be greater than 0"):
            Port(name="A", io_direction=IO.INPUT, width=0)

    def test_bad_io_direction_raises(self) -> None:
        """A non-IO io_direction is rejected."""
        with pytest.raises(TypeError):
            Port(name="A", io_direction="INPUT", width=1)

    def test_non_string_name_raises(self) -> None:
        """A non-string name is rejected."""
        with pytest.raises(TypeError):
            Port(name=123, io_direction=IO.INPUT, width=1)

    def test_expand_single_bit(self) -> None:
        """A width-1 port expands to a single bare name."""
        assert Port(name="x", io_direction=IO.INPUT, width=1).expand() == ["x"]

    def test_expand_multi_bit(self) -> None:
        """A multi-bit port expands to indexed names."""
        assert Port(name="y", io_direction=IO.OUTPUT, width=3).expand() == [
            "y[0]",
            "y[1]",
            "y[2]",
        ]

    def test_equality_is_identity(self) -> None:
        """Two distinct ports with equal data are not equal; identity holds."""
        p1 = Port(name="A", io_direction=IO.INPUT, width=1)
        p2 = Port(name="A", io_direction=IO.INPUT, width=1)
        assert p1 != p2
        assert p1 == p1
        assert hash(p1) == id(p1)

    def test_serialize(self) -> None:
        """Serialization contains name, io_direction value and width."""
        port = Port(name="A", io_direction=IO.OUTPUT, width=2)
        assert port.serialize() == {
            "name": "A",
            "io_direction": IO.OUTPUT.value,
            "width": 2,
        }


class TestBelPort:
    """Tests for BelPort."""

    def test_name_prepends_prefix(self) -> None:
        """The BelPort name is the prefix concatenated with the base name."""
        port = BelPort(name="sig", io_direction=IO.INPUT, width=1, prefix="lut_")
        assert port.name == "lut_sig"

    def test_external_and_control_flags(self) -> None:
        """External and control flags are exposed verbatim."""
        port = BelPort(
            name="io",
            io_direction=IO.OUTPUT,
            width=1,
            prefix="",
            external=True,
            control=False,
        )
        assert port.external is True
        assert port.control is False

    def test_expand_uses_prefixed_name(self) -> None:
        """Expansion uses the prefixed name."""
        port = BelPort(name="sig", io_direction=IO.INPUT, width=1, prefix="lut_")
        assert port.expand() == ["lut_sig"]

    def test_serialize_includes_belport_fields(self) -> None:
        """Serialization adds prefix, external and control."""
        port = BelPort(name="sig", io_direction=IO.INPUT, width=1, prefix="lut_")
        data = port.serialize()
        assert data["name"] == "lut_sig"
        assert data["prefix"] == "lut_"
        assert data["external"] is False
        assert data["control"] is False


class TestConfigPort:
    """Tests for ConfigPort."""

    def test_defaults(self) -> None:
        """Features default to empty and feature_type to ENUMERATE."""
        port = ConfigPort(name="cfg", io_direction=IO.INPUT, width=8)
        assert port.features == []
        assert port.feature_type == FeatureType.ENUMERATE

    def test_custom_features(self) -> None:
        """Custom features are stored as given."""
        features = [FeatureValue("INIT", 0), FeatureValue("MODE", None)]
        port = ConfigPort(
            name="cfg",
            io_direction=IO.INPUT,
            width=2,
            features=features,
        )
        assert port.features == features


class TestSharedPort:
    """Tests for SharedPort."""

    def test_shared_with(self) -> None:
        """The shared_with target is exposed."""
        port = SharedPort(
            name="clk", io_direction=IO.INPUT, width=1, shared_with="global_clk"
        )
        assert port.shared_with == "global_clk"

    def test_share_expand_single_bit(self) -> None:
        """A width-1 shared port expands to the bare shared_with name."""
        port = SharedPort(
            name="clk", io_direction=IO.INPUT, width=1, shared_with="global_clk"
        )
        assert port.share_expand() == ["global_clk"]

    def test_share_expand_multi_bit(self) -> None:
        """A multi-bit shared port expands to indexed shared_with names."""
        port = SharedPort(
            name="bus", io_direction=IO.INPUT, width=3, shared_with="shared_bus"
        )
        assert port.share_expand() == [
            "shared_bus[0]",
            "shared_bus[1]",
            "shared_bus[2]",
        ]


class TestTilePort:
    """Tests for TilePort ordering and construction."""

    def test_construct_with_side(self) -> None:
        """A TilePort exposes its side of the tile."""
        port = TilePort(
            name="N1", io_direction=IO.OUTPUT, width=1, side_of_tile=Side.NORTH
        )
        assert port.side_of_tile == Side.NORTH

    def test_ordering_by_side(self) -> None:
        """Ports are ordered by tile side (north before east)."""
        north = TilePort(
            name="n", io_direction=IO.OUTPUT, width=1, side_of_tile=Side.NORTH
        )
        east = TilePort(
            name="e", io_direction=IO.INPUT, width=1, side_of_tile=Side.EAST
        )
        assert north < east
        assert east > north

    def test_ordering_by_io_within_side(self) -> None:
        """Within a side, outputs are ordered before inputs."""
        out = TilePort(
            name="o", io_direction=IO.OUTPUT, width=1, side_of_tile=Side.NORTH
        )
        inp = TilePort(
            name="i", io_direction=IO.INPUT, width=1, side_of_tile=Side.NORTH
        )
        assert out < inp
        assert out <= inp
        assert inp >= out


class TestClockPort:
    """Tests for ClockPort."""

    def test_defaults_describe_user_clock(self) -> None:
        """A default ClockPort is the global rising-edge 1-bit UserCLK input."""
        port = ClockPort()
        assert port.name == "UserCLK"
        assert port.io_direction == IO.INPUT
        assert port.width == 1
        assert port.edge == ClockEdge.RISING
        assert port.domain == ""
        assert port.is_global is True

    def test_is_a_port(self) -> None:
        """A ClockPort is a Port and satisfies isinstance checks."""
        assert isinstance(ClockPort(), Port)

    def test_custom_fields(self) -> None:
        """Custom clock fields are stored as given."""
        port = ClockPort(
            name="clk2",
            width=1,
            edge=ClockEdge.FALLING,
            domain="dsp",
            is_global=False,
        )
        assert port.name == "clk2"
        assert port.edge == ClockEdge.FALLING
        assert port.domain == "dsp"
        assert port.is_global is False

    def test_bad_edge_raises(self) -> None:
        """A non-ClockEdge edge is rejected."""
        with pytest.raises(TypeError, match="edge must be a ClockEdge"):
            ClockPort(edge="rising")

    def test_bad_is_global_raises(self) -> None:
        """A non-bool is_global is rejected."""
        with pytest.raises(TypeError, match="is_global must be a bool"):
            ClockPort(is_global="yes")

    def test_serialize_includes_clock_fields(self) -> None:
        """Serialization adds edge, domain and is_global."""
        data = ClockPort(edge=ClockEdge.BOTH, domain="core").serialize()
        assert data == {
            "name": "UserCLK",
            "io_direction": IO.INPUT.value,
            "width": 1,
            "edge": ClockEdge.BOTH.value,
            "domain": "core",
            "is_global": True,
        }

    def test_serialize_round_trip(self) -> None:
        """A ClockPort survives a serialize / from_serialized round-trip."""
        port = ClockPort(
            name="clk_fast",
            io_direction=IO.INPUT,
            width=1,
            edge=ClockEdge.FALLING,
            domain="fast",
            is_global=False,
        )
        restored = ClockPort.from_serialized(port.serialize())
        assert restored.serialize() == port.serialize()

"""Unit tests for the Port class hierarchy introduced by the bel/port migration."""

import pytest

from fabulous.fabric_definition.define import (
    IO,
    FeatureType,
    FeatureValue,
    Side,
)
from fabulous.fabric_definition.port import (
    BelPort,
    ConfigPort,
    Port,
    SharedPort,
    SlicedPort,
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

    @pytest.mark.parametrize(
        ("io_direction", "is_input", "is_output", "is_inout"),
        [
            (IO.INPUT, True, False, False),
            (IO.OUTPUT, False, True, False),
            (IO.INOUT, False, False, True),
        ],
    )
    def test_direction_predicates(
        self, io_direction: IO, is_input: bool, is_output: bool, is_inout: bool
    ) -> None:
        """Exactly one direction predicate holds for each IO direction."""
        port = Port(name="A", io_direction=io_direction, width=1)
        assert port.is_input is is_input
        assert port.is_output is is_output
        assert port.is_inout is is_inout

    @pytest.mark.parametrize(
        ("name", "expected"), [("NULL", True), ("N1BEG", False), ("null", False)]
    )
    def test_name_is_null(self, name: str, expected: bool) -> None:
        """Only the exact NULL placeholder name marks an unconnected wire end."""
        port = Port(name=name, io_direction=IO.INPUT, width=1)
        assert port.name_is_null is expected

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
        """Serialization contains name, io_direction value, width and net info."""
        port = Port(name="A", io_direction=IO.OUTPUT, width=2)
        assert port.serialize() == {
            "name": "A",
            "io_direction": IO.OUTPUT.value,
            "width": 2,
            "is_clock": False,
            "is_global": False,
            "net": "",
        }


class TestPortClockFields:
    """Tests for the clock and net metadata carried by every Port."""

    def test_defaults_are_a_local_non_clock_port(self) -> None:
        """A Port is a non-clock, non-global port on the global net by default."""
        port = Port(name="A", io_direction=IO.INPUT, width=1)
        assert port.is_clock is False
        assert port.is_global is False
        assert port.net == ""

    def test_user_clock_fields(self) -> None:
        """The global user clock is described by the base Port fields."""
        port = Port(
            name="UserCLK",
            io_direction=IO.INPUT,
            width=1,
            is_clock=True,
            is_global=True,
        )
        assert port.is_clock is True
        assert port.is_global is True
        assert port.net == ""

    def test_local_clock_on_a_named_net(self) -> None:
        """A locally generated clock names the net it drives."""
        port = Port(
            name="clk2",
            io_direction=IO.INPUT,
            width=1,
            is_clock=True,
            net="dsp",
        )
        assert port.is_clock is True
        assert port.is_global is False
        assert port.net == "dsp"

    @pytest.mark.parametrize("field", ["is_clock", "is_global"])
    def test_non_bool_flag_raises(self, field: str) -> None:
        """A non-bool clock flag is rejected."""
        with pytest.raises(TypeError, match=f"{field} must be a bool"):
            Port(name="A", io_direction=IO.INPUT, width=1, **{field: "yes"})

    def test_serialize_includes_clock_fields(self) -> None:
        """Serialization carries is_clock, is_global and net."""
        port = Port(
            name="clk_fast",
            io_direction=IO.INPUT,
            width=1,
            is_clock=True,
            net="fast",
        )
        assert port.serialize() == {
            "name": "clk_fast",
            "io_direction": IO.INPUT.value,
            "width": 1,
            "is_clock": True,
            "is_global": False,
            "net": "fast",
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

    def test_clock_fields_reach_the_base_port(self) -> None:
        """Clock metadata passed to a BelPort is stored on the base Port."""
        port = BelPort(
            name="UserCLK",
            io_direction=IO.INPUT,
            width=1,
            is_clock=True,
            net="UserCLK",
        )
        assert port.is_clock is True
        assert port.is_global is False
        assert port.net == "UserCLK"

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


class TestSlicedPort:
    """Tests for SlicedPort's inclusive high/low bit range."""

    def test_width_spans_high_to_low_inclusive(self) -> None:
        """The slice width counts both endpoints."""
        original = BelPort(name="bus", io_direction=IO.OUTPUT, width=8)
        assert SlicedPort(original, high=5, low=2).width == 4
        assert SlicedPort(original, high=3, low=3).width == 1

    def test_expand_indexes_the_original_port(self) -> None:
        """Expansion names the original port's bits from low up to high."""
        original = BelPort(name="bus", io_direction=IO.OUTPUT, width=8)
        assert SlicedPort(original, high=3, low=1).expand() == [
            "bus[1]",
            "bus[2]",
            "bus[3]",
        ]

    def test_expand_of_nested_slice_indexes_the_parent(self) -> None:
        """A slice of a slice selects into the parent's expansion."""
        original = BelPort(name="bus", io_direction=IO.OUTPUT, width=8)
        parent = SlicedPort(original, high=5, low=2)
        assert SlicedPort(parent, high=2, low=1).expand() == ["bus[3]", "bus[4]"]

    def test_serialize_carries_high_and_low(self) -> None:
        """Serialization records the endpoints separately."""
        original = BelPort(name="bus", io_direction=IO.OUTPUT, width=8)
        data = SlicedPort(original, high=6, low=4).serialize()
        assert data["high"] == 6
        assert data["low"] == 4
        assert data["original_port"] == "bus"

    @pytest.mark.parametrize(
        ("high", "low", "match"),
        [
            (3, -1, "must not be negative"),
            (2, 5, "high downto low"),
            (8, 0, "outside the width"),
            (-1, -1, "must not be negative"),
        ],
    )
    def test_invalid_range_raises(self, high: int, low: int, match: str) -> None:
        """A slice outside the original port or written low-to-high is rejected."""
        original = BelPort(name="bus", io_direction=IO.OUTPUT, width=8)
        with pytest.raises(ValueError, match=match):
            SlicedPort(original, high=high, low=low)

    def test_endpoints_are_required(self) -> None:
        """The range must be given explicitly; there is no default slice."""
        original = BelPort(name="bus", io_direction=IO.OUTPUT, width=8)
        with pytest.raises(TypeError):
            SlicedPort(original)  # type: ignore[call-arg]


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

    def test_comparison_with_non_tileport_raises(self) -> None:
        """Ordering is only defined against another TilePort."""
        port = TilePort(
            name="n", io_direction=IO.OUTPUT, width=1, side_of_tile=Side.NORTH
        )
        with pytest.raises(TypeError, match="Cannot compare"):
            port < 1  # noqa: B015

    def test_tile_back_reference_defaults_to_none(self) -> None:
        """An unattached port has no owning tile."""
        port = TilePort(
            name="n", io_direction=IO.OUTPUT, width=1, side_of_tile=Side.NORTH
        )
        assert port.tile is None

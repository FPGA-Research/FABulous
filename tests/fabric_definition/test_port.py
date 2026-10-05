"""Unit tests for the Port class hierarchy introduced by the bel/port migration."""

import random

import pytest

from fabulous.fabric_definition.define import (
    IO,
    Direction,
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

    def test_zero_width_raises(self) -> None:
        """A non-positive width is rejected."""
        with pytest.raises(ValueError, match="Width must be greater than 0"):
            Port(name="A", io_direction=IO.INPUT, width=0)

    @pytest.mark.parametrize(
        ("overrides", "match"),
        [
            pytest.param(
                {"io_direction": "INPUT"},
                "io_direction must be an instance of IO",
                id="io_direction",
            ),
            pytest.param({"name": 123}, "name must be a string", id="name"),
            pytest.param({"is_clock": "yes"}, "is_clock must be a bool", id="is_clock"),
            pytest.param(
                {"is_global": "yes"}, "is_global must be a bool", id="is_global"
            ),
        ],
    )
    def test_wrong_type_raises(self, overrides: dict, match: str) -> None:
        """Each constructor argument of the wrong type is named in the error."""
        kwargs = {"name": "A", "io_direction": IO.INPUT, "width": 1} | overrides
        with pytest.raises(TypeError, match=match):
            Port(**kwargs)

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

    @pytest.mark.parametrize(
        ("kwargs", "expected"),
        [
            pytest.param(
                {"name": "A", "io_direction": IO.OUTPUT, "width": 2},
                {
                    "name": "A",
                    "io_direction": "OUTPUT",
                    "width": 2,
                    "is_clock": False,
                    "is_global": False,
                    "net": "",
                },
                id="local_non_clock_default",
            ),
            pytest.param(
                {
                    "name": "UserCLK",
                    "io_direction": IO.INPUT,
                    "width": 1,
                    "is_clock": True,
                    "is_global": True,
                },
                {
                    "name": "UserCLK",
                    "io_direction": "INPUT",
                    "width": 1,
                    "is_clock": True,
                    "is_global": True,
                    "net": "",
                },
                id="global_user_clock",
            ),
            pytest.param(
                {
                    "name": "clk_fast",
                    "io_direction": IO.INPUT,
                    "width": 1,
                    "is_clock": True,
                    "net": "fast",
                },
                {
                    "name": "clk_fast",
                    "io_direction": "INPUT",
                    "width": 1,
                    "is_clock": True,
                    "is_global": False,
                    "net": "fast",
                },
                id="local_clock_on_named_net",
            ),
        ],
    )
    def test_serialize(self, kwargs: dict, expected: dict) -> None:
        """Serialization carries the name, direction, width and clock/net metadata."""
        assert Port(**kwargs).serialize() == expected


class TestBelPort:
    """Tests for BelPort."""

    def test_name_prepends_prefix(self) -> None:
        """The BelPort name is the prefix concatenated with the base name."""
        port = BelPort(name="sig", io_direction=IO.INPUT, width=1, prefix="lut_")
        assert port.name == "lut_sig"

    def test_expand_uses_prefixed_name(self) -> None:
        """Expansion uses the prefixed name."""
        port = BelPort(name="sig", io_direction=IO.INPUT, width=1, prefix="lut_")
        assert port.expand() == ["lut_sig"]

    @pytest.mark.parametrize(
        ("kwargs", "expected"),
        [
            pytest.param(
                {"name": "sig", "io_direction": IO.INPUT, "width": 1, "prefix": "lut_"},
                {
                    "name": "lut_sig",
                    "io_direction": "INPUT",
                    "width": 1,
                    "is_clock": False,
                    "is_global": False,
                    "net": "",
                    "prefix": "lut_",
                    "external": False,
                    "control": False,
                },
                id="defaults",
            ),
            pytest.param(
                {
                    "name": "io",
                    "io_direction": IO.OUTPUT,
                    "width": 2,
                    "external": True,
                    "control": False,
                },
                {
                    "name": "io",
                    "io_direction": "OUTPUT",
                    "width": 2,
                    "is_clock": False,
                    "is_global": False,
                    "net": "",
                    "prefix": "",
                    "external": True,
                    "control": False,
                },
                id="external",
            ),
            pytest.param(
                {
                    "name": "en",
                    "io_direction": IO.INPUT,
                    "width": 1,
                    "external": False,
                    "control": True,
                },
                {
                    "name": "en",
                    "io_direction": "INPUT",
                    "width": 1,
                    "is_clock": False,
                    "is_global": False,
                    "net": "",
                    "prefix": "",
                    "external": False,
                    "control": True,
                },
                id="control",
            ),
            pytest.param(
                {
                    "name": "UserCLK",
                    "io_direction": IO.INPUT,
                    "width": 1,
                    "is_clock": True,
                    "net": "UserCLK",
                },
                {
                    "name": "UserCLK",
                    "io_direction": "INPUT",
                    "width": 1,
                    "is_clock": True,
                    "is_global": False,
                    "net": "UserCLK",
                    "prefix": "",
                    "external": False,
                    "control": False,
                },
                id="clock_fields_reach_base_port",
            ),
        ],
    )
    def test_serialize(self, kwargs: dict, expected: dict) -> None:
        """Serialization adds prefix, external and control to the base fields."""
        assert BelPort(**kwargs).serialize() == expected


class TestConfigPort:
    """Tests for ConfigPort."""

    @pytest.mark.parametrize(
        ("kwargs", "expected_extra"),
        [
            pytest.param(
                {},
                {"features": [], "feature_type": "ENUMERATE"},
                id="defaults",
            ),
            pytest.param(
                {
                    "features": [FeatureValue("INIT", 0), FeatureValue("MODE", None)],
                    "feature_type": FeatureType.INIT,
                },
                {
                    "features": [FeatureValue("INIT", 0), FeatureValue("MODE", None)],
                    "feature_type": "INIT",
                },
                id="custom_features",
            ),
        ],
    )
    def test_serialize(self, kwargs: dict, expected_extra: dict) -> None:
        """Serialization adds the features and the feature encoding."""
        port = ConfigPort(name="cfg", io_direction=IO.INPUT, width=2, **kwargs)
        assert (
            port.serialize()
            == {
                "name": "cfg",
                "io_direction": "INPUT",
                "width": 2,
                "is_clock": False,
                "is_global": False,
                "net": "",
            }
            | expected_extra
        )


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

    def test_serialize(self) -> None:
        """Serialization carries the original's name and direction plus the range."""
        original = BelPort(name="bus", io_direction=IO.OUTPUT, width=8)
        assert SlicedPort(original, high=6, low=4).serialize() == {
            "name": "bus",
            "io_direction": "OUTPUT",
            "width": 3,
            "is_clock": False,
            "is_global": False,
            "net": "",
            "high": 6,
            "low": 4,
            "original_port": "bus",
        }

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

    def test_serialize(self) -> None:
        """An unattached port serializes its side, wire fields and no owning tile."""
        port = TilePort(
            name="N2BEG",
            io_direction=IO.OUTPUT,
            width=4,
            side_of_tile=Side.NORTH,
            wire_direction=Direction.NORTH,
            source_name="N2BEG",
            x_offset=1,
            y_offset=-2,
            destination_name="N2END",
            wire_count=2,
        )
        assert port.serialize() == {
            "name": "N2BEG",
            "io_direction": "OUTPUT",
            "width": 4,
            "is_clock": False,
            "is_global": False,
            "net": "",
            "side_of_tile": "N",
            "term": False,
            "tile": None,
            "wire_direction": "NORTH",
            "source_name": "N2BEG",
            "x_offset": 1,
            "y_offset": -2,
            "destination_name": "N2END",
            "wire_count": 2,
        }

    def test_sort_orders_by_side_then_io(self) -> None:
        """Sorting follows [N, E, S, W, ANY] by side, then [out, in, inout]."""
        sides = [Side.NORTH, Side.EAST, Side.SOUTH, Side.WEST, Side.ANY]
        ios = [IO.OUTPUT, IO.INPUT, IO.INOUT]
        ports = [
            TilePort(name=f"{s}_{io.value}", io_direction=io, width=1, side_of_tile=s)
            for s in sides
            for io in ios
        ]
        shuffled = ports.copy()
        random.Random(0).shuffle(shuffled)

        assert [(p.side_of_tile, p.io_direction) for p in sorted(shuffled)] == [
            (s, io) for s in sides for io in ios
        ]

    def test_comparison_with_non_tileport_raises(self) -> None:
        """Ordering is only defined against another TilePort."""
        port = TilePort(
            name="n", io_direction=IO.OUTPUT, width=1, side_of_tile=Side.NORTH
        )
        with pytest.raises(TypeError, match="Cannot compare"):
            port < 1  # noqa: B015

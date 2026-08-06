"""Tests for the ODB antenna pre-check: span to margin, and net selection.

The measurement itself is OpenROAD's, so what is worth testing here is the
translation around it -- that a span becomes the right scaled limit, that a
declared wire name finds its bus bits, and that the sinks handed to the diode
step are gates rather than the diodes already sitting on the net.
"""

import pytest

from fabulous.fabric_generator.gds_generator.script.odb_antenna_precheck import (
    base_name,
    gate_pins,
    margin_for_span,
    nets_to_check,
    routing_level_names,
)


class FakeMTerm:
    """Mock master terminal, which knows whether the LEF gives it a gate area."""

    def __init__(self, name: str, has_antenna_model: bool) -> None:
        self._name = name
        self._has_antenna_model = has_antenna_model

    def getName(self) -> str:  # noqa: N802, D102
        return self._name

    def hasDefaultAntennaModel(self) -> bool:  # noqa: N802, D102
        return self._has_antenna_model


class FakeInst:
    """Mock instance."""

    def __init__(self, name: str) -> None:
        self._name = name

    def getName(self) -> str:  # noqa: N802, D102
        return self._name


class FakeITerm:
    """Mock instance terminal."""

    def __init__(self, inst: str, mterm: FakeMTerm, io_type: str) -> None:
        self._inst = FakeInst(inst)
        self._mterm = mterm
        self._io_type = io_type

    def getInst(self) -> FakeInst:  # noqa: N802, D102
        return self._inst

    def getMTerm(self) -> FakeMTerm:  # noqa: N802, D102
        return self._mterm

    def getIoType(self) -> str:  # noqa: N802, D102
        return self._io_type


class FakeNet:
    """Mock net."""

    def __init__(self, name: str, iterms: list[FakeITerm] | None = None) -> None:
        self._name = name
        self._iterms = iterms or []

    def getName(self) -> str:  # noqa: N802, D102
        return self._name

    def getITerms(self) -> list[FakeITerm]:  # noqa: N802, D102
        return self._iterms


class FakeBlock:
    """Mock block holding a fixed set of nets."""

    def __init__(self, nets: list[FakeNet]) -> None:
        self._nets = nets

    def getNets(self) -> list[FakeNet]:  # noqa: N802, D102
        return self._nets


class FakeLayer:
    """Mock technology layer."""

    def __init__(self, name: str, layer_type: str, level: int) -> None:
        self._name = name
        self._type = layer_type
        self._level = level

    def getName(self) -> str:  # noqa: N802, D102
        return self._name

    def getType(self) -> str:  # noqa: N802, D102
        return self._type

    def getRoutingLevel(self) -> int:  # noqa: N802, D102
        return self._level


class FakeTech:
    """Mock technology."""

    def __init__(self, layers: list[FakeLayer]) -> None:
        self._layers = layers

    def getLayers(self) -> list[FakeLayer]:  # noqa: N802, D102
        return self._layers


@pytest.mark.parametrize(
    ("span", "expected"),
    [(1, 0.0), (2, 50.0), (4, 75.0), (10, 90.0)],
)
def test_margin_for_span_scales_the_limit_by_the_span(
    span: int, expected: float
) -> None:
    """A margin of `100 * (1 - 1/span)` is what divides the limit by the span."""
    assert margin_for_span(span) == pytest.approx(expected)


@pytest.mark.parametrize("span", [1, 2, 3, 4, 10, 37])
def test_the_margin_recovers_the_span_exactly(span: int) -> None:
    """The whole method rests on this: OpenROAD scales limits by `1 - margin/100`."""
    scaled = 1.0 - margin_for_span(span) / 100.0

    assert 1.0 / scaled == pytest.approx(span), "the scaled limit must be limit/span"


def test_a_span_below_one_is_an_error() -> None:
    """A wire cannot travel less than the tile it is in."""
    with pytest.raises(ValueError, match="at least 1"):
        margin_for_span(0)


@pytest.mark.parametrize(
    ("net_name", "expected"),
    [
        ("FrameData[12]", "FrameData"),
        ("N10BEG", "N10BEG"),
        ("\\FrameStrobe[3]", "FrameStrobe"),
        ("top/inner/E4BEG[0]", "E4BEG"),
    ],
)
def test_base_name_strips_the_bus_index(net_name: str, expected: str) -> None:
    """A declared wire name covers every bit of its bus."""
    assert base_name(net_name) == expected


def test_nets_to_check_matches_bus_bits_against_the_declared_wire() -> None:
    """The fabric declares `FrameData`; the layout carries `FrameData[n]`."""
    block = FakeBlock(
        [FakeNet("FrameData[0]"), FakeNet("FrameData[7]"), FakeNet("N10BEG[3]")]
    )

    matched = nets_to_check(block, {"FrameData": 4, "N10BEG": 10})

    assert [(net.getName(), span) for net, span in matched] == [
        ("FrameData[0]", 4),
        ("FrameData[7]", 4),
        ("N10BEG[3]", 10),
    ]


def test_a_tile_local_net_is_not_checked() -> None:
    """At span 1 this predicts nothing `OpenROAD.CheckAntennas` has not reported."""
    block = FakeBlock(
        [FakeNet("local_thing"), FakeNet("N1BEG[0]"), FakeNet("N4BEG[0]")]
    )

    matched = nets_to_check(block, {"N1BEG": 1, "N4BEG": 4})

    assert [net.getName() for net, _ in matched] == ["N4BEG[0]"]


def test_gate_pins_name_the_sinks_a_diode_would_protect() -> None:
    """Only inputs the LEF gives a gate area are at risk from the antenna."""
    net = FakeNet(
        "N10BEG[3]",
        [
            FakeITerm("_013_", FakeMTerm("I", has_antenna_model=True), "INPUT"),
            FakeITerm("_014_", FakeMTerm("Y", has_antenna_model=True), "OUTPUT"),
        ],
    )

    assert gate_pins(net) == ["_013_/I"]


def test_a_diode_already_on_the_net_is_not_itself_a_target() -> None:
    """A diode declares diffusion area, not gate area, so it is not a victim."""
    net = FakeNet(
        "N10BEG[3]",
        [
            FakeITerm(
                "ANTENNA__013__I", FakeMTerm("I", has_antenna_model=False), "INPUT"
            ),
            FakeITerm("_013_", FakeMTerm("I", has_antenna_model=True), "INPUT"),
        ],
    )

    assert gate_pins(net) == ["_013_/I"]


def test_routing_level_names_skip_the_cut_layers() -> None:
    """A violation reports a routing level, which only routing layers carry."""
    tech = FakeTech(
        [
            FakeLayer("Metal1", "ROUTING", 1),
            FakeLayer("Via1", "CUT", 0),
            FakeLayer("Metal2", "ROUTING", 2),
        ]
    )

    assert routing_level_names(tech) == {1: "Metal1", 2: "Metal2"}

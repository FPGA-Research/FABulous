"""Tests for the nearest-port search of the synthesised timing model."""

import networkx as nx
import pytest
from pytest_mock import MockerFixture

from fabulous.fabric_cad.timing_model.hdlnx.hdlnx_timing_model import (
    HdlnxTimingModel,
)


def make_model(edges: list[tuple[str, str]]) -> HdlnxTimingModel:
    """Build a model over a bare timing graph, without running EDA tools."""
    model = HdlnxTimingModel.__new__(HdlnxTimingModel)
    model.graph = nx.DiGraph(edges)
    model.reverse_graph = model.graph.reverse(copy=True)
    model.input_ports = ["IN1", "IN2"]
    model.output_ports = ["OUT1", "OUT2"]
    return model


def test_nearest_port_from_pin_rejects_invalid_num_ports() -> None:
    with pytest.raises(ValueError, match="num_ports must be at least 1"):
        make_model([]).nearest_port_from_pin("X", num_ports=0)


@pytest.mark.parametrize(
    ("target", "expected"), [("OUT1", ["OUT1"]), (None, [])], ids=["found", "none"]
)
def test_nearest_port_from_pin_single_port_uses_the_sentinel_search(
    mocker: MockerFixture, target: str | None, expected: list[str]
) -> None:
    model = make_model([])
    mocker.patch.object(
        model, "path_to_nearest_target_sentinel", return_value=(["PIN"], target)
    )
    assert model.nearest_port_from_pin("PIN", num_ports=1) == expected


@pytest.mark.parametrize(
    ("edges", "reverse", "expected"),
    [
        pytest.param(
            [("PIN", "N1"), ("N1", "OUT1"), ("PIN", "N2"), ("N2", "OUT2")],
            False,
            ["OUT1", "OUT2"],
            id="forward",
        ),
        pytest.param(
            [("N1", "PIN"), ("IN1", "N1"), ("N2", "PIN"), ("IN2", "N2")],
            True,
            ["IN1", "IN2"],
            id="reverse",
        ),
        pytest.param([("PIN", "N1")], False, [], id="no-ports"),
    ],
)
def test_nearest_port_from_pin_multiple_ports(
    edges: list[tuple[str, str]], reverse: bool, expected: list[str]
) -> None:
    model = make_model(edges)
    assert model.nearest_port_from_pin("PIN", reverse=reverse, num_ports=2) == expected


def test_nearest_ports_from_pins_maps_each_net_from_its_first_pin() -> None:
    model = make_model([("p1", "OUT1"), ("p1", "N"), ("N", "OUT2"), ("p2", "OUT2")])

    mapping, flat = model.nearest_ports_from_pins(
        {"N1": ["p1", "p2"], "N2": ["p2"], "N3": []}, num_ports=2
    )

    assert mapping == {"N1": ["OUT1", "OUT2"], "N2": ["OUT2"]}
    assert flat == ["OUT1", "OUT2"]

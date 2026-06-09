"""Tests for NetlistTimingModel's timing-graph queries.

Only the graph-based queries live here (nearest-port search over the timing
graph). The structural netlist navigation is covered separately in
`tests/utils_test/test_yosys_navigator.py`; this fixture stubs `.netlist` and
the port lists so the graph methods can be exercised in isolation.
"""

from types import SimpleNamespace

import networkx as nx
import pytest

from fabulous.routing_model.netlist_timing_model import NetlistTimingModel


@pytest.fixture
def ntm() -> NetlistTimingModel:
    obj = NetlistTimingModel.__new__(NetlistTimingModel)
    obj.graph = nx.DiGraph()
    obj.reverse_graph = nx.DiGraph()
    obj.netlist = SimpleNamespace(
        input_ports={"IN1", "IN2"}, output_ports={"OUT1", "OUT2"}
    )
    return obj


def test_nearest_port_from_pin_rejects_invalid_num_ports(
    ntm: NetlistTimingModel,
) -> None:
    with pytest.raises(
        ValueError,
        match=r"num_ports must be at least 1",
    ):
        ntm.nearest_port_from_pin("X", num_ports=0)


def test_nearest_port_from_pin_single_port(
    ntm: NetlistTimingModel,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def _path_to_nearest_target_sentinel(
        _graph: nx.DiGraph, _pin: str, _targets: set[str]
    ) -> tuple[list[str], str]:
        return ["dummy"], "OUT1"

    monkeypatch.setattr(
        "fabulous.routing_model.netlist_timing_model.path_to_nearest_target_sentinel",
        _path_to_nearest_target_sentinel,
    )
    assert ntm.nearest_port_from_pin("u_buf0/A", reverse=False, num_ports=1) == ["OUT1"]


def test_nearest_port_from_pin_single_port_none(
    ntm: NetlistTimingModel,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def _path_to_nearest_target_sentinel(
        _graph: nx.DiGraph, _pin: str, _targets: set[str]
    ) -> tuple[list[str], None]:
        return [], None

    monkeypatch.setattr(
        "fabulous.routing_model.netlist_timing_model.path_to_nearest_target_sentinel",
        _path_to_nearest_target_sentinel,
    )
    assert ntm.nearest_port_from_pin("u_buf0/A", num_ports=1) == []


def test_nearest_port_from_pin_multiple_forward(
    ntm: NetlistTimingModel,
) -> None:
    ntm.graph.add_edges_from(
        [
            ("PIN", "N1"),
            ("N1", "OUT1"),
            ("PIN", "N2"),
            ("N2", "OUT2"),
        ]
    )
    ntm.netlist.output_ports = {"OUT1", "OUT2"}
    assert ntm.nearest_port_from_pin("PIN", reverse=False, num_ports=2) == [
        "OUT1",
        "OUT2",
    ]


def test_nearest_port_from_pin_multiple_reverse(
    ntm: NetlistTimingModel,
) -> None:
    ntm.reverse_graph.add_edges_from(
        [
            ("PIN", "N1"),
            ("N1", "IN1"),
            ("PIN", "N2"),
            ("N2", "IN2"),
        ]
    )
    ntm.netlist.input_ports = {"IN1", "IN2"}
    assert ntm.nearest_port_from_pin("PIN", reverse=True, num_ports=2) == ["IN1", "IN2"]


def test_nearest_port_from_pin_multiple_no_ports(
    ntm: NetlistTimingModel,
) -> None:
    ntm.graph.add_edge("PIN", "N1")
    ntm.netlist.output_ports = {"OUT1", "OUT2"}
    assert ntm.nearest_port_from_pin("PIN", reverse=False, num_ports=2) == []


def test_nearest_ports_from_instance_pin_nets(
    ntm: NetlistTimingModel,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    ntm.netlist.net_to_pin_paths_for_instance_resolved = lambda _inst: {
        "N1": ["p1"],
        "N2": ["p2"],
        "N3": [],
    }

    def fake_nearest(
        _pin: str,
        reverse: bool = False,
        num_ports: int = 1,
    ) -> list[str]:
        _ = (reverse, num_ports)
        if _pin == "p1":
            return ["OUT1", "OUT2"]
        if _pin == "p2":
            return ["OUT2"]
        return []

    monkeypatch.setattr(ntm, "nearest_port_from_pin", fake_nearest)

    mapping, flat = ntm.nearest_ports_from_instance_pin_nets(
        "u0", reverse=False, num_ports=2
    )

    assert mapping == {
        "N1": ["OUT1", "OUT2"],
        "N2": ["OUT2"],
    }
    assert flat == ["OUT1", "OUT2"]

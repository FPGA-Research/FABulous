"""Tests for the placement read-back model and its buffer-traversal walk."""

import json
from pathlib import Path

import pytest

from fabulous.custom_exception import GDSFlowError
from fabulous.fabric_generator.gds_generator.opt.placement import Placement


def _instance(master: str, x: float, y: float) -> dict:
    return {"master": master, "x": x, "y": y}


def _net(bterms: list[str], iterms: list[tuple[str, str, str]]) -> dict:
    return {"bterms": bterms, "iterms": [list(t) for t in iterms]}


# A west FrameData[0] port feeds a latch D pin and an antenna diode directly and
# reaches the east FrameData_O[0] port through a feed-through buffer. A south
# FrameStrobe[0] port reaches the latch GATE pin through two buffers, the second
# being an inverter-shaped cell, and reaches a mux through the first buffer only.
PLACEMENT_JSON: dict = {
    "die": [0, 0, 100, 80],
    "instances": {
        "lat0": _instance("dlhq", 40, 20),
        "buf_ft": _instance("buf", 90, 30),
        "diode0": _instance("antenna", 5, 30),
        "buf_s1": _instance("buf", 50, 5),
        "inv_s2": _instance("inv", 45, 10),
        "mux0": _instance("mux4", 60, 60),
        "tie0": _instance("tiehi", 70, 70),
    },
    "pins": {
        "FrameData[0]": {"io": "INPUT", "x": 0, "y": 30},
        "FrameData_O[0]": {"io": "OUTPUT", "x": 100, "y": 30},
        "FrameStrobe[0]": {"io": "INPUT", "x": 50, "y": 0},
        "N1BEG[0]": {"io": "OUTPUT", "x": 60, "y": 80},
    },
    "nets": {
        "FrameData[0]": _net(
            ["FrameData[0]"],
            [
                ("lat0", "D", "INPUT"),
                ("diode0", "DIODE", "INPUT"),
                ("buf_ft", "A", "INPUT"),
            ],
        ),
        "FrameData_O[0]": _net(["FrameData_O[0]"], [("buf_ft", "X", "OUTPUT")]),
        "FrameStrobe[0]": _net(["FrameStrobe[0]"], [("buf_s1", "A", "INPUT")]),
        "strobe_mid": _net(
            [],
            [
                ("buf_s1", "X", "OUTPUT"),
                ("inv_s2", "A", "INPUT"),
                ("mux0", "S0", "INPUT"),
            ],
        ),
        "strobe_end": _net([], [("inv_s2", "Y", "OUTPUT"), ("lat0", "GATE", "INPUT")]),
        "lat0_q": _net([], [("lat0", "Q", "OUTPUT"), ("mux0", "A0", "INPUT")]),
        "N1BEG[0]": _net(["N1BEG[0]"], [("mux0", "X", "OUTPUT")]),
        "tie_out": _net([], [("tie0", "X", "OUTPUT")]),
    },
}


@pytest.fixture
def placement(tmp_path: Path) -> Placement:
    path = tmp_path / "tile.placement.json"
    path.write_text(json.dumps(PLACEMENT_JSON))
    return Placement.from_json(path)


def test_die_dimensions(placement: Placement) -> None:
    assert (placement.width, placement.height) == (100, 80)


@pytest.mark.parametrize(
    ("instance", "is_buffer", "is_leaf"),
    [
        ("lat0", False, True),
        ("mux0", False, True),
        ("buf_ft", True, False),
        ("buf_s1", True, False),
        ("inv_s2", True, False),
        ("diode0", False, False),
        ("tie0", False, False),
        ("missing", False, False),
    ],
)
def test_cell_classification(
    placement: Placement, instance: str, is_buffer: bool, is_leaf: bool
) -> None:
    assert placement.is_buffer(instance) is is_buffer
    assert placement.is_leaf(instance) is is_leaf


@pytest.mark.parametrize(
    ("net", "members", "leaves", "ports"),
    [
        (
            "FrameData[0]",
            {"FrameData[0]", "FrameData_O[0]"},
            ("lat0",),
            {"FrameData[0]", "FrameData_O[0]"},
        ),
        (
            "FrameStrobe[0]",
            {"FrameStrobe[0]", "strobe_mid", "strobe_end"},
            ("lat0", "mux0"),
            {"FrameStrobe[0]"},
        ),
        ("lat0_q", {"lat0_q"}, ("lat0", "mux0"), set()),
        ("N1BEG[0]", {"N1BEG[0]"}, ("mux0",), {"N1BEG[0]"}),
    ],
)
def test_logical_net_walk(
    placement: Placement,
    net: str,
    members: set[str],
    leaves: tuple[str, ...],
    ports: set[str],
) -> None:
    assert placement.logical_net(net) == frozenset(members)
    assert tuple(leaf.name for leaf in placement.leaves(net)) == leaves
    assert placement.ports_of_logical_net(net) == frozenset(ports)


def test_net_of_port(placement: Placement) -> None:
    assert placement.net_of_port("FrameData_O[0]").name == "FrameData_O[0]"
    with pytest.raises(GDSFlowError, match="not on any signal net"):
        placement.net_of_port("UserCLK")


@pytest.mark.parametrize(
    ("mutate", "message"),
    [
        (lambda raw: raw["pins"]["N1BEG[0]"].__setitem__("io", "OUT"), "port N1BEG"),
        (
            lambda raw: raw["nets"]["tie_out"]["iterms"][0].__setitem__(2, "SUPPLY"),
            "net tie_out",
        ),
    ],
)
def test_from_json_rejects_unknown_io(
    tmp_path: Path, mutate: object, message: str
) -> None:
    raw = json.loads(json.dumps(PLACEMENT_JSON))
    mutate(raw)  # type: ignore[operator]
    path = tmp_path / "bad.placement.json"
    path.write_text(json.dumps(raw))
    with pytest.raises(GDSFlowError, match=message):
        Placement.from_json(path)

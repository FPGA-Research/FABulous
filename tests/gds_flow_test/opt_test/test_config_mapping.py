"""Tests for the configuration mapping on a two-by-two frame grid."""

import json
from pathlib import Path

import pytest

from fabulous.custom_exception import GDSFlowError
from fabulous.fabric_definition.configmem import ConfigMem, ConfigMemFrame, Crosspoint
from fabulous.fabric_definition.tile_interface import FRAME_CHAIN_PAIRS
from fabulous.fabric_generator.gds_generator.opt.config_mapping import (
    ConfigMapping,
    FrameLines,
    LatchPins,
    frame_grid,
    latch_pins,
    reconnections,
    solve_config_mapping,
)
from fabulous.fabric_generator.gds_generator.opt.placement import Placement


def _pin(io: str, x: float, y: float) -> dict:
    return {"io": io, "x": x, "y": y}


def _inst(master: str, x: float, y: float) -> dict:
    return {"master": master, "x": x, "y": y}


def _net(bterms: list[str], iterms: list[tuple[str, str, str]]) -> dict:
    return {"bterms": bterms, "iterms": [list(t) for t in iterms]}


# Frame data lines at y = 25 and 75, strobe lines at x = 25 and 75. Three of the
# four crosspoints hold a placed latch, each sitting close to a different
# crosspoint than the one the CSV gives it; the fourth bit's latch was removed.
GRID_PLACEMENT: dict = {
    "die": [0, 0, 100, 100],
    "instances": {
        "lat_f0d0": _inst("dlhq", 70, 70),
        "lat_f0d1": _inst("dlhq", 30, 30),
        "lat_f1d0": _inst("dlhq", 26, 74),
        "buf_d0": _inst("buf", 95, 25),
        "buf_d1": _inst("buf", 95, 75),
        "buf_s0": _inst("buf", 25, 5),
        "buf_s1": _inst("buf", 75, 5),
        "mux": _inst("mux4", 50, 50),
    },
    "pins": {
        "FrameData[0]": _pin("INPUT", 0, 25),
        "FrameData_O[0]": _pin("OUTPUT", 100, 25),
        "FrameData[1]": _pin("INPUT", 0, 75),
        "FrameData_O[1]": _pin("OUTPUT", 100, 75),
        "FrameStrobe[0]": _pin("INPUT", 25, 0),
        "FrameStrobe_O[0]": _pin("OUTPUT", 25, 100),
        "FrameStrobe[1]": _pin("INPUT", 75, 0),
        "FrameStrobe_O[1]": _pin("OUTPUT", 75, 100),
    },
    "nets": {
        "FrameData[0]": _net(
            ["FrameData[0]"],
            [
                ("lat_f0d0", "D", "INPUT"),
                ("lat_f1d0", "D", "INPUT"),
                ("buf_d0", "A", "INPUT"),
            ],
        ),
        "FrameData_O[0]": _net(["FrameData_O[0]"], [("buf_d0", "X", "OUTPUT")]),
        "FrameData[1]": _net(
            ["FrameData[1]"], [("lat_f0d1", "D", "INPUT"), ("buf_d1", "A", "INPUT")]
        ),
        "FrameData_O[1]": _net(["FrameData_O[1]"], [("buf_d1", "X", "OUTPUT")]),
        "FrameStrobe[0]": _net(["FrameStrobe[0]"], [("buf_s0", "A", "INPUT")]),
        "strobe0": _net(
            ["FrameStrobe_O[0]"],
            [
                ("buf_s0", "X", "OUTPUT"),
                ("lat_f0d0", "GATE", "INPUT"),
                ("lat_f0d1", "GATE", "INPUT"),
            ],
        ),
        "FrameStrobe[1]": _net(["FrameStrobe[1]"], [("buf_s1", "A", "INPUT")]),
        "strobe1": _net(
            ["FrameStrobe_O[1]"],
            [("buf_s1", "X", "OUTPUT"), ("lat_f1d0", "GATE", "INPUT")],
        ),
        "q0": _net([], [("lat_f0d0", "Q", "OUTPUT"), ("mux", "A0", "INPUT")]),
        "q1": _net([], [("lat_f0d1", "Q", "OUTPUT"), ("mux", "A1", "INPUT")]),
        "q2": _net([], [("lat_f1d0", "Q", "OUTPUT"), ("mux", "A2", "INPUT")]),
    },
}

# frame0 holds bit 1 on data line 1 and bit 0 on data line 0; frame1 holds bit 3
# on data line 1 and bit 2 on data line 0.
CURRENT = ConfigMem(
    (
        ConfigMemFrame("frame0", 0, 2, {1: 1, 0: 0}),
        ConfigMemFrame("frame1", 1, 2, {1: 3, 0: 2}),
    ),
    2,
)


LINES = FrameLines.from_pairs(FRAME_CHAIN_PAIRS)


def _placement(tmp_path: Path, raw: dict) -> Placement:
    path = tmp_path / "tile.placement.json"
    path.write_text(json.dumps(raw))
    return Placement.from_json(path)


# One data line at y = 50 and one strobe line at x = 50 with a single latch.
ONE_LATCH_PLACEMENT: dict = {
    "die": [0, 0, 100, 100],
    "instances": {
        "lat": _inst("dlhq", 20, 80),
        "buf_d": _inst("buf", 90, 50),
        "buf_s": _inst("buf", 50, 90),
        "mux": _inst("mux2", 10, 10),
    },
    "pins": {
        "FrameData[0]": _pin("INPUT", 0, 50),
        "FrameData_O[0]": _pin("OUTPUT", 100, 50),
        "FrameStrobe[0]": _pin("INPUT", 50, 0),
        "FrameStrobe_O[0]": _pin("OUTPUT", 50, 100),
    },
    "nets": {
        "FrameData[0]": _net(
            ["FrameData[0]"], [("lat", "D", "INPUT"), ("buf_d", "A", "INPUT")]
        ),
        "FrameData_O[0]": _net(["FrameData_O[0]"], [("buf_d", "X", "OUTPUT")]),
        "FrameStrobe[0]": _net(
            ["FrameStrobe[0]"], [("lat", "GATE", "INPUT"), ("buf_s", "A", "INPUT")]
        ),
        "FrameStrobe_O[0]": _net(["FrameStrobe_O[0]"], [("buf_s", "X", "OUTPUT")]),
        "q": _net([], [("lat", "Q", "OUTPUT"), ("mux", "A", "INPUT")]),
    },
}


@pytest.fixture
def placement(tmp_path: Path) -> Placement:
    return _placement(tmp_path, GRID_PLACEMENT)


@pytest.fixture
def one_latch_placement(tmp_path: Path) -> Placement:
    return _placement(tmp_path, ONE_LATCH_PLACEMENT)


def test_frame_grid_averages_both_ends(placement: Placement) -> None:
    grid = frame_grid(placement, LINES)
    assert grid.data_y == {0: 25, 1: 75}
    assert grid.strobe_x == {0: 25, 1: 75}
    assert grid.crosspoints() == [
        Crosspoint(0, 0),
        Crosspoint(0, 1),
        Crosspoint(1, 0),
        Crosspoint(1, 1),
    ]


def test_latches_are_found_through_buffers(placement: Placement) -> None:
    pins = latch_pins(placement, LINES)
    assert {c: latch.instance for c, latch in pins.items()} == {
        Crosspoint(0, 0): "lat_f0d0",
        Crosspoint(0, 1): "lat_f0d1",
        Crosspoint(1, 0): "lat_f1d0",
    }


def test_mapping_moves_each_latch_to_its_nearest_crosspoint(
    placement: Placement,
) -> None:
    mapping = solve_config_mapping(placement, CURRENT, LINES)

    assert mapping.crosspoint_of_bit == {
        0: Crosspoint(1, 1),
        1: Crosspoint(0, 0),
        2: Crosspoint(0, 1),
        3: Crosspoint(1, 0),
    }
    assert mapping.distance_before == 238
    assert mapping.distance_after == 22
    assert mapping.unplaced_bits == (3,)


def test_to_config_mem_inverts_the_mapping(placement: Placement) -> None:
    mapping = solve_config_mapping(placement, CURRENT, LINES)
    proposal = mapping.to_config_mem(CURRENT)
    assert proposal == ConfigMem(
        (
            ConfigMemFrame("frame0", 0, 2, {1: 2, 0: 1}),
            ConfigMemFrame("frame1", 1, 2, {1: 0, 0: 3}),
        ),
        2,
    )
    assert proposal.crosspoint_of == mapping.crosspoint_of_bit


def test_to_config_mem_rejects_a_gap_in_the_bit_range() -> None:
    mapping = ConfigMapping({0: Crosspoint(0, 0), 2: Crosspoint(1, 0)}, 0, 0, ())
    with pytest.raises(ValueError, match="not a contiguous range"):
        mapping.to_config_mem(CURRENT)


def _drop_pin(raw: dict) -> None:
    del raw["pins"]["FrameData_O[1]"]


def _second_latch_on_crosspoint(raw: dict) -> None:
    raw["instances"]["lat_dup"] = _inst("dlhq", 1, 1)
    raw["nets"]["FrameData[0]"]["iterms"].append(["lat_dup", "D", "INPUT"])
    raw["nets"]["strobe0"]["iterms"].append(["lat_dup", "GATE", "INPUT"])
    raw["nets"]["qd"] = _net([], [("lat_dup", "Q", "OUTPUT"), ("mux", "A3", "INPUT")])


def _mux_on_a_data_line(raw: dict) -> None:
    raw["nets"]["FrameData[1]"]["iterms"].append(["mux", "S0", "INPUT"])


def _latch_on_two_data_lines(raw: dict) -> None:
    raw["nets"]["FrameData[1]"]["iterms"].append(["lat_f0d0", "D2", "INPUT"])


def _no_latches(raw: dict) -> None:
    for name in ("lat_f0d0", "lat_f0d1", "lat_f1d0"):
        for net in raw["nets"].values():
            net["iterms"] = [t for t in net["iterms"] if t[0] != name]


@pytest.mark.parametrize(
    ("mutate", "message"),
    [
        (_drop_pin, "do not pair up"),
        (_second_latch_on_crosspoint, "both sit on FrameData"),
        (_mux_on_a_data_line, "reached from \\['FrameData'\\] only"),
        (_latch_on_two_data_lines, "hangs from FrameData\\[0\\] and FrameData\\[1\\]"),
        (_no_latches, "No configuration latch was reached"),
    ],
)
def test_mapping_rejects_structures_that_break_the_crosspoint_model(
    tmp_path: Path, mutate: object, message: str
) -> None:
    raw = json.loads(json.dumps(GRID_PLACEMENT))
    mutate(raw)  # type: ignore[operator]
    with pytest.raises(GDSFlowError, match=message):
        solve_config_mapping(_placement(tmp_path, raw), CURRENT, LINES)


def test_mapping_rejects_a_latch_the_csv_does_not_allocate(
    placement: Placement,
) -> None:
    memory = ConfigMem((ConfigMemFrame("frame0", 0, 2, {1: 1, 0: 0}),), 2)
    with pytest.raises(GDSFlowError, match="does not allocate: \\[\\(0, 1\\)\\]"):
        solve_config_mapping(placement, memory, LINES)


def test_latch_pins_names_the_data_and_strobe_pins(
    one_latch_placement: Placement,
) -> None:
    pins = latch_pins(one_latch_placement, LINES)
    assert pins == {Crosspoint(frame=0, data_bit=0): LatchPins("lat", "D", "GATE")}


def test_reconnections_give_every_latch_its_target_port_nets() -> None:
    pins = {
        Crosspoint(0, 0): LatchPins("lat_a", "D", "GATE"),
        Crosspoint(1, 1): LatchPins("lat_b", "D", "GATE"),
    }
    bit_at = {Crosspoint(0, 0): 0, Crosspoint(1, 1): 1}
    mapping = ConfigMapping(
        crosspoint_of_bit={0: Crosspoint(1, 0), 1: Crosspoint(0, 1)},
        distance_before=0.0,
        distance_after=0.0,
        unplaced_bits=(),
    )
    assert reconnections(pins, bit_at, mapping, LINES) == {
        "lat_a": {"D": "FrameData[0]", "GATE": "FrameStrobe[1]"},
        "lat_b": {"D": "FrameData[1]", "GATE": "FrameStrobe[0]"},
    }


def test_reconnections_reject_a_latch_on_an_unallocated_crosspoint() -> None:
    pins = {Crosspoint(0, 0): LatchPins("lat", "D", "GATE")}
    mapping = ConfigMapping({0: Crosspoint(0, 0)}, 0.0, 0.0, ())
    with pytest.raises(GDSFlowError, match="does not allocate"):
        reconnections(pins, {}, mapping, LINES)

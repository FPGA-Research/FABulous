"""Tests for the configuration mapping on a two-by-two frame grid."""

import json
from pathlib import Path

import pytest

from fabulous.custom_exception import GDSFlowError
from fabulous.fabric_definition.configmem import ConfigMem, ConfigMemFrame, Crosspoint
from fabulous.fabric_generator.gds_generator.opt.config_mapping import (
    frame_grid,
    reconnections,
    solve_config_mapping,
)
from fabulous.fabric_generator.gds_generator.opt.placement import (
    PlacedLatch,
    Placement,
)


def _latch(frame: int, data_bit: int, name: str, x: float, y: float) -> dict:
    return {
        "frame": frame,
        "data_bit": data_bit,
        "instance": name,
        "x": x,
        "y": y,
        "data_pin": "D",
        "strobe_pin": "GATE",
    }


# Frame data lines at y = 25 and 75, strobe lines at x = 25 and 75. Three of the
# four crosspoints hold a placed latch, each sitting nearer a different
# crosspoint than the one the CSV gives it; the fourth bit's latch was removed.
GRID_PLACEMENT: dict = {
    "die": [0, 0, 100, 100],
    "data_y": {"0": [25, 25], "1": [75, 75]},
    "strobe_x": {"0": [25, 25], "1": [75, 75]},
    "latches": [
        _latch(0, 0, "lat_f0d0", 70, 70),
        _latch(0, 1, "lat_f0d1", 30, 30),
        _latch(1, 0, "lat_f1d0", 26, 74),
    ],
}

SOURCE = Path("T_ConfigMem.csv")
CURRENT = ConfigMem(
    (
        ConfigMemFrame("frame0", 0, 2, {1: 1, 0: 0}),
        ConfigMemFrame("frame1", 1, 2, {1: 3, 0: 2}),
    ),
    2,
    2,
    source=SOURCE,
)


def _placement(tmp_path: Path, raw: dict) -> Placement:
    path = tmp_path / "tile.placement.json"
    path.write_text(json.dumps(raw))
    return Placement.from_json(path)


@pytest.fixture
def placement(tmp_path: Path) -> Placement:
    return _placement(tmp_path, GRID_PLACEMENT)


def _bunch_pins_in_a_corner(raw: dict) -> None:
    """Leave the buses contiguous, as a default pin order does."""
    for axis in ("data_y", "strobe_x"):
        raw[axis] = {"0": [90, 90], "1": [95, 95]}


def _reverse_pin_order(raw: dict) -> None:
    for axis in ("data_y", "strobe_x"):
        raw[axis] = {"0": [75, 75], "1": [25, 25]}


@pytest.mark.parametrize(
    ("mutate", "data_y", "strobe_x"),
    [
        (None, {0: 25, 1: 75}, {0: 25, 1: 75}),
        (_bunch_pins_in_a_corner, {0: 25, 1: 75}, {0: 25, 1: 75}),
        (_reverse_pin_order, {0: 75, 1: 25}, {0: 75, 1: 25}),
    ],
    ids=["already spread", "bunched in a corner", "reversed"],
)
def test_frame_grid_spreads_the_trunks_over_the_die(
    tmp_path: Path, mutate: object, data_y: dict, strobe_x: dict
) -> None:
    raw = json.loads(json.dumps(GRID_PLACEMENT))
    if mutate is not None:
        mutate(raw)  # type: ignore[operator]
    grid = frame_grid(_placement(tmp_path, raw))
    assert grid.data_y == data_y
    assert grid.strobe_x == strobe_x


def test_frame_grid_crosspoints_run_frame_then_data_bit(placement: Placement) -> None:
    assert frame_grid(placement).crosspoints() == [
        Crosspoint(0, 0),
        Crosspoint(0, 1),
        Crosspoint(1, 0),
        Crosspoint(1, 1),
    ]


def test_mapping_moves_each_latch_to_its_nearest_crosspoint(
    placement: Placement,
) -> None:
    proposal, moved = solve_config_mapping(placement, CURRENT)

    assert proposal.crosspoint_of == {
        0: Crosspoint(1, 1),
        1: Crosspoint(0, 0),
        2: Crosspoint(0, 1),
        3: Crosspoint(1, 0),
    }
    assert moved.stub_before == 238
    assert moved.stub_after == 22
    assert moved.unplaced_bits == (3,)


def test_the_proposal_is_a_memory_of_the_same_grid(placement: Placement) -> None:
    proposal, _ = solve_config_mapping(placement, CURRENT)
    assert proposal == ConfigMem(
        (
            ConfigMemFrame("frame0", 0, 2, {1: 2, 0: 1}),
            ConfigMemFrame("frame1", 1, 2, {1: 0, 0: 3}),
        ),
        2,
        2,
        source=SOURCE,
    )


def test_mapping_rejects_a_latch_the_csv_does_not_allocate(
    placement: Placement,
) -> None:
    memory = ConfigMem(
        (ConfigMemFrame("frame0", 0, 2, {1: 1, 0: 0}),), 2, 1, source=SOURCE
    )
    with pytest.raises(GDSFlowError, match="does not allocate: \\[\\(0, 1\\)\\]"):
        solve_config_mapping(placement, memory)


def test_reconnections_give_every_latch_its_target_port_nets() -> None:
    latches = (
        PlacedLatch(Crosspoint(0, 0), "lat_a", 0, 0, "D", "GATE"),
        PlacedLatch(Crosspoint(1, 1), "lat_b", 0, 0, "D", "GATE"),
    )
    bit_at = {Crosspoint(0, 0): 0, Crosspoint(1, 1): 1}
    proposal = CURRENT.rebuilt_with({Crosspoint(1, 0): 0, Crosspoint(0, 1): 1})
    assert reconnections(latches, bit_at, proposal) == {
        "lat_a": {"D": "FrameData[0]", "GATE": "FrameStrobe[1]"},
        "lat_b": {"D": "FrameData[1]", "GATE": "FrameStrobe[0]"},
    }


def test_reconnections_reject_a_latch_on_an_unallocated_crosspoint() -> None:
    latches = (PlacedLatch(Crosspoint(0, 0), "lat", 0, 0, "D", "GATE"),)
    proposal = CURRENT.rebuilt_with({Crosspoint(0, 0): 0})
    with pytest.raises(GDSFlowError, match="does not allocate"):
        reconnections(latches, {}, proposal)

"""Tests for Placement: loading the crosspoint grid the dump step wrote."""

import json
from pathlib import Path

import pytest

from fabulous.custom_exception import GDSFlowError
from fabulous.fabric_definition.configmem import Crosspoint
from fabulous.fabric_generator.gds_generator.opt.placement import (
    PlacedLatch,
    Placement,
)

DUMP: dict = {
    "die": [0, 0, 100, 80],
    "data_y": {"0": [25, 26], "1": [75, 74]},
    "strobe_x": {"0": [30, 31]},
    "latches": [
        {
            "frame": 0,
            "data_bit": 1,
            "instance": "lat0",
            "x": 12.5,
            "y": 40,
            "data_pin": "D",
            "strobe_pin": "GATE",
        }
    ],
}


def _write(tmp_path: Path, raw: dict) -> Path:
    path = tmp_path / "tile.placement.json"
    path.write_text(json.dumps(raw))
    return path


def test_the_dump_loads_as_the_grid_it_describes(tmp_path: Path) -> None:
    """Bus indices are JSON object keys, so they come back as integers."""
    placement = Placement.from_json(_write(tmp_path, DUMP))

    assert placement.die == (0, 0, 100, 80)
    assert placement.data_y == {0: (25, 26), 1: (75, 74)}
    assert placement.strobe_x == {0: (30, 31)}
    assert placement.latches == (
        PlacedLatch(Crosspoint(0, 1), "lat0", 12.5, 40, "D", "GATE"),
    )


@pytest.mark.parametrize(
    "drop",
    ["die", "data_y", "strobe_x", "latches"],
    ids=lambda field: f"without_{field}",
)
def test_a_dump_missing_a_field_is_refused(tmp_path: Path, drop: str) -> None:
    """A field absent means a different version of the step wrote the file."""
    raw = json.loads(json.dumps(DUMP))
    del raw[drop]

    with pytest.raises(GDSFlowError, match="not a FABulous placement dump"):
        Placement.from_json(_write(tmp_path, raw))


def test_a_latch_missing_a_field_is_refused(tmp_path: Path) -> None:
    raw = json.loads(json.dumps(DUMP))
    del raw["latches"][0]["strobe_pin"]

    with pytest.raises(GDSFlowError, match="not a FABulous placement dump"):
        Placement.from_json(_write(tmp_path, raw))

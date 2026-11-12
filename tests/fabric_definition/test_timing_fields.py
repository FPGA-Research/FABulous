"""Tests for the timing fields of the fabric model."""

from collections.abc import Callable
from copy import deepcopy
from dataclasses import replace
from pathlib import Path

import pytest

from fabulous.fabric_definition.define import IO, Direction
from fabulous.fabric_definition.switch_matrix import SwitchMatrix
from fabulous.fabric_definition.timing import BelArcs, DelayArc, SwitchPip, ns
from fabulous.fabric_definition.wire import Wire
from tests.conftest import make_empty_tile, make_fabric_from_grid, make_muladd_bel


def _bel_pair() -> tuple[object, object]:
    """Return a BEL without arcs and a copy of it with arcs."""
    untimed = make_muladd_bel([("SUPER_A", IO.INPUT), ("SUPER_Y", IO.OUTPUT)])
    timed = deepcopy(untimed)
    timed.arcs = BelArcs(
        delays=(DelayArc(timed.input_ports[0], timed.output_ports[0], ns(1.5)),)
    )
    return untimed, timed


def _switch_matrix_pair() -> tuple[object, object]:
    """Return a switch matrix without pip delays and a copy of it with them."""
    untimed = SwitchMatrix(matrix_file=Path(), connections={"Y": ["A"]})
    return untimed, replace(untimed, pip_delays={SwitchPip("A", "Y"): ns(0.5)})


def _wire_pair() -> tuple[object, object]:
    """Return a wire without delay and a copy of it with a delay."""
    untimed = Wire(Direction.JUMP, "A0", 0, 0, "B0", "", "")
    return untimed, replace(untimed, delay=ns(0.25))


def _fabric_pair() -> tuple[object, object]:
    """Return a fabric without clock arrival and a copy of it with one."""
    untimed = make_fabric_from_grid([[make_empty_tile("LUT", pinOrderConfig={})]])
    timed = deepcopy(untimed)
    timed.clock_arrival = ns(1.0)
    return untimed, timed


@pytest.mark.parametrize(
    "pair",
    [_bel_pair, _switch_matrix_pair, _wire_pair, _fabric_pair],
    ids=["bel", "switch-matrix", "wire", "fabric"],
)
def test_timing_is_not_part_of_model_equality(
    pair: Callable[[], tuple[object, object]],
) -> None:
    """Two model objects that differ only in their timing compare equal."""
    untimed, timed = pair()

    assert untimed == timed


def test_wire_delay_is_not_part_of_the_hash() -> None:
    """De-duplicating a tile's wires treats a timed wire as its untimed copy."""
    untimed, timed = _wire_pair()

    assert hash(untimed) == hash(timed)
    assert list(dict.fromkeys([untimed, timed])) == [untimed]


def test_fabric_has_timing_once_timing_is_set() -> None:
    """A parsed fabric is untimed until `set_timing` runs on it."""
    tile = make_empty_tile("LUT", pinOrderConfig={})
    tile.switch_matrix = SwitchMatrix(matrix_file=Path(), connections={"Y": ["A"]})
    fabric = make_fabric_from_grid([[tile]])
    assert not fabric.has_timing

    fabric.set_timing(
        tile_arcs={"LUT": []},
        tile_pip_delays={"LUT": {SwitchPip("A", "Y"): ns(0.5)}},
        super_tile_arcs={},
        super_tile_pip_delays={},
        clock_arrival=ns(1.0),
    )

    assert fabric.has_timing
    assert fabric.tile[0][0].switch_matrix.pip_delays == {SwitchPip("A", "Y"): ns(0.5)}

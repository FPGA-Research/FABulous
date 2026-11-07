"""Tests for the timing fields of the fabric model."""

from collections.abc import Callable
from copy import deepcopy
from dataclasses import replace
from pathlib import Path

import pytest

from fabulous.fabric_definition.define import IO
from fabulous.fabric_definition.switch_matrix import SwitchMatrix
from fabulous.fabric_definition.timing import BelArcs, BelPin, DelayArc, SwitchPip, ns
from tests.conftest import make_muladd_bel


def _bel_pair() -> tuple[object, object]:
    """Return a BEL without arcs and a copy of it with arcs."""
    untimed = make_muladd_bel([("SUPER_A", IO.INPUT), ("SUPER_Y", IO.OUTPUT)])
    timed = deepcopy(untimed)
    timed.arcs = BelArcs(delays=(DelayArc(BelPin("A"), BelPin("Y"), ns(1.5)),))
    return untimed, timed


def _switch_matrix_pair() -> tuple[object, object]:
    """Return a switch matrix without pip delays and a copy of it with them."""
    untimed = SwitchMatrix(matrix_file=Path(), connections={"Y": ["A"]})
    return untimed, replace(untimed, pip_delays={SwitchPip("A", "Y"): ns(0.5)})


@pytest.mark.parametrize(
    "pair", [_bel_pair, _switch_matrix_pair], ids=["bel", "switch-matrix"]
)
def test_timing_is_not_part_of_model_equality(
    pair: Callable[[], tuple[object, object]],
) -> None:
    """Two model objects that differ only in their timing compare equal."""
    untimed, timed = pair()

    assert untimed == timed

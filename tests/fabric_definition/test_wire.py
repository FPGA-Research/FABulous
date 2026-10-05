"""Unit tests for `Wire` equality and hashing."""

import pytest

from fabulous.fabric_definition.define import Direction
from fabulous.fabric_definition.wire import Wire

_BASE = Wire(Direction.EAST, "E1BEG0", 1, 0, "E1END0", "X0Y0", "X1Y0")


@pytest.mark.parametrize(
    ("other", "equal"),
    [
        pytest.param(
            Wire(Direction.EAST, "E1BEG0", 1, 0, "E1END0", "X0Y0", "X1Y0"),
            True,
            id="identical",
        ),
        pytest.param(
            Wire(Direction.EAST, "E1BEG0", 2, 0, "E1END0", "X0Y0", "X2Y0"),
            False,
            id="differ_by_offset",
        ),
        pytest.param(
            Wire(Direction.EAST, "E2BEG0", 1, 0, "E1END0", "X0Y0", "X1Y0"),
            False,
            id="differ_by_source",
        ),
    ],
)
def test_equality_agrees_with_hash(other: Wire, equal: bool) -> None:
    """Equal wires hash equal, so `dict.fromkeys` keeps exactly the distinct ones."""
    assert (other == _BASE) is equal
    if equal:
        assert hash(_BASE) == hash(other)
    assert len(dict.fromkeys([_BASE, other])) == (1 if equal else 2)

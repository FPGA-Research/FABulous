"""Conftest file providing fixtures for fabric definition tests."""

from collections.abc import Callable
from pathlib import Path

import pytest

from fabulous.fabric_definition.define import IO, Direction, Side
from fabulous.fabric_definition.fabric import Fabric
from fabulous.fabric_definition.port import Port
from tests.conftest import make_empty_tile  # re-exported for fabric_definition tests

__all__ = ["make_empty_tile"]


@pytest.fixture
def make_fabric() -> Callable[..., Fabric]:
    """Return a factory that creates a real Fabric with sensible defaults.

    Unlike the mocked fixtures in ``fabric_gen_test/conftest.py``, the objects
    produced here go through ``__post_init__`` and therefore exercise all
    validation logic.
    """

    def _make(**overrides: int) -> Fabric:
        defaults = {
            "fabric_dir": Path("/tmp"),
            "frameBitsPerRow": 32,
            "maxFramesPerCol": 20,
            "frameSelectWidth": 5,
            "desync_flag": 20,
            "numberOfColumns": 15,
        }
        defaults.update(overrides)
        return Fabric(**defaults)

    return _make


def make_side_port(side: Side, name: str = "P") -> Port:
    """Construct a Port physically located on the given side."""
    return Port(
        Direction.JUMP,
        name,
        0,
        0,
        name,
        1,
        name,
        IO.INPUT,
        side,
    )

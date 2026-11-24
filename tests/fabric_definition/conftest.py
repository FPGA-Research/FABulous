"""Conftest file providing fixtures for fabric definition tests."""

from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest

from fabulous.fabric_definition.define import IO, Direction, Side
from fabulous.fabric_definition.fabric import Fabric
from fabulous.fabric_definition.port import TilePort
from tests.conftest import make_empty_tile  # re-exported for fabric_definition tests

__all__ = ["make_empty_tile"]


@pytest.fixture
def make_fabric() -> Callable[..., Fabric]:
    """Return a factory that creates a real Fabric with sensible defaults.

    Unlike the mocked fixtures in ``fabric_gen_test/conftest.py``, the objects
    produced here go through ``__post_init__`` and therefore exercise all
    validation logic.
    """

    def _make(**overrides: object) -> Fabric:
        defaults: dict[str, Any] = {
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


def make_side_port(side: Side, name: str = "P") -> TilePort:
    """Construct a TilePort physically located on the given side."""
    return TilePort(
        name=name,
        io_direction=IO.INPUT,
        width=1,
        side_of_tile=side,
        wire_direction=Direction.JUMP,
        source_name=name,
        x_offset=0,
        y_offset=0,
        destination_name=name,
        wire_count=1,
    )

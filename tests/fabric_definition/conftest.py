"""Conftest file providing fixtures for fabric definition tests."""

from collections.abc import Callable
from pathlib import Path

import pytest

from fabulous.fabric_definition.define import IO, Direction, Side
from fabulous.fabric_definition.fabric import Fabric
from fabulous.fabric_definition.port import Port
from fabulous.fabric_definition.tile import Tile


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


def make_empty_tile(name: str, ports: list[Port] | None = None) -> Tile:
    """Build a minimal Tile usable inside a SuperTile.tileMap."""
    return Tile(
        name=name,
        ports=ports or [],
        bels=[],
        tileDir=Path(),
        matrixDir=Path(),
        gen_ios=[],
        userCLK=False,
    )


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

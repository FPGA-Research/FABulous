"""Tests for cached BEL timing dispatch through the fabric-level interface."""

import pytest
from pytest_mock import MockerFixture

from fabulous.fabric_cad.timing_model.FABulous_timing_model_interface import (
    FABulousTimingModelInterface,
)
from fabulous.fabric_cad.timing_model.models import (
    BelDelayTiming,
    BelTiming,
)
from fabulous.fabric_definition.bel import Bel
from fabulous.fabric_definition.define import IO


def _bel(prefix: str = "LA_") -> Bel:
    """Build the stable BEL identity needed by the interface cache.

    Parameters
    ----------
    prefix : str
        Instance prefix distinguishing BELs within one tile macro.

    Returns
    -------
    Bel
        Minimal BEL definition suitable for interface dispatch tests.
    """
    bel = Bel.__new__(Bel)
    bel.name = "LUT4c_frame_config_dffesr"
    bel.module_name = "LUT4c_frame_config_dffesr"
    bel.prefix = prefix
    bel.ports_vectors = {
        "internal": {
            "I": (IO.INPUT, 4),
            "O": (IO.OUTPUT, 1),
            "Ci": (IO.INPUT, 1),
            "Co": (IO.OUTPUT, 1),
        },
        "shared": {"UserCLK": (IO.INPUT, 1)},
    }
    bel.withUserCLK = True
    bel.belFeatureMap = {"INIT": {}, "INIT[1]": {}, "FF": {}, "IOmux": {}}
    bel.carry = {
        "C0": {
            IO.INPUT: f"{prefix}Ci",
            IO.OUTPUT: f"{prefix}Co",
        }
    }
    return bel


def _timing(delay: float = 3.0) -> BelTiming:
    """Build one immutable combinational timing request.

    Parameters
    ----------
    delay : float
        Placeholder arc delay in nanoseconds.

    Returns
    -------
    BelTiming
        Timing object containing one conditional input-to-output arc.
    """
    return BelTiming(arcs=(BelDelayTiming("I0", "O", delay, condition="FF=0"),))


def test_interface_bel_timing_caches_by_tile_and_bel_identity(
    mocker: MockerFixture,
) -> None:
    """Repeated requests reuse one tile-model BEL timing result."""
    tile_model = mocker.Mock()
    characterized = _timing(1.25)
    tile_model.bel_timing.return_value = characterized
    interface = FABulousTimingModelInterface.__new__(FABulousTimingModelInterface)
    interface.timing_models = {"LUT4AB": tile_model}
    interface.bel_timing_cache = {}
    bel = _bel()

    first = interface.bel_timing("LUT4AB", bel)
    second = interface.bel_timing("LUT4AB", bel)

    assert first is characterized
    assert second is characterized
    tile_model.bel_timing.assert_called_once_with(bel)


def test_interface_bel_timing_keeps_multiple_bel_prefixes_separate(
    mocker: MockerFixture,
) -> None:
    """Two instances of one BEL module do not collide in the cache."""
    tile_model = mocker.Mock()
    tile_model.bel_timing.return_value = BelTiming()
    interface = FABulousTimingModelInterface.__new__(FABulousTimingModelInterface)
    interface.timing_models = {"LUT4AB": tile_model}
    interface.bel_timing_cache = {}
    interface.bel_timing("LUT4AB", _bel("LA_"))
    interface.bel_timing("LUT4AB", _bel("LB_"))

    assert tile_model.bel_timing.call_count == 2


def test_interface_bel_timing_rejects_unknown_tile() -> None:
    """BEL timing requests require a timing model for the named tile type."""
    interface = FABulousTimingModelInterface.__new__(FABulousTimingModelInterface)
    interface.timing_models = {}
    interface.bel_timing_cache = {}

    with pytest.raises(ValueError, match="UNKNOWN"):
        interface.bel_timing("UNKNOWN", _bel())

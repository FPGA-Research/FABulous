"""Tests for FABulousDetailedRoutingTimed step.

Covers the wall-clock timeout wrapper around OpenROAD detailed routing without
relying on real timers or subprocesses.
"""

import pytest
from librelane.steps import openroad as OpenROAD
from pytest_mock import MockerFixture

from fabulous.fabric_generator.gds_generator.steps import timed_detailed_routing
from fabulous.fabric_generator.gds_generator.steps.timed_detailed_routing import (
    DRTTimedOutError,
    FABulousDetailedRoutingTimed,
)


class TestFABulousDetailedRoutingTimed:
    """Test suite for the timed detailed routing step."""

    def test_timeout_raises_drt_timed_out_error(self, mocker: MockerFixture) -> None:
        """When the timer fired, a failure is wrapped as DRTTimedOutError."""
        event = mocker.MagicMock()
        event.is_set.return_value = True
        mocker.patch.object(
            timed_detailed_routing.threading, "Event", return_value=event
        )
        mocker.patch.object(
            OpenROAD.DetailedRouting, "run", side_effect=RuntimeError("boom")
        )

        step = FABulousDetailedRoutingTimed.__new__(FABulousDetailedRoutingTimed)
        step.config = {"FABULOUS_DRT_TIMEOUT": 600}
        state = mocker.MagicMock()

        with pytest.raises(DRTTimedOutError):
            step.run(state)

    def test_non_timeout_reraises_original(self, mocker: MockerFixture) -> None:
        """When the timer never fired, the original exception propagates as-is."""
        event = mocker.MagicMock()
        event.is_set.return_value = False
        mocker.patch.object(
            timed_detailed_routing.threading, "Event", return_value=event
        )
        mocker.patch.object(
            OpenROAD.DetailedRouting, "run", side_effect=RuntimeError("boom")
        )

        step = FABulousDetailedRoutingTimed.__new__(FABulousDetailedRoutingTimed)
        step.config = {"FABULOUS_DRT_TIMEOUT": 600}
        state = mocker.MagicMock()

        with pytest.raises(RuntimeError, match="boom"):
            step.run(state)

    def test_success_passes_popen_callable(self, mocker: MockerFixture) -> None:
        """On success the result is returned and a _popen_callable kwarg is injected."""
        super_run = mocker.patch.object(
            OpenROAD.DetailedRouting, "run", return_value=({}, {})
        )

        step = FABulousDetailedRoutingTimed.__new__(FABulousDetailedRoutingTimed)
        step.config = {"FABULOUS_DRT_TIMEOUT": 600}
        state = mocker.MagicMock()

        result = step.run(state)

        assert result == ({}, {})
        assert "_popen_callable" in super_run.call_args.kwargs

"""Tests for FABulousDetailedRoutingTimed step.

Covers the wall-clock timeout wrapper around OpenROAD detailed routing without
relying on real timers or subprocesses.
"""

import signal

import pytest
from librelane.steps import openroad as OpenROAD
from pytest_mock import MockerFixture, MockType

from fabulous.fabric_generator.gds_generator.steps import timed_detailed_routing
from fabulous.fabric_generator.gds_generator.steps.timed_detailed_routing import (
    DRTTimedOutError,
    FABulousDetailedRoutingTimed,
)


def _make_step() -> FABulousDetailedRoutingTimed:
    """Build the step without librelane's config machinery."""
    step = FABulousDetailedRoutingTimed.__new__(FABulousDetailedRoutingTimed)
    step.config = {"FABULOUS_DRT_TIMEOUT": 600}
    return step


class TestFABulousDetailedRoutingTimed:
    """Test suite for the timed detailed routing step."""

    @pytest.fixture
    def popen(self, mocker: MockerFixture) -> MockType:
        """Replace the process class so no OpenROAD process is started."""
        popen = mocker.patch.object(timed_detailed_routing, "_GroupLeaderPopen")
        popen.return_value.pid = 1234
        return popen

    @pytest.fixture
    def timer(self, mocker: MockerFixture) -> MockType:
        """Replace `threading.Timer` so the kill callback only fires on demand."""
        return mocker.patch.object(timed_detailed_routing.threading, "Timer")

    @pytest.mark.usefixtures("popen")
    def test_timeout_kills_process_group_and_raises(
        self, mocker: MockerFixture, timer: MockType
    ) -> None:
        """When the timer fires, the process group is killed and the error wrapped."""
        killpg = mocker.patch.object(timed_detailed_routing.os, "killpg")
        mocker.patch.object(timed_detailed_routing.os, "getpgid", return_value=4321)

        def _route_until_killed(*_args: object, **kwargs: object) -> None:
            kwargs["_popen_callable"](["openroad"])
            ((_timeout, kill), _) = timer.call_args
            kill()
            raise RuntimeError("boom")

        mocker.patch.object(
            OpenROAD.DetailedRouting, "run", side_effect=_route_until_killed
        )

        with pytest.raises(DRTTimedOutError, match="exceeded 600s timeout"):
            _make_step().run(mocker.MagicMock())

        killpg.assert_called_once_with(4321, signal.SIGKILL)

    @pytest.mark.usefixtures("popen")
    def test_non_timeout_reraises_original(
        self, mocker: MockerFixture, timer: MockType
    ) -> None:
        """When the timer never fired, the original exception propagates as-is."""

        def _route_and_fail(*_args: object, **kwargs: object) -> None:
            kwargs["_popen_callable"](["openroad"])
            raise RuntimeError("boom")

        mocker.patch.object(
            OpenROAD.DetailedRouting, "run", side_effect=_route_and_fail
        )

        with pytest.raises(RuntimeError, match="boom"):
            _make_step().run(mocker.MagicMock())

        timer.return_value.cancel.assert_called_once_with()

    def test_success_spawns_in_new_session_with_timer(
        self, mocker: MockerFixture, popen: MockType, timer: MockType
    ) -> None:
        """OpenROAD runs as a session leader under a started, then cancelled, timer."""

        def _route(*_args: object, **kwargs: object) -> tuple[dict, dict]:
            proc = kwargs["_popen_callable"](["openroad", "-exit"], stdout=1)
            assert proc is popen.return_value
            timer.return_value.cancel.assert_not_called()
            return {"view": "data"}, {"metric": 1}

        mocker.patch.object(OpenROAD.DetailedRouting, "run", side_effect=_route)

        result = _make_step().run(mocker.MagicMock())

        assert result == ({"view": "data"}, {"metric": 1})
        popen.assert_called_once_with(
            ["openroad", "-exit"], stdout=1, start_new_session=True
        )
        assert timer.call_args.args[0] == 600
        assert timer.return_value.daemon is True
        timer.return_value.start.assert_called_once_with()
        timer.return_value.cancel.assert_called_once_with()

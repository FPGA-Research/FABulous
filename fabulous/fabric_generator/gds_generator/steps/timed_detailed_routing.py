"""Detailed Routing step with a hard wall-clock timeout.

During tile-size exploration TritonRoute can spin for hours on pathological
dies. This step wraps {class}`librelane.steps.openroad.DetailedRouting` so that
if routing has not finished within `FABULOUS_DRT_TIMEOUT` seconds the entire
OpenROAD process group is killed and a {class}`DRTTimedOutError` is raised,
which the surrounding optimisation loop treats as a hard stop.
"""

import contextlib
import os
import signal
import subprocess
import threading
from typing import Any

from librelane.config.variable import Variable
from librelane.logging.logger import warn
from librelane.state.state import State
from librelane.steps import openroad as OpenROAD
from librelane.steps.step import MetricsUpdate, Step, StepError, ViewsUpdate


class DRTTimedOutError(StepError):
    """Raised when Detailed Routing exceeds its configured wall-clock timeout."""


class _GroupLeaderPopen(subprocess.Popen):
    """Minimal `subprocess.Popen` shim accepted by librelane's stats thread.

    librelane's `ProcessStatsThread` checks
    `status() in {STATUS_ZOMBIE, STATUS_DEAD}` at entry to its sampling
    loop; returning `"dead"` (psutil's `STATUS_DEAD` literal) makes it
    exit immediately, so no psutil-specific methods are ever called and
    stats reporting is skipped for the timed DRT step. Everything else
    (line streaming, `wait()`, `returncode`, etc.) is plain
    `subprocess.Popen` behaviour.
    """

    def status(self) -> str:
        """Return status."""
        return "dead"


@Step.factory.register()
class FABulousDetailedRoutingTimed(OpenROAD.DetailedRouting):
    """`OpenROAD.DetailedRouting` with a hard wall-clock timeout."""

    id = "FABulous.DetailedRoutingTimed"
    name = "Detailed Routing (Timed)"

    config_vars = OpenROAD.DetailedRouting.config_vars + [
        Variable(
            "FABULOUS_DRT_TIMEOUT",
            int,
            "Maximum wall-clock seconds for Detailed Routing. The OpenROAD "
            "process group is killed when this elapses and the surrounding "
            "tile optimisation loop is aborted.",
            default=900,
        ),
    ]

    def run(
        self,
        state_in: State,
        **kwargs: Any,  # noqa: ANN401
    ) -> tuple[ViewsUpdate, MetricsUpdate]:
        """Run detailed routing, killing the OpenROAD process tree on timeout."""
        timeout_s = int(self.config["FABULOUS_DRT_TIMEOUT"])
        timed_out = threading.Event()
        timers: list[threading.Timer] = []

        def _spawn(
            *args: Any,  # noqa: ANN401
            **inner_kwargs: Any,  # noqa: ANN401
        ) -> _GroupLeaderPopen:
            # Put OpenROAD (and any descendants it spawns, e.g. TritonRoute
            # workers) into a fresh process group so we can SIGKILL the whole
            # tree with a single os.killpg call.
            inner_kwargs["start_new_session"] = True
            proc = _GroupLeaderPopen(*args, **inner_kwargs)

            def _kill() -> None:
                timed_out.set()
                warn(
                    f"{self.id}: Detailed Routing exceeded {timeout_s}s; "
                    "killing OpenROAD process group."
                )
                with contextlib.suppress(ProcessLookupError, PermissionError):
                    os.killpg(os.getpgid(proc.pid), signal.SIGKILL)

            timer = threading.Timer(timeout_s, _kill)
            timer.daemon = True
            timer.start()
            timers.append(timer)
            return proc

        kwargs["_popen_callable"] = _spawn
        try:
            return super().run(state_in, **kwargs)
        except Exception as exc:
            if timed_out.is_set():
                raise DRTTimedOutError(
                    f"Detailed Routing exceeded {timeout_s}s timeout and was killed."
                ) from exc
            raise
        finally:
            for timer in timers:
                timer.cancel()

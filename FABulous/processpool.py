"""A custom ProcessPoolExecutor that uses dill for serialization."""

import multiprocessing
from concurrent.futures import ProcessPoolExecutor
from multiprocessing.reduction import ForkingPickler
from typing import Any

import dill


def _init_worker() -> None:
    """Initialize worker process to use dill for pickling."""
    # Override ForkingPickler with dill
    ForkingPickler.dumps = dill.dumps
    ForkingPickler.loads = dill.loads


class DillProcessPoolExecutor(ProcessPoolExecutor):
    """ProcessPoolExecutor that uses dill for serialization.

    This executor patches both the main process and worker processes to use dill instead
    of pickle, allowing serialization of thread locks and other complex objects that
    standard pickle cannot handle.
    """

    def __init__(
        self,
        max_workers: int | None = None,
        initargs: tuple[Any, ...] = (),
        max_tasks_per_child: int | None = None,
    ) -> None:
        ForkingPickler.dumps = dill.dumps
        ForkingPickler.loads = dill.loads
        super().__init__(
            max_workers=max_workers,
            mp_context=multiprocessing.get_context("spawn"),
            initializer=_init_worker,
            initargs=initargs,
            max_tasks_per_child=max_tasks_per_child,
        )

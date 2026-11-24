"""A custom ProcessPoolExecutor that uses dill for serialization."""

import multiprocessing
from concurrent.futures import ProcessPoolExecutor
from multiprocessing.reduction import ForkingPickler
from typing import Any

import dill

from fabulous.fabulous_settings import get_context


def _init_worker() -> None:
    """Initialize worker process to use dill for pickling."""
    # Override ForkingPickler with dill
    ForkingPickler.dumps = dill.dumps  # ty: ignore[invalid-assignment]
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
        ForkingPickler.dumps = dill.dumps  # ty: ignore[invalid-assignment]
        ForkingPickler.loads = dill.loads
        workers = max_workers if max_workers is not None else get_context().max_worker
        super().__init__(
            max_workers=workers or None,
            mp_context=multiprocessing.get_context("spawn"),
            initializer=_init_worker,
            initargs=initargs,
            max_tasks_per_child=max_tasks_per_child,
        )

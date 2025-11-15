import multiprocessing
from concurrent.futures import ProcessPoolExecutor

import dill


def _init_worker() -> None:
    """Initialize worker process to use dill for pickling."""
    from multiprocessing.reduction import ForkingPickler

    # Override ForkingPickler with dill
    ForkingPickler.dumps = dill.dumps
    ForkingPickler.loads = dill.loads


class DillProcessPoolExecutor(ProcessPoolExecutor):
    """ProcessPoolExecutor that uses dill for serialization.

    This executor patches both the main process and worker processes to use dill instead
    of pickle, allowing serialization of thread locks and other complex objects that
    standard pickle cannot handle.
    """

    def __init__(self, *args, **kwargs):
        # Patch the main process to use dill BEFORE calling parent init
        from multiprocessing.reduction import ForkingPickler

        ForkingPickler.dumps = dill.dumps
        ForkingPickler.loads = dill.loads
        super().__init__(
            *args,
            mp_context=multiprocessing.get_context("spawn"),
            initializer=_init_worker,
            **kwargs,
        )

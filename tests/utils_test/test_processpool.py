"""Tests for DillProcessPoolExecutor worker-count resolution.

A worker count of 0 (from either the explicit argument or the context setting)
means "use the system default"; ProcessPoolExecutor only accepts None for that,
so the executor must coerce 0 -> None rather than crash.
"""

# accessing the private _max_workers is the cleanest observable here
# ruff: noqa: SLF001

import multiprocessing
from concurrent.futures import ProcessPoolExecutor

import pytest
from pytest_mock import MockerFixture

from fabulous import processpool


@pytest.fixture
def default_worker_count() -> int:
    """The worker count ProcessPoolExecutor picks when given None."""
    executor = ProcessPoolExecutor(
        max_workers=None, mp_context=multiprocessing.get_context("spawn")
    )
    try:
        return executor._max_workers
    finally:
        executor.shutdown()


@pytest.mark.parametrize(
    ("max_workers", "context_max_worker", "expected"),
    [
        # None in `expected` stands for the system default worker count.
        pytest.param(0, 7, None, id="zero_arg_maps_to_default"),
        pytest.param(None, 0, None, id="zero_context_maps_to_default"),
        pytest.param(3, 7, 3, id="positive_arg_wins_over_context"),
        pytest.param(None, 5, 5, id="positive_context_preserved"),
    ],
)
def test_worker_count_resolution(
    mocker: MockerFixture,
    default_worker_count: int,
    max_workers: int | None,
    context_max_worker: int,
    expected: int | None,
) -> None:
    """An explicit argument overrides the context; 0 means the system default."""
    mocker.patch.object(
        processpool, "get_context"
    ).return_value.max_worker = context_max_worker
    executor = processpool.DillProcessPoolExecutor(max_workers=max_workers)
    try:
        assert executor._max_workers == (
            default_worker_count if expected is None else expected
        )
    finally:
        executor.shutdown()

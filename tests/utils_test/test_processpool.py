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
        return executor._max_workers  # ty: ignore[unresolved-attribute]
    finally:
        executor.shutdown()


class TestDillProcessPoolWorkers:
    """Worker-count resolution for DillProcessPoolExecutor."""

    def test_zero_arg_maps_to_default(
        self, mocker: MockerFixture, default_worker_count: int
    ) -> None:
        mocker.patch.object(processpool, "get_context")
        executor = processpool.DillProcessPoolExecutor(max_workers=0)
        try:
            assert executor._max_workers == default_worker_count  # ty: ignore[unresolved-attribute]
        finally:
            executor.shutdown()

    def test_zero_context_maps_to_default(
        self, mocker: MockerFixture, default_worker_count: int
    ) -> None:
        mocker.patch.object(processpool, "get_context").return_value.max_worker = 0
        executor = processpool.DillProcessPoolExecutor(max_workers=None)
        try:
            assert executor._max_workers == default_worker_count  # ty: ignore[unresolved-attribute]
        finally:
            executor.shutdown()

    def test_positive_arg_preserved(self, mocker: MockerFixture) -> None:
        mocker.patch.object(processpool, "get_context")
        executor = processpool.DillProcessPoolExecutor(max_workers=3)
        try:
            assert executor._max_workers == 3  # ty: ignore[unresolved-attribute]
        finally:
            executor.shutdown()

    def test_positive_context_preserved(self, mocker: MockerFixture) -> None:
        mocker.patch.object(processpool, "get_context").return_value.max_worker = 5
        executor = processpool.DillProcessPoolExecutor(max_workers=None)
        try:
            assert executor._max_workers == 5  # ty: ignore[unresolved-attribute]
        finally:
            executor.shutdown()

"""Tests for benchmark-driven inverse routing."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

from fabulous.fabric_cad.fabxplore.modules.inverse_router import (
    InverseRouter,
    InverseRouterOptions,
)
from fabulous.fabric_cad.fabxplore.pnr.fab_graph.core.models import (
    RoutingEndpoint,
    RoutingPip,
    RoutingPipKind,
    RoutingResourceKey,
    RoutingSwitchMatrix,
)
from fabulous.fabric_cad.fabxplore.utils.fabulous_fasm import parse_fabulous_fasm

if TYPE_CHECKING:
    from collections.abc import Callable, Iterator


def test_inverse_router_scores_prunes_applies_and_validates() -> None:
    """Score route FASM, prune matrix resources, and report validation routes."""
    matrix = RoutingSwitchMatrix(
        tile_type="LUT5F",
        rows=["E1END0", "E2END0", "E3END0"],
        columns=["LA_I0", "LA_I1", "LA_I2"],
        matrix=[
            [8.0, 0.0, 0.0],
            [0.0, 8.0, 0.0],
            [0.0, 0.0, 8.0],
        ],
    )
    graph = _FakePnRBridge(
        matrix=matrix,
        pips=[
            _matrix_pip((1, 5), "E1END0", "LA_I0"),
            _matrix_pip((1, 5), "E2END0", "LA_I1"),
            _matrix_pip((1, 5), "E3END0", "LA_I2"),
        ],
        routes_by_seed={
            1: [
                _FakeRouteResult(
                    passed=True,
                    fasm_text="""
                    X1Y5.E1END0.LA_I0
                    """,
                ),
                _FakeRouteResult(
                    passed=True,
                    fasm_text="""
                    X1Y5.E1END0.LA_I0
                    X1Y5.E2END0.LA_I1
                    """,
                ),
            ],
        },
    )
    options = InverseRouterOptions(
        tile_name="LUT5F",
        training_benchmarks={
            "bench_a": Path("bench_a.json"),
            "bench_b": Path("bench_b.json"),
        },
        test_benchmarks={"test_a": Path("test_a.json")},
        optimize_switch_matrix=True,
        switch_matrix_remove_unused_ratio=1.0,
        switch_matrix_remove_used_ratio=0.0,
        track_progress=False,
    )

    result = InverseRouter(options).run(graph)

    assert [route.passed for route in result.training_routes] == [True, True]
    assert result.switch_matrix_score is not None
    assert result.switch_matrix_score.matrix == [
        [2.0, 0.0, 0.0],
        [0.0, 1.0, 0.0],
        [0.0, 0.0, 0.0],
    ]
    assert result.final_switch_matrix is not None
    assert result.final_switch_matrix.rows == ["E1END0", "E2END0"]
    assert result.final_switch_matrix.columns == ["LA_I0", "LA_I1"]
    assert result.final_switch_matrix.matrix == [[1.0, 0.0], [0.0, 1.0]]
    assert graph.set_matrix_calls[-1].rows == ["E1END0", "E2END0"]
    assert result.switch_matrix_stats.candidates == 3
    assert result.switch_matrix_stats.removed_unused == 1
    assert result.switch_matrix_stats.removed_used == 0
    assert len(result.training_validation_routes) == 2
    assert len(result.test_validation_routes) == 1
    assert "Switch Matrix" in result.report_summary
    assert "External Tracks" not in result.report_summary


def test_inverse_router_disabled_optimization_scores_without_pruning() -> None:
    """Keep matrix score data but do not apply pruning when disabled."""
    matrix = RoutingSwitchMatrix(
        tile_type="LUT5F",
        rows=["E1END0", "E2END0"],
        columns=["LA_I0", "LA_I1"],
        matrix=[
            [8.0, 0.0],
            [0.0, 8.0],
        ],
    )
    graph = _FakePnRBridge(
        matrix=matrix,
        pips=[
            _matrix_pip((1, 5), "E1END0", "LA_I0"),
            _matrix_pip((1, 5), "E2END0", "LA_I1"),
        ],
        routes_by_seed={
            1: [
                _FakeRouteResult(
                    passed=True,
                    fasm_text="""
                    X1Y5.E1END0.LA_I0
                    """,
                ),
            ],
        },
    )
    options = InverseRouterOptions(
        tile_name="LUT5F",
        training_benchmarks={"bench_a": Path("bench_a.json")},
        optimize_switch_matrix=False,
        switch_matrix_remove_unused_ratio=1.0,
        validate_training=False,
        validate_test=False,
        track_progress=False,
    )

    result = InverseRouter(options).run(graph)

    assert result.switch_matrix_score.matrix == [[1.0, 0.0], [0.0, 0.0]]
    assert result.switch_matrix_stats.unused_candidates == 1
    assert result.switch_matrix_stats.removed_unused == 0
    assert result.switch_matrix_stats.kept == 2
    assert result.final_switch_matrix == matrix
    assert graph.set_matrix_calls == []


def test_inverse_router_can_remove_low_score_used_matrix_pips() -> None:
    """Prune positive-score matrix PIPs from lowest score upward when requested."""
    matrix = RoutingSwitchMatrix(
        tile_type="LUT5F",
        rows=["E1END0", "E2END0"],
        columns=["LA_I0", "LA_I1"],
        matrix=[
            [8.0, 0.0],
            [0.0, 8.0],
        ],
    )
    graph = _FakePnRBridge(
        matrix=matrix,
        pips=[
            _matrix_pip((1, 5), "E1END0", "LA_I0"),
            _matrix_pip((1, 5), "E2END0", "LA_I1"),
        ],
        routes_by_seed={
            1: [
                _FakeRouteResult(
                    passed=True,
                    fasm_text="""
                    X1Y5.E1END0.LA_I0
                    X1Y5.E2END0.LA_I1
                    """,
                ),
                _FakeRouteResult(
                    passed=True,
                    fasm_text="""
                    X1Y5.E1END0.LA_I0
                    """,
                ),
            ],
        },
    )
    options = InverseRouterOptions(
        tile_name="LUT5F",
        training_benchmarks={
            "bench_a": Path("bench_a.json"),
            "bench_b": Path("bench_b.json"),
        },
        optimize_switch_matrix=True,
        switch_matrix_remove_unused_ratio=0.0,
        switch_matrix_remove_used_ratio=0.5,
        validate_training=False,
        validate_test=False,
        track_progress=False,
    )

    result = InverseRouter(options).run(graph)

    assert result.switch_matrix_stats.removed_unused == 0
    assert result.switch_matrix_stats.removed_used == 1
    assert result.final_switch_matrix is not None
    assert result.final_switch_matrix.rows == ["E1END0"]
    assert result.final_switch_matrix.columns == ["LA_I0"]


def test_inverse_router_reports_failed_training_without_throwing() -> None:
    """Keep failed training routes in the result instead of raising."""
    graph = _FakePnRBridge(
        matrix=RoutingSwitchMatrix(
            tile_type="LUT5F",
            rows=["E1END0"],
            columns=["LA_I0"],
            matrix=[[8.0]],
        ),
        pips=[_matrix_pip((1, 5), "E1END0", "LA_I0")],
        routes_by_seed={1: [_FakeRouteResult(passed=False, fasm_text=None)]},
    )
    options = InverseRouterOptions(
        tile_name="LUT5F",
        training_benchmarks={"bench_a": Path("bench_a.json")},
        validate_training=False,
        validate_test=False,
        track_progress=False,
    )

    result = InverseRouter(options).run(graph)

    assert result.training_routes[0].passed is False
    assert result.training_routes[0].fasm_available is False
    assert result.switch_matrix_stats.unused_candidates == 1
    assert result.switch_matrix_stats.removed_unused == 0
    assert result.switch_matrix_stats.kept == 1
    assert result.final_switch_matrix == graph.switch_matrix("LUT5F")
    assert graph.set_matrix_calls == []
    assert result.pruning_skipped_reason is not None
    assert "pruning was skipped" in result.report_summary


@dataclass
class _FakeRouteResult:
    """Small nextpnr route result test double."""

    passed: bool
    fasm_text: str | None


class _FakePnRBridge:
    """Small PnR bridge test double for inverse-router tests."""

    def __init__(
        self,
        *,
        matrix: RoutingSwitchMatrix,
        pips: list[RoutingPip],
        routes_by_seed: dict[int, list[_FakeRouteResult]],
    ) -> None:
        self._matrix = matrix
        self._pips = pips
        self.routes_by_seed = routes_by_seed
        self.set_matrix_calls: list[RoutingSwitchMatrix] = []
        self._route_calls_by_seed: dict[int, int] = {}

    def switch_matrix(self, tile_type: str) -> RoutingSwitchMatrix:
        """Return the fake switch matrix."""
        assert tile_type == "LUT5F"
        return self._matrix

    def set_switch_matrix(
        self,
        tile_type: str,
        columns: list[str],
        rows: list[str],
        matrix: list[list[float]],
    ) -> None:
        """Store a fake switch-matrix update."""
        next_matrix = RoutingSwitchMatrix(
            tile_type=tile_type,
            columns=columns,
            rows=rows,
            matrix=matrix,
        )
        self._matrix = next_matrix
        self.set_matrix_calls.append(next_matrix)

    def nextpnr_batch_test(
        self,
        designs: dict[str, Path | dict[str, object]],
        *,
        pcf_assignment_seed: int,
        **_kwargs: object,
    ) -> list[_FakeRouteResult]:
        """Return fake route results for the requested seed."""
        call_index = self._route_calls_by_seed.get(pcf_assignment_seed, 0)
        self._route_calls_by_seed[pcf_assignment_seed] = call_index + 1
        if call_index > 0:
            return [_FakeRouteResult(passed=True, fasm_text="") for _design in designs]
        results = self.routes_by_seed[pcf_assignment_seed]
        return results[: len(designs)]

    def evaluate_fasm(self, fasm_text: str) -> object:
        """Evaluate FASM with the fake graph."""
        return parse_fabulous_fasm(fasm_text, self)

    def iter_active_pips(
        self,
        where: Callable[[RoutingPip], bool] | None = None,
    ) -> Iterator[RoutingPip]:
        """Yield fake active PIPs."""
        for pip in self._pips:
            if where is None or where(pip):
                yield pip

    def tile_type_at(self, x: int, y: int) -> str | None:
        """Return a fake tile type."""
        if (x, y) == (1, 5):
            return "LUT5F"
        return None


def _matrix_pip(owner: tuple[int, int], source: str, destination: str) -> RoutingPip:
    """Create a fake matrix PIP."""
    return RoutingPip(
        pip_id=None,
        kind=RoutingPipKind.INTERNAL_MATRIX,
        source=RoutingEndpoint(owner[0], owner[1], source),
        destination=RoutingEndpoint(owner[0], owner[1], destination),
        delay=8.0,
        name=f"{source}.{destination}",
        owner_tile=owner,
        tile_type="LUT5F",
        resource_key=RoutingResourceKey(
            tile_type="LUT5F",
            kind=RoutingPipKind.INTERNAL_MATRIX,
            source_name=source,
            destination_name=destination,
        ),
    )

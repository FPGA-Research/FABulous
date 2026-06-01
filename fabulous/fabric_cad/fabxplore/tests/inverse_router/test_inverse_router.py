"""Tests for benchmark-driven inverse routing."""

from __future__ import annotations

from dataclasses import dataclass, replace
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
    """Score route FASM, prune graph resources, and report validation routes."""
    ww4_key = _external_key("WW4BEG", "WW4END", 4)
    ee2_key = _external_key("EE2BEG", "EE2END", 2)
    ss1_key = _external_key("SS1BEG", "SS1END", 1)
    null1_key = _external_key("NULL", "TERM_END", 1)
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
    used_external_a = _pip(
        owner=(1, 5),
        source=(1, 5, "WW4BEG12"),
        destination=(0, 5, "WW4END8"),
        name="WW4BEG12.WW4END8",
        kind=RoutingPipKind.EXTERNAL_WIRE,
        resource_key=ww4_key,
    )
    used_external_b = _pip(
        owner=(1, 5),
        source=(1, 5, "EE2BEG0"),
        destination=(2, 5, "EE2END0"),
        name="EE2BEG0.EE2END0",
        kind=RoutingPipKind.EXTERNAL_WIRE,
        resource_key=ee2_key,
    )
    unused_external = _pip(
        owner=(1, 5),
        source=(1, 5, "SS1BEG0"),
        destination=(0, 5, "SS1END0"),
        name="SS1BEG0.SS1END0",
        kind=RoutingPipKind.EXTERNAL_WIRE,
        resource_key=ss1_key,
    )
    used_null_external = _pip(
        owner=(1, 5),
        source=(1, 5, "TERM_END0"),
        destination=(1, 5, "TERM_END0"),
        name="TERM_END0.TERM_END0",
        kind=RoutingPipKind.EXTERNAL_WIRE,
        resource_key=null1_key,
    )
    graph = _FakePnRBridge(
        matrix=matrix,
        pips=[
            _matrix_pip((1, 5), "E1END0", "LA_I0"),
            _matrix_pip((1, 5), "E2END0", "LA_I1"),
            _matrix_pip((1, 5), "E3END0", "LA_I2"),
            used_external_a,
            used_external_b,
            unused_external,
            used_null_external,
        ],
        routes_by_seed={
            1: [
                _FakeRouteResult(
                    passed=True,
                    fasm_text="""
                    X1Y5.E1END0.LA_I0
                    X1Y5.WW4BEG12.WW4END8
                    X1Y5.TERM_END0.TERM_END0
                    """,
                ),
                _FakeRouteResult(
                    passed=True,
                    fasm_text="""
                    X1Y5.E1END0.LA_I0
                    X1Y5.E2END0.LA_I1
                    X1Y5.EE2BEG0.EE2END0
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
        optimize_external_pips=True,
        external_remove_unused_ratio=1.0,
        external_remove_used_ratio=0.0,
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
    assert result.external_scores == {
        (ww4_key, 0): 1,
        (ww4_key, 1): 0,
        (ww4_key, 2): 0,
        (ww4_key, 3): 0,
        (ee2_key, 0): 1,
        (ee2_key, 1): 0,
        (ss1_key, 0): 0,
        (null1_key, 0): 1,
    }
    assert result.final_external_pips == [
        (ww4_key, 0),
        (ee2_key, 0),
        (null1_key, 0),
    ]
    assert result.removed_external_pips == [
        (ww4_key, 1),
        (ww4_key, 2),
        (ww4_key, 3),
        (ee2_key, 1),
        (ss1_key, 0),
    ]
    assert graph.removed_external_tracks == [
        (ww4_key, 3),
        (replace(ww4_key, wire_count=3), 2),
        (replace(ww4_key, wire_count=2), 1),
        (ee2_key, 1),
        (ss1_key, 0),
    ]
    assert len(result.training_validation_routes) == 2
    assert len(result.test_validation_routes) == 1
    assert "Switch Matrix" in result.report_summary
    assert "External Tracks" in result.report_summary


def test_inverse_router_disabled_optimization_scores_without_pruning() -> None:
    """Keep score data but do not select removals when optimization is disabled."""
    ww4_key = _external_key("WW4BEG", "WW4END", 4)
    ss1_key = _external_key("SS1BEG", "SS1END", 1)
    matrix = RoutingSwitchMatrix(
        tile_type="LUT5F",
        rows=["E1END0", "E2END0"],
        columns=["LA_I0", "LA_I1"],
        matrix=[
            [8.0, 0.0],
            [0.0, 8.0],
        ],
    )
    used_external = _pip(
        owner=(1, 5),
        source=(1, 5, "WW4BEG12"),
        destination=(0, 5, "WW4END8"),
        name="WW4BEG12.WW4END8",
        kind=RoutingPipKind.EXTERNAL_WIRE,
        resource_key=ww4_key,
    )
    unused_external = _pip(
        owner=(1, 5),
        source=(1, 5, "SS1BEG0"),
        destination=(0, 5, "SS1END0"),
        name="SS1BEG0.SS1END0",
        kind=RoutingPipKind.EXTERNAL_WIRE,
        resource_key=ss1_key,
    )
    graph = _FakePnRBridge(
        matrix=matrix,
        pips=[
            _matrix_pip((1, 5), "E1END0", "LA_I0"),
            _matrix_pip((1, 5), "E2END0", "LA_I1"),
            used_external,
            unused_external,
        ],
        routes_by_seed={
            1: [
                _FakeRouteResult(
                    passed=True,
                    fasm_text="""
                    X1Y5.E1END0.LA_I0
                    X1Y5.WW4BEG12.WW4END8
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
        optimize_external_pips=False,
        external_remove_unused_ratio=1.0,
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
    assert result.external_scores == {
        (ww4_key, 0): 1,
        (ww4_key, 1): 0,
        (ww4_key, 2): 0,
        (ww4_key, 3): 0,
        (ss1_key, 0): 0,
    }
    assert result.external_stats.unused_candidates == 4
    assert result.external_stats.removed_unused == 0
    assert result.external_stats.kept == 5
    assert result.final_external_pips == [
        (ww4_key, 0),
        (ww4_key, 1),
        (ww4_key, 2),
        (ww4_key, 3),
        (ss1_key, 0),
    ]
    assert result.removed_external_pips == []
    assert graph.removed_external_tracks == []


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
    assert result.switch_matrix_stats.removed_unused == 1


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
        self.removed_external_tracks: list[tuple[RoutingResourceKey, int]] = []

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

    def remove_external_resource_track(
        self,
        *,
        key: RoutingResourceKey,
        track_index: int,
    ) -> RoutingResourceKey:
        """Store a fake removed external track and return the compacted key."""
        self.removed_external_tracks.append((key, track_index))
        if key.wire_count == 1:
            return key
        assert key.wire_count is not None
        return replace(key, wire_count=key.wire_count - 1)

    def nextpnr_batch_test(
        self,
        designs: dict[str, Path | dict[str, object]],
        *,
        pcf_assignment_seed: int,
        **_kwargs: object,
    ) -> list[_FakeRouteResult]:
        """Return fake route results for the requested seed."""
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

    def external_resources(
        self,
        tile_type: str | None = None,
        *,
        active_only: bool = True,
        where: Callable[[RoutingResourceKey], bool] | None = None,
    ) -> list[RoutingResourceKey]:
        """Return fake external resources."""
        del active_only
        resources: dict[RoutingResourceKey, RoutingResourceKey] = {}
        for pip in self._pips:
            key = pip.resource_key
            if key.kind is not RoutingPipKind.EXTERNAL_WIRE:
                continue
            if tile_type is not None and key.tile_type != tile_type:
                continue
            if where is not None and not where(key):
                continue
            resources.setdefault(key, key)
        return list(resources.values())

    def tile_type_at(self, x: int, y: int) -> str | None:
        """Return a fake tile type."""
        if (x, y) in {(1, 5), (0, 5), (2, 5)}:
            return "LUT5F"
        return None


def _matrix_pip(owner: tuple[int, int], source: str, destination: str) -> RoutingPip:
    """Create a fake matrix PIP."""
    return _pip(
        owner=owner,
        source=(owner[0], owner[1], source),
        destination=(owner[0], owner[1], destination),
        name=f"{source}.{destination}",
        kind=RoutingPipKind.INTERNAL_MATRIX,
    )


def _pip(
    *,
    owner: tuple[int, int],
    source: tuple[int, int, str],
    destination: tuple[int, int, str],
    name: str,
    kind: RoutingPipKind,
    resource_key: RoutingResourceKey | None = None,
) -> RoutingPip:
    """Create a fake routing PIP."""
    return RoutingPip(
        pip_id=None,
        kind=kind,
        source=RoutingEndpoint(source[0], source[1], source[2]),
        destination=RoutingEndpoint(destination[0], destination[1], destination[2]),
        delay=8.0,
        name=name,
        owner_tile=owner,
        tile_type="LUT5F",
        resource_key=resource_key
        or RoutingResourceKey(
            tile_type="LUT5F",
            kind=kind,
            source_name=source[2],
            destination_name=destination[2],
        ),
    )


def _external_key(
    source_name: str,
    destination_name: str,
    wire_count: int,
) -> RoutingResourceKey:
    """Create a fake tile-local external resource key."""
    return RoutingResourceKey(
        tile_type="LUT5F",
        kind=RoutingPipKind.EXTERNAL_WIRE,
        source_name=source_name,
        destination_name=destination_name,
        wire_count=wire_count,
    )

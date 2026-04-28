"""Tests for GlobalTileSizeOptimization NLP problem helpers.

The Pareto frontier helper is the most failure-prone part of the NLP setup: a
flipped iteration direction silently locks the body row to the worst-aspect
sample, producing 1:8 rectangles for square-ish tiles. These tests pin the
correct algorithm so that regression cannot reappear unnoticed.
"""

# for testing private methods
# ruff: noqa: SLF001

import json
from pathlib import Path

import pytest

from fabulous.fabric_generator.gds_generator.steps.global_tile_opitmisation import (
    GlobalTileSizeOptimization,
    NLPTileProblem,
)
from fabulous.fabric_generator.gds_generator.steps.tile_optimisation import OptMode


class TestParetoFrontier:
    """Unit tests for NLPTileProblem._pareto_frontier."""

    def test_empty_input_returns_empty(self) -> None:
        assert NLPTileProblem._pareto_frontier([]) == []

    def test_single_sample_round_trips(self) -> None:
        assert NLPTileProblem._pareto_frontier([(100.0, 50.0)]) == [(100.0, 50.0)]

    def test_keeps_wide_short_alongside_narrow_tall(self) -> None:
        """Two samples with opposite trade-offs are both Pareto-optimal."""
        # (236.16, 470.4) and (127.68, 1034.88) are mutually non-dominated:
        # neither has both smaller w AND smaller h. This is the DSP supertile
        # case from the demo project that the buggy frontier discarded.
        samples = [(127.68, 1034.88), (236.16, 470.4)]
        frontier = NLPTileProblem._pareto_frontier(samples)

        assert (236.16, 470.4) in frontier
        assert (127.68, 1034.88) in frontier
        assert len(frontier) == 2

    def test_drops_dominated_samples(self) -> None:
        """A sample that is wider AND taller than another is dominated and dropped."""
        # (200, 200) dominates (300, 300) — keep the former, drop the latter.
        samples = [(300.0, 300.0), (200.0, 200.0), (250.0, 250.0)]
        frontier = NLPTileProblem._pareto_frontier(samples)
        assert frontier == [(200.0, 200.0)]

    def test_dedupes_equal_height_samples_keeping_smallest_w(self) -> None:
        """At the same h, only the smallest-w sample survives."""
        samples = [(150.0, 100.0), (100.0, 100.0), (200.0, 100.0)]
        frontier = NLPTileProblem._pareto_frontier(samples)
        assert frontier == [(100.0, 100.0)]

    def test_output_sorted_by_h_ascending(self) -> None:
        """Frontier is sorted by h ascending, w strictly decreasing along it."""
        # Real LUT4AB samples from the demo project's exploration:
        samples = [
            (582.72, 108.36),  # FIND_MIN_WIDTH probe
            (238.08, 271.74),  # BALANCE final
            (120.96, 1310.4),  # FIND_MIN_HEIGHT final
            (731.52, 108.36),  # dominated by (582.72, 108.36) at same h
        ]
        frontier = NLPTileProblem._pareto_frontier(samples)
        assert frontier == [
            (582.72, 108.36),
            (238.08, 271.74),
            (120.96, 1310.4),
        ]
        # Heights strictly increase, widths strictly decrease.
        for prev, curr in zip(frontier, frontier[1:], strict=False):
            assert curr[1] > prev[1]
            assert curr[0] < prev[0]

    @pytest.mark.parametrize(
        ("samples", "expected_first_w_h", "expected_last_w_h"),
        [
            pytest.param(
                # DSP supertile: balance (236, 470), find_min_height probes
                # at w=127.68 with various h. Frontier should include both
                # the wide+short balance sample AND the narrow+tall extremes.
                [
                    (236.16, 470.4),
                    (127.68, 828.24),
                    (127.68, 1034.88),
                    (127.68, 916.02),
                ],
                (236.16, 470.4),
                (127.68, 828.24),
                id="dsp-supertile-frontier",
            ),
            pytest.param(
                # W_IO real samples — has 3 frontier points.
                [
                    (108.48, 142.38),
                    (20.16, 1338.96),
                    (125.76, 108.36),
                    (249.6, 108.36),  # dominated by (125.76, 108.36)
                ],
                (125.76, 108.36),
                (20.16, 1338.96),
                id="w-io-frontier",
            ),
        ],
    )
    def test_real_demo_project_frontiers(
        self,
        samples: list[tuple[float, float]],
        expected_first_w_h: tuple[float, float],
        expected_last_w_h: tuple[float, float],
    ) -> None:
        """Lock in the frontier shape for representative tiles from the demo."""
        frontier = NLPTileProblem._pareto_frontier(samples)
        assert frontier[0] == expected_first_w_h
        assert frontier[-1] == expected_last_w_h
        # Every kept sample is non-dominated by every other kept sample.
        for i, (w_i, h_i) in enumerate(frontier):
            for j, (w_j, h_j) in enumerate(frontier):
                if i == j:
                    continue
                assert not (w_j <= w_i and h_j <= h_i and (w_j, h_j) != (w_i, h_i)), (
                    f"{frontier[j]} dominates {frontier[i]}"
                )


class TestEnvelopeWFloor:
    """Piecewise-linear lower bound on width given a row height.

    The Pareto frontier delivered by ``_pareto_frontier`` is sorted by ``h``
    ascending and ``w`` descending — that monotone shape is the precondition
    of the linear interpolation used here.
    """

    def test_no_samples_returns_zero(self) -> None:
        # No exploration data -> no constraint, the floor is 0.
        assert NLPTileProblem._envelope_w_floor(100.0, []) == 0.0

    def test_below_sample_range_clamps_to_first(self) -> None:
        # The frontier is sorted by h ascending; below the smallest h we clamp
        # to the widest sample. This is the correct convex lower bound.
        samples = [(200.0, 50.0), (100.0, 100.0)]
        assert NLPTileProblem._envelope_w_floor(10.0, samples) == 200.0
        # And exactly at the smallest h.
        assert NLPTileProblem._envelope_w_floor(50.0, samples) == 200.0

    def test_above_sample_range_clamps_to_last(self) -> None:
        samples = [(200.0, 50.0), (100.0, 100.0)]
        assert NLPTileProblem._envelope_w_floor(999.0, samples) == 100.0
        # And exactly at the largest h.
        assert NLPTileProblem._envelope_w_floor(100.0, samples) == 100.0

    def test_inside_range_linearly_interpolates(self) -> None:
        # Between (200, 50) and (100, 100): at h=75 (midpoint) -> w=150.
        samples = [(200.0, 50.0), (100.0, 100.0)]
        assert NLPTileProblem._envelope_w_floor(75.0, samples) == 150.0

    def test_three_segment_envelope_picks_correct_segment(self) -> None:
        # Three Pareto points -> two interpolation segments.
        samples = [(300.0, 10.0), (200.0, 20.0), (100.0, 40.0)]
        # h=15 is in [10, 20]: w = 300 + (200-300)*(15-10)/(20-10) = 250.
        assert NLPTileProblem._envelope_w_floor(15.0, samples) == 250.0
        # h=30 is in [20, 40]: w = 200 + (100-200)*(30-20)/(40-20) = 150.
        assert NLPTileProblem._envelope_w_floor(30.0, samples) == 150.0


class TestComputeEquivalenceClasses:
    """Union-find groupings: tiles that share rows pull those rows together."""

    def test_disjoint_rows_form_separate_groups(self) -> None:
        # Tile A occupies rows {0, 1}; tile B occupies rows {3}. No overlap,
        # so {0, 1} merge into one group and {3} stays alone.
        positions = {"A": {0, 1}, "B": {3}}
        groups: dict[int, int] = {}
        NLPTileProblem._compute_equivalence_classes(positions, groups)

        # Indices in the same set should hash to the same group.
        assert groups[0] == groups[1]
        # Different sets should hash to different groups.
        assert groups[0] != groups[3]
        # Every input index must appear in the result.
        assert set(groups.keys()) == {0, 1, 3}

    def test_shared_row_merges_two_tile_groups(self) -> None:
        # Tile A on rows {0, 1}, tile B on rows {1, 2}: the shared row 1
        # forces all three indices into one equivalence class.
        positions = {"A": {0, 1}, "B": {1, 2}}
        groups: dict[int, int] = {}
        NLPTileProblem._compute_equivalence_classes(positions, groups)

        assert groups[0] == groups[1] == groups[2]

    def test_empty_input_yields_empty_groups(self) -> None:
        groups: dict[int, int] = {}
        NLPTileProblem._compute_equivalence_classes({}, groups)
        assert groups == {}


class TestFindSharingTiles:
    """Sets of tiles that share at least one row or column with the target."""

    def test_returns_only_overlapping_neighbours(self) -> None:
        positions = {
            "A": {0, 1},
            "B": {1, 2},  # shares row 1 with A
            "C": {3},  # disjoint from A
        }
        # The implementation excludes the target itself.
        assert NLPTileProblem._find_sharing_tiles("A", positions) == {"B"}

    def test_returns_empty_when_no_overlap(self) -> None:
        positions = {"A": {0}, "B": {1}, "C": {2}}
        assert NLPTileProblem._find_sharing_tiles("A", positions) == set()

    def test_target_itself_never_in_result(self) -> None:
        # Tile A only occupies rows it shares with itself; result must skip A.
        positions = {"A": {0, 1, 2}}
        assert NLPTileProblem._find_sharing_tiles("A", positions) == set()


class TestParseTileFields:
    """``_parse_tile_fields`` converts JSON strings/lists into typed metric values."""

    def test_parses_required_bbox_strings_to_floats(self) -> None:
        # Bbox fields arrive as space-separated strings and must come out as
        # 4-tuples of floats.
        out = GlobalTileSizeOptimization._parse_tile_fields(
            {
                "design__die__bbox": "0 0 100 200",
                "design__core__bbox": "1 2 99 198",
            }
        )
        assert out["design__die__bbox"] == [0.0, 0.0, 100.0, 200.0]
        assert out["design__core__bbox"] == [1.0, 2.0, 99.0, 198.0]

    def test_optional_scalar_fields_passed_through_as_floats(self) -> None:
        out = GlobalTileSizeOptimization._parse_tile_fields(
            {
                "design__die__bbox": "0 0 100 100",
                "design__core__bbox": "0 0 100 100",
                "fabulous__pin_min_width": "12.5",
                "fabulous__pin_min_height": 7.0,
                "design__instance__area__stdcell": "999",
            }
        )
        assert out["fabulous__pin_min_width"] == 12.5
        assert out["fabulous__pin_min_height"] == 7.0
        assert out["design__instance__area__stdcell"] == 999.0

    def test_optional_fields_omitted_when_none(self) -> None:
        # Explicitly None scalars must not appear in the output.
        out = GlobalTileSizeOptimization._parse_tile_fields(
            {
                "design__die__bbox": "0 0 100 100",
                "design__core__bbox": "0 0 100 100",
                "fabulous__pin_min_width": None,
            }
        )
        assert "fabulous__pin_min_width" not in out

    def test_clean_probes_parsed_into_nested_floats(self) -> None:
        # Each probe is a list of stringly-typed numerics; output is float-of-float.
        out = GlobalTileSizeOptimization._parse_tile_fields(
            {
                "design__die__bbox": "0 0 100 100",
                "design__core__bbox": "0 0 100 100",
                "fabulous__clean_probes": [["0", "0", "50", "60"], [0, 0, 70, 80]],
            }
        )
        assert out["fabulous__clean_probes"] == [
            [0.0, 0.0, 50.0, 60.0],
            [0.0, 0.0, 70.0, 80.0],
        ]

    def test_missing_bbox_raises_typeerror(self) -> None:
        with pytest.raises(TypeError, match="design__die__bbox"):
            GlobalTileSizeOptimization._parse_tile_fields(
                {"design__core__bbox": "0 0 1 1"}
            )

    def test_non_string_bbox_raises_typeerror(self) -> None:
        # Lists / numbers are not accepted — bbox must be a string.
        with pytest.raises(TypeError, match="design__die__bbox"):
            GlobalTileSizeOptimization._parse_tile_fields(
                {
                    "design__die__bbox": [0, 0, 1, 1],
                    "design__core__bbox": "0 0 1 1",
                }
            )


class TestLoadTileMetricsFromJson:
    """End-to-end deserialisation of the per-mode metric file produced by the
    exploration phase. The function partitions tiles into:

    - ``valid_data``: tiles whose exploration found a working state
      (used for feasibility constraints).
    - ``all_data``: every tile that has a bbox, including those that never
      compiled (used for lower-bound estimates only).
    """

    def test_partitions_valid_and_all_metrics(self, tmp_path: Path) -> None:
        # "good" tile compiled cleanly; "broken" tile has a bbox but
        # exploration eventually gave up with "No working state found".
        # The latter is included in all_data but excluded from valid_data.
        payload = {
            OptMode.BALANCE.value: {
                "good": {
                    "design__die__bbox": "0 0 100 100",
                    "design__core__bbox": "0 0 100 100",
                },
                "broken": {
                    "design__die__bbox": "0 0 50 50",
                    "design__core__bbox": "0 0 50 50",
                    "error_traceback": "RuntimeError: No working state found",
                },
            }
        }
        path = tmp_path / "metrics.json"
        path.write_text(json.dumps(payload))

        valid, all_ = GlobalTileSizeOptimization._load_tile_metrics_from_json(path)

        assert OptMode.BALANCE in valid
        assert "good" in valid[OptMode.BALANCE]
        assert "broken" not in valid[OptMode.BALANCE]
        assert "good" in all_[OptMode.BALANCE]
        assert "broken" in all_[OptMode.BALANCE]

    def test_skips_entries_without_bbox(self, tmp_path: Path) -> None:
        # No bbox -> nothing to constrain; the entry is dropped from both dicts.
        payload = {
            OptMode.BALANCE.value: {
                "no_bbox": {"error": "compilation failed"},
            }
        }
        path = tmp_path / "metrics.json"
        path.write_text(json.dumps(payload))

        valid, all_ = GlobalTileSizeOptimization._load_tile_metrics_from_json(path)
        assert valid[OptMode.BALANCE] == {}
        assert all_[OptMode.BALANCE] == {}

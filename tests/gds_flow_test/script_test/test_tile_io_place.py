"""Tests for tile_io_place module."""
# ruff: noqa: E402, SLF001, E501, F841

import os
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace
from typing import TYPE_CHECKING

import pytest
import yaml
from conftest import MockDie, MockLayer, MockTechIoPlace, PinPlacementRecorder
from pytest_mock import MockerFixture, MockType

from fabulous.fabric_definition.define import PinSortMode, Side
from fabulous.fabric_generator.gds_generator.gen_io_pin_config_yaml import (
    PinOrderConfig,
)
from fabulous.fabric_generator.gds_generator.helper import round_die_dimension
from fabulous.fabric_generator.gds_generator.script import tile_io_place
from fabulous.fabric_generator.gds_generator.script.tile_io_place import (
    PinPlacementPlan,
    SegmentInfo,
    equally_spaced_sequence,
    filter_pin_tracks_by_stride_and_distance,
    grid_to_tracks,
)

if TYPE_CHECKING:
    from fabulous.fabric_generator.gds_generator.script.odb_protocol import odbBTermLike


def _make_bterms(mocker: MockerFixture, names: list[str]) -> list[MockType]:
    """Build one mock BTerm per name, in the given order."""
    bterms = []
    for name in names:
        bterm = mocker.Mock()
        bterm.getName.return_value = name
        bterms.append(bterm)
    return bterms


@pytest.mark.parametrize(
    ("origin", "count", "step", "expected"),
    [
        pytest.param(0.0, 5, 100.0, [0.0, 100.0, 200.0, 300.0, 400.0], id="basic"),
        pytest.param(-100.0, 3, 50.0, [-100.0, -50.0, 0.0], id="negative-origin"),
        pytest.param(500.0, 1, 100.0, [500.0], id="single-track"),
        pytest.param(
            1000.0, 4, -250.0, [250.0, 500.0, 750.0, 1000.0], id="negative-step-sorted"
        ),
    ],
)
def test_grid_to_tracks(
    origin: float, count: int, step: float, expected: list[float]
) -> None:
    """Tracks start at the origin, advance by the step and come back ascending."""
    assert grid_to_tracks(origin, count, step) == expected


class TestEquallySpacedSequence:
    """Test suite for equally_spaced_sequence function."""

    def test_pins_equal_tracks(self, mocker: MockerFixture) -> None:
        """Test when number of pins equals number of tracks."""
        mock_pins: list[int | odbBTermLike] = [
            mocker.Mock(getName=lambda i=i: f"pin{i}") for i in range(5)
        ]
        tracks = [0.0, 100.0, 200.0, 300.0, 400.0]

        result = equally_spaced_sequence(mock_pins, tracks)

        assert result == list(zip(tracks, mock_pins, strict=True))

    def test_pins_less_than_tracks(self, mocker: MockerFixture) -> None:
        """Test even spacing when pins < tracks."""
        mock_pins: list[int | odbBTermLike] = [
            mocker.Mock(getName=lambda i=i: f"pin{i}") for i in range(3)
        ]
        tracks = [0.0, 100.0, 200.0, 300.0, 400.0, 500.0, 600.0]

        result = equally_spaced_sequence(mock_pins, tracks)

        # Two tracks per pin, the one spare track split evenly at both ends.
        assert result == [
            (100.0, mock_pins[0]),
            (300.0, mock_pins[1]),
            (500.0, mock_pins[2]),
        ]

    def test_no_pins(self) -> None:
        """Test with no pins."""
        tracks = [0.0, 100.0, 200.0]

        result = equally_spaced_sequence([], tracks)

        assert result == []

    def test_with_virtual_pins(self, mocker: MockerFixture) -> None:
        """Test spacing with virtual pins (integers in list)."""
        mock_pins: list[int | odbBTermLike] = [
            mocker.Mock(getName=lambda: "pin0"),
            2,
            mocker.Mock(getName=lambda: "pin1"),
        ]
        tracks = [0.0, 100.0, 200.0, 300.0, 400.0, 500.0, 600.0, 700.0]

        result = equally_spaced_sequence(mock_pins, tracks)

        # 4 slots over 8 tracks: the 2 virtual slots push pin1 to the 4th slot.
        assert result == [(0.0, mock_pins[0]), (600.0, mock_pins[2])]

    def test_too_many_pins(self, mocker: MockerFixture) -> None:
        """Test error when pins exceed available tracks."""
        mock_pins: list[int | odbBTermLike] = [
            mocker.Mock(getName=lambda i=i: f"pin{i}") for i in range(10)
        ]
        tracks = [0.0, 100.0, 200.0]

        with pytest.raises(SystemExit) as exc_info:
            equally_spaced_sequence(mock_pins, tracks)

        assert exc_info.value.code == 1


class TestSegmentInfo:
    """Test suite for SegmentInfo dataclass."""

    def test_from_config_basic(self, mocker: MockerFixture) -> None:
        """Test basic SegmentInfo creation from config."""
        segment_config = PinOrderConfig(
            pins=["pin.*"],
            sort_mode=PinSortMode.BUS_MAJOR,
            min_distance=None,
            max_distance=None,
            reverse_result=False,
        )

        mock_bterm = mocker.Mock()
        mock_bterm.getName.return_value = "pin_test"
        bterms = [mock_bterm]
        regex_by_bterm = {}
        unmatched = set()

        seg_info = SegmentInfo.from_config(
            Side.NORTH,
            segment_config,
            bterms,
            regex_by_bterm,
            unmatched,
        )

        assert seg_info == SegmentInfo(
            side=Side.NORTH,
            sort_mode=PinSortMode.BUS_MAJOR,
            min_distance=None,
            max_distance=None,
            reverse_result=False,
            pin_entries=[mock_bterm],
        )
        assert regex_by_bterm == {mock_bterm: "pin.*"}
        assert unmatched == set()

    def test_from_config_with_virtual_pins(self, mocker: MockerFixture) -> None:
        """Test SegmentInfo with virtual pins."""
        segment_config = PinOrderConfig(
            pins=["pin1", 3, "pin2"],
            sort_mode=PinSortMode.BIT_MINOR,
            min_distance=1,
            max_distance=5,
            reverse_result=True,
        )

        mock_bterm1 = mocker.Mock()
        mock_bterm1.getName.return_value = "pin1"
        mock_bterm2 = mocker.Mock()
        mock_bterm2.getName.return_value = "pin2"
        bterms = [mock_bterm1, mock_bterm2]

        seg_info = SegmentInfo.from_config(
            Side.EAST,
            segment_config,
            bterms,
            {},
            set(),
            tile_index=2,
            tile_x=3,
            tile_y=1,
        )

        assert seg_info == SegmentInfo(
            side=Side.EAST,
            sort_mode=PinSortMode.BIT_MINOR,
            min_distance=1,
            max_distance=5,
            reverse_result=True,
            pin_entries=[mock_bterm1, 3, mock_bterm2],
            tile_index=2,
            tile_x=3,
            tile_y=1,
        )

    def test_actual_pin_count(self, mocker: MockerFixture) -> None:
        """Test actual_pin_count property."""
        seg_info = SegmentInfo(
            side=Side.NORTH,
            sort_mode=PinSortMode.BUS_MAJOR,
            min_distance=None,
            max_distance=None,
            reverse_result=False,
            pin_entries=[mocker.Mock(), 2, mocker.Mock(), 3, mocker.Mock()],
        )

        assert seg_info.actual_pin_count == 3

    def test_invalid_sort_mode(self) -> None:
        """A sort_mode outside `PinSortMode` is rejected naming the bad value."""
        # Segments are built straight from YAML, so sort_mode arrives as a raw
        # string and is looked up by member name.
        segment_config = PinOrderConfig(
            pins=["pin.*"],
            sort_mode="invalid_mode",
            min_distance=None,
            max_distance=None,
            reverse_result=False,
        )

        with pytest.raises(ValueError, match="Invalid sort_mode 'invalid_mode'"):
            SegmentInfo.from_config(Side.NORTH, segment_config, [], {}, set())

    def test_duplicate_regex_match(self, mocker: MockerFixture) -> None:
        """Test error when multiple regexes match same pin."""
        segment_config1 = PinOrderConfig(
            pins=["pin.*"],
            sort_mode=PinSortMode.BUS_MAJOR,
            min_distance=None,
            max_distance=None,
            reverse_result=False,
        )
        segment_config2 = PinOrderConfig(
            pins=["pin_test"],
            sort_mode=PinSortMode.BUS_MAJOR,
            min_distance=None,
            max_distance=None,
            reverse_result=False,
        )

        mock_bterm = mocker.Mock()
        mock_bterm.getName.return_value = "pin_test"
        bterms = [mock_bterm]
        regex_by_bterm = {}

        # First match should succeed
        SegmentInfo.from_config(
            Side.NORTH,
            segment_config1,
            bterms,
            regex_by_bterm,
            set(),
        )

        # Second match should fail
        with pytest.raises(SystemExit):
            SegmentInfo.from_config(
                Side.NORTH,
                segment_config2,
                bterms,
                regex_by_bterm,
                set(),
            )


class TestPinPlacementPlan:
    """Test suite for PinPlacementPlan class."""

    def test_init_empty_config(self) -> None:
        """Test initialization with empty config."""
        plan = PinPlacementPlan({}, [], "none")

        assert plan.segments_by_side == {side: [] for side in Side}
        assert plan.tile_counts_by_side == {side: 0 for side in Side}
        assert plan.fabric_dimensions == (1, 1)

    def test_init_basic_config(self, mocker: MockerFixture) -> None:
        """A single-tile config yields one segment carrying the matched pins."""
        config = {
            "X0Y0": {
                "NORTH": [
                    {
                        "pins": ["clk", "rst"],
                        "sort_mode": "bus_major",
                        "min_distance": None,
                        "max_distance": None,
                        "reverse_result": False,
                    }
                ]
            }
        }
        mock_clk, mock_rst = _make_bterms(mocker, ["clk", "rst"])

        plan = PinPlacementPlan(config, [mock_clk, mock_rst], "none")

        assert plan.segments_by_side == {
            Side.NORTH: [
                SegmentInfo(
                    side=Side.NORTH,
                    sort_mode=PinSortMode.BUS_MAJOR,
                    min_distance=None,
                    max_distance=None,
                    reverse_result=False,
                    pin_entries=[mock_clk, mock_rst],
                    tile_index=0,
                    tile_x=0,
                    tile_y=0,
                )
            ],
            Side.SOUTH: [],
            Side.EAST: [],
            Side.WEST: [],
            Side.ANY: [],
        }
        assert plan.tile_counts_by_side == {
            Side.NORTH: 1,
            Side.SOUTH: 0,
            Side.EAST: 0,
            Side.WEST: 0,
            Side.ANY: 0,
        }
        assert plan.fabric_dimensions == (1, 1)

    @pytest.mark.parametrize(
        ("config", "expected_dims", "expected_tiles_by_side"),
        [
            pytest.param(
                {
                    "X0Y0": {"NORTH": [{"pins": ["pin0"], "sort_mode": "bus_major"}]},
                    "X1Y0": {"NORTH": [{"pins": ["pin1"], "sort_mode": "bus_major"}]},
                    "X2Y1": {"EAST": [{"pins": ["pin2"], "sort_mode": "bus_major"}]},
                },
                (3, 2),
                {Side.NORTH: [(0, 0, 0), (1, 1, 0)], Side.EAST: [(0, 2, 1)]},
                id="3x2",
            ),
            pytest.param(
                # X2Y0 listed first: segment order must follow the x coordinate.
                {
                    "X2Y0": {"NORTH": [{"pins": ["pin1"], "sort_mode": "bus_major"}]},
                    "X0Y0": {"NORTH": [{"pins": ["pin0"], "sort_mode": "bus_major"}]},
                    "X1Y3": {"EAST": [{"pins": ["pin2"], "sort_mode": "bus_major"}]},
                },
                (3, 4),
                {Side.NORTH: [(0, 0, 0), (1, 2, 0)], Side.EAST: [(0, 1, 3)]},
                id="3x4-unordered",
            ),
        ],
    )
    def test_init_multi_tile_config(
        self,
        mocker: MockerFixture,
        config: dict,
        expected_dims: tuple[int, int],
        expected_tiles_by_side: dict[Side, list[tuple[int, int, int]]],
    ) -> None:
        """Fabric size, per-side tile counts and segment tile order follow the keys."""
        plan = PinPlacementPlan(
            config, _make_bterms(mocker, ["pin0", "pin1", "pin2"]), "none"
        )

        assert plan.fabric_dimensions == expected_dims
        assert plan.tile_counts_by_side == {
            side: len(expected_tiles_by_side.get(side, [])) for side in Side
        }
        tiles_by_side = {
            side: [(seg.tile_index, seg.tile_x, seg.tile_y) for seg in segments]
            for side, segments in plan.segments_by_side.items()
            if segments
        }
        assert tiles_by_side == expected_tiles_by_side

    def test_unmatched_design_pins(self, mocker: MockerFixture) -> None:
        """Test handling of unmatched design pins."""
        config = {"X0Y0": {"NORTH": [{"pins": ["clk"], "sort_mode": "bus_major"}]}}
        mock_clk, mock_rst = _make_bterms(mocker, ["clk", "rst"])

        plan = PinPlacementPlan(config, [mock_clk, mock_rst], "none")

        assert plan.unmatched_design_bterms == {mock_rst}
        assert plan.unmatched_design_pin_names == {"rst"}

    @pytest.mark.parametrize(
        ("config_pins", "unmatched_error", "raises"),
        [
            pytest.param(["pin0", "ghost"], "unmatched_cfg", True, id="cfg-cfg"),
            pytest.param(["pin0", "ghost"], "both", True, id="cfg-both"),
            pytest.param(["pin0", "ghost"], "unmatched_design", False, id="cfg-design"),
            pytest.param(["pin0", "ghost"], "none", False, id="cfg-none"),
            pytest.param([], "unmatched_design", True, id="design-design"),
            pytest.param([], "both", True, id="design-both"),
            pytest.param([], "unmatched_cfg", False, id="design-cfg"),
            pytest.param([], "none", False, id="design-none"),
        ],
    )
    def test_unmatched_pins_error_mode(
        self,
        mocker: MockerFixture,
        config_pins: list[str],
        unmatched_error: str,
        raises: bool,
    ) -> None:
        """Each mode exits with EX_DATAERR only for the mismatch kind it names.

        The design holds only `pin0`. The `cfg-*` rows add the config-only pin
        `ghost`; the `design-*` rows leave `pin0` out of the config.
        """
        config = {"X0Y0": {"NORTH": [{"pins": config_pins, "sort_mode": "bus_major"}]}}
        bterms = _make_bterms(mocker, ["pin0"])

        if raises:
            with pytest.raises(SystemExit) as exc_info:
                PinPlacementPlan(config, bterms, unmatched_error)
            assert exc_info.value.code == os.EX_DATAERR
        else:
            PinPlacementPlan(config, bterms, unmatched_error)

    def test_boundary_validation(self, mocker: MockerFixture) -> None:
        """Only boundary sides may carry pins; an inner side is rejected."""
        boundary_only = {
            "X0Y0": {"EAST": [{"pins": ["pin0"], "sort_mode": "bus_major"}]},
        }
        plan = PinPlacementPlan(boundary_only, _make_bterms(mocker, ["pin0"]), "none")
        assert len(plan.segments_by_side[Side.EAST]) == 1

        # X1Y0 makes X0Y0's EAST side an inner edge of the fabric.
        inner_side = {
            "X0Y0": {"EAST": [{"pins": ["pin0"], "sort_mode": "bus_major"}]},
            "X1Y0": {"EAST": [{"pins": ["pin1"], "sort_mode": "bus_major"}]},
        }
        with pytest.raises(
            ValueError, match="Tile X0Y0 side EAST is not on the boundary"
        ):
            PinPlacementPlan(inner_side, _make_bterms(mocker, ["pin0", "pin1"]), "none")

    def test_allocate_tracks_single_tile(self, mocker: MockerFixture) -> None:
        """A 1000-wide tile on a 100 pitch keeps 9 of its 11 tracks after the offset."""
        config = {
            "X0Y0": {"NORTH": [{"pins": ["pin0", "pin1"], "sort_mode": "bus_major"}]}
        }
        plan = PinPlacementPlan(config, _make_bterms(mocker, ["pin0", "pin1"]), "none")

        specs = {
            Side.NORTH: (10, 100.0, 0.0, 1000.0),
        }
        plan.allocate_tracks(specs)

        assert plan.track_coordinates[Side.NORTH] == [
            [200.0, 300.0, 400.0, 500.0, 600.0, 700.0, 800.0, 900.0, 1000.0]
        ]

    def test_allocate_tracks_multiple_tiles(self, mocker: MockerFixture) -> None:
        """Each tile gets the single-tile track set, shifted by its own origin."""
        config = {
            "X0Y0": {"NORTH": [{"pins": ["pin0"], "sort_mode": "bus_major"}]},
            "X1Y0": {"NORTH": [{"pins": ["pin1"], "sort_mode": "bus_major"}]},
        }
        plan = PinPlacementPlan(config, _make_bterms(mocker, ["pin0", "pin1"]), "none")

        specs = {
            Side.NORTH: (20, 100.0, 0.0, 2000.0),
        }
        plan.allocate_tracks(specs)

        assert plan.track_coordinates[Side.NORTH] == [
            [200.0, 300.0, 400.0, 500.0, 600.0, 700.0, 800.0, 900.0, 1000.0],
            [1200.0, 1300.0, 1400.0, 1500.0, 1600.0, 1700.0, 1800.0, 1900.0, 2000.0],
        ]

    @pytest.mark.parametrize(
        ("configured", "expected"),
        [
            pytest.param(0.5, 1.0, id="raised-to-floor"),
            pytest.param(None, 1.0, id="unset-takes-floor"),
            pytest.param(2.0, 2.0, id="larger-kept"),
        ],
    )
    def test_ensure_min_distances(
        self, mocker: MockerFixture, configured: float | None, expected: float
    ) -> None:
        """A segment min_distance is raised to the technology floor, never lowered."""
        config = {
            "X0Y0": {
                "NORTH": [
                    {
                        "pins": ["pin0"],
                        "sort_mode": "bus_major",
                        "min_distance": configured,
                    }
                ]
            }
        }
        plan = PinPlacementPlan(config, _make_bterms(mocker, ["pin0"]), "none")

        plan.ensure_min_distances({side: 1.0 for side in Side})

        assert plan.segments_by_side[Side.NORTH][0].min_distance == expected

    def test_assign_unmatched_pins(self, mocker: MockerFixture) -> None:
        """An unmatched design pin is appended to the least-used segment."""
        config = {"X0Y0": {"NORTH": [{"pins": ["pin0"], "sort_mode": "bus_major"}]}}
        mock_pin0, mock_unmatched = _make_bterms(mocker, ["pin0", "unmatched_pin"])

        plan = PinPlacementPlan(config, [mock_pin0, mock_unmatched], "none")
        plan.assign_unmatched_pins()

        assert plan.segments_by_side[Side.NORTH][0].pin_entries == [
            mock_pin0,
            mock_unmatched,
        ]
        assert plan.unmatched_design_bterms == set()
        assert plan.unmatched_design_pin_names == set()


class TestSupertileDivisionGridAlignment:
    """DRT-0416 offgrid pin on multi-column super tiles, across many sizings.

    ``allocate_tracks`` places each logical division at
    ``origin + ceil(die_width * division_index / num_divisions)`` and lays every
    pin track a whole ``step`` from there. When the die width is not a multiple of
    ``num_divisions * step``, some division origin is off the manufacturing grid,
    so all its pin tracks land off-grid, exactly the failure reported in
    discussion #880. ``round_die_dimension`` (applied by the balance/large sizing)
    removes it by making the width a multiple of ``num_divisions * step``.
    """

    MANUFACTURING_GRID = 5.0

    def _division_tracks(
        self,
        mocker: MockerFixture,
        num_divisions: int,
        step: float,
        die_width: float,
    ) -> list[list[float]]:
        # N-column super tile (X0..X{N-1} on the north edge), one pin per column;
        # return the raw tracks allocated to each division, ordered by column.
        config = {
            f"X{x}Y0": {"NORTH": [{"pins": [f"pin{x}"], "sort_mode": "bus_major"}]}
            for x in range(num_divisions)
        }
        pins = [
            mocker.Mock(getName=lambda n=f"pin{x}": n) for x in range(num_divisions)
        ]
        plan = PinPlacementPlan(config, pins, "none")

        # The first spec element (track count) is unused by allocate_tracks; the
        # origin is 0 so alignment is decided purely by the division origins.
        plan.allocate_tracks({Side.NORTH: (0, step, 0.0, die_width)})
        return plan.track_coordinates[Side.NORTH]

    # Sizings that DO trigger the bug: width is a multiple of step but not of
    # num_divisions * step, so at least one division origin is off-grid. Covers
    # odd column counts (3, 6, 7), realistic sky130 pitches (340, 460), the
    # smallest such tile, and the 2-column edge that only breaks for an
    # odd-grid-multiple pitch. Every division spans at least two steps, so it
    # keeps a pin track past the two reserved offset tracks.
    OFFGRID_SIZINGS = [
        pytest.param(3, 100.0, 1000.0, id="3col_step100"),
        pytest.param(3, 100.0, 700.0, id="3col_smallest"),
        pytest.param(3, 340.0, 3400.0, id="3col_step340"),
        pytest.param(3, 460.0, 4600.0, id="3col_step460"),
        pytest.param(6, 100.0, 1300.0, id="6col_step100"),
        pytest.param(7, 100.0, 1500.0, id="7col_step100"),
        pytest.param(7, 460.0, 10000.0, id="7col_step460"),
        pytest.param(2, 15.0, 75.0, id="2col_oddpitch"),
    ]

    # Sizings where the bug never manifests (width already divides evenly into
    # grid-aligned parts). round_die_dimension must be a safe no-op here.
    ALIGNED_SIZINGS = [
        pytest.param(1, 100.0, 1000.0, id="1col_regular_tile"),
        pytest.param(2, 100.0, 1000.0, id="2col_step100"),
        pytest.param(4, 100.0, 1000.0, id="4col_step100"),
        pytest.param(5, 100.0, 1000.0, id="5col_step100"),
    ]

    @pytest.mark.parametrize(
        ("num_divisions", "step", "raw_width"), OFFGRID_SIZINGS + ALIGNED_SIZINGS
    )
    def test_round_die_dimension_keeps_every_division_on_grid(
        self,
        mocker: MockerFixture,
        num_divisions: int,
        step: float,
        raw_width: float,
    ) -> None:
        # The fix: every division of the rounded width must be on-grid.
        fixed_width = float(
            round_die_dimension(Decimal(raw_width), Decimal(step), num_divisions)
        )
        division_tracks = self._division_tracks(
            mocker, num_divisions, step, fixed_width
        )

        assert len(division_tracks) == num_divisions
        for tracks in division_tracks:
            assert tracks  # each division actually received tracks
            assert all(t % self.MANUFACTURING_GRID == 0 for t in tracks)

    @pytest.mark.parametrize(("num_divisions", "step", "raw_width"), OFFGRID_SIZINGS)
    def test_unaligned_width_reproduces_offgrid(
        self,
        mocker: MockerFixture,
        num_divisions: int,
        step: float,
        raw_width: float,
    ) -> None:
        # The bug: the raw (unrounded) width places at least one pin off-grid;
        # test_round_die_dimension_keeps_every_division_on_grid covers the fix.
        raw_tracks = [
            t
            for tracks in self._division_tracks(mocker, num_divisions, step, raw_width)
            for t in tracks
        ]
        assert any(t % self.MANUFACTURING_GRID != 0 for t in raw_tracks)


class TestPinPlacementPlanPrivateMethods:
    """Test suite for PinPlacementPlan private methods."""

    def test_group_segments_by_tile(self, mocker: MockerFixture) -> None:
        """Segments are keyed by tile index with that tile's coordinates."""
        seg1 = SegmentInfo(
            side=Side.NORTH,
            sort_mode=PinSortMode.BUS_MAJOR,
            min_distance=None,
            max_distance=None,
            reverse_result=False,
            pin_entries=[mocker.Mock()],
            tile_index=0,
            tile_x=0,
            tile_y=0,
        )
        seg2 = SegmentInfo(
            side=Side.NORTH,
            sort_mode=PinSortMode.BUS_MAJOR,
            min_distance=None,
            max_distance=None,
            reverse_result=False,
            pin_entries=[mocker.Mock()],
            tile_index=1,
            tile_x=1,
            tile_y=0,
        )

        result = PinPlacementPlan._group_segments_by_tile([seg1, seg2])

        assert result == {0: (0, 0, [seg1]), 1: (1, 0, [seg2])}

    @pytest.mark.parametrize(
        ("side", "tile_x", "tile_y", "tile_idx", "num_divisions", "expected"),
        [
            pytest.param(Side.NORTH, 2, 0, 0, 5, 2, id="north-uses-x"),
            pytest.param(Side.SOUTH, 3, 9, 0, 5, 3, id="south-uses-x"),
            pytest.param(Side.EAST, 0, 1, 0, 4, 2, id="east-inverts-y"),
            pytest.param(Side.WEST, 0, 1, 0, 4, 2, id="west-inverts-y"),
            pytest.param(Side.WEST, 0, 0, 0, 4, 3, id="west-top-row-highest"),
            pytest.param(Side.EAST, 0, 3, 0, 4, 0, id="east-bottom-row-zero"),
            pytest.param(Side.NORTH, 10, 0, 0, 5, 4, id="clamp-high"),
            pytest.param(Side.EAST, 0, 6, 0, 4, 0, id="clamp-low"),
            pytest.param(Side.NORTH, None, 0, 3, 5, 3, id="no-x-uses-tile-idx"),
            pytest.param(Side.WEST, 0, None, 1, 4, 1, id="no-y-uses-tile-idx"),
        ],
    )
    def test_get_division_index(
        self,
        side: Side,
        tile_x: int | None,
        tile_y: int | None,
        tile_idx: int,
        num_divisions: int,
        expected: int,
    ) -> None:
        """N/S index by x, E/W by inverted y, tile_idx without coordinates, clamped."""
        index = PinPlacementPlan._get_division_index(
            side,
            tile_x=tile_x,
            tile_y=tile_y,
            tile_idx=tile_idx,
            num_divisions=num_divisions,
        )
        assert index == expected

    def test_allocate_tracks_for_tile(self, mocker: MockerFixture) -> None:
        """28 usable tracks split 2:1 rounds up to 19+10 and trims the first to 18."""
        seg1 = SegmentInfo(
            side=Side.NORTH,
            sort_mode=PinSortMode.BUS_MAJOR,
            min_distance=None,
            max_distance=None,
            reverse_result=False,
            pin_entries=[mocker.Mock(), mocker.Mock()],
        )
        seg2 = SegmentInfo(
            side=Side.NORTH,
            sort_mode=PinSortMode.BUS_MAJOR,
            min_distance=None,
            max_distance=None,
            reverse_result=False,
            pin_entries=[mocker.Mock()],
        )

        tracks = PinPlacementPlan._allocate_tracks_for_tile(
            track_count=30,
            step=100.0,
            origin=0.0,
            segments=[seg1, seg2],
        )

        assert tracks == [
            [100.0 * i for i in range(2, 20)],
            [100.0 * i for i in range(20, 30)],
        ]


class TestIntegration:
    """Integration tests for complete pin placement workflow."""

    @staticmethod
    def _filtered_north_tracks(
        mocker: MockerFixture, min_distance: float, max_distance: float | None
    ) -> list[list[float]]:
        """Return the stride-filtered NORTH tracks for a single three-pin segment.

        The segment spans 10.0 units on a 1.0 track step with a zero origin, so
        `allocate_tracks` hands the filter the raw tracks 0.0 … 10.0.
        """
        config = {
            "X0Y0": {
                "NORTH": [
                    {
                        "pins": ["pin0", "pin1", "pin2"],
                        "sort_mode": "bus_major",
                        "min_distance": min_distance,
                        "max_distance": max_distance,
                        "reverse_result": False,
                    }
                ]
            }
        }

        mock_pins = [mocker.Mock(getName=lambda i=i: f"pin{i}") for i in range(3)]
        for pin in mock_pins:
            pin.getName.return_value = pin.getName()

        plan = PinPlacementPlan(config, mock_pins, "none")
        plan.allocate_tracks({Side.NORTH: (11, 1.0, 0.0, 10.0)}, offset=0)

        pin_tracks, track_errors = filter_pin_tracks_by_stride_and_distance(
            plan,
            step_by_side={side: 1.0 for side in Side},
            origin_by_side={side: 0.0 for side in Side},
            micron_in_units=1.0,
        )

        assert track_errors == [], f"filter reported track shortfalls: {track_errors}"
        return pin_tracks[Side.NORTH]

    def test_track_allocation_respects_min_distance(
        self, mocker: MockerFixture
    ) -> None:
        """min_distance drops raw tracks so consecutive tracks are a stride apart.

        min_distance 2.5 over a 1.0 step gives stride 3, so the raw tracks
        0.0 … 10.0 collapse to every third one.
        """
        tracks = self._filtered_north_tracks(mocker, 2.5, None)

        assert tracks == [[0.0, 3.0, 6.0, 9.0]]

    def test_track_allocation_respects_max_distance(
        self, mocker: MockerFixture
    ) -> None:
        """max_distance re-inserts tracks into gaps the stride filter opened up.

        min_distance 3.0 alone leaves `[0.0, 3.0, 6.0, 9.0]`; a max_distance of
        2.0 caps each gap at two steps, so an interim track is inserted in every
        three-step gap.
        """
        tracks = self._filtered_north_tracks(mocker, 3.0, 2.0)

        assert tracks == [[0.0, 2.0, 3.0, 5.0, 6.0, 8.0, 9.0]]

    @pytest.mark.parametrize(
        ("sort_mode", "expected_order"),
        [
            (
                "bus_major",
                [
                    "addr[2]",
                    "addr[5]",
                    "data[2]",
                    "data[5]",
                    "data[8]",
                ],
            ),
            (
                "bit_minor",
                [
                    "addr[2]",
                    "data[2]",
                    "addr[5]",
                    "data[5]",
                    "data[8]",
                ],
            ),
        ],
    )
    def test_pin_sorting_modes(
        self,
        sort_mode: str,
        expected_order: list[str],
        mocker: MockerFixture,
    ) -> None:
        """Test that pins are sorted correctly in different sort modes.

        Uses the same mixed bus pin set with overlapping indices:
        - Input: data[5], addr[2], data[8], addr[5], data[2]
        - BUS_MAJOR: sorts by bus name first, then index
          → addr[2], addr[5], data[2], data[5], data[8]
        - BIT_MINOR: sorts by index first, then bus name
          → addr[2], data[2], addr[5], data[5], data[8]
        """
        config = {
            "X0Y0": {
                "NORTH": [
                    {
                        "pins": [".*\\[.*\\]"],  # Single regex matching both buses
                        "sort_mode": sort_mode,
                        "min_distance": None,
                        "max_distance": None,
                        "reverse_result": False,
                    }
                ]
            }
        }

        # Create pins in random order with mixed bus names and overlapping indices
        pin_names_input = ["data[5]", "addr[2]", "data[8]", "addr[5]", "data[2]"]
        mock_pins = []
        for name in pin_names_input:
            pin = mocker.Mock()
            pin.getName.return_value = name
            mock_pins.append(pin)

        plan = PinPlacementPlan(config, mock_pins, "none")

        # Get the segment
        segments = plan.segments_by_side[Side.NORTH]
        assert len(segments) == 1
        segment = segments[0]

        # Verify pins are sorted according to the sort mode
        pin_names = [p.getName() for p in segment.pin_entries if not isinstance(p, int)]
        assert pin_names == expected_order

    @pytest.mark.parametrize(
        ("reverse_result", "expected_order"),
        [
            pytest.param(False, ["a", "b"], id="in-order"),
            pytest.param(True, ["b", "a"], id="reversed"),
        ],
    )
    def test_io_place_stamps_pins_in_segment_order(
        self,
        mocker: MockerFixture,
        tmp_path: Path,
        mock_odb_io_place: SimpleNamespace,
        pin_placement_recorder: PinPlacementRecorder,
        reverse_result: bool,
        expected_order: list[str],
    ) -> None:
        """`io_place` stamps one box per pin on its slot; reverse_result flips the order.

        A 100x100 die with a 1-unit track grid leaves the SOUTH segment tracks 2..100.
        The 4-unit pin pitch strides them to 2, 6, ..., 98 (25 tracks), and the two
        pins sit centred on tracks 26 and 74. Each box is the 4-wide pin centred on
        its track, 10 long from the south die edge.
        """
        config = tmp_path / "pins.yaml"
        config.write_text(
            yaml.safe_dump(
                {
                    "X0Y0": {
                        "SOUTH": [
                            {
                                "pins": ["a", "b"],
                                "sort_mode": "bus_major",
                                "reverse_result": reverse_result,
                            }
                        ]
                    }
                }
            )
        )
        bterms = []
        for name, io_type in [("a", "INPUT"), ("b", "OUTPUT")]:
            bterm = mocker.Mock()
            bterm.getName.return_value = name
            bterm.getSigType.return_value = "SIGNAL"
            bterm.getIoType.return_value = io_type
            bterm.getBPins.return_value = []
            bterms.append(bterm)
        h_layer = MockLayer(width=2, name="H")
        v_layer = MockLayer(width=2, name="V")
        track_grid = SimpleNamespace(
            getGridPatternX=lambda _i: (0, 101, 1),
            getGridPatternY=lambda _i: (0, 101, 1),
        )
        reader = SimpleNamespace(
            dbunits=1.0,
            name="tile",
            tech=MockTechIoPlace(h_layer, v_layer),
            block=SimpleNamespace(
                getBTerms=lambda: bterms,
                getDieArea=lambda: MockDie(0, 0, 100, 100),
                findTrackGrid=lambda _layer: track_grid,
            ),
        )
        mocker.patch.object(tile_io_place, "odb", mock_odb_io_place)
        utl = mocker.patch.object(tile_io_place, "utl")

        tile_io_place.io_place.callback.__wrapped__(
            reader=reader,
            config=str(config),
            ver_layer="V",
            hor_layer="H",
            ver_width_mult=2,
            hor_width_mult=2,
            hor_length=10,
            ver_length=10,
            hor_extension=0,
            ver_extension=0,
            unmatched_error="both",
            verbose=False,
        )

        assert pin_placement_recorder.placements == [
            (expected_order[0], v_layer, 24, 0, 28, 10),
            (expected_order[1], v_layer, 72, 0, 76, 10),
        ]
        assert utl.metric_integer.call_args_list == [
            mocker.call("design__io__count__input", 1),
            mocker.call("design__io__count__output", 1),
        ]

    def test_multi_segment_per_tile(self, mocker: MockerFixture) -> None:
        """Test handling of multiple segments on the same tile side."""
        config = {
            "X0Y0": {
                "NORTH": [
                    {"pins": ["clk"], "sort_mode": "bus_major"},
                    {"pins": ["rst"], "sort_mode": "bus_major"},
                    {"pins": ["data.*"], "sort_mode": "bus_major"},
                ]
            }
        }
        mock_clk, mock_rst, mock_data1, mock_data0 = _make_bterms(
            mocker, ["clk", "rst", "data1", "data0"]
        )

        plan = PinPlacementPlan(
            config, [mock_clk, mock_rst, mock_data1, mock_data0], "none"
        )

        assert [seg.pin_entries for seg in plan.segments_by_side[Side.NORTH]] == [
            [mock_clk],
            [mock_rst],
            [mock_data0, mock_data1],
        ]


class TestNormalTileSupertilePinAlignment:
    """Pin Y-coordinate alignment between stacked normal tiles and a 2-tall super tile.

    Each super tile division must produce the same track coordinates as a standalone
    normal tile of the same height.  With non-zero track origins (sky130) the total
    track count is not 2x the single-tile count, so naive integer division loses tracks
    per division.
    """

    @pytest.mark.parametrize(
        ("origin", "step", "tile_height", "normal_count", "super_count", "label"),
        [
            # --- on-pitch (tile_height is a multiple of step, guaranteed by round_die_area) ---
            (0.0, 42.0, 1008.0, 24, 48, "on-pitch-ihp-zero-offset"),
            (34.0, 68.0, 1020.0, 15, 30, "on-pitch-sky130"),
            (23.0, 46.0, 920.0, 20, 40, "on-pitch-arbitrary"),
            # --- off-pitch (tile_height NOT a multiple of step) ---
            # round_die_area should prevent this, but test resilience anyway
            (34.0, 68.0, 1000.0, 15, 29, "off-pitch-sky130"),
            (0.0, 42.0, 1000.0, 24, 48, "off-pitch-ihp"),
            (23.0, 46.0, 1000.0, 22, 43, "off-pitch-arbitrary"),
        ],
    )
    def test_pin_tracks_align(
        self,
        mocker: MockerFixture,
        origin: float,
        step: float,
        tile_height: float,
        normal_count: int,
        super_count: int,
        label: str,
    ) -> None:
        """Normal tile EAST tracks must match super tile WEST tracks per division."""
        normal_config = {
            "X0Y0": {"EAST": [{"pins": ["nA0", "nA1"], "sort_mode": "bus_major"}]},
        }
        super_config = {
            "X0Y0": {"WEST": [{"pins": ["sA0", "sA1"], "sort_mode": "bus_major"}]},
            "X0Y1": {"WEST": [{"pins": ["sB0", "sB1"], "sort_mode": "bus_major"}]},
        }

        plan_normal = PinPlacementPlan(
            normal_config,
            _make_bterms(mocker, ["nA0", "nA1"]),
            "none",
        )
        plan_super = PinPlacementPlan(
            super_config,
            _make_bterms(mocker, ["sA0", "sA1", "sB0", "sB1"]),
            "none",
        )

        plan_normal.allocate_tracks(
            {Side.EAST: (normal_count, step, origin, tile_height)}
        )
        plan_super.allocate_tracks(
            {Side.WEST: (super_count, step, origin, 2 * tile_height)}
        )

        normal_tracks = plan_normal.track_coordinates[Side.EAST]
        super_tracks = plan_super.track_coordinates[Side.WEST]

        assert len(normal_tracks) == 1
        assert len(super_tracks) == 2

        # Bottom division (super_tracks[1] = tile_y=1) must match normal tile exactly
        assert normal_tracks[0] == super_tracks[1], (
            f"[{label}] Bottom row tracks differ: "
            f"normal={normal_tracks[0]} vs super={super_tracks[1]}"
        )
        # Top division is the normal tile shifted up by one tile height
        assert super_tracks[0] == [t + tile_height for t in normal_tracks[0]], (
            f"[{label}] Top row tracks differ from the shifted normal tile"
        )

    @pytest.mark.parametrize(
        ("origin", "step", "tile_height", "normal_count", "super_count", "label"),
        [
            # --- on-pitch ---
            (34.0, 68.0, 1020.0, 15, 45, "3tall-on-pitch-sky130"),
            (60.0, 68.0, 1020.0, 15, 45, "3tall-on-pitch-large-origin"),
            (2.0, 68.0, 1020.0, 15, 45, "3tall-on-pitch-small-origin"),
            # --- off-pitch ---
            (34.0, 68.0, 1000.0, 15, 43, "3tall-off-pitch-sky130"),
        ],
    )
    def test_3tall_supertile_pin_alignment(
        self,
        mocker: MockerFixture,
        origin: float,
        step: float,
        tile_height: float,
        normal_count: int,
        super_count: int,
        label: str,
    ) -> None:
        """3-tall super tile divisions must each match a standalone normal tile.

        Checks both track count AND coordinate match for the bottom row.
        """
        normal_config = {
            "X0Y0": {"EAST": [{"pins": ["n0", "n1"], "sort_mode": "bus_major"}]},
        }
        super_config = {
            "X0Y0": {"WEST": [{"pins": ["s0", "s1"], "sort_mode": "bus_major"}]},
            "X0Y1": {"WEST": [{"pins": ["s2", "s3"], "sort_mode": "bus_major"}]},
            "X0Y2": {"WEST": [{"pins": ["s4", "s5"], "sort_mode": "bus_major"}]},
        }

        plan_normal = PinPlacementPlan(
            normal_config,
            _make_bterms(mocker, ["n0", "n1"]),
            "none",
        )
        plan_super = PinPlacementPlan(
            super_config,
            _make_bterms(mocker, ["s0", "s1", "s2", "s3", "s4", "s5"]),
            "none",
        )

        plan_normal.allocate_tracks(
            {Side.EAST: (normal_count, step, origin, tile_height)}
        )
        plan_super.allocate_tracks(
            {Side.WEST: (super_count, step, origin, 3 * tile_height)}
        )

        normal_tracks = plan_normal.track_coordinates[Side.EAST]
        super_tracks = plan_super.track_coordinates[Side.WEST]

        assert len(normal_tracks) == 1
        assert len(super_tracks) == 3

        # super_tracks sorted by tile_y: [Y0(top), Y1(mid), Y2(bottom)]
        # Bottom division (Y2) must match normal tile coordinates exactly
        assert normal_tracks[0] == super_tracks[2], (
            f"[{label}] Bottom row coordinates differ: "
            f"normal={normal_tracks[0]} vs super_bottom={super_tracks[2]}"
        )
        # Every division is the normal tile shifted by its row offset
        assert super_tracks == [
            [t + 2 * tile_height for t in normal_tracks[0]],
            [t + tile_height for t in normal_tracks[0]],
            normal_tracks[0],
        ], f"[{label}] Divisions differ from the shifted normal tile"

    @pytest.mark.parametrize(
        ("origin", "step", "tile_width", "normal_count", "super_count", "label"),
        [
            # --- on-pitch ---
            (0.0, 46.0, 920.0, 20, 40, "2wide-on-pitch-zero-offset"),
            (34.0, 68.0, 1020.0, 15, 30, "2wide-on-pitch-sky130"),
            # --- off-pitch ---
            (34.0, 68.0, 1000.0, 15, 29, "2wide-off-pitch-sky130"),
        ],
    )
    def test_2wide_supertile_north_south_alignment(
        self,
        mocker: MockerFixture,
        origin: float,
        step: float,
        tile_width: float,
        normal_count: int,
        super_count: int,
        label: str,
    ) -> None:
        """2-wide super tile SOUTH divisions must match stacked normal tiles NORTH."""
        normal_config = {
            "X0Y0": {"NORTH": [{"pins": ["n0", "n1"], "sort_mode": "bus_major"}]},
        }
        super_config = {
            "X0Y0": {"SOUTH": [{"pins": ["s0", "s1"], "sort_mode": "bus_major"}]},
            "X1Y0": {"SOUTH": [{"pins": ["s2", "s3"], "sort_mode": "bus_major"}]},
        }

        plan_normal = PinPlacementPlan(
            normal_config,
            _make_bterms(mocker, ["n0", "n1"]),
            "none",
        )
        plan_super = PinPlacementPlan(
            super_config,
            _make_bterms(mocker, ["s0", "s1", "s2", "s3"]),
            "none",
        )

        plan_normal.allocate_tracks(
            {Side.NORTH: (normal_count, step, origin, tile_width)}
        )
        plan_super.allocate_tracks(
            {Side.SOUTH: (super_count, step, origin, 2 * tile_width)}
        )

        normal_tracks = plan_normal.track_coordinates[Side.NORTH]
        super_tracks = plan_super.track_coordinates[Side.SOUTH]

        assert len(normal_tracks) == 1
        assert len(super_tracks) == 2

        # First division (X0) of super tile must match standalone normal tile
        assert normal_tracks[0] == super_tracks[0], (
            f"[{label}] X0 tracks differ: "
            f"normal={normal_tracks[0]} vs super={super_tracks[0]}"
        )
        assert super_tracks[1] == [t + tile_width for t in normal_tracks[0]], (
            f"[{label}] X1 tracks differ from the shifted normal tile"
        )

    @pytest.mark.parametrize(
        ("origin", "step", "tile_height", "normal_count", "super_count", "label"),
        [
            # --- on-pitch ---
            (60.0, 68.0, 136.0, 2, 4, "tiny-on-pitch"),
            (34.0, 68.0, 136.0, 2, 4, "small-on-pitch"),
            (34.0, 68.0, 68.0, 1, 2, "one-track-on-pitch"),
            # --- off-pitch ---
            (60.0, 68.0, 100.0, 1, 1, "tiny-off-pitch"),
            (34.0, 68.0, 102.0, 1, 2, "small-off-pitch"),
        ],
    )
    def test_edge_case_minimal_tracks(
        self,
        mocker: MockerFixture,
        origin: float,
        step: float,
        tile_height: float,
        normal_count: int,
        super_count: int,
        label: str,
    ) -> None:
        """Extreme tile sizes must not crash and must stay consistent."""
        normal_config = {
            "X0Y0": {"EAST": [{"pins": ["n0"], "sort_mode": "bus_major"}]},
        }
        super_config = {
            "X0Y0": {"WEST": [{"pins": ["s0"], "sort_mode": "bus_major"}]},
            "X0Y1": {"WEST": [{"pins": ["s1"], "sort_mode": "bus_major"}]},
        }

        plan_normal = PinPlacementPlan(
            normal_config,
            _make_bterms(mocker, ["n0"]),
            "none",
        )
        plan_super = PinPlacementPlan(
            super_config,
            _make_bterms(mocker, ["s0", "s1"]),
            "none",
        )

        plan_normal.allocate_tracks(
            {Side.EAST: (normal_count, step, origin, tile_height)}
        )
        plan_super.allocate_tracks(
            {Side.WEST: (super_count, step, origin, 2 * tile_height)}
        )

        normal_tracks = plan_normal.track_coordinates[Side.EAST]
        super_tracks = plan_super.track_coordinates[Side.WEST]

        assert len(normal_tracks) == 1
        assert super_tracks == [
            [t + tile_height for t in normal_tracks[0]],
            normal_tracks[0],
        ], f"[{label}] Divisions differ from the shifted normal tile"

    @pytest.mark.parametrize(
        ("origin", "step", "tile_height"),
        [
            pytest.param(60.0, 68.0, 136.0, id="tiny-on-pitch"),
            pytest.param(34.0, 68.0, 68.0, id="one-track-on-pitch"),
            pytest.param(34.0, 68.0, 102.0, id="small-off-pitch"),
        ],
    )
    def test_minimal_tile_tracks_stay_inside_tile(
        self,
        mocker: MockerFixture,
        origin: float,
        step: float,
        tile_height: float,
    ) -> None:
        """A tile with no track past the reserved offset gets no pin track, so
        the pin shortage check reports it instead of a track outside the tile."""
        plan = PinPlacementPlan(
            {"X0Y0": {"EAST": [{"pins": ["n0"], "sort_mode": "bus_major"}]}},
            _make_bterms(mocker, ["n0"]),
            "none",
        )
        plan.allocate_tracks({Side.EAST: (0, step, origin, tile_height)})
        plan.ensure_min_distances({Side.EAST: 0.0})
        _, track_errors = filter_pin_tracks_by_stride_and_distance(
            plan, {Side.EAST: step}, {Side.EAST: origin}, 1.0
        )

        assert plan.track_coordinates[Side.EAST] == [[]]
        assert track_errors == [
            {"side": Side.EAST, "shortage": 1, "step": step, "min_distance": 0.0}
        ]

    def test_uneven_pin_counts_across_subtiles(self, mocker: MockerFixture) -> None:
        """Sub-tiles with different pin counts must still get equal track allocation.

        Real super tiles often have different port counts per row (e.g., DSP_top has
        more ports than DSP_bot).  The track allocation per division must be the same
        regardless of how many pins each sub-tile has.
        """
        # Normal tile with 4 pins
        normal_config = {
            "X0Y0": {
                "EAST": [{"pins": ["n0", "n1", "n2", "n3"], "sort_mode": "bus_major"}]
            },
        }
        # Super tile: Y0 has 5 pins, Y1 has 2 pins (uneven)
        super_config = {
            "X0Y0": {
                "WEST": [
                    {"pins": ["s0", "s1", "s2", "s3", "s4"], "sort_mode": "bus_major"}
                ]
            },
            "X0Y1": {"WEST": [{"pins": ["s5", "s6"], "sort_mode": "bus_major"}]},
        }

        plan_normal = PinPlacementPlan(
            normal_config,
            _make_bterms(mocker, ["n0", "n1", "n2", "n3"]),
            "none",
        )
        plan_super = PinPlacementPlan(
            super_config,
            _make_bterms(mocker, ["s0", "s1", "s2", "s3", "s4", "s5", "s6"]),
            "none",
        )

        origin, step, tile_height = 34.0, 68.0, 1020.0
        plan_normal.allocate_tracks({Side.EAST: (15, step, origin, tile_height)})
        plan_super.allocate_tracks({Side.WEST: (30, step, origin, 2 * tile_height)})

        normal_tracks = plan_normal.track_coordinates[Side.EAST]
        super_tracks = plan_super.track_coordinates[Side.WEST]

        # Both divisions get the normal tile's tracks whatever their pin count
        assert super_tracks == [
            [t + tile_height for t in normal_tracks[0]],
            normal_tracks[0],
        ]

    def test_multiple_segments_per_subtile(self, mocker: MockerFixture) -> None:
        """Sub-tiles with multiple segments on the same side must align.

        Real tiles have routing ports AND frame signals on the same side, represented as
        separate segments.
        """
        normal_config = {
            "X0Y0": {
                "EAST": [
                    {"pins": ["route0", "route1"], "sort_mode": "bus_major"},
                    {"pins": ["frame0"], "sort_mode": "bus_major"},
                ]
            },
        }
        super_config = {
            "X0Y0": {
                "WEST": [
                    {"pins": ["sr0", "sr1"], "sort_mode": "bus_major"},
                    {"pins": ["sf0"], "sort_mode": "bus_major"},
                ]
            },
            "X0Y1": {
                "WEST": [
                    {"pins": ["sr2", "sr3"], "sort_mode": "bus_major"},
                    {"pins": ["sf1"], "sort_mode": "bus_major"},
                ]
            },
        }

        plan_normal = PinPlacementPlan(
            normal_config,
            _make_bterms(mocker, ["route0", "route1", "frame0"]),
            "none",
        )
        plan_super = PinPlacementPlan(
            super_config,
            _make_bterms(mocker, ["sr0", "sr1", "sf0", "sr2", "sr3", "sf1"]),
            "none",
        )

        origin, step, tile_height = 34.0, 68.0, 1020.0
        plan_normal.allocate_tracks({Side.EAST: (15, step, origin, tile_height)})
        plan_super.allocate_tracks({Side.WEST: (30, step, origin, 2 * tile_height)})

        normal_tracks = plan_normal.track_coordinates[Side.EAST]
        super_tracks = plan_super.track_coordinates[Side.WEST]

        # Normal: 2 segments, Super: 4 segments (2 per sub-tile)
        assert len(normal_tracks) == 2
        assert len(super_tracks) == 4

        # super_tracks[0:2] = Y0 (top), super_tracks[2:4] = Y1 (bottom); each
        # division splits its tracks between its segments like the normal tile.
        assert super_tracks[2:4] == normal_tracks
        assert super_tracks[0:2] == [
            [t + tile_height for t in segment] for segment in normal_tracks
        ]

    @pytest.mark.parametrize(
        ("origin", "step", "tile_height", "normal_count", "super_count", "label"),
        [
            # --- on-pitch ---
            (100.0, 68.0, 1020.0, 14, 28, "origin-exceeds-step-on-pitch"),
            (68.0, 68.0, 1020.0, 14, 28, "origin-equals-step-on-pitch"),
            # --- off-pitch ---
            (100.0, 68.0, 1000.0, 14, 27, "origin-exceeds-step-off-pitch"),
            (68.0, 68.0, 1000.0, 14, 27, "origin-equals-step-off-pitch"),
        ],
    )
    def test_origin_ge_step(
        self,
        mocker: MockerFixture,
        origin: float,
        step: float,
        tile_height: float,
        normal_count: int,
        super_count: int,
        label: str,
    ) -> None:
        """Origin >= step must not crash and divisions must stay consistent."""
        normal_config = {
            "X0Y0": {"EAST": [{"pins": ["n0", "n1"], "sort_mode": "bus_major"}]},
        }
        super_config = {
            "X0Y0": {"WEST": [{"pins": ["s0", "s1"], "sort_mode": "bus_major"}]},
            "X0Y1": {"WEST": [{"pins": ["s2", "s3"], "sort_mode": "bus_major"}]},
        }

        plan_normal = PinPlacementPlan(
            normal_config,
            _make_bterms(mocker, ["n0", "n1"]),
            "none",
        )
        plan_super = PinPlacementPlan(
            super_config,
            _make_bterms(mocker, ["s0", "s1", "s2", "s3"]),
            "none",
        )

        plan_normal.allocate_tracks(
            {Side.EAST: (normal_count, step, origin, tile_height)}
        )
        plan_super.allocate_tracks(
            {Side.WEST: (super_count, step, origin, 2 * tile_height)}
        )

        normal_tracks = plan_normal.track_coordinates[Side.EAST]
        super_tracks = plan_super.track_coordinates[Side.WEST]

        assert super_tracks == [
            [t + tile_height for t in normal_tracks[0]],
            normal_tracks[0],
        ], f"[{label}] Divisions differ from the shifted normal tile"

    @pytest.mark.parametrize(
        ("origin", "step", "tile_height", "stride", "label"),
        [
            # Real sky130: met3 origin=340, step=680, LUT4AB height=245480
            # division_boundary / step = 361 (ODD) → stride=2 filter would
            # skip the first track in the top division if using global indices
            (340, 680, 245480, 2, "sky130-met3-stride2"),
            # Same but with stride=3
            (340, 680, 245480, 3, "sky130-met3-stride3"),
            # Zero origin with odd division boundary
            (0, 680, 245480, 2, "zero-origin-odd-boundary"),
        ],
    )
    def test_stride_filter_does_not_shift_divisions(
        self,
        mocker: MockerFixture,
        origin: int,
        step: int,
        tile_height: int,
        stride: int,
        label: str,
    ) -> None:
        """Stride filtering must not shift pins between super-tile divisions.

        When the division boundary falls on an odd global track index and stride=2, a
        global-index-based filter would skip the first track in upper divisions,
        shifting all pins by 1 track.  The cadence must reset at every ``tile_index``
        boundary so each super-tile division reproduces the standalone tile layout.
        """
        import math as m

        origin_f = float(origin)
        step_f = float(step)
        tile_h = float(tile_height)
        min_distance = stride * step_f
        micron_in_units = 1.0
        normal_count = m.floor((tile_h - origin_f) / step_f) + 1
        super_count = m.floor((2 * tile_h - origin_f) / step_f) + 1

        # Normal tile
        normal_config = {
            "X0Y0": {
                "EAST": [
                    {
                        "pins": ["n0", "n1"],
                        "sort_mode": "bus_major",
                        "min_distance": min_distance,
                    }
                ]
            },
        }
        plan_normal = PinPlacementPlan(
            normal_config,
            _make_bterms(mocker, ["n0", "n1"]),
            "none",
        )
        plan_normal.allocate_tracks(
            {Side.EAST: (normal_count, step_f, origin_f, tile_h)}
        )
        plan_normal.ensure_min_distances({Side.EAST: min_distance})

        # Super tile
        super_config = {
            "X0Y0": {
                "WEST": [
                    {
                        "pins": ["s0", "s1"],
                        "sort_mode": "bus_major",
                        "min_distance": min_distance,
                    }
                ]
            },
            "X0Y1": {
                "WEST": [
                    {
                        "pins": ["s2", "s3"],
                        "sort_mode": "bus_major",
                        "min_distance": min_distance,
                    }
                ]
            },
        }
        plan_super = PinPlacementPlan(
            super_config,
            _make_bterms(mocker, ["s0", "s1", "s2", "s3"]),
            "none",
        )
        plan_super.allocate_tracks(
            {Side.WEST: (super_count, step_f, origin_f, 2 * tile_h)}
        )
        plan_super.ensure_min_distances({Side.WEST: min_distance})

        step_by_side = {side: step_f for side in Side}
        origin_by_side = {side: origin_f for side in Side}

        normal_pin_tracks, normal_errors = filter_pin_tracks_by_stride_and_distance(
            plan_normal, step_by_side, origin_by_side, micron_in_units
        )
        super_pin_tracks, super_errors = filter_pin_tracks_by_stride_and_distance(
            plan_super, step_by_side, origin_by_side, micron_in_units
        )

        assert normal_errors == [], f"[{label}] normal filter errors: {normal_errors}"
        assert super_errors == [], f"[{label}] super filter errors: {super_errors}"

        normal_filtered = normal_pin_tracks[Side.EAST][0]
        super_top_filtered = super_pin_tracks[Side.WEST][0]  # Y0 = top
        super_bot_filtered = super_pin_tracks[Side.WEST][1]  # Y1 = bottom

        # Bottom division must match normal tile exactly
        assert normal_filtered == super_bot_filtered, (
            f"[{label}] Bottom division stride-filtered tracks differ from normal tile"
        )
        # Top division must have the same count
        assert len(normal_filtered) == len(super_top_filtered), (
            f"[{label}] Top division has {len(super_top_filtered)} tracks after "
            f"stride filter, normal has {len(normal_filtered)}"
        )

    def test_stride_filter_respects_distance_across_segments_in_tile(
        self, mocker: MockerFixture
    ) -> None:
        """Stride filter must hold ``stride * step`` across segment boundaries.

        Real tiles split one side across multiple YAML segments (e.g.
        ``N_term_single`` SOUTH allocates pins to ``N1END``, ``N2MID``,
        ``N2END``).  The stride filter that enforces ``min_distance`` should
        treat the whole side of a physical tile as one stride cadence.
        When the cadence restarts at every segment boundary the last
        filtered pin of segment A and the first filtered pin of segment B
        can land at ``step`` apart instead of ``stride * step``, which
        TritonRoute then reports as Metal Spacing DRCs on the routed nets.

        Reproduction observed on ``N_term_single`` SOUTH at W=120.96 um.
        """
        # SG13G2 Metal2 routing parameters: origin on-grid, step is the
        # native pitch, min_distance = 2 pitches → stride = 2.
        origin, step, tile_width = 0.0, 0.48, 60.0
        min_distance = 2 * step
        expected_spacing = min_distance
        micron_in_units = 1.0

        # Three segments on SOUTH with odd-sized pin sets so the buggy
        # per-segment cadence reset puts the boundaries off-parity.
        config = {
            "X0Y0": {
                "SOUTH": [
                    {
                        "pins": ["a0", "a1", "a2", "a3", "a4"],
                        "sort_mode": "bus_major",
                        "min_distance": min_distance,
                    },
                    {
                        "pins": ["b0", "b1", "b2", "b3", "b4"],
                        "sort_mode": "bus_major",
                        "min_distance": min_distance,
                    },
                    {
                        "pins": ["c0", "c1", "c2", "c3", "c4"],
                        "sort_mode": "bus_major",
                        "min_distance": min_distance,
                    },
                ],
            },
        }
        pin_names = [f"{letter}{i}" for letter in "abc" for i in range(5)]
        plan = PinPlacementPlan(config, _make_bterms(mocker, pin_names), "none")

        track_count = int((tile_width - origin) / step) + 1
        plan.allocate_tracks({Side.SOUTH: (track_count, step, origin, tile_width)})
        plan.ensure_min_distances({Side.SOUTH: min_distance})

        assert len(plan.segments_by_side[Side.SOUTH]) == 3
        assert len(plan.track_coordinates[Side.SOUTH]) == 3

        pin_tracks, track_errors = filter_pin_tracks_by_stride_and_distance(
            plan,
            step_by_side={
                Side.NORTH: step,
                Side.SOUTH: step,
                Side.EAST: step,
                Side.WEST: step,
            },
            origin_by_side={
                Side.NORTH: origin,
                Side.SOUTH: origin,
                Side.EAST: origin,
                Side.WEST: origin,
            },
            micron_in_units=micron_in_units,
        )

        assert track_errors == [], (
            f"filter reported track shortfalls instead of producing tracks: "
            f"{track_errors}"
        )

        south_segments = pin_tracks[Side.SOUTH]
        assert len(south_segments) == 3

        # Each segment in isolation must satisfy its own stride spacing.
        for seg_idx, filtered in enumerate(south_segments):
            for i in range(len(filtered) - 1):
                delta = filtered[i + 1] - filtered[i]
                assert delta == pytest.approx(expected_spacing), (
                    f"segment {seg_idx} internal spacing {delta} "
                    f"!= expected {expected_spacing}"
                )

        # Spacing must also hold across segment boundaries on the same side.
        side_tracks = [t for seg in south_segments for t in seg]
        for i in range(len(side_tracks) - 1):
            delta = side_tracks[i + 1] - side_tracks[i]
            assert delta == pytest.approx(expected_spacing), (
                f"cross-segment spacing violation between filtered "
                f"track {i}={side_tracks[i]} and {i + 1}={side_tracks[i + 1]}: "
                f"Δ={delta} != expected {expected_spacing}"
            )

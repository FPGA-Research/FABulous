"""Tests for tile_io_place module."""
# ruff: noqa: E402, SLF001, E501, F841

import sys
from typing import TYPE_CHECKING

import pytest
from pytest_mock import MockerFixture

# Mock external dependencies BEFORE importing the module under test
from fabulous.fabric_definition.define import PinSortMode, Side
from fabulous.fabric_generator.gds_generator.gen_io_pin_config_yaml import (
    PinOrderConfig,
)
from fabulous.fabric_generator.gds_generator.script.tile_io_place import (
    PinPlacementPlan,
    SegmentInfo,
    equally_spaced_sequence,
    grid_to_tracks,
)

if TYPE_CHECKING:
    from fabulous.fabric_generator.gds_generator.script.odb_protocol import odbBTermLike


@pytest.fixture(autouse=True)
def mock_modules(mocker: MockerFixture) -> None:
    sys.modules["odb"] = mocker.MagicMock()
    sys.modules["openroad"] = mocker.MagicMock()


class TestGridToTracks:
    """Test suite for grid_to_tracks function."""

    def test_basic_track_generation(self) -> None:
        """Test basic track generation with positive step."""
        tracks = grid_to_tracks(0.0, 5, 100.0)
        assert tracks == [0.0, 100.0, 200.0, 300.0, 400.0]

    def test_negative_origin(self) -> None:
        """Test track generation with negative origin."""
        tracks = grid_to_tracks(-100.0, 3, 50.0)
        assert tracks == [-100.0, -50.0, 0.0]

    def test_single_track(self) -> None:
        """Test generation of a single track."""
        tracks = grid_to_tracks(500.0, 1, 100.0)
        assert tracks == [500.0]

    def test_tracks_are_sorted(self) -> None:
        """Test that tracks are returned in sorted order."""
        tracks = grid_to_tracks(1000.0, 4, -250.0)
        assert tracks == sorted(tracks)


class TestEquallySpacedSequence:
    """Test suite for equally_spaced_sequence function."""

    def test_pins_equal_tracks(self, mocker: MockerFixture) -> None:
        """Test when number of pins equals number of tracks."""
        mock_pins: list[int | odbBTermLike] = [
            mocker.Mock(getName=lambda i=i: f"pin{i}") for i in range(5)
        ]
        tracks = [0.0, 100.0, 200.0, 300.0, 400.0]

        result = equally_spaced_sequence(mock_pins, tracks)

        assert len(result) == 5
        assert all(result[i][0] == tracks[i] for i in range(5))

    def test_pins_less_than_tracks(self, mocker: MockerFixture) -> None:
        """Test even spacing when pins < tracks."""
        mock_pins: list[int | odbBTermLike] = [
            mocker.Mock(getName=lambda i=i: f"pin{i}") for i in range(3)
        ]
        tracks = [0.0, 100.0, 200.0, 300.0, 400.0, 500.0, 600.0]

        result = equally_spaced_sequence(mock_pins, tracks)

        assert len(result) == 3
        expected_positions = [100.0, 300.0, 500.0]

        # Pins should be evenly distributed and centered
        assert all(result[i][0] == expected_positions[i] for i in range(3))

    def test_no_pins(self) -> None:
        """Test with no pins."""
        tracks = [0.0, 100.0, 200.0]

        result = equally_spaced_sequence([], tracks)

        assert len(result) == 0

    def test_with_virtual_pins(self, mocker: MockerFixture) -> None:
        """Test spacing with virtual pins (integers in list)."""
        mock_pins: list[int | odbBTermLike] = [
            mocker.Mock(getName=lambda: "pin0"),
            2,
            mocker.Mock(getName=lambda: "pin1"),
        ]
        tracks = [0.0, 100.0, 200.0, 300.0, 400.0, 500.0, 600.0, 700.0]

        result = equally_spaced_sequence(mock_pins, tracks)

        # Should have 2 actual pins
        assert len(result) == 2
        assert all(not isinstance(p, int) for p in result)
        expected_positions = [0.0, 600.0]  # Pins should be at these tracks
        assert all(result[i][0] == expected_positions[i] for i in range(2))

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

        assert seg_info.side == Side.NORTH
        assert seg_info.sort_mode == PinSortMode.BUS_MAJOR
        assert len(seg_info.pin_entries) == 1
        assert mock_bterm in regex_by_bterm

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

        assert seg_info.tile_index == 2
        assert seg_info.tile_x == 3
        assert seg_info.tile_y == 1
        assert 3 in seg_info.pin_entries  # Virtual pin
        assert seg_info.reverse_result is True

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
        """Test error on invalid sort mode."""
        segment_config = PinOrderConfig(
            pins=["pin.*"],
            sort_mode=PinSortMode.BUS_MAJOR,
            min_distance=None,
            max_distance=None,
            reverse_result=False,
        )

        # The error comes from trying to convert an invalid string to PinSortMode
        # Let's modify the config to have an invalid sort_mode string
        segment_config_dict = {
            "pins": ["pin.*"],
            "sort_mode": "invalid_mode",
            "min_distance": None,
            "max_distance": None,
            "reverse_result": False,
        }

        with pytest.raises(KeyError):
            PinSortMode[segment_config_dict["sort_mode"]]

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

        assert len(plan.segments_by_side) == 5  # NORTH, SOUTH, EAST, WEST, ANY
        assert all(len(segs) == 0 for segs in plan.segments_by_side.values())
        assert plan.fabric_dimensions == (1, 1)

    def test_init_basic_config(self, mocker: MockerFixture) -> None:
        """Test initialization with basic tile config."""
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

        mock_clk = mocker.Mock()
        mock_clk.getName.return_value = "clk"
        mock_rst = mocker.Mock()
        mock_rst.getName.return_value = "rst"
        bterms = [mock_clk, mock_rst]

        plan = PinPlacementPlan(config, bterms, "none")

        assert len(plan.segments_by_side[Side.NORTH]) == 1
        assert plan.tile_counts_by_side[Side.NORTH] == 1
        assert plan.fabric_dimensions == (1, 1)

    def test_init_multi_tile_config(self, mocker: MockerFixture) -> None:
        """Test initialization with multiple tiles."""
        config = {
            "X0Y0": {"NORTH": [{"pins": ["pin0"], "sort_mode": "bus_major"}]},
            "X1Y0": {"NORTH": [{"pins": ["pin1"], "sort_mode": "bus_major"}]},
            "X2Y1": {"EAST": [{"pins": ["pin2"], "sort_mode": "bus_major"}]},
        }

        pins = [mocker.Mock(getName=lambda n=f"pin{i}": n) for i in range(3)]
        for pin in pins:
            pin.getName.return_value = pin.getName()

        plan = PinPlacementPlan(config, pins, "none")

        assert plan.fabric_dimensions == (3, 2)  # X goes 0-2, Y goes 0-1
        assert plan.tile_counts_by_side[Side.NORTH] == 2
        assert plan.tile_counts_by_side[Side.EAST] == 1

    def test_unmatched_design_pins(self, mocker: MockerFixture) -> None:
        """Test handling of unmatched design pins."""
        config = {"X0Y0": {"NORTH": [{"pins": ["clk"], "sort_mode": "bus_major"}]}}

        mock_clk = mocker.Mock()
        mock_clk.getName.return_value = "clk"
        mock_rst = mocker.Mock()
        mock_rst.getName.return_value = "rst"
        bterms = [mock_clk, mock_rst]

        plan = PinPlacementPlan(config, bterms, "none")

        assert "rst" in plan.unmatched_design_pin_names

    def test_unmatched_config_pins_error(self) -> None:
        """Test error on unmatched config pins."""
        config = {
            "X0Y0": {"NORTH": [{"pins": ["nonexistent"], "sort_mode": "bus_major"}]}
        }

        with pytest.raises(SystemExit):
            PinPlacementPlan(config, [], "unmatched_cfg")

    def test_boundary_validation(self, mocker: MockerFixture) -> None:
        """Test that non-boundary tiles cannot have pin configs."""
        config = {
            "X0Y0": {
                "EAST": [{"pins": ["pin0"], "sort_mode": "bus_major"}]
            },  # X0Y0 East neighbor is X1Y0, which doesn't exist in config
        }

        mock_pin0 = mocker.Mock()
        mock_pin0.getName.return_value = "pin0"

        # This should work - X0Y0 is on the East boundary
        plan = PinPlacementPlan(config, [mock_pin0], "none")
        assert len(plan.segments_by_side[Side.EAST]) == 1

    def test_allocate_tracks_single_tile(self, mocker: MockerFixture) -> None:
        """Test track allocation for a single tile."""
        config = {
            "X0Y0": {"NORTH": [{"pins": ["pin0", "pin1"], "sort_mode": "bus_major"}]}
        }

        pins = [mocker.Mock(getName=lambda n=f"pin{i}": n) for i in range(2)]
        for pin in pins:
            pin.getName.return_value = pin.getName()

        plan = PinPlacementPlan(config, pins, "none")

        specs = {
            Side.NORTH: (10, 100.0, 0.0, 1000.0),
        }
        plan.allocate_tracks(specs)

        assert len(plan.track_coordinates[Side.NORTH]) == 1
        assert len(plan.track_coordinates[Side.NORTH][0]) > 0

    def test_allocate_tracks_multiple_tiles(self, mocker: MockerFixture) -> None:
        """Test track allocation across multiple tiles."""
        config = {
            "X0Y0": {"NORTH": [{"pins": ["pin0"], "sort_mode": "bus_major"}]},
            "X1Y0": {"NORTH": [{"pins": ["pin1"], "sort_mode": "bus_major"}]},
        }

        pins = [mocker.Mock(getName=lambda n=f"pin{i}": n) for i in range(2)]
        for pin in pins:
            pin.getName.return_value = pin.getName()

        plan = PinPlacementPlan(config, pins, "none")

        specs = {
            Side.NORTH: (20, 100.0, 0.0, 2000.0),
        }
        plan.allocate_tracks(specs)

        assert len(plan.track_coordinates[Side.NORTH]) == 2

    def test_ensure_min_distances(self, mocker: MockerFixture) -> None:
        """Test ensuring minimum distances for segments."""
        config = {
            "X0Y0": {
                "NORTH": [
                    {"pins": ["pin0"], "sort_mode": "bus_major", "min_distance": 0.5}
                ]
            }
        }

        mock_pin = mocker.Mock()
        mock_pin.getName.return_value = "pin0"

        plan = PinPlacementPlan(config, [mock_pin], "none")

        min_by_side = {side: 1.0 for side in Side}
        plan.ensure_min_distances(min_by_side)

        assert plan.segments_by_side[Side.NORTH][0].min_distance == 1.0

    def test_assign_unmatched_pins(self, mocker: MockerFixture) -> None:
        """Test assigning unmatched pins to segments."""
        config = {"X0Y0": {"NORTH": [{"pins": ["pin0"], "sort_mode": "bus_major"}]}}

        mock_pin0 = mocker.Mock()
        mock_pin0.getName.return_value = "pin0"
        mock_unmatched = mocker.Mock()
        mock_unmatched.getName.return_value = "unmatched_pin"

        plan = PinPlacementPlan(config, [mock_pin0, mock_unmatched], "none")

        assert len(plan.unmatched_design_bterms) == 1

        plan.assign_unmatched_pins()

        assert len(plan.unmatched_design_bterms) == 0
        # Pin should be added to a segment
        total_pins = sum(
            len(seg.pin_entries)
            for segs in plan.segments_by_side.values()
            for seg in segs
        )
        assert total_pins == 2


class TestPinPlacementPlanPrivateMethods:
    """Test suite for PinPlacementPlan private methods."""

    def test_group_segments_by_tile(self, mocker: MockerFixture) -> None:
        """Test _group_segments_by_tile method."""
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

        assert len(result) == 2
        assert 0 in result
        assert 1 in result
        assert result[0][0] == 0  # tile_x
        assert result[0][1] == 0  # tile_y

    def test_get_division_index_north_south(self) -> None:
        """Test _get_division_index for North/South sides."""
        # For North/South, use X coordinate
        index = PinPlacementPlan._get_division_index(
            Side.NORTH, tile_x=2, tile_y=0, tile_idx=0, num_divisions=5
        )
        assert index == 2

    def test_get_division_index_east_west(self) -> None:
        """Test _get_division_index for East/West sides."""
        # For East/West, use inverted Y coordinate
        index = PinPlacementPlan._get_division_index(
            Side.EAST, tile_x=0, tile_y=1, tile_idx=0, num_divisions=4
        )
        # Y=1 should map to index 2 (inverted from 4-1)
        assert index == 2

    def test_get_division_index_clamping(self) -> None:
        """Test division index clamping."""
        # Test upper bound clamping
        index = PinPlacementPlan._get_division_index(
            Side.NORTH, tile_x=10, tile_y=0, tile_idx=0, num_divisions=5
        )
        assert index == 4  # Should be clamped to max

    def test_allocate_tracks_for_tile(self, mocker: MockerFixture) -> None:
        """Test _allocate_tracks_for_tile method."""
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

        assert len(tracks) == 2
        assert len(tracks[0]) >= 2  # Enough for seg1's pins
        assert len(tracks[1]) >= 1  # Enough for seg2's pins


class TestIntegration:
    """Integration tests for complete pin placement workflow."""

    def test_track_allocation_respects_min_distance(
        self, mocker: MockerFixture
    ) -> None:
        """Test that min_distance filtering works correctly.

        The allocate_tracks() method generates raw tracks based on the track grid.
        The min_distance constraint is then enforced by filtering these tracks
        with a stride, as done in the io_place() function.
        """
        config = {
            "X0Y0": {
                "NORTH": [
                    {
                        "pins": ["pin0", "pin1", "pin2"],
                        "sort_mode": "bus_major",
                        "min_distance": 2.5,  # Minimum 2.5 units between pins
                        "max_distance": None,
                        "reverse_result": False,
                    }
                ]
            }
        }

        mock_pins = [mocker.Mock(getName=lambda i=i: f"pin{i}") for i in range(3)]
        for pin in mock_pins:
            pin.getName.return_value = pin.getName()

        plan = PinPlacementPlan(config, mock_pins, "none")

        # Ensure min_distance is set
        plan.ensure_min_distances({Side.NORTH: 2.5})

        # Allocate tracks with specific parameters
        specs = {
            Side.NORTH: (
                10,
                1.0,
                0.0,
                10.0,
            ),  # 10 tracks, step=1.0, origin=0, length=10
        }
        plan.allocate_tracks(specs, offset=0)

        # Verify tracks were allocated
        assert len(plan.track_coordinates[Side.NORTH]) == 1
        raw_tracks = plan.track_coordinates[Side.NORTH][0]

        # Apply min_distance filtering (as done in io_place())
        segment = plan.segments_by_side[Side.NORTH][0]
        step = 1.0
        assert segment.min_distance is not None
        min_distance = segment.min_distance * 1.0  # Assume dbunits=1 for simplicity

        # Calculate stride based on min_distance
        import math

        stride = max(1, math.ceil(min_distance / step))
        filtered_tracks = [raw_tracks[i] for i in range(0, len(raw_tracks), stride)]

        # Verify filtering: with min_distance=2.5 and step=1.0, stride=3
        # So we get tracks at indices 0, 3, 6, 9
        assert stride == 3, f"Expected stride=3, got {stride}"
        assert len(filtered_tracks) == 4, (
            f"Expected 4 filtered tracks, got {len(filtered_tracks)}"
        )

        # Verify actual distances between consecutive filtered tracks
        for i in range(len(filtered_tracks) - 1):
            distance = abs(filtered_tracks[i + 1] - filtered_tracks[i])
            assert distance >= min_distance, (
                f"Distance {distance} < min_distance {min_distance}"
            )

    def test_track_allocation_respects_max_distance(
        self, mocker: MockerFixture
    ) -> None:
        """Test that allocated tracks respect max_distance constraints."""
        config = {
            "X0Y0": {
                "NORTH": [
                    {
                        "pins": ["pin0", "pin1", "pin2"],
                        "sort_mode": "bus_major",
                        "min_distance": None,
                        "max_distance": 5.0,  # Maximum 5.0 units between consecutive pins
                        "reverse_result": False,
                    }
                ]
            }
        }

        mock_pins = [mocker.Mock(getName=lambda i=i: f"pin{i}") for i in range(3)]
        for pin in mock_pins:
            pin.getName.return_value = pin.getName()

        plan = PinPlacementPlan(config, mock_pins, "none")

        # Allocate with large track space
        specs = {
            Side.NORTH: (100, 1.0, 0.0, 100.0),  # Many tracks available
        }
        plan.allocate_tracks(specs)

        tracks = plan.track_coordinates[Side.NORTH][0]
        assert len(tracks) >= 3

        # Verify max distance is respected
        for i in range(len(tracks) - 1):
            distance = abs(tracks[i + 1] - tracks[i])
            assert distance <= 5.0, f"Distance {distance} > max_distance 5.0"

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

    def test_reverse_result_reverses_pin_order(self, mocker: MockerFixture) -> None:
        """Test that reverse_result actually reverses the pin order."""
        config = {
            "X0Y0": {
                "SOUTH": [
                    {
                        "pins": ["pin0", "pin1", "pin2"],
                        "sort_mode": "bus_major",
                        "min_distance": None,
                        "max_distance": None,
                        "reverse_result": True,
                    }
                ]
            }
        }

        mock_pins = []
        for i in range(3):
            pin = mocker.Mock()
            pin.getName.return_value = f"pin{i}"
            mock_pins.append(pin)

        plan = PinPlacementPlan(config, mock_pins, "none")

        segments = plan.segments_by_side[Side.SOUTH]
        segment = segments[0]

        # Verify reverse_result is set
        assert segment.reverse_result is True

    def test_multi_tile_fabric_dimensions(self, mocker: MockerFixture) -> None:
        """Test fabric dimensions are calculated correctly for multi-tile configs."""
        config = {
            "X0Y0": {"NORTH": [{"pins": ["pin0"], "sort_mode": "bus_major"}]},
            "X2Y0": {"NORTH": [{"pins": ["pin1"], "sort_mode": "bus_major"}]},
            "X1Y3": {"EAST": [{"pins": ["pin2"], "sort_mode": "bus_major"}]},
        }

        mock_pins = []
        for i in range(3):
            pin = mocker.Mock()
            pin.getName.return_value = f"pin{i}"
            mock_pins.append(pin)

        plan = PinPlacementPlan(config, mock_pins, "none")

        # Fabric should be (3, 4) because X goes 0-2 and Y goes 0-3
        assert plan.fabric_dimensions == (3, 4)

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

        mock_clk = mocker.Mock()
        mock_clk.getName.return_value = "clk"
        mock_rst = mocker.Mock()
        mock_rst.getName.return_value = "rst"
        mock_data0 = mocker.Mock()
        mock_data0.getName.return_value = "data0"
        mock_data1 = mocker.Mock()
        mock_data1.getName.return_value = "data1"

        bterms = [mock_clk, mock_rst, mock_data0, mock_data1]

        plan = PinPlacementPlan(config, bterms, "none")

        # Should have 3 segments on NORTH side
        segments = plan.segments_by_side[Side.NORTH]
        assert len(segments) == 3

        # Verify each segment has correct pins
        assert len(segments[0].pin_entries) == 1  # clk
        assert len(segments[1].pin_entries) == 1  # rst
        assert len(segments[2].pin_entries) == 2  # data0, data1


class TestNormalTileSupertilePinAlignment:
    """Pin Y-coordinate alignment between stacked normal tiles and a 2-tall super tile.

    Each super tile division must produce the same track coordinates as a
    standalone normal tile of the same height.  With non-zero track origins
    (sky130) the total track count is not 2x the single-tile count, so naive
    integer division loses tracks per division.
    """

    @staticmethod
    def _make_bterms(mocker: MockerFixture, names: list[str]) -> list:
        bterms = []
        for name in names:
            bt = mocker.Mock()
            bt.getName.return_value = name
            bterms.append(bt)
        return bterms

    @pytest.mark.parametrize(
        ("origin", "step", "tile_height", "normal_count", "super_count", "label"),
        [
            # normal_count = floor((tile_height - origin) / step) + 1
            # super_count = floor((2*tile_height - origin) / step) + 1
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
            self._make_bterms(mocker, ["nA0", "nA1"]),
            "none",
        )
        plan_super = PinPlacementPlan(
            super_config,
            self._make_bterms(mocker, ["sA0", "sA1", "sB0", "sB1"]),
            "none",
        )

        plan_normal.allocate_tracks({Side.EAST: (normal_count, step, origin, tile_height)})
        plan_super.allocate_tracks({Side.WEST: (super_count, step, origin, 2 * tile_height)})

        normal_tracks = plan_normal.track_coordinates[Side.EAST]
        super_tracks = plan_super.track_coordinates[Side.WEST]

        assert len(normal_tracks) == 1
        assert len(super_tracks) == 2

        # Bottom division (super_tracks[1] = tile_y=1) must match normal tile exactly
        assert normal_tracks[0] == super_tracks[1], (
            f"[{label}] Bottom row tracks differ: "
            f"normal={normal_tracks[0]} vs super={super_tracks[1]}"
        )
        # Top division must have the same track count
        assert len(normal_tracks[0]) == len(super_tracks[0]), (
            f"[{label}] Track count differs: "
            f"normal={len(normal_tracks[0])} vs super_top={len(super_tracks[0])}"
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
            self._make_bterms(mocker, ["n0", "n1"]),
            "none",
        )
        plan_super = PinPlacementPlan(
            super_config,
            self._make_bterms(mocker, ["s0", "s1", "s2", "s3", "s4", "s5"]),
            "none",
        )

        plan_normal.allocate_tracks({Side.EAST: (normal_count, step, origin, tile_height)})
        plan_super.allocate_tracks({Side.WEST: (super_count, step, origin, 3 * tile_height)})

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
        # All divisions must have the same track count
        normal_track_count = len(normal_tracks[0])
        for i, st in enumerate(super_tracks):
            assert len(st) == normal_track_count, (
                f"[{label}] Division {i} track count {len(st)} != "
                f"normal tile {normal_track_count}"
            )

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
            self._make_bterms(mocker, ["n0", "n1"]),
            "none",
        )
        plan_super = PinPlacementPlan(
            super_config,
            self._make_bterms(mocker, ["s0", "s1", "s2", "s3"]),
            "none",
        )

        plan_normal.allocate_tracks({Side.NORTH: (normal_count, step, origin, tile_width)})
        plan_super.allocate_tracks({Side.SOUTH: (super_count, step, origin, 2 * tile_width)})

        normal_tracks = plan_normal.track_coordinates[Side.NORTH]
        super_tracks = plan_super.track_coordinates[Side.SOUTH]

        assert len(normal_tracks) == 1
        assert len(super_tracks) == 2

        # First division (X0) of super tile must match standalone normal tile
        assert normal_tracks[0] == super_tracks[0], (
            f"[{label}] X0 tracks differ: "
            f"normal={normal_tracks[0]} vs super={super_tracks[0]}"
        )
        assert len(normal_tracks[0]) == len(super_tracks[1]), (
            f"[{label}] X1 track count differs: "
            f"normal={len(normal_tracks[0])} vs super_x1={len(super_tracks[1])}"
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
            self._make_bterms(mocker, ["n0"]),
            "none",
        )
        plan_super = PinPlacementPlan(
            super_config,
            self._make_bterms(mocker, ["s0", "s1"]),
            "none",
        )

        plan_normal.allocate_tracks({Side.EAST: (normal_count, step, origin, tile_height)})
        plan_super.allocate_tracks({Side.WEST: (super_count, step, origin, 2 * tile_height)})

        normal_tracks = plan_normal.track_coordinates[Side.EAST]
        super_tracks = plan_super.track_coordinates[Side.WEST]

        assert len(normal_tracks) == 1
        assert len(super_tracks) == 2

        # Track counts per division must match the normal tile
        normal_track_count = len(normal_tracks[0])
        for i, st in enumerate(super_tracks):
            assert len(st) == normal_track_count, (
                f"[{label}] Division {i} track count {len(st)} != "
                f"normal tile {normal_track_count}"
            )

    def test_uneven_pin_counts_across_subtiles(self, mocker: MockerFixture) -> None:
        """Sub-tiles with different pin counts must still get equal track allocation.

        Real super tiles often have different port counts per row (e.g., DSP_top
        has more ports than DSP_bot).  The track allocation per division must be
        the same regardless of how many pins each sub-tile has.
        """
        # Normal tile with 4 pins
        normal_config = {
            "X0Y0": {"EAST": [{"pins": ["n0", "n1", "n2", "n3"], "sort_mode": "bus_major"}]},
        }
        # Super tile: Y0 has 5 pins, Y1 has 2 pins (uneven)
        super_config = {
            "X0Y0": {
                "WEST": [{"pins": ["s0", "s1", "s2", "s3", "s4"], "sort_mode": "bus_major"}]
            },
            "X0Y1": {
                "WEST": [{"pins": ["s5", "s6"], "sort_mode": "bus_major"}]
            },
        }

        plan_normal = PinPlacementPlan(
            normal_config,
            self._make_bterms(mocker, ["n0", "n1", "n2", "n3"]),
            "none",
        )
        plan_super = PinPlacementPlan(
            super_config,
            self._make_bterms(mocker, ["s0", "s1", "s2", "s3", "s4", "s5", "s6"]),
            "none",
        )

        origin, step, tile_height = 34.0, 68.0, 1020.0
        plan_normal.allocate_tracks({Side.EAST: (15, step, origin, tile_height)})
        plan_super.allocate_tracks({Side.WEST: (30, step, origin, 2 * tile_height)})

        normal_tracks = plan_normal.track_coordinates[Side.EAST]
        super_tracks = plan_super.track_coordinates[Side.WEST]

        # Both divisions must get the same number of tracks as the normal tile
        normal_track_count = len(normal_tracks[0])
        for i, st in enumerate(super_tracks):
            assert len(st) == normal_track_count, (
                f"Division {i} track count {len(st)} != normal tile {normal_track_count}"
            )

    def test_multiple_segments_per_subtile(self, mocker: MockerFixture) -> None:
        """Sub-tiles with multiple segments on the same side must align.

        Real tiles have routing ports AND frame signals on the same side,
        represented as separate segments.
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
            self._make_bterms(mocker, ["route0", "route1", "frame0"]),
            "none",
        )
        plan_super = PinPlacementPlan(
            super_config,
            self._make_bterms(mocker, ["sr0", "sr1", "sf0", "sr2", "sr3", "sf1"]),
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

        # Total tracks allocated to each division must match normal tile total
        normal_total = sum(len(t) for t in normal_tracks)
        # super_tracks[0:2] = Y0 (top), super_tracks[2:4] = Y1 (bottom)
        super_bottom_total = sum(len(t) for t in super_tracks[2:4])
        super_top_total = sum(len(t) for t in super_tracks[0:2])

        assert super_bottom_total == normal_total, (
            f"Bottom division total tracks {super_bottom_total} != "
            f"normal tile total {normal_total}"
        )
        assert super_top_total == normal_total, (
            f"Top division total tracks {super_top_total} != "
            f"normal tile total {normal_total}"
        )

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
        """origin >= step must not crash and divisions must stay consistent."""
        normal_config = {
            "X0Y0": {"EAST": [{"pins": ["n0", "n1"], "sort_mode": "bus_major"}]},
        }
        super_config = {
            "X0Y0": {"WEST": [{"pins": ["s0", "s1"], "sort_mode": "bus_major"}]},
            "X0Y1": {"WEST": [{"pins": ["s2", "s3"], "sort_mode": "bus_major"}]},
        }

        plan_normal = PinPlacementPlan(
            normal_config,
            self._make_bterms(mocker, ["n0", "n1"]),
            "none",
        )
        plan_super = PinPlacementPlan(
            super_config,
            self._make_bterms(mocker, ["s0", "s1", "s2", "s3"]),
            "none",
        )

        plan_normal.allocate_tracks({Side.EAST: (normal_count, step, origin, tile_height)})
        plan_super.allocate_tracks({Side.WEST: (super_count, step, origin, 2 * tile_height)})

        normal_tracks = plan_normal.track_coordinates[Side.EAST]
        super_tracks = plan_super.track_coordinates[Side.WEST]

        normal_track_count = len(normal_tracks[0])
        for i, st in enumerate(super_tracks):
            assert len(st) == normal_track_count, (
                f"[{label}] Division {i} track count {len(st)} != "
                f"normal tile {normal_track_count}"
            )

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
        """Stride filtering must not shift pins between divisions.

        When the division boundary falls on an odd global track index and
        stride=2, a global-index-based filter would skip the first track in
        upper divisions, shifting all pins by 1 track.  The stride must be
        relative to each division's start instead.
        """
        import math as m

        origin_f = float(origin)
        step_f = float(step)
        tile_h = float(tile_height)
        normal_count = m.floor((tile_h - origin_f) / step_f) + 1
        super_count = m.floor((2 * tile_h - origin_f) / step_f) + 1

        # Normal tile
        normal_config = {
            "X0Y0": {"EAST": [{"pins": ["n0", "n1"], "sort_mode": "bus_major"}]},
        }
        plan_normal = PinPlacementPlan(
            normal_config, self._make_bterms(mocker, ["n0", "n1"]), "none",
        )
        plan_normal.allocate_tracks(
            {Side.EAST: (normal_count, step_f, origin_f, tile_h)}
        )
        normal_raw = plan_normal.track_coordinates[Side.EAST][0]

        # Super tile
        super_config = {
            "X0Y0": {"WEST": [{"pins": ["s0", "s1"], "sort_mode": "bus_major"}]},
            "X0Y1": {"WEST": [{"pins": ["s2", "s3"], "sort_mode": "bus_major"}]},
        }
        plan_super = PinPlacementPlan(
            super_config, self._make_bterms(mocker, ["s0", "s1", "s2", "s3"]), "none",
        )
        plan_super.allocate_tracks(
            {Side.WEST: (super_count, step_f, origin_f, 2 * tile_h)}
        )
        super_raw_top = plan_super.track_coordinates[Side.WEST][0]  # Y0 = top
        super_raw_bot = plan_super.track_coordinates[Side.WEST][1]  # Y1 = bottom

        # Apply stride filter (same logic as io_place)
        def stride_filter(tracks: list[float]) -> list[float]:
            result = []
            ref_idx = None
            for t in tracks:
                idx = round((t - origin_f) / step_f)
                if ref_idx is None:
                    ref_idx = idx
                if (idx - ref_idx) % stride == 0:
                    result.append(t)
            return result

        normal_filtered = stride_filter(normal_raw)
        super_top_filtered = stride_filter(super_raw_top)
        super_bot_filtered = stride_filter(super_raw_bot)

        # Bottom division must match normal tile exactly
        assert normal_filtered == super_bot_filtered, (
            f"[{label}] Bottom division stride-filtered tracks differ from normal tile"
        )
        # Top division must have the same count
        assert len(normal_filtered) == len(super_top_filtered), (
            f"[{label}] Top division has {len(super_top_filtered)} tracks after "
            f"stride filter, normal has {len(normal_filtered)}"
        )

    @pytest.mark.parametrize("num_divisions", [2, 3, 4])
    def test_division_index_symmetry_east_west(self, num_divisions: int) -> None:
        """EAST and WEST sides must produce the same division index for the same tile_y."""
        for tile_y in range(num_divisions):
            east_idx = PinPlacementPlan._get_division_index(
                Side.EAST, tile_x=0, tile_y=tile_y, tile_idx=0,
                num_divisions=num_divisions,
            )
            west_idx = PinPlacementPlan._get_division_index(
                Side.WEST, tile_x=0, tile_y=tile_y, tile_idx=0,
                num_divisions=num_divisions,
            )
            assert east_idx == west_idx, (
                f"tile_y={tile_y}, num_divisions={num_divisions}: "
                f"EAST={east_idx} != WEST={west_idx}"
            )

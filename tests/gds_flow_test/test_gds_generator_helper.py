"""Tests for GDS generator helper utilities."""

from decimal import Decimal
from pathlib import Path

import pytest
from librelane.config.config import Config

from fabulous.fabric_generator.gds_generator.helper import (
    get_layer_info,
    get_pitch,
    get_routing_obstructions,
    round_die_area,
    round_die_dimension,
    round_up_decimal,
)

# X and Y pitches differ on every layer, so a lookup of the wrong layer or the
# wrong cardinal direction changes the result.
TRACKS_CONTENT = """M1 X 0 0.28
M1 Y 0 0.34
M2 X 0.14 0.46
M2 Y 0 0.56
"""


@pytest.fixture
def tracks_file(tmp_path: Path) -> Path:
    """Create a sample FP_TRACKS_INFO file."""
    tracks_file = tmp_path / "tracks.txt"
    tracks_file.write_text(TRACKS_CONTENT)
    return tracks_file


def _config(tracks_file: Path, **values: object) -> Config:
    """Build a real librelane `Config` with M1 vertical and M2 horizontal pins."""
    return Config(
        {
            "FP_TRACKS_INFO": str(tracks_file),
            "IO_PIN_V_LAYER": "M1",
            "IO_PIN_H_LAYER": "M2",
            **values,
        }
    )


@pytest.mark.parametrize(
    ("content", "expected"),
    [
        pytest.param(
            TRACKS_CONTENT,
            {
                "M1": {
                    "X": (Decimal(0), Decimal("0.28")),
                    "Y": (Decimal(0), Decimal("0.34")),
                },
                "M2": {
                    "X": (Decimal("0.14"), Decimal("0.46")),
                    "Y": (Decimal(0), Decimal("0.56")),
                },
            },
            id="both_directions_per_layer",
        ),
        pytest.param(
            "M1 X 0 0.28\n\nM1 Y 0 0.34\n\nM2 X 0.14 0.46\n",
            {
                "M1": {
                    "X": (Decimal(0), Decimal("0.28")),
                    "Y": (Decimal(0), Decimal("0.34")),
                },
                "M2": {"X": (Decimal("0.14"), Decimal("0.46"))},
            },
            id="blank_lines_skipped",
        ),
    ],
)
def test_get_layer_info(
    tmp_path: Path,
    content: str,
    expected: dict[str, dict[str, tuple[Decimal, Decimal]]],
) -> None:
    """Every track line becomes a `(offset, pitch)` entry under its layer."""
    tracks_file = tmp_path / "tracks.txt"
    tracks_file.write_text(content)

    assert get_layer_info(_config(tracks_file)) == expected


def test_get_pitch(tracks_file: Path) -> None:
    """X pitch is the V layer's X track, Y pitch the H layer's Y track."""
    assert get_pitch(_config(tracks_file)) == (Decimal("0.28"), Decimal("0.56"))


@pytest.mark.parametrize(
    ("value", "pitch", "expected"),
    [
        pytest.param(Decimal(10), Decimal(5), Decimal(10), id="no_remainder"),
        pytest.param(Decimal("10.5"), Decimal(5), Decimal(15), id="with_remainder"),
        pytest.param(Decimal(1), Decimal(5), Decimal(5), id="below_pitch"),
        pytest.param(Decimal("10.5"), Decimal(0), Decimal("10.5"), id="zero_pitch"),
        pytest.param(
            Decimal("1.5"), Decimal("0.28"), Decimal("1.68"), id="fractional_pitch"
        ),
        pytest.param(Decimal("-5.5"), Decimal(5), Decimal(-5), id="negative_value"),
    ],
)
def test_round_up_decimal(value: Decimal, pitch: Decimal, expected: Decimal) -> None:
    """`value` rounds up to the next multiple of `pitch`; zero pitch is a no-op."""
    assert round_up_decimal(value, pitch) == expected


class TestRoundDieDimension:
    """Tests for round_die_dimension function.

    A super tile is split into `divisions` equal physical parts during IO
    placement. Rounding the whole dimension to the pitch is not enough: each
    division boundary must land on the grid, so `dimension / divisions` itself
    must be a multiple of the pitch.
    """

    def test_each_division_lands_on_grid(self) -> None:
        # 10.2 across 2 divisions on a 0.5 grid: rounding the total (-> 10.5)
        # leaves 10.5/2 = 5.25 off-grid. Per-division rounding must give 11.0.
        result = round_die_dimension(Decimal("10.2"), Decimal("0.5"), 2)
        assert result == Decimal("11.0")
        assert (result / 2) % Decimal("0.5") == 0

    def test_single_division_matches_round_up(self) -> None:
        # divisions == 1 (a regular tile) is identical to round_up_decimal.
        assert round_die_dimension(Decimal("10.2"), Decimal("0.5"), 1) == Decimal(
            "10.5"
        )

    def test_already_aligned_is_unchanged(self) -> None:
        assert round_die_dimension(Decimal("11.0"), Decimal("0.5"), 2) == Decimal(
            "11.0"
        )


class TestRoundDieArea:
    """Tests for round_die_area function."""

    def test_round_die_area_basic(self, tracks_file: Path) -> None:
        """Each logical division of each axis is rounded onto that axis's pitch."""
        config = _config(
            tracks_file,
            DIE_AREA=(0, 0, 100, 200),
            FABULOUS_TILE_LOGICAL_WIDTH=2,
            FABULOUS_TILE_LOGICAL_HEIGHT=5,
        )

        result = round_die_area(config)

        # 100 / 2 = 50 -> 179 * 0.28 = 50.12, x2 -> 100.24
        # 200 / 5 = 40 -> 72 * 0.56 = 40.32, x5 -> 201.60
        assert result["DIE_AREA"] == (0, 0, Decimal("100.24"), Decimal("201.60"))

    def test_round_die_area_missing_die_area(self, tracks_file: Path) -> None:
        """Test that ValueError is raised when DIE_AREA is missing."""
        with pytest.raises(ValueError, match="DIE_AREA metric not found in state"):
            round_die_area(_config(tracks_file))


class TestGetRoutingObstructions:
    """Tests for get_routing_obstructions function."""

    # Half-pitch guard bands on all four edges of the 100 x 200 die, per layer.
    EDGE_GUARDS: list[tuple[str, Decimal, Decimal, Decimal, Decimal]] = [
        ("M1", Decimal(0), Decimal("-0.17"), Decimal(100), Decimal(0)),
        ("M1", Decimal(0), Decimal(200), Decimal(100), Decimal("200.17")),
        ("M1", Decimal("-0.14"), Decimal(0), Decimal(0), Decimal(200)),
        ("M1", Decimal(100), Decimal(0), Decimal("100.14"), Decimal(200)),
        ("M2", Decimal(0), Decimal("-0.28"), Decimal(100), Decimal(0)),
        ("M2", Decimal(0), Decimal(200), Decimal(100), Decimal("200.28")),
        ("M2", Decimal("-0.23"), Decimal(0), Decimal(0), Decimal(200)),
        ("M2", Decimal(100), Decimal(0), Decimal("100.23"), Decimal(200)),
    ]

    @pytest.mark.parametrize(
        ("custom_obs", "expected_custom"),
        [
            pytest.param(None, [], id="no_custom"),
            pytest.param(
                [("M3", 10, 10, 20, 20)],
                [("M3", 10, 10, 20, 20)],
                id="custom_on_untracked_layer",
            ),
            pytest.param(
                [("M1", 5, 5, 15, 15)],
                [("M1", 5, 5, 15, 15)],
                id="custom_on_tracked_layer",
            ),
        ],
    )
    def test_get_routing_obstructions(
        self,
        tracks_file: Path,
        custom_obs: list[tuple[str, int, int, int, int]] | None,
        expected_custom: list[tuple[str, int, int, int, int]],
    ) -> None:
        """Custom obstructions are kept and every tracked layer gets edge guards."""
        config = _config(
            tracks_file, DIE_AREA=(0, 0, 100, 200), ROUTING_OBSTRUCTIONS=custom_obs
        )

        result = get_routing_obstructions(config)

        assert sorted(result) == sorted(expected_custom + self.EDGE_GUARDS)

    def test_get_routing_obstructions_invalid_format(self, tracks_file: Path) -> None:
        """Test error handling for invalid obstruction format."""
        config = _config(
            tracks_file,
            DIE_AREA=(0, 0, 100, 100),
            ROUTING_OBSTRUCTIONS=[("M1", 10, 10)],
        )

        with pytest.raises(ValueError, match="Invalid obstruction"):
            get_routing_obstructions(config)

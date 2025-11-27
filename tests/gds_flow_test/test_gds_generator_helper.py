"""Tests for GDS generator helper utilities."""

from decimal import Decimal
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from fabulous.fabric_generator.gds_generator.helper import (
    get_layer_info,
    get_pitch,
    round_die_area,
    round_up_decimal,
    get_routing_obstructions,
)


@pytest.fixture
def mock_config():
    """Create a mock config object."""
    config = MagicMock()
    return config


@pytest.fixture
def sample_tracks_file(tmp_path: Path):
    """Create a sample FP_TRACKS_INFO file."""
    tracks_file = tmp_path / "tracks.txt"
    tracks_content = """M1 X 0 0.28
M1 Y 0 0.28
M2 X 0.14 0.56
M2 Y 0 0.56
M3 X 0 0.28
M3 Y 0 0.28
"""
    tracks_file.write_text(tracks_content)
    return tracks_file


class TestGetLayerInfo:
    """Tests for get_layer_info function."""

    def test_get_layer_info_basic(self, sample_tracks_file, mock_config):
        """Test basic layer info retrieval."""
        mock_config.__getitem__.side_effect = lambda key: (
            str(sample_tracks_file) if key == "FP_TRACKS_INFO" else None
        )

        result = get_layer_info(mock_config)

        assert "M1" in result
        assert "M2" in result
        assert "M3" in result
        assert result["M1"]["X"] == (Decimal("0"), Decimal("0.28"))
        assert result["M1"]["Y"] == (Decimal("0"), Decimal("0.28"))
        assert result["M2"]["X"] == (Decimal("0.14"), Decimal("0.56"))

    def test_get_layer_info_with_empty_lines(self, tmp_path: Path, mock_config):
        """Test layer info retrieval with empty lines."""
        tracks_file = tmp_path / "tracks_with_empty.txt"
        tracks_content = """M1 X 0 0.28

M1 Y 0 0.28

M2 X 0.14 0.56
"""
        tracks_file.write_text(tracks_content)
        mock_config.__getitem__.side_effect = lambda key: (
            str(tracks_file) if key == "FP_TRACKS_INFO" else None
        )

        result = get_layer_info(mock_config)

        assert len(result) == 2
        assert "M1" in result
        assert "M2" in result

    def test_get_layer_info_preserves_decimal_precision(
        self, sample_tracks_file, mock_config
    ):
        """Test that Decimal precision is preserved."""
        mock_config.__getitem__.side_effect = lambda key: (
            str(sample_tracks_file) if key == "FP_TRACKS_INFO" else None
        )

        result = get_layer_info(mock_config)

        # Verify that Decimal objects are used
        assert isinstance(result["M2"]["X"][0], Decimal)
        assert isinstance(result["M2"]["X"][1], Decimal)


class TestGetPitch:
    """Tests for get_pitch function."""

    def test_get_pitch_basic(self, sample_tracks_file, mock_config):
        """Test basic pitch retrieval."""
        mock_config.__getitem__.side_effect = lambda key: {
            "FP_TRACKS_INFO": str(sample_tracks_file),
            "FP_IO_VLAYER": "M1",
            "FP_IO_HLAYER": "M2",
        }.get(key)

        x_pitch, y_pitch = get_pitch(mock_config)

        assert x_pitch == Decimal("0.28")
        assert y_pitch == Decimal("0.56")

    def test_get_pitch_returns_tuple_of_decimals(self, sample_tracks_file, mock_config):
        """Test that get_pitch returns Decimal objects."""
        mock_config.__getitem__.side_effect = lambda key: {
            "FP_TRACKS_INFO": str(sample_tracks_file),
            "FP_IO_VLAYER": "M1",
            "FP_IO_HLAYER": "M3",
        }.get(key)

        x_pitch, y_pitch = get_pitch(mock_config)

        assert isinstance(x_pitch, Decimal)
        assert isinstance(y_pitch, Decimal)


class TestRoundUpDecimal:
    """Tests for round_up_decimal function."""

    def test_round_up_decimal_no_remainder(self):
        """Test rounding when value is already multiple of pitch."""
        value = Decimal("10")
        pitch = Decimal("5")
        result = round_up_decimal(value, pitch)
        assert result == Decimal("10")

    def test_round_up_decimal_with_remainder(self):
        """Test rounding when value has remainder."""
        value = Decimal("10.5")
        pitch = Decimal("5")
        result = round_up_decimal(value, pitch)
        assert result == Decimal("15")

    def test_round_up_decimal_small_value(self):
        """Test rounding with value smaller than pitch."""
        value = Decimal("1")
        pitch = Decimal("5")
        result = round_up_decimal(value, pitch)
        assert result == Decimal("5")

    def test_round_up_decimal_zero_pitch(self):
        """Test rounding with zero pitch returns original value."""
        value = Decimal("10.5")
        pitch = Decimal("0")
        result = round_up_decimal(value, pitch)
        assert result == Decimal("10.5")

    def test_round_up_decimal_fractional_pitch(self):
        """Test rounding with fractional pitch."""
        value = Decimal("1.5")
        pitch = Decimal("0.28")
        result = round_up_decimal(value, pitch)
        # 1.5 / 0.28 = 5.357..., so quotient = 5, remainder > 0, so quotient = 6
        # 6 * 0.28 = 1.68
        assert result == Decimal("1.68")

    def test_round_up_decimal_negative_value(self):
        """Test rounding with negative value."""
        value = Decimal("-5.5")
        pitch = Decimal("5")
        result = round_up_decimal(value, pitch)
        # -5.5 // 5 = -2 (floor division)
        # -5.5 % 5 = 4.5 (positive remainder with negative dividend)
        # Since remainder > 0, quotient becomes -2 + 1 = -1
        # -1 * 5 = -5
        assert result == Decimal("-5")


class TestRoundDieArea:
    """Tests for round_die_area function."""

    def test_round_die_area_basic(self, sample_tracks_file, mock_config):
        """Test basic die area rounding."""
        mock_config.__getitem__.side_effect = lambda key: {
            "FP_TRACKS_INFO": str(sample_tracks_file),
            "FP_IO_VLAYER": "M1",
            "FP_IO_HLAYER": "M2",
            "DIE_AREA": (0, 0, 100, 200),
            "FABULOUS_TILE_LOGICAL_WIDTH": "10",
            "FABULOUS_TILE_LOGICAL_HEIGHT": "10",
        }.get(key)
        mock_config.get.side_effect = lambda key: {
            "DIE_AREA": (0, 0, 100, 200),
        }.get(key)
        mock_config.copy.side_effect = lambda **kwargs: {
            **mock_config.__dict__,
            **kwargs,
        }

        result = round_die_area(mock_config)

        # Result should have DIE_AREA with rounded dimensions
        assert result["DIE_AREA"][0] == 0
        assert result["DIE_AREA"][1] == 0
        # Width: 100/10 = 10, 10/0.28 = 35.714..., round up to 36, 36 * 0.28 * 10 = 100.8
        # Height: 200/10 = 20, 20/0.56 = 35.714..., round up to 36, 36 * 0.56 * 10 = 201.6
        assert result["DIE_AREA"][2] > 100
        assert result["DIE_AREA"][3] > 200

    def test_round_die_area_missing_die_area(self, sample_tracks_file, mock_config):
        """Test that ValueError is raised when DIE_AREA is missing."""
        mock_config.__getitem__.side_effect = lambda key: {
            "FP_TRACKS_INFO": str(sample_tracks_file),
            "FP_IO_VLAYER": "M1",
            "FP_IO_HLAYER": "M2",
        }.get(key)
        mock_config.get.return_value = None

        with pytest.raises(ValueError, match="DIE_AREA metric not found in state"):
            round_die_area(mock_config)

    def test_round_die_area_preserves_origin(self, sample_tracks_file, mock_config):
        """Test that rounded die area starts at (0, 0)."""
        mock_config.__getitem__.side_effect = lambda key: {
            "FP_TRACKS_INFO": str(sample_tracks_file),
            "FP_IO_VLAYER": "M1",
            "FP_IO_HLAYER": "M2",
            "DIE_AREA": (0, 0, 100, 100),
            "FABULOUS_TILE_LOGICAL_WIDTH": "1",
            "FABULOUS_TILE_LOGICAL_HEIGHT": "1",
        }.get(key)
        mock_config.get.side_effect = lambda key: {
            "DIE_AREA": (0, 0, 100, 100),
        }.get(key)
        mock_config.copy.side_effect = lambda **kwargs: {
            **mock_config.__dict__,
            **kwargs,
        }

        result = round_die_area(mock_config)

        assert result["DIE_AREA"][0] == 0
        assert result["DIE_AREA"][1] == 0


class TestGetRoutingObstructions:
    """Tests for get_routing_obstructions function."""

    def test_get_routing_obstructions_empty(self, mock_config):
        """Test with no routing obstructions."""
        mock_config.get.return_value = None
        mock_config.__getitem__.side_effect = lambda key: {
            "DIE_AREA": (0, 0, 100, 100),
            "FP_IO_VLAYER": "M1",
            "FP_IO_HLAYER": "M2",
        }.get(key)

        result = get_routing_obstructions(mock_config)

        # Should have default obstructions for M1 and M2
        assert len(result) == 4
        assert ("M1", 0, -1, 100, 0) in result
        assert ("M1", 0, 100, 100, 101) in result
        assert ("M2", -1, 0, 0, 100) in result
        assert ("M2", 100, 0, 101, 100) in result

    def test_get_routing_obstructions_with_custom(self, mock_config):
        """Test with empty obstruction list and default obstructions are added."""
        mock_config.get.return_value = None
        mock_config.__getitem__.side_effect = lambda key: {
            "DIE_AREA": (0, 0, 100, 100),
            "FP_IO_VLAYER": "M1",
            "FP_IO_HLAYER": "M2",
        }.get(key)

        result = get_routing_obstructions(mock_config)

        # Should have default M1 horizontal obstructions
        assert ("M1", 0, -1, 100, 0) in result
        assert ("M1", 0, 100, 100, 101) in result
        # Should have default M2 vertical obstructions
        assert ("M2", -1, 0, 0, 100) in result
        assert ("M2", 100, 0, 101, 100) in result

    def test_get_routing_obstructions_invalid_obstruction(self, mock_config):
        """Test that ValueError is raised for invalid obstructions."""
        obstructions = [("M1", 10, 10)]  # Only 3 values instead of 4
        mock_config.get.return_value = obstructions
        mock_config.__getitem__.side_effect = lambda key: {
            "DIE_AREA": (0, 0, 100, 100),
            "FP_IO_VLAYER": "M3",
            "FP_IO_HLAYER": "M2",
        }.get(key)

        with pytest.raises(ValueError, match="Invalid obstruction"):
            get_routing_obstructions(mock_config)

    def test_get_routing_obstructions_format(self, mock_config):
        """Test that output format is correct."""
        mock_config.get.return_value = None
        mock_config.__getitem__.side_effect = lambda key: {
            "DIE_AREA": (0, 0, 100, 100),
            "FP_IO_VLAYER": "M1",
            "FP_IO_HLAYER": "M2",
        }.get(key)

        result = get_routing_obstructions(mock_config)

        # Each result should be tuple of (layer, x1, y1, x2, y2)
        for obs in result:
            assert len(obs) == 5
            assert isinstance(obs[0], str)  # layer is string
            assert all(isinstance(coord, int) for coord in obs[1:])  # coords are ints

    def test_get_routing_obstructions_default_hlayer_not_overridden(self, mock_config):
        """Test that different V and H layers both get default obstructions."""
        mock_config.get.return_value = None
        mock_config.__getitem__.side_effect = lambda key: {
            "DIE_AREA": (0, 0, 100, 100),
            "FP_IO_VLAYER": "M5",
            "FP_IO_HLAYER": "M6",
        }.get(key)

        result = get_routing_obstructions(mock_config)

        # Should have default M5 horizontal obstructions
        assert ("M5", 0, -1, 100, 0) in result
        assert ("M5", 0, 100, 100, 101) in result
        # Should have default M6 vertical obstructions
        assert ("M6", -1, 0, 0, 100) in result
        assert ("M6", 100, 0, 101, 100) in result

    def test_get_routing_obstructions_multiple_same_layer(self, mock_config):
        """Test when both V and H layers are the same."""
        mock_config.get.return_value = []
        mock_config.__getitem__.side_effect = lambda key: {
            "DIE_AREA": (0, 0, 100, 100),
            "FP_IO_VLAYER": "M1",
            "FP_IO_HLAYER": "M1",
        }.get(key)

        result = get_routing_obstructions(mock_config)

        # When both layers are the same, the function checks VLAYER first (lines 111-114)
        # and adds horizontal obstructions. Then it checks HLAYER (lines 116-119) but layer
        # is already in parsed_obstructions, so no vertical obstructions are added.
        m1_obstructions = [obs for obs in result if obs[0] == "M1"]
        # Should have only 2 obstructions for M1 (the horizontal ones, vertical not added)
        assert len(m1_obstructions) == 2
        assert ("M1", 0, -1, 100, 0) in result
        assert ("M1", 0, 100, 100, 101) in result

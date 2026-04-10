"""Tests for GDS generator helper utilities."""

from decimal import Decimal
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

import pytest
import yaml
from librelane.config.config import Config
from pytest_mock import MockerFixture

from fabulous.fabric_generator.gds_generator.helper import (
    get_layer_info,
    get_pitch,
    get_routing_obstructions,
    merge_config_mappings,
    round_die_area,
    round_up_decimal,
)


@pytest.fixture
def mock_config(mocker: MockerFixture) -> MagicMock:
    """Create a mock config object."""
    return mocker.MagicMock(spec=Config)


@pytest.fixture
def sample_tracks_file(tmp_path: Path) -> Path:
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

    def test_get_layer_info_basic(
        self, sample_tracks_file: Path, mock_config: MagicMock
    ) -> None:
        """Test basic layer info retrieval."""
        mock_config.__getitem__.side_effect = lambda key: (
            str(sample_tracks_file) if key == "FP_TRACKS_INFO" else None
        )

        result = get_layer_info(mock_config)

        assert "M1" in result
        assert "M2" in result
        assert "M3" in result
        assert result["M1"]["X"] == (Decimal(0), Decimal("0.28"))
        assert result["M1"]["Y"] == (Decimal(0), Decimal("0.28"))
        assert result["M2"]["X"] == (Decimal("0.14"), Decimal("0.56"))

    def test_get_layer_info_with_empty_lines(
        self, tmp_path: Path, mock_config: MagicMock
    ) -> None:
        """Test layer info retrieval with empty lines."""
        tracks_file = tmp_path / "tracks_with_empty.txt"
        tracks_content = "M1 X 0 0.28\n\nM1 Y 0 0.28\n\nM2 X 0.14 0.56\n"
        tracks_file.write_text(tracks_content)
        mock_config.__getitem__.side_effect = lambda key: (
            str(tracks_file) if key == "FP_TRACKS_INFO" else None
        )

        result = get_layer_info(mock_config)

        assert len(result) == 2
        assert "M1" in result
        assert "M2" in result

    def test_get_layer_info_preserves_decimal_precision(
        self, sample_tracks_file: Path, mock_config: MagicMock
    ) -> None:
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

    def test_get_pitch_basic(
        self, sample_tracks_file: Path, mock_config: MagicMock
    ) -> None:
        """Test basic pitch retrieval."""
        mock_config.__getitem__.side_effect = lambda key: {
            "FP_TRACKS_INFO": str(sample_tracks_file),
            "IO_PIN_V_LAYER": "M1",
            "IO_PIN_H_LAYER": "M2",
        }.get(key)

        x_pitch, y_pitch = get_pitch(mock_config)

        assert x_pitch == Decimal("0.28")
        assert y_pitch == Decimal("0.56")

    def test_get_pitch_returns_tuple_of_decimals(
        self, sample_tracks_file: Path, mock_config: MagicMock
    ) -> None:
        """Test that get_pitch returns Decimal objects."""
        mock_config.__getitem__.side_effect = lambda key: {
            "FP_TRACKS_INFO": str(sample_tracks_file),
            "IO_PIN_V_LAYER": "M1",
            "IO_PIN_H_LAYER": "M3",
        }.get(key)

        x_pitch, y_pitch = get_pitch(mock_config)

        assert isinstance(x_pitch, Decimal)
        assert isinstance(y_pitch, Decimal)


class TestRoundUpDecimal:
    """Tests for round_up_decimal function."""

    def test_round_up_decimal_no_remainder(self) -> None:
        """Test rounding when value is already multiple of pitch."""
        value = Decimal(10)
        pitch = Decimal(5)
        result = round_up_decimal(value, pitch)
        assert result == Decimal(10)

    def test_round_up_decimal_with_remainder(self) -> None:
        """Test rounding when value has remainder."""
        value = Decimal("10.5")
        pitch = Decimal(5)
        result = round_up_decimal(value, pitch)
        assert result == Decimal(15)

    def test_round_up_decimal_small_value(self) -> None:
        """Test rounding with value smaller than pitch."""
        value = Decimal(1)
        pitch = Decimal(5)
        result = round_up_decimal(value, pitch)
        assert result == Decimal(5)

    def test_round_up_decimal_zero_pitch(self) -> None:
        """Test rounding with zero pitch returns original value."""
        value = Decimal("10.5")
        pitch = Decimal(0)
        result = round_up_decimal(value, pitch)
        assert result == Decimal("10.5")

    def test_round_up_decimal_fractional_pitch(self) -> None:
        """Test rounding with fractional pitch."""
        value = Decimal("1.5")
        pitch = Decimal("0.28")
        result = round_up_decimal(value, pitch)
        assert result == Decimal("1.68")

    def test_round_up_decimal_negative_value(self) -> None:
        """Test rounding with negative value."""
        value = Decimal("-5.5")
        pitch = Decimal(5)
        result = round_up_decimal(value, pitch)
        assert result == Decimal(-5)


class TestMergeConfigMappings:
    """Tests for merge_config_mappings function."""

    def test_merge_nested_dict_one_level(self, tmp_path: Path) -> None:
        """Test one-level nested mapping merge with override precedence."""
        base_config = tmp_path / "base.yaml"
        override_config = tmp_path / "override.yaml"
        base_config.write_text(
            yaml.dump(
                {
                    "NESTED": {"base_only": "keep", "shared": "base"},
                    "SCALAR": "base",
                }
            ),
            encoding="utf-8",
        )
        override_config.write_text(
            yaml.dump(
                {
                    "NESTED": {"shared": "override", "override_only": "new"},
                    "SCALAR": "override",
                }
            ),
            encoding="utf-8",
        )

        merged = merge_config_mappings({}, base_config, override_config)

        assert merged["NESTED"] == {
            "base_only": "keep",
            "shared": "override",
            "override_only": "new",
        }
        assert merged["SCALAR"] == "override"

    def test_merge_replaces_lists(self, tmp_path: Path) -> None:
        """Test list values are replaced by override values."""
        base_config = tmp_path / "base.yaml"
        override_config = tmp_path / "override.yaml"
        base_config.write_text(yaml.dump({"LIST_CFG": ["base"]}), encoding="utf-8")
        override_config.write_text(
            yaml.dump({"LIST_CFG": ["override"]}),
            encoding="utf-8",
        )

        merged = merge_config_mappings({}, base_config, override_config)

        assert merged["LIST_CFG"] == ["override"]

    def test_merge_precedence_base_files_kwargs(self, tmp_path: Path) -> None:
        """Test full three-layer precedence: base < files < kwargs."""
        cfg = tmp_path / "cfg.yaml"
        cfg.write_text(
            yaml.dump(
                {
                    "NESTED": {"a": 1, "shared": "file"},
                    "SCALAR": "file",
                    "FILE_ONLY": "yes",
                }
            ),
            encoding="utf-8",
        )

        result = merge_config_mappings(
            {"SCALAR": "base", "BASE_ONLY": "yes", "NESTED": {"shared": "base"}},
            cfg,
            SCALAR="kwarg",
            NESTED={"shared": "kwarg", "b": 2},
        )

        assert result["SCALAR"] == "kwarg"
        assert result["NESTED"] == {"a": 1, "shared": "kwarg", "b": 2}
        assert result["BASE_ONLY"] == "yes"
        assert result["FILE_ONLY"] == "yes"

    def test_merge_empty_file_is_empty_mapping(self, tmp_path: Path) -> None:
        """Test empty YAML file is treated as an empty mapping."""
        empty_config = tmp_path / "empty.yaml"
        empty_config.write_text("", encoding="utf-8")

        merged = merge_config_mappings({}, empty_config, KEY="value")

        assert merged["KEY"] == "value"

    def test_merge_non_mapping_yaml_raises(self, tmp_path: Path) -> None:
        """Test non-mapping YAML files raise TypeError."""
        bad_config = tmp_path / "bad.yaml"
        bad_config.write_text("- item1\n- item2\n", encoding="utf-8")

        with pytest.raises(TypeError, match="must contain a mapping"):
            merge_config_mappings({}, bad_config)


class TestRoundDieArea:
    """Tests for round_die_area function."""

    def test_round_die_area_basic(
        self, sample_tracks_file: Path, mock_config: MagicMock
    ) -> None:
        """Test basic die area rounding."""
        mock_config.__getitem__.side_effect = lambda key: {
            "FP_TRACKS_INFO": str(sample_tracks_file),
            "IO_PIN_V_LAYER": "M1",
            "IO_PIN_H_LAYER": "M2",
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
        assert result["DIE_AREA"][2] > 100
        assert result["DIE_AREA"][3] > 200

    def test_round_die_area_missing_die_area(
        self, sample_tracks_file: Path, mock_config: MagicMock
    ) -> None:
        """Test that ValueError is raised when DIE_AREA is missing."""
        mock_config.__getitem__.side_effect = lambda key: {
            "FP_TRACKS_INFO": str(sample_tracks_file),
            "IO_PIN_V_LAYER": "M1",
            "IO_PIN_H_LAYER": "M2",
        }.get(key)
        mock_config.get.return_value = None

        with pytest.raises(ValueError, match="DIE_AREA metric not found in state"):
            round_die_area(mock_config)

    def test_round_die_area_preserves_origin(
        self, sample_tracks_file: Path, mock_config: MagicMock
    ) -> None:
        """Test that rounded die area starts at (0, 0)."""
        mock_config.__getitem__.side_effect = lambda key: {
            "FP_TRACKS_INFO": str(sample_tracks_file),
            "IO_PIN_V_LAYER": "M1",
            "IO_PIN_H_LAYER": "M2",
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

    @pytest.mark.parametrize(
        ("custom_obs", "v_layer", "h_layer", "expected_count", "expected_contains"),
        [
            pytest.param(
                None,
                "M1",
                "M2",
                12,
                [
                    ("M1", Decimal(0), Decimal("-0.14"), Decimal(100), Decimal(0)),
                    ("M2", Decimal("-0.28"), Decimal(0), Decimal(0), Decimal(100)),
                ],
                id="no_custom_diff_layers",
            ),
            pytest.param(
                None,
                "M1",
                "M1",
                12,
                [
                    ("M1", Decimal(0), Decimal("-0.14"), Decimal(100), Decimal(0)),
                    ("M1", Decimal("-0.14"), Decimal(0), Decimal(0), Decimal(100)),
                ],
                id="no_custom_same_layer",
            ),
            pytest.param(
                [("M3", 10, 10, 20, 20)],
                "M1",
                "M2",
                13,
                [("M3", 10, 10, 20, 20)],
                id="custom_other_layer",
            ),
            pytest.param(
                [("M1", 5, 5, 15, 15)],
                "M1",
                "M2",
                13,
                [
                    ("M1", 5, 5, 15, 15),
                    ("M1", Decimal(0), Decimal("-0.14"), Decimal(100), Decimal(0)),
                ],
                id="custom_same_layer",
            ),
        ],
    )
    def test_get_routing_obstructions_logic(
        self,
        sample_tracks_file: Path,
        mock_config: MagicMock,
        custom_obs: list[tuple[str, Any, Any, Any, Any]] | None,
        v_layer: str,
        h_layer: str,
        expected_count: int,
        expected_contains: list[tuple[str, Any, Any, Any, Any]],
    ) -> None:
        """Streamlined test for various obstruction scenarios."""
        mock_config.get.return_value = custom_obs
        mock_config.__getitem__.side_effect = lambda key: {
            "DIE_AREA": (0, 0, 100, 100),
            "IO_PIN_V_LAYER": v_layer,
            "IO_PIN_H_LAYER": h_layer,
            "FP_TRACKS_INFO": str(sample_tracks_file),
        }.get(key)

        result = get_routing_obstructions(mock_config)

        assert len(result) == expected_count
        for item in expected_contains:
            assert item in result

    def test_get_routing_obstructions_invalid_format(
        self, sample_tracks_file: Path, mock_config: MagicMock
    ) -> None:
        """Test error handling for invalid obstruction format."""
        mock_config.get.return_value = [("M1", 10, 10)]  # Missing coords
        mock_config.__getitem__.side_effect = lambda key: {
            "DIE_AREA": (0, 0, 100, 100),
            "IO_PIN_V_LAYER": "M1",
            "IO_PIN_H_LAYER": "M2",
            "FP_TRACKS_INFO": str(sample_tracks_file),
        }.get(key)

        with pytest.raises(ValueError, match="Invalid obstruction"):
            get_routing_obstructions(mock_config)

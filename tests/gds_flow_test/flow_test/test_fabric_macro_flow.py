"""Tests for FABulousFabricMacroFlow - Fabric stitching flow.

Tests focus on:
- Flow initialization and configuration
- Die area computation
- Macro overlap validation
- Tile size validation
"""

from decimal import Decimal
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from librelane.config.variable import Instance, Macro, Orientation

from FABulous.fabric_generator.gds_generator.flows.fabric_macro_flow import (
    FABulousFabricMacroFlow,
)


class TestComputeDieArea:
    """Tests for _compute_die_area method."""

    @pytest.fixture
    def mock_flow(self):
        """Create a minimal mock flow instance for testing methods."""
        flow = MagicMock(spec=FABulousFabricMacroFlow)
        flow._compute_die_area = FABulousFabricMacroFlow._compute_die_area
        return flow

    def test_compute_die_area_basic(self, mock_flow):
        """Test basic die area computation with no spacing."""
        row_heights = [Decimal("100"), Decimal("200")]
        column_widths = [Decimal("150"), Decimal("250")]
        halo_spacing = (Decimal("0"), Decimal("0"), Decimal("0"), Decimal("0"))
        tile_spacing = (Decimal("0"), Decimal("0"))

        width, height = mock_flow._compute_die_area(
            mock_flow, row_heights, column_widths, halo_spacing, tile_spacing
        )

        assert width == Decimal("400"), f"Expected 400, got {width}"
        assert height == Decimal("300"), f"Expected 300, got {height}"

    def test_compute_die_area_with_halo_spacing(self, mock_flow):
        """Test die area computation with halo spacing."""
        row_heights = [Decimal("100")]
        column_widths = [Decimal("200")]
        halo_spacing = (Decimal("10"), Decimal("20"), Decimal("30"), Decimal("40"))
        tile_spacing = (Decimal("0"), Decimal("0"))

        width, height = mock_flow._compute_die_area(
            mock_flow, row_heights, column_widths, halo_spacing, tile_spacing
        )

        # width = left + right + sum(widths) = 10 + 30 + 200 = 240
        # height = bottom + top + sum(heights) = 20 + 40 + 100 = 160
        assert width == Decimal("240"), f"Expected 240, got {width}"
        assert height == Decimal("160"), f"Expected 160, got {height}"

    def test_compute_die_area_with_tile_spacing(self, mock_flow):
        """Test die area computation with tile spacing."""
        row_heights = [Decimal("100"), Decimal("100"), Decimal("100")]
        column_widths = [Decimal("200"), Decimal("200")]
        halo_spacing = (Decimal("0"), Decimal("0"), Decimal("0"), Decimal("0"))
        tile_spacing = (Decimal("5"), Decimal("10"))

        width, height = mock_flow._compute_die_area(
            mock_flow, row_heights, column_widths, halo_spacing, tile_spacing
        )

        # width = sum(widths) + spacing * (cols - 1) = 400 + 5 * 1 = 405
        # height = sum(heights) + spacing * (rows - 1) = 300 + 10 * 2 = 320
        assert width == Decimal("405"), f"Expected 405, got {width}"
        assert height == Decimal("320"), f"Expected 320, got {height}"

    def test_compute_die_area_empty_grid(self, mock_flow):
        """Test die area computation with empty grid."""
        row_heights = []
        column_widths = []
        halo_spacing = (Decimal("10"), Decimal("10"), Decimal("10"), Decimal("10"))
        tile_spacing = (Decimal("5"), Decimal("5"))

        width, height = mock_flow._compute_die_area(
            mock_flow, row_heights, column_widths, halo_spacing, tile_spacing
        )

        # Should just be halo spacing with no tiles
        assert width == Decimal("20"), f"Expected 20, got {width}"
        assert height == Decimal("20"), f"Expected 20, got {height}"


class TestValidateNoMacroOverlaps:
    """Tests for _validate_no_macro_overlaps method."""

    @pytest.fixture
    def mock_flow(self):
        """Create a minimal mock flow instance for testing methods."""
        flow = MagicMock(spec=FABulousFabricMacroFlow)
        flow._validate_no_macro_overlaps = FABulousFabricMacroFlow._validate_no_macro_overlaps
        return flow

    def _create_macro(self, instances):
        """Helper to create a valid Macro object for testing."""
        return Macro(
            gds=[Path("dummy.gds")],
            lef=[Path("dummy.lef")],
            vh=[],
            nl=[],
            pnl=[],
            spef={},
            instances=instances
        )

    def test_no_overlaps_single_macro(self, mock_flow):
        """Test validation passes with a single macro."""
        instance = Instance(location=(Decimal("0"), Decimal("0")), orientation=Orientation.N)
        macro = self._create_macro({"inst1": instance})
        macros = {"tile1": macro}
        tile_sizes = {"tile1": (Decimal("100"), Decimal("100"))}

        result = mock_flow._validate_no_macro_overlaps(mock_flow, macros, tile_sizes)
        assert result is True

    def test_no_overlaps_multiple_macros(self, mock_flow):
        """Test validation passes with non-overlapping macros."""
        instance1 = Instance(location=(Decimal("0"), Decimal("0")), orientation=Orientation.N)
        instance2 = Instance(location=(Decimal("200"), Decimal("0")), orientation=Orientation.N)

        macro1 = self._create_macro({"inst1": instance1})
        macro2 = self._create_macro({"inst2": instance2})

        macros = {"tile1": macro1, "tile2": macro2}
        tile_sizes = {
            "tile1": (Decimal("100"), Decimal("100")),
            "tile2": (Decimal("100"), Decimal("100")),
        }

        result = mock_flow._validate_no_macro_overlaps(mock_flow, macros, tile_sizes)
        assert result is True

    def test_overlapping_macros_raises_error(self, mock_flow):
        """Test validation raises error when macros overlap."""
        instance1 = Instance(location=(Decimal("0"), Decimal("0")), orientation=Orientation.N)
        instance2 = Instance(location=(Decimal("50"), Decimal("50")), orientation=Orientation.N)

        macro1 = self._create_macro({"inst1": instance1})
        macro2 = self._create_macro({"inst2": instance2})

        macros = {"tile1": macro1, "tile2": macro2}
        tile_sizes = {
            "tile1": (Decimal("100"), Decimal("100")),
            "tile2": (Decimal("100"), Decimal("100")),
        }

        with pytest.raises(ValueError, match="overlapping macros detected"):
            mock_flow._validate_no_macro_overlaps(mock_flow, macros, tile_sizes)

    def test_adjacent_macros_no_overlap(self, mock_flow):
        """Test that adjacent (touching) macros don't count as overlapping."""
        instance1 = Instance(location=(Decimal("0"), Decimal("0")), orientation=Orientation.N)
        instance2 = Instance(location=(Decimal("100"), Decimal("0")), orientation=Orientation.N)

        macro1 = self._create_macro({"inst1": instance1})
        macro2 = self._create_macro({"inst2": instance2})

        macros = {"tile1": macro1, "tile2": macro2}
        tile_sizes = {
            "tile1": (Decimal("100"), Decimal("100")),
            "tile2": (Decimal("100"), Decimal("100")),
        }

        result = mock_flow._validate_no_macro_overlaps(mock_flow, macros, tile_sizes)
        assert result is True

    def test_multiple_instances_in_same_macro(self, mock_flow):
        """Test validation with multiple instances in the same macro."""
        instance1 = Instance(location=(Decimal("0"), Decimal("0")), orientation=Orientation.N)
        instance2 = Instance(location=(Decimal("200"), Decimal("0")), orientation=Orientation.N)

        macro = self._create_macro({"inst1": instance1, "inst2": instance2})

        macros = {"tile1": macro}
        tile_sizes = {"tile1": (Decimal("100"), Decimal("100"))}

        result = mock_flow._validate_no_macro_overlaps(mock_flow, macros, tile_sizes)
        assert result is True


class TestValidateTileSizes:
    """Tests for _validate_tile_sizes method."""

    @pytest.fixture
    def mock_flow(self):
        """Create a minimal mock flow instance for testing methods."""
        flow = MagicMock(spec=FABulousFabricMacroFlow)
        flow._validate_tile_sizes = FABulousFabricMacroFlow._validate_tile_sizes
        return flow

    @pytest.fixture
    def mock_fabric(self):
        """Create a minimal mock fabric for testing."""
        fabric = MagicMock()
        fabric.superTileDic = {}
        return fabric

    def test_valid_tile_sizes_aligned(self, mock_flow, mock_fabric):
        """Test validation passes when tiles are aligned to pitch."""
        tile_sizes = {
            "tile1": (Decimal("100"), Decimal("200")),
            "tile2": (Decimal("50"), Decimal("100")),
        }
        pitch_x = Decimal("50")
        pitch_y = Decimal("100")

        result = mock_flow._validate_tile_sizes(
            mock_flow, mock_fabric, tile_sizes, pitch_x, pitch_y
        )
        assert result is True

    def test_invalid_tile_width_not_aligned(self, mock_flow, mock_fabric):
        """Test validation fails when tile width is not aligned."""
        tile_sizes = {
            "tile1": (Decimal("75"), Decimal("100")),  # 75 not multiple of 50
        }
        pitch_x = Decimal("50")
        pitch_y = Decimal("100")

        with pytest.raises(ValueError, match="Tile size validation failed"):
            mock_flow._validate_tile_sizes(
                mock_flow, mock_fabric, tile_sizes, pitch_x, pitch_y
            )

    def test_invalid_tile_height_not_aligned(self, mock_flow, mock_fabric):
        """Test validation fails when tile height is not aligned."""
        tile_sizes = {
            "tile1": (Decimal("100"), Decimal("75")),  # 75 not multiple of 50
        }
        pitch_x = Decimal("50")
        pitch_y = Decimal("50")

        with pytest.raises(ValueError, match="Tile size validation failed"):
            mock_flow._validate_tile_sizes(
                mock_flow, mock_fabric, tile_sizes, pitch_x, pitch_y
            )

    def test_zero_pitch_handling(self, mock_flow, mock_fabric):
        """Test validation handles zero pitch gracefully."""
        tile_sizes = {
            "tile1": (Decimal("100"), Decimal("200")),
        }
        pitch_x = Decimal("0")
        pitch_y = Decimal("0")

        # Should not raise - zero pitch means no alignment check
        result = mock_flow._validate_tile_sizes(
            mock_flow, mock_fabric, tile_sizes, pitch_x, pitch_y
        )
        assert result is True

    def test_supertile_validation(self, mock_flow):
        """Test validation also checks supertiles."""
        fabric = MagicMock()
        fabric.superTileDic = {"super1": MagicMock()}

        tile_sizes = {
            "tile1": (Decimal("100"), Decimal("200")),
            "super1": (Decimal("75"), Decimal("200")),  # Not aligned
        }
        pitch_x = Decimal("50")
        pitch_y = Decimal("100")

        with pytest.raises(ValueError, match="Tile size validation failed"):
            mock_flow._validate_tile_sizes(
                mock_flow, fabric, tile_sizes, pitch_x, pitch_y
            )

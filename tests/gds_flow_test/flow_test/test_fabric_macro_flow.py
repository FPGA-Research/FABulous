"""Tests for FABulousFabricMacroFlow - Fabric stitching flow.

Tests focus on:
- Flow initialization and configuration
- Die area computation
- Macro overlap validation
- Tile size validation
- Row and column size computation
"""

# ruff: noqa: SLF001

from decimal import Decimal
from typing import Any
from unittest.mock import MagicMock

import pytest
from conftest import create_instance, create_macro
from librelane.config.variable import Orientation
from pytest_mock import MockerFixture

from FABulous.fabric_generator.gds_generator.flows.fabric_macro_flow import (
    FABulousFabricMacroFlow,
    configs,
    subs,
)


class TestComputeDieArea:
    """Tests for _compute_die_area method."""

    @pytest.fixture
    def flow(self, mocker: MockerFixture) -> MagicMock:
        """Create a mock flow with _compute_die_area method bound."""
        mock_flow = mocker.MagicMock(spec=FABulousFabricMacroFlow)
        mock_flow._compute_die_area = FABulousFabricMacroFlow._compute_die_area
        return mock_flow

    def test_compute_die_area_basic(self, flow: MagicMock) -> None:
        """Test basic die area computation with no spacing."""
        row_heights = [Decimal(100), Decimal(200)]
        column_widths = [Decimal(150), Decimal(250)]
        halo_spacing = (Decimal(0), Decimal(0), Decimal(0), Decimal(0))
        tile_spacing = (Decimal(0), Decimal(0))

        width, height = flow._compute_die_area(
            flow, row_heights, column_widths, halo_spacing, tile_spacing
        )

        assert width == Decimal(400), f"Expected 400, got {width}"
        assert height == Decimal(300), f"Expected 300, got {height}"

    def test_compute_die_area_with_halo_spacing(self, flow: MagicMock) -> None:
        """Test die area computation with halo spacing."""
        row_heights = [Decimal(100)]
        column_widths = [Decimal(200)]
        halo_spacing = (Decimal(10), Decimal(20), Decimal(30), Decimal(40))
        tile_spacing = (Decimal(0), Decimal(0))

        width, height = flow._compute_die_area(
            flow, row_heights, column_widths, halo_spacing, tile_spacing
        )

        # width = left + right + sum(widths) = 10 + 30 + 200 = 240
        # height = bottom + top + sum(heights) = 20 + 40 + 100 = 160
        assert width == Decimal(240), f"Expected 240, got {width}"
        assert height == Decimal(160), f"Expected 160, got {height}"

    def test_compute_die_area_with_tile_spacing(self, flow: MagicMock) -> None:
        """Test die area computation with tile spacing."""
        row_heights = [Decimal(100), Decimal(100), Decimal(100)]
        column_widths = [Decimal(200), Decimal(200)]
        halo_spacing = (Decimal(0), Decimal(0), Decimal(0), Decimal(0))
        tile_spacing = (Decimal(5), Decimal(10))

        width, height = flow._compute_die_area(
            flow, row_heights, column_widths, halo_spacing, tile_spacing
        )

        # width = sum(widths) + spacing * (cols - 1) = 400 + 5 * 1 = 405
        # height = sum(heights) + spacing * (rows - 1) = 300 + 10 * 2 = 320
        assert width == Decimal(405), f"Expected 405, got {width}"
        assert height == Decimal(320), f"Expected 320, got {height}"

    def test_compute_die_area_empty_grid(self, flow: MagicMock) -> None:
        """Test die area computation with empty grid."""
        row_heights: list[Decimal] = []
        column_widths: list[Decimal] = []
        halo_spacing = (Decimal(10), Decimal(10), Decimal(10), Decimal(10))
        tile_spacing = (Decimal(5), Decimal(5))

        width, height = flow._compute_die_area(
            flow, row_heights, column_widths, halo_spacing, tile_spacing
        )

        # Should just be halo spacing with no tiles
        assert width == Decimal(20), f"Expected 20, got {width}"
        assert height == Decimal(20), f"Expected 20, got {height}"


class TestValidateNoMacroOverlaps:
    """Tests for _validate_no_macro_overlaps method."""

    @pytest.fixture
    def flow(self, mocker: MockerFixture) -> MagicMock:
        """Create a mock flow with _validate_no_macro_overlaps method bound."""
        mock_flow = mocker.MagicMock(spec=FABulousFabricMacroFlow)
        mock_flow._validate_no_macro_overlaps = (
            FABulousFabricMacroFlow._validate_no_macro_overlaps
        )
        return mock_flow

    def test_no_overlaps_single_macro(self, flow: MagicMock) -> None:
        """Test validation passes with a single macro."""
        instance = create_instance(Decimal(0), Decimal(0))
        macro = create_macro({"inst1": instance})
        macros = {"tile1": macro}
        tile_sizes = {"tile1": (Decimal(100), Decimal(100))}

        result = flow._validate_no_macro_overlaps(flow, macros, tile_sizes)
        assert result is True

    def test_no_overlaps_multiple_macros(self, flow: MagicMock) -> None:
        """Test validation passes with non-overlapping macros."""
        instance1 = create_instance(Decimal(0), Decimal(0))
        instance2 = create_instance(Decimal(200), Decimal(0))

        macro1 = create_macro({"inst1": instance1})
        macro2 = create_macro({"inst2": instance2})

        macros = {"tile1": macro1, "tile2": macro2}
        tile_sizes = {
            "tile1": (Decimal(100), Decimal(100)),
            "tile2": (Decimal(100), Decimal(100)),
        }

        result = flow._validate_no_macro_overlaps(flow, macros, tile_sizes)
        assert result is True

    def test_overlapping_macros_raises_error(self, flow: MagicMock) -> None:
        """Test validation raises error when macros overlap."""
        instance1 = create_instance(Decimal(0), Decimal(0))
        instance2 = create_instance(Decimal(50), Decimal(50))

        macro1 = create_macro({"inst1": instance1})
        macro2 = create_macro({"inst2": instance2})

        macros = {"tile1": macro1, "tile2": macro2}
        tile_sizes = {
            "tile1": (Decimal(100), Decimal(100)),
            "tile2": (Decimal(100), Decimal(100)),
        }

        with pytest.raises(ValueError, match="overlapping macros detected"):
            flow._validate_no_macro_overlaps(flow, macros, tile_sizes)

    def test_adjacent_macros_no_overlap(self, flow: MagicMock) -> None:
        """Test that adjacent (touching) macros don't count as overlapping."""
        instance1 = create_instance(Decimal(0), Decimal(0))
        instance2 = create_instance(Decimal(100), Decimal(0))

        macro1 = create_macro({"inst1": instance1})
        macro2 = create_macro({"inst2": instance2})

        macros = {"tile1": macro1, "tile2": macro2}
        tile_sizes = {
            "tile1": (Decimal(100), Decimal(100)),
            "tile2": (Decimal(100), Decimal(100)),
        }

        result = flow._validate_no_macro_overlaps(flow, macros, tile_sizes)
        assert result is True

    def test_multiple_instances_in_same_macro(self, flow: MagicMock) -> None:
        """Test validation with multiple instances in the same macro."""
        instance1 = create_instance(Decimal(0), Decimal(0))
        instance2 = create_instance(Decimal(200), Decimal(0))

        macro = create_macro({"inst1": instance1, "inst2": instance2})

        macros = {"tile1": macro}
        tile_sizes = {"tile1": (Decimal(100), Decimal(100))}

        result = flow._validate_no_macro_overlaps(flow, macros, tile_sizes)
        assert result is True


class TestValidateTileSizes:
    """Tests for _validate_tile_sizes method."""

    @pytest.fixture
    def flow(self, mocker: MockerFixture) -> MagicMock:
        """Create a mock flow with _validate_tile_sizes method bound."""
        mock_flow = mocker.MagicMock(spec=FABulousFabricMacroFlow)
        mock_flow._validate_tile_sizes = FABulousFabricMacroFlow._validate_tile_sizes
        return mock_flow

    def test_valid_tile_sizes_aligned(
        self, flow: MagicMock, mock_fabric: MagicMock
    ) -> None:
        """Test validation passes when tiles are aligned to pitch."""
        tile_sizes = {
            "tile1": (Decimal(100), Decimal(200)),
            "tile2": (Decimal(50), Decimal(100)),
        }
        pitch_x = Decimal(50)
        pitch_y = Decimal(100)

        result = flow._validate_tile_sizes(
            flow, mock_fabric, tile_sizes, pitch_x, pitch_y
        )
        assert result is True

    def test_invalid_tile_width_not_aligned(
        self, flow: MagicMock, mock_fabric: MagicMock
    ) -> None:
        """Test validation fails when tile width is not aligned."""
        tile_sizes = {
            "tile1": (Decimal(75), Decimal(100)),  # 75 not multiple of 50
        }
        pitch_x = Decimal(50)
        pitch_y = Decimal(100)

        with pytest.raises(ValueError, match="Tile size validation failed"):
            flow._validate_tile_sizes(
                flow, mock_fabric, tile_sizes, pitch_x, pitch_y
            )

    def test_invalid_tile_height_not_aligned(
        self, flow: MagicMock, mock_fabric: MagicMock
    ) -> None:
        """Test validation fails when tile height is not aligned."""
        tile_sizes = {
            "tile1": (Decimal(100), Decimal(75)),  # 75 not multiple of 50
        }
        pitch_x = Decimal(50)
        pitch_y = Decimal(50)

        with pytest.raises(ValueError, match="Tile size validation failed"):
            flow._validate_tile_sizes(
                flow, mock_fabric, tile_sizes, pitch_x, pitch_y
            )

    def test_zero_pitch_handling(
        self, flow: MagicMock, mock_fabric: MagicMock
    ) -> None:
        """Test validation handles zero pitch gracefully."""
        tile_sizes = {
            "tile1": (Decimal(100), Decimal(200)),
        }
        pitch_x = Decimal(0)
        pitch_y = Decimal(0)

        # Should not raise - zero pitch means no alignment check
        result = flow._validate_tile_sizes(
            flow, mock_fabric, tile_sizes, pitch_x, pitch_y
        )
        assert result is True

    def test_supertile_validation(
        self, flow: MagicMock, mocker: MockerFixture
    ) -> None:
        """Test validation also checks supertiles."""
        fabric = mocker.MagicMock()
        fabric.superTileDic = {"super1": mocker.MagicMock()}

        tile_sizes = {
            "tile1": (Decimal(100), Decimal(200)),
            "super1": (Decimal(75), Decimal(200)),  # Not aligned
        }
        pitch_x = Decimal(50)
        pitch_y = Decimal(100)

        with pytest.raises(ValueError, match="Tile size validation failed"):
            flow._validate_tile_sizes(flow, fabric, tile_sizes, pitch_x, pitch_y)


class TestComputeRowAndColumnSizes:
    """Tests for _compute_row_and_column_sizes method."""

    @pytest.fixture
    def flow(self, mocker: MockerFixture) -> MagicMock:
        """Create a mock flow with _compute_row_and_column_sizes method bound."""
        mock_flow = mocker.MagicMock(spec=FABulousFabricMacroFlow)
        mock_flow._compute_row_and_column_sizes = (
            FABulousFabricMacroFlow._compute_row_and_column_sizes
        )
        return mock_flow

    def test_compute_sizes_simple_grid(
        self, flow: MagicMock, mocker: MockerFixture
    ) -> None:
        """Test computing sizes for a simple 2x2 grid."""
        fabric = mocker.MagicMock()
        fabric.numberOfRows = 2
        fabric.numberOfColumns = 2
        fabric.superTileDic = {}

        # Mock tile
        tile1 = mocker.MagicMock()
        tile1.name = "tile1"

        # Iterator returns (x, y), tile
        fabric.__iter__ = mocker.MagicMock(
            return_value=iter(
                [
                    ((0, 0), tile1),
                    ((1, 0), tile1),
                    ((0, 1), tile1),
                    ((1, 1), tile1),
                ]
            )
        )

        tile_sizes = {"tile1": (Decimal(100), Decimal(50))}

        row_heights, col_widths = flow._compute_row_and_column_sizes(
            flow, fabric, tile_sizes
        )

        assert len(row_heights) == 2
        assert len(col_widths) == 2
        assert row_heights[0] == Decimal(50)
        assert row_heights[1] == Decimal(50)
        assert col_widths[0] == Decimal(100)
        assert col_widths[1] == Decimal(100)

    def test_compute_sizes_with_none_tiles(
        self, flow: MagicMock, mocker: MockerFixture
    ) -> None:
        """Test computing sizes when some tiles are None."""
        fabric = mocker.MagicMock()
        fabric.numberOfRows = 2
        fabric.numberOfColumns = 2
        fabric.superTileDic = {}

        tile1 = mocker.MagicMock()
        tile1.name = "tile1"

        # Only two tiles, rest are None
        fabric.__iter__ = mocker.MagicMock(
            return_value=iter(
                [
                    ((0, 0), tile1),
                    ((1, 0), None),
                    ((0, 1), None),
                    ((1, 1), tile1),
                ]
            )
        )

        tile_sizes = {"tile1": (Decimal(100), Decimal(50))}

        row_heights, col_widths = flow._compute_row_and_column_sizes(
            flow, fabric, tile_sizes
        )

        # Should still compute sizes from available tiles
        assert len(row_heights) == 2
        assert len(col_widths) == 2

    def test_compute_sizes_non_uniform_raises_error(
        self, flow: MagicMock, mocker: MockerFixture
    ) -> None:
        """Test that non-uniform tile sizes in a column raise error."""
        fabric = mocker.MagicMock()
        fabric.numberOfRows = 2
        fabric.numberOfColumns = 1
        fabric.superTileDic = {}

        tile1 = mocker.MagicMock()
        tile1.name = "tile1"
        tile2 = mocker.MagicMock()
        tile2.name = "tile2"

        fabric.__iter__ = mocker.MagicMock(
            return_value=iter(
                [
                    ((0, 0), tile1),
                    ((0, 1), tile2),
                ]
            )
        )

        # Different widths for same column
        tile_sizes = {
            "tile1": (Decimal(100), Decimal(50)),
            "tile2": (Decimal(150), Decimal(50)),  # Different width
        }

        with pytest.raises(ValueError, match="Non-uniform tile widths"):
            flow._compute_row_and_column_sizes(flow, fabric, tile_sizes)


class TestFlowConfiguration:
    """Tests for flow configuration and class attributes."""

    def test_flow_has_substitutions(self) -> None:
        """Test that flow has expected substitutions."""
        assert "OpenROAD.STAPrePNR*" in subs
        assert subs["OpenROAD.STAPrePNR*"] is None

    def test_flow_has_fabulous_tile_spacing_config(self) -> None:
        """Test flow has FABULOUS_TILE_SPACING config var."""
        config_names = [var.name for var in configs]
        assert "FABULOUS_TILE_SPACING" in config_names

    def test_flow_has_fabulous_halo_spacing_config(self) -> None:
        """Test flow has FABULOUS_HALO_SPACING config var."""
        config_names = [var.name for var in configs]
        assert "FABULOUS_HALO_SPACING" in config_names

    def test_flow_has_fabulous_spef_corners_config(self) -> None:
        """Test flow has FABULOUS_SPEF_CORNERS config var."""
        config_names = [var.name for var in configs]
        assert "FABULOUS_SPEF_CORNERS" in config_names

    def test_io_placement_substitution(self) -> None:
        """Test IO placement substitution."""
        from FABulous.fabric_generator.gds_generator.steps.fabric_IO_placement import (
            FABulousFabricIOPlacement,
        )

        assert subs["Odb.CustomIOPlacement"] == FABulousFabricIOPlacement

    def test_pdn_substitution(self) -> None:
        """Test PDN substitution."""
        from FABulous.fabric_generator.gds_generator.steps.odb_connect_power import (
            FABulousPower,
        )

        assert subs["OpenROAD.GeneratePDN"] == FABulousPower


class TestMacroOverlapEdgeCases:
    """Additional edge case tests for macro overlap validation."""

    @pytest.fixture
    def flow(self, mocker: MockerFixture) -> MagicMock:
        """Create a mock flow with _validate_no_macro_overlaps method bound."""
        mock_flow = mocker.MagicMock(spec=FABulousFabricMacroFlow)
        mock_flow._validate_no_macro_overlaps = (
            FABulousFabricMacroFlow._validate_no_macro_overlaps
        )
        return mock_flow

    def test_y_overlap_only(self, flow: MagicMock) -> None:
        """Test macros that overlap in Y but not X don't overlap."""
        instance1 = create_instance(Decimal(0), Decimal(0))
        instance2 = create_instance(Decimal(200), Decimal(50))

        macro1 = create_macro({"inst1": instance1})
        macro2 = create_macro({"inst2": instance2})

        macros = {"tile1": macro1, "tile2": macro2}
        tile_sizes = {
            "tile1": (Decimal(100), Decimal(100)),
            "tile2": (Decimal(100), Decimal(100)),
        }

        # No overlap - they overlap in Y (0-100 and 50-150) but not in X
        result = flow._validate_no_macro_overlaps(flow, macros, tile_sizes)
        assert result is True

    def test_x_overlap_only(self, flow: MagicMock) -> None:
        """Test macros that overlap in X but not Y don't overlap."""
        instance1 = create_instance(Decimal(0), Decimal(0))
        instance2 = create_instance(Decimal(50), Decimal(200))

        macro1 = create_macro({"inst1": instance1})
        macro2 = create_macro({"inst2": instance2})

        macros = {"tile1": macro1, "tile2": macro2}
        tile_sizes = {
            "tile1": (Decimal(100), Decimal(100)),
            "tile2": (Decimal(100), Decimal(100)),
        }

        # No overlap - they overlap in X (0-100 and 50-150) but not in Y
        result = flow._validate_no_macro_overlaps(flow, macros, tile_sizes)
        assert result is True

    def test_instance_without_location(self, flow: MagicMock) -> None:
        """Test handling of instance without location set."""
        from librelane.config.variable import Instance

        instance = Instance(location=None, orientation=Orientation.N)
        macro = create_macro({"inst1": instance})

        macros = {"tile1": macro}
        tile_sizes = {"tile1": (Decimal(100), Decimal(100))}

        # Should not raise - just logs error
        result = flow._validate_no_macro_overlaps(flow, macros, tile_sizes)
        assert result is True

    def test_tile_not_in_sizes(self, flow: MagicMock) -> None:
        """Test handling when tile is not in tile_sizes."""
        instance = create_instance(Decimal(0), Decimal(0))
        macro = create_macro({"inst1": instance})

        macros = {"unknown_tile": macro}
        tile_sizes: dict[str, Any] = {}  # Empty

        # Should not raise - just logs error
        result = flow._validate_no_macro_overlaps(flow, macros, tile_sizes)
        assert result is True

    def test_empty_macros_dict(self, flow: MagicMock) -> None:
        """Test with empty macros dictionary."""
        result = flow._validate_no_macro_overlaps(flow, {}, {})
        assert result is True


class TestFlowSteps:
    """Tests for flow step configuration."""

    def test_flow_steps_attribute(self) -> None:
        """Test that flow has Steps attribute."""
        assert hasattr(FABulousFabricMacroFlow, "Steps")
        assert isinstance(FABulousFabricMacroFlow.Steps, list)

    def test_flow_substitutions_attribute(self) -> None:
        """Test that flow has Substitutions attribute."""
        assert hasattr(FABulousFabricMacroFlow, "Substitutions")

    def test_flow_config_vars_attribute(self) -> None:
        """Test that flow has config_vars attribute."""
        assert hasattr(FABulousFabricMacroFlow, "config_vars")
        assert isinstance(FABulousFabricMacroFlow.config_vars, list)

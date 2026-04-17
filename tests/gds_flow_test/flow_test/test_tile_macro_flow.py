"""Tests for FABulousTileVerilogMacroFlow - Tile macro generation flow.

Tests focus on:
- Flow initialization with various parameters
- Configuration merging and validation
- OptMode handling
- DIE_AREA validation
- Logical dimension calculation for Tile vs SuperTile
- Routing obstructions generation
- Error handling for invalid configurations

Note: These tests use shared fixtures from conftest.py that mock the PDK
and Config.load to avoid requiring actual PDK files.
"""

from decimal import Decimal
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

import pytest
from librelane.flows.flow import FlowException

from fabulous.fabric_generator.gds_generator.flows.tile_macro_flow import (
    FABulousTileVerilogMacroFlow,
)
from fabulous.fabric_generator.gds_generator.steps.tile_optimisation import OptMode


@pytest.mark.usefixtures("mock_config_load")
class TestFABulousTileVerilogMacroFlowInit:
    """Tests for FABulousTileVerilogMacroFlow initialization and configuration."""

    def _create_flow(
        self,
        *,
        tile_type: MagicMock,
        io_pin_config: Path,
        mock_pdk_root: dict[str, Any],
        opt_mode: OptMode | None = OptMode.FIND_MIN_WIDTH,
        **kwargs: dict,
    ) -> FABulousTileVerilogMacroFlow:
        """Create a flow with shared defaults used across tests."""
        flow_kwargs: dict[str, Any] = {
            "tile_type": tile_type,
            "io_pin_config": io_pin_config,
            "opt_mode": opt_mode,
            "pdk": mock_pdk_root["pdk"],
            "pdk_root": mock_pdk_root["pdk_root"],
            "models_pack_path": Path("/fake/models/pack"),
        }
        flow_kwargs.update(kwargs)
        return FABulousTileVerilogMacroFlow(**flow_kwargs)

    def test_init_with_basic_tile(
        self,
        mock_tile: MagicMock,
        io_pin_config: Path,
        mock_pdk_root: dict[str, Any],
    ) -> None:
        """Test initialization with a basic Tile."""
        flow: FABulousTileVerilogMacroFlow = self._create_flow(
            tile_type=mock_tile,
            io_pin_config=io_pin_config,
            mock_pdk_root=mock_pdk_root,
        )

        assert flow.config["DESIGN_NAME"] == "TestTile"
        assert flow.config["FABULOUS_OPT_MODE"] == OptMode.FIND_MIN_WIDTH
        assert flow.config["FABULOUS_TILE_LOGICAL_WIDTH"] == 1
        assert flow.config["FABULOUS_TILE_LOGICAL_HEIGHT"] == 1
        assert flow.config["FABULOUS_IO_PIN_ORDER_CFG"] == str(io_pin_config)

    def test_init_with_supertile(
        self,
        mock_supertile: MagicMock,
        io_pin_config: Path,
        mock_pdk_root: dict[str, Any],
    ) -> None:
        """Test initialization with a SuperTile sets correct logical dimensions."""
        flow: FABulousTileVerilogMacroFlow = self._create_flow(
            tile_type=mock_supertile,
            io_pin_config=io_pin_config,
            opt_mode=OptMode.FIND_MIN_HEIGHT,
            mock_pdk_root=mock_pdk_root,
        )

        assert flow.config["DESIGN_NAME"] == "TestSuperTile"
        assert flow.config["FABULOUS_TILE_LOGICAL_WIDTH"] == 4
        assert flow.config["FABULOUS_TILE_LOGICAL_HEIGHT"] == 3

    def test_config_merging_precedence(
        self,
        mock_tile: MagicMock,
        io_pin_config: Path,
        base_config_file: Path,
        override_config_file: Path,
        mock_pdk_root: dict[str, Any],
    ) -> None:
        """Test config merging follows correct precedence: custom > override > base."""
        flow: FABulousTileVerilogMacroFlow = self._create_flow(
            tile_type=mock_tile,
            io_pin_config=io_pin_config,
            mock_pdk_root=mock_pdk_root,
            base_config_path=base_config_file,
            override_config_path=override_config_file,
            OVERRIDE_ME="custom",
            CUSTOM_VAR="custom_value",
        )

        assert flow.config["BASE_VAR"] == "base_value"
        assert flow.config["OVERRIDE_VAR"] == "override_value"
        assert flow.config["OVERRIDE_ME"] == "custom"
        assert flow.config["CUSTOM_VAR"] == "custom_value"

    def test_opt_mode_string_conversion(
        self,
        mock_tile: MagicMock,
        io_pin_config: Path,
        mock_pdk_root: dict[str, Any],
    ) -> None:
        """Test that string FABULOUS_OPT_MODE is converted to OptMode enum."""
        flow: FABulousTileVerilogMacroFlow = self._create_flow(
            tile_type=mock_tile,
            io_pin_config=io_pin_config,
            mock_pdk_root=mock_pdk_root,
            FABULOUS_OPT_MODE="find_min_height",
        )

        assert flow.config["FABULOUS_OPT_MODE"] == OptMode.FIND_MIN_HEIGHT
        assert isinstance(flow.config["FABULOUS_OPT_MODE"], OptMode)

    def test_min_die_area_uses_io_pin_thickness_multipliers(
        self,
        mock_tile: MagicMock,
        io_pin_config: Path,
        mock_pdk_root: dict[str, Any],
    ) -> None:
        """Test IO pin thickness multipliers are forwarded to min die area calc."""
        self._create_flow(
            tile_type=mock_tile,
            io_pin_config=io_pin_config,
            mock_pdk_root=mock_pdk_root,
            IO_PIN_V_THICKNESS_MULT=Decimal("2.0"),
            IO_PIN_H_THICKNESS_MULT=Decimal("3.0"),
        )

        mock_tile.get_min_die_area.assert_called_once_with(
            x_pitch=Decimal("0.28"),
            y_pitch=Decimal("0.56"),
            x_pin_thickness_mult=Decimal("2.0"),
            y_pin_thickness_mult=Decimal("3.0"),
        )

    def test_init_ignores_invalid_pdk_pad_paths_for_tile_flow(
        self,
        mock_tile: MagicMock,
        io_pin_config: Path,
        mock_pdk_root: dict[str, Any],
    ) -> None:
        """Test tile flow is not blocked by stale PAD_* paths from PDK config."""
        mock_pdk_root["config_vars"]["PAD_GDS"] = ["/definitely/missing/pad.gds"]

        flow: FABulousTileVerilogMacroFlow = self._create_flow(
            tile_type=mock_tile,
            io_pin_config=io_pin_config,
            mock_pdk_root=mock_pdk_root,
            models_pack_path=Path("/fake/models/pack.v"),
        )

        assert flow.config["PAD_GDS"] == ["/definitely/missing/pad.gds"]

    def test_die_area_set_with_ignore_default(
        self,
        mock_tile: MagicMock,
        io_pin_config: Path,
        mock_pdk_root: dict[str, Any],
    ) -> None:
        """Test DIE_AREA is set when FABULOUS_IGNORE_DEFAULT_DIE_AREA is True."""
        flow: FABulousTileVerilogMacroFlow = self._create_flow(
            tile_type=mock_tile,
            io_pin_config=io_pin_config,
            mock_pdk_root=mock_pdk_root,
            FABULOUS_IGNORE_DEFAULT_DIE_AREA=True,
        )

        die_area: tuple[int, int, Decimal, Decimal] = flow.config["DIE_AREA"]
        # DIE_AREA is rounded to pitch multiples (0.28 for X, 0.56 for Y)
        # 100.0 / 0.28 = 357.14... -> 358 * 0.28 = 100.24
        # 100.0 / 0.56 = 178.57... -> 179 * 0.56 = 100.24
        assert die_area == (0, 0, Decimal("100.24"), Decimal("100.24"))

    def test_die_area_validation_too_small(
        self,
        mock_tile: MagicMock,
        io_pin_config: Path,
        mock_pdk_root: dict[str, Any],
    ) -> None:
        """Test that FlowException is raised when DIE_AREA is too small."""
        with pytest.raises(FlowException, match="DIE_AREA.*is smaller than"):
            self._create_flow(
                tile_type=mock_tile,
                io_pin_config=io_pin_config,
                mock_pdk_root=mock_pdk_root,
                DIE_AREA=(0, 0, Decimal("50.0"), Decimal("50.0")),
            )

    def test_die_area_validation_valid(
        self,
        mock_tile: MagicMock,
        io_pin_config: Path,
        mock_pdk_root: dict[str, Any],
    ) -> None:
        """Test that valid DIE_AREA is accepted."""
        flow: FABulousTileVerilogMacroFlow = self._create_flow(
            tile_type=mock_tile,
            io_pin_config=io_pin_config,
            mock_pdk_root=mock_pdk_root,
            DIE_AREA=(0, 0, Decimal("150.0"), Decimal("150.0")),
        )

        # DIE_AREA is rounded to pitch multiples (0.28 for X, 0.56 for Y)
        # 150.0 / 0.28 = 535.71... -> 536 * 0.28 = 150.08
        # 150.0 / 0.56 = 267.85... -> 268 * 0.56 = 150.08
        assert flow.config["DIE_AREA"] == (0, 0, Decimal("150.08"), Decimal("150.08"))

    def test_no_opt_mode_requires_die_area(
        self,
        mock_tile: MagicMock,
        io_pin_config: Path,
        mock_pdk_root: dict[str, Any],
    ) -> None:
        """Test that NO_OPT mode requires DIE_AREA to be set."""
        with pytest.raises(FlowException, match="Invalid DIE_AREA configuration"):
            self._create_flow(
                tile_type=mock_tile,
                io_pin_config=io_pin_config,
                opt_mode=OptMode.NO_OPT,
                mock_pdk_root=mock_pdk_root,
            )

    def test_no_opt_mode_with_die_area(
        self,
        mock_tile: MagicMock,
        io_pin_config: Path,
        mock_pdk_root: dict[str, Any],
    ) -> None:
        """Test that NO_OPT mode works when DIE_AREA is provided."""
        flow: FABulousTileVerilogMacroFlow = self._create_flow(
            tile_type=mock_tile,
            io_pin_config=io_pin_config,
            opt_mode=OptMode.NO_OPT,
            mock_pdk_root=mock_pdk_root,
            DIE_AREA=(0, 0, Decimal("200.0"), Decimal("200.0")),
        )

        # DIE_AREA is rounded to pitch multiples (0.28 for X, 0.56 for Y)
        # 200.0 / 0.28 = 714.28... -> 715 * 0.28 = 200.20
        # 200.0 / 0.56 = 357.14... -> 358 * 0.56 = 200.48
        assert flow.config["DIE_AREA"] == (0, 0, Decimal("200.20"), Decimal("200.48"))

    def test_routing_obstructions_generated(
        self,
        mock_tile: MagicMock,
        io_pin_config: Path,
        mock_pdk_root: dict[str, Any],
    ) -> None:
        """Test that routing obstructions are generated when not provided."""
        flow: FABulousTileVerilogMacroFlow = self._create_flow(
            tile_type=mock_tile,
            io_pin_config=io_pin_config,
            mock_pdk_root=mock_pdk_root,
        )

        # Routing obstructions should be generated (a list)
        assert flow.config["ROUTING_OBSTRUCTIONS"] is not None
        assert isinstance(flow.config["ROUTING_OBSTRUCTIONS"], list)

    def test_routing_obstructions_not_generated_when_false(
        self,
        mock_tile: MagicMock,
        io_pin_config: Path,
        mock_pdk_root: dict[str, Any],
    ) -> None:
        """Test that routing obstructions are not generated when explicitly False."""
        flow: FABulousTileVerilogMacroFlow = self._create_flow(
            tile_type=mock_tile,
            io_pin_config=io_pin_config,
            mock_pdk_root=mock_pdk_root,
            ROUTING_OBSTRUCTIONS=False,
        )

        assert flow.config["ROUTING_OBSTRUCTIONS"] is False

    def test_routing_obstructions_custom_value(
        self,
        mock_tile: MagicMock,
        io_pin_config: Path,
        mock_pdk_root: dict[str, Any],
    ) -> None:
        """Test that custom routing obstructions value is preserved."""
        custom_obstructions: list[tuple[str, int, int, int, int]] = [
            ("M1", 0, 0, 10, 10)
        ]
        flow: FABulousTileVerilogMacroFlow = self._create_flow(
            tile_type=mock_tile,
            io_pin_config=io_pin_config,
            mock_pdk_root=mock_pdk_root,
            ROUTING_OBSTRUCTIONS=custom_obstructions,
        )

        assert flow.config["ROUTING_OBSTRUCTIONS"] == custom_obstructions

    def test_design_dir_default(
        self,
        mock_tile: MagicMock,
        io_pin_config: Path,
        mock_pdk_root: dict[str, Any],
    ) -> None:
        """Test that design_dir defaults to tile macro directory."""
        _flow: FABulousTileVerilogMacroFlow = self._create_flow(
            tile_type=mock_tile,
            io_pin_config=io_pin_config,
            mock_pdk_root=mock_pdk_root,
        )

        expected_dir: Path = mock_tile.tileDir.parent / "macro" / "find_min_width"
        assert expected_dir.exists()

    def test_design_dir_custom(
        self,
        mock_tile: MagicMock,
        io_pin_config: Path,
        mock_pdk_root: dict[str, Any],
        tmp_path: Path,
    ) -> None:
        """Test that custom design_dir is used when provided."""
        custom_dir: Path = tmp_path / "custom_design_dir"
        custom_dir.mkdir()

        flow: FABulousTileVerilogMacroFlow = self._create_flow(
            tile_type=mock_tile,
            io_pin_config=io_pin_config,
            mock_pdk_root=mock_pdk_root,
            design_dir=custom_dir,
        )

        assert flow.design_dir == str(custom_dir)

    def test_verilog_files_collected(
        self,
        mock_tile: MagicMock,
        io_pin_config: Path,
        mock_pdk_root: dict[str, Any],
    ) -> None:
        """Test that VERILOG_FILES are collected from tile directory."""
        flow: FABulousTileVerilogMacroFlow = self._create_flow(
            tile_type=mock_tile,
            io_pin_config=io_pin_config,
            mock_pdk_root=mock_pdk_root,
            models_pack_path=Path("/fake/models/pack.v"),
        )

        verilog_files: list[str] = flow.config["VERILOG_FILES"]
        assert isinstance(verilog_files, list)
        assert len(verilog_files) > 0
        assert all(f.endswith(".v") for f in verilog_files)

    def test_nonexistent_config_files_ignored(
        self,
        mock_tile: MagicMock,
        io_pin_config: Path,
        mock_pdk_root: dict[str, Any],
        tmp_path: Path,
    ) -> None:
        """Test that nonexistent config files don't cause errors."""
        nonexistent: Path = tmp_path / "nonexistent.yaml"

        flow: FABulousTileVerilogMacroFlow = self._create_flow(
            tile_type=mock_tile,
            io_pin_config=io_pin_config,
            mock_pdk_root=mock_pdk_root,
            base_config_path=nonexistent,
            override_config_path=nonexistent,
        )

        assert flow.config["DESIGN_NAME"] == "TestTile"

    def test_none_cast_to_no_opt(
        self,
        mock_tile: MagicMock,
        io_pin_config: Path,
        mock_pdk_root: dict[str, Any],
    ) -> None:
        """Test none handling for opt_mode results in NO_OPT."""

        flow: FABulousTileVerilogMacroFlow = self._create_flow(
            tile_type=mock_tile,
            io_pin_config=io_pin_config,
            mock_pdk_root=mock_pdk_root,
            opt_mode=None,
            DIE_AREA=(0, 0, Decimal("200.0"), Decimal("200.0")),
        )

        assert flow.config["FABULOUS_OPT_MODE"] == OptMode.NO_OPT

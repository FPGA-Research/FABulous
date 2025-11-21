"""Tests for FABulousTileVerilogMarcoFlow - Tile macro generation flow.

Tests focus on:
- Flow configuration and initialization
- OptMode handling
- DIE_AREA configuration
- Routing obstruction generation
"""

from decimal import Decimal
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from FABulous.fabric_generator.gds_generator.steps.tile_optimisation import OptMode


class TestTileFlowOptModes:
    """Tests for optimization mode handling in tile flows."""

    def test_opt_mode_values(self):
        """Test that OptMode enum has expected values."""
        assert OptMode.NO_OPT.value == "no_opt"
        assert OptMode.BALANCE.value == "balance"
        assert OptMode.FIND_MIN_WIDTH.value == "find_min_width"
        assert OptMode.FIND_MIN_HEIGHT.value == "find_min_height"

    def test_opt_mode_from_string(self):
        """Test creating OptMode from string values."""
        assert OptMode("no_opt") == OptMode.NO_OPT
        assert OptMode("balance") == OptMode.BALANCE
        assert OptMode("find_min_width") == OptMode.FIND_MIN_WIDTH
        assert OptMode("find_min_height") == OptMode.FIND_MIN_HEIGHT

    def test_invalid_opt_mode_raises_error(self):
        """Test that invalid opt mode string raises ValueError."""
        with pytest.raises(ValueError):
            OptMode("invalid_mode")


class TestTileFlowConfiguration:
    """Tests for tile flow configuration behavior."""

    def test_flow_uses_correct_steps_for_verilog(self):
        """Test that Verilog flow includes TileOptimisation step."""
        from FABulous.fabric_generator.gds_generator.flows.tile_macro_flow import (
            FABulousTileVerilogMarcoFlow,
        )
        from FABulous.fabric_generator.gds_generator.steps.tile_optimisation import (
            TileOptimisation,
        )

        assert TileOptimisation in FABulousTileVerilogMarcoFlow.Steps

    def test_flow_has_config_vars(self):
        """Test that tile flow has required config variables."""
        from FABulous.fabric_generator.gds_generator.flows.tile_macro_flow import (
            FABulousTileVerilogMarcoFlow,
        )

        config_var_names = [var.name for var in FABulousTileVerilogMarcoFlow.config_vars]
        assert "FABULOUS_IGNORE_DEFAULT_DIE_AREA" in config_var_names

    def test_vhdl_flow_has_correct_steps(self):
        """Test that VHDL flow includes prep and physical steps."""
        from FABulous.fabric_generator.gds_generator.flows.tile_macro_flow import (
            FABulousTileVHDLMarcoFlowClassic,
        )
        from FABulous.fabric_generator.gds_generator.flows.flow_define import (
            prep_steps,
            physical_steps,
        )

        # Check some key steps are included
        for step in prep_steps[:3]:  # First few prep steps
            assert step in FABulousTileVHDLMarcoFlowClassic.Steps


class TestTileFlowSubstitutions:
    """Tests for step substitutions in tile flows."""

    def test_io_placement_substitution(self):
        """Test that CustomIOPlacement is substituted with FABulous version."""
        from FABulous.fabric_generator.gds_generator.flows.tile_macro_flow import subs
        from FABulous.fabric_generator.gds_generator.steps.tile_IO_placement import (
            FABulousTileIOPlacement,
        )

        assert subs["Odb.CustomIOPlacement"] == FABulousTileIOPlacement

    def test_pdn_substitution(self):
        """Test that GeneratePDN is substituted with CustomGeneratePDN."""
        from FABulous.fabric_generator.gds_generator.flows.tile_macro_flow import subs
        from FABulous.fabric_generator.gds_generator.steps.custom_pdn import (
            CustomGeneratePDN,
        )

        assert subs["OpenROAD.GeneratePDN"] == CustomGeneratePDN

    def test_sta_steps_disabled(self):
        """Test that STA steps are disabled (set to None)."""
        from FABulous.fabric_generator.gds_generator.flows.tile_macro_flow import subs

        assert subs["OpenROAD.STAPrePNR*"] is None
        assert subs["OpenROAD.STAMidPNR*"] is None
        assert subs["OpenROAD.STAPostPNR*"] is None

    def test_resize_steps_disabled(self):
        """Test that resize steps are disabled."""
        from FABulous.fabric_generator.gds_generator.flows.tile_macro_flow import subs

        assert subs["OpenROAD.Resize*"] is None
        assert subs["OpenROAD.RepairDesign*"] is None

    def test_add_buffers_added_after_global_placement(self):
        """Test that AddBuffers is added after GlobalPlacement."""
        from FABulous.fabric_generator.gds_generator.flows.tile_macro_flow import subs
        from FABulous.fabric_generator.gds_generator.steps.add_buffer import AddBuffers

        assert subs["+OpenROAD.GlobalPlacement"] == AddBuffers

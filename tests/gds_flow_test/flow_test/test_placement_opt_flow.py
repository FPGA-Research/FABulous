"""Tests for the flow that searches a tile for its own inputs.

The flow is the tile macro flow with a shorter step list and two extra config
entries, so what is tested here is the step list, the entries and the refusal
of a super tile.
"""

from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

import pytest
import yaml
from librelane.flows.flow import FlowException

from fabulous.fabric_generator.gds_generator.flows.placement_opt_flow import (
    FABulousTileVerilogPlacementOptFlow,
    config_mem_csv_for,
    write_pin_pairs_for,
)
from fabulous.fabric_generator.gds_generator.opt.placement_opt import (
    PlacementDrivenTileOptimisation,
)
from fabulous.fabric_generator.gds_generator.opt.tile_area_opt import OptMode
from fabulous.fabric_generator.gds_generator.opt.variables import (
    CONFIG_MEM_CSV_VARIABLE,
    TILE_INTERFACE_PAIRS_VARIABLE,
)


class TestConfigMemCsvFor:
    @pytest.mark.parametrize(
        ("config_bits", "named"),
        [(16, True), (0, False)],
        ids=["with config bits", "without config bits"],
    )
    def test_only_a_tile_with_bits_has_a_mapping(
        self, mock_tile: MagicMock, config_bits: int, named: bool
    ) -> None:
        mock_tile.globalConfigBits = config_bits
        mock_tile.config_mem_path = mock_tile.tileDir.parent / "TestTile_ConfigMem.csv"

        result = config_mem_csv_for(mock_tile)

        assert result == (str(mock_tile.config_mem_path) if named else None)


class TestWritePinPairsFor:
    def test_the_pairs_land_next_to_the_run(
        self, mock_tile: MagicMock, tmp_path: Path
    ) -> None:
        mock_tile.interface.pairs = []

        path = Path(write_pin_pairs_for(mock_tile, tmp_path))

        assert path == tmp_path / "TestTile_pin_pairs.yaml"
        assert yaml.safe_load(path.read_text()) == []


@pytest.mark.usefixtures("mock_config_load")
class TestFABulousTileVerilogPlacementOptFlow:
    def _create_flow(
        self,
        *,
        tile_type: MagicMock,
        io_pin_config: Path,
        mock_pdk_root: dict[str, Any],
        **kwargs: dict,
    ) -> FABulousTileVerilogPlacementOptFlow:
        flow_kwargs: dict[str, Any] = {
            "tile_type": tile_type,
            "io_pin_config": io_pin_config,
            "opt_mode": OptMode.NO_OPT,
            "pdk": mock_pdk_root["pdk"],
            "pdk_root": mock_pdk_root["pdk_root"],
            "models_pack_path": Path("/fake/models/pack"),
            "DIE_AREA": (0, 0, 200, 200),
        }
        flow_kwargs.update(kwargs)
        return FABulousTileVerilogPlacementOptFlow(**flow_kwargs)

    def test_the_flow_ends_at_the_optimisation(self) -> None:
        steps = FABulousTileVerilogPlacementOptFlow.Steps

        assert steps[-1] is PlacementDrivenTileOptimisation
        assert not [step for step in steps if "Magic" in step.id or "DRC" in step.id]

    def test_the_tile_inputs_reach_the_proposal_steps(
        self,
        mock_tile: MagicMock,
        io_pin_config: Path,
        mock_pdk_root: dict[str, Any],
    ) -> None:
        mock_tile.globalConfigBits = 16
        mock_tile.config_mem_path = mock_tile.tileDir.parent / "TestTile_ConfigMem.csv"
        mock_tile.interface.pairs = []

        flow = self._create_flow(
            tile_type=mock_tile,
            io_pin_config=io_pin_config,
            mock_pdk_root=mock_pdk_root,
        )

        assert flow.config[CONFIG_MEM_CSV_VARIABLE.name] == str(
            mock_tile.config_mem_path
        )
        assert str(flow.config[TILE_INTERFACE_PAIRS_VARIABLE.name]).endswith(
            "TestTile_pin_pairs.yaml"
        )

    def test_a_super_tile_is_refused(
        self,
        mock_supertile: MagicMock,
        io_pin_config: Path,
        mock_pdk_root: dict[str, Any],
    ) -> None:
        with pytest.raises(FlowException, match="super tile"):
            self._create_flow(
                tile_type=mock_supertile,
                io_pin_config=io_pin_config,
                mock_pdk_root=mock_pdk_root,
            )

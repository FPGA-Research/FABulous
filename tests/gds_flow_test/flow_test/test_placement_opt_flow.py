"""Tests for the flow that searches a tile for its own inputs.

The flow is the tile macro flow with a shorter step list and two extra config
entries, so what is tested here is the step list, the entries and what it
refuses.
"""

from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

import pytest
import yaml
from librelane.flows.flow import FlowException

from fabulous.fabric_generator.gds_generator.flows.placement_opt_flow import (
    FABulousTileVerilogPlacementOptFlow,
)
from fabulous.fabric_generator.gds_generator.opt.placement_opt import (
    PlacementDrivenTileOptimisation,
)
from fabulous.fabric_generator.gds_generator.opt.variables import (
    CONFIG_MEM_CSV_VARIABLE,
    TILE_INTERFACE_PAIRS_VARIABLE,
)


@pytest.mark.usefixtures("mock_config_load")
class TestFABulousTileVerilogPlacementOptFlow:
    def _create_flow(
        self,
        *,
        tile_type: MagicMock,
        io_pin_config: Path,
        mock_pdk_root: dict[str, Any],
        tmp_path: Path,
        **kwargs: dict,
    ) -> FABulousTileVerilogPlacementOptFlow:
        flow_kwargs: dict[str, Any] = {
            "tile_type": tile_type,
            "io_pin_config": io_pin_config,
            "pdk": mock_pdk_root["pdk"],
            "pdk_root": mock_pdk_root["pdk_root"],
            "models_pack_path": Path("/fake/models/pack"),
            "design_dir": tmp_path,
            "DIE_AREA": (0, 0, 200, 200),
        }
        flow_kwargs.update(kwargs)
        return FABulousTileVerilogPlacementOptFlow(**flow_kwargs)

    def test_the_flow_ends_at_the_optimisation(self) -> None:
        steps = FABulousTileVerilogPlacementOptFlow.Steps

        assert steps[-1] is PlacementDrivenTileOptimisation
        assert not [step for step in steps if "Magic" in step.id or "DRC" in step.id]

    @pytest.mark.parametrize(
        ("config_bits", "mapped"),
        [(16, True), (0, False)],
        ids=["with config bits", "without config bits"],
    )
    def test_the_tile_inputs_reach_the_proposal_steps(
        self,
        mock_tile: MagicMock,
        io_pin_config: Path,
        mock_pdk_root: dict[str, Any],
        tmp_path: Path,
        config_bits: int,
        mapped: bool,
    ) -> None:
        mock_tile.total_config_bits = config_bits
        mock_tile.pairs = []

        flow = self._create_flow(
            tile_type=mock_tile,
            io_pin_config=io_pin_config,
            mock_pdk_root=mock_pdk_root,
            tmp_path=tmp_path,
        )

        csv = flow.config[CONFIG_MEM_CSV_VARIABLE.name]
        assert (csv is not None) is mapped
        if mapped:
            assert str(csv).endswith("TestTile_ConfigMem.csv")
        pairs = Path(str(flow.config[TILE_INTERFACE_PAIRS_VARIABLE.name]))
        assert pairs == tmp_path / "TestTile_pin_pairs.yaml"
        assert yaml.safe_load(pairs.read_text()) == []

    def test_a_composite_tile_is_refused(
        self,
        mock_supertile: MagicMock,
        io_pin_config: Path,
        mock_pdk_root: dict[str, Any],
        tmp_path: Path,
    ) -> None:
        with pytest.raises(FlowException, match="composite tile"):
            self._create_flow(
                tile_type=mock_supertile,
                io_pin_config=io_pin_config,
                mock_pdk_root=mock_pdk_root,
                tmp_path=tmp_path,
            )

    def test_a_run_without_its_own_directory_is_refused(
        self,
        mock_tile: MagicMock,
        io_pin_config: Path,
        mock_pdk_root: dict[str, Any],
        tmp_path: Path,
    ) -> None:
        mock_tile.pairs = []
        with pytest.raises(FlowException, match="design directory of its own"):
            self._create_flow(
                tile_type=mock_tile,
                io_pin_config=io_pin_config,
                mock_pdk_root=mock_pdk_root,
                tmp_path=tmp_path,
                design_dir=None,
            )

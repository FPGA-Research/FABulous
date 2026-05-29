"""PnR pass wrapper for FABulous tile building."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from fabulous.fabric_cad.fabxplore.modules.tile_builder.core.builder import TileBuilder
from fabulous.fabric_cad.fabxplore.modules.tile_builder.core.models import (
    BaselineRouting,
    TileBel,
    TileBuilderOptions,
    TileBuilderResult,
)
from fabulous.fabric_cad.fabxplore.pnr.pnr_pass import PnRPass

if TYPE_CHECKING:
    from pathlib import Path

    from fabulous.fabric_cad.fabxplore.pnr.pnr_bridge import PnRBridge


@dataclass
class TileBuilderPass(PnRPass):
    """Build a FABulous tile package from BEL RTL.

    Attributes
    ----------
    tile_name : str
        Name of the FABulous tile to generate.
    bels : list[TileBel | dict[str, object]]
        BEL source files and prefixes to instantiate.
    routing : BaselineRouting | dict[str, object] | None
        Baseline routing options. ``None`` selects defaults.
    tile_dir : Path | None
        Optional tile directory. ``None`` selects ``<project>/Tile/<tile_name>``.
    config_bit_capacity_override : int | None
        Optional total config-bit capacity. ``None`` uses the loaded FABulous fabric.
    register_in_fabric : bool
        Whether ``fabric.csv`` should receive a ``Tile`` entry for the generated tile.
    track_progress : bool
        Whether progress should be logged.
    progress_chunk_size : int
        Number of BEL instances between progress messages.
    """

    tile_name: str
    bels: list[TileBel | dict[str, object]]
    routing: BaselineRouting | dict[str, object] | None = None
    tile_dir: Path | None = None
    config_bit_capacity_override: int | None = None
    register_in_fabric: bool = True
    track_progress: bool = True
    progress_chunk_size: int = 25

    _result: TileBuilderResult | None = None

    def run_on(self, fpga_model: PnRBridge) -> None:
        """Run the tile builder on the active FABulous project.

        Parameters
        ----------
        fpga_model : PnRBridge
            Combined packed design, FABulous project API, and routing graph.
        """
        options = TileBuilderOptions(
            tile_name=self.tile_name,
            bels=[
                bel if isinstance(bel, TileBel) else TileBel(**bel) for bel in self.bels
            ],
            routing=self.routing
            if isinstance(self.routing, BaselineRouting)
            else BaselineRouting(**(self.routing or {})),
            tile_dir=self.tile_dir,
            config_bit_capacity_override=self.config_bit_capacity_override,
            register_in_fabric=self.register_in_fabric,
            track_progress=self.track_progress,
            progress_chunk_size=self.progress_chunk_size,
        )
        self._result = TileBuilder(options).build(fpga_model)

    @property
    def report_summary(self) -> str:
        """Return the latest report summary.

        Returns
        -------
        str
            Report text, or a placeholder if the pass has not run.
        """
        return self._result.report_summary if self._result else "No result available."

    @property
    def result_data(self) -> TileBuilderResult | None:
        """Return the latest structured result.

        Returns
        -------
        TileBuilderResult | None
            Latest result if available.
        """
        return self._result

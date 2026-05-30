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
    use_fabulous_auto : bool
        If ``True``, emit ``MATRIX,GENERATE`` and let FABulous create the list.
    base_csv_includes : list[str] | None
        Tile CSV include paths for shared base wire descriptions.
        ``None`` selects ``BaselineRouting`` defaults.
    base_list_includes : list[str] | None
        Switch-matrix list include paths for shared base routing lists.
        ``None`` selects ``BaselineRouting`` defaults.
    input_fanin : int
        Preferred number of routing sources for each ordinary BEL input.
    output_fanin : int
        Preferred mux size for routing destinations driven by BEL outputs.
    min_input_fanin : int
        Lowest BEL-input fanin allowed when fitting the config-bit budget.
    min_output_fanin : int
        Lowest BEL-output routing fanin allowed when fitting the config-bit budget.
    config_bit_margin : int
        Number of fabric config bits to leave unused.
    derive_sources_from_base : bool
        Whether ordinary BEL inputs may use discovered base input ports.
    cover_unconnected_outputs : bool
        Whether to add coverage for base output rows not covered by included lists.
    emit_constants_if_missing : bool
        Whether to add local GND/VCC jump sources when the base does not define them.
    allow_bel_output_feedback_sources : bool
        Whether ordinary BEL input muxes may also select ordinary BEL outputs.
    tile_dir : Path | None
        Optional tile directory. ``None`` selects ``<project>/Tile/<tile_name>``.
    config_bit_capacity_override : int | None
        Optional total config-bit capacity. ``None`` uses the loaded FABulous fabric.
    register_in_fabric : bool
        Whether ``fabric.csv`` should receive a ``Tile`` entry for the generated tile.
    register_tile_in_fpga_model : bool
        Whether the active PnR bridge should reload project and graph after a
        successful build.
    track_progress : bool
        Whether progress should be logged.
    progress_chunk_size : int
        Number of BEL instances between progress messages.
    """

    tile_name: str
    bels: list[TileBel | dict[str, object]]
    use_fabulous_auto: bool = False
    base_csv_includes: list[str] | None = None
    base_list_includes: list[str] | None = None
    input_fanin: int = 4
    output_fanin: int = 5
    min_input_fanin: int = 1
    min_output_fanin: int = 1
    config_bit_margin: int = 0
    derive_sources_from_base: bool = True
    cover_unconnected_outputs: bool = True
    emit_constants_if_missing: bool = True
    allow_bel_output_feedback_sources: bool = True
    tile_dir: Path | None = None
    config_bit_capacity_override: int | None = None
    register_in_fabric: bool = True
    register_tile_in_fpga_model: bool = True
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
        routing_defaults = BaselineRouting()

        options = TileBuilderOptions(
            tile_name=self.tile_name,
            bels=[
                bel if isinstance(bel, TileBel) else TileBel(**bel) for bel in self.bels
            ],
            routing=BaselineRouting(
                use_fabulous_auto=self.use_fabulous_auto,
                base_csv_includes=self.base_csv_includes
                if self.base_csv_includes is not None
                else routing_defaults.base_csv_includes,
                base_list_includes=self.base_list_includes
                if self.base_list_includes is not None
                else routing_defaults.base_list_includes,
                input_fanin=self.input_fanin,
                output_fanin=self.output_fanin,
                min_input_fanin=self.min_input_fanin,
                min_output_fanin=self.min_output_fanin,
                config_bit_margin=self.config_bit_margin,
                derive_sources_from_base=self.derive_sources_from_base,
                cover_unconnected_outputs=self.cover_unconnected_outputs,
                emit_constants_if_missing=self.emit_constants_if_missing,
                allow_bel_output_feedback_sources=self.allow_bel_output_feedback_sources,
            ),
            tile_dir=self.tile_dir,
            config_bit_capacity_override=self.config_bit_capacity_override,
            register_in_fabric=self.register_in_fabric,
            register_tile_in_fpga_model=self.register_tile_in_fpga_model,
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

"""PnR pass wrapper for graph-only switch-matrix pattern generation."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from fabulous.fabric_cad.fabxplore.modules.routing_patterns import (
    RoutingPipPattern,
    SwitchMatrixPattern,
    SwitchMatrixPatternOptions,
    SwitchMatrixPatternResult,
)
from fabulous.fabric_cad.fabxplore.pnr.pnr_pass import PnRPass

if TYPE_CHECKING:
    from fabulous.fabric_cad.fabxplore.pnr.pnr_bridge import PnRBridge


@dataclass
class SwitchMatrixPatternPass(PnRPass):
    """Apply graph-only switch-matrix patterns to one FABulous tile type.

    Attributes
    ----------
    tile_name : str
        FABulous tile type to modify in the graph.
    input_fanin : int
        Number of sources generated for each BEL input row.
    include_bel_output_sources : bool
        Whether BEL outputs are eligible as local source columns.
    include_constant_sources : bool
        Whether constant wires are eligible as source columns.
    output_fanin : int
        Number of sources generated for each uncovered routing output row.
    cover_unconnected_matrix_rows : bool
        Whether uncovered routing output rows should receive sources.
    routing_pip_pattern : RoutingPipPattern | str
        Routing-resource pattern name.
    routing_pip_fs : int
        Number of routing-resource sources per generated route-through row.
    generate_straight_routing_pips : bool
        Whether same-direction route-through pairs are generated.
    generate_turn_routing_pips : bool
        Whether turn route-through pairs are generated.
    hierarchy_enabled : bool
        Whether BEL input access should be built through generated JUMP levels.
    hierarchy_levels : list[int]
        Fanins for generated JUMP hierarchy levels.
    hierarchy_jump_prefix : str
        Prefix for generated hierarchy JUMP resources.
    hierarchy_replace_direct_input_pips : bool
        Whether hierarchy PIPs replace direct BEL-input PIPs.
    replace_existing_matrix : bool
        Whether generated pairs replace the tile matrix instead of adding to it.
    delay : float
        Delay assigned to generated active matrix resources.
    track_progress : bool
        Whether progress should be logged.
    progress_chunk_size : int
        Number of generated rows between progress messages.
    """

    tile_name: str
    input_fanin: int = 6
    include_bel_output_sources: bool = True
    include_constant_sources: bool = True
    output_fanin: int = 3
    cover_unconnected_matrix_rows: bool = True
    routing_pip_pattern: RoutingPipPattern | str = RoutingPipPattern.WILTON
    routing_pip_fs: int = 4
    generate_straight_routing_pips: bool = True
    generate_turn_routing_pips: bool = True
    hierarchy_enabled: bool = False
    hierarchy_levels: list[int] = field(default_factory=lambda: [2, 2])
    hierarchy_jump_prefix: str = "J_LOCAL"
    hierarchy_replace_direct_input_pips: bool = True
    replace_existing_matrix: bool = False
    delay: float = 8.0
    track_progress: bool = True
    progress_chunk_size: int = 100

    _result: SwitchMatrixPatternResult | None = None

    def run_on(self, fpga_model: PnRBridge) -> None:
        """Run the pattern pass on the active PnR bridge.

        Parameters
        ----------
        fpga_model : PnRBridge
            Combined packed design, FABulous project API, and routing graph.
        """
        options = SwitchMatrixPatternOptions(
            tile_name=self.tile_name,
            input_fanin=self.input_fanin,
            include_bel_output_sources=self.include_bel_output_sources,
            include_constant_sources=self.include_constant_sources,
            output_fanin=self.output_fanin,
            cover_unconnected_matrix_rows=self.cover_unconnected_matrix_rows,
            routing_pip_pattern=self.routing_pip_pattern,
            routing_pip_fs=self.routing_pip_fs,
            generate_straight_routing_pips=self.generate_straight_routing_pips,
            generate_turn_routing_pips=self.generate_turn_routing_pips,
            hierarchy_enabled=self.hierarchy_enabled,
            hierarchy_levels=self.hierarchy_levels,
            hierarchy_jump_prefix=self.hierarchy_jump_prefix,
            hierarchy_replace_direct_input_pips=(
                self.hierarchy_replace_direct_input_pips
            ),
            replace_existing_matrix=self.replace_existing_matrix,
            delay=self.delay,
            track_progress=self.track_progress,
            progress_chunk_size=self.progress_chunk_size,
        )
        self._result = SwitchMatrixPattern(options).run(fpga_model)

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
    def result_data(self) -> SwitchMatrixPatternResult | None:
        """Return the latest structured result.

        Returns
        -------
        SwitchMatrixPatternResult | None
            Latest result if available.
        """
        return self._result

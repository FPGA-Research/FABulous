"""Dispatch parameterized switch-matrix patterns through the FPGA model."""

from __future__ import annotations

from typing import TYPE_CHECKING

from fabulous.fabric_cad.fabxplore.modules.routing_patterns.core.models import (
    SwitchMatrixPatternOptions,
    SwitchMatrixPatternResult,
    SwitchMatrixPatternStats,
)
from fabulous.fabric_cad.fabxplore.modules.routing_patterns.core.process_tracker import (  # noqa: E501
    SwitchMatrixPatternProcessTracker,
)
from fabulous.fabric_cad.fabxplore.modules.routing_patterns.core.report import (
    render_switch_matrix_pattern_report,
)
from fabulous.fabric_cad.fabxplore.modules.routing_patterns.patterns import (
    apply_registered_pattern,
)
from fabulous.fabric_cad.fabxplore.modules.routing_patterns.patterns.common import (
    active_pairs,
)

if TYPE_CHECKING:
    from fabulous.fabric_cad.fabxplore.pnr.pnr_bridge import PnRBridge


class SwitchMatrixPattern:
    """Apply graph-only switch-matrix patterns to one FABulous tile type.

    Parameters
    ----------
    options : SwitchMatrixPatternOptions
        Normalized pattern options.
    """

    def __init__(self, options: SwitchMatrixPatternOptions) -> None:
        self.options = options

    def run(self, fpga_model: PnRBridge) -> SwitchMatrixPatternResult:
        """Run the selected switch-matrix pattern on the FPGA model.

        Parameters
        ----------
        fpga_model : PnRBridge
            Combined packed design, FABulous API, and editable routing graph.

        Returns
        -------
        SwitchMatrixPatternResult
            Structured result and report.
        """
        tracker = SwitchMatrixPatternProcessTracker(
            enabled=self.options.track_progress,
            chunk_size=self.options.progress_chunk_size,
        )
        tracker.start(self.options.tile_name)

        before_matrix = fpga_model.switch_matrix(self.options.tile_name)
        before_config = fpga_model.get_config_bits(self.options.tile_name)
        before_active_pips = len(active_pairs(before_matrix))

        apply_result = apply_registered_pattern(fpga_model, self.options)
        tracker.generated(
            "BEL input access PIPs",
            apply_result.generated_bel_input_pips,
        )
        tracker.generated(
            "hierarchy stage PIPs",
            apply_result.generated_hierarchy_pips,
        )
        tracker.generated(
            "output-row coverage PIPs",
            apply_result.generated_output_coverage_pips,
        )
        tracker.generated(
            "routing-resource pattern PIPs",
            apply_result.generated_routing_pips,
        )
        tracker.record_pairs(apply_result.applied_pips)

        after_matrix = fpga_model.switch_matrix(self.options.tile_name)
        after_config = fpga_model.get_config_bits(self.options.tile_name)
        stats = SwitchMatrixPatternStats(
            rows_before=len(before_matrix.rows),
            rows_after=len(after_matrix.rows),
            columns_before=len(before_matrix.columns),
            columns_after=len(after_matrix.columns),
            active_pips_before=before_active_pips,
            active_pips_after=len(active_pairs(after_matrix)),
            generated_bel_input_pips=apply_result.generated_bel_input_pips,
            generated_output_coverage_pips=(
                apply_result.generated_output_coverage_pips
            ),
            generated_routing_pips=apply_result.generated_routing_pips,
            generated_hierarchy_pips=apply_result.generated_hierarchy_pips,
            added_jump_wires=apply_result.added_jump_wires,
            applied_pips=apply_result.applied_pips,
            compatible_routing_groups=apply_result.compatible_routing_groups,
            matrix_config_bits_before=before_config.matrix_config_bits,
            matrix_config_bits_after=after_config.matrix_config_bits,
            total_config_bits_after=after_config.total_config_bits,
        )

        result = SwitchMatrixPatternResult(
            options=self.options,
            tile_name=self.options.tile_name,
            stats=stats,
            warnings=apply_result.warnings,
        )
        result = result.model_copy(
            update={"report_summary": render_switch_matrix_pattern_report(result)}
        )
        tracker.finish(self.options.tile_name, stats.applied_pips)
        return result

"""Apply a full switch-matrix pattern."""

from __future__ import annotations

from typing import TYPE_CHECKING

from fabulous.fabric_cad.fabxplore.modules.routing_patterns.core.models import (
    SwitchMatrixPatternApplyResult,
    SwitchMatrixPatternImplementation,
    SwitchMatrixPatternOptions,
)

if TYPE_CHECKING:
    from fabulous.fabric_cad.fabxplore.pnr.pnr_bridge import PnRBridge


class FullRoutingPattern(SwitchMatrixPatternImplementation):
    """Enable every cell in the current switch-matrix row/column domain."""

    def apply(
        self,
        fpga_model: PnRBridge,
        options: SwitchMatrixPatternOptions,
    ) -> SwitchMatrixPatternApplyResult:
        """Apply the full switch-matrix pattern.

        Parameters
        ----------
        fpga_model : PnRBridge
            FPGA model exposing the FabGraph API.
        options : SwitchMatrixPatternOptions
            Normalized pattern options.

        Returns
        -------
        SwitchMatrixPatternApplyResult
            Applied edit counts and warnings.
        """
        switch_matrix = fpga_model.switch_matrix(options.tile_name)
        rows = list(switch_matrix.rows)
        columns = list(switch_matrix.columns)
        warnings: list[str] = []
        if not rows or not columns:
            warnings.append(
                "Full switch-matrix pattern requested, but the current matrix "
                "has no rows or columns."
            )
            return SwitchMatrixPatternApplyResult(warnings=tuple(warnings))

        matrix = [[options.delay for _column in columns] for _row in rows]
        if options.replace_existing_matrix:
            applied_pips = len(rows) * len(columns)
            fpga_model.set_switch_matrix(options.tile_name, columns, rows, matrix)
        else:
            entries: list[tuple[str, str, float]] = []
            for row_index, row in enumerate(rows):
                for column_index, column in enumerate(columns):
                    if switch_matrix.matrix[row_index][column_index] > 0:
                        continue
                    entries.append((row, column, options.delay))
            applied_pips = len(entries)
            fpga_model.add_matrix_rows(
                options.tile_name,
                entries,
                overwrite=False,
            )

        return SwitchMatrixPatternApplyResult(
            generated_routing_pips=len(rows) * len(columns),
            applied_pips=applied_pips,
            compatible_routing_groups=len(rows),
            warnings=tuple(warnings),
        )

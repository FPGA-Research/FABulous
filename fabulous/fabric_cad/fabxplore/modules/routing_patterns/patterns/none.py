"""Apply the no-op routing-resource pattern."""

from __future__ import annotations

from typing import TYPE_CHECKING

from fabulous.fabric_cad.fabxplore.modules.routing_patterns.core.models import (
    SwitchMatrixPatternApplyResult,
    SwitchMatrixPatternImplementation,
    SwitchMatrixPatternOptions,
)
from fabulous.fabric_cad.fabxplore.modules.routing_patterns.patterns.common import (
    apply_pattern_pairs,
    routing_track_groups,
)

if TYPE_CHECKING:
    from fabulous.fabric_cad.fabxplore.pnr.pnr_bridge import PnRBridge


class NoneRoutingPattern(SwitchMatrixPatternImplementation):
    """Apply only common BEL and output-row edits without route-through PIPs."""

    def apply(
        self,
        fpga_model: PnRBridge,
        options: SwitchMatrixPatternOptions,
    ) -> SwitchMatrixPatternApplyResult:
        """Apply the no-op routing-resource pattern.

        Parameters
        ----------
        fpga_model : PnRBridge
            FPGA model exposing the FabGraph API.
        options : SwitchMatrixPatternOptions
            Normalized pattern options.

        Returns
        -------
        SwitchMatrixPatternApplyResult
            Applied common edit counts.
        """
        groups = routing_track_groups(fpga_model, options.tile_name)
        return apply_pattern_pairs(
            fpga_model,
            options,
            groups=groups,
            routing_pairs=[],
            compatible_routing_groups=0,
        )

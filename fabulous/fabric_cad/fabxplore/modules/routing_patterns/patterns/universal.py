"""Apply universal-style routing-resource route-through PIPs."""

from __future__ import annotations

from typing import TYPE_CHECKING

from fabulous.fabric_cad.fabxplore.modules.routing_patterns.core.models import (
    RoutingPipPattern,
    SwitchMatrixPatternApplyResult,
    SwitchMatrixPatternImplementation,
    SwitchMatrixPatternOptions,
)
from fabulous.fabric_cad.fabxplore.modules.routing_patterns.patterns.common import (
    MatrixPair,
    RoutingTrackGroup,
    allowed_source_groups,
    append_pair,
    apply_pattern_pairs,
    cardinal_routable_groups,
    routing_pattern_warnings,
    routing_track_groups,
    row_pair_count,
    unique_pairs,
)

if TYPE_CHECKING:
    from fabulous.fabric_cad.fabxplore.pnr.pnr_bridge import PnRBridge


class UniversalRoutingPattern(SwitchMatrixPatternImplementation):
    """Apply locally diverse route-through PIPs."""

    def apply(
        self,
        fpga_model: PnRBridge,
        options: SwitchMatrixPatternOptions,
    ) -> SwitchMatrixPatternApplyResult:
        """Apply the universal-style pattern to the FPGA model.

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
        groups = routing_track_groups(fpga_model, options.tile_name)
        compatible_groups = cardinal_routable_groups(groups)
        routing_pairs = _routing_pairs(compatible_groups, options)
        return apply_pattern_pairs(
            fpga_model,
            options,
            groups=groups,
            routing_pairs=routing_pairs,
            compatible_routing_groups=len(compatible_groups),
            routing_warnings=routing_pattern_warnings(
                RoutingPipPattern.UNIVERSAL,
                compatible_groups,
                routing_pairs,
            ),
        )


def _routing_pairs(
    groups: list[RoutingTrackGroup],
    options: SwitchMatrixPatternOptions,
) -> list[MatrixPair]:
    """Generate locally diverse route-through pairs.

    Parameters
    ----------
    groups : list[RoutingTrackGroup]
        Compatible routing groups.
    options : SwitchMatrixPatternOptions
        Pattern options.

    Returns
    -------
    list[MatrixPair]
        Generated routing-resource pairs.
    """
    pairs: list[MatrixPair] = []
    for destination_group in groups:
        candidate_groups = allowed_source_groups(destination_group, groups, options)
        max_source_count = max(
            (len(group.selectable_sources) for group in candidate_groups),
            default=0,
        )
        for row_index, destination_row in enumerate(destination_group.destination_rows):
            offset = 0
            while (
                row_pair_count(pairs, destination_row) < options.routing_pip_fs
                and offset < max_source_count
            ):
                for source_group in candidate_groups:
                    source = source_group.selectable_sources[
                        (row_index + offset) % len(source_group.selectable_sources)
                    ]
                    append_pair(pairs, destination_row, source)
                    if row_pair_count(pairs, destination_row) >= options.routing_pip_fs:
                        break
                offset += 1
    return unique_pairs(pairs)

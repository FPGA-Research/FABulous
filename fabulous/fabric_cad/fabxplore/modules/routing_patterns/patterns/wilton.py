"""Apply Wilton-inspired routing-resource route-through PIPs."""

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
from fabulous.fabric_definition.define import Direction

if TYPE_CHECKING:
    from fabulous.fabric_cad.fabxplore.pnr.pnr_bridge import PnRBridge

_DIRECTION_ORDER = (
    Direction.NORTH,
    Direction.EAST,
    Direction.SOUTH,
    Direction.WEST,
)


class WiltonRoutingPattern(SwitchMatrixPatternImplementation):
    """Apply side-dependent permuted route-through PIPs."""

    def apply(
        self,
        fpga_model: PnRBridge,
        options: SwitchMatrixPatternOptions,
    ) -> SwitchMatrixPatternApplyResult:
        """Apply the Wilton-inspired pattern to the FPGA model.

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
                RoutingPipPattern.WILTON,
                compatible_groups,
                routing_pairs,
            ),
        )


def _routing_pairs(
    groups: list[RoutingTrackGroup],
    options: SwitchMatrixPatternOptions,
) -> list[MatrixPair]:
    """Generate side-dependent permuted route-through pairs.

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
        for row_index, destination_row in enumerate(destination_group.destination_rows):
            for source_group in allowed_source_groups(
                destination_group,
                groups,
                options,
            ):
                source_count = len(source_group.selectable_sources)
                offset = _wilton_offset(destination_group, source_group, source_count)
                source = source_group.selectable_sources[
                    (row_index + offset) % source_count
                ]
                append_pair(pairs, destination_row, source)
                if row_pair_count(pairs, destination_row) >= options.routing_pip_fs:
                    break
    return unique_pairs(pairs)


def _wilton_offset(
    destination_group: RoutingTrackGroup,
    source_group: RoutingTrackGroup,
    source_count: int,
) -> int:
    """Return a deterministic side-dependent track permutation offset.

    Parameters
    ----------
    destination_group : RoutingTrackGroup
        Destination group.
    source_group : RoutingTrackGroup
        Candidate source group.
    source_count : int
        Number of source tracks.

    Returns
    -------
    int
        Track permutation offset.
    """
    if destination_group.direction == source_group.direction:
        return 0
    destination_index = _direction_index(destination_group.direction)
    source_index = _direction_index(source_group.direction)
    delta = (source_index - destination_index) % len(_DIRECTION_ORDER)
    return ((2 * delta) - 1) % source_count


def _direction_index(direction: Direction) -> int:
    """Return the ordering index for one routing direction.

    Parameters
    ----------
    direction : Direction
        Routing direction.

    Returns
    -------
    int
        Direction index.
    """
    return _DIRECTION_ORDER.index(direction)

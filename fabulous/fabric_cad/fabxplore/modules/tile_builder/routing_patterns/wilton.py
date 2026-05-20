"""Generate Wilton-inspired routing-resource PIPs."""

from fabulous.fabric_cad.fabxplore.modules.tile_builder.core.models import (
    RoutingPatternContext,
    RoutingPatternResult,
    RoutingTrackGroup,
)
from fabulous.fabric_definition.define import Direction

_DIRECTION_ORDER = [
    Direction.NORTH,
    Direction.EAST,
    Direction.SOUTH,
    Direction.WEST,
]


def generate_wilton_pattern(context: RoutingPatternContext) -> RoutingPatternResult:
    """Generate side-dependent permuted route-through PIPs.

    Parameters
    ----------
    context : RoutingPatternContext
        Normalized routing resources available to the pattern.

    Returns
    -------
    RoutingPatternResult
        Generated Wilton-inspired PIPs.
    """
    pairs: list[tuple[str, str]] = []
    for destination_group in context.groups:
        for row_index, destination_row in enumerate(destination_group.destination_rows):
            sources = _permuted_sources(
                destination_group=destination_group,
                row_index=row_index,
                context=context,
            )
            pairs.extend((destination_row, source) for source in sources)
    pairs = _unique_pairs(pairs)
    return RoutingPatternResult(
        pairs=pairs,
        generated_pips=len(pairs),
        compatible_groups=len(context.groups),
    )


def _permuted_sources(
    destination_group: RoutingTrackGroup,
    row_index: int,
    context: RoutingPatternContext,
) -> list[str]:
    """Return Wilton-permuted sources for one destination row.

    Parameters
    ----------
    destination_group : RoutingTrackGroup
        Group that owns the destination row.
    row_index : int
        Destination row index inside the group.
    context : RoutingPatternContext
        Pattern context and limits.

    Returns
    -------
    list[str]
        Selectable sources for the destination row.
    """
    sources: list[str] = []
    for source_group in context.groups:
        if not _allow_group_pair(destination_group, source_group, context):
            continue
        source_count = len(source_group.selectable_sources)
        if source_count == 0:
            continue
        offset = _wilton_offset(destination_group, source_group, source_count)
        source = source_group.selectable_sources[(row_index + offset) % source_count]
        if source not in sources:
            sources.append(source)
        if len(sources) >= context.fs:
            break
    return sources


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
        Source group.
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
        FABulous routing direction.

    Returns
    -------
    int
        Direction index.
    """
    return _DIRECTION_ORDER.index(direction)


def _allow_group_pair(
    destination_group: RoutingTrackGroup,
    source_group: RoutingTrackGroup,
    context: RoutingPatternContext,
) -> bool:
    """Return whether a source group may drive a destination group.

    Parameters
    ----------
    destination_group : RoutingTrackGroup
        Destination group.
    source_group : RoutingTrackGroup
        Candidate source group.
    context : RoutingPatternContext
        Pattern context and options.

    Returns
    -------
    bool
        Whether the group pair is enabled.
    """
    same_direction = destination_group.direction == source_group.direction
    if same_direction:
        return context.generate_straight
    return context.generate_turns


def _unique_pairs(pairs: list[tuple[str, str]]) -> list[tuple[str, str]]:
    """Return unique pairs while preserving order.

    Parameters
    ----------
    pairs : list[tuple[str, str]]
        Pairs to deduplicate.

    Returns
    -------
    list[tuple[str, str]]
        Unique pairs.
    """
    return list(dict.fromkeys(pairs))

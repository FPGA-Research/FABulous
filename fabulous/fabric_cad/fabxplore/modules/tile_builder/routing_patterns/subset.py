"""Generate subset-style routing-resource PIPs."""

from fabulous.fabric_cad.fabxplore.modules.tile_builder.core.models import (
    RoutingPatternContext,
    RoutingPatternResult,
    RoutingTrackGroup,
)


def generate_subset_pattern(context: RoutingPatternContext) -> RoutingPatternResult:
    """Generate same-index route-through PIPs.

    Parameters
    ----------
    context : RoutingPatternContext
        Normalized routing resources available to the pattern.

    Returns
    -------
    RoutingPatternResult
        Generated subset-style PIPs.
    """
    pairs: list[tuple[str, str]] = []
    for destination_group in context.groups:
        for row_index, destination_row in enumerate(destination_group.destination_rows):
            sources = _same_index_sources(
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


def _same_index_sources(
    destination_group: RoutingTrackGroup,
    row_index: int,
    context: RoutingPatternContext,
) -> list[str]:
    """Return same-index sources for one destination row.

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
        if not source_group.selectable_sources:
            continue
        source = source_group.selectable_sources[
            row_index % len(source_group.selectable_sources)
        ]
        if source not in sources:
            sources.append(source)
        if len(sources) >= context.fs:
            break
    return sources


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

"""Generate no additional routing-resource PIPs."""

from fabulous.fabric_cad.fabxplore.modules.tile_builder.core.models import (
    RoutingPatternContext,
    RoutingPatternResult,
)


def generate_none_pattern(context: RoutingPatternContext) -> RoutingPatternResult:
    """Return an empty routing pattern result.

    Parameters
    ----------
    context : RoutingPatternContext
        Normalized routing resources available to the pattern.

    Returns
    -------
    RoutingPatternResult
        Empty pattern result.
    """
    return RoutingPatternResult(compatible_groups=len(context.groups))

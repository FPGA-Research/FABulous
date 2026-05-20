"""Route routing-pattern requests to registered generators."""

from __future__ import annotations

from collections.abc import Callable
from typing import TYPE_CHECKING

from fabulous.fabric_cad.fabxplore.modules.tile_builder.core.models import (
    BaselineRouting,
    RoutingPatternContext,
    RoutingPatternResult,
    RoutingPipPattern,
)

from .none import generate_none_pattern
from .subset import generate_subset_pattern
from .universal import generate_universal_pattern
from .wilton import generate_wilton_pattern

if TYPE_CHECKING:
    from fabulous.fabric_cad.fabxplore.modules.tile_builder.core.base_model import (
        BaseRoutingModel,
    )

PatternGenerator = Callable[[RoutingPatternContext], RoutingPatternResult]

_PATTERN_GENERATORS: dict[RoutingPipPattern, PatternGenerator] = {
    RoutingPipPattern.NONE: generate_none_pattern,
    RoutingPipPattern.SUBSET: generate_subset_pattern,
    RoutingPipPattern.WILTON: generate_wilton_pattern,
    RoutingPipPattern.UNIVERSAL: generate_universal_pattern,
}


def generate_routing_pattern_pairs(
    base_model: BaseRoutingModel,
    routing: BaselineRouting,
) -> RoutingPatternResult:
    """Generate routing-resource PIPs for the selected pattern.

    Parameters
    ----------
    base_model : BaseRoutingModel
        Expanded base routing resources.
    routing : BaselineRouting
        Tile-builder routing options.

    Returns
    -------
    RoutingPatternResult
        Generated PIP pairs and diagnostics.
    """
    context = RoutingPatternContext(
        groups=base_model.routing_track_groups,
        fs=routing.routing_pip_fs,
        generate_straight=routing.generate_straight_routing_pips,
        generate_turns=routing.generate_turn_routing_pips,
    )
    generator = _PATTERN_GENERATORS[routing.routing_pip_pattern]
    result = generator(context)
    pairs = _unique_new_pairs(result.pairs, base_model.existing_pairs)
    warnings = list(result.warnings)
    if routing.routing_pip_pattern != RoutingPipPattern.NONE and not context.groups:
        warnings.append(
            "Routing PIP pattern requested, but no compatible routing track groups "
            "were discovered from the base CSV includes."
        )
    if routing.routing_pip_pattern != RoutingPipPattern.NONE and not pairs:
        warnings.append(
            f"Routing PIP pattern {routing.routing_pip_pattern.value!r} generated no "
            "new PIPs after removing pairs already present in base list includes."
        )
    return RoutingPatternResult(
        pairs=pairs,
        warnings=tuple(warnings),
        generated_pips=len(pairs),
        compatible_groups=result.compatible_groups,
    )


def _unique_new_pairs(
    pairs: list[tuple[str, str]],
    existing_pairs: list[tuple[str, str]],
) -> list[tuple[str, str]]:
    """Return generated pairs that are not already included by the base.

    Parameters
    ----------
    pairs : list[tuple[str, str]]
        Generated PIP pairs.
    existing_pairs : list[tuple[str, str]]
        PIP pairs already present in base list includes.

    Returns
    -------
    list[tuple[str, str]]
        Unique generated pairs not present in the base.
    """
    existing = set(existing_pairs)
    return [pair for pair in dict.fromkeys(pairs) if pair not in existing]

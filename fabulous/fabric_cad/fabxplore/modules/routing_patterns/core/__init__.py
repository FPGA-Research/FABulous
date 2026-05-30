"""Core implementation for graph-only switch-matrix pattern generation."""

from fabulous.fabric_cad.fabxplore.modules.routing_patterns.core.models import (
    RoutingPipPattern,
    SwitchMatrixPatternApplyResult,
    SwitchMatrixPatternImplementation,
    SwitchMatrixPatternOptions,
    SwitchMatrixPatternResult,
    SwitchMatrixPatternStats,
)
from fabulous.fabric_cad.fabxplore.modules.routing_patterns.core.patterner import (
    SwitchMatrixPattern,
)

__all__ = [
    "RoutingPipPattern",
    "SwitchMatrixPattern",
    "SwitchMatrixPatternApplyResult",
    "SwitchMatrixPatternImplementation",
    "SwitchMatrixPatternOptions",
    "SwitchMatrixPatternResult",
    "SwitchMatrixPatternStats",
]

"""Core implementation for benchmark-driven inverse routing."""

from fabulous.fabric_cad.fabxplore.modules.inverse_router.core.iv_router import (
    InverseRouter,
)
from fabulous.fabric_cad.fabxplore.modules.inverse_router.core.models import (
    BenchmarkSource,
    InverseRouterOptions,
    InverseRouterPruneStats,
    InverseRouterResult,
    InverseRouterRouteResult,
)

__all__ = [
    "BenchmarkSource",
    "InverseRouter",
    "InverseRouterOptions",
    "InverseRouterPruneStats",
    "InverseRouterResult",
    "InverseRouterRouteResult",
]

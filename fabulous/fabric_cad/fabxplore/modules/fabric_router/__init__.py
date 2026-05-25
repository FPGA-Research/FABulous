"""Fabric-level routing utilities for fabxplore.

This package contains routers that operate on a packed ``PyosysBridge`` design and
the active FABulous project metadata. The first implementation wraps FABulous'
nextpnr generic micro-architecture and keeps generated design artifacts under the
user-design output directory.
"""

from fabulous.fabric_cad.fabxplore.modules.fabric_router.nextpnr import (
    NextpnrCommand,
    NextpnrCommandResult,
    NextpnrRouter,
    NextpnrRouterOptions,
    NextpnrRouterPaths,
    NextpnrRouterResult,
)

__all__ = [
    "NextpnrCommand",
    "NextpnrCommandResult",
    "NextpnrRouter",
    "NextpnrRouterOptions",
    "NextpnrRouterPaths",
    "NextpnrRouterResult",
]

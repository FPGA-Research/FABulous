"""Nextpnr-backed FABulous fabric routing.

The objects exported here provide a small, testable layer over the FABulous
``nextpnr-generic --uarch fabulous`` flow. They resolve output paths, generate a
concrete PCF from the in-memory FABulous routing model, run nextpnr, and parse the
JSON report produced by nextpnr.
"""

from fabulous.fabric_cad.fabxplore.modules.fabric_router.nextpnr import (
    models,
    nextpnr_command,
    nextpnr_router,
)

NextpnrCommand = nextpnr_command.NextpnrCommand
NextpnrCommandResult = models.NextpnrCommandResult
NextpnrRouter = nextpnr_router.NextpnrRouter
NextpnrRouterOptions = models.NextpnrRouterOptions
NextpnrRouterPaths = models.NextpnrRouterPaths
NextpnrRouterResult = models.NextpnrRouterResult

__all__ = [
    "NextpnrCommand",
    "NextpnrCommandResult",
    "NextpnrRouter",
    "NextpnrRouterOptions",
    "NextpnrRouterPaths",
    "NextpnrRouterResult",
]

"""Fast tile-local graph API for FABulous routing optimization."""

from fabulous.fabric_cad.fabxplore.pnr.fab_graph.core import (
    fab_graph,
    models,
    rgraph,
    writer,
)

FabGraph = fab_graph.FabGraph
PipFileWriteResult = writer.PipFileWriteResult
ProjectSourceWriteResult = writer.ProjectSourceWriteResult
RoutingEndpoint = models.RoutingEndpoint
RoutingConfigBits = models.RoutingConfigBits
RoutingFabricGraph = rgraph.RoutingFabricGraph
RoutingGraphStats = models.RoutingGraphStats
RoutingPip = models.RoutingPip
RoutingPipKind = models.RoutingPipKind
RoutingResourceCounts = models.RoutingResourceCounts
RoutingResourceKey = models.RoutingResourceKey
RoutingSwitchMatrix = models.RoutingSwitchMatrix
RoutingTileBelModel = models.RoutingTileBelModel
RoutingTileGenIOModel = models.RoutingTileGenIOModel
RoutingTileModel = models.RoutingTileModel
RoutingTilePortModel = models.RoutingTilePortModel

__all__ = [
    "FabGraph",
    "PipFileWriteResult",
    "ProjectSourceWriteResult",
    "RoutingEndpoint",
    "RoutingConfigBits",
    "RoutingFabricGraph",
    "RoutingGraphStats",
    "RoutingPip",
    "RoutingPipKind",
    "RoutingResourceCounts",
    "RoutingResourceKey",
    "RoutingSwitchMatrix",
    "RoutingTileBelModel",
    "RoutingTileGenIOModel",
    "RoutingTileModel",
    "RoutingTilePortModel",
]

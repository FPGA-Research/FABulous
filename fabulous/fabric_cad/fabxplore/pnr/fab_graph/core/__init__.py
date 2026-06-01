"""Fast tile-local graph API for FABulous routing optimization."""

from fabulous.fabric_cad.fabxplore.pnr.fab_graph.core import (
    fab_graph,
    models,
    rgraph,
    writer,
)

FabGraph = fab_graph.FabGraph
FabricDimensions = models.FabricDimensions
PipFileWriteResult = writer.PipFileWriteResult
ProjectSourceWriteResult = writer.ProjectSourceWriteResult
RoutingEndpoint = models.RoutingEndpoint
RoutingConfigBits = models.RoutingConfigBits
RoutingFabricGraph = rgraph.RoutingFabricGraph
RoutingGraphStats = models.RoutingGraphStats
RoutingModelText = models.RoutingModelText
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
    "FabricDimensions",
    "PipFileWriteResult",
    "ProjectSourceWriteResult",
    "RoutingEndpoint",
    "RoutingConfigBits",
    "RoutingFabricGraph",
    "RoutingGraphStats",
    "RoutingModelText",
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

"""Load FABulous switch matrices from the active PnRBridge graph."""

from __future__ import annotations

from typing import TYPE_CHECKING, cast

from fabulous.fabric_cad.fabxplore.modules.routing_demand_evaluator.core.models import (
    MatrixData,
)
from fabulous.fabric_cad.fabxplore.modules.routing_demand_evaluator.core.terminal_classifier import (  # noqa: E501
    classify_tile_terminals,
)
from fabulous.fabric_cad.fabxplore.pnr.fab_graph.core.models import (
    RoutingConfigBits,
    RoutingPipKind,
)
from fabulous.fabric_definition.define import Direction

if TYPE_CHECKING:
    from fabulous.fabric_cad.fabxplore.modules.routing_demand_evaluator.core.models import (  # noqa: E501
        RoutingDemandEvaluatorOptions,
    )
    from fabulous.fabric_cad.fabxplore.pnr.fab_graph.core.models import (
        RoutingResourceKey,
        RoutingSwitchMatrix,
    )
    from fabulous.fabric_cad.fabxplore.pnr.pnr_bridge import PnRBridge
    from fabulous.fabric_definition.tile import Tile
    from fabulous.fabulous_api import FABulous_API


def load_matrix_data(
    options: RoutingDemandEvaluatorOptions,
    fpga_model: PnRBridge,
) -> MatrixData:
    """Snapshot switch-matrix connectivity and tile metadata from FabGraph.

    Parameters
    ----------
    options : RoutingDemandEvaluatorOptions
        Evaluator options.
    fpga_model : PnRBridge
        Active PnR bridge whose in-memory graph is the source of truth.

    Returns
    -------
    MatrixData
        Loaded graph snapshot.
    """
    tile = _get_tile(fpga_model.fab, options.tile_name)
    switch_matrix = fpga_model.switch_matrix(options.tile_name)
    config_bits = cast(
        "RoutingConfigBits",
        fpga_model.get_config_bits(options.tile_name),
    )
    return MatrixData(
        tile_name=options.tile_name,
        matrix_source=f"FabGraph:{options.tile_name}",
        columns=list(switch_matrix.columns),
        rows=list(switch_matrix.rows),
        connections=_connections_from_switch_matrix(switch_matrix),
        delay_by_row=_delays_from_switch_matrix(switch_matrix),
        jump_edges=_jump_edges_from_graph(fpga_model, options.tile_name),
        terminals=classify_tile_terminals(tile).terminals,
        matrix_config_bits=config_bits.matrix_config_bits,
        total_config_bits=config_bits.total_config_bits,
        config_capacity=_config_capacity(fpga_model.fab),
    )


def _get_tile(fab: FABulous_API, tile_name: str) -> Tile:
    """Return a loaded FABulous tile.

    Parameters
    ----------
    fab : FABulous_API
        Loaded FABulous API instance.
    tile_name : str
        Tile name.

    Returns
    -------
    Tile
        FABulous tile object.

    Raises
    ------
    ValueError
        If the tile is not found.
    """
    tile = fab.fabric.getTileByName(tile_name)
    if tile is None:
        raise ValueError(f"FABulous tile does not exist: {tile_name}")
    return tile


def _connections_from_switch_matrix(
    switch_matrix: RoutingSwitchMatrix,
) -> dict[str, list[str]]:
    """Return active destination-row to source-column connections.

    Parameters
    ----------
    switch_matrix : RoutingSwitchMatrix
        FabGraph switch-matrix snapshot.

    Returns
    -------
    dict[str, list[str]]
        Active matrix PIPs keyed by destination row.
    """
    connections: dict[str, list[str]] = {}
    for row_index, row in enumerate(switch_matrix.rows):
        sources = [
            column
            for column_index, column in enumerate(switch_matrix.columns)
            if switch_matrix.matrix[row_index][column_index] != 0.0
        ]
        if sources:
            connections[row] = sources
    return connections


def _delays_from_switch_matrix(
    switch_matrix: RoutingSwitchMatrix,
) -> dict[str, dict[str, float]]:
    """Return active PIP delays keyed by destination row and source column.

    Parameters
    ----------
    switch_matrix : RoutingSwitchMatrix
        FabGraph switch-matrix snapshot.

    Returns
    -------
    dict[str, dict[str, float]]
        Delay lookup for active PIPs.
    """
    delays: dict[str, dict[str, float]] = {}
    for row_index, row in enumerate(switch_matrix.rows):
        for column_index, column in enumerate(switch_matrix.columns):
            delay = switch_matrix.matrix[row_index][column_index]
            if delay != 0.0:
                delays.setdefault(row, {})[column] = float(delay)
    return delays


def _jump_edges_from_graph(
    fpga_model: PnRBridge,
    tile_name: str,
) -> list[tuple[str, str]]:
    """Return active local JUMP edges from FabGraph resource metadata.

    Parameters
    ----------
    fpga_model : PnRBridge
        Active PnR bridge.
    tile_name : str
        Tile name.

    Returns
    -------
    list[tuple[str, str]]
        Directed local JUMP edges.
    """
    edges: list[tuple[str, str]] = []
    for key in fpga_model.external_resources(tile_name):
        if key.kind is not RoutingPipKind.EXTERNAL_WIRE:
            continue
        if key.direction is not Direction.JUMP:
            continue
        edges.extend(_jump_edges_from_key(key))
    return _dedupe_edges(edges)


def _jump_edges_from_key(key: RoutingResourceKey) -> list[tuple[str, str]]:
    """Expand one JUMP resource key into tile-local graph edges.

    Parameters
    ----------
    key : RoutingResourceKey
        Active external JUMP resource key.

    Returns
    -------
    list[tuple[str, str]]
        Directed local JUMP edges.
    """
    if key.wire_count is None:
        return []
    if key.source_name == "NULL" or key.destination_name == "NULL":
        return []
    return [
        (f"{key.source_name}{index}", f"{key.destination_name}{index}")
        for index in range(key.wire_count)
    ]


def _dedupe_edges(edges: list[tuple[str, str]]) -> list[tuple[str, str]]:
    """Return unique edges while preserving order.

    Parameters
    ----------
    edges : list[tuple[str, str]]
        Edge list.

    Returns
    -------
    list[tuple[str, str]]
        Deduplicated edges.
    """
    seen: set[tuple[str, str]] = set()
    result: list[tuple[str, str]] = []
    for edge in edges:
        if edge not in seen:
            seen.add(edge)
            result.append(edge)
    return result


def _config_capacity(fab: FABulous_API) -> int:
    """Return the fabric config-bit capacity for one tile.

    Parameters
    ----------
    fab : FABulous_API
        Loaded FABulous API instance.

    Returns
    -------
    int
        Config-bit capacity.
    """
    return fab.fabric.frameBitsPerRow * fab.fabric.maxFramesPerCol

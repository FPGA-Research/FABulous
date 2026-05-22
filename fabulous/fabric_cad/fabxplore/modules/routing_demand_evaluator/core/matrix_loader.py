"""Load FABulous switch matrices for routing-demand evaluation."""

from __future__ import annotations

import csv
from typing import TYPE_CHECKING

from fabulous.fabric_cad.fabxplore.modules.routing_demand_evaluator.core.models import (
    MatrixData,
    RoutingDemandEvaluatorOptions,
    RoutingTerminalRole,
)
from fabulous.fabric_cad.fabxplore.modules.routing_demand_evaluator.core.terminal_classifier import (  # noqa: E501
    classify_tile_terminals,
)
from fabulous.fabric_definition.define import Direction
from fabulous.fabric_generator.parser.parse_csv import parsePortLine
from fabulous.fabric_generator.parser.parse_switchmatrix import parseList, parseMatrix
from fabulous.fabulous_settings import get_context

if TYPE_CHECKING:
    from pathlib import Path

    from fabulous.fabric_definition.port import Port
    from fabulous.fabric_definition.tile import Tile
    from fabulous.fabulous_api import FABulous_API


def load_matrix_data(
    options: RoutingDemandEvaluatorOptions,
    fab: FABulous_API,
) -> MatrixData:
    """Load switch-matrix connectivity and tile metadata.

    Parameters
    ----------
    options : RoutingDemandEvaluatorOptions
        Evaluator options.
    fab : FABulous_API
        Loaded FABulous API instance.

    Returns
    -------
    MatrixData
        Loaded matrix data.

    Raises
    ------
    ValueError
        If the requested tile or matrix cannot be resolved.
    """
    tile = _get_tile(fab, options.tile_name)
    tile_dir = options.tile_dir or _tile_dir(tile)
    tile_csv = options.tile_csv or tile_dir / f"{options.tile_name}.csv"
    switch_matrix = options.switch_matrix or tile.matrixDir
    if switch_matrix is None:
        raise ValueError(f"Tile {options.tile_name} has no active switch matrix")
    switch_matrix = _resolve_matrix_path(switch_matrix, tile_dir)
    connections = _read_connections(switch_matrix, options.tile_name)
    capacity = _config_capacity(fab, options.config_bit_capacity_override)
    return MatrixData(
        tile_name=options.tile_name,
        tile_dir=tile_dir,
        tile_csv=tile_csv,
        switch_matrix=switch_matrix,
        connections=connections,
        jump_edges=_read_jump_edges(tile_csv),
        terminals=classify_tile_terminals(
            tile,
            carry_port_roles=_read_carry_port_roles(tile_csv),
        ).terminals,
        matrix_config_bits=tile.matrixConfigBits,
        total_config_bits=tile.globalConfigBits,
        config_capacity=capacity,
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


def _tile_dir(tile: Tile) -> Path:
    """Return the directory containing one tile CSV.

    Parameters
    ----------
    tile : Tile
        FABulous tile.

    Returns
    -------
    Path
        Tile directory.
    """
    if tile.matrixDir:
        return tile.matrixDir.parent
    return tile.tileDir.parent


def _resolve_matrix_path(matrix: Path, tile_dir: Path) -> Path:
    """Resolve a matrix path.

    Parameters
    ----------
    matrix : Path
        Matrix path, possibly relative.
    tile_dir : Path
        Tile directory.

    Returns
    -------
    Path
        Resolved matrix path.
    """
    if matrix.is_absolute():
        return matrix
    candidate = tile_dir / matrix
    if candidate.exists():
        return candidate.resolve()
    return (get_context().proj_dir / matrix).resolve()


def _read_connections(matrix_path: Path, tile_name: str) -> dict[str, list[str]]:
    """Read switch-matrix connectivity with FABulous parsers.

    Parameters
    ----------
    matrix_path : Path
        Matrix list or CSV path.
    tile_name : str
        Tile name for CSV validation.

    Returns
    -------
    dict[str, list[str]]
        Mapping from destination rows to selectable sources.

    Raises
    ------
    ValueError
        If the matrix format is unsupported.
    """
    match matrix_path.suffix:
        case ".list":
            return {
                row: list(sources)
                for row, sources in parseList(matrix_path, collect="source").items()
            }
        case ".csv":
            return {
                row: list(sources)
                for row, sources in parseMatrix(matrix_path, tile_name).items()
            }
        case _:
            raise ValueError(
                "routing-demand evaluator supports only .list and .csv matrices, "
                f"got {matrix_path}"
            )


def _read_jump_edges(tile_csv: Path) -> list[tuple[str, str]]:
    """Read local JUMP edges from a tile CSV and its includes.

    Parameters
    ----------
    tile_csv : Path
        Tile CSV path.

    Returns
    -------
    list[tuple[str, str]]
        Directed JUMP edges expanded with FABulous port expansion.
    """
    edges: list[tuple[str, str]] = []
    for csv_path in _iter_csv_fragments(tile_csv):
        for row in _read_csv_rows(csv_path):
            if not row or row[0] != "JUMP":
                continue
            ports, _common = parsePortLine(",".join(row))
            edges.extend(_jump_edges_from_ports(ports))
    return _dedupe_edges(edges)


def _read_carry_port_roles(tile_csv: Path) -> dict[str, RoutingTerminalRole]:
    """Read carry-annotated tile port roles from CSV fragments.

    Parameters
    ----------
    tile_csv : Path
        Tile CSV path.

    Returns
    -------
    dict[str, RoutingTerminalRole]
        Mapping from expanded port node name to carry role.
    """
    roles: dict[str, RoutingTerminalRole] = {}
    for csv_path in _iter_csv_fragments(tile_csv):
        for row in _read_csv_rows(csv_path):
            if len(row) < 7 or row[0] == "JUMP" or "CARRY" not in row[6]:
                continue
            ports, _common = parsePortLine(",".join(row))
            for port in ports:
                sources, sinks = port.expandPortInfo("AutoSwitchMatrix")
                roles.update(
                    {source: RoutingTerminalRole.CARRY_OUTPUT for source in sources}
                )
                roles.update({sink: RoutingTerminalRole.CARRY_INPUT for sink in sinks})
    return roles


def _iter_csv_fragments(tile_csv: Path) -> list[Path]:
    """Return a tile CSV and recursively included CSV fragments.

    Parameters
    ----------
    tile_csv : Path
        Root tile CSV path.

    Returns
    -------
    list[Path]
        CSV files in traversal order.
    """
    visited: set[Path] = set()
    ordered: list[Path] = []

    def visit(path: Path) -> None:
        resolved = path.resolve()
        if resolved in visited or not resolved.exists():
            return
        visited.add(resolved)
        ordered.append(resolved)
        for row in _read_csv_rows(resolved):
            if row and row[0] == "INCLUDE" and len(row) > 1:
                visit((resolved.parent / row[1]).resolve())

    visit(tile_csv)
    return ordered


def _read_csv_rows(path: Path) -> list[list[str]]:
    """Read stripped CSV rows.

    Parameters
    ----------
    path : Path
        CSV file path.

    Returns
    -------
    list[list[str]]
        CSV rows.
    """
    rows: list[list[str]] = []
    with path.open(newline="", encoding="utf-8") as stream:
        for row in csv.reader(stream):
            stripped = [field.strip() for field in row]
            if stripped and stripped[0]:
                rows.append(stripped)
    return rows


def _jump_edges_from_ports(ports: list[Port]) -> list[tuple[str, str]]:
    """Expand parsed JUMP ports into directed local edges.

    Parameters
    ----------
    ports : list[Port]
        Ports returned by FABulous ``parsePortLine``.

    Returns
    -------
    list[tuple[str, str]]
        Expanded JUMP edges.

    Raises
    ------
    ValueError
        If a routable JUMP expansion has mismatched source and sink counts.
    """
    edges: list[tuple[str, str]] = []
    for port in ports:
        if port.wireDirection != Direction.JUMP:
            continue
        sources, sinks = port.expandPortInfo("AutoSwitchMatrix")
        if not sources or not sinks:
            break
        if len(sources) != len(sinks):
            raise ValueError(
                "JUMP port expansion produced mismatched source/sink counts: "
                f"{sources!r} -> {sinks!r}"
            )
        edges.extend(zip(sources, sinks, strict=True))
        break
    return edges


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


def _config_capacity(fab: FABulous_API, override: int | None = None) -> int:
    """Return the fabric config-bit capacity for one tile.

    Parameters
    ----------
    fab : FABulous_API
        Loaded FABulous API instance.
    override : int | None
        Optional capacity override.

    Returns
    -------
    int
        Config-bit capacity.
    """
    if override is not None:
        return override
    return fab.fabric.frameBitsPerRow * fab.fabric.maxFramesPerCol

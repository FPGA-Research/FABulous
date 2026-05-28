"""Writers for the fast tile-local FABulous routing graph.

The fast graph owns tile resources and lazily materializes concrete PIPs.  This
module handles file output only: ``pips.txt``, explicit matrix lists/CSVs, and
standalone tile CSVs.
"""

from __future__ import annotations

import csv
import shutil
from dataclasses import dataclass
from typing import TYPE_CHECKING

from fabulous.fabric_definition.define import Direction

if TYPE_CHECKING:
    from collections.abc import Iterable
    from pathlib import Path

    from fabulous.fabric_cad.fabxplore.pnr.fab_graph.core import (
        rgraph,
    )
    from fabulous.fabric_cad.fabxplore.pnr.fab_graph.core.models import (
        RoutingResourceKey,
        RoutingTileBelModel,
        RoutingTileGenIOModel,
        RoutingTileModel,
        RoutingTilePortModel,
    )


@dataclass(frozen=True, slots=True)
class PipFileWriteResult:
    """Metadata returned after writing ``pips.txt``.

    Attributes
    ----------
    path : Path
        Written path.
    pip_count : int | None
        Active PIPs represented in the file, if requested.
    byte_count : int
        UTF-8 byte count.
    """

    path: Path
    pip_count: int | None
    byte_count: int


@dataclass(frozen=True, slots=True)
class TileSourceWriteResult:
    """Metadata returned after writing one tile type.

    Attributes
    ----------
    tile_type : str
        Tile type written.
    tile_csv_path : Path
        Written tile CSV.
    matrix_list_path : Path
        Written matrix list.
    matrix_csv_path : Path
        Written matrix CSV.
    routing_rows : int
        Number of routing rows.
    matrix_pairs : int
        Number of matrix pairs.
    removed_artifacts : tuple[Path, ...]
        Removed stale generated artifacts.
    """

    tile_type: str
    tile_csv_path: Path
    matrix_list_path: Path
    matrix_csv_path: Path
    routing_rows: int
    matrix_pairs: int
    removed_artifacts: tuple[Path, ...]


@dataclass(frozen=True, slots=True)
class ProjectSourceWriteResult:
    """Metadata returned after writing tile sources.

    Attributes
    ----------
    tile_results : tuple[TileSourceWriteResult, ...]
        Per-tile write results.
    """

    tile_results: tuple[TileSourceWriteResult, ...]


def render_pips_txt(graph: rgraph.RoutingFabricGraph) -> str:
    """Render active graph PIPs.

    Parameters
    ----------
    graph : rgraph.RoutingFabricGraph
        Graph to render.

    Returns
    -------
    str
        ``pips.txt`` text.
    """
    return graph.render_pips_txt()


def render_matrix_list(
    graph: rgraph.RoutingFabricGraph,
    tile_type: str,
) -> str:
    """Render active matrix rows as explicit list pairs.

    Parameters
    ----------
    graph : rgraph.RoutingFabricGraph
        Graph to inspect.
    tile_type : str
        Tile type to render.

    Returns
    -------
    str
        Matrix list text.
    """
    pairs = _matrix_pairs(graph, tile_type)
    if not pairs:
        return ""
    return "\n".join(f"{source},{sink}" for source, sink in pairs) + "\n"


def render_matrix_csv(
    graph: rgraph.RoutingFabricGraph,
    tile_type: str,
) -> str:
    """Render active matrix rows as switch-matrix CSV.

    Parameters
    ----------
    graph : rgraph.RoutingFabricGraph
        Graph to inspect.
    tile_type : str
        Tile type to render.

    Returns
    -------
    str
        Matrix CSV text.
    """
    pairs = _matrix_pairs(graph, tile_type)
    destinations = list(dict.fromkeys(sink for _source, sink in pairs))
    sources = list(dict.fromkeys(source for source, _sink in pairs))
    pair_set = set(pairs)
    rows: list[list[str | int]] = [[tile_type, *destinations]]
    rows.extend(
        [
            source,
            *[
                1 if (source, destination) in pair_set else 0
                for destination in destinations
            ],
        ]
        for source in sources
    )
    return _csv_text(rows)


def render_tile_csv(
    graph: rgraph.RoutingFabricGraph,
    tile_type: str,
    matrix_list_name: str | None = None,
) -> str:
    """Render one standalone tile CSV.

    Parameters
    ----------
    graph : rgraph.RoutingFabricGraph
        Graph to inspect.
    tile_type : str
        Tile type to render.
    matrix_list_name : str | None
        Matrix list or CSV file name to reference.

    Returns
    -------
    str
        Tile CSV text.
    """
    tile = graph.tile_model(tile_type)
    matrix_name = matrix_list_name or f"{tile_type}_switch_matrix.list"
    rows: list[list[str | int]] = [["TILE", tile_type]]
    rows.extend(_external_csv_rows(graph, tile_type))
    rows.extend(_gen_io_rows(tile.gen_ios))
    rows.extend(_bel_rows(tile))
    rows.append(["MATRIX", f"./{matrix_name}"])
    rows.append(["EndTILE"])
    return _csv_text(rows)


def write_tile_sources(
    graph: rgraph.RoutingFabricGraph,
    output_root: Path | None = None,
    tile_types: Iterable[str] | None = None,
    *,
    remove_generated_artifacts: bool = True,
    preserve_relative_to: Path | None = None,
    copy_bel_sources: bool = False,
) -> ProjectSourceWriteResult:
    """Write standalone tile sources.

    Parameters
    ----------
    graph : rgraph.RoutingFabricGraph
        Graph to write.
    output_root : Path | None
        Optional project root.
    tile_types : Iterable[str] | None
        Optional tile-type subset.
    remove_generated_artifacts : bool
        Whether to remove stale generated files.
    preserve_relative_to : Path | None
        Preserve original tile-relative layout below this root.
    copy_bel_sources : bool
        Copy tile-local BEL sources.

    Returns
    -------
    ProjectSourceWriteResult
        Per-tile write metadata.
    """
    selected = tuple(tile_types) if tile_types is not None else graph.tile_types()
    return ProjectSourceWriteResult(
        tile_results=tuple(
            write_tile_source(
                graph,
                tile_type,
                _output_tile_dir(
                    graph.tile_model(tile_type),
                    output_root,
                    preserve_relative_to,
                ),
                remove_generated_artifacts=remove_generated_artifacts,
                copy_bel_sources=copy_bel_sources,
            )
            for tile_type in selected
        )
    )


def write_tile_source(
    graph: rgraph.RoutingFabricGraph,
    tile_type: str,
    tile_dir: Path,
    *,
    remove_generated_artifacts: bool = True,
    copy_bel_sources: bool = False,
) -> TileSourceWriteResult:
    """Write standalone sources for one tile type.

    Parameters
    ----------
    graph : rgraph.RoutingFabricGraph
        Graph to write.
    tile_type : str
        Tile type to write.
    tile_dir : Path
        Destination tile directory.
    remove_generated_artifacts : bool
        Remove stale generated files.
    copy_bel_sources : bool
        Copy tile-local BEL source files.

    Returns
    -------
    TileSourceWriteResult
        Write metadata.
    """
    tile = graph.tile_model(tile_type)
    tile_dir.mkdir(parents=True, exist_ok=True)
    tile_csv_path = tile_dir / f"{tile_type}.csv"
    matrix_list_path = tile_dir / f"{tile_type}_switch_matrix.list"
    matrix_csv_path = tile_dir / f"{tile_type}_switch_matrix.csv"
    removed = (
        _remove_generated_tile_artifacts(tile_dir, tile_type)
        if remove_generated_artifacts
        else ()
    )
    if copy_bel_sources:
        _copy_tile_bel_sources(tile, tile_dir)

    matrix_list_path.write_text(render_matrix_list(graph, tile_type), encoding="utf-8")
    matrix_csv_path.write_text(render_matrix_csv(graph, tile_type), encoding="utf-8")
    tile_csv_path.write_text(
        render_tile_csv(graph, tile_type, matrix_csv_path.name),
        encoding="utf-8",
    )
    return TileSourceWriteResult(
        tile_type=tile_type,
        tile_csv_path=tile_csv_path,
        matrix_list_path=matrix_list_path,
        matrix_csv_path=matrix_csv_path,
        routing_rows=len(_external_csv_rows(graph, tile_type)),
        matrix_pairs=len(_matrix_pairs(graph, tile_type)),
        removed_artifacts=removed,
    )


def write_pips_txt(
    graph: rgraph.RoutingFabricGraph,
    output_path: Path,
    *,
    count_pips: bool = False,
) -> PipFileWriteResult:
    """Write active graph PIPs to ``pips.txt``.

    Parameters
    ----------
    graph : rgraph.RoutingFabricGraph
        Graph to render.
    output_path : Path
        Destination path.
    count_pips : bool
        Whether to count active PIPs for the returned metadata.  Counting
        requires a second lazy graph walk, so optimizer loops should leave this
        disabled.

    Returns
    -------
    PipFileWriteResult
        Write metadata.
    """
    text = render_pips_txt(graph)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(text, encoding="utf-8")
    return PipFileWriteResult(
        path=output_path,
        pip_count=sum(1 for _pip in graph.iter_pips()) if count_pips else None,
        byte_count=len(text.encode("utf-8")),
    )


def _matrix_pairs(
    graph: rgraph.RoutingFabricGraph,
    tile_type: str,
) -> tuple[tuple[str, str], ...]:
    """Return active matrix pairs for one tile type.

    Parameters
    ----------
    graph : rgraph.RoutingFabricGraph
        Graph to inspect.
    tile_type : str
        Tile type to inspect.

    Returns
    -------
    tuple[tuple[str, str], ...]
        Matrix pairs.
    """
    return tuple(
        (key.source_name, key.destination_name)
        for key in graph.matrix_resources(tile_type)
    )


def _external_csv_rows(
    graph: rgraph.RoutingFabricGraph,
    tile_type: str,
) -> list[list[str | int]]:
    """Return active external resource rows for one tile type.

    Parameters
    ----------
    graph : rgraph.RoutingFabricGraph
        Graph to inspect.
    tile_type : str
        Tile type to inspect.

    Returns
    -------
    list[list[str | int]]
        Tile CSV routing rows.
    """
    rows: list[list[str | int]] = []
    seen_rows: set[tuple[str | int, ...]] = set()
    managed_identities: set[tuple[str, str, int, int, str]] = set()
    for key in graph.external_resources(tile_type):
        _validate_external_resource_for_csv(key)
        managed_identities.add(_external_resource_port_identity(key))
        _append_unique_row(
            rows,
            seen_rows,
            [
                key.direction.value,
                key.source_name,
                key.x_offset,
                key.y_offset,
                key.destination_name,
                key.wire_count,
                "",
            ],
        )

    matrix_wires = _active_matrix_wires(graph, tile_type)
    for port in graph.tile_model(tile_type).ports:
        if _tile_port_identity(port) in managed_identities:
            continue
        if _declared_wires_for_port(port).isdisjoint(matrix_wires):
            continue
        _append_unique_row(rows, seen_rows, _port_csv_row(port))
    return rows


def _active_matrix_wires(
    graph: rgraph.RoutingFabricGraph,
    tile_type: str,
) -> set[str]:
    """Return wires referenced by active matrix rows.

    Parameters
    ----------
    graph : rgraph.RoutingFabricGraph
        Graph to inspect.
    tile_type : str
        Tile type to inspect.

    Returns
    -------
    set[str]
        Matrix wires.
    """
    wires: set[str] = set()
    for key in graph.matrix_resources(tile_type):
        wires.add(key.source_name)
        wires.add(key.destination_name)
    return wires


def _external_resource_port_identity(
    key: RoutingResourceKey,
) -> tuple[str, str, int, int, str]:
    """Return resource identity excluding wire count.

    Parameters
    ----------
    key : RoutingResourceKey
        External key.

    Returns
    -------
    tuple[str, str, int, int, str]
        Port identity.

    Raises
    ------
    ValueError
        If the key has no external direction.
    """
    if key.direction is None:
        raise ValueError(f"external resource has no direction: {key}")
    return (
        key.direction.value,
        key.source_name,
        key.x_offset,
        key.y_offset,
        key.destination_name,
    )


def _tile_port_identity(port: RoutingTilePortModel) -> tuple[str, str, int, int, str]:
    """Return port identity excluding wire count.

    Parameters
    ----------
    port : RoutingTilePortModel
        Port metadata.

    Returns
    -------
    tuple[str, str, int, int, str]
        Port identity.
    """
    return (
        port.direction.value,
        port.source_name,
        port.x_offset,
        port.y_offset,
        port.destination_name,
    )


def _append_unique_row(
    rows: list[list[str | int]],
    seen_rows: set[tuple[str | int, ...]],
    row: list[str | int],
) -> None:
    """Append one CSV row if not already present.

    Parameters
    ----------
    rows : list[list[str | int]]
        Rows to mutate.
    seen_rows : set[tuple[str | int, ...]]
        Row identities already emitted.
    row : list[str | int]
        Candidate row.
    """
    row_key = tuple(row)
    if row_key not in seen_rows:
        seen_rows.add(row_key)
        rows.append(row)


def _port_csv_row(port: RoutingTilePortModel) -> list[str | int]:
    """Return one tile routing CSV row.

    Parameters
    ----------
    port : RoutingTilePortModel
        Port metadata.

    Returns
    -------
    list[str | int]
        CSV row.
    """
    return [
        port.direction.value,
        port.source_name,
        port.x_offset,
        port.y_offset,
        port.destination_name,
        port.wire_count,
        "",
    ]


def _declared_wires_for_port(port: RoutingTilePortModel) -> frozenset[str]:
    """Return matrix-visible wires declared by a port row.

    Parameters
    ----------
    port : RoutingTilePortModel
        Port metadata.

    Returns
    -------
    frozenset[str]
        Declared wires.
    """
    wire_count = port.wire_count
    if port.direction is not Direction.JUMP and (
        port.source_name == "NULL" or port.destination_name == "NULL"
    ):
        wire_count *= abs(port.x_offset) + abs(port.y_offset)
    wires: set[str] = set()
    for index in range(wire_count):
        if port.source_name != "NULL":
            wires.add(f"{port.source_name}{index}")
        if port.destination_name != "NULL":
            wires.add(f"{port.destination_name}{index}")
    return frozenset(wires)


def _validate_external_resource_for_csv(key: RoutingResourceKey) -> None:
    """Validate external resource metadata for CSV emission.

    Parameters
    ----------
    key : RoutingResourceKey
        External key.

    Raises
    ------
    ValueError
        If direction or wire count is missing.
    """
    if key.direction is None:
        raise ValueError(f"external resource has no direction metadata: {key}")
    if key.wire_count is None:
        raise ValueError(f"external resource has no wire count metadata: {key}")


def _gen_io_rows(gen_ios: tuple[RoutingTileGenIOModel, ...]) -> list[list[str | int]]:
    """Return GEN_IO CSV rows.

    Parameters
    ----------
    gen_ios : tuple[RoutingTileGenIOModel, ...]
        GEN_IO metadata.

    Returns
    -------
    list[list[str | int]]
        CSV rows.
    """
    return [_gen_io_row(gen_io) for gen_io in gen_ios]


def _gen_io_row(gen_io: RoutingTileGenIOModel) -> list[str | int]:
    """Return one GEN_IO CSV row.

    Parameters
    ----------
    gen_io : RoutingTileGenIOModel
        GEN_IO metadata.

    Returns
    -------
    list[str | int]
        CSV row.
    """
    row: list[str | int] = ["GEN_IO", gen_io.pins, gen_io.io.value, gen_io.prefix]
    if gen_io.config_access:
        row.append("CONFIGACCESS")
    if gen_io.inverted:
        row.append("INVERTED")
    if gen_io.clocked:
        row.append("CLOCKED")
    if gen_io.clocked_comb:
        row.append("CLOCKED_COMB")
    if gen_io.clocked_mux:
        row.append("CLOCKED_MUX")
    return row


def _bel_rows(tile: RoutingTileModel) -> list[list[str]]:
    """Return BEL CSV rows.

    Parameters
    ----------
    tile : RoutingTileModel
        Tile metadata.

    Returns
    -------
    list[list[str]]
        BEL rows.
    """
    return [_bel_row(tile, bel) for bel in tile.bels]


def _bel_row(tile: RoutingTileModel, bel: RoutingTileBelModel) -> list[str]:
    """Return one BEL CSV row.

    Parameters
    ----------
    tile : RoutingTileModel
        Tile metadata.
    bel : RoutingTileBelModel
        BEL metadata.

    Returns
    -------
    list[str]
        BEL row.
    """
    row = ["BEL", _relative_bel_path(tile, bel)]
    if bel.prefix:
        row.append(bel.prefix)
    return row


def _relative_bel_path(tile: RoutingTileModel, bel: RoutingTileBelModel) -> str:
    """Return BEL path relative to tile directory when possible.

    Parameters
    ----------
    tile : RoutingTileModel
        Tile metadata.
    bel : RoutingTileBelModel
        BEL metadata.

    Returns
    -------
    str
        CSV path.
    """
    try:
        relative = bel.source_path.relative_to(tile.tile_dir)
    except ValueError:
        return str(bel.source_path)
    return f"./{relative.as_posix()}"


def _csv_text(rows: list[list[str | int]]) -> str:
    """Render CSV rows with Unix line endings.

    Parameters
    ----------
    rows : list[list[str | int]]
        Rows to render.

    Returns
    -------
    str
        CSV text.
    """
    from io import StringIO

    output = StringIO()
    writer = csv.writer(output, lineterminator="\n")
    writer.writerows(rows)
    return output.getvalue()


def _output_tile_dir(
    tile: RoutingTileModel,
    output_root: Path | None,
    preserve_relative_to: Path | None,
) -> Path:
    """Return output directory for one tile.

    Parameters
    ----------
    tile : RoutingTileModel
        Tile metadata.
    output_root : Path | None
        Optional root.
    preserve_relative_to : Path | None
        Optional source project root.

    Returns
    -------
    Path
        Output tile directory.
    """
    if output_root is None:
        return tile.tile_dir
    if preserve_relative_to is not None:
        return output_root / tile.tile_dir.relative_to(preserve_relative_to)
    return output_root / "Tile" / tile.tile_type


def _copy_tile_bel_sources(tile: RoutingTileModel, tile_dir: Path) -> None:
    """Copy BEL files that live inside the source tile directory.

    Parameters
    ----------
    tile : RoutingTileModel
        Tile metadata.
    tile_dir : Path
        Destination directory.
    """
    for bel in tile.bels:
        try:
            relative = bel.source_path.relative_to(tile.tile_dir)
        except ValueError:
            continue
        destination = tile_dir / relative
        if bel.source_path.resolve() == destination.resolve():
            continue
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(bel.source_path, destination)


def _remove_generated_tile_artifacts(
    tile_dir: Path,
    tile_type: str,
) -> tuple[Path, ...]:
    """Remove stale generated artifacts for one tile type.

    Parameters
    ----------
    tile_dir : Path
        Tile directory.
    tile_type : str
        Tile type.

    Returns
    -------
    tuple[Path, ...]
        Removed paths.
    """
    candidates = [
        tile_dir / f"{tile_type}.v",
        tile_dir / f"{tile_type}.vhdl",
        tile_dir / f"{tile_type}_ConfigMem.csv",
        tile_dir / f"{tile_type}_ConfigMem.v",
        tile_dir / f"{tile_type}_ConfigMem.vhdl",
        tile_dir / f"{tile_type}_switch_matrix.csv",
        tile_dir / f"{tile_type}_switch_matrix.v",
        tile_dir / f"{tile_type}_switch_matrix.vhdl",
    ]
    removed: list[Path] = []
    for path in candidates:
        if path.exists():
            path.unlink()
            removed.append(path)
    return tuple(removed)

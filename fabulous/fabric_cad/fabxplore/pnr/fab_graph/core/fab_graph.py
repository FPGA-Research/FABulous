"""Public facade for FABulous routing graph edits.

``FabGraph`` wraps :class:`RoutingFabricGraph` with a user-facing API.
The facade keeps hot operations tile-local: adding, deleting, restoring, and
resizing resources update only the affected tile type and its tile-local indexes.
Concrete PIPs are generated lazily for queries that explicitly ask for
PIPs, for ``pips.txt`` rendering, or for project write-back.
"""

from __future__ import annotations

import csv
import pickle
import shutil
from pathlib import Path
from typing import TYPE_CHECKING

import fabulous.fabulous_settings as fabulous_settings
from fabulous.fabric_cad.fabxplore.pnr.fab_graph.core.models import (
    RoutingConfigBits,
    RoutingGraphStats,
    RoutingPip,
    RoutingPipKind,
    RoutingResourceCounts,
    RoutingResourceKey,
    RoutingSwitchMatrix,
    RoutingTileModel,
)
from fabulous.fabric_cad.fabxplore.pnr.fab_graph.core.rgraph import (
    RoutingFabricGraph,
)
from fabulous.fabric_cad.fabxplore.pnr.fab_graph.core.writer import (
    write_pips_txt,
    write_tile_source,
    write_tile_sources,
)

if TYPE_CHECKING:
    from collections.abc import Callable, Iterable

    from fabulous.fabric_definition.define import Direction
    from fabulous.fabulous_api import FABulous_API


def _filter_items[ItemT](
    items: Iterable[ItemT],
    where: Callable[[ItemT], bool] | None,
) -> list[ItemT]:
    """Return items accepted by an optional predicate.

    Parameters
    ----------
    items : Iterable[ItemT]
        Candidate items.
    where : Callable[[ItemT], bool] | None
        Optional predicate.  If ``None``, all items are returned.

    Returns
    -------
    list[ItemT]
        Filtered items.
    """
    if where is None:
        return list(items)
    return [item for item in items if where(item)]


class FabGraph:
    """Public routing graph API.

    Parameters
    ----------
    fabulous_api : FABulous_API
        Loaded FABulous project API.
    project_dir : Path
        FABulous project root.
    routing_graph : RoutingFabricGraph | None
        Optional pre-built graph.  If omitted, the graph is built from the
        currently loaded ``fabulous_api.fabric``.
    """

    def __init__(
        self,
        fabulous_api: FABulous_API,
        project_dir: Path,
        routing_graph: RoutingFabricGraph | None = None,
    ) -> None:
        self.fab = fabulous_api
        self.project_dir = Path(project_dir)
        self._graph = routing_graph or RoutingFabricGraph.from_fabric(self.fab.fabric)

    @classmethod
    def from_routing_graph(
        cls,
        fabulous_api: FABulous_API,
        project_dir: Path,
        routing_graph: RoutingFabricGraph,
    ) -> FabGraph:
        """Wrap an existing graph.

        Parameters
        ----------
        fabulous_api : FABulous_API
            Loaded FABulous project API.
        project_dir : Path
            FABulous project root.
        routing_graph : RoutingFabricGraph
            Existing tile-local graph.

        Returns
        -------
        FabGraph
            Public facade.
        """
        return cls(fabulous_api, project_dir, routing_graph)

    @property
    def routing_graph(self) -> RoutingFabricGraph:
        """Return the wrapped graph.

        Returns
        -------
        RoutingFabricGraph
            Wrapped graph.
        """
        return self._graph

    def stats(self) -> RoutingGraphStats:
        """Materialize and return graph statistics.

        Returns
        -------
        RoutingGraphStats
            Concrete graph counts.
        """
        return self._graph.stats()

    def get_config_bits(
        self,
        tile_type: str | None = None,
    ) -> RoutingConfigBits | dict[str, RoutingConfigBits]:
        """Return current tile-local configuration-bit counts.

        Parameters
        ----------
        tile_type : str | None
            Optional tile type.  If omitted, returns counts for all tile types.

        Returns
        -------
        RoutingConfigBits | dict[str, RoutingConfigBits]
            One tile summary, or summaries keyed by tile type.
        """
        return self._graph.get_config_bits(tile_type)

    def get_resource_counts(
        self,
        tile_type: str | None = None,
    ) -> RoutingResourceCounts | dict[str, RoutingResourceCounts]:
        """Return tile-local routing resource counts.

        Parameters
        ----------
        tile_type : str | None
            Optional tile type.  If omitted, returns counts for all tile types.

        Returns
        -------
        RoutingResourceCounts | dict[str, RoutingResourceCounts]
            One tile summary, or summaries keyed by tile type.
        """
        return self._graph.get_resource_counts(tile_type)

    def tile_types(
        self,
        where: Callable[[str], bool] | None = None,
    ) -> list[str]:
        """Return tile types represented by the graph.

        Parameters
        ----------
        where : Callable[[str], bool] | None
            Optional predicate.

        Returns
        -------
        list[str]
            Tile type names.
        """
        return _filter_items(self._graph.tile_types(), where)

    def tile_model(self, tile_type: str) -> RoutingTileModel:
        """Return metadata for one tile type.

        Parameters
        ----------
        tile_type : str
            Tile type name.

        Returns
        -------
        RoutingTileModel
            Tile metadata.
        """
        return self._graph.tile_model(tile_type)

    def active_pips(
        self,
        where: Callable[[RoutingPip], bool] | None = None,
    ) -> list[RoutingPip]:
        """Materialize active concrete PIPs.

        Parameters
        ----------
        where : Callable[[RoutingPip], bool] | None
            Optional predicate.

        Returns
        -------
        list[RoutingPip]
            Active concrete PIPs.
        """
        return _filter_items(self._graph.active_pips(), where)

    def disabled_pips(
        self,
        where: Callable[[RoutingPip], bool] | None = None,
    ) -> list[RoutingPip]:
        """Materialize disabled concrete PIPs.

        Parameters
        ----------
        where : Callable[[RoutingPip], bool] | None
            Optional predicate.

        Returns
        -------
        list[RoutingPip]
            Disabled concrete PIPs.
        """
        return _filter_items(self._graph.disabled_pips(), where)

    def external_resources(
        self,
        tile_type: str | None = None,
        *,
        active_only: bool = True,
        where: Callable[[RoutingResourceKey], bool] | None = None,
    ) -> list[RoutingResourceKey]:
        """Return external routing resources from tile-local indexes.

        Parameters
        ----------
        tile_type : str | None
            Optional tile type.
        active_only : bool
            If ``True``, return only active resources.
        where : Callable[[RoutingResourceKey], bool] | None
            Optional predicate.

        Returns
        -------
        list[RoutingResourceKey]
            Matching resource keys.
        """
        return _filter_items(
            self._graph.external_resources(tile_type, active_only=active_only),
            where,
        )

    def matrix_resources(
        self,
        tile_type: str | None = None,
        *,
        active_only: bool = True,
        where: Callable[[RoutingResourceKey], bool] | None = None,
    ) -> list[RoutingResourceKey]:
        """Return matrix resources from tile-local indexes.

        Parameters
        ----------
        tile_type : str | None
            Optional tile type.
        active_only : bool
            If ``True``, return only active resources.
        where : Callable[[RoutingResourceKey], bool] | None
            Optional predicate.

        Returns
        -------
        list[RoutingResourceKey]
            Matching resource keys.
        """
        return _filter_items(
            self._graph.matrix_resources(tile_type, active_only=active_only),
            where,
        )

    def matrix_sources(
        self,
        tile_type: str,
        where: Callable[[str], bool] | None = None,
    ) -> list[str]:
        """Return matrix source candidate wires for one tile type.

        Parameters
        ----------
        tile_type : str
            Tile type name.
        where : Callable[[str], bool] | None
            Optional predicate.

        Returns
        -------
        list[str]
            Candidate wire names.
        """
        return _filter_items(self._graph.matrix_sources(tile_type), where)

    def matrix_sinks(
        self,
        tile_type: str,
        where: Callable[[str], bool] | None = None,
    ) -> list[str]:
        """Return matrix sink candidate wires for one tile type.

        Parameters
        ----------
        tile_type : str
            Tile type name.
        where : Callable[[str], bool] | None
            Optional predicate.

        Returns
        -------
        list[str]
            Candidate wire names.
        """
        return _filter_items(self._graph.matrix_sinks(tile_type), where)

    def switch_matrix(self, tile_type: str) -> RoutingSwitchMatrix:
        """Return a tile-local switch-matrix delay table.

        Parameters
        ----------
        tile_type : str
            Tile type to inspect.

        Returns
        -------
        RoutingSwitchMatrix
            Matrix rows, columns, and delay values.
        """
        return self._graph.switch_matrix(tile_type)

    def set_switch_matrix(
        self,
        tile_type: str,
        columns: list[str],
        rows: list[str],
        matrix: list[list[float]],
    ) -> None:
        """Replace one tile type's switch matrix from a delay table.

        Parameters
        ----------
        tile_type : str
            Tile type to update.
        columns : list[str]
            Matrix column labels from :meth:`switch_matrix`.
        rows : list[str]
            Matrix row labels from :meth:`switch_matrix`.
        matrix : list[list[float]]
            Delay matrix. ``0.0`` disables a PIP; positive values set the active
            PIP delay.
        """
        self._graph.set_switch_matrix(tile_type, columns, rows, matrix)

    def render_pips_txt(self) -> str:
        """Render active concrete PIPs in nextpnr ``pips.txt`` format.

        Returns
        -------
        str
            PIP text.
        """
        return self._graph.render_pips_txt()

    def add_external_resource(
        self,
        tile_type: str,
        direction: Direction,
        source_name: str,
        x_offset: int,
        y_offset: int,
        destination_name: str,
        wire_count: int,
        *,
        delay: float = 8,
    ) -> None:
        """Add an external CSV-style routing resource.

        Parameters
        ----------
        tile_type : str
            Owner tile type.
        direction : Direction
            FABulous routing direction.
        source_name : str
            CSV source name.
        x_offset : int
            CSV X offset.
        y_offset : int
            CSV Y offset.
        destination_name : str
            CSV destination name.
        wire_count : int
            Number of wires in the resource.
        delay : float
            Delay used when PIPs are materialized.
        """
        self._graph.add_external_resource(
            tile_type,
            direction,
            source_name,
            x_offset,
            y_offset,
            destination_name,
            wire_count,
            delay=delay,
        )

    def add_matrix_resource(
        self,
        tile_type: str,
        source_name: str,
        destination_name: str,
        *,
        delay: float = 8,
    ) -> None:
        """Add one switch-matrix row.

        Parameters
        ----------
        tile_type : str
            Owner tile type.
        source_name : str
            Matrix source wire.
        destination_name : str
            Matrix destination wire.
        delay : float
            Delay used when PIPs are materialized.
        """
        self._graph.add_matrix_resource(
            tile_type,
            source_name,
            destination_name,
            delay=delay,
        )

    def add_matrix_rows(
        self,
        tile_type: str,
        entries: Iterable[tuple[str, str, float]],
        *,
        overwrite: bool = False,
    ) -> None:
        """Add multiple matrix rows.

        Parameters
        ----------
        tile_type : str
            Owner tile type.
        entries : Iterable[tuple[str, str, float]]
            Matrix row triplets as ``(source, destination, delay)``.
        overwrite : bool
            If ``True``, active matrix rows for ``tile_type`` are deleted before
            inserting the new rows.
        """
        self._graph.add_matrix_rows(tile_type, entries, overwrite=overwrite)

    def _delete_resource(self, resource_key: RoutingResourceKey) -> None:
        """Delete one routing resource.

        Parameters
        ----------
        resource_key : RoutingResourceKey
            Resource to delete.
        """
        self._graph.delete_resource(resource_key)

    def _disable_resource(self, resource_key: RoutingResourceKey) -> None:
        """Alias for :meth:`_delete_resource`.

        Parameters
        ----------
        resource_key : RoutingResourceKey
            Resource to disable.
        """
        self._delete_resource(resource_key)

    def delete_external_resource(
        self,
        tile_type: str | None = None,
        direction: Direction | None = None,
        source_name: str | None = None,
        x_offset: int | None = None,
        y_offset: int | None = None,
        destination_name: str | None = None,
        wire_count: int | None = None,
        *,
        key: RoutingResourceKey | None = None,
    ) -> None:
        """Delete an external resource by key or CSV-style parameters.

        Parameters
        ----------
        tile_type : str | None
            Owner tile type.
        direction : Direction | None
            FABulous routing direction.
        source_name : str | None
            CSV source name.
        x_offset : int | None
            CSV X offset.
        y_offset : int | None
            CSV Y offset.
        destination_name : str | None
            CSV destination name.
        wire_count : int | None
            Optional current wire count.
        key : RoutingResourceKey | None
            Optional pre-resolved key.  If provided, parameters are ignored.
        """
        self._delete_resource(
            self._resolve_external_resource_key(
                tile_type,
                direction,
                source_name,
                x_offset,
                y_offset,
                destination_name,
                wire_count,
                key=key,
                active_only=True,
            )
        )

    def disable_external_resource(
        self,
        tile_type: str | None = None,
        direction: Direction | None = None,
        source_name: str | None = None,
        x_offset: int | None = None,
        y_offset: int | None = None,
        destination_name: str | None = None,
        wire_count: int | None = None,
        *,
        key: RoutingResourceKey | None = None,
    ) -> None:
        """Alias for :meth:`delete_external_resource`.

        Parameters
        ----------
        tile_type : str | None
            Owner tile type.
        direction : Direction | None
            FABulous routing direction.
        source_name : str | None
            CSV source name.
        x_offset : int | None
            CSV X offset.
        y_offset : int | None
            CSV Y offset.
        destination_name : str | None
            CSV destination name.
        wire_count : int | None
            Optional current wire count.
        key : RoutingResourceKey | None
            Optional pre-resolved key.
        """
        self.delete_external_resource(
            tile_type,
            direction,
            source_name,
            x_offset,
            y_offset,
            destination_name,
            wire_count,
            key=key,
        )

    def delete_matrix_resource(
        self,
        tile_type: str | None = None,
        source_name: str | None = None,
        destination_name: str | None = None,
        *,
        key: RoutingResourceKey | None = None,
    ) -> None:
        """Delete a switch-matrix row by key or row parameters.

        Parameters
        ----------
        tile_type : str | None
            Owner tile type.
        source_name : str | None
            Matrix source wire.
        destination_name : str | None
            Matrix destination wire.
        key : RoutingResourceKey | None
            Optional pre-resolved key.  If provided, parameters are ignored.
        """
        self._delete_resource(
            self._resolve_matrix_resource_key(
                tile_type,
                source_name,
                destination_name,
                key=key,
                active_only=True,
            )
        )

    def disable_matrix_resource(
        self,
        tile_type: str | None = None,
        source_name: str | None = None,
        destination_name: str | None = None,
        *,
        key: RoutingResourceKey | None = None,
    ) -> None:
        """Alias for :meth:`delete_matrix_resource`.

        Parameters
        ----------
        tile_type : str | None
            Owner tile type.
        source_name : str | None
            Matrix source wire.
        destination_name : str | None
            Matrix destination wire.
        key : RoutingResourceKey | None
            Optional pre-resolved key.
        """
        self.delete_matrix_resource(
            tile_type,
            source_name,
            destination_name,
            key=key,
        )

    def _restore_resource(self, resource_key: RoutingResourceKey) -> None:
        """Restore one disabled routing resource.

        Parameters
        ----------
        resource_key : RoutingResourceKey
            Resource to restore.
        """
        self._graph.restore_resource(resource_key)

    def _enable_resource(self, resource_key: RoutingResourceKey) -> None:
        """Alias for :meth:`_restore_resource`.

        Parameters
        ----------
        resource_key : RoutingResourceKey
            Resource to enable.
        """
        self._restore_resource(resource_key)

    def restore_external_resource(
        self,
        tile_type: str | None = None,
        direction: Direction | None = None,
        source_name: str | None = None,
        x_offset: int | None = None,
        y_offset: int | None = None,
        destination_name: str | None = None,
        wire_count: int | None = None,
        *,
        key: RoutingResourceKey | None = None,
    ) -> None:
        """Restore an external resource by key or CSV-style parameters.

        Parameters
        ----------
        tile_type : str | None
            Owner tile type.
        direction : Direction | None
            FABulous routing direction.
        source_name : str | None
            CSV source name.
        x_offset : int | None
            CSV X offset.
        y_offset : int | None
            CSV Y offset.
        destination_name : str | None
            CSV destination name.
        wire_count : int | None
            Optional current wire count.
        key : RoutingResourceKey | None
            Optional pre-resolved key.
        """
        self._restore_resource(
            self._resolve_external_resource_key(
                tile_type,
                direction,
                source_name,
                x_offset,
                y_offset,
                destination_name,
                wire_count,
                key=key,
                active_only=False,
            )
        )

    def enable_external_resource(
        self,
        tile_type: str | None = None,
        direction: Direction | None = None,
        source_name: str | None = None,
        x_offset: int | None = None,
        y_offset: int | None = None,
        destination_name: str | None = None,
        wire_count: int | None = None,
        *,
        key: RoutingResourceKey | None = None,
    ) -> None:
        """Alias for :meth:`restore_external_resource`.

        Parameters
        ----------
        tile_type : str | None
            Owner tile type.
        direction : Direction | None
            FABulous routing direction.
        source_name : str | None
            CSV source name.
        x_offset : int | None
            CSV X offset.
        y_offset : int | None
            CSV Y offset.
        destination_name : str | None
            CSV destination name.
        wire_count : int | None
            Optional current wire count.
        key : RoutingResourceKey | None
            Optional pre-resolved key.
        """
        self.restore_external_resource(
            tile_type,
            direction,
            source_name,
            x_offset,
            y_offset,
            destination_name,
            wire_count,
            key=key,
        )

    def restore_matrix_resource(
        self,
        tile_type: str | None = None,
        source_name: str | None = None,
        destination_name: str | None = None,
        *,
        key: RoutingResourceKey | None = None,
    ) -> None:
        """Restore a switch-matrix row by key or row parameters.

        Parameters
        ----------
        tile_type : str | None
            Owner tile type.
        source_name : str | None
            Matrix source wire.
        destination_name : str | None
            Matrix destination wire.
        key : RoutingResourceKey | None
            Optional pre-resolved key.
        """
        self._restore_resource(
            self._resolve_matrix_resource_key(
                tile_type,
                source_name,
                destination_name,
                key=key,
                active_only=False,
            )
        )

    def enable_matrix_resource(
        self,
        tile_type: str | None = None,
        source_name: str | None = None,
        destination_name: str | None = None,
        *,
        key: RoutingResourceKey | None = None,
    ) -> None:
        """Alias for :meth:`restore_matrix_resource`.

        Parameters
        ----------
        tile_type : str | None
            Owner tile type.
        source_name : str | None
            Matrix source wire.
        destination_name : str | None
            Matrix destination wire.
        key : RoutingResourceKey | None
            Optional pre-resolved key.
        """
        self.restore_matrix_resource(
            tile_type,
            source_name,
            destination_name,
            key=key,
        )

    def resize_external_resource(
        self,
        tile_type: str | None = None,
        direction: Direction | None = None,
        source_name: str | None = None,
        x_offset: int | None = None,
        y_offset: int | None = None,
        destination_name: str | None = None,
        new_wire_count: int | None = None,
        *,
        wire_count: int | None = None,
        key: RoutingResourceKey | None = None,
    ) -> None:
        """Resize an external resource by key or CSV-style parameters.

        Parameters
        ----------
        tile_type : str | None
            Owner tile type.
        direction : Direction | None
            FABulous routing direction.
        source_name : str | None
            CSV source name.
        x_offset : int | None
            CSV X offset.
        y_offset : int | None
            CSV Y offset.
        destination_name : str | None
            CSV destination name.
        new_wire_count : int | None
            New wire count.  ``0`` deletes the resource.
        wire_count : int | None
            Optional current wire count.
        key : RoutingResourceKey | None
            Optional pre-resolved key.

        Raises
        ------
        ValueError
            If ``new_wire_count`` is missing.
        """
        if new_wire_count is None:
            raise ValueError("resize_external_resource requires new_wire_count.")
        self._graph.resize_external_resource(
            self._resolve_external_resource_key(
                tile_type,
                direction,
                source_name,
                x_offset,
                y_offset,
                destination_name,
                wire_count,
                key=key,
                active_only=True,
            ),
            new_wire_count,
        )

    def write_pips_txt(self, output_path: Path | str) -> None:
        """Write active PIPs to an explicit ``pips.txt`` path.

        Parameters
        ----------
        output_path : Path | str
            Destination path.
        """
        write_pips_txt(self._graph, Path(output_path))

    def write_pips(self, path: Path | str | None = None) -> None:
        """Write only ``pips.txt`` from the current graph.

        Parameters
        ----------
        path : Path | str | None
            Optional destination path.  If omitted, writes to
            ``<project>/.FABulous/pips.txt``.  Existing directories receive a
            child file named ``pips.txt``.
        """
        output_path = self.project_dir / ".FABulous" / "pips.txt"
        if path is not None:
            output_path = Path(path)
            if output_path.exists() and output_path.is_dir():
                output_path = output_path / "pips.txt"
        write_pips_txt(self._graph, output_path)

    def write_tile(
        self,
        name: str | None = None,
        path: Path | str | None = None,
    ) -> None:
        """Write one tile type to an explicit output directory.

        Parameters
        ----------
        name : str | None
            Tile type to write.
        path : Path | str | None
            Destination tile directory.

        Raises
        ------
        ValueError
            If ``name`` or ``path`` is omitted.
        """
        if not name:
            raise ValueError("write_tile requires a tile name.")
        if path is None:
            raise ValueError("write_tile requires an explicit output path.")
        write_tile_source(
            self._graph,
            name,
            Path(path),
            remove_generated_artifacts=True,
            copy_bel_sources=True,
        )

    def write_project(
        self,
        path: Path | str | None = None,
        *,
        generate_rtl: bool = True,
    ) -> None:
        """Write a complete FABulous project from the current graph.

        Parameters
        ----------
        path : Path | str | None
            Optional destination project.  If omitted, the current project is
            overwritten in place.
        generate_rtl : bool
            If ``True``, regenerate switch-matrix RTL, config memory, and tile
            RTL.  If ``False``, only the config-memory data needed for metadata
            is generated.

        Raises
        ------
        ValueError
            If the output path is not a directory or lies inside the source
            project.
        """
        target_project = self.project_dir if path is None else Path(path)
        if target_project.exists() and not target_project.is_dir():
            raise ValueError(
                f"Project output path is not a directory: {target_project}"
            )

        in_place = target_project.resolve() == self.project_dir.resolve()
        if not in_place:
            self._copy_project_shell(target_project)
            self._copy_supertile_sources(target_project)
            write_tile_sources(
                self._graph,
                output_root=target_project,
                remove_generated_artifacts=True,
                preserve_relative_to=self.project_dir,
                copy_bel_sources=True,
            )
        else:
            write_tile_sources(
                self._graph,
                remove_generated_artifacts=True,
            )

        try:
            self._reload_project(target_project)
            self._generate_project_artifacts(generate_rtl=generate_rtl)
            self._write_routing_metadata(target_project / ".FABulous")
        finally:
            if not in_place:
                self._reload_project(self.project_dir)

    def write_tile_sources(
        self,
        output_root: Path | str | None = None,
        tile_types: Iterable[str] | None = None,
        *,
        remove_generated_artifacts: bool = True,
    ) -> None:
        """Write tile source files from the graph.

        Parameters
        ----------
        output_root : Path | str | None
            Optional output project root.  If omitted, writes in place.
        tile_types : Iterable[str] | None
            Optional tile-type subset.
        remove_generated_artifacts : bool
            Remove stale generated tile artifacts before writing.
        """
        root = None if output_root is None else Path(output_root)
        write_tile_sources(
            self._graph,
            output_root=root,
            tile_types=tile_types,
            remove_generated_artifacts=remove_generated_artifacts,
        )

    def _copy_project_shell(self, target_project: Path) -> None:
        """Copy non-generated project content to a new project.

        Parameters
        ----------
        target_project : Path
            Destination project root.

        Raises
        ------
        ValueError
            If ``target_project`` is inside the current project.
        """
        source_project = self.project_dir.resolve()
        target_resolved = target_project.resolve()
        if target_resolved != source_project and target_resolved.is_relative_to(
            source_project
        ):
            raise ValueError(
                "Project output path must not be inside the source project: "
                f"{target_project}"
            )

        target_project.mkdir(parents=True, exist_ok=True)
        for generated_dir in (target_project / "Tile", target_project / ".FABulous"):
            if generated_dir.exists():
                shutil.rmtree(generated_dir)

        for source in self.project_dir.iterdir():
            if source.name in {"Tile", ".FABulous"}:
                continue
            destination = target_project / source.name
            if source.is_dir():
                shutil.copytree(source, destination, dirs_exist_ok=True)
            else:
                destination.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(source, destination)

    def _copy_supertile_sources(self, target_project: Path) -> None:
        """Copy project-level supertile descriptor CSVs.

        Parameters
        ----------
        target_project : Path
            Destination project root.

        Raises
        ------
        FileNotFoundError
            If a referenced supertile source is missing.
        """
        fabric_csv = self.project_dir / "fabric.csv"
        with fabric_csv.open(encoding="utf-8", newline="") as fabric_file:
            fabric_reader = csv.reader(fabric_file)
            for row in fabric_reader:
                if not row or row[0].strip().lower() != "supertile":
                    continue
                if len(row) < 2 or not row[1].strip():
                    continue
                source = self.project_dir / row[1].strip()
                if not source.exists():
                    raise FileNotFoundError(
                        f"Missing FABulous supertile source: {source}"
                    )
                destination = target_project / source.relative_to(self.project_dir)
                destination.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(source, destination)

    def _reload_project(self, project_dir: Path) -> None:
        """Reload the FABulous API from one project.

        Parameters
        ----------
        project_dir : Path
            Project root.

        Raises
        ------
        FileNotFoundError
            If ``fabric.csv`` is missing.
        """
        fabric_csv = project_dir / "fabric.csv"
        if not fabric_csv.exists():
            raise FileNotFoundError(f"Missing FABulous project file: {fabric_csv}")
        self._set_project_context(project_dir)
        self.fab.loadFabric(fabric_csv)

    def _set_project_context(self, project_dir: Path) -> None:
        """Set FABulous global project context.

        Parameters
        ----------
        project_dir : Path
            Project root.
        """
        fabulous_settings._context_instance = (  # noqa: SLF001
            fabulous_settings.FABulousSettings.model_construct(
                proj_dir=project_dir,
                nix_shell=None,
            )
        )

    def _generate_project_artifacts(self, *, generate_rtl: bool) -> None:
        """Generate derived FABulous tile artifacts.

        Parameters
        ----------
        generate_rtl : bool
            Whether to generate tile RTL in addition to config-memory CSV data.
        """
        for tile_type in self._graph.tile_types():
            tile = self.fab.getTile(tile_type, raises_on_miss=True)
            tile_dir = tile.tileDir.parent

            if generate_rtl:
                self.fab.setWriterOutputFile(
                    tile_dir / f"{tile_type}_switch_matrix{self.fab.fileExtension}"
                )
                self.fab.genSwitchMatrix(tile_type)

            config_mem_rtl = tile_dir / f"{tile_type}_ConfigMem{self.fab.fileExtension}"
            self.fab.setWriterOutputFile(config_mem_rtl)
            self.fab.genConfigMem(tile_type, tile_dir / f"{tile_type}_ConfigMem.csv")
            if not generate_rtl and config_mem_rtl.exists():
                config_mem_rtl.unlink()

            if generate_rtl:
                self.fab.setWriterOutputFile(
                    tile_dir / f"{tile_type}{self.fab.fileExtension}"
                )
                self.fab.genTile(tile_type)

    def _write_routing_metadata(self, metadata_dir: Path) -> Path:
        """Write nextpnr and bitstream metadata from the loaded project.

        Parameters
        ----------
        metadata_dir : Path
            Destination ``.FABulous`` directory.

        Returns
        -------
        Path
            Metadata directory.
        """
        metadata_dir.mkdir(parents=True, exist_ok=True)

        pips, bel, bel_v2, template_pcf = self.fab.genRoutingModel()
        (metadata_dir / "pips.txt").write_text(pips, encoding="utf-8")
        (metadata_dir / "bel.txt").write_text(bel, encoding="utf-8")
        (metadata_dir / "bel.v2.txt").write_text(bel_v2, encoding="utf-8")
        (metadata_dir / "template.pcf").write_text(template_pcf, encoding="utf-8")

        spec_object = self.fab.genBitStreamSpec()
        with (metadata_dir / "bitStreamSpec.bin").open("wb") as out_file:
            pickle.dump(spec_object, out_file)

        with (metadata_dir / "bitStreamSpec.csv").open(
            "w",
            encoding="utf-8",
            newline="\n",
        ) as spec_file:
            spec_writer = csv.writer(spec_file)
            for tile_name in spec_object["TileSpecs"]:
                spec_writer.writerow([tile_name])
                for key, value in spec_object["TileSpecs"][tile_name].items():
                    spec_writer.writerow([key, value])

        return metadata_dir

    def _resolve_external_resource_key(
        self,
        tile_type: str | None,
        direction: Direction | None,
        source_name: str | None,
        x_offset: int | None,
        y_offset: int | None,
        destination_name: str | None,
        wire_count: int | None,
        *,
        key: RoutingResourceKey | None,
        active_only: bool,
    ) -> RoutingResourceKey:
        """Resolve an external resource key.

        Parameters
        ----------
        tile_type : str | None
            Owner tile type.
        direction : Direction | None
            FABulous routing direction.
        source_name : str | None
            CSV source name.
        x_offset : int | None
            CSV X offset.
        y_offset : int | None
            CSV Y offset.
        destination_name : str | None
            CSV destination name.
        wire_count : int | None
            Optional wire count.
        key : RoutingResourceKey | None
            Optional pre-resolved key.
        active_only : bool
            If ``True``, require an active resource.

        Returns
        -------
        RoutingResourceKey
            Resolved key.
        """
        if key is not None:
            self._validate_resource_key_kind(key, RoutingPipKind.EXTERNAL_WIRE)
            return key
        self._require_lookup_parameters(
            "external resource",
            {
                "tile_type": tile_type,
                "direction": direction,
                "source_name": source_name,
                "x_offset": x_offset,
                "y_offset": y_offset,
                "destination_name": destination_name,
            },
        )
        return self._graph.external_resource_key(
            tile_type,
            direction,
            source_name,
            x_offset,
            y_offset,
            destination_name,
            wire_count,
            active_only=active_only,
        )

    def _resolve_matrix_resource_key(
        self,
        tile_type: str | None,
        source_name: str | None,
        destination_name: str | None,
        *,
        key: RoutingResourceKey | None,
        active_only: bool,
    ) -> RoutingResourceKey:
        """Resolve a matrix resource key.

        Parameters
        ----------
        tile_type : str | None
            Owner tile type.
        source_name : str | None
            Matrix source wire.
        destination_name : str | None
            Matrix destination wire.
        key : RoutingResourceKey | None
            Optional pre-resolved key.
        active_only : bool
            If ``True``, require an active resource.

        Returns
        -------
        RoutingResourceKey
            Resolved key.
        """
        if key is not None:
            self._validate_resource_key_kind(key, RoutingPipKind.INTERNAL_MATRIX)
            return key
        self._require_lookup_parameters(
            "matrix resource",
            {
                "tile_type": tile_type,
                "source_name": source_name,
                "destination_name": destination_name,
            },
        )
        return self._graph.matrix_resource_key(
            tile_type,
            source_name,
            destination_name,
            active_only=active_only,
        )

    @staticmethod
    def _validate_resource_key_kind(
        key: RoutingResourceKey,
        kind: RoutingPipKind,
    ) -> None:
        """Validate a resource key kind.

        Parameters
        ----------
        key : RoutingResourceKey
            Resource key.
        kind : RoutingPipKind
            Expected kind.

        Raises
        ------
        ValueError
            If the key kind is wrong.
        """
        if key.kind is not kind:
            raise ValueError(f"Expected {kind.value} resource key, got {key.kind}.")

    @staticmethod
    def _require_lookup_parameters(
        label: str,
        values: dict[str, object | None],
    ) -> None:
        """Validate parameter-based key lookup inputs.

        Parameters
        ----------
        label : str
            Human-readable lookup label.
        values : dict[str, object | None]
            Parameter names and values.

        Raises
        ------
        ValueError
            If any required value is missing.
        """
        missing = [name for name, value in values.items() if value is None]
        if missing:
            joined = ", ".join(missing)
            raise ValueError(f"{label} lookup requires {joined}, or key.")

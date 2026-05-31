"""Fast tile-local routing resource graph for FABulous projects.

The fast graph keeps tile-type routing resources as the source of truth.  Hot
operations such as add, delete, restore, resize, and resource queries update only
per-tile dictionaries and indexes.  Concrete PIPs are generated lazily
when callers ask for ``pips.txt``, concrete PIP lists, or full statistics.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, replace
from typing import TYPE_CHECKING

from fabulous.custom_exception import InvalidFileType
from fabulous.fabric_cad.fabxplore.pnr.fab_graph.core.models import (
    RoutingConfigBits,
    RoutingEndpoint,
    RoutingGraphStats,
    RoutingPip,
    RoutingPipKind,
    RoutingResourceCounts,
    RoutingResourceKey,
    RoutingSwitchMatrix,
    RoutingTileBelModel,
    RoutingTileGenIOModel,
    RoutingTileModel,
    RoutingTilePortModel,
)
from fabulous.fabric_definition.define import Direction
from fabulous.fabric_generator.parser.parse_switchmatrix import parseList, parseMatrix

if TYPE_CHECKING:
    from collections.abc import Iterable, Iterator

    from fabulous.fabric_cad.timing_model.FABulous_timing_model_interface import (
        FABulousTimingModelInterface,
    )
    from fabulous.fabric_definition.bel import Bel
    from fabulous.fabric_definition.fabric import Fabric
    from fabulous.fabric_definition.gen_io import Gen_IO
    from fabulous.fabric_definition.port import Port
    from fabulous.fabric_definition.tile import Tile


@dataclass(slots=True)
class _ExternalResourceState:
    """Mutable state for one external tile resource.

    Attributes
    ----------
    key : RoutingResourceKey
        External resource identity.
    delay : float
        Delay used when materializing concrete PIPs.
    active : bool
        Whether this resource currently participates in the architecture.
    """

    key: RoutingResourceKey
    delay: float = 8
    active: bool = True


@dataclass(slots=True)
class _MatrixResourceState:
    """Mutable state for one internal matrix resource.

    Attributes
    ----------
    key : RoutingResourceKey
        Matrix resource identity.
    delay : float
        Delay used when materializing concrete PIPs.
    active : bool
        Whether this row currently participates in the architecture.
    """

    key: RoutingResourceKey
    delay: float = 8
    active: bool = True


class RoutingFabricGraph:
    """Tile-local routing resource graph with lazy concrete PIP generation.

    Parameters
    ----------
    rows : int
        Fabric row count.
    columns : int
        Fabric column count.
    tile_types_by_xy : dict[tuple[int, int], str]
        Placed tile-type lookup.
    tile_models : dict[str, RoutingTileModel]
        Tile metadata keyed by tile type.
    """

    def __init__(
        self,
        rows: int,
        columns: int,
        tile_types_by_xy: dict[tuple[int, int], str],
        tile_models: dict[str, RoutingTileModel],
    ) -> None:
        self.rows = rows
        self.columns = columns
        self.tile_types_by_xy = dict(tile_types_by_xy)
        self._tile_models = dict(tile_models)
        self._tile_locations_by_type = _tile_locations_by_type(self.tile_types_by_xy)
        self._static_matrix_wires_by_tile_type = _static_matrix_wires_by_tile_type(
            self._tile_models
        )

        self._external_by_tile: dict[
            str,
            dict[RoutingResourceKey, _ExternalResourceState],
        ] = defaultdict(dict)
        self._matrix_by_tile: dict[
            str,
            dict[RoutingResourceKey, _MatrixResourceState],
        ] = defaultdict(dict)
        self._external_lookup: dict[
            tuple[str, Direction, str, int, int, str, int],
            RoutingResourceKey,
        ] = {}
        self._matrix_pair_lookup: dict[
            tuple[str, str, str],
            RoutingResourceKey,
        ] = {}
        self._matrix_by_wire: dict[
            tuple[str, str],
            dict[RoutingResourceKey, None],
        ] = defaultdict(dict)

    @classmethod
    def from_fabric(
        cls,
        fabric: Fabric,
        delay_model: FABulousTimingModelInterface | None = None,
    ) -> RoutingFabricGraph:
        """Build a fast graph from a parsed FABulous fabric.

        Parameters
        ----------
        fabric : Fabric
            Parsed FABulous fabric.
        delay_model : FABulousTimingModelInterface | None
            Optional delay model.  Matrix row delays are captured per tile type;
            external resources currently use the FABulous default delay.

        Returns
        -------
        RoutingFabricGraph
            Fast tile-local graph.
        """
        tile_types_by_xy = _tile_type_map(fabric)
        tile_models = _tile_models(fabric)
        graph = cls(
            rows=fabric.numberOfRows,
            columns=fabric.numberOfColumns,
            tile_types_by_xy=tile_types_by_xy,
            tile_models=tile_models,
        )

        matrix_pair_cache: dict[tuple[str, str], tuple[tuple[str, str], ...]] = {}
        tile_definitions = _tile_definitions_by_type(fabric)
        for tile_type, tile in tile_definitions.items():
            seen_external_rows: set[tuple[Direction, str, int, int, str, int]] = set()
            for port in tile.portsInfo:
                external_row = (
                    port.wireDirection,
                    port.sourceName,
                    port.xOffset,
                    port.yOffset,
                    port.destinationName,
                    port.wireCount,
                )
                if external_row in seen_external_rows:
                    continue
                seen_external_rows.add(external_row)
                graph.add_external_resource(
                    tile_type,
                    port.wireDirection,
                    port.sourceName,
                    port.xOffset,
                    port.yOffset,
                    port.destinationName,
                    port.wireCount,
                )
            for source_name, destination_name in _matrix_pairs(tile, matrix_pair_cache):
                delay = (
                    8
                    if delay_model is None
                    else delay_model.pip_delay(
                        tile_type,
                        destination_name,
                        source_name,
                    )
                )
                graph.add_matrix_resource(
                    tile_type,
                    source_name,
                    destination_name,
                    delay=delay,
                )

        return graph

    def tile_types(self) -> tuple[str, ...]:
        """Return all known tile types in first-seen order.

        Returns
        -------
        tuple[str, ...]
            Tile type names, including standalone tile definitions that are not
            placed in the fabric grid.
        """
        return tuple(self._tile_models)

    def placed_tile_types(self) -> tuple[str, ...]:
        """Return tile types with at least one placed grid instance.

        Returns
        -------
        tuple[str, ...]
            Tile type names that can emit concrete routing PIPs.
        """
        return tuple(
            tile_type
            for tile_type in self._tile_models
            if self._tile_locations_by_type.get(tile_type)
        )

    def standalone_tile_types(self) -> tuple[str, ...]:
        """Return declared tile types with no placed grid instances.

        Returns
        -------
        tuple[str, ...]
            Tile type names that are available for tile-local queries and edits
            but cannot emit concrete routing PIPs.
        """
        return tuple(
            tile_type
            for tile_type in self._tile_models
            if not self._tile_locations_by_type.get(tile_type)
        )

    def tile_models(self) -> tuple[RoutingTileModel, ...]:
        """Return tile metadata models in graph order.

        Returns
        -------
        tuple[RoutingTileModel, ...]
            Tile models.
        """
        return tuple(self._tile_models.values())

    def tile_model(self, tile_type: str) -> RoutingTileModel:
        """Return metadata for one tile type.

        Parameters
        ----------
        tile_type : str
            Tile type to look up.

        Returns
        -------
        RoutingTileModel
            Tile metadata.
        """
        return self._tile_models[tile_type]

    def tile_type_at(self, x: int, y: int) -> str | None:
        """Return the placed tile type at one grid coordinate.

        Parameters
        ----------
        x : int
            Fabric x coordinate.
        y : int
            Fabric y coordinate.

        Returns
        -------
        str | None
            Placed tile type, or ``None`` if the coordinate has no tile.
        """
        return self.tile_types_by_xy.get((x, y))

    def tile_model_at(self, x: int, y: int) -> RoutingTileModel | None:
        """Return the placed tile model at one grid coordinate.

        Parameters
        ----------
        x : int
            Fabric x coordinate.
        y : int
            Fabric y coordinate.

        Returns
        -------
        RoutingTileModel | None
            Shared tile model for the placed tile type, or ``None`` if the
            coordinate has no tile.
        """
        tile_type = self.tile_type_at(x, y)
        if tile_type is None:
            return None
        return self.tile_model(tile_type)

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
        """Add or restore an external CSV-style resource for one tile type.

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
            CSV wire count.
        delay : float
            Delay used when concrete PIPs are materialized.

        Raises
        ------
        ValueError
            If ``wire_count`` is not positive or the active resource exists.
        """
        self._require_tile_type(tile_type)
        if wire_count <= 0:
            raise ValueError(f"wire count must be positive: {wire_count}")
        key = RoutingResourceKey(
            tile_type=tile_type,
            kind=RoutingPipKind.EXTERNAL_WIRE,
            source_name=source_name,
            destination_name=destination_name,
            direction=direction,
            x_offset=x_offset,
            y_offset=y_offset,
            wire_count=wire_count,
            wire_class=abs(x_offset) + abs(y_offset),
        )
        existing = self._external_by_tile[tile_type].get(key)
        if existing is not None:
            if existing.active:
                raise ValueError(f"external resource already exists: {key}")
            existing.active = True
            existing.delay = delay
        else:
            self._external_by_tile[tile_type][key] = _ExternalResourceState(
                key=key,
                delay=delay,
            )
            self._external_lookup[_external_lookup_key(key)] = key

        # maybe add here _validate_tile of tile_type

    def add_matrix_resource(
        self,
        tile_type: str,
        source_name: str,
        destination_name: str,
        *,
        delay: float = 8,
    ) -> None:
        """Add or restore one switch-matrix row for a tile type.

        Parameters
        ----------
        tile_type : str
            Owner tile type.
        source_name : str
            Matrix source wire.
        destination_name : str
            Matrix destination wire.
        delay : float
            Delay used when concrete PIPs are materialized.

        Raises
        ------
        ValueError
            If the active row exists or references unavailable wires.
        """
        self._require_tile_type(tile_type)
        key = RoutingResourceKey(
            tile_type=tile_type,
            kind=RoutingPipKind.INTERNAL_MATRIX,
            source_name=source_name,
            destination_name=destination_name,
            matrix_path=self.tile_model(tile_type).matrix_path,
        )
        existing = self._matrix_by_tile[tile_type].get(key)
        created = existing is None
        if existing is not None:
            if existing.active:
                raise ValueError(f"matrix resource already exists: {key}")
            existing.active = True
            existing.delay = delay
        else:
            self._matrix_by_tile[tile_type][key] = _MatrixResourceState(
                key=key,
                delay=delay,
            )
            self._matrix_pair_lookup[(tile_type, source_name, destination_name)] = key
            self._matrix_by_wire[(tile_type, source_name)][key] = None
            self._matrix_by_wire[(tile_type, destination_name)][key] = None
        try:
            self._validate_matrix_resource(key)
        except ValueError:
            if created:
                del self._matrix_by_tile[tile_type][key]
                self._matrix_pair_lookup.pop(
                    (tile_type, source_name, destination_name),
                    None,
                )
                self._matrix_by_wire[(tile_type, source_name)].pop(key, None)
                self._matrix_by_wire[(tile_type, destination_name)].pop(key, None)
            else:
                self._matrix_by_tile[tile_type][key].active = False
            raise

    def add_matrix_rows(
        self,
        tile_type: str,
        entries: Iterable[tuple[str, str, float]],
        *,
        overwrite: bool = False,
    ) -> None:
        """Add multiple matrix rows for one tile type.

        Parameters
        ----------
        tile_type : str
            Owner tile type.
        entries : Iterable[tuple[str, str, float]]
            ``(source, destination, delay)`` triplets.
        overwrite : bool
            If ``True``, deactivate current active matrix rows first.
        """
        if overwrite:
            for key in self.matrix_resources(tile_type):
                self.delete_resource(key)
        for source_name, destination_name, delay in entries:
            self.add_matrix_resource(
                tile_type,
                source_name,
                destination_name,
                delay=delay,
            )

    def delete_resource(self, resource_key: RoutingResourceKey) -> None:
        """Deactivate one tile resource and prune local dependents.

        Parameters
        ----------
        resource_key : RoutingResourceKey
            Resource to deactivate.
        """
        state = self._state_for_key(resource_key)
        if not state.active:
            return
        state.active = False
        if resource_key.kind is RoutingPipKind.EXTERNAL_WIRE:
            removed_wires = _declared_wires_for_external_resource(resource_key)
            self._deactivate_external_resource_dependencies(
                resource_key,
                removed_wires=removed_wires,
            )

    def disable_resource(self, resource_key: RoutingResourceKey) -> None:
        """Alias for :meth:`delete_resource`.

        Parameters
        ----------
        resource_key : RoutingResourceKey
            Resource to deactivate.
        """
        self.delete_resource(resource_key)

    def restore_resource(self, resource_key: RoutingResourceKey) -> None:
        """Reactivate a previously deactivated resource.

        Parameters
        ----------
        resource_key : RoutingResourceKey
            Resource to reactivate.
        """
        state = self._state_for_key(resource_key)
        state.active = True
        if resource_key.kind is RoutingPipKind.INTERNAL_MATRIX:
            self._validate_matrix_resource(resource_key)
        else:
            self._validate_tile(resource_key.tile_type)

    def enable_resource(self, resource_key: RoutingResourceKey) -> None:
        """Alias for :meth:`restore_resource`.

        Parameters
        ----------
        resource_key : RoutingResourceKey
            Resource to reactivate.
        """
        self.restore_resource(resource_key)

    def resize_external_resource(
        self,
        resource_key: RoutingResourceKey,
        new_wire_count: int,
    ) -> None:
        """Resize one external resource without materializing concrete PIPs.

        Parameters
        ----------
        resource_key : RoutingResourceKey
            Active external resource to resize.
        new_wire_count : int
            New wire count.  ``0`` deactivates the resource.

        Raises
        ------
        ValueError
            If the key is not an active external resource or count is negative.
        """
        if resource_key.kind is not RoutingPipKind.EXTERNAL_WIRE:
            raise ValueError(f"only external resources can be resized: {resource_key}")
        if resource_key.wire_count is None:
            raise ValueError(f"external resource has no wire count: {resource_key}")
        if new_wire_count < 0:
            raise ValueError(f"wire count must be non-negative: {new_wire_count}")
        state = self._state_for_key(resource_key)
        if not state.active:
            raise ValueError(f"cannot resize inactive resource: {resource_key}")

        old_wires = _declared_wires_for_external_resource(resource_key)
        state.active = False
        if new_wire_count == 0:
            new_wires: frozenset[str] = frozenset()
        else:
            new_key = replace(resource_key, wire_count=new_wire_count)
            new_state = self._external_by_tile[resource_key.tile_type].get(new_key)
            if new_state is None:
                new_state = _ExternalResourceState(key=new_key, delay=state.delay)
                self._external_by_tile[resource_key.tile_type][new_key] = new_state
                self._external_lookup[_external_lookup_key(new_key)] = new_key
            new_state.active = True
            new_state.delay = state.delay
            new_wires = _declared_wires_for_external_resource(new_key)

        self._deactivate_dangling_matrix_resources(
            resource_key.tile_type,
            candidate_wires=old_wires - new_wires,
        )

    def resource_keys(
        self,
        *,
        active_only: bool = True,
    ) -> tuple[RoutingResourceKey, ...]:
        """Return resource keys in tile-local insertion order.

        Parameters
        ----------
        active_only : bool
            If ``True``, return only active keys.

        Returns
        -------
        tuple[RoutingResourceKey, ...]
            Resource keys.
        """
        keys: list[RoutingResourceKey] = []
        for tile_type in self.tile_types():
            keys.extend(self.external_resources(tile_type, active_only=active_only))
            keys.extend(self.matrix_resources(tile_type, active_only=active_only))
        return tuple(keys)

    def external_resource_key(
        self,
        tile_type: str,
        direction: Direction,
        source_name: str,
        x_offset: int,
        y_offset: int,
        destination_name: str,
        wire_count: int | None = None,
        *,
        active_only: bool = True,
    ) -> RoutingResourceKey:
        """Return a unique external resource key from tile-local metadata.

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
        wire_count : int | None
            Optional wire count.  If provided, an exact dictionary lookup is used.
        active_only : bool
            If ``True``, inactive resources are ignored.

        Returns
        -------
        RoutingResourceKey
            Matching resource key.

        Raises
        ------
        KeyError
            If no resource matches.
        ValueError
            If ``wire_count`` is omitted and the lookup is ambiguous.
        """
        self._require_tile_type(tile_type)
        if wire_count is not None:
            lookup_key = (
                tile_type,
                direction,
                source_name,
                x_offset,
                y_offset,
                destination_name,
                wire_count,
            )
            key = self._external_lookup.get(lookup_key)
            if key is None:
                raise KeyError(
                    "external resource not found: "
                    f"{tile_type} {direction.value},{source_name},{x_offset},"
                    f"{y_offset},{destination_name},{wire_count}"
                )
            state = self._external_by_tile[tile_type][key]
            if active_only and not state.active:
                raise KeyError(f"external resource is inactive: {key}")
            return key

        matches = [
            state.key
            for state in self._external_by_tile.get(tile_type, {}).values()
            if (state.active or not active_only)
            and state.key.direction is direction
            and state.key.source_name == source_name
            and state.key.x_offset == x_offset
            and state.key.y_offset == y_offset
            and state.key.destination_name == destination_name
        ]
        if not matches:
            raise KeyError(
                "external resource not found: "
                f"{tile_type} {direction.value},{source_name},{x_offset},"
                f"{y_offset},{destination_name}"
            )
        if len(matches) > 1:
            raise ValueError(
                f"external resource lookup is ambiguous; provide wire_count: {matches}"
            )
        return matches[0]

    def matrix_resource_key(
        self,
        tile_type: str,
        source_name: str,
        destination_name: str,
        *,
        active_only: bool = True,
    ) -> RoutingResourceKey:
        """Return a matrix resource key from the tile-local pair index.

        Parameters
        ----------
        tile_type : str
            Owner tile type.
        source_name : str
            Matrix source wire.
        destination_name : str
            Matrix destination wire.
        active_only : bool
            If ``True``, inactive resources are ignored.

        Returns
        -------
        RoutingResourceKey
            Matching resource key.

        Raises
        ------
        KeyError
            If no matching resource exists.
        """
        self._require_tile_type(tile_type)
        lookup_key = (tile_type, source_name, destination_name)
        key = self._matrix_pair_lookup.get(lookup_key)
        if key is None:
            raise KeyError(
                "matrix resource not found: "
                f"{tile_type} {source_name},{destination_name}"
            )
        state = self._matrix_by_tile[tile_type][key]
        if active_only and not state.active:
            raise KeyError(f"matrix resource is inactive: {key}")
        return key

    def external_resources(
        self,
        tile_type: str | None = None,
        *,
        active_only: bool = True,
    ) -> list[RoutingResourceKey]:
        """Return external resources using tile-local indexes.

        Parameters
        ----------
        tile_type : str | None
            Optional tile type.
        active_only : bool
            If ``True``, return only active resources.

        Returns
        -------
        list[RoutingResourceKey]
            External resource keys.
        """
        tile_types = self.tile_types() if tile_type is None else (tile_type,)
        result: list[RoutingResourceKey] = []
        for selected in tile_types:
            self._require_tile_type(selected)
            result.extend(
                state.key
                for state in self._external_by_tile.get(selected, {}).values()
                if state.active or not active_only
            )
        return result

    def matrix_resources(
        self,
        tile_type: str | None = None,
        *,
        active_only: bool = True,
    ) -> list[RoutingResourceKey]:
        """Return matrix resources using tile-local indexes.

        Parameters
        ----------
        tile_type : str | None
            Optional tile type.
        active_only : bool
            If ``True``, return only active rows.

        Returns
        -------
        list[RoutingResourceKey]
            Matrix resource keys.
        """
        tile_types = self.tile_types() if tile_type is None else (tile_type,)
        result: list[RoutingResourceKey] = []
        for selected in tile_types:
            self._require_tile_type(selected)
            result.extend(
                state.key
                for state in self._matrix_by_tile.get(selected, {}).values()
                if state.active or not active_only
            )
        return result

    def matrix_sources(self, tile_type: str) -> list[str]:
        """Return matrix source candidate wires for one tile type.

        Parameters
        ----------
        tile_type : str
            Tile type to inspect.

        Returns
        -------
        list[str]
            Sorted candidate wires.
        """
        self._require_tile_type(tile_type)
        return sorted(self._available_matrix_wires(tile_type))

    def matrix_sinks(self, tile_type: str) -> list[str]:
        """Return matrix sink candidate wires for one tile type.

        Parameters
        ----------
        tile_type : str
            Tile type to inspect.

        Returns
        -------
        list[str]
            Sorted candidate wires.
        """
        return self.matrix_sources(tile_type)

    def switch_matrix(self, tile_type: str) -> RoutingSwitchMatrix:
        """Return a tile-local switch matrix with active delays.

        Rows and columns are built from all tracked matrix resources for the tile
        type, including inactive resources. Inactive resources are represented by
        ``0.0`` cells, while active resources store their delay.

        Parameters
        ----------
        tile_type : str
            Tile type to inspect.

        Returns
        -------
        RoutingSwitchMatrix
            Matrix view of the tile-type switch matrix.
        """
        self._require_tile_type(tile_type)
        states = list(self._matrix_by_tile.get(tile_type, {}).values())
        rows = list(dict.fromkeys(state.key.source_name for state in states))
        columns = list(dict.fromkeys(state.key.destination_name for state in states))
        row_index = {row: index for index, row in enumerate(rows)}
        column_index = {column: index for index, column in enumerate(columns)}
        matrix = [[0.0 for _column in columns] for _row in rows]

        for state in states:
            if not state.active:
                continue
            matrix[row_index[state.key.source_name]][
                column_index[state.key.destination_name]
            ] = float(state.delay)

        return RoutingSwitchMatrix(
            tile_type=tile_type,
            columns=columns,
            rows=rows,
            matrix=matrix,
        )

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
            Matrix column labels. These are FABulous ``.list`` right-hand side
            wires and nextpnr source endpoint wires.
        rows : list[str]
            Matrix row labels. These are FABulous ``.list`` left-hand side wires
            and nextpnr destination endpoint wires.
        matrix : list[list[float]]
            Delay matrix indexed as ``matrix[row_index][column_index]``.
            ``0.0`` disables a PIP; positive values add or restore a PIP with
            that delay.

        Raises
        ------
        ValueError
            If dimensions are inconsistent or any delay is negative.
        """
        self._require_tile_type(tile_type)
        if len(set(columns)) != len(columns):
            raise ValueError("switch matrix columns must be unique")
        if len(set(rows)) != len(rows):
            raise ValueError("switch matrix rows must be unique")
        if len(matrix) != len(rows):
            raise ValueError(
                "switch matrix row count does not match rows: "
                f"{len(matrix)} != {len(rows)}"
            )
        matrix_path = self.tile_model(tile_type).matrix_path
        available_wires = self._available_matrix_wires(tile_type)
        new_states: dict[RoutingResourceKey, _MatrixResourceState] = {}
        new_pair_lookup: dict[tuple[str, str, str], RoutingResourceKey] = {}
        new_by_wire: dict[tuple[str, str], dict[RoutingResourceKey, None]] = (
            defaultdict(dict)
        )
        if rows and columns:
            first_row = rows[0]
            first_column = columns[0]
            for source_name in rows:
                key = RoutingResourceKey(
                    tile_type=tile_type,
                    kind=RoutingPipKind.INTERNAL_MATRIX,
                    source_name=source_name,
                    destination_name=first_column,
                    matrix_path=matrix_path,
                )
                new_states[key] = _MatrixResourceState(
                    key=key,
                    delay=0.0,
                    active=False,
                )
                new_pair_lookup[(tile_type, source_name, first_column)] = key
                new_by_wire[(tile_type, source_name)][key] = None
                new_by_wire[(tile_type, first_column)][key] = None
            for destination_name in columns:
                key = RoutingResourceKey(
                    tile_type=tile_type,
                    kind=RoutingPipKind.INTERNAL_MATRIX,
                    source_name=first_row,
                    destination_name=destination_name,
                    matrix_path=matrix_path,
                )
                new_states[key] = _MatrixResourceState(
                    key=key,
                    delay=0.0,
                    active=False,
                )
                new_pair_lookup[(tile_type, first_row, destination_name)] = key
                new_by_wire[(tile_type, first_row)][key] = None
                new_by_wire[(tile_type, destination_name)][key] = None

        for row_index, source_name in enumerate(rows):
            row = matrix[row_index]
            if len(row) != len(columns):
                raise ValueError(
                    "switch matrix column count does not match columns at row "
                    f"{row_index}: {len(row)} != {len(columns)}"
                )
            for column_index, destination_name in enumerate(columns):
                delay = float(row[column_index])
                if delay < 0:
                    raise ValueError(
                        "switch matrix delays must be non-negative at "
                        f"row {row_index}, column {column_index}: "
                        f"{row[column_index]}"
                    )
                if delay == 0.0:
                    continue
                key = RoutingResourceKey(
                    tile_type=tile_type,
                    kind=RoutingPipKind.INTERNAL_MATRIX,
                    source_name=source_name,
                    destination_name=destination_name,
                    matrix_path=matrix_path,
                )
                if delay != 0.0 and (
                    source_name not in available_wires
                    or destination_name not in available_wires
                ):
                    raise ValueError(
                        f"active matrix resource references missing tile wire: {key}"
                    )
                new_states[key] = _MatrixResourceState(
                    key=key,
                    delay=delay,
                    active=delay != 0.0,
                )
                new_pair_lookup[(tile_type, source_name, destination_name)] = key
                new_by_wire[(tile_type, source_name)][key] = None
                new_by_wire[(tile_type, destination_name)][key] = None

        old_pair_lookup_keys = [
            lookup_key
            for lookup_key in self._matrix_pair_lookup
            if lookup_key[0] == tile_type
        ]
        old_wire_keys = [
            wire_key for wire_key in self._matrix_by_wire if wire_key[0] == tile_type
        ]

        self._matrix_by_tile[tile_type] = new_states
        for lookup_key in old_pair_lookup_keys:
            self._matrix_pair_lookup.pop(lookup_key, None)
        self._matrix_pair_lookup.update(new_pair_lookup)
        for wire_key in old_wire_keys:
            self._matrix_by_wire.pop(wire_key, None)
        for wire_key, keys in new_by_wire.items():
            self._matrix_by_wire[wire_key] = keys

    def by_resource_key(
        self,
        resource_key: RoutingResourceKey,
        *,
        active_only: bool = True,
    ) -> tuple[RoutingPip, ...]:
        """Return concrete PIPs generated by one resource.

        Parameters
        ----------
        resource_key : RoutingResourceKey
            Resource to materialize.
        active_only : bool
            If ``True``, inactive resources return no PIPs.

        Returns
        -------
        tuple[RoutingPip, ...]
            Concrete PIPs.
        """
        state = self._state_for_key(resource_key)
        if active_only and not state.active:
            return ()
        return tuple(self._iter_resource_pips(resource_key, state.delay))

    def pips(self) -> tuple[RoutingPip, ...]:
        """Return all concrete PIPs materialized lazily.

        Returns
        -------
        tuple[RoutingPip, ...]
            Active and inactive concrete PIPs.
        """
        return tuple(self.iter_pips(active_only=False))

    def active_pips(self) -> tuple[RoutingPip, ...]:
        """Return active concrete PIPs materialized lazily.

        Returns
        -------
        tuple[RoutingPip, ...]
            Active concrete PIPs.
        """
        return tuple(self.iter_pips(active_only=True))

    def disabled_pips(self) -> tuple[RoutingPip, ...]:
        """Return inactive concrete PIPs materialized lazily.

        Returns
        -------
        tuple[RoutingPip, ...]
            Inactive concrete PIPs.
        """
        return tuple(self.iter_pips(active_only=False, inactive_only=True))

    def iter_pips(
        self,
        *,
        active_only: bool = True,
        inactive_only: bool = False,
    ) -> Iterator[RoutingPip]:
        """Yield concrete PIPs generated from current tile resources.

        Parameters
        ----------
        active_only : bool
            If ``True``, skip inactive resources.
        inactive_only : bool
            If ``True``, yield only inactive resources.

        Yields
        ------
        RoutingPip
            Concrete PIP with a render-local id.
        """
        pip_id = 0
        for y in range(self.rows):
            for x in range(self.columns):
                tile_type = self.tile_types_by_xy.get((x, y))
                if tile_type is None:
                    continue
                for state in self._matrix_by_tile.get(tile_type, {}).values():
                    if not _state_selected(state.active, active_only, inactive_only):
                        continue
                    yield from self._iter_matrix_resource_pips(
                        state.key,
                        state.delay,
                        x,
                        y,
                        pip_id_start=pip_id,
                    )
                    pip_id += 1
                for state in self._external_by_tile.get(tile_type, {}).values():
                    if not _state_selected(state.active, active_only, inactive_only):
                        continue
                    for pip in self._iter_external_resource_pips(
                        state.key,
                        state.delay,
                        x,
                        y,
                        pip_id_start=pip_id,
                    ):
                        yield pip
                        pip_id += 1

    def render_pips_txt(self) -> str:
        """Render active PIPs in nextpnr ``pips.txt`` format.

        Returns
        -------
        str
            Rendered routing model.
        """
        lines: list[str] = []
        for y in range(self.rows):
            for x in range(self.columns):
                tile_type = self.tile_types_by_xy.get((x, y))
                if tile_type is None:
                    continue
                lines.append(f"#Tile-internal pips on tile X{x}Y{y}:")
                for state in self._matrix_by_tile.get(tile_type, {}).values():
                    if not state.active:
                        continue
                    for pip in self._iter_matrix_resource_pips(
                        state.key,
                        state.delay,
                        x,
                        y,
                    ):
                        lines.append(pip.render())
                lines.append(f"#Tile-external pips on tile X{x}Y{y}:")
                for state in self._external_by_tile.get(tile_type, {}).values():
                    if not state.active:
                        continue
                    for pip in self._iter_external_resource_pips(
                        state.key,
                        state.delay,
                        x,
                        y,
                    ):
                        lines.append(pip.render())
        return "\n".join(lines)

    def stats(self) -> RoutingGraphStats:
        """Return concrete graph statistics by lazy materialization.

        Returns
        -------
        RoutingGraphStats
            Current concrete graph counts.
        """
        active = self.active_pips()
        inactive = self.disabled_pips()
        return RoutingGraphStats(
            total_pips=len(active) + len(inactive),
            active_pips=len(active),
            disabled_pips=len(inactive),
            internal_pips=sum(
                1 for pip in active if pip.kind is RoutingPipKind.INTERNAL_MATRIX
            ),
            external_pips=sum(
                1 for pip in active if pip.kind is RoutingPipKind.EXTERNAL_WIRE
            ),
            tile_types=len({pip.tile_type for pip in active}),
            resource_keys=len({pip.resource_key for pip in active}),
        )

    def get_config_bits(
        self,
        tile_type: str | None = None,
    ) -> RoutingConfigBits | dict[str, RoutingConfigBits]:
        """Return current tile-local configuration-bit counts.

        Matrix bits are recomputed from active switch-matrix resources using the
        same mux-size rule as FABulous CSV parsing.  BEL bits come from the
        preserved tile metadata and therefore stay fixed unless the tile model is
        rebuilt.

        Parameters
        ----------
        tile_type : str | None
            Optional tile type.  If omitted, counts are returned for every tile
            type.

        Returns
        -------
        RoutingConfigBits | dict[str, RoutingConfigBits]
            One tile summary, or summaries keyed by tile type.
        """
        if tile_type is not None:
            return self._config_bits_for_tile(tile_type)
        return {
            selected: self._config_bits_for_tile(selected)
            for selected in self.tile_types()
        }

    def get_resource_counts(
        self,
        tile_type: str | None = None,
    ) -> RoutingResourceCounts | dict[str, RoutingResourceCounts]:
        """Return tile-local routing resource counts without materializing PIPs.

        Parameters
        ----------
        tile_type : str | None
            Optional tile type.  If omitted, counts are returned for every tile
            type.

        Returns
        -------
        RoutingResourceCounts | dict[str, RoutingResourceCounts]
            One tile summary, or summaries keyed by tile type.
        """
        if tile_type is not None:
            return self._resource_counts_for_tile(tile_type)
        return {
            selected: self._resource_counts_for_tile(selected)
            for selected in self.tile_types()
        }

    def validate(self) -> None:
        """Validate every tile-local resource."""
        for tile_type in self.tile_types():
            self._validate_tile(tile_type)

    def _config_bits_for_tile(self, tile_type: str) -> RoutingConfigBits:
        """Return current configuration-bit counts for one tile type.

        Parameters
        ----------
        tile_type : str
            Tile type to inspect.

        Returns
        -------
        RoutingConfigBits
            Current tile-local bit counts.
        """
        tile_model = self.tile_model(tile_type)
        fanin_by_source: dict[str, int] = defaultdict(int)
        for state in self._matrix_by_tile.get(tile_type, {}).values():
            if state.active:
                fanin_by_source[state.key.source_name] += 1
        matrix_config_bits = sum(
            (fanin - 1).bit_length() for fanin in fanin_by_source.values() if fanin >= 2
        )
        fixed_config_bits = sum(bel.config_bits for bel in tile_model.bels)
        return RoutingConfigBits(
            tile_type=tile_type,
            matrix_config_bits=matrix_config_bits,
            fixed_config_bits=fixed_config_bits,
            total_config_bits=matrix_config_bits + fixed_config_bits,
        )

    def _resource_counts_for_tile(self, tile_type: str) -> RoutingResourceCounts:
        """Return active and disabled resource counts for one tile type.

        Parameters
        ----------
        tile_type : str
            Tile type to inspect.

        Returns
        -------
        RoutingResourceCounts
            Tile-local resource counts.
        """
        self._require_tile_type(tile_type)
        external_active = 0
        external_disabled = 0
        for state in self._external_by_tile.get(tile_type, {}).values():
            if state.active:
                external_active += 1
            else:
                external_disabled += 1

        matrix_active = 0
        matrix_disabled = 0
        for state in self._matrix_by_tile.get(tile_type, {}).values():
            if state.active:
                matrix_active += 1
            else:
                matrix_disabled += 1

        total_active = external_active + matrix_active
        total_disabled = external_disabled + matrix_disabled
        return RoutingResourceCounts(
            tile_type=tile_type,
            external_active=external_active,
            external_disabled=external_disabled,
            matrix_active=matrix_active,
            matrix_disabled=matrix_disabled,
            total_active=total_active,
            total_disabled=total_disabled,
            total=total_active + total_disabled,
        )

    def _iter_resource_pips(
        self,
        resource_key: RoutingResourceKey,
        delay: float,
    ) -> Iterator[RoutingPip]:
        """Yield concrete PIPs for one resource over every owner tile.

        Parameters
        ----------
        resource_key : RoutingResourceKey
            Resource to materialize.
        delay : float
            PIP delay.

        Yields
        ------
        RoutingPip
            Concrete PIP.
        """
        pip_id = 0
        for x, y in self._tile_locations_by_type.get(resource_key.tile_type, ()):
            if resource_key.kind is RoutingPipKind.INTERNAL_MATRIX:
                yield from self._iter_matrix_resource_pips(
                    resource_key,
                    delay,
                    x,
                    y,
                    pip_id_start=pip_id,
                )
                pip_id += 1
            else:
                for pip in self._iter_external_resource_pips(
                    resource_key,
                    delay,
                    x,
                    y,
                    pip_id_start=pip_id,
                ):
                    yield pip
                    pip_id += 1

    def _iter_matrix_resource_pips(
        self,
        resource_key: RoutingResourceKey,
        delay: float,
        x: int,
        y: int,
        *,
        pip_id_start: int | None = None,
    ) -> Iterator[RoutingPip]:
        """Yield one concrete matrix PIP for an owner tile.

        Parameters
        ----------
        resource_key : RoutingResourceKey
            Matrix resource.
        delay : float
            PIP delay.
        x : int
            Owner X coordinate.
        y : int
            Owner Y coordinate.
        pip_id_start : int | None
            Optional render-local id.

        Yields
        ------
        RoutingPip
            Concrete matrix PIP.
        """
        yield RoutingPip(
            pip_id=pip_id_start,
            kind=RoutingPipKind.INTERNAL_MATRIX,
            source=RoutingEndpoint(x, y, resource_key.destination_name),
            destination=RoutingEndpoint(x, y, resource_key.source_name),
            delay=delay,
            name=f"{resource_key.destination_name}.{resource_key.source_name}",
            owner_tile=(x, y),
            tile_type=resource_key.tile_type,
            resource_key=resource_key,
            source_tile_type=resource_key.tile_type,
            destination_tile_type=resource_key.tile_type,
            matrix_path=resource_key.matrix_path,
        )

    def _iter_external_resource_pips(
        self,
        resource_key: RoutingResourceKey,
        delay: float,
        x: int,
        y: int,
        *,
        pip_id_start: int | None = None,
    ) -> Iterator[RoutingPip]:
        """Yield concrete external PIPs for one owner tile.

        Parameters
        ----------
        resource_key : RoutingResourceKey
            External resource.
        delay : float
            PIP delay.
        x : int
            Owner X coordinate.
        y : int
            Owner Y coordinate.
        pip_id_start : int | None
            Optional first render-local id.

        Yields
        ------
        RoutingPip
            Concrete external PIP.
        """
        pip_id = pip_id_start
        for source, x_offset, y_offset, destination in _external_wire_specs_for_key(
            resource_key,
            common_wire_pairs=self._common_wire_pairs(),
        ):
            endpoint = RoutingEndpoint(x + x_offset, y + y_offset, destination)
            if not self._endpoint_is_valid(endpoint):
                continue
            yield RoutingPip(
                pip_id=pip_id,
                kind=RoutingPipKind.EXTERNAL_WIRE,
                source=RoutingEndpoint(x, y, source),
                destination=endpoint,
                delay=delay,
                name=f"{source}.{destination}",
                owner_tile=(x, y),
                tile_type=resource_key.tile_type,
                resource_key=resource_key,
                source_tile_type=self.tile_types_by_xy.get((x, y)),
                destination_tile_type=self.tile_types_by_xy.get(endpoint.tile),
                emitted_x_offset=x_offset,
                emitted_y_offset=y_offset,
            )
            if pip_id is not None:
                pip_id += 1

    def _state_for_key(
        self,
        resource_key: RoutingResourceKey,
    ) -> _ExternalResourceState | _MatrixResourceState:
        """Return mutable state for a resource key.

        Parameters
        ----------
        resource_key : RoutingResourceKey
            Key to look up.

        Returns
        -------
        _ExternalResourceState | _MatrixResourceState
            Mutable state.
        """
        if resource_key.kind is RoutingPipKind.EXTERNAL_WIRE:
            return self._external_by_tile[resource_key.tile_type][resource_key]
        return self._matrix_by_tile[resource_key.tile_type][resource_key]

    def _validate_tile(self, tile_type: str) -> None:
        """Validate active matrix rows for one tile type.

        Parameters
        ----------
        tile_type : str
            Tile type to validate.
        """
        for state in self._matrix_by_tile.get(tile_type, {}).values():
            if state.active:
                self._validate_matrix_resource(state.key)

    def _validate_matrix_resource(self, resource_key: RoutingResourceKey) -> None:
        """Validate one active matrix resource against available tile wires.

        Parameters
        ----------
        resource_key : RoutingResourceKey
            Matrix key to validate.

        Raises
        ------
        ValueError
            If source or destination is unavailable.
        """
        available = self._available_matrix_wires(resource_key.tile_type)
        if (
            resource_key.source_name not in available
            or resource_key.destination_name not in available
        ):
            raise ValueError(
                f"active matrix resource references missing tile wire: {resource_key}"
            )

    def _available_matrix_wires(self, tile_type: str) -> set[str]:
        """Return matrix-visible wires for active resources of one tile type.

        Parameters
        ----------
        tile_type : str
            Tile type to inspect.

        Returns
        -------
        set[str]
            Available local wires.
        """
        wires = set(self._static_matrix_wires_by_tile_type.get(tile_type, ()))
        disabled_wires: set[str] = set()
        active_wires: set[str] = set()
        for state in self._external_by_tile.get(tile_type, {}).values():
            declared_wires = _declared_wires_for_external_resource(state.key)
            if state.active:
                active_wires.update(declared_wires)
            else:
                disabled_wires.update(declared_wires)
        return (wires - disabled_wires) | active_wires

    def _deactivate_external_resource_dependencies(
        self,
        resource_key: RoutingResourceKey,
        *,
        removed_wires: Iterable[str],
    ) -> None:
        """Deactivate resources made invalid by an external resource removal.

        Parameters
        ----------
        resource_key : RoutingResourceKey
            External resource that was just deactivated.
        removed_wires : Iterable[str]
            Local matrix wires declared by ``resource_key``.
        """
        self._deactivate_dangling_matrix_resources(
            resource_key.tile_type,
            candidate_wires=removed_wires,
        )
        if not _external_resource_provides_common_mapping(resource_key):
            return
        if self._has_active_common_mapping(resource_key.source_name):
            return

        for dependent_key in self._dependent_termination_resources(resource_key):
            dependent_state = self._state_for_key(dependent_key)
            if not dependent_state.active:
                continue
            dependent_state.active = False
            self._deactivate_dangling_matrix_resources(
                dependent_key.tile_type,
                candidate_wires=_declared_wires_for_external_resource(dependent_key),
            )

    def _has_active_common_mapping(self, source_name: str) -> bool:
        """Return whether any active external resource maps a source name.

        Parameters
        ----------
        source_name : str
            Source base name to inspect.

        Returns
        -------
        bool
            Whether an active non-``NULL`` destination resource exists.
        """
        return any(
            state.active
            and _external_resource_provides_common_mapping(state.key)
            and state.key.source_name == source_name
            for resources in self._external_by_tile.values()
            for state in resources.values()
        )

    def _dependent_termination_resources(
        self,
        resource_key: RoutingResourceKey,
    ) -> tuple[RoutingResourceKey, ...]:
        """Return active termination resources that depend on a mapping.

        Parameters
        ----------
        resource_key : RoutingResourceKey
            Disabled common-wire mapping resource.

        Returns
        -------
        tuple[RoutingResourceKey, ...]
            Active source-to-``NULL`` resources using the same source name.
        """
        dependents: list[RoutingResourceKey] = []
        for resources in self._external_by_tile.values():
            for state in resources.values():
                candidate = state.key
                if (
                    state.active
                    and candidate.source_name == resource_key.source_name
                    and candidate.destination_name == "NULL"
                ):
                    dependents.append(candidate)
        return tuple(dict.fromkeys(dependents))

    def _deactivate_dangling_matrix_resources(
        self,
        tile_type: str,
        *,
        candidate_wires: Iterable[str],
    ) -> None:
        """Deactivate active matrix rows touching now-unavailable wires.

        Parameters
        ----------
        tile_type : str
            Tile type to prune.
        candidate_wires : Iterable[str]
            Wires that may have become unavailable.
        """
        available = self._available_matrix_wires(tile_type)
        missing = set(candidate_wires) - available
        for wire in missing:
            for key in tuple(self._matrix_by_wire.get((tile_type, wire), {})):
                state = self._matrix_by_tile[tile_type].get(key)
                if state is not None and state.active:
                    state.active = False

    def _common_wire_pairs(self) -> dict[str, str]:
        """Return common source-to-destination wire mappings.

        Returns
        -------
        dict[str, str]
            Mapping from source base name to destination base name.
        """
        pairs: dict[str, str] = {}
        for tile in self._tile_models.values():
            for port in tile.ports:
                if port.source_name == "NULL" or port.destination_name == "NULL":
                    continue
                pairs.setdefault(port.source_name, port.destination_name)
        return pairs

    def _endpoint_is_valid(self, endpoint: RoutingEndpoint) -> bool:
        """Return whether an endpoint lies on a placed tile.

        Parameters
        ----------
        endpoint : RoutingEndpoint
            Endpoint to check.

        Returns
        -------
        bool
            Whether the endpoint is valid for concrete PIP emission.
        """
        return (
            0 <= endpoint.tile_x <= self.columns and 0 <= endpoint.tile_y <= self.rows
        )

    def _require_tile_type(self, tile_type: str) -> None:
        """Raise if a tile type is unknown.

        Parameters
        ----------
        tile_type : str
            Tile type to check.

        Raises
        ------
        KeyError
            If the tile type is unknown.
        """
        if tile_type not in self._tile_models:
            raise KeyError(tile_type)


def _state_selected(active: bool, active_only: bool, inactive_only: bool) -> bool:
    """Return whether a resource state should be emitted.

    Parameters
    ----------
    active : bool
        Resource activity.
    active_only : bool
        Whether only active resources are requested.
    inactive_only : bool
        Whether only inactive resources are requested.

    Returns
    -------
    bool
        Selection result.
    """
    if inactive_only:
        return not active
    if active_only:
        return active
    return True


def _matrix_pairs(
    tile: Tile,
    cache: dict[tuple[str, str], tuple[tuple[str, str], ...]],
) -> tuple[tuple[str, str], ...]:
    """Return parsed matrix pairs for a tile type.

    Parameters
    ----------
    tile : Tile
        Parsed tile.
    cache : dict[tuple[str, str], tuple[tuple[str, str], ...]]
        Matrix parse cache.

    Returns
    -------
    tuple[tuple[str, str], ...]
        ``(source, sink)`` pairs.

    Raises
    ------
    InvalidFileType
        If the matrix file type is unsupported.
    """
    key = (tile.name, str(tile.matrixDir))
    if key in cache:
        return cache[key]
    if tile.matrixDir.suffix == ".csv":
        pairs = tuple(
            (source, sink)
            for source, sinks in parseMatrix(tile.matrixDir, tile.name).items()
            for sink in sinks
        )
    elif tile.matrixDir.suffix == ".list":
        pairs = tuple(parseList(tile.matrixDir))
    else:
        raise InvalidFileType(f"File {tile.matrixDir} is not a .csv or .list file")
    cache[key] = pairs
    return pairs


def _external_wire_specs_for_key(
    resource_key: RoutingResourceKey,
    *,
    common_wire_pairs: dict[str, str],
) -> tuple[tuple[str, int, int, str], ...]:
    """Expand one external resource into concrete wire specs.

    Parameters
    ----------
    resource_key : RoutingResourceKey
        External key.
    common_wire_pairs : dict[str, str]
        NULL-termination wire mapping.

    Returns
    -------
    tuple[tuple[str, int, int, str], ...]
        ``(source, x_offset, y_offset, destination)`` specs.

    Raises
    ------
    ValueError
        If the resource lacks external metadata.
    """
    if resource_key.kind is not RoutingPipKind.EXTERNAL_WIRE:
        raise ValueError(f"not an external resource: {resource_key}")
    if resource_key.direction is None:
        raise ValueError(f"external resource has no direction: {resource_key}")
    if resource_key.wire_count is None:
        raise ValueError(f"external resource has no wire count: {resource_key}")

    source_name = resource_key.source_name
    destination_name = resource_key.destination_name
    wire_count = resource_key.wire_count
    x_offset = resource_key.x_offset
    y_offset = resource_key.y_offset
    specs: list[tuple[str, int, int, str]] = []

    if (
        abs(x_offset) <= 1
        and abs(y_offset) <= 1
        and source_name != "NULL"
        and destination_name != "NULL"
    ):
        specs.extend(
            (
                f"{source_name}{index}",
                x_offset,
                y_offset,
                f"{destination_name}{index}",
            )
            for index in range(wire_count)
        )
        return _dedupe_wire_specs(specs)

    if source_name != "NULL" and destination_name != "NULL":
        specs.extend(
            _long_wire_axis_specs(
                source_name=source_name,
                destination_name=destination_name,
                wire_count=wire_count,
                axis_offset=x_offset,
                other_offset=y_offset,
                x_axis=True,
            )
        )
        specs.extend(
            _long_wire_axis_specs(
                source_name=source_name,
                destination_name=destination_name,
                wire_count=wire_count,
                axis_offset=y_offset,
                other_offset=x_offset,
                x_axis=False,
            )
        )
        return _dedupe_wire_specs(specs)

    if source_name != "NULL" and destination_name == "NULL":
        real_destination = common_wire_pairs.get(source_name, source_name)
        specs.extend(
            _termination_axis_specs(
                source_name=source_name,
                destination_name=real_destination,
                wire_count=wire_count,
                axis_offset=x_offset,
                other_offset=y_offset,
                x_axis=True,
            )
        )
        specs.extend(
            _termination_axis_specs(
                source_name=source_name,
                destination_name=real_destination,
                wire_count=wire_count,
                axis_offset=y_offset,
                other_offset=x_offset,
                x_axis=False,
            )
        )
        return _dedupe_wire_specs(specs)

    return ()


def _external_resource_provides_common_mapping(
    resource_key: RoutingResourceKey,
) -> bool:
    """Return whether an external resource defines a common wire pair.

    Parameters
    ----------
    resource_key : RoutingResourceKey
        Resource key to inspect.

    Returns
    -------
    bool
        ``True`` for non-``NULL`` source and destination external resources.
    """
    return (
        resource_key.kind is RoutingPipKind.EXTERNAL_WIRE
        and resource_key.source_name != "NULL"
        and resource_key.destination_name != "NULL"
    )


def _long_wire_axis_specs(
    *,
    source_name: str,
    destination_name: str,
    wire_count: int,
    axis_offset: int,
    other_offset: int,
    x_axis: bool,
) -> list[tuple[str, int, int, str]]:
    """Return concrete long-wire specs along one axis.

    Parameters
    ----------
    source_name : str
        Source base name.
    destination_name : str
        Destination base name.
    wire_count : int
        Wire count.
    axis_offset : int
        Offset along selected axis.
    other_offset : int
        Offset along other axis.
    x_axis : bool
        Whether selected axis is X.

    Returns
    -------
    list[tuple[str, int, int, str]]
        Concrete specs.
    """
    if axis_offset == 0:
        return []
    step = min(max(axis_offset, -1), 1)
    specs: list[tuple[str, int, int, str]] = []
    for index in range(wire_count * abs(axis_offset)):
        if index < wire_count:
            cascaded_index = index + wire_count * (abs(axis_offset) - 1)
        else:
            cascaded_index = index - wire_count
            specs.append((f"{destination_name}{index}", 0, 0, f"{source_name}{index}"))
        if x_axis:
            specs.append(
                (
                    f"{source_name}{index}",
                    step,
                    other_offset,
                    f"{destination_name}{cascaded_index}",
                )
            )
        else:
            specs.append(
                (
                    f"{source_name}{index}",
                    other_offset,
                    step,
                    f"{destination_name}{cascaded_index}",
                )
            )
    return specs


def _termination_axis_specs(
    *,
    source_name: str,
    destination_name: str,
    wire_count: int,
    axis_offset: int,
    other_offset: int,
    x_axis: bool,
) -> list[tuple[str, int, int, str]]:
    """Return concrete termination specs along one axis.

    Parameters
    ----------
    source_name : str
        Source base name.
    destination_name : str
        Destination base name.
    wire_count : int
        Wire count.
    axis_offset : int
        Offset along selected axis.
    other_offset : int
        Offset along other axis.
    x_axis : bool
        Whether selected axis is X.

    Returns
    -------
    list[tuple[str, int, int, str]]
        Concrete specs.
    """
    if axis_offset == 0:
        return []
    step = min(max(axis_offset, -1), 1)
    specs: list[tuple[str, int, int, str]] = []
    for index in range(wire_count * abs(axis_offset)):
        if x_axis:
            specs.append(
                (
                    f"{source_name}{index}",
                    step,
                    other_offset,
                    f"{destination_name}{index}",
                )
            )
        else:
            specs.append(
                (
                    f"{source_name}{index}",
                    other_offset,
                    step,
                    f"{destination_name}{index}",
                )
            )
    return specs


def _dedupe_wire_specs(
    specs: Iterable[tuple[str, int, int, str]],
) -> tuple[tuple[str, int, int, str], ...]:
    """Deduplicate concrete specs while preserving first-seen order.

    Parameters
    ----------
    specs : Iterable[tuple[str, int, int, str]]
        Candidate specs.

    Returns
    -------
    tuple[tuple[str, int, int, str], ...]
        Deduplicated specs.
    """
    by_pair: dict[tuple[str, str], tuple[str, int, int, str]] = {}
    for spec in specs:
        source, _x_offset, _y_offset, destination = spec
        by_pair.setdefault((source, destination), spec)
    return tuple(by_pair.values())


def _tile_type_map(fabric: Fabric) -> dict[tuple[int, int], str]:
    """Build placed tile-type lookup.

    Parameters
    ----------
    fabric : Fabric
        Parsed fabric.

    Returns
    -------
    dict[tuple[int, int], str]
        Coordinate to tile type.
    """
    return {
        (x, y): tile.name
        for y, row in enumerate(fabric.tile)
        for x, tile in enumerate(row)
        if tile is not None
    }


def _tile_locations_by_type(
    tile_types_by_xy: dict[tuple[int, int], str],
) -> dict[str, tuple[tuple[int, int], ...]]:
    """Build tile-type to coordinates index.

    Parameters
    ----------
    tile_types_by_xy : dict[tuple[int, int], str]
        Coordinate to tile type.

    Returns
    -------
    dict[str, tuple[tuple[int, int], ...]]
        Coordinates by tile type.
    """
    locations: defaultdict[str, list[tuple[int, int]]] = defaultdict(list)
    for location, tile_type in sorted(
        tile_types_by_xy.items(),
        key=lambda item: item[0][::-1],
    ):
        locations[tile_type].append(location)
    return {tile_type: tuple(values) for tile_type, values in locations.items()}


def _first_tiles_by_type(fabric: Fabric) -> dict[str, Tile]:
    """Return first parsed tile object for every tile type.

    Parameters
    ----------
    fabric : Fabric
        Parsed fabric.

    Returns
    -------
    dict[str, Tile]
        Tile objects keyed by tile type.
    """
    tiles: dict[str, Tile] = {}
    for row in fabric.tile:
        for tile in row:
            if tile is not None:
                tiles.setdefault(tile.name, tile)
    return tiles


def _tile_definitions_by_type(fabric: Fabric) -> dict[str, Tile]:
    """Return placed and standalone tile definitions in stable order.

    Parameters
    ----------
    fabric : Fabric
        Parsed fabric.

    Returns
    -------
    dict[str, Tile]
        Tile objects keyed by tile type.  Placed grid tile types keep their
        first-seen order; declared but unplaced tile types are appended.
    """
    tiles = _first_tiles_by_type(fabric)
    for tile_type, tile in getattr(fabric, "tileDic", {}).items():
        tiles.setdefault(tile_type, tile)
    for tile_type, tile in getattr(fabric, "unusedTileDic", {}).items():
        tiles.setdefault(tile_type, tile)
    return tiles


def _tile_models(fabric: Fabric) -> dict[str, RoutingTileModel]:
    """Build stable tile metadata models.

    Parameters
    ----------
    fabric : Fabric
        Parsed fabric.

    Returns
    -------
    dict[str, RoutingTileModel]
        Models keyed by tile type.
    """
    return {
        tile_type: _tile_model(tile)
        for tile_type, tile in _tile_definitions_by_type(fabric).items()
    }


def _tile_model(tile: Tile) -> RoutingTileModel:
    """Convert one FABulous tile object to metadata.

    Parameters
    ----------
    tile : Tile
        Parsed tile.

    Returns
    -------
    RoutingTileModel
        Stable tile metadata.
    """
    tile_csv_path = tile.tileDir
    tile_dir = tile_csv_path.parent if tile_csv_path.suffix else tile_csv_path
    return RoutingTileModel(
        tile_type=tile.name,
        tile_csv_path=tile_csv_path,
        tile_dir=tile_dir,
        matrix_path=tile.matrixDir,
        matrix_config_bits=tile.matrixConfigBits,
        with_user_clk=tile.withUserCLK,
        ports=tuple(_port_model(port) for port in tile.portsInfo),
        bels=tuple(_bel_model(bel) for bel in tile.bels),
        gen_ios=tuple(_gen_io_model(gen_io) for gen_io in tile.gen_ios),
    )


def _port_model(port: Port) -> RoutingTilePortModel:
    """Convert one FABulous port object to metadata.

    Parameters
    ----------
    port : Port
        Parsed port.

    Returns
    -------
    RoutingTilePortModel
        Port metadata.
    """
    return RoutingTilePortModel(
        direction=port.wireDirection,
        source_name=port.sourceName,
        x_offset=port.xOffset,
        y_offset=port.yOffset,
        destination_name=port.destinationName,
        wire_count=port.wireCount,
        name=port.name,
        io=port.inOut,
        side=port.sideOfTile,
    )


def _bel_model(bel: Bel) -> RoutingTileBelModel:
    """Convert one FABulous BEL object to metadata.

    Parameters
    ----------
    bel : Bel
        Parsed BEL.

    Returns
    -------
    RoutingTileBelModel
        BEL metadata.
    """
    return RoutingTileBelModel(
        source_path=bel.src,
        prefix=bel.prefix,
        name=bel.name,
        module_name=bel.module_name,
        inputs=tuple(bel.inputs),
        outputs=tuple(bel.outputs),
        external_inputs=tuple(bel.externalInput),
        external_outputs=tuple(bel.externalOutput),
        config_bits=bel.configBit,
        feature_names=tuple(sorted(bel.belFeatureMap)),
        with_user_clk=bel.withUserCLK,
    )


def _gen_io_model(gen_io: Gen_IO) -> RoutingTileGenIOModel:
    """Convert one FABulous GEN_IO object to metadata.

    Parameters
    ----------
    gen_io : Gen_IO
        Parsed GEN_IO.

    Returns
    -------
    RoutingTileGenIOModel
        GEN_IO metadata.
    """
    return RoutingTileGenIOModel(
        prefix=gen_io.prefix,
        pins=gen_io.pins,
        io=gen_io.IO,
        config_bits=gen_io.configBit,
        config_access=gen_io.configAccess,
        inverted=gen_io.inverted,
        clocked=gen_io.clocked,
        clocked_comb=gen_io.clockedComb,
        clocked_mux=gen_io.clockedMux,
    )


def _static_matrix_wires_by_tile_type(
    tile_models: dict[str, RoutingTileModel],
) -> dict[str, frozenset[str]]:
    """Return wires available without active external resources.

    Parameters
    ----------
    tile_models : dict[str, RoutingTileModel]
        Tile metadata.

    Returns
    -------
    dict[str, frozenset[str]]
        Static matrix wires by tile type.
    """
    constants = {"GND", "GND0", "VCC", "VCC0"}
    static_wires: dict[str, frozenset[str]] = {}
    for tile_type, tile_model in tile_models.items():
        wires = set(constants)
        for bel in tile_model.bels:
            wires.update(bel.inputs)
            wires.update(bel.outputs)
            wires.update(bel.external_outputs)
        static_wires[tile_type] = frozenset(wires)
    return static_wires


def _declared_wires_for_external_resource(
    resource_key: RoutingResourceKey,
) -> frozenset[str]:
    """Return matrix-visible wires declared by an external resource.

    Parameters
    ----------
    resource_key : RoutingResourceKey
        External resource key.

    Returns
    -------
    frozenset[str]
        Declared local wires.
    """
    if resource_key.kind is not RoutingPipKind.EXTERNAL_WIRE:
        return frozenset()
    if resource_key.wire_count is None:
        return frozenset(
            wire
            for wire in (resource_key.source_name, resource_key.destination_name)
            if wire != "NULL"
        )

    wire_count = resource_key.wire_count
    if resource_key.direction is not Direction.JUMP and (
        resource_key.source_name == "NULL" or resource_key.destination_name == "NULL"
    ):
        wire_count *= abs(resource_key.x_offset) + abs(resource_key.y_offset)

    wires: set[str] = set()
    for index in range(wire_count):
        if resource_key.source_name != "NULL":
            wires.add(f"{resource_key.source_name}{index}")
        if resource_key.destination_name != "NULL":
            wires.add(f"{resource_key.destination_name}{index}")
    return frozenset(wires)


def _external_lookup_key(
    key: RoutingResourceKey,
) -> tuple[str, Direction, str, int, int, str, int]:
    """Return exact lookup tuple for one external key.

    Parameters
    ----------
    key : RoutingResourceKey
        External resource key.

    Returns
    -------
    tuple[str, Direction, str, int, int, str, int]
        Lookup tuple.

    Raises
    ------
    ValueError
        If required external metadata is missing.
    """
    if key.direction is None or key.wire_count is None:
        raise ValueError(f"external resource lacks lookup metadata: {key}")
    return (
        key.tile_type,
        key.direction,
        key.source_name,
        key.x_offset,
        key.y_offset,
        key.destination_name,
        key.wire_count,
    )

"""Small FABulous-oriented FASM parser.

The parser intentionally keeps only real FASM features.  Blank lines, comments, and
annotations are ignored.  When a FabGraph-like object is provided, each feature is
annotated with tile and PIP metadata from the graph.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, replace
from enum import StrEnum
from typing import TYPE_CHECKING, Protocol

from fabulous.fabric_cad.fabxplore.pnr.fab_graph.core.models import (
    RoutingPipKind,
    RoutingSwitchMatrix,
)

if TYPE_CHECKING:
    from collections.abc import Callable, Iterable

    from fabulous.fabric_cad.fabxplore.pnr.fab_graph.core.models import (
        RoutingPip,
        RoutingResourceKey,
    )


_FEATURE_RE = re.compile(
    r"^(?P<feature>[A-Za-z][A-Za-z0-9_]*(?:\.[A-Za-z][A-Za-z0-9_]*)*)"
    r"(?P<address>\[[0-9_]+(?::[0-9_]+)?\])?$"
)
_TILE_RE = re.compile(r"^X(?P<x>\d+)Y(?P<y>\d+)$")


class FabulousFasmFeatureType(StrEnum):
    """Classify a parsed FABulous FASM feature."""

    ROUTING = "routing"
    CONFIG = "config"


class FabulousFasmParseError(ValueError):
    """Raised when a non-empty FASM feature line cannot be parsed."""


class FabulousFasmResolveError(ValueError):
    """Raised when graph annotation cannot resolve a parsed feature."""


class FabulousFasmGraph(Protocol):
    """Graph API used to annotate parsed FASM features."""

    def iter_active_pips(
        self,
        where: Callable[[RoutingPip], bool] | None = None,
    ) -> Iterable[RoutingPip]:
        """Yield active concrete graph PIPs."""

    def tile_type_at(self, x: int, y: int) -> str | None:
        """Return the placed tile type at one coordinate."""


@dataclass(frozen=True, slots=True)
class FabulousFasmFeature:
    """One parsed FABulous FASM feature.

    Attributes
    ----------
    raw : str
        Original feature text without comments or annotations.
    feature_type : FabulousFasmFeatureType
        Routing or configuration classification.
    tile : str | None
        Tile coordinate token such as ``X1Y5``.
    tile_x : int | None
        Tile X coordinate.
    tile_y : int | None
        Tile Y coordinate.
    parts : tuple[str, ...]
        Dot-separated feature path without any address suffix.
    address : str | None
        Optional FASM address such as ``[15:0]``.
    value : str | None
        Optional raw FASM value text after ``=``.
    source : str | None
        Routing source token for routing-shaped features.
    destination : str | None
        Routing destination token for routing-shaped features.
    tile_type : str | None
        Graph-resolved placed tile type.
    pip_kind : RoutingPipKind | None
        Graph-resolved routing PIP kind.
    pip : RoutingPip | None
        Graph-resolved routing PIP.
    external_resource_key : RoutingResourceKey | None
        Graph-resolved external resource key for external routing features.
    external_track_index : int | None
        Logical external vector track used by an external routing feature.
    external_source_index : int | None
        Concrete expanded source-wire index, when it can be parsed.
    external_destination_index : int | None
        Concrete expanded destination-wire index, when it can be parsed.
    external_segment_index : int | None
        Expanded segment index derived from the source index when available,
        otherwise from the destination index.
    resolved : bool
        Whether graph annotation was requested and succeeded.
    """

    raw: str
    feature_type: FabulousFasmFeatureType
    tile: str | None
    tile_x: int | None
    tile_y: int | None
    parts: tuple[str, ...]
    address: str | None = None
    value: str | None = None
    source: str | None = None
    destination: str | None = None
    tile_type: str | None = None
    pip_kind: RoutingPipKind | None = None
    pip: RoutingPip | None = None
    external_resource_key: RoutingResourceKey | None = None
    external_track_index: int | None = None
    external_source_index: int | None = None
    external_destination_index: int | None = None
    external_segment_index: int | None = None
    resolved: bool = False

    @property
    def coordinate(self) -> tuple[int, int] | None:
        """Return the feature tile coordinate when present.

        Returns
        -------
        tuple[int, int] | None
            ``(x, y)`` coordinate, or ``None`` for non-tile features.
        """
        if self.tile_x is None or self.tile_y is None:
            return None
        return (self.tile_x, self.tile_y)


@dataclass(slots=True)
class FabulousFasmDocument:
    """Parsed FABulous FASM feature collection."""

    features: list[FabulousFasmFeature]

    def query(
        self,
        where: Callable[[FabulousFasmFeature], bool] | None = None,
    ) -> list[FabulousFasmFeature]:
        """Return features that match an optional predicate.

        Parameters
        ----------
        where : Callable[[FabulousFasmFeature], bool] | None
            Optional predicate. If ``None``, all features are returned.

        Returns
        -------
        list[FabulousFasmFeature]
            Matching features.
        """
        if where is None:
            return list(self.features)
        return [feature for feature in self.features if where(feature)]

    def routing_matrix_features_for_tile_type(
        self,
        tile_type: str,
        where: Callable[[FabulousFasmFeature], bool] | None = None,
        *,
        filter_unique_pips: bool = False,
    ) -> list[FabulousFasmFeature]:
        """Return matrix-routing features owned by instances of a tile type.

        Parameters
        ----------
        tile_type : str
            Placed tile type to query.
        where : Callable[[FabulousFasmFeature], bool] | None
            Optional additional predicate.
        filter_unique_pips : bool
            If ``True``, return only the first feature for each tile-local
            matrix PIP name after all other filters are applied.

        Returns
        -------
        list[FabulousFasmFeature]
            Resolved internal switch-matrix routing features owned by all
            instances of ``tile_type``.
        """
        features = [
            feature
            for feature in self.features
            if feature.tile_type == tile_type
            and feature.feature_type is FabulousFasmFeatureType.ROUTING
            and feature.pip_kind is RoutingPipKind.INTERNAL_MATRIX
            and (where is None or where(feature))
        ]
        if not filter_unique_pips:
            return features

        unique_features: dict[str, FabulousFasmFeature] = {}
        for feature in features:
            unique_features.setdefault(_pip_name(feature), feature)
        return list(unique_features.values())

    def routing_external_features_for_tile_type(
        self,
        tile_type: str,
        where: Callable[[FabulousFasmFeature], bool] | None = None,
        *,
        filter_unique_pips: bool = False,
    ) -> list[FabulousFasmFeature]:
        """Return external-routing features owned by instances of a tile type.

        Parameters
        ----------
        tile_type : str
            Placed tile type to query.
        where : Callable[[FabulousFasmFeature], bool] | None
            Optional additional predicate.
        filter_unique_pips : bool
            If ``True``, return only the first feature for each tile-local
            external PIP name after all other filters are applied.

        Returns
        -------
        list[FabulousFasmFeature]
            Resolved external routing features owned by all instances of
            ``tile_type``.
        """
        features = [
            feature
            for feature in self.features
            if feature.tile_type == tile_type
            and feature.feature_type is FabulousFasmFeatureType.ROUTING
            and feature.pip_kind is RoutingPipKind.EXTERNAL_WIRE
            and (where is None or where(feature))
        ]
        if not filter_unique_pips:
            return features

        unique_features: dict[str, FabulousFasmFeature] = {}
        for feature in features:
            unique_features.setdefault(_pip_name(feature), feature)
        return list(unique_features.values())

    def used_external_pips_for_tile_type(
        self,
        tile_type: str,
        where: Callable[[FabulousFasmFeature], bool] | None = None,
        *,
        filter_unique_pips: bool = True,
    ) -> list[RoutingPip]:
        """Return resolved external PIPs used by instances of a tile type.

        Parameters
        ----------
        tile_type : str
            Placed tile type to query.
        where : Callable[[FabulousFasmFeature], bool] | None
            Optional additional predicate applied before PIPs are returned.
        filter_unique_pips : bool
            If ``True``, collapse repeated tile-local external PIP names across
            tile instances before returning PIPs.

        Returns
        -------
        list[RoutingPip]
            Resolved active external PIPs used by all matching tile instances.
        """
        features = self.routing_external_features_for_tile_type(
            tile_type,
            where=where,
            filter_unique_pips=filter_unique_pips,
        )
        return [feature.pip for feature in features if feature.pip is not None]

    def used_external_tracks_for_tile_type(
        self,
        tile_type: str,
        where: Callable[[FabulousFasmFeature], bool] | None = None,
        *,
        filter_unique_tracks: bool = True,
    ) -> list[tuple[RoutingResourceKey, int]]:
        """Return resolved logical external tracks used by a tile type.

        Parameters
        ----------
        tile_type : str
            Placed tile type to query.
        where : Callable[[FabulousFasmFeature], bool] | None
            Optional additional predicate applied before tracks are returned.
        filter_unique_tracks : bool
            If ``True``, collapse repeated ``(resource_key, track_index)`` pairs
            across tile instances and expanded long-wire segments.

        Returns
        -------
        list[tuple[RoutingResourceKey, int]]
            Used logical external tracks.
        """
        tracks: list[tuple[RoutingResourceKey, int]] = []
        seen: set[tuple[RoutingResourceKey, int]] = set()
        for feature in self.routing_external_features_for_tile_type(
            tile_type,
            where=where,
            filter_unique_pips=False,
        ):
            if (
                feature.external_resource_key is None
                or feature.external_track_index is None
            ):
                continue
            track = (feature.external_resource_key, feature.external_track_index)
            if filter_unique_tracks and track in seen:
                continue
            tracks.append(track)
            seen.add(track)
        return tracks

    def used_external_track_scores_for_tile_type(
        self,
        tile_type: str,
        where: Callable[[FabulousFasmFeature], bool] | None = None,
    ) -> dict[tuple[RoutingResourceKey, int], int]:
        """Return usage counts for logical external tracks.

        Parameters
        ----------
        tile_type : str
            Placed tile type to query.
        where : Callable[[FabulousFasmFeature], bool] | None
            Optional additional predicate applied before tracks are scored.

        Returns
        -------
        dict[tuple[RoutingResourceKey, int], int]
            Mapping from ``(resource_key, track_index)`` to number of matching
            external FASM features.
        """
        scores: dict[tuple[RoutingResourceKey, int], int] = {}
        for feature in self.routing_external_features_for_tile_type(
            tile_type,
            where=where,
            filter_unique_pips=False,
        ):
            if (
                feature.external_resource_key is None
                or feature.external_track_index is None
            ):
                continue
            track = (feature.external_resource_key, feature.external_track_index)
            scores[track] = scores.get(track, 0) + 1
        return scores

    def unused_external_pips_for_tile_type(
        self,
        graph: FabulousFasmGraph,
        tile_type: str,
        where: Callable[[FabulousFasmFeature], bool] | None = None,
        *,
        filter_unique_pips: bool = True,
    ) -> list[RoutingPip]:
        """Return active external PIPs not observed in this FASM document.

        Parameters
        ----------
        graph : FabulousFasmGraph
            Graph-like object that provides all active PIPs for comparison.
        tile_type : str
            Placed tile type to query.
        where : Callable[[FabulousFasmFeature], bool] | None
            Optional additional predicate applied to the used FASM features
            before the used set is built.
        filter_unique_pips : bool
            If ``True``, compare tile-local external PIP names and return a
            tile-type-level union. If ``False``, compare concrete owner-tile PIP
            instances.

        Returns
        -------
        list[RoutingPip]
            Active external PIPs from ``graph`` that were not observed as used
            by this FASM document.
        """
        used_keys = {
            _external_pip_key(pip, filter_unique_pips=filter_unique_pips)
            for pip in self.used_external_pips_for_tile_type(
                tile_type,
                where=where,
                filter_unique_pips=filter_unique_pips,
            )
        }
        unused_pips: list[RoutingPip] = []
        emitted_keys: set[str | tuple[tuple[int, int], str]] = set()
        for pip in graph.iter_active_pips(
            lambda candidate: candidate.tile_type == tile_type
            and candidate.kind is RoutingPipKind.EXTERNAL_WIRE
        ):
            key = _external_pip_key(pip, filter_unique_pips=filter_unique_pips)
            if key in used_keys or key in emitted_keys:
                continue
            unused_pips.append(pip)
            emitted_keys.add(key)
        return unused_pips

    def used_switch_matrix_for_tile_type(
        self,
        tile_type: str,
        where: Callable[[FabulousFasmFeature], bool] | None = None,
        *,
        filter_unique_pips: bool = True,
        active_pip_value: int | None = None,
    ) -> RoutingSwitchMatrix:
        """Return the union of used matrix PIPs for one tile type.

        Parameters
        ----------
        tile_type : str
            Placed tile type to query.
        where : Callable[[FabulousFasmFeature], bool] | None
            Optional additional predicate applied before matrix construction.
        filter_unique_pips : bool
            If ``True``, collapse repeated tile-local PIP names across tile
            instances before constructing the matrix.
        active_pip_value : int | None
            Optional positive value to write for every active PIP cell. If
            ``None``, the graph-resolved PIP delay is used.

        Returns
        -------
        RoutingSwitchMatrix
            Switch matrix containing the used internal matrix PIPs from all
            matching tile instances.

        Raises
        ------
        ValueError
            If ``active_pip_value`` is provided and is not positive.
        """
        if active_pip_value is not None and active_pip_value <= 0:
            raise ValueError("active_pip_value must be greater than 0")

        features = self.routing_matrix_features_for_tile_type(
            tile_type,
            where=where,
            filter_unique_pips=filter_unique_pips,
        )
        pips = [feature.pip for feature in features if feature.pip is not None]
        rows = list(dict.fromkeys(pip.resource_key.source_name for pip in pips))
        columns = list(dict.fromkeys(pip.resource_key.destination_name for pip in pips))
        row_index = {row: index for index, row in enumerate(rows)}
        column_index = {column: index for index, column in enumerate(columns)}
        matrix = [[0.0 for _column in columns] for _row in rows]

        for pip in pips:
            value = (
                float(active_pip_value) if active_pip_value is not None else pip.delay
            )
            matrix[row_index[pip.resource_key.source_name]][
                column_index[pip.resource_key.destination_name]
            ] = float(value)

        return RoutingSwitchMatrix(
            tile_type=tile_type,
            columns=columns,
            rows=rows,
            matrix=matrix,
        )


def parse_fabulous_fasm(
    text: str,
    graph: FabulousFasmGraph | None = None,
) -> FabulousFasmDocument:
    """Parse FABulous FASM text.

    Parameters
    ----------
    text : str
        FASM text.
    graph : FabulousFasmGraph | None
        Optional graph used to annotate every feature. If provided, every parsed
        feature must resolve to either a graph PIP or a placed tile.

    Returns
    -------
    FabulousFasmDocument
        Parsed FASM document.
    """
    features = [
        feature
        for line in text.splitlines()
        if (feature := _parse_line(line)) is not None
    ]
    if graph is not None:
        features = _annotate_features(features, graph)
    return FabulousFasmDocument(features=features)


def _parse_line(line: str) -> FabulousFasmFeature | None:
    """Parse one physical FASM line.

    Parameters
    ----------
    line : str
        Raw line from the FASM text, including any comments or annotation
        blocks.

    Returns
    -------
    FabulousFasmFeature | None
        Parsed feature, or ``None`` when the line contains only whitespace,
        comments, or annotations.

    Raises
    ------
    FabulousFasmParseError
        If the remaining feature text is not a supported FABulous FASM shape.
    """
    raw = _strip_annotations(_strip_comment(line)).strip()
    if not raw:
        return None

    feature_text, value = _split_value(raw)
    match = _FEATURE_RE.fullmatch(feature_text)
    if match is None:
        raise FabulousFasmParseError(f"cannot parse FASM feature: {line!r}")

    feature = match.group("feature")
    address = match.group("address")
    parts = tuple(feature.split("."))
    tile = parts[0] if parts else None
    tile_x, tile_y = _parse_tile_coordinate(tile)
    source = parts[1] if len(parts) == 3 and tile_x is not None else None
    destination = parts[2] if len(parts) == 3 and tile_x is not None else None
    feature_type = (
        FabulousFasmFeatureType.CONFIG
        if address is not None or value is not None
        else FabulousFasmFeatureType.ROUTING
    )

    return FabulousFasmFeature(
        raw=raw,
        feature_type=feature_type,
        tile=tile if tile_x is not None else None,
        tile_x=tile_x,
        tile_y=tile_y,
        parts=parts,
        address=address,
        value=value,
        source=source,
        destination=destination,
    )


def _annotate_features(
    features: Iterable[FabulousFasmFeature],
    graph: FabulousFasmGraph,
) -> list[FabulousFasmFeature]:
    """Attach graph metadata to a sequence of parsed features.

    Parameters
    ----------
    features : Iterable[FabulousFasmFeature]
        Parsed features to annotate. The iterable is materialized once so the
        requested routing PIPs can be collected before active graph PIPs are
        consumed.
    graph : FabulousFasmGraph
        Graph-like object used to resolve tile types and active PIPs.

    Returns
    -------
    list[FabulousFasmFeature]
        Features annotated with tile type information and, for routing
        features, the matching graph PIP metadata.
    """
    features = list(features)
    requested_keys = _requested_pip_keys(features)
    pip_index = _pip_index(graph.iter_active_pips(), requested_keys)
    annotated: list[FabulousFasmFeature] = []
    for feature in features:
        annotated.append(_annotate_feature(feature, graph, pip_index))
    return annotated


def _annotate_feature(
    feature: FabulousFasmFeature,
    graph: FabulousFasmGraph,
    pip_index: dict[tuple[int, int, str], RoutingPip],
) -> FabulousFasmFeature:
    """Attach graph metadata to one parsed feature.

    Parameters
    ----------
    feature : FabulousFasmFeature
        Feature to resolve.
    graph : FabulousFasmGraph
        Graph-like object used for coordinate to tile-type lookup.
    pip_index : dict[tuple[int, int, str], RoutingPip]
        Mapping from ``(owner_x, owner_y, pip_name)`` to active graph PIP.

    Returns
    -------
    FabulousFasmFeature
        Resolved feature. Routing features receive PIP metadata; non-routing
        features are marked as configuration features on the resolved tile.

    Raises
    ------
    FabulousFasmResolveError
        If the feature has no tile coordinate or the coordinate is not present
        in the graph.
    """
    if feature.tile_x is None or feature.tile_y is None:
        raise FabulousFasmResolveError(
            f"cannot resolve non-tile FASM feature: {feature.raw}"
        )

    tile_type = graph.tile_type_at(feature.tile_x, feature.tile_y)
    if tile_type is None:
        raise FabulousFasmResolveError(
            f"cannot resolve FASM feature on unplaced tile {feature.tile}: "
            f"{feature.raw}"
        )

    pip = pip_index.get((feature.tile_x, feature.tile_y, _pip_name(feature)))
    if pip is not None:
        external_metadata = _external_track_metadata(pip)
        return replace(
            feature,
            feature_type=FabulousFasmFeatureType.ROUTING,
            tile_type=pip.tile_type,
            pip_kind=pip.kind,
            pip=pip,
            resolved=True,
            **external_metadata,
        )

    return replace(
        feature,
        feature_type=FabulousFasmFeatureType.CONFIG,
        tile_type=tile_type,
        resolved=True,
    )


def _requested_pip_keys(
    features: Iterable[FabulousFasmFeature],
) -> set[tuple[int, int, str]]:
    """Collect active graph PIP keys that may be referenced by FASM features.

    Parameters
    ----------
    features : Iterable[FabulousFasmFeature]
        Parsed features to inspect.

    Returns
    -------
    set[tuple[int, int, str]]
        Candidate keys in ``(owner_x, owner_y, pip_name)`` form. Only
        routing-shaped features with tile coordinates are included.
    """
    return {
        (feature.tile_x, feature.tile_y, _pip_name(feature))
        for feature in features
        if feature.feature_type is FabulousFasmFeatureType.ROUTING
        and feature.tile_x is not None
        and feature.tile_y is not None
        and _pip_name(feature)
    }


def _pip_index(
    pips: Iterable[RoutingPip],
    requested_keys: set[tuple[int, int, str]],
) -> dict[tuple[int, int, str], RoutingPip]:
    """Index only active graph PIPs referenced by the parsed FASM text.

    Parameters
    ----------
    pips : Iterable[RoutingPip]
        Active graph PIPs. This can be a lazy iterator.
    requested_keys : set[tuple[int, int, str]]
        Keys needed by the parsed FASM features.

    Returns
    -------
    dict[tuple[int, int, str], RoutingPip]
        PIPs found for the requested keys. Iteration stops once all requested
        keys have been found, so unrelated graph PIPs are not consumed.
    """
    if not requested_keys:
        return {}

    index: dict[tuple[int, int, str], RoutingPip] = {}
    for pip in pips:
        key = (pip.owner_tile[0], pip.owner_tile[1], pip.name)
        if key not in requested_keys:
            continue
        index[key] = pip
        if len(index) == len(requested_keys):
            break
    return index


def _pip_name(feature: FabulousFasmFeature) -> str:
    """Build the tile-local graph PIP name represented by one feature.

    Parameters
    ----------
    feature : FabulousFasmFeature
        Parsed feature whose path parts should be converted to a PIP name.

    Returns
    -------
    str
        Dot-joined feature path after the tile coordinate, or an empty string
        when the feature has no tile-local path.
    """
    return ".".join(feature.parts[1:]) if len(feature.parts) > 1 else ""


def _external_pip_key(
    pip: RoutingPip,
    *,
    filter_unique_pips: bool,
) -> str | tuple[tuple[int, int], str]:
    """Return the comparison key for an external graph PIP.

    Parameters
    ----------
    pip : RoutingPip
        External graph PIP to key.
    filter_unique_pips : bool
        Whether the key should ignore concrete owner-tile coordinates.

    Returns
    -------
    str | tuple[tuple[int, int], str]
        Tile-local PIP name for union queries, or ``(owner_tile, name)`` for
        concrete instance-level queries.
    """
    if filter_unique_pips:
        return pip.name
    return (pip.owner_tile, pip.name)


def _external_track_metadata(pip: RoutingPip) -> dict[str, object]:
    """Return graph-backed logical track fields for one resolved external PIP.

    Parameters
    ----------
    pip : RoutingPip
        Resolved graph PIP.

    Returns
    -------
    dict[str, object]
        Keyword values suitable for :func:`dataclasses.replace`. Non-external
        PIPs, ``NULL`` endpoint resources, and resources without a wire count
        return an empty dictionary.

    Raises
    ------
    FabulousFasmResolveError
        If a non-``NULL`` external PIP has inconsistent source and destination
        track indexes.
    """
    if pip.kind is not RoutingPipKind.EXTERNAL_WIRE:
        return {}

    key = pip.resource_key
    if key.wire_count is None:
        return {"external_resource_key": key}
    if key.source_name == "NULL" or key.destination_name == "NULL":
        metadata: dict[str, object] = {"external_resource_key": key}
        if key.wire_count == 1:
            metadata["external_track_index"] = 0
        return metadata

    source_index = _external_endpoint_index(pip.source.wire, key)
    destination_index = _external_endpoint_index(pip.destination.wire, key)
    concrete_index = source_index if source_index is not None else destination_index
    if concrete_index is None:
        return {"external_resource_key": key}

    track_index = concrete_index % key.wire_count
    if (
        source_index is not None
        and destination_index is not None
        and source_index % key.wire_count != destination_index % key.wire_count
    ):
        raise FabulousFasmResolveError(
            f"external FASM PIP endpoints disagree on logical track: {pip.name}"
        )

    return {
        "external_resource_key": key,
        "external_track_index": track_index,
        "external_source_index": source_index,
        "external_destination_index": destination_index,
        "external_segment_index": concrete_index // key.wire_count,
    }


def _wire_suffix_index(wire_name: str, base_name: str) -> int | None:
    """Return the integer suffix of ``wire_name`` after ``base_name``.

    Parameters
    ----------
    wire_name : str
        Concrete wire name such as ``EE4BEG12``.
    base_name : str
        Base vector name such as ``EE4BEG``.

    Returns
    -------
    int | None
        Parsed suffix index, or ``None`` if the wire does not match the base.
    """
    if base_name == "NULL" or not wire_name.startswith(base_name):
        return None
    suffix = wire_name[len(base_name) :]
    if not suffix.isdigit():
        return None
    return int(suffix)


def _external_endpoint_index(
    wire_name: str,
    resource_key: RoutingResourceKey,
) -> int | None:
    """Return the expanded index for an endpoint of an external resource.

    Parameters
    ----------
    wire_name : str
        Concrete endpoint wire.
    resource_key : RoutingResourceKey
        External resource that generated the endpoint.

    Returns
    -------
    int | None
        Parsed expanded index from either the resource source or destination
        base name.
    """
    base_names = sorted(
        (resource_key.source_name, resource_key.destination_name),
        key=len,
        reverse=True,
    )
    for base_name in base_names:
        index = _wire_suffix_index(wire_name, base_name)
        if index is not None:
            return index
    return None


def _parse_tile_coordinate(tile: str | None) -> tuple[int | None, int | None]:
    """Parse a FABulous tile coordinate token.

    Parameters
    ----------
    tile : str | None
        Candidate coordinate token such as ``X1Y5``.

    Returns
    -------
    tuple[int | None, int | None]
        Parsed ``(x, y)`` coordinate. ``(None, None)`` is returned when the
        token is missing or not a coordinate.
    """
    if tile is None:
        return (None, None)
    match = _TILE_RE.fullmatch(tile)
    if match is None:
        return (None, None)
    return (int(match.group("x")), int(match.group("y")))


def _split_value(line: str) -> tuple[str, str | None]:
    """Split a FASM feature path from an optional value assignment.

    Parameters
    ----------
    line : str
        Feature line after comments and annotations have been removed.

    Returns
    -------
    tuple[str, str | None]
        ``(feature_text, value)``. ``value`` is ``None`` when the line has no
        ``=`` assignment.
    """
    if "=" not in line:
        return (line.strip(), None)
    feature, value = line.split("=", 1)
    return (feature.strip(), value.strip())


def _strip_comment(line: str) -> str:
    """Remove a trailing FASM comment while preserving quoted strings.

    Parameters
    ----------
    line : str
        Raw FASM line.

    Returns
    -------
    str
        Text before the first unquoted ``#`` character. Quoted strings and
        escaped characters inside quoted strings are preserved.
    """
    in_string = False
    escaped = False
    for index, char in enumerate(line):
        if escaped:
            escaped = False
            continue
        if char == "\\" and in_string:
            escaped = True
            continue
        if char == '"':
            in_string = not in_string
            continue
        if char == "#" and not in_string:
            return line[:index]
    return line


def _strip_annotations(line: str) -> str:
    """Remove FASM annotation blocks while preserving feature text.

    Parameters
    ----------
    line : str
        FASM line after comment stripping.

    Returns
    -------
    str
        Line with top-level ``{...}`` annotation blocks removed. Braces inside
        quoted strings are preserved.
    """
    output: list[str] = []
    depth = 0
    in_string = False
    escaped = False
    for char in line:
        if escaped:
            escaped = False
            if depth == 0:
                output.append(char)
            continue
        if char == "\\" and in_string:
            escaped = True
            if depth == 0:
                output.append(char)
            continue
        if char == '"':
            in_string = not in_string
            if depth == 0:
                output.append(char)
            continue
        if char == "{" and not in_string:
            depth += 1
            continue
        if char == "}" and depth > 0 and not in_string:
            depth -= 1
            continue
        if depth == 0:
            output.append(char)
    return "".join(output)

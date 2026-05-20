"""Discover routing resources from FABulous tile CSV and list fragments.

The tile builder treats base CSV/list files as routing fragments. This module expands
those fragments using FABulous' switch-matrix naming rules so the baseline generator can
derive source pools and output rows without assuming a specific project naming scheme.
"""

from __future__ import annotations

import csv
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from fabulous.custom_exception import InvalidPortType
from fabulous.fabric_cad.fabxplore.modules.tile_builder.core.models import (
    BaselineRouting,
    FabulousCsvKeyword,
    RoutingTrackGroup,
    TileBuilderGeneratedWire,
)
from fabulous.fabric_definition.define import Direction
from fabulous.fabric_generator.parser.parse_csv import parsePortLine
from fabulous.fabric_generator.parser.parse_switchmatrix import parseList

if TYPE_CHECKING:
    from collections.abc import Iterable
    from pathlib import Path


@dataclass(frozen=True)
class BasePortRecord:
    """One FABulous tile CSV wire row after include expansion.

    Attributes
    ----------
    direction : Direction
        FABulous routing direction.
    source_name : str
        Opaque FABulous source name from the CSV row.
    destination_name : str
        Opaque FABulous destination name from the CSV row.
    x_offset : int
        X offset from the CSV row.
    y_offset : int
        Y offset from the CSV row.
    wire_count : int
        Wire count from the CSV row.
    switch_matrix_sources : list[str]
        Expanded switch-matrix source row names.
    switch_matrix_destinations : list[str]
        Expanded switch-matrix destination column names.
    """

    direction: Direction
    source_name: str
    destination_name: str
    x_offset: int
    y_offset: int
    wire_count: int
    switch_matrix_sources: list[str]
    switch_matrix_destinations: list[str]

    def output_ports(self) -> list[str]:
        """Return expanded switch-matrix output row names.

        Returns
        -------
        list[str]
            Expanded output row names.
        """
        return list(self.switch_matrix_sources)

    def input_ports(self) -> list[str]:
        """Return expanded switch-matrix input column names.

        Returns
        -------
        list[str]
            Expanded input column names.
        """
        return list(self.switch_matrix_destinations)

    def to_routing_track_group(self, index: int) -> RoutingTrackGroup | None:
        """Convert directional records into a normalized routing track group.

        Parameters
        ----------
        index : int
            Record index used for a stable diagnostic identifier.

        Returns
        -------
        RoutingTrackGroup | None
            Routing track group, or ``None`` for non-routing records.
        """
        if self.direction == Direction.JUMP:
            return None
        if not self.switch_matrix_sources or not self.switch_matrix_destinations:
            return None
        return RoutingTrackGroup(
            group_id=(
                f"{self.direction.value}:{self.x_offset}:{self.y_offset}:"
                f"{self.wire_count}:{index}"
            ),
            direction=self.direction,
            x_offset=self.x_offset,
            y_offset=self.y_offset,
            wire_count=self.wire_count,
            destination_rows=list(self.switch_matrix_sources),
            selectable_sources=list(self.switch_matrix_destinations),
        )


@dataclass(frozen=True)
class BaseRoutingModel:
    """Expanded base routing resources for a generated tile.

    Attributes
    ----------
    csv_includes : list[str]
        Include lines to emit in the tile CSV.
    list_includes : list[str]
        Include lines to emit in the switch-matrix list.
    csv_paths : list[Path]
        Resolved top-level CSV include paths.
    list_paths : list[Path]
        Resolved top-level list include paths.
    port_records : list[BasePortRecord]
        Expanded CSV wire rows.
    existing_pairs : list[tuple[str, str]]
        Pairs parsed from included list files.
    extra_csv_lines : list[str]
        Additional CSV rows the tile builder must emit directly.
    """

    csv_includes: list[str]
    list_includes: list[str]
    csv_paths: list[Path]
    list_paths: list[Path]
    port_records: list[BasePortRecord]
    existing_pairs: list[tuple[str, str]]
    extra_csv_lines: list[str] = field(default_factory=list)

    @property
    def input_ports(self) -> list[str]:
        """Return discovered switch-matrix input column names.

        Returns
        -------
        list[str]
            Unique input column names.
        """
        return _unique(
            port for record in self.port_records for port in record.input_ports()
        )

    @property
    def output_ports(self) -> list[str]:
        """Return discovered switch-matrix output row names.

        Returns
        -------
        list[str]
            Unique output row names.
        """
        return _unique(
            port for record in self.port_records for port in record.output_ports()
        )

    @property
    def covered_outputs(self) -> set[str]:
        """Return output rows already covered by included list files.

        Returns
        -------
        set[str]
            Output row names present as first element in list pairs.
        """
        return {source for source, _sink in self.existing_pairs}

    @property
    def uncovered_outputs(self) -> list[str]:
        """Return discovered output rows not covered by included list files.

        Returns
        -------
        list[str]
            Output rows that still need at least one connection.
        """
        covered = self.covered_outputs
        return [port for port in self.output_ports if port not in covered]

    @property
    def gnd_source(self) -> str | None:
        """Return a discovered GND input source.

        Returns
        -------
        str | None
            Expanded GND source name if present.
        """
        return _find_named_source(self.input_ports, TileBuilderGeneratedWire.GND)

    @property
    def vcc_source(self) -> str | None:
        """Return a discovered VCC input source.

        Returns
        -------
        str | None
            Expanded VCC source name if present.
        """
        return _find_named_source(self.input_ports, TileBuilderGeneratedWire.VCC)

    @property
    def routing_track_groups(self) -> list[RoutingTrackGroup]:
        """Return directional routing groups for pattern generators.

        Returns
        -------
        list[RoutingTrackGroup]
            Track groups derived from non-JUMP base records.
        """
        groups: list[RoutingTrackGroup] = []
        for index, record in enumerate(self.port_records):
            group = record.to_routing_track_group(index)
            if group is not None:
                groups.append(group)
        return groups


def build_base_routing_model(
    tile_dir: Path,
    routing: BaselineRouting,
    require_gnd: bool,
    require_vcc: bool,
) -> BaseRoutingModel:
    """Build an expanded base routing model from routing options.

    Parameters
    ----------
    tile_dir : Path
        Directory of the generated tile CSV/list files.
    routing : BaselineRouting
        Tile-builder routing options.
    require_gnd : bool
        Whether generated special wiring needs a GND source.
    require_vcc : bool
        Whether generated special wiring needs a VCC source.

    Returns
    -------
    BaseRoutingModel
        Expanded base routing model.
    """
    csv_paths = [
        _resolve_include(tile_dir, include) for include in routing.base_csv_includes
    ]
    list_paths = [
        _resolve_include(tile_dir, include) for include in routing.base_list_includes
    ]
    port_records = _read_csv_fragments(csv_paths)
    existing_pairs = _read_list_fragments(list_paths)
    extra_csv_lines: list[str] = []

    model = BaseRoutingModel(
        csv_includes=list(routing.base_csv_includes),
        list_includes=list(routing.base_list_includes),
        csv_paths=csv_paths,
        list_paths=list_paths,
        port_records=port_records,
        existing_pairs=existing_pairs,
        extra_csv_lines=extra_csv_lines,
    )
    if routing.emit_constants_if_missing:
        model = _add_missing_constants(model, require_gnd, require_vcc)
    return model


def _resolve_include(tile_dir: Path, include: str) -> Path:
    """Resolve a configured include path from the generated tile directory.

    Parameters
    ----------
    tile_dir : Path
        Generated tile directory.
    include : str
        Include path string.

    Returns
    -------
    Path
        Resolved include path.
    """
    return (tile_dir / include).resolve()


def _read_csv_fragments(paths: list[Path]) -> list[BasePortRecord]:
    """Read all configured CSV fragments recursively.

    Parameters
    ----------
    paths : list[Path]
        Top-level CSV include paths.

    Returns
    -------
    list[BasePortRecord]
        Parsed wire records.
    """
    records: list[BasePortRecord] = []
    seen: set[Path] = set()
    for path in paths:
        records.extend(_read_csv_fragment(path, seen))
    return records


def _read_csv_fragment(path: Path, seen: set[Path]) -> list[BasePortRecord]:
    """Read one CSV fragment and recursively expand its includes.

    Parameters
    ----------
    path : Path
        CSV fragment path.
    seen : set[Path]
        Already visited paths.

    Returns
    -------
    list[BasePortRecord]
        Parsed wire records.

    Raises
    ------
    FileNotFoundError
        If the fragment does not exist.
    """
    resolved = path.resolve()
    if resolved in seen:
        return []
    if not resolved.is_file():
        raise FileNotFoundError(f"base CSV include does not exist: {resolved}")
    seen.add(resolved)

    records: list[BasePortRecord] = []
    rows = csv.reader(_comment_stripped_lines(resolved))
    for row in rows:
        if not row:
            continue
        fields = [field.strip() for field in row]
        if not fields or not fields[0]:
            continue
        if fields[0] == FabulousCsvKeyword.INCLUDE:
            records.extend(_read_csv_fragment(resolved.parent / fields[1], seen))
            continue
        record = _parse_port_record(fields)
        if record is not None:
            records.append(record)
    return records


def _comment_stripped_lines(path: Path) -> list[str]:
    """Return non-empty CSV lines with comments removed.

    Parameters
    ----------
    path : Path
        CSV path.

    Returns
    -------
    list[str]
        Cleaned CSV lines.
    """
    lines: list[str] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        clean = line.split("#", 1)[0].strip()
        if clean:
            lines.append(clean)
    return lines


def _parse_port_record(fields: list[str]) -> BasePortRecord | None:
    """Parse one FABulous tile CSV wire row.

    Parameters
    ----------
    fields : list[str]
        CSV fields.

    Returns
    -------
    BasePortRecord | None
        Parsed record, or ``None`` for non-wire rows.
    """
    if len(fields) < 6 or fields[0] not in Direction.__members__:
        return None
    try:
        ports, _common_wire_pair = parsePortLine(",".join(fields[:6]))
    except (InvalidPortType, ValueError):
        return None
    source_ports: list[str] = []
    destination_ports: list[str] = []
    for port in ports:
        source_names, destination_names = port.expandPortInfo("AutoSwitchMatrix")
        source_ports.extend(source_names)
        destination_ports.extend(destination_names)
    direction = fields[0]
    source_name = fields[1]
    x_offset = fields[2]
    y_offset = fields[3]
    destination_name = fields[4]
    wire_count = fields[5]
    return BasePortRecord(
        direction=Direction[direction],
        source_name=source_name,
        destination_name=destination_name,
        x_offset=int(x_offset),
        y_offset=int(y_offset),
        wire_count=int(wire_count),
        switch_matrix_sources=_unique(source_ports),
        switch_matrix_destinations=_unique(destination_ports),
    )


def _read_list_fragments(paths: list[Path]) -> list[tuple[str, str]]:
    """Read all configured list fragments through FABulous' parser.

    Parameters
    ----------
    paths : list[Path]
        Top-level list include paths.

    Returns
    -------
    list[tuple[str, str]]
        Parsed switch-matrix pairs.

    Raises
    ------
    FileNotFoundError
        If a configured list include does not exist.
    """
    pairs: list[tuple[str, str]] = []
    for path in paths:
        if not path.is_file():
            raise FileNotFoundError(f"base list include does not exist: {path}")
        pairs.extend(parseList(path))
    return list(dict.fromkeys(pairs))


def _add_missing_constants(
    model: BaseRoutingModel,
    require_gnd: bool,
    require_vcc: bool,
) -> BaseRoutingModel:
    """Add local constant jump rows required by generated routing.

    Parameters
    ----------
    model : BaseRoutingModel
        Existing base routing model.
    require_gnd : bool
        Whether a GND source is required.
    require_vcc : bool
        Whether a VCC source is required.

    Returns
    -------
    BaseRoutingModel
        Model with additional constant records and CSV lines.
    """
    records = list(model.port_records)
    extra_lines = list(model.extra_csv_lines)
    if require_gnd and model.gnd_source is None:
        records.append(
            _parse_required_port_record(
                [
                    Direction.JUMP.value,
                    FabulousCsvKeyword.NULL,
                    "0",
                    "0",
                    TileBuilderGeneratedWire.GND,
                    "1",
                    "",
                ]
            )
        )
        extra_lines.append(
            ",".join(
                [
                    Direction.JUMP.value,
                    FabulousCsvKeyword.NULL,
                    "0",
                    "0",
                    TileBuilderGeneratedWire.GND,
                    "1",
                    "",
                ]
            )
        )
    if require_vcc and model.vcc_source is None:
        records.append(
            _parse_required_port_record(
                [
                    Direction.JUMP.value,
                    FabulousCsvKeyword.NULL,
                    "0",
                    "0",
                    TileBuilderGeneratedWire.VCC,
                    "1",
                    "",
                ]
            )
        )
        extra_lines.append(
            ",".join(
                [
                    Direction.JUMP.value,
                    FabulousCsvKeyword.NULL,
                    "0",
                    "0",
                    TileBuilderGeneratedWire.VCC,
                    "1",
                    "",
                ]
            )
        )
    return BaseRoutingModel(
        csv_includes=model.csv_includes,
        list_includes=model.list_includes,
        csv_paths=model.csv_paths,
        list_paths=model.list_paths,
        port_records=records,
        existing_pairs=model.existing_pairs,
        extra_csv_lines=extra_lines,
    )


def _parse_required_port_record(fields: list[str]) -> BasePortRecord:
    """Parse an internally generated port record.

    Parameters
    ----------
    fields : list[str]
        CSV fields for a generated FABulous wire row.

    Returns
    -------
    BasePortRecord
        Parsed port record.

    Raises
    ------
    ValueError
        If the generated row cannot be parsed.
    """
    record = _parse_port_record(fields)
    if record is None:
        raise ValueError(f"cannot parse generated port record: {fields}")
    return record


def _find_named_source(sources: list[str], base_name: str) -> str | None:
    """Find a source with a FABulous constant base name.

    Parameters
    ----------
    sources : list[str]
        Candidate source names.
    base_name : str
        Constant base name, usually ``GND`` or ``VCC``.

    Returns
    -------
    str | None
        Matching source name if present.
    """
    for source in sources:
        if source == base_name or source.startswith(base_name):
            return source
    return None


def _unique(values: Iterable[str]) -> list[str]:
    """Return unique strings while preserving order.

    Parameters
    ----------
    values : Iterable[str]
        Values to deduplicate.

    Returns
    -------
    list[str]
        Unique values.
    """
    return list(dict.fromkeys(values))

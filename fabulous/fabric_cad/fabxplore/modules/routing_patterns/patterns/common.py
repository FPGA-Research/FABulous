"""Shared helpers for graph-backed switch-matrix pattern classes."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import TYPE_CHECKING

from fabulous.fabric_cad.fabxplore.modules.routing_patterns.core.models import (
    RoutingPipPattern,
    SwitchMatrixPatternApplyResult,
    SwitchMatrixPatternOptions,
)
from fabulous.fabric_definition.define import Direction

if TYPE_CHECKING:
    from collections.abc import Iterable

    from fabulous.fabric_cad.fabxplore.pnr.fab_graph.core.models import (
        RoutingSwitchMatrix,
        RoutingTileModel,
    )
    from fabulous.fabric_cad.fabxplore.pnr.pnr_bridge import PnRBridge

MatrixPair = tuple[str, str]

CARDINAL_DIRECTIONS = (
    Direction.NORTH,
    Direction.EAST,
    Direction.SOUTH,
    Direction.WEST,
)
CONSTANT_WIRES = ("GND", "GND0", "VCC", "VCC0")


@dataclass(frozen=True, slots=True)
class RoutingTrackGroup:
    """One directional routing-resource group discovered from the FPGA model.

    Attributes
    ----------
    direction : Direction
        FABulous routing direction for the group.
    source_name : str
        FABulous source base name for routing rows.
    x_offset : int
        Horizontal routing offset represented by the group.
    y_offset : int
        Vertical routing offset represented by the group.
    destination_name : str
        FABulous destination base name for selectable source columns.
    wire_count : int
        Number of declared tracks before FABulous direction expansion.
    destination_rows : list[str]
        Switch-matrix output rows driven by the group.
    selectable_sources : list[str]
        Switch-matrix input columns that can drive other rows.
    """

    direction: Direction
    source_name: str
    x_offset: int
    y_offset: int
    destination_name: str
    wire_count: int
    destination_rows: list[str]
    selectable_sources: list[str]


class _HierarchyResult:
    """Internal result for generated BEL-input hierarchy resources.

    Parameters
    ----------
    pairs : list[MatrixPair]
        Matrix pairs needed to connect sources through generated hierarchy
        JUMP wires and into the final BEL input rows.
    added_jump_wires : int
        Number of new JUMP resources added to the FPGA model.
    """

    def __init__(self, pairs: list[MatrixPair], added_jump_wires: int) -> None:
        self.pairs = pairs
        self.added_jump_wires = added_jump_wires


def routing_track_groups(
    fpga_model: PnRBridge,
    tile_name: str,
) -> list[RoutingTrackGroup]:
    """Return routing track groups visible to one tile switch matrix.

    Parameters
    ----------
    fpga_model : PnRBridge
        FPGA model exposing the FabGraph API.
    tile_name : str
        Tile type to inspect.

    Returns
    -------
    list[RoutingTrackGroup]
        Routing-resource groups discovered from the tile model.
    """
    tile_model = fpga_model.tile_model(tile_name)
    available_wires = fpga_model.matrix_sources(tile_name)
    return _routing_track_groups(tile_model, available_wires)


def routable_groups(groups: list[RoutingTrackGroup]) -> list[RoutingTrackGroup]:
    """Return groups with both destination rows and selectable sources.

    Parameters
    ----------
    groups : list[RoutingTrackGroup]
        Candidate groups.

    Returns
    -------
    list[RoutingTrackGroup]
        Groups usable by route-through patterns.
    """
    return [
        group for group in groups if group.destination_rows and group.selectable_sources
    ]


def cardinal_routable_groups(
    groups: list[RoutingTrackGroup],
) -> list[RoutingTrackGroup]:
    """Return routable groups that represent side-to-side routing tracks.

    Parameters
    ----------
    groups : list[RoutingTrackGroup]
        Candidate routing groups.

    Returns
    -------
    list[RoutingTrackGroup]
        Routable groups whose direction is one of the cardinal tile sides.
        Local JUMP groups are intentionally excluded from route-through
        patterns, while remaining available to common BEL/input logic.
    """
    return [
        group
        for group in routable_groups(groups)
        if group.direction in CARDINAL_DIRECTIONS
    ]


def allowed_source_groups(
    destination_group: RoutingTrackGroup,
    groups: list[RoutingTrackGroup],
    options: SwitchMatrixPatternOptions,
) -> list[RoutingTrackGroup]:
    """Return compatible source groups for one destination group.

    Parameters
    ----------
    destination_group : RoutingTrackGroup
        Destination group.
    groups : list[RoutingTrackGroup]
        Candidate source groups.
    options : SwitchMatrixPatternOptions
        Pattern options.

    Returns
    -------
    list[RoutingTrackGroup]
        Compatible source groups.
    """
    return [
        source_group
        for source_group in groups
        if source_group.selectable_sources
        and _allow_group_pair(destination_group, source_group, options)
    ]


def apply_pattern_pairs(
    fpga_model: PnRBridge,
    options: SwitchMatrixPatternOptions,
    *,
    groups: list[RoutingTrackGroup],
    routing_pairs: list[MatrixPair],
    compatible_routing_groups: int,
    routing_warnings: Iterable[str] = (),
) -> SwitchMatrixPatternApplyResult:
    """Apply generated pairs and common BEL/output/hierarchy edits.

    Parameters
    ----------
    fpga_model : PnRBridge
        FPGA model exposing the FabGraph API.
    options : SwitchMatrixPatternOptions
        Normalized pattern options.
    groups : list[RoutingTrackGroup]
        Routing groups discovered by the pattern implementation.
    routing_pairs : list[MatrixPair]
        Routing-resource route-through pairs generated by the pattern.
    compatible_routing_groups : int
        Number of compatible routing groups used by the pattern.
    routing_warnings : Iterable[str]
        Pattern-local warnings.

    Returns
    -------
    SwitchMatrixPatternApplyResult
        Counts and warnings for the applied edit.
    """
    tile_model = fpga_model.tile_model(options.tile_name)
    available_wires = fpga_model.matrix_sources(options.tile_name)
    active_before = active_pairs(fpga_model.switch_matrix(options.tile_name))
    active_by_row = (
        {} if options.replace_existing_matrix else _active_pairs_by_row(active_before)
    )

    warnings = list(routing_warnings)
    routing_sources = _routing_source_pool(groups, available_wires)
    bel_inputs = _bel_input_wires(tile_model, available_wires)
    bel_outputs = _bel_output_wires(tile_model, available_wires)
    constant_sources = _constant_wires(available_wires)
    source_pool = _source_pool(
        routing_sources=routing_sources,
        bel_outputs=bel_outputs,
        constant_sources=constant_sources,
        include_bel_output_sources=options.include_bel_output_sources,
        include_constant_sources=options.include_constant_sources,
    )

    bel_pairs = _bel_input_pairs(
        bel_inputs=bel_inputs,
        sources=source_pool,
        fanin=options.input_fanin,
    )
    if bel_inputs and not bel_pairs:
        warnings.append(
            "BEL input access requested, but no compatible source wires were available."
        )
    bel_pair_count = len(bel_pairs)

    hierarchy_pairs: list[MatrixPair] = []
    added_jump_wires = 0
    if options.hierarchy_enabled:
        hierarchy_result = _apply_bel_input_hierarchy(
            fpga_model=fpga_model,
            tile_name=options.tile_name,
            direct_pairs=bel_pairs,
            options=options,
        )
        hierarchy_pairs = hierarchy_result.pairs
        added_jump_wires = hierarchy_result.added_jump_wires
        if options.hierarchy_replace_direct_input_pips:
            bel_pairs = []

    output_pairs = _output_coverage_pairs(
        groups=groups,
        sources=source_pool,
        fanin=options.output_fanin,
        active_by_row=active_by_row,
        enabled=options.cover_unconnected_matrix_rows,
    )

    requested_pairs = unique_pairs(
        bel_pairs + hierarchy_pairs + output_pairs + routing_pairs
    )
    deleted_active_pairs: set[MatrixPair] = set()
    if (
        options.hierarchy_enabled
        and options.hierarchy_replace_direct_input_pips
        and not options.replace_existing_matrix
    ):
        deleted_active_pairs = _delete_active_rows(
            fpga_model,
            options.tile_name,
            active_before,
            set(bel_inputs),
        )
    active_pair_set = set(active_before) - deleted_active_pairs
    pairs_to_apply = (
        requested_pairs
        if options.replace_existing_matrix
        else [pair for pair in requested_pairs if pair not in active_pair_set]
    )

    if options.replace_existing_matrix:
        _replace_switch_matrix(
            fpga_model,
            options.tile_name,
            pairs_to_apply,
            options.delay,
        )
    else:
        fpga_model.add_matrix_rows(
            options.tile_name,
            [(row, source, options.delay) for row, source in pairs_to_apply],
            overwrite=False,
        )

    return SwitchMatrixPatternApplyResult(
        generated_bel_input_pips=bel_pair_count,
        generated_output_coverage_pips=len(output_pairs),
        generated_routing_pips=len(routing_pairs),
        generated_hierarchy_pips=len(hierarchy_pairs),
        added_jump_wires=added_jump_wires,
        applied_pips=len(pairs_to_apply),
        compatible_routing_groups=compatible_routing_groups,
        warnings=tuple(warnings),
    )


def routing_pattern_warnings(
    pattern: RoutingPipPattern,
    groups: list[RoutingTrackGroup],
    pairs: list[MatrixPair],
) -> tuple[str, ...]:
    """Return common routing-pattern diagnostics.

    Parameters
    ----------
    pattern : RoutingPipPattern
        Selected pattern.
    groups : list[RoutingTrackGroup]
        Compatible routing groups.
    pairs : list[MatrixPair]
        Generated route-through pairs.

    Returns
    -------
    tuple[str, ...]
        Warning messages.
    """
    warnings: list[str] = []
    if pattern is not RoutingPipPattern.NONE and not groups:
        warnings.append(
            "Routing PIP pattern requested, but no compatible routing track "
            "groups were discovered from the FPGA model."
        )
    if pattern is not RoutingPipPattern.NONE and not pairs:
        warnings.append(
            f"Routing PIP pattern {pattern.value!r} generated no matrix pairs."
        )
    return tuple(warnings)


def active_pairs(switch_matrix: RoutingSwitchMatrix) -> list[MatrixPair]:
    """Return active ``(row, source)`` pairs from a switch matrix.

    Parameters
    ----------
    switch_matrix : RoutingSwitchMatrix
        Switch-matrix view from the FPGA model.

    Returns
    -------
    list[MatrixPair]
        Active matrix pairs.
    """
    pairs: list[MatrixPair] = []
    for row_index, row_name in enumerate(switch_matrix.rows):
        for column_index, column_name in enumerate(switch_matrix.columns):
            if switch_matrix.matrix[row_index][column_index] > 0:
                pairs.append((row_name, column_name))
    return pairs


def append_pair(pairs: list[MatrixPair], row: str, source: str) -> None:
    """Append one pair if it is not a self-connection.

    Parameters
    ----------
    pairs : list[MatrixPair]
        Mutable output pair list.
    row : str
        Destination row.
    source : str
        Selectable source.
    """
    if row != source:
        pairs.append((row, source))


def row_pair_count(pairs: list[MatrixPair], row: str) -> int:
    """Return the current number of pairs targeting one row.

    Parameters
    ----------
    pairs : list[MatrixPair]
        Current generated pairs.
    row : str
        Row to count.

    Returns
    -------
    int
        Pair count for ``row``.
    """
    return sum(1 for pair_row, _source in pairs if pair_row == row)


def unique_pairs(pairs: list[MatrixPair]) -> list[MatrixPair]:
    """Return unique pairs while preserving order.

    Parameters
    ----------
    pairs : list[MatrixPair]
        Generated pairs.

    Returns
    -------
    list[MatrixPair]
        Deduplicated pairs.
    """
    return list(dict.fromkeys(pairs))


def _active_pairs_by_row(pairs: list[MatrixPair]) -> dict[str, set[str]]:
    """Group active switch-matrix pairs by destination row.

    Parameters
    ----------
    pairs : list[MatrixPair]
        Active ``(row, source)`` matrix pairs.

    Returns
    -------
    dict[str, set[str]]
        Mapping from each destination row to the active sources that already
        drive it.
    """
    grouped: dict[str, set[str]] = {}
    for row, source in pairs:
        grouped.setdefault(row, set()).add(source)
    return grouped


def _routing_track_groups(
    tile_model: RoutingTileModel,
    available_wires: list[str],
) -> list[RoutingTrackGroup]:
    """Build routing groups from tile ports visible in the switch matrix.

    Parameters
    ----------
    tile_model : RoutingTileModel
        Tile model containing FABulous routing port declarations.
    available_wires : list[str]
        Switch-matrix rows and columns currently present in the graph.

    Returns
    -------
    list[RoutingTrackGroup]
        Directional routing groups whose expanded destination rows or
        selectable source columns exist in ``available_wires``.
    """
    available = set(available_wires)
    groups: list[RoutingTrackGroup] = []
    for port in tile_model.ports:
        destination_rows = [
            wire
            for wire in _declared_wire_names(
                source_name=port.source_name,
                destination_name="NULL",
                direction=port.direction,
                x_offset=port.x_offset,
                y_offset=port.y_offset,
                wire_count=port.wire_count,
            )
            if wire in available
        ]
        selectable_sources = [
            wire
            for wire in _declared_wire_names(
                source_name="NULL",
                destination_name=port.destination_name,
                direction=port.direction,
                x_offset=port.x_offset,
                y_offset=port.y_offset,
                wire_count=port.wire_count,
            )
            if wire in available
        ]
        if destination_rows or selectable_sources:
            groups.append(
                RoutingTrackGroup(
                    direction=port.direction,
                    source_name=port.source_name,
                    x_offset=port.x_offset,
                    y_offset=port.y_offset,
                    destination_name=port.destination_name,
                    wire_count=port.wire_count,
                    destination_rows=destination_rows,
                    selectable_sources=selectable_sources,
                )
            )
    return groups


def _declared_wire_names(
    *,
    source_name: str,
    destination_name: str,
    direction: Direction,
    x_offset: int,
    y_offset: int,
    wire_count: int,
) -> list[str]:
    """Expand one FABulous routing declaration into concrete wire names.

    Parameters
    ----------
    source_name : str
        FABulous source base name, or ``"NULL"`` when the declaration only
        contributes destination wires.
    destination_name : str
        FABulous destination base name, or ``"NULL"`` when the declaration
        only contributes source wires.
    direction : Direction
        Routing direction for the declaration.
    x_offset : int
        Horizontal routing offset from the tile.
    y_offset : int
        Vertical routing offset from the tile.
    wire_count : int
        Number of wires declared for the routing resource.

    Returns
    -------
    list[str]
        Concrete matrix wire names such as ``NBEG0`` or ``NEND0``.
    """
    expanded_count = wire_count
    if direction is not Direction.JUMP and (
        source_name == "NULL" or destination_name == "NULL"
    ):
        expanded_count *= abs(x_offset) + abs(y_offset)
    wires: list[str] = []
    for index in range(expanded_count):
        if source_name != "NULL":
            wires.append(f"{source_name}{index}")
        if destination_name != "NULL":
            wires.append(f"{destination_name}{index}")
    return wires


def _routing_source_pool(
    groups: list[RoutingTrackGroup],
    available_wires: list[str],
) -> list[str]:
    """Collect selectable routing-resource source columns.

    Parameters
    ----------
    groups : list[RoutingTrackGroup]
        Routing groups discovered from the tile model.
    available_wires : list[str]
        Switch-matrix rows and columns currently present in the graph.

    Returns
    -------
    list[str]
        Unique routing source columns, preserving model order.
    """
    available = set(available_wires)
    return _unique_items(
        source
        for group in groups
        for source in group.selectable_sources
        if source in available
    )


def _bel_input_wires(
    tile_model: RoutingTileModel,
    available_wires: list[str],
) -> list[str]:
    """Return BEL input wires that are switch-matrix rows or columns.

    Parameters
    ----------
    tile_model : RoutingTileModel
        Tile model with parsed BEL port metadata.
    available_wires : list[str]
        Switch-matrix rows and columns currently present in the graph.

    Returns
    -------
    list[str]
        Unique BEL input wires visible to the matrix, preserving BEL order.
    """
    available = set(available_wires)
    return _unique_items(
        wire for bel in tile_model.bels for wire in bel.inputs if wire in available
    )


def _bel_output_wires(
    tile_model: RoutingTileModel,
    available_wires: list[str],
) -> list[str]:
    """Return BEL output wires that can be used as matrix sources.

    Parameters
    ----------
    tile_model : RoutingTileModel
        Tile model with parsed BEL port metadata.
    available_wires : list[str]
        Switch-matrix rows and columns currently present in the graph.

    Returns
    -------
    list[str]
        Unique BEL output wires visible to the matrix, preserving BEL order.
    """
    available = set(available_wires)
    return _unique_items(
        wire for bel in tile_model.bels for wire in bel.outputs if wire in available
    )


def _constant_wires(available_wires: list[str]) -> list[str]:
    """Return known constant source wires present in the matrix.

    Parameters
    ----------
    available_wires : list[str]
        Switch-matrix rows and columns currently present in the graph.

    Returns
    -------
    list[str]
        Constant wire names from :data:`CONSTANT_WIRES` that exist in the
        current switch matrix.
    """
    available = set(available_wires)
    return [wire for wire in CONSTANT_WIRES if wire in available]


def _source_pool(
    *,
    routing_sources: list[str],
    bel_outputs: list[str],
    constant_sources: list[str],
    include_bel_output_sources: bool,
    include_constant_sources: bool,
) -> list[str]:
    """Build the shared source pool for generated matrix rows.

    Parameters
    ----------
    routing_sources : list[str]
        Routing-resource source columns.
    bel_outputs : list[str]
        BEL output wires visible to the matrix.
    constant_sources : list[str]
        Constant source wires visible to the matrix.
    include_bel_output_sources : bool
        Whether BEL outputs may be used as generated sources.
    include_constant_sources : bool
        Whether constant wires may be used as generated sources.

    Returns
    -------
    list[str]
        Unique source pool, preserving routing sources before optional BEL and
        constant sources.
    """
    sources = list(routing_sources)
    if include_bel_output_sources:
        sources.extend(bel_outputs)
    if include_constant_sources:
        sources.extend(constant_sources)
    return _unique_items(sources)


def _bel_input_pairs(
    *,
    bel_inputs: list[str],
    sources: list[str],
    fanin: int,
) -> list[MatrixPair]:
    """Generate matrix pairs that make BEL inputs reachable.

    Parameters
    ----------
    bel_inputs : list[str]
        BEL input rows to drive.
    sources : list[str]
        Candidate source columns.
    fanin : int
        Maximum number of sources to connect to each BEL input row.

    Returns
    -------
    list[MatrixPair]
        Generated ``(BEL input row, source)`` pairs. Source selection rotates
        by row index so adjacent inputs do not all receive the same prefix of
        the source pool.
    """
    pairs: list[MatrixPair] = []
    for row_index, bel_input in enumerate(bel_inputs):
        for source in _rotating_sources(sources, row_index, fanin):
            append_pair(pairs, bel_input, source)
    return pairs


def _output_coverage_pairs(
    *,
    groups: list[RoutingTrackGroup],
    sources: list[str],
    fanin: int,
    active_by_row: dict[str, set[str]],
    enabled: bool,
) -> list[MatrixPair]:
    """Generate fallback source pairs for uncovered routing output rows.

    Parameters
    ----------
    groups : list[RoutingTrackGroup]
        Routing groups containing destination output rows.
    sources : list[str]
        Candidate source columns.
    fanin : int
        Maximum number of sources to connect to each uncovered row.
    active_by_row : dict[str, set[str]]
        Existing active sources grouped by row. Rows present in this mapping
        are treated as already covered.
    enabled : bool
        Whether output-row coverage generation is enabled.

    Returns
    -------
    list[MatrixPair]
        Generated coverage pairs, or an empty list when disabled.
    """
    if not enabled:
        return []
    pairs: list[MatrixPair] = []
    output_rows = _unique_items(
        row for group in groups for row in group.destination_rows
    )
    for row_index, output_row in enumerate(output_rows):
        if active_by_row.get(output_row):
            continue
        for source in _rotating_sources(sources, row_index, fanin):
            append_pair(pairs, output_row, source)
    return pairs


def _apply_bel_input_hierarchy(
    *,
    fpga_model: PnRBridge,
    tile_name: str,
    direct_pairs: list[MatrixPair],
    options: SwitchMatrixPatternOptions,
) -> _HierarchyResult:
    """Replace direct BEL input fanin with generated local JUMP stages.

    Parameters
    ----------
    fpga_model : PnRBridge
        FPGA model exposing graph edit operations.
    tile_name : str
        Tile type receiving hierarchy resources.
    direct_pairs : list[MatrixPair]
        Direct ``(BEL input row, source)`` pairs to transform into hierarchy
        connections.
    options : SwitchMatrixPatternOptions
        Pattern options controlling hierarchy fanin, naming, and delay.

    Returns
    -------
    _HierarchyResult
        Generated hierarchy matrix pairs and count of newly added JUMP
        resources.
    """
    pairs: list[MatrixPair] = []
    added_jump_wires = 0
    grouped: dict[str, list[str]] = {}
    for destination, source in direct_pairs:
        grouped.setdefault(destination, []).append(source)

    available = set(fpga_model.matrix_sources(tile_name))
    for destination_index, (destination, sources) in enumerate(grouped.items()):
        current_sources = _unique_items(sources)
        for level_index, fanin in enumerate(options.hierarchy_levels):
            if len(current_sources) <= 1:
                break
            next_sources: list[str] = []
            for chunk_index, chunk in enumerate(_chunks(current_sources, fanin)):
                base = _hierarchy_base_name(
                    options.hierarchy_jump_prefix,
                    destination,
                    destination_index,
                    level_index,
                    chunk_index,
                )
                beg_base = f"{base}_BEG"
                end_base = f"{base}_END"
                beg_wire = f"{beg_base}0"
                end_wire = f"{end_base}0"
                if beg_wire not in available or end_wire not in available:
                    fpga_model.add_external_resource(
                        tile_name,
                        Direction.JUMP,
                        beg_base,
                        0,
                        0,
                        end_base,
                        1,
                        delay=options.delay,
                    )
                    available.update((beg_wire, end_wire))
                    added_jump_wires += 1
                for source in chunk:
                    append_pair(pairs, beg_wire, source)
                next_sources.append(end_wire)
            current_sources = next_sources
        for source in current_sources:
            append_pair(pairs, destination, source)
    return _HierarchyResult(
        pairs=unique_pairs(pairs), added_jump_wires=added_jump_wires
    )


def _hierarchy_base_name(
    prefix: str,
    destination: str,
    destination_index: int,
    level_index: int,
    chunk_index: int,
) -> str:
    """Return a deterministic base name for one generated JUMP resource.

    Parameters
    ----------
    prefix : str
        User-selected hierarchy wire prefix.
    destination : str
        Final BEL input destination row.
    destination_index : int
        Stable index of the destination row in the generated hierarchy order.
    level_index : int
        Hierarchy level being generated.
    chunk_index : int
        Chunk index within the hierarchy level.

    Returns
    -------
    str
        Sanitized base name used for the generated ``*_BEG`` and ``*_END``
        JUMP resource endpoints.
    """
    token = re.sub(r"[^A-Za-z0-9_]", "_", destination).strip("_") or "ROW"
    return f"{prefix}_D{destination_index}_{token}_L{level_index}_{chunk_index}"


def _replace_switch_matrix(
    fpga_model: PnRBridge,
    tile_name: str,
    pairs: list[MatrixPair],
    delay: float,
) -> None:
    """Replace a graph switch matrix with exactly the generated pairs.

    Parameters
    ----------
    fpga_model : PnRBridge
        FPGA model exposing graph edit operations.
    tile_name : str
        Tile type whose switch matrix is replaced.
    pairs : list[MatrixPair]
        Active ``(row, source)`` pairs for the replacement matrix.
    delay : float
        Delay value stored for each generated active pair.
    """
    rows = _unique_items(row for row, _source in pairs)
    columns = _unique_items(source for _row, source in pairs)
    row_index = {row: index for index, row in enumerate(rows)}
    column_index = {column: index for index, column in enumerate(columns)}
    matrix = [[0.0 for _column in columns] for _row in rows]
    for row, source in pairs:
        matrix[row_index[row]][column_index[source]] = delay
    fpga_model.set_switch_matrix(tile_name, columns, rows, matrix)


def _delete_active_rows(
    fpga_model: PnRBridge,
    tile_name: str,
    active_pairs_: list[MatrixPair],
    target_rows: set[str],
) -> set[MatrixPair]:
    """Delete existing active pairs for selected destination rows.

    Parameters
    ----------
    fpga_model : PnRBridge
        FPGA model exposing graph edit operations.
    tile_name : str
        Tile type whose matrix rows are edited.
    active_pairs_ : list[MatrixPair]
        Active matrix pairs captured before generation.
    target_rows : set[str]
        Destination rows whose active pairs should be removed.

    Returns
    -------
    set[MatrixPair]
        Pairs deleted from the graph.
    """
    deleted: set[MatrixPair] = set()
    for row, source in active_pairs_:
        if row not in target_rows:
            continue
        fpga_model.delete_matrix_resource(tile_name, row, source)
        deleted.add((row, source))
    return deleted


def _allow_group_pair(
    destination_group: RoutingTrackGroup,
    source_group: RoutingTrackGroup,
    options: SwitchMatrixPatternOptions,
) -> bool:
    """Return whether routing options allow one group-to-group connection.

    Parameters
    ----------
    destination_group : RoutingTrackGroup
        Destination routing group being driven.
    source_group : RoutingTrackGroup
        Candidate source routing group.
    options : SwitchMatrixPatternOptions
        Pattern options containing straight and turn enable flags.

    Returns
    -------
    bool
        ``True`` when same-direction connections are enabled for straight
        routes, or different-direction connections are enabled for turns.
    """
    same_direction = destination_group.direction == source_group.direction
    if same_direction:
        return options.generate_straight_routing_pips
    return options.generate_turn_routing_pips


def _rotating_sources(sources: list[str], row_index: int, fanin: int) -> list[str]:
    """Return a deterministic fanin-limited source slice for one row.

    Parameters
    ----------
    sources : list[str]
        Candidate source pool.
    row_index : int
        Index of the destination row being generated.
    fanin : int
        Maximum number of sources to return.

    Returns
    -------
    list[str]
        Rotated source subset. Rotation spreads fanin across rows while
        keeping generation deterministic.
    """
    if not sources:
        return []
    count = min(fanin, len(sources))
    return [sources[(row_index + offset) % len(sources)] for offset in range(count)]


def _chunks(items: list[str], chunk_size: int) -> list[list[str]]:
    """Split items into fixed-size chunks.

    Parameters
    ----------
    items : list[str]
        Items to split.
    chunk_size : int
        Maximum chunk size.

    Returns
    -------
    list[list[str]]
        Contiguous chunks in original order.
    """
    return [
        items[index : index + chunk_size] for index in range(0, len(items), chunk_size)
    ]


def _unique_items(items: Iterable[str]) -> list[str]:
    """Return unique string items while preserving first occurrence order.

    Parameters
    ----------
    items : Iterable[str]
        Items to deduplicate.

    Returns
    -------
    list[str]
        Deduplicated items in first-seen order.
    """
    return list(dict.fromkeys(items))

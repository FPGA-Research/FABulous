"""Generate a sparse LUT/carry-oriented switch-matrix pattern.

This pattern is designed for tiles that contain several LUT-like BELs with
ordinary data inputs, optional enable/reset pins, and carry-style pins.  It
starts from a Wilton-like route-through pattern, then adds the extra local PIPs
that these LUT tiles need for practical placement and routing: routing-track
ingress into LUT inputs, LUT/carry egress back to routing tracks, constants,
local feedback, and adjacent carry chaining.

Attributes
----------
_DIRECTION_ORDER : tuple[Direction, ...]
    Cardinal direction order used for deterministic balancing.
_LUT_INPUT_SUFFIXES : frozenset[str]
    BEL pin suffixes treated as LUT or carry data inputs.
_LOCAL_FEEDBACK_INPUT_SUFFIXES : frozenset[str]
    Input suffixes that may receive local LUT-output feedback.
_LUT_OUTPUT_SUFFIXES : frozenset[str]
    BEL output suffixes that may drive routing tracks or local feedback.
_CONTROL_INPUT_SUFFIXES : frozenset[str]
    Shared control pin suffixes, currently enable and reset.
_INPUT_INGRESS_FANIN_PER_GROUP : int
    Maximum routing sources used per routing group for each LUT input.
_CONTROL_INGRESS_FANIN_PER_GROUP : int
    Maximum routing sources used per routing group for each control input.
_MAX_OUTPUT_EGRESS_ROWS_PER_GROUP : int
    Maximum routing rows driven by each normal LUT output per routing group.
_MAX_CARRY_EGRESS_ROWS_PER_GROUP : int
    Maximum routing rows driven by each carry output per routing group.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from fabulous.fabric_cad.fabxplore.modules.routing_patterns.core.models import (
    RoutingPipPattern,
    SwitchMatrixPatternApplyResult,
    SwitchMatrixPatternImplementation,
    SwitchMatrixPatternOptions,
)
from fabulous.fabric_cad.fabxplore.modules.routing_patterns.patterns.common import (
    CONSTANT_WIRES,
    MatrixPair,
    RoutingTrackGroup,
    allowed_source_groups,
    append_pair,
    apply_pattern_pairs,
    cardinal_routable_groups,
    routing_pattern_warnings,
    routing_track_groups,
    row_pair_count,
    unique_pairs,
)
from fabulous.fabric_definition.define import Direction

if TYPE_CHECKING:
    from collections.abc import Iterable

    from fabulous.fabric_cad.fabxplore.pnr.fab_graph.core.models import (
        RoutingTileBelModel,
    )
    from fabulous.fabric_cad.fabxplore.pnr.pnr_bridge import PnRBridge

_DIRECTION_ORDER = (
    Direction.NORTH,
    Direction.EAST,
    Direction.SOUTH,
    Direction.WEST,
)
_LUT_INPUT_SUFFIXES = frozenset(("I0", "I1", "I2", "A0", "B0", "S", "Ci"))
_LOCAL_FEEDBACK_INPUT_SUFFIXES = frozenset(("I0", "I1", "Ci"))
_LUT_OUTPUT_SUFFIXES = frozenset(("O", "O0", "O1", "Q", "Q0", "Q1", "Co"))
_CONTROL_INPUT_SUFFIXES = frozenset(("SR", "EN"))
_CARRY_INPUT_SUFFIX = "Ci"
_CARRY_OUTPUT_SUFFIX = "Co"
_INPUT_INGRESS_FANIN_PER_GROUP = 1
_CONTROL_INGRESS_FANIN_PER_GROUP = 1
_MAX_OUTPUT_EGRESS_ROWS_PER_GROUP = 1
_MAX_CARRY_EGRESS_ROWS_PER_GROUP = 2


class LutCarryRichRoutingPattern(SwitchMatrixPatternImplementation):
    """Apply Wilton route-throughs plus richer LUT/carry access PIPs.

    The implementation is stateless.  All generated PIPs are derived from the supplied
    FPGA model, the selected tile name, and the normalized pattern options.
    """

    def apply(
        self,
        fpga_model: PnRBridge,
        options: SwitchMatrixPatternOptions,
    ) -> SwitchMatrixPatternApplyResult:
        """Apply the LUT/carry-rich pattern to the FPGA model.

        Parameters
        ----------
        fpga_model : PnRBridge
            FPGA model exposing the FabGraph API.
        options : SwitchMatrixPatternOptions
            Normalized pattern options.

        Returns
        -------
        SwitchMatrixPatternApplyResult
            Applied edit counts and warnings.
        """
        groups = routing_track_groups(fpga_model, options.tile_name)
        compatible_groups = cardinal_routable_groups(groups)
        routing_pairs = unique_pairs(
            _wilton_routing_pairs(compatible_groups, options)
            + _lut_input_ingress_pairs(fpga_model, options, compatible_groups)
            + _lut_output_egress_pairs(
                fpga_model,
                options.tile_name,
                compatible_groups,
            )
            + _bel_constant_ingress_pairs(fpga_model, options.tile_name)
            + _control_input_ingress_pairs(
                fpga_model,
                options,
                compatible_groups,
            )
            + _local_carry_chain_pairs(fpga_model, options.tile_name)
            + _local_lut_feedback_pairs(fpga_model, options.tile_name)
        )
        return apply_pattern_pairs(
            fpga_model,
            options,
            groups=groups,
            routing_pairs=routing_pairs,
            compatible_routing_groups=len(compatible_groups),
            routing_warnings=routing_pattern_warnings(
                RoutingPipPattern.LUT_CARRY_RICH,
                compatible_groups,
                routing_pairs,
            ),
        )


def _wilton_routing_pairs(
    groups: list[RoutingTrackGroup],
    options: SwitchMatrixPatternOptions,
) -> list[MatrixPair]:
    """Generate direction-balanced side-dependent route-through pairs.

    Parameters
    ----------
    groups : list[RoutingTrackGroup]
        Routing track groups whose destination rows should receive route-through
        sources.
    options : SwitchMatrixPatternOptions
        Pattern options controlling the route-through fan-in.

    Returns
    -------
    list[MatrixPair]
        Unique ``(destination_row, source_column)`` pairs for side-to-side
        routing.
    """
    pairs: list[MatrixPair] = []
    for destination_group in groups:
        for row_index, destination_row in enumerate(destination_group.destination_rows):
            source_groups = _direction_balanced_source_groups(
                allowed_source_groups(
                    destination_group,
                    groups,
                    options,
                )
            )
            for source_group in source_groups:
                source_count = len(source_group.selectable_sources)
                offset = _wilton_offset(destination_group, source_group, source_count)
                source = source_group.selectable_sources[
                    (row_index + offset) % source_count
                ]
                append_pair(pairs, destination_row, source)
                if row_pair_count(pairs, destination_row) >= options.routing_pip_fs:
                    break
    return unique_pairs(pairs)


def _lut_input_ingress_pairs(
    fpga_model: PnRBridge,
    options: SwitchMatrixPatternOptions,
    groups: list[RoutingTrackGroup],
) -> list[MatrixPair]:
    """Connect LUT-like BEL inputs to routing tracks.

    Parameters
    ----------
    fpga_model : PnRBridge
        FPGA model containing the tile and switch-matrix metadata.
    options : SwitchMatrixPatternOptions
        Pattern options containing the target tile name and routing fan-in.
    groups : list[RoutingTrackGroup]
        Routing track groups used as possible sources for BEL inputs.

    Returns
    -------
    list[MatrixPair]
        Unique pairs that drive LUT input rows from routing source columns.
    """
    available = set(fpga_model.matrix_sources(options.tile_name))
    lut_bels = _lut_bels(fpga_model, options.tile_name, available)
    if not lut_bels:
        return []

    pairs: list[MatrixPair] = []
    fanin_per_group = min(
        max(1, options.routing_pip_fs),
        _INPUT_INGRESS_FANIN_PER_GROUP,
    )
    for bel_index, bel in enumerate(lut_bels):
        bel_inputs = [
            wire
            for wire in bel.inputs
            if wire in available and _wire_suffix(wire) in _LUT_INPUT_SUFFIXES
        ]
        for group_index, group in enumerate(groups):
            sources = group.selectable_sources
            if not sources:
                continue
            base_index = _bel_pair_lane_index(bel_index, len(sources), group_index)
            for offset in range(min(fanin_per_group, len(sources))):
                source = sources[(base_index + offset) % len(sources)]
                for bel_input in bel_inputs:
                    append_pair(pairs, bel_input, source)
    return unique_pairs(pairs)


def _bel_constant_ingress_pairs(
    fpga_model: PnRBridge,
    tile_name: str,
) -> list[MatrixPair]:
    """Connect local constant columns to matrix-visible BEL inputs.

    Parameters
    ----------
    fpga_model : PnRBridge
        FPGA model containing tile metadata.
    tile_name : str
        Name of the tile whose switch matrix is edited.

    Returns
    -------
    list[MatrixPair]
        Unique pairs from local constant columns, such as GND/VCC, to BEL input
        rows.  An empty list is returned when the tile has no visible constant
        sources.
    """
    available = set(fpga_model.matrix_sources(tile_name))
    constant_sources = [wire for wire in CONSTANT_WIRES if wire in available]
    if not constant_sources:
        return []

    return unique_pairs(
        [
            (bel_input, constant_source)
            for bel_input in _bel_input_wires(fpga_model, tile_name, available)
            for constant_source in constant_sources
            if bel_input != constant_source
        ]
    )


def _lut_output_egress_pairs(
    fpga_model: PnRBridge,
    tile_name: str,
    groups: list[RoutingTrackGroup],
) -> list[MatrixPair]:
    """Allow LUT outputs to enter each routing direction explicitly.

    Parameters
    ----------
    fpga_model : PnRBridge
        FPGA model containing tile metadata.
    tile_name : str
        Name of the tile whose switch matrix is edited.
    groups : list[RoutingTrackGroup]
        Routing track groups whose destination rows may be driven by LUT
        outputs.

    Returns
    -------
    list[MatrixPair]
        Unique pairs from LUT/carry output columns to routing destination rows.
    """
    available = set(fpga_model.matrix_sources(tile_name))
    lut_outputs = _lut_output_wires(fpga_model, tile_name, available)
    if not lut_outputs:
        return []

    pairs: list[MatrixPair] = []
    output_to_bel_index = _lut_output_bel_indices(
        fpga_model,
        tile_name,
        available,
    )
    for output_index, lut_output in enumerate(lut_outputs):
        bel_index = output_to_bel_index.get(lut_output, output_index)
        for group_index, group in enumerate(groups):
            destination_rows = group.destination_rows
            if not destination_rows:
                continue
            row_count = len(destination_rows)
            row_budget = (
                _MAX_CARRY_EGRESS_ROWS_PER_GROUP
                if _wire_suffix(lut_output) == _CARRY_OUTPUT_SUFFIX
                else _MAX_OUTPUT_EGRESS_ROWS_PER_GROUP
            )
            row_budget = min(row_count, row_budget)
            start = _bel_pair_lane_index(bel_index, row_count, group_index)
            for offset in range(row_budget):
                row_index = (start + offset) % row_count
                append_pair(pairs, destination_rows[row_index], lut_output)
    return unique_pairs(pairs)


def _local_carry_chain_pairs(
    fpga_model: PnRBridge,
    tile_name: str,
) -> list[MatrixPair]:
    """Add adjacent in-tile carry-output to carry-input shortcuts.

    Parameters
    ----------
    fpga_model : PnRBridge
        FPGA model containing tile metadata.
    tile_name : str
        Name of the tile whose switch matrix is edited.

    Returns
    -------
    list[MatrixPair]
        Unique pairs connecting each visible carry output to the next BEL's
        visible carry input.
    """
    available = set(fpga_model.matrix_sources(tile_name))
    carry_bels = _carry_bels(fpga_model, tile_name, available)
    pairs: list[MatrixPair] = []
    for index, bel in enumerate(carry_bels[:-1]):
        source = _suffix_wire(bel.outputs, _CARRY_OUTPUT_SUFFIX, available)
        destination = _suffix_wire(
            carry_bels[index + 1].inputs,
            _CARRY_INPUT_SUFFIX,
            available,
        )
        if source is not None and destination is not None:
            append_pair(pairs, destination, source)
    return unique_pairs(pairs)


def _local_lut_feedback_pairs(
    fpga_model: PnRBridge,
    tile_name: str,
) -> list[MatrixPair]:
    """Add local and adjacent LUT-output feedback into LUT-like inputs.

    Parameters
    ----------
    fpga_model : PnRBridge
        FPGA model containing tile metadata.
    tile_name : str
        Name of the tile whose switch matrix is edited.

    Returns
    -------
    list[MatrixPair]
        Unique pairs that let a LUT output feed its own BEL and neighboring BELs
        through selected local input rows.
    """
    available = set(fpga_model.matrix_sources(tile_name))
    lut_bels = _lut_bels(fpga_model, tile_name, available)
    pairs: list[MatrixPair] = []
    for source_index, source_bel in enumerate(lut_bels):
        sources = [
            wire
            for wire in source_bel.outputs
            if wire in available and _wire_suffix(wire) in _LUT_OUTPUT_SUFFIXES
        ]
        if not sources:
            continue
        for destination_index in _feedback_destination_indices(
            source_index,
            len(lut_bels),
        ):
            for destination in lut_bels[destination_index].inputs:
                if (
                    destination in available
                    and _wire_suffix(destination) in _LOCAL_FEEDBACK_INPUT_SUFFIXES
                ):
                    for source in sources:
                        append_pair(pairs, destination, source)
    return unique_pairs(pairs)


def _control_input_ingress_pairs(
    fpga_model: PnRBridge,
    options: SwitchMatrixPatternOptions,
    groups: list[RoutingTrackGroup],
) -> list[MatrixPair]:
    """Give shared enable/reset pins direct access to routing tracks.

    Parameters
    ----------
    fpga_model : PnRBridge
        FPGA model containing tile metadata.
    options : SwitchMatrixPatternOptions
        Pattern options containing the target tile name and routing fan-in.
    groups : list[RoutingTrackGroup]
        Routing track groups used as possible sources for control input rows.

    Returns
    -------
    list[MatrixPair]
        Unique pairs that drive enable/reset-style BEL input rows from routing
        source columns and destination-row wires that are visible as sources.
    """
    available = set(fpga_model.matrix_sources(options.tile_name))
    control_inputs = _control_input_wires(fpga_model, options.tile_name, available)
    if not control_inputs:
        return []

    pairs: list[MatrixPair] = []
    fanin_per_group = min(
        max(1, options.routing_pip_fs),
        _CONTROL_INGRESS_FANIN_PER_GROUP,
    )
    for row_index, control_input in enumerate(control_inputs):
        for group_index, group in enumerate(groups):
            sources = _group_wire_sources(group, available)
            if not sources:
                continue
            for offset in range(min(fanin_per_group, len(sources))):
                source_index = row_index + group_index + offset
                append_pair(
                    pairs,
                    control_input,
                    sources[source_index % len(sources)],
                )
    return unique_pairs(pairs)


def _lut_output_bel_indices(
    fpga_model: PnRBridge,
    tile_name: str,
    available: set[str],
) -> dict[str, int]:
    """Map LUT-like output wires to their BEL index in tile order.

    Parameters
    ----------
    fpga_model : PnRBridge
        FPGA model containing tile metadata.
    tile_name : str
        Name of the tile being inspected.
    available : set[str]
        Matrix source names visible in the tile switch matrix.

    Returns
    -------
    dict[str, int]
        Mapping from output wire name to the zero-based BEL index that owns it.
    """
    result: dict[str, int] = {}
    for bel_index, bel in enumerate(_lut_bels(fpga_model, tile_name, available)):
        for wire in bel.outputs:
            if wire in available and _wire_suffix(wire) in _LUT_OUTPUT_SUFFIXES:
                result[wire] = bel_index
    return result


def _bel_pair_lane_index(
    bel_index: int,
    lane_count: int,
    group_index: int,
) -> int:
    """Return a sparse routing lane shared by adjacent LUT BEL pairs.

    Parameters
    ----------
    bel_index : int
        Zero-based BEL index in tile order.
    lane_count : int
        Number of candidate rows or columns in the current routing group.
    group_index : int
        Zero-based routing group index.

    Returns
    -------
    int
        Lane index used to spread adjacent BEL pairs over the available lanes.
    """
    if lane_count <= 1:
        return 0
    pair_base = (bel_index // 2) * 2
    return (pair_base + group_index) % lane_count


def _direction_balanced_source_groups(
    groups: list[RoutingTrackGroup],
) -> list[RoutingTrackGroup]:
    """Return source groups interleaved by cardinal direction.

    Parameters
    ----------
    groups : list[RoutingTrackGroup]
        Candidate routing groups, usually already filtered for compatibility
        with one destination group.

    Returns
    -------
    list[RoutingTrackGroup]
        Groups ordered as N/E/S/W rounds so sparse fan-in still sees directional
        diversity before repeating the same direction.
    """
    groups_by_direction = {
        direction: [
            group
            for group in groups
            if group.direction is direction and group.selectable_sources
        ]
        for direction in _DIRECTION_ORDER
    }
    max_groups = max(
        (len(direction_groups) for direction_groups in groups_by_direction.values()),
        default=0,
    )
    balanced: list[RoutingTrackGroup] = []
    for group_index in range(max_groups):
        for direction in _DIRECTION_ORDER:
            direction_groups = groups_by_direction[direction]
            if group_index < len(direction_groups):
                balanced.append(direction_groups[group_index])
    return balanced


def _lut_input_wires(
    fpga_model: PnRBridge,
    tile_name: str,
    available: set[str],
) -> list[str]:
    """Return LUT-like BEL input wires visible to the matrix.

    Parameters
    ----------
    fpga_model : PnRBridge
        FPGA model containing tile metadata.
    tile_name : str
        Name of the tile being inspected.
    available : set[str]
        Matrix source names visible in the tile switch matrix.

    Returns
    -------
    list[str]
        Unique LUT-like input wires in tile model order.
    """
    return _unique_visible_wires(
        wire
        for bel in fpga_model.tile_model(tile_name).bels
        for wire in bel.inputs
        if _wire_suffix(wire) in _LUT_INPUT_SUFFIXES and wire in available
    )


def _bel_input_wires(
    fpga_model: PnRBridge,
    tile_name: str,
    available: set[str],
) -> list[str]:
    """Return BEL input wires visible to the matrix.

    Parameters
    ----------
    fpga_model : PnRBridge
        FPGA model containing tile metadata.
    tile_name : str
        Name of the tile being inspected.
    available : set[str]
        Matrix source names visible in the tile switch matrix.

    Returns
    -------
    list[str]
        Unique BEL input wires in tile model order.
    """
    return _unique_visible_wires(
        wire
        for bel in fpga_model.tile_model(tile_name).bels
        for wire in bel.inputs
        if wire in available
    )


def _control_input_wires(
    fpga_model: PnRBridge,
    tile_name: str,
    available: set[str],
) -> list[str]:
    """Return enable/reset-style BEL input wires visible to the matrix.

    Parameters
    ----------
    fpga_model : PnRBridge
        FPGA model containing tile metadata.
    tile_name : str
        Name of the tile being inspected.
    available : set[str]
        Matrix source names visible in the tile switch matrix.

    Returns
    -------
    list[str]
        Unique control input wires in tile model order.
    """
    return _unique_visible_wires(
        wire
        for bel in fpga_model.tile_model(tile_name).bels
        for wire in bel.inputs
        if _wire_suffix(wire) in _CONTROL_INPUT_SUFFIXES and wire in available
    )


def _lut_output_wires(
    fpga_model: PnRBridge,
    tile_name: str,
    available: set[str],
) -> list[str]:
    """Return LUT output wires visible to the matrix.

    Parameters
    ----------
    fpga_model : PnRBridge
        FPGA model containing tile metadata.
    tile_name : str
        Name of the tile being inspected.
    available : set[str]
        Matrix source names visible in the tile switch matrix.

    Returns
    -------
    list[str]
        Unique LUT-like output wires in tile model order.
    """
    return _unique_visible_wires(
        wire
        for bel in fpga_model.tile_model(tile_name).bels
        for wire in bel.outputs
        if _wire_suffix(wire) in _LUT_OUTPUT_SUFFIXES and wire in available
    )


def _carry_bels(
    fpga_model: PnRBridge,
    tile_name: str,
    available: set[str],
) -> list[RoutingTileBelModel]:
    """Return BELs with matrix-visible carry input and output wires.

    Parameters
    ----------
    fpga_model : PnRBridge
        FPGA model containing tile metadata.
    tile_name : str
        Name of the tile being inspected.
    available : set[str]
        Matrix source names visible in the tile switch matrix.

    Returns
    -------
    list[RoutingTileBelModel]
        BELs that expose both ``Ci`` and ``Co`` through the matrix.
    """
    return [
        bel
        for bel in fpga_model.tile_model(tile_name).bels
        if _suffix_wire(bel.inputs, _CARRY_INPUT_SUFFIX, available) is not None
        and _suffix_wire(bel.outputs, _CARRY_OUTPUT_SUFFIX, available) is not None
    ]


def _lut_bels(
    fpga_model: PnRBridge,
    tile_name: str,
    available: set[str],
) -> list[RoutingTileBelModel]:
    """Return BELs with matrix-visible LUT-like inputs and outputs.

    Parameters
    ----------
    fpga_model : PnRBridge
        FPGA model containing tile metadata.
    tile_name : str
        Name of the tile being inspected.
    available : set[str]
        Matrix source names visible in the tile switch matrix.

    Returns
    -------
    list[RoutingTileBelModel]
        BELs that have at least one visible LUT-like input and one visible
        LUT-like output.
    """
    return [
        bel
        for bel in fpga_model.tile_model(tile_name).bels
        if any(
            wire in available and _wire_suffix(wire) in _LUT_INPUT_SUFFIXES
            for wire in bel.inputs
        )
        and any(
            wire in available and _wire_suffix(wire) in _LUT_OUTPUT_SUFFIXES
            for wire in bel.outputs
        )
    ]


def _suffix_wire(
    wires: tuple[str, ...],
    suffix: str,
    available: set[str],
) -> str | None:
    """Return the first visible wire with the requested suffix.

    Parameters
    ----------
    wires : tuple[str, ...]
        Candidate wire names from one BEL pin list.
    suffix : str
        Required suffix after the final underscore.
    available : set[str]
        Matrix source names visible in the tile switch matrix.

    Returns
    -------
    str | None
        First visible matching wire, or ``None`` if no candidate matches.
    """
    for wire in wires:
        if wire in available and _wire_suffix(wire) == suffix:
            return wire
    return None


def _wire_suffix(wire: str) -> str:
    """Return the suffix after the final BEL-prefix underscore.

    Parameters
    ----------
    wire : str
        Matrix wire name, usually in ``BEL_PIN`` form.

    Returns
    -------
    str
        Suffix after the final underscore.  Names without underscores are
        returned unchanged.
    """
    return wire.rsplit("_", maxsplit=1)[-1]


def _unique_visible_wires(wires: Iterable[str]) -> list[str]:
    """Return unique wires while preserving model order.

    Parameters
    ----------
    wires : Iterable[str]
        Candidate wire names.

    Returns
    -------
    list[str]
        First occurrence of each string wire, preserving input order.
    """
    result: list[str] = []
    seen: set[str] = set()
    for wire in wires:
        if not isinstance(wire, str) or wire in seen:
            continue
        seen.add(wire)
        result.append(wire)
    return result


def _feedback_destination_indices(source_index: int, count: int) -> tuple[int, ...]:
    """Return same-BEL and adjacent-BEL destinations for local feedback.

    Parameters
    ----------
    source_index : int
        Zero-based index of the BEL that owns the feedback source.
    count : int
        Number of LUT-like BELs in the tile.

    Returns
    -------
    tuple[int, ...]
        Destination BEL indices containing the source BEL and any immediate
        neighbors inside the tile.
    """
    if count <= 1:
        return (source_index,)
    indices = [source_index]
    if source_index > 0:
        indices.append(source_index - 1)
    if source_index + 1 < count:
        indices.append(source_index + 1)
    return tuple(indices)


def _group_wire_sources(
    group: RoutingTrackGroup,
    available: set[str],
) -> list[str]:
    """Return both ends of a routing group as possible control sources.

    Parameters
    ----------
    group : RoutingTrackGroup
        Routing group whose selectable source columns and destination rows are
        considered.
    available : set[str]
        Matrix source names visible in the tile switch matrix.

    Returns
    -------
    list[str]
        Unique visible wires from both sides of the group.
    """
    wires: list[str] = []
    max_count = max(len(group.selectable_sources), len(group.destination_rows))
    for index in range(max_count):
        if index < len(group.selectable_sources):
            wires.append(group.selectable_sources[index])
        if index < len(group.destination_rows):
            wires.append(group.destination_rows[index])
    return _unique_visible_wires(wire for wire in wires if wire in available)


def _wilton_offset(
    destination_group: RoutingTrackGroup,
    source_group: RoutingTrackGroup,
    source_count: int,
) -> int:
    """Return a deterministic side-dependent track permutation offset.

    Parameters
    ----------
    destination_group : RoutingTrackGroup
        Routing group that owns the destination row.
    source_group : RoutingTrackGroup
        Routing group used as the source column family.
    source_count : int
        Number of selectable sources in ``source_group``.

    Returns
    -------
    int
        Side-dependent offset for the Wilton-style source permutation.
    """
    if destination_group.direction == source_group.direction:
        return 0
    destination_index = _direction_index(destination_group.direction)
    source_index = _direction_index(source_group.direction)
    delta = (source_index - destination_index) % len(_DIRECTION_ORDER)
    return ((2 * delta) - 1) % source_count


def _direction_index(direction: Direction) -> int:
    """Return the ordering index for one routing direction.

    Parameters
    ----------
    direction : Direction
        Cardinal routing direction.

    Returns
    -------
    int
        Index of ``direction`` in ``_DIRECTION_ORDER``.
    """
    return _DIRECTION_ORDER.index(direction)


def _coprime_stride(count: int, seed: int) -> int:
    """Return a small deterministic stride that walks all rows before repeating.

    Parameters
    ----------
    count : int
        Number of lanes that should be covered.
    seed : int
        Deterministic seed used to derive the initial odd stride candidate.

    Returns
    -------
    int
        Positive stride coprime with ``count``.
    """
    if count <= 1:
        return 1
    stride = (2 * seed) + 1
    while _gcd(stride, count) != 1:
        stride += 2
    return stride % count or 1


def _gcd(lhs: int, rhs: int) -> int:
    """Return the greatest common divisor without importing another module.

    Parameters
    ----------
    lhs : int
        First integer.
    rhs : int
        Second integer.

    Returns
    -------
    int
        Non-negative greatest common divisor of both inputs.
    """
    while rhs:
        lhs, rhs = rhs, lhs % rhs
    return abs(lhs)

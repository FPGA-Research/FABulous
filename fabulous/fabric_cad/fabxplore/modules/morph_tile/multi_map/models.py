"""Typed records for multi-LUT morph-tile mapping.

The multi-map flow keeps its own result and replacement models because it replaces
several original LUT cells with one tile instance.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from fabulous.fabric_cad.fabxplore.modules.morph_tile.core.models import (
        CutSolveResult,
    )


@dataclass(frozen=True)
class PortBitRef:
    """Reference one bit of an original cell port.

    Attributes
    ----------
    cell_id : str
        Original cell name.
    port : str
        Cell port name without a leading backslash.
    index : int
        Port bit index.
    """

    cell_id: str
    port: str
    index: int = 0


InputPortSource = PortBitRef | int


@dataclass(frozen=True)
class LutNode:
    """Represent one LUT-mapped cell in the source design.

    Attributes
    ----------
    cell_id : str
        Source cell name.
    width : int
        LUT input width.
    init : int
        LSB-first LUT INIT value.
    input_tokens : tuple[str, ...]
        Net tokens connected to LUT input bits in INIT-index order.
    output_token : str
        Net token driven by the LUT output.
    input_refs : tuple[PortBitRef, ...]
        References to the input port bits carrying ``input_tokens``.
    output_ref : PortBitRef
        Reference to the output port bit carrying ``output_token``.
    """

    cell_id: str
    width: int
    init: int
    input_tokens: tuple[str, ...]
    output_token: str
    input_refs: tuple[PortBitRef, ...]
    output_ref: PortBitRef


@dataclass(frozen=True)
class LutGraph:
    """Store LUT nodes and basic net connectivity.

    Attributes
    ----------
    nodes : dict[str, LutNode]
        LUT nodes keyed by cell id.
    driver_by_token : dict[str, str]
        Mapping from output net token to driving LUT cell id.
    users_by_token : dict[str, tuple[str, ...]]
        Mapping from input net token to consuming LUT cell ids.
    external_user_tokens : frozenset[str]
        LUT output net tokens also touched by non-LUT cells. These tokens must
        stay visible as boundary outputs when their driving LUT is selected.
    """

    nodes: dict[str, LutNode]
    driver_by_token: dict[str, str]
    users_by_token: dict[str, tuple[str, ...]]
    external_user_tokens: frozenset[str] = field(default_factory=frozenset)


@dataclass(frozen=True)
class LutGroupCandidate:
    """Represent one candidate group of LUT cells.

    Attributes
    ----------
    lut_ids : tuple[str, ...]
        Grouped LUT cell ids.
    boundary_tokens : tuple[str, ...]
        Distinct non-constant net tokens entering the group.
    boundary_refs : dict[str, PortBitRef]
        Spec input name to original-cell port reference.
    output_refs : dict[str, PortBitRef]
        Spec output name to original LUT output reference.
    """

    lut_ids: tuple[str, ...]
    boundary_tokens: tuple[str, ...]
    boundary_refs: dict[str, PortBitRef]
    output_refs: dict[str, PortBitRef]


@dataclass(frozen=True)
class LutGroupTruth:
    """Store a group's multi-output truth tables.

    Attributes
    ----------
    input_names : list[str]
        Spec input names.
    output_inits : dict[str, int]
        Multi-output INITs keyed by spec output name.
    """

    input_names: list[str]
    output_inits: dict[str, int]


@dataclass(frozen=True)
class MultiMapMatch:
    """Store one successful group-to-tile match.

    Attributes
    ----------
    candidate : LutGroupCandidate
        Group that was checked.
    truth : LutGroupTruth
        Truth table used for the SAT check.
    result : CutSolveResult
        Decoded SAT result.
    score : int
        Greedy selection score.
    """

    candidate: LutGroupCandidate
    truth: LutGroupTruth
    result: CutSolveResult
    score: int


@dataclass(frozen=True)
class MultiMapReplacement:
    """Describe one multi-cell replacement.

    Attributes
    ----------
    original_cell_ids : tuple[str, ...]
        LUT cells removed by this replacement.
    replacement_cell_id : str
        New tile instance name.
    input_ports : dict[str, InputPortSource]
        Tile input ports wired from original source nets.
    output_ports : dict[str, PortBitRef]
        Tile output ports wired to original LUT output nets.
    config_bits : dict[str, bool | None]
        Solved tile configuration bits.
    input_mapping : dict[str, str]
        Candidate tile input to group spec input mapping.
    output_mapping : dict[str, str]
        Group spec output to candidate tile output mapping.
    """

    original_cell_ids: tuple[str, ...]
    replacement_cell_id: str
    input_ports: dict[str, InputPortSource]
    output_ports: dict[str, PortBitRef]
    config_bits: dict[str, bool | None]
    input_mapping: dict[str, str]
    output_mapping: dict[str, str]


@dataclass(frozen=True)
class MultiMapStats:
    """Summarize one multi-map run.

    Attributes
    ----------
    total_groups : int
        Groups sampled before filtering duplicates and failed checks.
    checked_groups : int
        Groups sent to sat_fab.
    sat_matches_total : int
        Total groups accepted by SAT before match-storage pruning.
    matched_groups : int
        Successful SAT matches retained after match-storage pruning.
    selected_groups : int
        Disjoint groups selected for replacement.
    replaced_luts : int
        Number of original LUT cells removed by selected groups.
    cache_hits : int
        SAT checks served by the permutation cache.
    cache_misses : int
        SAT checks computed from scratch.
    """

    total_groups: int = 0
    checked_groups: int = 0
    sat_matches_total: int = 0
    matched_groups: int = 0
    selected_groups: int = 0
    replaced_luts: int = 0
    cache_hits: int = 0
    cache_misses: int = 0


@dataclass(frozen=True)
class MultiMapResult:
    """Return data for one multi-map run.

    Attributes
    ----------
    top_name : str
        Processed top module.
    tile_top_name : str
        Tile module instantiated for replacements.
    options_summary : dict[str, list[str]]
        User-facing options summary.
    stats : MultiMapStats
        Aggregate mapping counters.
    replacements : tuple[MultiMapReplacement, ...]
        Applied multi-cell replacements.
    report_summary : str
        Human-readable report.
    metadata : dict[str, object]
        Optional auxiliary data for the outer morph-tile reporting adapter.
    """

    top_name: str
    tile_top_name: str
    options_summary: dict[str, list[str]]
    stats: MultiMapStats
    replacements: tuple[MultiMapReplacement, ...]
    report_summary: str = ""
    metadata: dict[str, object] = field(default_factory=dict)

"""Typed models for area-saving leftover optimization.

The reorder-opt stage consumes reusable leftover LUT capacity to remove whole pair
cells. It is similar to leftover reordering, but its objective is reducing the mapped
FRAC cell count instead of increasing future reusable capacity.
"""

from dataclasses import dataclass, field

from fabulous.fabric_cad.fabxplore.modules.lut_combinator.core.models import (
    MappingResult,
)


@dataclass(frozen=True)
class ReorderOptConfig:
    """Configure the reorder-opt area optimization.

    Attributes
    ----------
    require_saved_cell : bool
        If ``True``, only transformations that remove one donor pair cell are
        accepted. This is the intended safe mode for area optimization.
    max_host_candidates_per_side : int
        Maximum compatible hosts kept per moved LUT side while searching one
        donor pair. This bounds runtime on large designs while still trying the
        lowest-waste host choices first.
    """

    require_saved_cell: bool = True
    max_host_candidates_per_side: int = 32


@dataclass(frozen=True)
class ReorderOptMove:
    """Describe one applied reorder-opt transformation.

    Attributes
    ----------
    donor_packed_id : str
        Pair-cell FRAC instance removed by this optimization.
    host0_packed_id : str
        First single-cell host that receives one donor LUT.
    host1_packed_id : str
        Second single-cell host that receives one donor LUT.
    moved0_cell_id : str
        Donor LUT moved into ``host0_packed_id``.
    moved1_cell_id : str
        Donor LUT moved into ``host1_packed_id``.
    host0_width : int
        Original logical LUT width in host0.
    host1_width : int
        Original logical LUT width in host1.
    moved0_width : int
        Width of the LUT moved into host0.
    moved1_width : int
        Width of the LUT moved into host1.
    host0_effective_leftover : int
        Reusable effective leftover width in host0 before optimization.
    host1_effective_leftover : int
        Reusable effective leftover width in host1 before optimization.
    leftover_waste : int
        Unused host capacity after placing both moved LUTs.
    saved_cells : int
        Number of FRAC cells removed by this optimization.
    """

    donor_packed_id: str
    host0_packed_id: str
    host1_packed_id: str
    moved0_cell_id: str
    moved1_cell_id: str
    host0_width: int
    host1_width: int
    moved0_width: int
    moved1_width: int
    host0_effective_leftover: int
    host1_effective_leftover: int
    leftover_waste: int
    saved_cells: int = 1


@dataclass(frozen=True)
class ReorderOptStats:
    """Aggregate counters for one reorder-opt run.

    Attributes
    ----------
    candidate_hosts : int
        Number of single non-full FRAC cells considered as destinations.
    candidate_donors : int
        Number of dual FRAC cells considered for removal.
    legal_optimizations : int
        Number of legal donor/host-pair assignments found.
    applied_optimizations : int
        Number of optimizations selected after conflict resolution.
    frac_cells_before : int
        Number of mapped FRAC cells before reorder-opt.
    frac_cells_after : int
        Number of mapped FRAC cells after reorder-opt.
    frac_cells_saved : int
        Difference between before and after mapped FRAC cells.
    reusable_leftover_before : int
        Total reusable effective leftover width before reorder-opt.
    reusable_leftover_after : int
        Total reusable effective leftover width after reorder-opt.
    reusable_leftover_delta : int
        Difference between after and before reusable effective leftover.
    move_type_count : dict[str, int]
        Applied move counts grouped by moved LUT pair and host LUT pair.
    """

    candidate_hosts: int = 0
    candidate_donors: int = 0
    legal_optimizations: int = 0
    applied_optimizations: int = 0
    frac_cells_before: int = 0
    frac_cells_after: int = 0
    frac_cells_saved: int = 0
    reusable_leftover_before: int = 0
    reusable_leftover_after: int = 0
    reusable_leftover_delta: int = 0
    move_type_count: dict[str, int] = field(default_factory=dict)


@dataclass(frozen=True)
class ReorderOptResult:
    """Bundle optimized mapping and reorder-opt report data.

    Attributes
    ----------
    mapping : MappingResult
        Mapping result after selected pair-cell removals.
    stats : ReorderOptStats
        Aggregate counters for the optimization run.
    moves : tuple[ReorderOptMove, ...]
        Applied optimizations in deterministic output order.
    report_summary : str
        Human-readable reorder-opt report block.
    """

    mapping: MappingResult
    stats: ReorderOptStats
    moves: tuple[ReorderOptMove, ...]
    report_summary: str

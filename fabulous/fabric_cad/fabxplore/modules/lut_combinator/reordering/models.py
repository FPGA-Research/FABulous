"""Typed models for LUT leftover reordering.

The reordering stage consumes an already packed LUT-combinator result and tries to
rearrange logical LUT ownership between packed cells. Its goal is to keep the same
number of emitted FRAC cells while increasing reusable leftover LUT space in single-
output cells.
"""

from dataclasses import dataclass, field

from fabulous.fabric_cad.fabxplore.modules.lut_combinator.core.models import (
    MappingResult,
)


@dataclass(frozen=True)
class LeftoverReorderingConfig:
    """Configure the leftover reordering optimization.

    Attributes
    ----------
    require_positive_gain : bool
        If ``True``, only apply moves that strictly increase reusable effective
        leftover width. Keeping this enabled guarantees that an opt-in run never
        makes leftover capacity worse.
    """

    require_positive_gain: bool = True


@dataclass(frozen=True)
class ReorderingMove:
    """Describe one applied logical LUT move between two packed cells.

    Attributes
    ----------
    host_packed_id : str
        Single-cell FRAC instance that receives the moved LUT.
    donor_packed_id : str
        Pair-cell FRAC instance that gives up one LUT and becomes a single cell.
    moved_cell_id : str
        Logical LUT moved from the donor into the host.
    remaining_cell_id : str
        Logical LUT left behind in the donor cell.
    host_width : int
        Input width of the original host LUT.
    moved_width : int
        Input width of the moved LUT.
    remaining_width : int
        Input width of the donor LUT that remains single mapped.
    old_host_effective_leftover : int
        Reusable effective leftover width in the host before the move.
    new_donor_effective_leftover : int
        Reusable effective leftover width in the rebuilt donor after the move.
    gain : int
        Difference between new donor reusable leftover and old host reusable
        leftover.
    """

    host_packed_id: str
    donor_packed_id: str
    moved_cell_id: str
    remaining_cell_id: str
    host_width: int
    moved_width: int
    remaining_width: int
    old_host_effective_leftover: int
    new_donor_effective_leftover: int
    gain: int


@dataclass(frozen=True)
class LeftoverReorderingStats:
    """Aggregate counters for one leftover reordering run.

    Attributes
    ----------
    candidate_hosts : int
        Number of single non-full FRAC cells considered as destinations.
    candidate_donors : int
        Number of dual FRAC cells considered as move donors.
    legal_moves : int
        Number of profitable legal moves discovered before greedy selection.
    applied_moves : int
        Number of moves actually applied after resolving host/donor conflicts.
    reusable_leftover_before : int
        Total reusable effective leftover width before reordering.
    reusable_leftover_after : int
        Total reusable effective leftover width after reordering.
    reusable_leftover_gain : int
        Difference between after and before reusable effective leftover.
    move_type_count : dict[str, int]
        Applied move counts grouped by ``LUTm -> LUTn`` display label.
    """

    candidate_hosts: int = 0
    candidate_donors: int = 0
    legal_moves: int = 0
    applied_moves: int = 0
    reusable_leftover_before: int = 0
    reusable_leftover_after: int = 0
    reusable_leftover_gain: int = 0
    move_type_count: dict[str, int] = field(default_factory=dict)


@dataclass(frozen=True)
class LeftoverReorderingResult:
    """Bundle reordered mapping and reordering report data.

    Attributes
    ----------
    mapping : MappingResult
        Mapping result after applying selected reordering moves.
    stats : LeftoverReorderingStats
        Aggregate counters for the reordering run.
    moves : tuple[ReorderingMove, ...]
        Applied moves in deterministic output order.
    report_summary : str
        Human-readable reordering report block.
    """

    mapping: MappingResult
    stats: LeftoverReorderingStats
    moves: tuple[ReorderingMove, ...]
    report_summary: str

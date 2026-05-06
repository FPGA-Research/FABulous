"""Reorder packed LUT-combinator cells to improve reusable leftover space.

The reorderer is deliberately a second-stage optimizer. It does not create new
logical LUTs and does not change the number of mapped FRAC cells. Instead, it
moves a small LUT out of an already paired cell into a compatible single-cell
host, then rebuilds the donor as a single cell with larger reusable leftover
capacity.

All legality and INIT remapping is delegated back to
``FracLutArchitecture``. This keeps the reordering pass independent from the
architecture's pin order, select-as-data mode, and future binding details.
"""

from dataclasses import dataclass, replace

from fabulous.fabric_cad.fabxplore.modules.lut_combinator.core.architecture import (
    FracLutArchitecture,
)
from fabulous.fabric_cad.fabxplore.modules.lut_combinator.core.models import (
    LogicalLutCell,
    MappingResult,
    PackedCell,
    PairBinding,
)
from fabulous.fabric_cad.fabxplore.modules.lut_combinator.reordering.models import (
    LeftoverReorderingConfig,
    LeftoverReorderingResult,
    LeftoverReorderingStats,
    ReorderingMove,
)
from fabulous.fabric_cad.fabxplore.modules.lut_combinator.reordering.report import (
    render_reordering_report,
)


@dataclass(frozen=True)
class _CandidateMove:
    """Internal move candidate with rebuilt cells attached.

    Attributes
    ----------
    host_index : int
        Index of the single-cell host in the mapped-cell list.
    donor_index : int
        Index of the pair-cell donor in the mapped-cell list.
    new_host : PackedCell
        Rebuilt host cell after accepting the moved LUT.
    new_donor : PackedCell
        Rebuilt donor cell after leaving one LUT behind.
    move : ReorderingMove
        Public move description used for reporting.
    """

    host_index: int
    donor_index: int
    new_host: PackedCell
    new_donor: PackedCell
    move: ReorderingMove


class LeftoverReorderer:
    """Improve reusable leftover LUT capacity without increasing FRAC count.

    The normal LUT combinator minimizes or chooses packed FRAC cells first.
    This class operates afterward on the resulting ``MappingResult``. It looks
    for cases where a paired cell ``A+B`` can be split, one side can be moved
    into the free half of a single-cell host ``H``, and the donor can then become
    a single cell with more reusable leftover capacity:

    ``H`` plus ``A+B`` becomes ``H+A`` plus ``B``.

    Only non-full single cells are used as hosts. Full LUT(K+1) cells are
    ignored because both internal LUT halves are already part of one logical
    function. Candidate moves are checked with simple leftover-capacity math
    first, then validated and rebuilt through the architecture binder. The final
    selection is deterministic and greedy: all legal profitable moves are sorted
    by gain, and each host/donor cell can be used at most once.

    Parameters
    ----------
    architecture : FracLutArchitecture
        Architecture helper used to validate and rebuild changed FRAC cells.
    config : LeftoverReorderingConfig | None
        Optional reordering configuration. If omitted, default conservative
        settings are used.
    """

    def __init__(
        self,
        architecture: FracLutArchitecture,
        config: LeftoverReorderingConfig | None = None,
    ) -> None:
        self.arch = architecture
        self.config = config or LeftoverReorderingConfig()

    def reorder(self, mapping: MappingResult) -> LeftoverReorderingResult:
        """Return a mapping with profitable leftover reordering moves applied.

        Parameters
        ----------
        mapping : MappingResult
            Mapping result produced by the normal LUT combinator stage.

        Returns
        -------
        LeftoverReorderingResult
            Reordered mapping, applied moves, aggregate stats, and report text.
        """
        mapped_cells: list[PackedCell] = list(mapping.mapped_cells)
        host_indices: list[int] = [
            idx for idx, cell in enumerate(mapped_cells) if self._is_host_cell(cell)
        ]
        donor_indices: list[int] = [
            idx for idx, cell in enumerate(mapped_cells) if len(cell.placements) == 2
        ]
        reusable_before: int = self._total_reusable_effective_leftover(mapped_cells)

        candidates: list[_CandidateMove] = self._build_candidates(
            mapped_cells=mapped_cells,
            host_indices=host_indices,
            donor_indices=donor_indices,
        )
        selected: list[_CandidateMove] = self._select_moves(candidates)

        reordered_cells: list[PackedCell] = list(mapped_cells)
        for candidate in selected:
            reordered_cells[candidate.host_index] = candidate.new_host
            reordered_cells[candidate.donor_index] = candidate.new_donor

        reusable_after: int = self._total_reusable_effective_leftover(reordered_cells)
        moves: tuple[ReorderingMove, ...] = tuple(
            candidate.move for candidate in selected
        )
        stats = LeftoverReorderingStats(
            candidate_hosts=len(host_indices),
            candidate_donors=len(donor_indices),
            legal_moves=len(candidates),
            applied_moves=len(moves),
            reusable_leftover_before=reusable_before,
            reusable_leftover_after=reusable_after,
            reusable_leftover_gain=reusable_after - reusable_before,
            move_type_count=self._move_type_count(moves),
        )
        report_summary = render_reordering_report(stats, moves)

        metadata: dict = dict(mapping.metadata)
        metadata.update(
            {
                "leftover_reordering_enabled": True,
                "leftover_reordering_moves": stats.applied_moves,
                "leftover_reordering_gain": stats.reusable_leftover_gain,
                "_leftover_reordering_report": report_summary,
            }
        )

        reordered_mapping = MappingResult(
            architecture_name=mapping.architecture_name,
            top_name=mapping.top_name,
            mapped_cells=reordered_cells,
            passthrough_luts=mapping.passthrough_luts,
            stats=replace(mapping.stats),
            metadata=metadata,
            report_summary=mapping.report_summary,
        )

        return LeftoverReorderingResult(
            mapping=reordered_mapping,
            stats=stats,
            moves=moves,
            report_summary=report_summary,
        )

    def _build_candidates(
        self,
        mapped_cells: list[PackedCell],
        host_indices: list[int],
        donor_indices: list[int],
    ) -> list[_CandidateMove]:
        """Build all legal profitable move candidates.

        Parameters
        ----------
        mapped_cells : list[PackedCell]
            Current mapped-cell list from the normal combinator result.
        host_indices : list[int]
            Indices of eligible single-cell hosts in ``mapped_cells``.
        donor_indices : list[int]
            Indices of pair-cell donors in ``mapped_cells``.

        Returns
        -------
        list[_CandidateMove]
            Candidate moves that pass capacity, architecture binding, and gain
            checks.
        """
        candidates: list[_CandidateMove] = []

        for host_index in host_indices:
            host_cell = mapped_cells[host_index]
            host_lut = host_cell.placements[0].cell
            host_capacity = self._reusable_effective_leftover(host_cell)

            for donor_index in donor_indices:
                donor_cell = mapped_cells[donor_index]
                donor_luts = tuple(plc.cell for plc in donor_cell.placements)

                for move_side in (0, 1):
                    moved_lut = donor_luts[move_side]
                    remaining_lut = donor_luts[1 - move_side]

                    if host_capacity < moved_lut.width:
                        continue

                    candidate = self._try_build_candidate(
                        host_index=host_index,
                        donor_index=donor_index,
                        host_cell=host_cell,
                        donor_cell=donor_cell,
                        host_lut=host_lut,
                        moved_lut=moved_lut,
                        remaining_lut=remaining_lut,
                    )
                    if candidate is not None:
                        candidates.append(candidate)

        return candidates

    def _try_build_candidate(
        self,
        host_index: int,
        donor_index: int,
        host_cell: PackedCell,
        donor_cell: PackedCell,
        host_lut: LogicalLutCell,
        moved_lut: LogicalLutCell,
        remaining_lut: LogicalLutCell,
    ) -> _CandidateMove | None:
        """Validate and rebuild one candidate move.

        Parameters
        ----------
        host_index : int
            Index of ``host_cell`` in the mapped-cell list.
        donor_index : int
            Index of ``donor_cell`` in the mapped-cell list.
        host_cell : PackedCell
            Existing single-cell host that may receive ``moved_lut``.
        donor_cell : PackedCell
            Existing pair cell that may give up ``moved_lut``.
        host_lut : LogicalLutCell
            Logical LUT currently placed in the host.
        moved_lut : LogicalLutCell
            Logical LUT to move out of the donor and into the host.
        remaining_lut : LogicalLutCell
            Logical LUT left behind in the donor.

        Returns
        -------
        _CandidateMove | None
            Rebuilt candidate if the move is legal and profitable, otherwise
            ``None``.
        """
        binding: PairBinding | None = self.arch.try_bind_pair(host_lut, moved_lut)
        if binding is None:
            return None

        rebuilt_host = self.arch.build_mapped_cell(host_cell.packed_id, binding)
        rebuilt_donor = self.arch.bind_single_lut(remaining_lut)
        if rebuilt_donor is None:
            return None

        rebuilt_donor = replace(rebuilt_donor, packed_id=donor_cell.packed_id)
        new_donor_capacity = self._reusable_effective_leftover(rebuilt_donor)
        old_host_capacity = self._reusable_effective_leftover(host_cell)
        gain = new_donor_capacity - old_host_capacity

        if self.config.require_positive_gain and gain <= 0:
            return None

        move = ReorderingMove(
            host_packed_id=host_cell.packed_id,
            donor_packed_id=donor_cell.packed_id,
            moved_cell_id=moved_lut.cell_id,
            remaining_cell_id=remaining_lut.cell_id,
            host_width=host_lut.width,
            moved_width=moved_lut.width,
            remaining_width=remaining_lut.width,
            old_host_effective_leftover=old_host_capacity,
            new_donor_effective_leftover=new_donor_capacity,
            gain=gain,
        )

        return _CandidateMove(
            host_index=host_index,
            donor_index=donor_index,
            new_host=rebuilt_host,
            new_donor=rebuilt_donor,
            move=move,
        )

    def _select_moves(self, candidates: list[_CandidateMove]) -> list[_CandidateMove]:
        """Select a deterministic non-conflicting greedy move set.

        Parameters
        ----------
        candidates : list[_CandidateMove]
            Legal move candidates to choose from.

        Returns
        -------
        list[_CandidateMove]
            Selected moves sorted by original mapped-cell order. Each selected
            move uses a unique host and donor.
        """
        ordered = sorted(
            candidates,
            key=lambda c: (
                -c.move.gain,
                -c.move.new_donor_effective_leftover,
                c.move.host_packed_id,
                c.move.donor_packed_id,
                c.move.moved_cell_id,
            ),
        )
        used_hosts: set[int] = set()
        used_donors: set[int] = set()
        selected: list[_CandidateMove] = []

        for candidate in ordered:
            if candidate.host_index in used_hosts:
                continue
            if candidate.donor_index in used_donors:
                continue
            selected.append(candidate)
            used_hosts.add(candidate.host_index)
            used_donors.add(candidate.donor_index)

        return sorted(
            selected,
            key=lambda c: (c.host_index, c.donor_index, c.move.moved_cell_id),
        )

    def _is_host_cell(self, cell: PackedCell) -> bool:
        """Return whether a packed cell can host one additional LUT.

        Parameters
        ----------
        cell : PackedCell
            Packed cell to classify.

        Returns
        -------
        bool
            ``True`` when ``cell`` is a non-full single cell with at least one
            reusable effective leftover input.
        """
        if len(cell.placements) != 1:
            return False
        lut = cell.placements[0].cell
        if lut.width > self.arch.frac_lut_size:
            return False
        return self._reusable_effective_leftover(cell) >= 1

    def _total_reusable_effective_leftover(self, cells: list[PackedCell]) -> int:
        """Return total reusable leftover capacity across single non-full cells.

        Parameters
        ----------
        cells : list[PackedCell]
            Mapped cells to aggregate.

        Returns
        -------
        int
            Sum of reusable effective leftover widths.
        """
        return sum(self._reusable_effective_leftover(cell) for cell in cells)

    def _reusable_effective_leftover(self, cell: PackedCell) -> int:
        """Return reusable effective leftover width for one packed cell.

        Parameters
        ----------
        cell : PackedCell
            Packed cell to evaluate.

        Returns
        -------
        int
            Effective leftover width that can host another independent LUT.
            Pair cells and full LUT(K+1) single cells return zero.
        """
        if len(cell.placements) != 1:
            return 0
        if cell.placements[0].cell.width > self.arch.frac_lut_size:
            return 0
        leftover = min(self.arch.frac_lut_size, max(0, cell.leftover_lut_width))
        if cell.frac_lut_parameters.select_as_data_capable:
            leftover += 1
        return min(self.arch.frac_lut_size, leftover)

    def _move_type_count(self, moves: tuple[ReorderingMove, ...]) -> dict[str, int]:
        """Count applied moves by host/moved LUT width combination.

        Parameters
        ----------
        moves : tuple[ReorderingMove, ...]
            Applied moves from the current reordering run.

        Returns
        -------
        dict[str, int]
            Counts keyed by labels such as ``"LUT2 into LUT4"``.
        """
        counts: dict[str, int] = {}
        for move in moves:
            label = f"LUT{move.moved_width} into LUT{move.host_width}"
            counts[label] = counts.get(label, 0) + 1
        return counts

"""Remove pair cells by spending reusable leftover LUT capacity.

The optimizer is an area-saving companion to leftover reordering. It searches
for two single-cell hosts with enough reusable leftover capacity to absorb the
two LUTs from one donor pair cell. When both new host pairs are legal according
to the architecture binder, the donor pair cell can be removed.

The pass is intentionally bounded and streaming. A naive implementation would
materialize all donor-pair and host-pair combinations, which grows as
``O(donors * hosts**2)``. Instead, each donor only looks at the lowest-waste
host options per side and immediately consumes selected hosts. This keeps memory
usage stable on larger designs while preserving the important architectural
legality checks.
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
from fabulous.fabric_cad.fabxplore.modules.lut_combinator.reorder_opt.models import (
    ReorderOptConfig,
    ReorderOptMove,
    ReorderOptResult,
    ReorderOptStats,
)
from fabulous.fabric_cad.fabxplore.modules.lut_combinator.reorder_opt.report import (
    render_reorder_opt_report,
)


@dataclass(frozen=True)
class _OptCandidate:
    """Internal removable-pair candidate with rebuilt hosts attached.

    Attributes
    ----------
    donor_index : int
        Index of the pair-cell donor that would be removed.
    host0_index : int
        Index of the first single-cell host.
    host1_index : int
        Index of the second single-cell host.
    new_host0 : PackedCell
        Rebuilt first host after accepting one donor LUT.
    new_host1 : PackedCell
        Rebuilt second host after accepting the other donor LUT.
    move : ReorderOptMove
        Public move description used for reporting.
    """

    donor_index: int
    host0_index: int
    host1_index: int
    new_host0: PackedCell
    new_host1: PackedCell
    move: ReorderOptMove


class ReorderOptOptimizer:
    """Save FRAC cells by splitting pair cells into existing leftovers.

    For a donor pair ``A+B`` and two single hosts ``H0`` and ``H1``, the
    optimizer tries both assignments:

    ``H0+A`` and ``H1+B``

    ``H0+B`` and ``H1+A``

    If both rebuilt host pairs are legal, the original donor pair is removed:

    ``H0 + H1 + (A+B) -> (H0+A) + (H1+B)``

    or the swapped version:

    ``H0 + H1 + (A+B) -> (H0+B) + (H1+A)``

    The normal architecture binding functions perform the final pin and INIT
    remapping, so this pass only chooses and applies valid transformations. It
    trades reusable leftover capacity for fewer mapped FRAC cells.

    Parameters
    ----------
    architecture : FracLutArchitecture
        Architecture helper used to validate and rebuild changed FRAC cells.
    config : ReorderOptConfig | None
        Optional optimization configuration. Defaults to conservative settings.
    """

    def __init__(
        self,
        architecture: FracLutArchitecture,
        config: ReorderOptConfig | None = None,
    ) -> None:
        self.arch = architecture
        self.config = config or ReorderOptConfig()

    def optimize(self, mapping: MappingResult) -> ReorderOptResult:
        """Return a mapping with removable pair cells optimized away.

        Parameters
        ----------
        mapping : MappingResult
            Mapping result produced by normal packing and optional reordering.

        Returns
        -------
        ReorderOptResult
            Optimized mapping, applied moves, aggregate stats, and report text.
        """
        mapped_cells: list[PackedCell] = list(mapping.mapped_cells)
        host_indices: list[int] = [
            idx for idx, cell in enumerate(mapped_cells) if self._is_host_cell(cell)
        ]
        donor_indices: list[int] = [
            idx for idx, cell in enumerate(mapped_cells) if len(cell.placements) == 2
        ]
        reusable_before = self._total_reusable_effective_leftover(mapped_cells)

        selected, legal_optimizations = self._select_optimizations_streaming(
            mapped_cells=mapped_cells,
            host_indices=host_indices,
            donor_indices=donor_indices,
        )

        replacements: dict[int, PackedCell] = {}
        removed_donors: set[int] = set()
        for candidate in selected:
            replacements[candidate.host0_index] = candidate.new_host0
            replacements[candidate.host1_index] = candidate.new_host1
            removed_donors.add(candidate.donor_index)

        optimized_cells: list[PackedCell] = []
        for idx, cell in enumerate(mapped_cells):
            if idx in removed_donors:
                continue
            optimized_cells.append(replacements.get(idx, cell))

        reusable_after = self._total_reusable_effective_leftover(optimized_cells)
        moves: tuple[ReorderOptMove, ...] = tuple(
            candidate.move for candidate in selected
        )
        saved_cells = len(removed_donors)
        stats = ReorderOptStats(
            candidate_hosts=len(host_indices),
            candidate_donors=len(donor_indices),
            legal_optimizations=legal_optimizations,
            applied_optimizations=len(moves),
            frac_cells_before=len(mapped_cells),
            frac_cells_after=len(optimized_cells),
            frac_cells_saved=saved_cells,
            reusable_leftover_before=reusable_before,
            reusable_leftover_after=reusable_after,
            reusable_leftover_delta=reusable_after - reusable_before,
            move_type_count=self._move_type_count(moves),
        )
        report_summary = render_reorder_opt_report(stats, moves)

        result_type_count = dict(mapping.stats.result_type_count)
        arch_count = result_type_count.get(mapping.architecture_name, 0)
        result_type_count[mapping.architecture_name] = max(0, arch_count - saved_cells)

        optimized_stats = replace(
            mapping.stats,
            total_cells_after=max(0, mapping.stats.total_cells_after - saved_cells),
            mapped_groups=max(0, mapping.stats.mapped_groups - saved_cells),
            result_type_count=result_type_count,
        )

        metadata = dict(mapping.metadata)
        metadata.update(
            {
                "reorder_opt_enabled": True,
                "reorder_opt_saved_cells": saved_cells,
                "reorder_opt_applied_optimizations": stats.applied_optimizations,
                "_reorder_opt_report": report_summary,
            }
        )

        optimized_mapping = MappingResult(
            architecture_name=mapping.architecture_name,
            top_name=mapping.top_name,
            mapped_cells=optimized_cells,
            passthrough_luts=mapping.passthrough_luts,
            stats=optimized_stats,
            metadata=metadata,
            report_summary=mapping.report_summary,
        )

        return ReorderOptResult(
            mapping=optimized_mapping,
            stats=stats,
            moves=moves,
            report_summary=report_summary,
        )

    def _select_optimizations_streaming(
        self,
        mapped_cells: list[PackedCell],
        host_indices: list[int],
        donor_indices: list[int],
    ) -> tuple[list[_OptCandidate], int]:
        """Select donor-removal candidates without materializing all options.

        Parameters
        ----------
        mapped_cells : list[PackedCell]
            Current mapped-cell list.
        host_indices : list[int]
            Indices of eligible single-cell hosts.
        donor_indices : list[int]
            Indices of pair-cell donors.

        Returns
        -------
        tuple[list[_OptCandidate], int]
            Selected non-conflicting candidates and the number of legal
            candidates seen during the bounded search.
        """
        available_hosts: set[int] = set(host_indices)
        selected: list[_OptCandidate] = []
        legal_optimizations = 0

        for donor_index in self._ordered_donor_indices(mapped_cells, donor_indices):
            donor_cell = mapped_cells[donor_index]
            donor_luts = tuple(plc.cell for plc in donor_cell.placements)

            candidate, legal_count = self._best_candidate_for_donor(
                mapped_cells=mapped_cells,
                available_hosts=available_hosts,
                donor_index=donor_index,
                donor_cell=donor_cell,
                donor_luts=donor_luts,
            )
            legal_optimizations += legal_count

            if candidate is None:
                continue

            selected.append(candidate)
            available_hosts.remove(candidate.host0_index)
            available_hosts.remove(candidate.host1_index)

        return selected, legal_optimizations

    def _best_candidate_for_donor(
        self,
        mapped_cells: list[PackedCell],
        available_hosts: set[int],
        donor_index: int,
        donor_cell: PackedCell,
        donor_luts: tuple[LogicalLutCell, LogicalLutCell],
    ) -> tuple[_OptCandidate | None, int]:
        """Return the best bounded candidate for one donor pair.

        Parameters
        ----------
        mapped_cells : list[PackedCell]
            Current mapped-cell list.
        available_hosts : set[int]
            Host indices not consumed by earlier selected optimizations.
        donor_index : int
            Index of ``donor_cell`` in ``mapped_cells``.
        donor_cell : PackedCell
            Pair cell considered for removal.
        donor_luts : tuple[LogicalLutCell, LogicalLutCell]
            The two logical LUTs currently placed in ``donor_cell``.

        Returns
        -------
        tuple[_OptCandidate | None, int]
            Best candidate for this donor, if any, and the number of legal
            bounded candidates found.
        """
        lut_a, lut_b = donor_luts
        candidates: list[_OptCandidate] = []

        candidates.extend(
            self._candidates_for_assignment(
                mapped_cells=mapped_cells,
                available_hosts=available_hosts,
                donor_index=donor_index,
                donor_cell=donor_cell,
                moved0=lut_a,
                moved1=lut_b,
            )
        )
        candidates.extend(
            self._candidates_for_assignment(
                mapped_cells=mapped_cells,
                available_hosts=available_hosts,
                donor_index=donor_index,
                donor_cell=donor_cell,
                moved0=lut_b,
                moved1=lut_a,
            )
        )

        if not candidates:
            return None, 0

        return min(candidates, key=self._candidate_sort_key), len(candidates)

    def _candidates_for_assignment(
        self,
        mapped_cells: list[PackedCell],
        available_hosts: set[int],
        donor_index: int,
        donor_cell: PackedCell,
        moved0: LogicalLutCell,
        moved1: LogicalLutCell,
    ) -> list[_OptCandidate]:
        """Build bounded host-pair candidates for one donor assignment.

        Parameters
        ----------
        mapped_cells : list[PackedCell]
            Current mapped-cell list.
        available_hosts : set[int]
            Host indices still available for selection.
        donor_index : int
            Index of the donor pair in ``mapped_cells``.
        donor_cell : PackedCell
            Donor pair cell being considered for removal.
        moved0 : LogicalLutCell
            Donor LUT assigned to the first host.
        moved1 : LogicalLutCell
            Donor LUT assigned to the second host.

        Returns
        -------
        list[_OptCandidate]
            Legal bounded candidates for this donor-side assignment.
        """
        host0_options = self._host_options_for_lut(
            mapped_cells=mapped_cells,
            available_hosts=available_hosts,
            moved_lut=moved0,
        )
        host1_options = self._host_options_for_lut(
            mapped_cells=mapped_cells,
            available_hosts=available_hosts,
            moved_lut=moved1,
        )
        candidates: list[_OptCandidate] = []

        for host0_index in host0_options:
            for host1_index in host1_options:
                if host0_index == host1_index:
                    continue
                host0_cell = mapped_cells[host0_index]
                host1_cell = mapped_cells[host1_index]
                candidate = self._try_build_candidate(
                    donor_index=donor_index,
                    donor_cell=donor_cell,
                    host0_index=host0_index,
                    host1_index=host1_index,
                    host0_cell=host0_cell,
                    host1_cell=host1_cell,
                    moved0=moved0,
                    moved1=moved1,
                )
                if candidate is not None:
                    candidates.append(candidate)

        return candidates

    def _host_options_for_lut(
        self,
        mapped_cells: list[PackedCell],
        available_hosts: set[int],
        moved_lut: LogicalLutCell,
    ) -> list[int]:
        """Return bounded host options ordered by lowest capacity waste.

        Parameters
        ----------
        mapped_cells : list[PackedCell]
            Current mapped-cell list.
        available_hosts : set[int]
            Host indices still available for selection.
        moved_lut : LogicalLutCell
            Logical LUT that must fit into a host's leftover space.

        Returns
        -------
        list[int]
            At most ``max_host_candidates_per_side`` host indices ordered by
            increasing leftover waste.
        """
        options = [
            idx
            for idx in available_hosts
            if self._reusable_effective_leftover(mapped_cells[idx]) >= moved_lut.width
        ]
        options.sort(
            key=lambda idx: (
                self._reusable_effective_leftover(mapped_cells[idx]) - moved_lut.width,
                self._reusable_effective_leftover(mapped_cells[idx]),
                mapped_cells[idx].packed_id,
            )
        )
        return options[: self.config.max_host_candidates_per_side]

    def _ordered_donor_indices(
        self, mapped_cells: list[PackedCell], donor_indices: list[int]
    ) -> list[int]:
        """Return donors in an order that tries easier removals first.

        Parameters
        ----------
        mapped_cells : list[PackedCell]
            Current mapped-cell list.
        donor_indices : list[int]
            Indices of pair-cell donors.

        Returns
        -------
        list[int]
            Donor indices sorted by total donor LUT width and stable IDs.
        """
        return sorted(
            donor_indices,
            key=lambda idx: (
                sum(plc.cell.width for plc in mapped_cells[idx].placements),
                tuple(plc.cell.width for plc in mapped_cells[idx].placements),
                mapped_cells[idx].packed_id,
            ),
        )

    def _try_build_candidate(
        self,
        donor_index: int,
        donor_cell: PackedCell,
        host0_index: int,
        host1_index: int,
        host0_cell: PackedCell,
        host1_cell: PackedCell,
        moved0: LogicalLutCell,
        moved1: LogicalLutCell,
    ) -> _OptCandidate | None:
        """Validate and rebuild one donor-removal candidate.

        Parameters
        ----------
        donor_index : int
            Index of the donor pair in the mapped-cell list.
        donor_cell : PackedCell
            Pair cell considered for removal.
        host0_index : int
            Index of ``host0_cell`` in the mapped-cell list.
        host1_index : int
            Index of ``host1_cell`` in the mapped-cell list.
        host0_cell : PackedCell
            First single-cell host.
        host1_cell : PackedCell
            Second single-cell host.
        moved0 : LogicalLutCell
            Donor LUT assigned to ``host0_cell``.
        moved1 : LogicalLutCell
            Donor LUT assigned to ``host1_cell``.

        Returns
        -------
        _OptCandidate | None
            Rebuilt candidate if both host pairings are legal, otherwise
            ``None``.
        """
        cap0 = self._reusable_effective_leftover(host0_cell)
        cap1 = self._reusable_effective_leftover(host1_cell)
        if cap0 < moved0.width or cap1 < moved1.width:
            return None

        host0_lut = host0_cell.placements[0].cell
        host1_lut = host1_cell.placements[0].cell
        binding0: PairBinding | None = self.arch.try_bind_pair(host0_lut, moved0)
        if binding0 is None:
            return None
        binding1: PairBinding | None = self.arch.try_bind_pair(host1_lut, moved1)
        if binding1 is None:
            return None

        new_host0 = self.arch.build_mapped_cell(host0_cell.packed_id, binding0)
        new_host1 = self.arch.build_mapped_cell(host1_cell.packed_id, binding1)
        waste = (cap0 - moved0.width) + (cap1 - moved1.width)

        move = ReorderOptMove(
            donor_packed_id=donor_cell.packed_id,
            host0_packed_id=host0_cell.packed_id,
            host1_packed_id=host1_cell.packed_id,
            moved0_cell_id=moved0.cell_id,
            moved1_cell_id=moved1.cell_id,
            host0_width=host0_lut.width,
            host1_width=host1_lut.width,
            moved0_width=moved0.width,
            moved1_width=moved1.width,
            host0_effective_leftover=cap0,
            host1_effective_leftover=cap1,
            leftover_waste=waste,
            saved_cells=1,
        )

        return _OptCandidate(
            donor_index=donor_index,
            host0_index=host0_index,
            host1_index=host1_index,
            new_host0=new_host0,
            new_host1=new_host1,
            move=move,
        )

    def _candidate_sort_key(self, candidate: _OptCandidate) -> tuple:
        """Return deterministic score for candidate comparison.

        Parameters
        ----------
        candidate : _OptCandidate
            Candidate to score.

        Returns
        -------
        tuple
            Sort key prioritizing low leftover waste and stable IDs.
        """
        return (
            candidate.move.leftover_waste,
            (
                candidate.move.host0_effective_leftover
                + candidate.move.host1_effective_leftover
            ),
            candidate.move.donor_packed_id,
            candidate.move.host0_packed_id,
            candidate.move.host1_packed_id,
            candidate.move.moved0_cell_id,
            candidate.move.moved1_cell_id,
        )

    def _is_host_cell(self, cell: PackedCell) -> bool:
        """Return whether a packed cell can receive one donor LUT.

        Parameters
        ----------
        cell : PackedCell
            Packed cell to classify.

        Returns
        -------
        bool
            ``True`` when ``cell`` is a non-full single cell with reusable
            effective leftover capacity.
        """
        if len(cell.placements) != 1:
            return False
        lut = cell.placements[0].cell
        if lut.width > self.arch.frac_lut_size:
            return False
        return self._reusable_effective_leftover(cell) >= 1

    def _total_reusable_effective_leftover(self, cells: list[PackedCell]) -> int:
        """Return total reusable leftover capacity across eligible single cells.

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
            Effective leftover width that can receive one donor LUT. Pair cells
            and full LUT(K+1) single cells return zero.
        """
        if len(cell.placements) != 1:
            return 0
        if cell.placements[0].cell.width > self.arch.frac_lut_size:
            return 0
        leftover = cell.leftover_lut_width
        if cell.frac_lut_parameters.select_as_data_capable:
            leftover += 1
        return max(0, leftover)

    def _move_type_count(self, moves: tuple[ReorderOptMove, ...]) -> dict[str, int]:
        """Count applied optimizations by moved and host LUT widths.

        Parameters
        ----------
        moves : tuple[ReorderOptMove, ...]
            Applied reorder-opt transformations.

        Returns
        -------
        dict[str, int]
            Counts keyed by moved pair type and host pair type.
        """
        counts: dict[str, int] = {}
        for move in moves:
            moved = sorted((move.moved0_width, move.moved1_width))
            hosts = sorted((move.host0_width, move.host1_width))
            label = (
                f"LUT{moved[0]}+LUT{moved[1]} into "
                f"LUT{hosts[0]}/LUT{hosts[1]} leftovers"
            )
            counts[label] = counts.get(label, 0) + 1
        return counts

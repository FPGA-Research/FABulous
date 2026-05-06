"""Extract reusable leftover LUT slots from packed combinator results."""

from fabulous.fabric_cad.fabxplore.modules.lut_combinator.core.architecture import (
    FracLutArchitecture,
)
from fabulous.fabric_cad.fabxplore.modules.lut_combinator.core.models import (
    MappingResult,
    PackedCell,
)
from fabulous.fabric_cad.fabxplore.modules.lut_layering.core.models import (
    LeftoverSlot,
)


def collect_leftover_slots(
    mapping: MappingResult,
    architecture: FracLutArchitecture,
) -> tuple[LeftoverSlot, ...]:
    """Return all single-cell leftover slots usable for layering.

    Parameters
    ----------
    mapping : MappingResult
        Current packed base design mapping.
    architecture : FracLutArchitecture
        Fractional LUT architecture used to calculate effective capacity.

    Returns
    -------
    tuple[LeftoverSlot, ...]
        Slots with effective leftover width of at least one input.
    """
    slots: list[LeftoverSlot] = []
    for idx, cell in enumerate(mapping.mapped_cells):
        if not _is_layering_host(cell, architecture):
            continue

        effective = effective_leftover_width(cell, architecture)
        if effective < 1:
            continue

        host_lut = cell.placements[0].cell
        slots.append(
            LeftoverSlot(
                cell_index=idx,
                packed_id=cell.packed_id,
                host_cell_id=host_lut.cell_id,
                host_width=host_lut.width,
                effective_leftover_width=effective,
                nominal_leftover_width=max(0, cell.leftover_lut_width),
            )
        )

    return tuple(slots)


def effective_leftover_width(
    cell: PackedCell,
    architecture: FracLutArchitecture,
) -> int:
    """Return reusable effective leftover width for one packed cell.

    Select-as-data capable single cells effectively expose one additional
    leftover input because ``S`` can be used as a data input for the injected
    second LUT. Full LUT(K+1) cells and pair cells are not reusable hosts.

    Parameters
    ----------
    cell : PackedCell
        Packed FRAC cell to inspect.
    architecture : FracLutArchitecture
        Architecture that produced the mapping.

    Returns
    -------
    int
        Effective reusable leftover width. Non-host cells return zero.
    """
    if not _is_layering_host(cell, architecture):
        return 0

    base = max(0, cell.leftover_lut_width)
    if architecture.use_select_as_data_in_pair_mode:
        return base + 1
    return base


def _is_layering_host(cell: PackedCell, architecture: FracLutArchitecture) -> bool:
    """Return whether ``cell`` may receive one overlay LUT.

    Parameters
    ----------
    cell : PackedCell
        Packed cell candidate.
    architecture : FracLutArchitecture
        Architecture used to reject full LUT(K+1) hosts.

    Returns
    -------
    bool
        ``True`` when ``cell`` is a single non-full FRAC cell.
    """
    if len(cell.placements) != 1:
        return False
    return cell.placements[0].cell.width <= architecture.frac_lut_size

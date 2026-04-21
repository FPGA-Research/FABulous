"""Create text reports for LUT packing results.

This module renders human-readable summaries from a ``MappingResult`` and a
template. It also computes and formats LUT type distributions so users can
compare source and mapped designs quickly.
"""

from fabulous.fabric_cad.fabxplore.modules.lut_combinator.core.models import (
    MappingResult,
)

REPORT_TEMPLATE = """
LUT Combinator Mapping Report
Architecture: {architecture}
Top Module: {top}

Before {architecture} packing:
{before_stats}

After {architecture} packing:
{after_stats}

Summary
- Mapped Groups: {mapped_groups}
- Mapped LUTs: {mapped_luts}
- Passthrough LUTs: {passthrough_luts}
"""


def render_report(mapping: MappingResult) -> str:
    """Render a report string from mapping data and a text template.

    The template is filled with high-level mapping statistics and formatted
    LUT-type tables before and after packing.

    Parameters
    ----------
    mapping : MappingResult
        Full mapping result containing statistics, architecture metadata,
        mapped groups, and passthrough LUTs.

    Returns
    -------
    str
        Fully rendered report text.
    """
    template: str = REPORT_TEMPLATE

    before_counts: dict[str, int] = dict(mapping.stats.source_type_count)
    after_counts: dict[str, int] = _compute_after_counts(mapping)

    before_stats: str = _format_lut_type_stats(
        total=mapping.stats.total_luts_before,
        counts=before_counts,
        preferred_first=(),
    )

    after_stats: str = _format_lut_type_stats(
        total=mapping.stats.total_cells_after,
        counts=after_counts,
        preferred_first=(mapping.architecture_name,),
    )

    return template.format(
        architecture=mapping.architecture_name,
        top=mapping.top_name,
        total_luts_before=mapping.stats.total_luts_before,
        total_cells_after=mapping.stats.total_cells_after,
        mapped_groups=mapping.stats.mapped_groups,
        mapped_luts=mapping.stats.mapped_luts,
        passthrough_luts=mapping.stats.passthrough_luts,
        before_stats=before_stats,
        after_stats=after_stats,
    )


def _compute_after_counts(mapping: MappingResult) -> dict[str, int]:
    """Compute LUT-type counts for the mapped design view.

    The mapped view includes passthrough LUT cells by their original LUT type
    and adds one entry for the fractional architecture cell when at least one
    mapping group was created.

    Parameters
    ----------
    mapping : MappingResult
        Mapping result that provides passthrough LUTs and group statistics.

    Returns
    -------
    dict[str, int]
        Mapping from cell type name to count for the post-pack design.
    """
    return mapping.stats.result_type_count


def _format_lut_type_stats(
    total: int, counts: dict[str, int], preferred_first: tuple[str, ...]
) -> str:
    """Format LUT-type statistics as a readable multi-line table.

    Type rows are ordered using preferred names first and then a stable default
    ordering. Percentages are computed relative to ``total`` and shown with one
    decimal place.

    Parameters
    ----------
    total : int
        Total number of LUT-like cells for percentage normalization.
    counts : dict[str, int]
        Per-type cell counts.
    preferred_first : tuple[str, ...]
        Type names that should appear first when present.

    Returns
    -------
    str
        Formatted statistics block suitable for report embedding.
    """
    lines: list[str] = ["LUT Type Statistics:", f"  Total LUTs: {total}"]

    if total <= 0:
        return "\n".join(lines)

    ordered_keys: list[str] = _ordered_types(counts, preferred_first)

    for key in ordered_keys:
        value: int = counts[key]
        pct: float = (100.0 * value) / float(total)
        lines.append(f"    {key}: {value} ({pct:.1f}%)")
    return "\n".join(lines)


def _ordered_types(
    counts: dict[str, int], preferred_first: tuple[str, ...]
) -> list[str]:
    """Return a deterministic display order for type names.

    Preferred names are emitted first in declaration order when present.
    Remaining names are sorted with ``_type_sort_key`` so LUTN names are shown
    before non-LUT names.

    Parameters
    ----------
    counts : dict[str, int]
        Per-type counts whose keys define candidate type names.
    preferred_first : tuple[str, ...]
        Type names to prioritize at the start of the output order.

    Returns
    -------
    list[str]
        Ordered list of type names for display.
    """
    out: list[str] = []

    for key in preferred_first:
        if key in counts and key not in out:
            out.append(key)

    remaining: list[str] = [k for k in counts if k not in out]
    remaining.sort(key=_type_sort_key)

    out.extend(remaining)
    return out


def _type_sort_key(name: str) -> tuple[int, int, str]:
    """Build a sort key that keeps LUTN names in numeric order.

    Names like ``LUT2`` and ``LUT10`` are sorted by their numeric suffix.
    All other names are placed after LUT names and sorted lexicographically.

    Parameters
    ----------
    name : str
        Cell type name to classify for sorting.

    Returns
    -------
    tuple[int, int, str]
        Composite key ``(group, lut_index, name)`` for stable ordering.
    """
    if name.startswith("LUT") and name[3:].isdigit():
        return (0, int(name[3:]), name)
    return (1, 0, name)

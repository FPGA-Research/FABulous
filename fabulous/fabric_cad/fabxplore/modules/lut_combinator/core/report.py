"""Create text reports for LUT packing results.

This module renders human-readable summaries from a ``MappingResult`` and a
Jinja2 template. It also computes and formats LUT type distributions so users
can compare source and mapped designs quickly.
"""

from collections import Counter
from dataclasses import dataclass

from jinja2 import Environment

from fabulous.fabric_cad.fabxplore.modules.lut_combinator.core.models import (
    MappingResult,
    PackedCell,
)

_REPORT_ENV = Environment(
    autoescape=False,
    keep_trailing_newline=True,
    lstrip_blocks=True,
    trim_blocks=True,
)

REPORT_TEMPLATE = """\
LUT Combinator Mapping Report
Architecture: {{ architecture }}
Top Module: {{ top }}
{% if config_lines %}

Configuration
{% for line in config_lines %}
- {{ line }}
{% endfor %}
{% endif %}

Before {{ architecture }} packing:
{{ before_stats }}

After {{ architecture }} packing:
{{ after_stats }}

Summary
- Mapped Groups: {{ mapped_groups }}
- Mapped LUTs: {{ mapped_luts }}
- Passthrough LUTs: {{ passthrough_luts }}
- Pair mapped cells: {{ pair_stats.total_cells }}
{% if pair_stats.combination_rows %}
{% for row in pair_stats.combination_rows %}
  - {{ row.label }}: {{ row.count }} pair cells ({{ row.percent }})
{% for shared_row in row.child_rows %}
    - {{ shared_row.label }}: {{ shared_row.count }} cells ({{ shared_row.percent }})
{% endfor %}
{% endfor %}
{% endif %}
- Single mapped cells: {{ single_stats.total_cells }}
{% if single_stats.type_rows %}
{% for row in single_stats.type_rows %}
  - {{ row.label }}: {{ row.count }} cells ({{ row.percent }})
{% endfor %}
{% endif %}

Pair Packing
- Normal dual cells (select-as-data not used): {{ pair_stats.normal_dual_cells }}
- Select-as-data dual cells: {{ pair_stats.select_as_data_cells }}
{% if pair_stats.select_as_data_cells > 0 and pair_stats.normal_dual_cells == 0 %}
- Note: all dual cells used select-as-data, so the normal dual count is 0.
{% endif %}
- Packed pairs by logical shared inputs:
{% if pair_stats.shared_input_rows %}
{% for row in pair_stats.shared_input_rows %}
  - {{ row.label }}: {{ row.count }} pair cells ({{ row.percent }})
{% endfor %}
{% else %}
  - none
{% endif %}
{% if pair_stats.dominant_shared_inputs %}
- Most packed pairs use {{ pair_stats.dominant_shared_inputs }}.
{% endif %}
- Logical shared inputs:
  total={{ pair_stats.total_logical_shared_inputs }},
  average={{ pair_stats.avg_logical_shared_inputs }}
- Effective shared-input capacity:
  total={{ pair_stats.total_effective_shared_capacity }},
  average={{ pair_stats.avg_effective_shared_inputs }}
- Shared-input utilization of effective capacity:
  {{ pair_stats.effective_shared_utilization_pct }}
- Shared-input utilization of nominal capacity:
  {{ pair_stats.nominal_shared_utilization_pct }}

Single/Full LUT Packing
- Single/full mapped cells: {{ single_stats.total_cells }}
- Total leftover LUT input width: {{ single_stats.total_leftover_lut_width }}
{% if single_stats.has_effective_leftover %}
  - effective with select-as-data: {{ single_stats.total_effective_leftover_lut_width }}
{% endif %}
- Average leftover LUT input width: {{ single_stats.avg_leftover_lut_width }}
{% if single_stats.has_effective_leftover %}
  - effective with select-as-data: {{ single_stats.avg_effective_leftover_lut_width }}
{% endif %}
- Cells with reusable leftover width >= 1: {{ single_stats.reusable_leftover_cells }}
{% if single_stats.leftover_type_rows %}
{% for row in single_stats.leftover_type_rows %}
  - reusable {{ row.label }} capacity: {{ row.count }} cells ({{ row.percent }})
{% endfor %}
{% endif %}
{% if single_stats.total_cells > 0 %}
- Note: a single/full mapped FRAC cell with leftover width >= 1 has
  remaining LUT capacity that could be targeted by a later synthesis/remapping
  step.
{% endif %}

Capacity
- Total leftover LUT input width across mapped cells: {{ total_leftover_lut_width }}
- Effective leftover LUT input width across mapped cells:
  {{ total_effective_leftover_lut_width }}
- Mapped cells with leftover width >= 1: {{ reusable_leftover_cells }}
{% if reordering_report %}

{{ reordering_report }}
{% endif %}
{% if reorder_opt_report %}

{{ reorder_opt_report }}
{% endif %}
"""

_REPORT_TEMPLATE = _REPORT_ENV.from_string(REPORT_TEMPLATE)


@dataclass(frozen=True)
class BreakdownRow:
    """One display row for count/percentage breakdowns."""

    label: str
    count: int
    percent: str
    child_rows: tuple["BreakdownRow", ...] = ()


@dataclass(frozen=True)
class PairPackingStats:
    """Statistics for two-LUT packed cells."""

    total_cells: int
    normal_dual_cells: int
    select_as_data_cells: int
    combination_rows: tuple[BreakdownRow, ...]
    shared_input_rows: tuple[BreakdownRow, ...]
    dominant_shared_inputs: str
    total_logical_shared_inputs: int
    avg_logical_shared_inputs: str
    total_effective_shared_capacity: int
    avg_effective_shared_inputs: str
    effective_shared_utilization_pct: str
    nominal_shared_utilization_pct: str


@dataclass(frozen=True)
class SinglePackingStats:
    """Statistics for one-LUT/full-LUT mapped cells."""

    total_cells: int
    type_rows: tuple[BreakdownRow, ...]
    has_effective_leftover: bool
    total_leftover_lut_width: int
    total_effective_leftover_lut_width: int
    avg_leftover_lut_width: str
    avg_effective_leftover_lut_width: str
    reusable_leftover_cells: int
    leftover_type_rows: tuple[BreakdownRow, ...]


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

    mapped_cells: list[PackedCell] = mapping.mapped_cells
    pair_stats: PairPackingStats = _compute_pair_stats(mapped_cells)
    single_stats: SinglePackingStats = _compute_single_stats(mapped_cells)

    return _REPORT_TEMPLATE.render(
        architecture=mapping.architecture_name,
        top=mapping.top_name,
        config_lines=_format_config_lines(mapping.metadata),
        mapped_groups=mapping.stats.mapped_groups,
        mapped_luts=mapping.stats.mapped_luts,
        passthrough_luts=mapping.stats.passthrough_luts,
        before_stats=before_stats,
        after_stats=after_stats,
        pair_stats=pair_stats,
        single_stats=single_stats,
        total_leftover_lut_width=sum(c.leftover_lut_width for c in mapped_cells),
        total_effective_leftover_lut_width=sum(
            _effective_leftover_lut_width(c) for c in mapped_cells
        ),
        reusable_leftover_cells=sum(
            1 for c in mapped_cells if c.leftover_lut_width >= 1
        ),
        reordering_report=mapping.metadata.get("_leftover_reordering_report", ""),
        reorder_opt_report=mapping.metadata.get("_reorder_opt_report", ""),
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


def _format_config_lines(metadata: dict) -> list[str]:
    """Format mapping metadata for report display.

    Parameters
    ----------
    metadata : dict
        Mapping metadata attached to the result.

    Returns
    -------
    list[str]
        Human-readable configuration lines.
    """
    lines: list[str] = []
    ordered_keys: tuple[str, ...] = (
        "frac_lut_size",
        "num_shared_inputs",
        "passthrough",
        "mode",
    )

    for key in ordered_keys:
        if key in metadata:
            lines.append(f"{key}: {metadata[key]}")

    for key in sorted(
        k for k in metadata if k not in ordered_keys and not k.startswith("_")
    ):
        lines.append(f"{key}: {metadata[key]}")

    return lines


def _compute_pair_stats(mapped_cells: list[PackedCell]) -> PairPackingStats:
    """Compute statistics for cells that pack two logical LUTs.

    Parameters
    ----------
    mapped_cells : list[PackedCell]
        Packed cells emitted by the mapper.

    Returns
    -------
    PairPackingStats
        Aggregate pair-packing metrics.
    """
    pair_cells: list[PackedCell] = [c for c in mapped_cells if len(c.placements) == 2]
    total_cells: int = len(pair_cells)
    select_as_data_cells: int = sum(
        1 for c in pair_cells if c.frac_lut_parameters.select_as_data_used
    )
    normal_dual_cells: int = total_cells - select_as_data_cells
    logical_shared_counts: list[int] = [
        _logical_shared_input_count(c) for c in pair_cells
    ]
    effective_shared_inputs: list[int] = [
        _effective_shared_inputs(c) for c in pair_cells
    ]
    nominal_shared_inputs: list[int] = [
        c.frac_lut_parameters.num_shared_inputs for c in pair_cells
    ]

    total_logical_shared: int = sum(logical_shared_counts)
    total_effective_capacity: int = sum(effective_shared_inputs)
    total_nominal_capacity: int = sum(nominal_shared_inputs)
    shared_histogram: Counter[int] = Counter(logical_shared_counts)

    return PairPackingStats(
        total_cells=total_cells,
        normal_dual_cells=normal_dual_cells,
        select_as_data_cells=select_as_data_cells,
        combination_rows=_format_pair_combination_rows(pair_cells),
        shared_input_rows=_format_shared_input_rows(shared_histogram, total_cells),
        dominant_shared_inputs=_format_dominant_shared_inputs(shared_histogram),
        total_logical_shared_inputs=total_logical_shared,
        avg_logical_shared_inputs=_format_average(total_logical_shared, total_cells),
        total_effective_shared_capacity=total_effective_capacity,
        avg_effective_shared_inputs=_format_average(
            total_effective_capacity, total_cells
        ),
        effective_shared_utilization_pct=_format_percentage(
            total_logical_shared,
            total_effective_capacity,
        ),
        nominal_shared_utilization_pct=_format_percentage(
            total_logical_shared,
            total_nominal_capacity,
        ),
    )


def _compute_single_stats(mapped_cells: list[PackedCell]) -> SinglePackingStats:
    """Compute statistics for one-LUT/full-LUT mapped cells.

    Parameters
    ----------
    mapped_cells : list[PackedCell]
        Packed cells emitted by the mapper.

    Returns
    -------
    SinglePackingStats
        Aggregate single/full-cell metrics.
    """
    single_cells: list[PackedCell] = [c for c in mapped_cells if len(c.placements) == 1]
    total_cells: int = len(single_cells)
    total_leftover: int = sum(c.leftover_lut_width for c in single_cells)
    total_effective_leftover: int = sum(
        _effective_leftover_lut_width(c) for c in single_cells
    )

    return SinglePackingStats(
        total_cells=total_cells,
        type_rows=_format_single_type_rows(single_cells),
        has_effective_leftover=any(
            _effective_leftover_lut_width(c) != c.leftover_lut_width
            for c in single_cells
        ),
        total_leftover_lut_width=total_leftover,
        total_effective_leftover_lut_width=total_effective_leftover,
        avg_leftover_lut_width=_format_average(total_leftover, total_cells),
        avg_effective_leftover_lut_width=_format_average(
            total_effective_leftover, total_cells
        ),
        reusable_leftover_cells=sum(
            1 for c in single_cells if c.leftover_lut_width >= 1
        ),
        leftover_type_rows=_format_leftover_type_rows(single_cells),
    )


def _format_pair_combination_rows(
    pair_cells: list[PackedCell],
) -> tuple[BreakdownRow, ...]:
    """Format pair-cell counts by logical LUT type combination.

    Parameters
    ----------
    pair_cells : list[PackedCell]
        Packed cells containing exactly two logical LUT placements.

    Returns
    -------
    tuple[BreakdownRow, ...]
        Count rows keyed by unordered LUT type combinations.
    """
    total: int = len(pair_cells)
    cells_by_combination: dict[tuple[str, str], list[PackedCell]] = {}
    for cell in pair_cells:
        cells_by_combination.setdefault(_pair_type_key(cell), []).append(cell)

    rows: list[BreakdownRow] = []

    for key, cells in sorted(
        cells_by_combination.items(), key=lambda item: _pair_row_sort_key(item[0])
    ):
        count: int = len(cells)
        shared_histogram: Counter[int] = Counter(
            _logical_shared_input_count(cell) for cell in cells
        )
        rows.append(
            BreakdownRow(
                label=f"{key[0]} + {key[1]}",
                count=count,
                percent=_format_percentage(count, total),
                child_rows=_format_shared_input_rows(shared_histogram, count),
            )
        )

    return tuple(rows)


def _format_single_type_rows(
    single_cells: list[PackedCell],
) -> tuple[BreakdownRow, ...]:
    """Format single-cell counts by source LUT type.

    Parameters
    ----------
    single_cells : list[PackedCell]
        Packed cells containing exactly one logical LUT placement.

    Returns
    -------
    tuple[BreakdownRow, ...]
        Count rows keyed by the single mapped LUT type.
    """
    total: int = len(single_cells)
    counts: Counter[str] = Counter(
        _lut_width_label(c.placements[0].cell.width) for c in single_cells
    )
    rows: list[BreakdownRow] = []

    for lut_type in _ordered_types(dict(counts), ()):
        rows.append(
            BreakdownRow(
                label=lut_type,
                count=counts[lut_type],
                percent=_format_percentage(counts[lut_type], total),
            )
        )

    return tuple(rows)


def _format_leftover_type_rows(
    single_cells: list[PackedCell],
) -> tuple[BreakdownRow, ...]:
    """Format reusable leftover LUT capacity by effective LUT width.

    Parameters
    ----------
    single_cells : list[PackedCell]
        Packed cells containing exactly one logical LUT placement.

    Returns
    -------
    tuple[BreakdownRow, ...]
        Count rows keyed by reusable leftover LUT width.
    """
    reusable_cells: list[PackedCell] = [
        cell for cell in single_cells if cell.leftover_lut_width >= 1
    ]
    total: int = len(reusable_cells)
    counts: Counter[str] = Counter(
        _leftover_capacity_label(cell) for cell in reusable_cells
    )
    rows: list[BreakdownRow] = []

    for lut_type in _ordered_types(dict(counts), ()):
        rows.append(
            BreakdownRow(
                label=lut_type,
                count=counts[lut_type],
                percent=_format_percentage(counts[lut_type], total),
            )
        )

    return tuple(rows)


def _leftover_capacity_label(cell: PackedCell) -> str:
    """Return the physical and optional effective leftover LUT capacity label."""
    physical_label = _lut_width_label(cell.leftover_lut_width)
    effective_width = _effective_leftover_lut_width(cell)

    if effective_width == cell.leftover_lut_width:
        return physical_label
    return f"{physical_label} (effective {_lut_width_label(effective_width)})"


def _format_shared_input_rows(
    shared_histogram: Counter[int], total_cells: int
) -> tuple[BreakdownRow, ...]:
    """Format pair-cell counts by actual logical shared-input count.

    Parameters
    ----------
    shared_histogram : Counter[int]
        Counter from shared-input count to number of packed pair cells.
    total_cells : int
        Total number of packed pair cells.

    Returns
    -------
    tuple[BreakdownRow, ...]
        Count rows sorted by shared-input count.
    """
    rows: list[BreakdownRow] = []

    for shared_count in sorted(shared_histogram):
        rows.append(
            BreakdownRow(
                label=f"{shared_count}-shared inputs",
                count=shared_histogram[shared_count],
                percent=_format_percentage(shared_histogram[shared_count], total_cells),
            )
        )

    return tuple(rows)


def _format_dominant_shared_inputs(shared_histogram: Counter[int]) -> str:
    """Return a readable summary of the most common shared-input count.

    Parameters
    ----------
    shared_histogram : Counter[int]
        Counter from shared-input count to number of packed pair cells.

    Returns
    -------
    str
        Text such as ``"2-shared inputs"`` or ``"1- and 2-shared inputs"``
        when there is a tie.
    """
    if not shared_histogram:
        return ""

    highest_count: int = max(shared_histogram.values())
    dominant_counts: list[int] = [
        shared_count
        for shared_count, count in shared_histogram.items()
        if count == highest_count
    ]
    dominant_counts.sort()

    labels: list[str] = [f"{count}-shared inputs" for count in dominant_counts]
    return _join_labels(labels)


def _pair_type_key(cell: PackedCell) -> tuple[str, str]:
    """Return an unordered LUT type key for a packed pair cell."""
    lut_types: list[str] = [_lut_width_label(p.cell.width) for p in cell.placements]
    lut_types.sort(key=_type_sort_key)
    return (lut_types[0], lut_types[1])


def _lut_width_label(width: int) -> str:
    """Return the display name for a logical LUT width."""
    return f"LUT{width}"


def _pair_row_sort_key(key: tuple[str, str]) -> tuple[tuple[int, int, str], ...]:
    """Return a deterministic sort key for pair-combination rows."""
    return (_type_sort_key(key[0]), _type_sort_key(key[1]))


def _join_labels(labels: list[str]) -> str:
    """Join display labels using a compact natural-language form."""
    if len(labels) <= 1:
        return "".join(labels)
    if len(labels) == 2:
        return f"{labels[0]} and {labels[1]}"
    return f"{', '.join(labels[:-1])}, and {labels[-1]}"


def _logical_shared_input_count(cell: PackedCell) -> int:
    """Return the number of logical input nets shared by both placements.

    Parameters
    ----------
    cell : PackedCell
        Packed pair cell.

    Returns
    -------
    int
        Count of distinct input nets used by both logical LUTs.
    """
    if len(cell.placements) != 2:
        return 0
    nets0: set[str] = set(cell.placements[0].cell.input_nets)
    nets1: set[str] = set(cell.placements[1].cell.input_nets)
    return len(nets0 & nets1)


def _effective_shared_inputs(cell: PackedCell) -> int:
    """Return the effective shared-input count for one packed cell.

    Parameters
    ----------
    cell : PackedCell
        Packed cell with typed FRAC parameters.

    Returns
    -------
    int
        Effective shared-input count after select-as-data adjustment.
    """
    params = cell.frac_lut_parameters
    if params.effective_shared_inputs is None:
        return params.num_shared_inputs
    return params.effective_shared_inputs


def _effective_leftover_lut_width(cell: PackedCell) -> int:
    """Return leftover LUT width including select-as-data extra capacity."""
    if len(cell.placements) == 1 and cell.frac_lut_parameters.select_as_data_capable:
        return cell.leftover_lut_width + 1
    return cell.leftover_lut_width


def _format_average(total: int, count: int) -> str:
    """Format an average as text.

    Parameters
    ----------
    total : int
        Numerator.
    count : int
        Denominator.

    Returns
    -------
    str
        Average with two decimal places or ``"n/a"`` when unavailable.
    """
    if count <= 0:
        return "n/a"
    return f"{total / count:.2f}"


def _format_percentage(numerator: int, denominator: int) -> str:
    """Format a percentage as text.

    Parameters
    ----------
    numerator : int
        Numerator value.
    denominator : int
        Denominator value.

    Returns
    -------
    str
        Percentage with one decimal place or ``"n/a"`` when unavailable.
    """
    if denominator <= 0:
        return "n/a"
    return f"{(100.0 * numerator) / float(denominator):.1f}%"


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

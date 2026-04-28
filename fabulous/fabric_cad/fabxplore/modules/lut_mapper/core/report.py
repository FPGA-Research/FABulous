"""Render human-readable reports for LUT mapper cost decisions.

The report module is intentionally presentation-only. It receives a populated
``LutMapperResult`` and formats the cost-model configuration, pairability
matrices, final ABC cost vector, and emitted pyosys commands into a stable text
summary for logs and DSE comparisons.
"""

from jinja2 import Environment

from fabulous.fabric_cad.fabxplore.modules.lut_mapper.core.models import (
    LutMapperResult,
)

_REPORT_ENV = Environment(
    autoescape=False,
    keep_trailing_newline=True,
    lstrip_blocks=True,
    trim_blocks=True,
)

REPORT_TEMPLATE = """\
LUT Mapper Report
Top Module: {{ result.top_name }}

Configuration
- base_lut_size: {{ cfg.base_lut_size }}
- num_shared_inputs: {{ cfg.num_shared_inputs }}
- use_select_as_data_in_pair_mode: {{ cfg.use_select_as_data_in_pair_mode }}
- max_lut_size: {{ cfg.max_lut_size }}
- backend: {{ cfg.backend.value }}
- sharing_penalty_factor: {{ cfg.sharing_penalty_factor }}
- size_penalty_factor: {{ cfg.size_penalty_factor }}
- pair_discount_strength: {{ cfg.pair_discount_strength }}
- larger_lut_base_multiplier: {{ cfg.larger_lut_base_multiplier }}
- larger_lut_discount_factor: {{ cfg.larger_lut_discount_factor }}
- cost_scale: {{ cfg.cost_scale }}
- min_cost: {{ cfg.min_cost }}
- max_cost: {{ cfg.max_cost if cfg.max_cost is not none else "none" }}
- raw_cost_vector_override: {{ result.cost_vector.raw_override_used }}
- run_opt_lut: {{ cfg.run_opt_lut }}
- run_clean: {{ cfg.run_clean }}

Derived Architecture Model
- effective_shared_inputs: {{ result.effective_shared_inputs }}
- effective_private_inputs: {{ result.effective_private_inputs }}
- pair_capacity: {{ result.pair_capacity }}
- pairability formula:
  combined = {{ cfg.sharing_penalty_factor }} * required_shared
           + {{ cfg.size_penalty_factor }} * unused_capacity

Required Shared Inputs
{{ sharing_table }}

Unused-Capacity Penalty
{{ size_table }}

Combined Pair Penalty
{{ combined_table }}

Pairability By Width
{% for width, score in pairability_rows %}
- LUT{{ width }}: {{ "%.3f"|format(score) }}
{% endfor %}

ABC Cost Histogram
{% for width, cost in cost_rows %}
- LUT{{ width }}: {{ cost }}
{% endfor %}

Commands
- {{ result.abc_command }}
{% for command in result.followup_commands %}
- {{ command }}
{% endfor %}
"""

_REPORT_TEMPLATE = _REPORT_ENV.from_string(REPORT_TEMPLATE)


def render_lut_mapper_report(result: LutMapperResult) -> str:
    """Render a report string from a LUT mapper result.

    Parameters
    ----------
    result : LutMapperResult
        Complete result object produced by the LUT mapper.

    Returns
    -------
    str
        Human-readable report containing settings, analytical tables, and the
        emitted ABC cost vector.
    """
    cost_rows = tuple(enumerate(result.cost_vector.costs, start=1))
    pairability_rows = tuple(
        zip(result.widths, result.pairability_by_width, strict=True)
    )

    return _REPORT_TEMPLATE.render(
        result=result,
        cfg=result.config,
        sharing_table=_format_matrix(result.widths, result.sharing_required_table),
        size_table=_format_matrix(result.widths, result.size_penalty_table),
        combined_table=_format_matrix(result.widths, result.combined_penalty_table),
        pairability_rows=pairability_rows,
        cost_rows=cost_rows,
    )


def _format_matrix(
    widths: tuple[int, ...],
    rows: tuple[tuple[float, ...], ...],
) -> str:
    """Format one pair-width matrix as a fixed-width text table.

    Parameters
    ----------
    widths : tuple[int, ...]
        LUT widths used for both row and column labels.
    rows : tuple[tuple[float, ...], ...]
        Matrix values to display. Each row must have the same length as
        ``widths``.

    Returns
    -------
    str
        Multi-line table with aligned ``LUTN`` row and column labels.
    """
    labels = [f"LUT{width}" for width in widths]
    cell_text: list[list[str]] = [
        [_format_number(value) for value in row] for row in rows
    ]

    first_col_width = max(len(""), *(len(label) for label in labels))
    col_widths: list[int] = []
    for col_idx, label in enumerate(labels):
        values = [row[col_idx] for row in cell_text]
        col_widths.append(max(len(label), *(len(value) for value in values)))

    header = " " * first_col_width
    header += "  " + "  ".join(
        label.rjust(col_widths[idx]) for idx, label in enumerate(labels)
    )

    out_lines = [header.rstrip()]
    for row_idx, label in enumerate(labels):
        values = "  ".join(
            cell_text[row_idx][col_idx].rjust(col_widths[col_idx])
            for col_idx in range(len(labels))
        )
        out_lines.append(f"{label.rjust(first_col_width)}  {values}".rstrip())
    return "\n".join(out_lines)


def _format_number(value: float) -> str:
    """Format one matrix cell without noisy trailing zeros.

    Parameters
    ----------
    value : float
        Matrix value to format.

    Returns
    -------
    str
        Integer-looking values are rendered without decimals; fractional
        values are rendered with three digits after the decimal point.
    """
    if isinstance(value, int):
        return str(value)
    if value.is_integer():
        return str(int(value))
    return f"{value:.3f}"

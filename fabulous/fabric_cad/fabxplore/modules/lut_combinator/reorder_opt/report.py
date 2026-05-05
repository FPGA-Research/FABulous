"""Render reports for reorder-opt area optimization results."""

from jinja2 import Environment

from fabulous.fabric_cad.fabxplore.modules.lut_combinator.reorder_opt.models import (
    ReorderOptMove,
    ReorderOptStats,
)

_REPORT_ENV = Environment(
    autoescape=False,
    keep_trailing_newline=True,
    lstrip_blocks=True,
    trim_blocks=True,
)

REPORT_TEMPLATE = """\
Reorder Opt
- Candidate host single cells: {{ stats.candidate_hosts }}
- Candidate donor pair cells: {{ stats.candidate_donors }}
- Legal optimizations: {{ stats.legal_optimizations }}
- Applied optimizations: {{ stats.applied_optimizations }}
- FRAC cells before: {{ stats.frac_cells_before }}
- FRAC cells after: {{ stats.frac_cells_after }}
- FRAC cells saved: {{ stats.frac_cells_saved }}
- Reusable effective leftover before: {{ stats.reusable_leftover_before }}
- Reusable effective leftover after: {{ stats.reusable_leftover_after }}
- Reusable effective leftover delta: {{ stats.reusable_leftover_delta }}
{% if stats.move_type_count %}
- Applied optimizations by type:
{% for label, count in move_type_rows %}
  - {{ label }}: {{ count }} optimizations
{% endfor %}
{% endif %}
{% if moves %}
- Optimizations:
{% for move in moves %}
  - removed {{ move.donor_packed_id }};
    moved {{ move.moved0_cell_id }} (LUT{{ move.moved0_width }})
    into {{ move.host0_packed_id }} and
    {{ move.moved1_cell_id }} (LUT{{ move.moved1_width }})
    into {{ move.host1_packed_id }};
    leftover_waste={{ move.leftover_waste }}
{% endfor %}
{% else %}
- Note: no legal pair cell could be removed with the available leftovers.
{% endif %}
"""

_REPORT_TEMPLATE = _REPORT_ENV.from_string(REPORT_TEMPLATE)


def render_reorder_opt_report(
    stats: ReorderOptStats, moves: tuple[ReorderOptMove, ...]
) -> str:
    """Render a human-readable reorder-opt report.

    Parameters
    ----------
    stats : ReorderOptStats
        Aggregate counters for the optimization run.
    moves : tuple[ReorderOptMove, ...]
        Applied optimizations to list in the report.

    Returns
    -------
    str
        Rendered report block.
    """
    return _REPORT_TEMPLATE.render(
        stats=stats,
        moves=moves,
        move_type_rows=tuple(sorted(stats.move_type_count.items())),
    ).rstrip()

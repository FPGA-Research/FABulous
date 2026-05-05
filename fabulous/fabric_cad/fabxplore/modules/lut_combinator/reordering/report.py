"""Render reports for LUT leftover reordering results."""

from jinja2 import Environment

from fabulous.fabric_cad.fabxplore.modules.lut_combinator.reordering.models import (
    LeftoverReorderingStats,
    ReorderingMove,
)

_REPORT_ENV = Environment(
    autoescape=False,
    keep_trailing_newline=True,
    lstrip_blocks=True,
    trim_blocks=True,
)

REPORT_TEMPLATE = """\
Leftover Reordering
- Candidate host single cells: {{ stats.candidate_hosts }}
- Candidate donor pair cells: {{ stats.candidate_donors }}
- Legal profitable moves: {{ stats.legal_moves }}
- Applied moves: {{ stats.applied_moves }}
- Reusable effective leftover before: {{ stats.reusable_leftover_before }}
- Reusable effective leftover after: {{ stats.reusable_leftover_after }}
- Reusable effective leftover gain: {{ stats.reusable_leftover_gain }}
{% if stats.move_type_count %}
- Applied moves by type:
{% for label, count in move_type_rows %}
  - {{ label }}: {{ count }} moves
{% endfor %}
{% endif %}
{% if moves %}
- Moves:
{% for move in moves %}
  - {{ move.moved_cell_id }} (LUT{{ move.moved_width }}) from {{ move.donor_packed_id }}
    into {{ move.host_packed_id }} with LUT{{ move.host_width }};
    donor keeps {{ move.remaining_cell_id }} (LUT{{ move.remaining_width }}),
    gain={{ move.gain }}
{% endfor %}
{% else %}
- Note: no profitable legal leftover reordering move was available.
{% endif %}
"""

_REPORT_TEMPLATE = _REPORT_ENV.from_string(REPORT_TEMPLATE)


def render_reordering_report(
    stats: LeftoverReorderingStats, moves: tuple[ReorderingMove, ...]
) -> str:
    """Render a human-readable leftover reordering report.

    Parameters
    ----------
    stats : LeftoverReorderingStats
        Aggregate counters for the reordering run.
    moves : tuple[ReorderingMove, ...]
        Applied moves to list in the report.

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

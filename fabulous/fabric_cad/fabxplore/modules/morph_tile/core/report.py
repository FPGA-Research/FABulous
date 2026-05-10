"""Render compact reports for morph-tile mapping runs."""

from jinja2 import Environment

from fabulous.fabric_cad.fabxplore.modules.morph_tile.core.models import (
    MorphTileResult,
)

_REPORT_ENV = Environment(
    autoescape=False,
    keep_trailing_newline=True,
    lstrip_blocks=True,
    trim_blocks=True,
)

REPORT_TEMPLATE = """\
Morph Tile Mapping Report
Top Module: {{ result.top_name }}
Tile Module: {{ result.tile_top_name }}

Configuration
{% if result.filter_summary %}
{% for name, values in result.filter_summary | dictsort %}
- {{ name }}: {{ values }}
{% endfor %}
{% else %}
- filters: none
{% endif %}
- max_replacements:
  {{ result.max_replacements if result.max_replacements is not none else "none" }}

Summary
- Total candidates: {{ stats.total_candidates }}
- Checked candidates: {{ stats.checked_candidates }}
- Replaced candidates: {{ stats.replaced_candidates }}
  - of all candidates: {{ "%.1f"|format(result.replaced_total_percent) }}%
  - of checked candidates:
    {{ "%.1f"|format(result.replaced_checked_candidate_percent) }}%
- Failed candidates: {{ stats.failed_candidates }}
- Skipped candidates: {{ stats.skipped_candidates }}
  - skipped by filter: {{ stats.skipped_filter_candidates }}
  - skipped after limit: {{ stats.skipped_limit_candidates }}
- Solver cache hits: {{ stats.cache_hits }}
- Solver cache misses: {{ stats.cache_misses }}

Replacements By Width
{% if stats.replacements_by_width %}
{% for label, count in stats.replacements_by_width | dictsort %}
- {{ label }}: {{ count }}
{% endfor %}
{% else %}
- none
{% endif %}

Failures By Width
{% if stats.failures_by_width %}
{% for label, count in stats.failures_by_width | dictsort %}
- {{ label }}: {{ count }}
{% endfor %}
{% else %}
- none
{% endif %}

Top Replaced Signatures
{% if init_rows %}
{% for label, count in init_rows %}
- {{ label }}: {{ count }}
{% endfor %}
{% else %}
- none
{% endif %}
"""

_REPORT_TEMPLATE = _REPORT_ENV.from_string(REPORT_TEMPLATE)


def render_morph_tile_report(result: MorphTileResult, max_init_rows: int = 12) -> str:
    """Render a human-readable morph-tile mapping summary.

    Parameters
    ----------
    result : MorphTileResult
        Mapping result to summarize.
    max_init_rows : int
        Maximum number of INIT histogram rows to display.

    Returns
    -------
    str
        Rendered report text.
    """
    init_rows = sorted(
        result.stats.mapped_init_count.items(),
        key=lambda item: (-item[1], item[0]),
    )[:max_init_rows]
    return _REPORT_TEMPLATE.render(
        result=result,
        stats=result.stats,
        init_rows=init_rows,
    ).rstrip()

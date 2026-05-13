"""Render register absorption reports."""

from jinja2 import Template

from fabulous.fabric_cad.fabxplore.modules.reg_absorber.core.models import (
    RegAbsorberResult,
    count_absorptions_by_type,
)

_REPORT_TEMPLATE = Template(
    """Register Absorber Report
Top Module: {{ result.top_name }}

Configuration
- Rules: {{ result.rules | length }}
- FF cell types: {{ result.ff_ports.keys() | list | join(", ") }}

Summary
- Primitive cells considered: {{ stats.primitive_cells }}
- FF cells considered: {{ stats.ff_cells }}
- Absorbed FFs: {{ result.absorptions | length }}
  - output-side: {{ stats.output_absorptions }}
  - input-side: {{ stats.input_absorptions }}

Skipped
- no matching FF: {{ stats.skipped_no_match }}
- extra fanout: {{ stats.skipped_extra_fanout }}
- clock mismatch: {{ stats.skipped_clock_mismatch }}
- config conflict: {{ stats.skipped_config_conflict }}
- already used: {{ stats.skipped_already_used }}

Absorptions by Primitive Type
{% if by_type -%}
{% for cell_type, count in by_type.items() -%}
- {{ cell_type }}: {{ count }}
{% endfor -%}
{% else -%}
- none
{% endif -%}
"""
)


def render_reg_absorber_report(result: RegAbsorberResult) -> str:
    """Render a human-readable report.

    Parameters
    ----------
    result : RegAbsorberResult
        Structured absorption result.

    Returns
    -------
    str
        Report text.
    """
    return _REPORT_TEMPLATE.render(
        result=result,
        stats=result.stats,
        by_type=count_absorptions_by_type(result.absorptions),
    ).strip()

"""Render FF materialization reports."""

from jinja2 import Template

from fabulous.fabric_cad.fabxplore.modules.ff_materializer.core.models import (
    FfMaterializerResult,
    count_materializations_by_size,
)

_REPORT_TEMPLATE = Template(
    """FF Materializer Report
Top Module: {{ result.top_name }}

Configuration
- Tile top: {{ result.tile.top_name }}
- Tile Verilog: {{ result.tile.verilog_path }}
- Lanes: {{ result.lanes | length }}
- FF cell types: {{ result.ff_ports.keys() | list | join(", ") }}
- Config bits discovered: {{ result.tile.config_bits | length }}

Summary
- FF cells considered: {{ stats.ff_cells }}
- Materialized FFs: {{ stats.materialized_ffs }}
- Inserted tile instances: {{ stats.inserted_tiles }}

Skipped
- no compatible lane: {{ stats.skipped_no_lane }}
- control mismatch: {{ stats.skipped_control_mismatch }}
- config/param conflict: {{ stats.skipped_config_conflict }}
- replacement limit: {{ stats.skipped_limit }}

Inserted Tiles by Occupied Lane Count
{% if by_size -%}
{% for lane_count, count in by_size.items() -%}
- {{ lane_count }} lane(s): {{ count }}
{% endfor -%}
{% else -%}
- none
{% endif -%}
"""
)


def render_ff_materializer_report(result: FfMaterializerResult) -> str:
    """Render a human-readable report.

    Parameters
    ----------
    result : FfMaterializerResult
        Structured materialization result.

    Returns
    -------
    str
        Report text.
    """
    return _REPORT_TEMPLATE.render(
        result=result,
        stats=result.stats,
        by_size=count_materializations_by_size(result.materializations),
    ).strip()

"""Render FF materialization reports."""

from jinja2 import Template

from fabulous.fabric_cad.fabxplore.modules.ff_materializer.core.models import (
    FfMaterializerResult,
    count_bindings_by_depth,
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
- pack_multiple_ffs_per_tile: {{ result.options.pack_multiple_ffs_per_tile }}
- auto_config: {{ result.options.auto_config }}
- auto_config_overwrites:
{% if result.options.auto_config_overwrites %}
{% for name, value in result.options.auto_config_overwrites.items() | sort %}
  - {{ name }} = {{ value | int }}
{% endfor %}
{% else %}
- none
{% endif %}
- max_replacements: {{
    result.options.max_replacements
    if result.options.max_replacements is not none
    else "none"
}}
- fail_on_invalid_lane: {{ result.options.fail_on_invalid_lane }}
- fail_on_auto_config_unsat: {{ result.options.fail_on_auto_config_unsat }}
- fail_on_pack_conflict: {{ result.options.fail_on_pack_conflict }}
- fail_on_unmaterialized_ff: {{ result.options.fail_on_unmaterialized_ff }}
- progress_chunk_size: {{ result.options.progress_chunk_size }}

Summary
- FF cells considered: {{ stats.ff_cells }}
- Materialized FFs: {{ stats.materialized_ffs }}
- Inserted tile instances: {{ stats.inserted_tiles }}

Skipped
- no compatible lane: {{ stats.skipped_no_lane }}
- control mismatch: {{ stats.skipped_control_mismatch }}
- config/attribute conflict: {{ stats.skipped_config_conflict }}
- replacement limit: {{ stats.skipped_limit }}

Inserted Tiles by Occupied Lane Count
{% if by_size -%}
{% for lane_count, count in by_size.items() -%}
- {{ lane_count }} lane(s): {{ count }}
{% endfor -%}
{% else -%}
- none
{% endif -%}

Materialized Chunks by Depth
{% if by_depth -%}
{% for depth, count in by_depth.items() -%}
- depth {{ depth }}: {{ count }}
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
        by_depth=count_bindings_by_depth(result.materializations),
    ).strip()

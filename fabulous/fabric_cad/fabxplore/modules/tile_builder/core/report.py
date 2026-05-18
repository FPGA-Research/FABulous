"""Render reports for FABulous tile building."""

from jinja2 import Environment

from fabulous.fabric_cad.fabxplore.modules.tile_builder.core.models import (
    TileBuilderResult,
)

_REPORT_ENV = Environment(
    autoescape=False,
    keep_trailing_newline=True,
    lstrip_blocks=True,
    trim_blocks=True,
)

REPORT_TEMPLATE = """\
Tile Builder Report
Tile: {{ result.tile_name }}
Directory: {{ result.tile_dir }}

Configuration
- use_fabulous_auto: {{ result.options.routing.use_fabulous_auto }}
- input_fanin: {{ result.options.routing.input_fanin }}
- output_fanin: {{ result.options.routing.output_fanin }}
- min_input_fanin: {{ result.options.routing.min_input_fanin }}
- min_output_fanin: {{ result.options.routing.min_output_fanin }}
- config_bit_margin: {{ result.options.routing.config_bit_margin }}
- base_csv_includes: {{ result.options.routing.base_csv_includes }}
- base_list_includes: {{ result.options.routing.base_list_includes }}
- derive_sources_from_base: {{ result.options.routing.derive_sources_from_base }}
- cover_unconnected_outputs: {{ result.options.routing.cover_unconnected_outputs }}
- emit_constants_if_missing: {{ result.options.routing.emit_constants_if_missing }}
- allow_bel_output_feedback_sources:
  {{ result.options.routing.allow_bel_output_feedback_sources }}

BELs
- Instances: {{ stats.bel_instances }}
- Unique modules: {{ stats.unique_bel_modules }}
{% for module_name in modules %}
- {{ module_name }}: {{ module_counts[module_name] }}
{% endfor %}

Routing
- Matrix config bits: {{ stats.matrix_config_bits }}
- Input muxes: {{ stats.input_muxes }}
- Output muxes: {{ stats.output_muxes }}
- Direct connections: {{ stats.direct_connections }}
- Input fanin used: {{ stats.input_fanin_used }}
- Output fanin used: {{ stats.output_fanin_used }}

Config Bits
- BEL config bits: {{ stats.bel_config_bits }}
- Total config bits: {{ stats.total_config_bits }}
- Capacity: {{ stats.config_capacity }}

Artifacts
{% if result.artifacts %}
{% for artifact in result.artifacts %}
- {{ artifact.kind }}: {{ artifact.path }}
{% endfor %}
{% else %}
- none
{% endif %}

Warnings
{% if result.warnings %}
{% for warning in result.warnings %}
- {{ warning }}
{% endfor %}
{% else %}
- none
{% endif %}
"""

_REPORT_TEMPLATE = _REPORT_ENV.from_string(REPORT_TEMPLATE)


def render_tile_builder_report(result: TileBuilderResult) -> str:
    """Render a human-readable tile-builder report.

    Parameters
    ----------
    result : TileBuilderResult
        Structured tile-builder result.

    Returns
    -------
    str
        Report text.
    """
    module_counts: dict[str, int] = {}
    for module_name in result.parsed_bel_modules:
        module_counts[module_name] = module_counts.get(module_name, 0) + 1
    return _REPORT_TEMPLATE.render(
        result=result,
        stats=result.stats,
        modules=tuple(sorted(module_counts)),
        module_counts=module_counts,
    ).rstrip()

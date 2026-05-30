"""Human-readable reporting for switch-matrix pattern generation."""

from jinja2 import Environment

from fabulous.fabric_cad.fabxplore.modules.routing_patterns.core.models import (
    SwitchMatrixPatternResult,
)

_REPORT_ENV = Environment(
    autoescape=False,
    keep_trailing_newline=True,
    lstrip_blocks=True,
    trim_blocks=True,
)

REPORT_TEMPLATE = """\
Switch Matrix Pattern Report
Tile: {{ result.tile_name }}

Configuration
- input_fanin: {{ result.options.input_fanin }}
- include_bel_output_sources: {{ result.options.include_bel_output_sources }}
- include_constant_sources: {{ result.options.include_constant_sources }}
- output_fanin: {{ result.options.output_fanin }}
- cover_unconnected_matrix_rows:
  {{ result.options.cover_unconnected_matrix_rows }}
- routing_pip_pattern: {{ result.options.routing_pip_pattern.value }}
- routing_pip_fs: {{ result.options.routing_pip_fs }}
- generate_straight_routing_pips:
  {{ result.options.generate_straight_routing_pips }}
- generate_turn_routing_pips: {{ result.options.generate_turn_routing_pips }}
- hierarchy_enabled: {{ result.options.hierarchy_enabled }}
- hierarchy_levels: {{ result.options.hierarchy_levels }}
- hierarchy_jump_prefix: {{ result.options.hierarchy_jump_prefix }}
- hierarchy_replace_direct_input_pips:
  {{ result.options.hierarchy_replace_direct_input_pips }}
- replace_existing_matrix: {{ result.options.replace_existing_matrix }}
- delay: {{ result.options.delay }}

Matrix
- rows: {{ stats.rows_before }} -> {{ stats.rows_after }}
- columns: {{ stats.columns_before }} -> {{ stats.columns_after }}
- active pips: {{ stats.active_pips_before }} -> {{ stats.active_pips_after }}
- applied generated pips: {{ stats.applied_pips }}

Generated PIPs
- BEL input access: {{ stats.generated_bel_input_pips }}
- output-row coverage: {{ stats.generated_output_coverage_pips }}
- routing-resource pattern: {{ stats.generated_routing_pips }}
- hierarchy stages: {{ stats.generated_hierarchy_pips }}
- added JUMP wires: {{ stats.added_jump_wires }}
- compatible routing groups: {{ stats.compatible_routing_groups }}

Config Bits
- matrix config bits before: {{ stats.matrix_config_bits_before }}
- matrix config bits after: {{ stats.matrix_config_bits_after }}
- total tile config bits after: {{ stats.total_config_bits_after }}

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


def render_switch_matrix_pattern_report(result: SwitchMatrixPatternResult) -> str:
    """Render the switch-matrix pattern report.

    Parameters
    ----------
    result : SwitchMatrixPatternResult
        Structured pattern result.

    Returns
    -------
    str
        Human-readable report text.
    """
    return _REPORT_TEMPLATE.render(result=result, stats=result.stats).rstrip()

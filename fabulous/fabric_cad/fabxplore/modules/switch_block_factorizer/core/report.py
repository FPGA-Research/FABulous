"""Human-readable reporting for switch-block factorization."""

from jinja2 import Template

from fabulous.fabric_cad.fabxplore.modules.switch_block_factorizer.core.models import (
    SwitchBlockFactorizerResult,
)

_REPORT_TEMPLATE = Template(
    """Switch Block Factorizer Report
Tile: {{ result.tile_name }}

Configuration
- global_reduction: {{ result.options.global_reduction }}
- reduction_rules:
{{ reduction_rules }}
- min_mux_fanin_to_factorize: {{ result.options.min_mux_fanin_to_factorize }}
- jump_prefix: {{ result.options.jump_prefix }}
- max_added_jump_wires: {{ result.options.max_added_jump_wires }}
- config_bit_margin: {{ result.options.config_bit_margin }}
- config_bit_limit: {{ result.options.config_bit_limit }}

Muxes
- rows: {{ stats.mux_rows_before }} -> {{ stats.mux_rows_after }}
- pips: {{ stats.pips_before }} -> {{ stats.pips_after }}
- max fanin: {{ stats.max_fanin_before }} -> {{ stats.max_fanin_after }}
- factorized rows: {{ stats.factorized_rows }}
- added JUMP wires: {{ stats.added_jump_wires }}
- generated hierarchy PIPs: {{ stats.generated_hierarchy_pips }}

Config Bits
- fixed config bits: {{ stats.fixed_config_bits }}
- matrix config bits before: {{ stats.matrix_config_bits_before }}
- matrix config bits after: {{ stats.matrix_config_bits_after }}
- total tile config bits before: {{ stats.total_config_bits_before }}
- total tile config bits after: {{ stats.total_config_bits_after }}
- effective config-bit limit: {{ stats.effective_config_bit_limit }}
- blocked reductions: {{ stats.blocked_reductions }}

Fanin Histogram Before
{{ histogram_before }}

Fanin Histogram After
{{ histogram_after }}

Verification
- source-to-sink reachability preserved: {{ stats.reachability_preserved }}
{% if result.warnings %}

Warnings
{% for warning in result.warnings -%}
- {{ warning }}
{% endfor -%}
{% endif %}
"""
)


def render_switch_block_factorizer_report(
    result: SwitchBlockFactorizerResult,
) -> str:
    """Render the switch-block factorizer report.

    Parameters
    ----------
    result : SwitchBlockFactorizerResult
        Structured factorizer result.

    Returns
    -------
    str
        Human-readable report text.
    """
    return _REPORT_TEMPLATE.render(
        result=result,
        stats=result.stats,
        reduction_rules=_format_reduction_rules(result),
        histogram_before=_format_histogram(result.stats.fanin_histogram_before),
        histogram_after=_format_histogram(result.stats.fanin_histogram_after),
    ).strip()


def _format_reduction_rules(result: SwitchBlockFactorizerResult) -> str:
    """Format reduction rules without Python braces.

    Parameters
    ----------
    result : SwitchBlockFactorizerResult
        Structured factorizer result.

    Returns
    -------
    str
        Report text.
    """
    if not result.options.reduction_rules:
        return "- none"
    return "\n".join(
        f"- mux{rule.from_fanin} -> mux{rule.to_fanin}"
        for rule in result.options.reduction_rules
    )


def _format_histogram(histogram: dict[int, int]) -> str:
    """Format a mux-fanin histogram.

    Parameters
    ----------
    histogram : dict[int, int]
        Mapping from fanin to row count.

    Returns
    -------
    str
        Report text.
    """
    if not histogram:
        return "- none"
    return "\n".join(
        f"- mux{fanin}: {count}" for fanin, count in sorted(histogram.items())
    )

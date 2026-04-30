"""Render reports for techmap-based chain mapping."""

from jinja2 import Environment

from fabulous.fabric_cad.fabxplore.modules.chain_mapper.core.models import (
    ChainMapperResult,
)

_REPORT_ENV = Environment(
    autoescape=False,
    keep_trailing_newline=True,
    lstrip_blocks=True,
    trim_blocks=True,
)

REPORT_TEMPLATE = """\
Chain Mapper Report
Top Module: {{ result.top_name }}
Chain Primitive: {{ result.chain_name }}

Configuration
- ops: {{ ops }}
- chunk_size: {{ cfg.chunk_size }}
- min_chain_prims: {{ cfg.min_chain_prims }}
- max_chain_prims: {{ max_chain_prims }}
- and_to_or: {{ cfg.and_to_or }}
- or_to_and: {{ cfg.or_to_and }}
- leave_short: {{ cfg.leave_short }}
- normalize_extract_reduce: {{ cfg.normalize_extract_reduce }}
- normalize_alumacc: {{ cfg.normalize_alumacc }}
- alu_init_mode: {{ cfg.alu_init_mode.value }}
- read_chain_blackbox: {{ cfg.read_chain_blackbox }}
- run_clean: {{ cfg.run_clean }}

Generated Techmap Modules
{% for module in result.stats.generated_modules %}
- {{ module }}
{% endfor %}

Cell Counts Before
{% for cell_type, count in before_rows %}
- {{ cell_type }}: {{ count }}
{% endfor %}

Cell Counts After
{% for cell_type, count in after_rows %}
- {{ cell_type }}: {{ count }}
{% endfor %}

Commands
{% for command in result.stats.commands %}
- {{ command }}
{% endfor %}
{% if result.techmap_paths %}

Generated Techmap Files
{% for path in result.techmap_paths %}
- {{ path }}
{% endfor %}
{% elif result.techmap_path %}

Generated techmap file: {{ result.techmap_path }}
{% endif %}
"""

_REPORT_TEMPLATE = _REPORT_ENV.from_string(REPORT_TEMPLATE)


def render_chain_mapper_report(result: ChainMapperResult) -> str:
    """Render a chain mapper result as a human-readable report.

    Parameters
    ----------
    result : ChainMapperResult
        Result object produced by the chain mapper.

    Returns
    -------
    str
        Formatted report with configuration, generated modules, cell counts,
        and pyosys commands.
    """
    return _REPORT_TEMPLATE.render(
        result=result,
        cfg=result.config,
        max_chain_prims=result.config.max_chain_prims
        if result.config.max_chain_prims is not None
        else "none",
        ops=", ".join(op.value for op in result.config.ops),
        before_rows=_sorted_counts(result.stats.before_counts),
        after_rows=_sorted_counts(result.stats.after_counts),
    )


def _sorted_counts(counts: dict[str, int]) -> tuple[tuple[str, int], ...]:
    """Return cell counts ordered by descending frequency.

    Parameters
    ----------
    counts : dict[str, int]
        Cell-type histogram.

    Returns
    -------
    tuple[tuple[str, int], ...]
        Sorted ``(cell_type, count)`` rows.
    """
    return tuple(sorted(counts.items(), key=lambda item: (-item[1], item[0])))

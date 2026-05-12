"""Render compact reports for LUT decomposition."""

from collections import Counter

from jinja2 import Environment

from fabulous.fabric_cad.fabxplore.modules.lut_decomposer.core.models import (
    LutDecomposerResult,
)

_REPORT_ENV = Environment(
    autoescape=False,
    keep_trailing_newline=True,
    lstrip_blocks=True,
    trim_blocks=True,
)

REPORT_TEMPLATE = """\
LUT Decomposer Report
Top Module: {{ result.top_name }}

Configuration
- Source LUT widths: {{ widths }}
- Leaf LUT width: LUT{{ result.leaf_lut_width }}

Summary
- Total LUTs: {{ stats.total_luts }}
- Candidate LUTs: {{ stats.candidate_luts }}
- Decomposed LUTs: {{ stats.decomposed_luts }}
- Failed LUTs: {{ stats.failed_luts }}
- Skipped by width: {{ stats.skipped_width_luts }}
- Generated leaf LUTs: {{ stats.generated_leaf_luts }}

Mux Solver
- SAT solves: {{ stats.mux_solves }}
- Cache hits: {{ stats.mux_cache_hits }}

Decompositions by Shape
{% if shape_rows %}
{% for row in shape_rows %}
- {{ row.label }}: {{ row.count }}
{% endfor %}
{% else %}
- none
{% endif %}
"""

_REPORT_TEMPLATE = _REPORT_ENV.from_string(REPORT_TEMPLATE)


def render_lut_decomposer_report(result: LutDecomposerResult) -> str:
    """Render a human-readable decomposition summary.

    Parameters
    ----------
    result : LutDecomposerResult
        Decomposition result to render.

    Returns
    -------
    str
        Report text.
    """
    return _REPORT_TEMPLATE.render(
        result=result,
        stats=result.stats,
        widths=_format_widths(result.source_lut_widths),
        shape_rows=_shape_rows(result),
    ).rstrip()


def _shape_rows(result: LutDecomposerResult) -> tuple[dict[str, int], ...]:
    """Return decomposition shape rows for the report template.

    Parameters
    ----------
    result : LutDecomposerResult
        Decomposition result to summarize.

    Returns
    -------
    tuple[dict[str, int], ...]
        Ordered shape rows containing source width, cofactor count, and count.
    """
    counts = Counter(
        (decomposition.source_width, len(decomposition.cofactors))
        for decomposition in result.decompositions
    )
    return tuple(
        {
            "label": _shape_label(source_width, cofactors, result.leaf_lut_width),
            "count": count,
        }
        for (source_width, cofactors), count in sorted(counts.items())
    )


def _shape_label(source_width: int, cofactors: int, leaf_width: int) -> str:
    """Return a compact decomposition shape label.

    Parameters
    ----------
    source_width : int
        Source LUT width.
    cofactors : int
        Number of generated cofactors.
    leaf_width : int
        Leaf LUT width.

    Returns
    -------
    str
        Human-readable shape label.
    """
    return f"LUT{source_width} -> {cofactors} x LUT{leaf_width} + mux"


def _format_widths(widths: tuple[int, ...]) -> str:
    """Format selected source widths.

    Parameters
    ----------
    widths : tuple[int, ...]
        Source LUT widths.

    Returns
    -------
    str
        Comma-separated width labels.
    """
    return ", ".join(f"LUT{width}" for width in widths) or "none"

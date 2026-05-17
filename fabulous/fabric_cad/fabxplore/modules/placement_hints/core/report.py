"""Render placement-hints reports."""

from jinja2 import Template

from fabulous.fabric_cad.fabxplore.modules.placement_hints.core.models import (
    PlacementHintsResult,
)


class PlacementHintsReportTemplate:
    """Container for the placement-hints report template."""

    text = """Placement Hints Report
======================

Top module: {{ result.top_name }}

Options
-------
- attribute_prefix: {{ result.options.attribute_prefix }}
- overwrite_existing: {{ result.options.overwrite_existing }}
- fail_on_conflict: {{ result.options.fail_on_conflict }}

Rules
-----
{% for rule in result.options.rules %}
- {{ rule.kind }}: {{ rule.name }} ({{ rule.source_port }} -> {{ rule.sink_port }})
{% endfor %}

Statistics
----------
- Total cells: {{ result.stats.total_cells }}
- Rules: {{ result.stats.rules }}
- Candidate cell visits: {{ result.stats.candidate_cells }}
- Clusters: {{ result.stats.clusters }}
- Assigned cells: {{ result.stats.assigned_cells }}
- Skipped chains: {{ result.stats.skipped_chains }}
- Conflicts: {{ result.stats.conflicts }}

Clusters
--------
{% if result.clusters %}
{% for cluster in result.clusters %}
- {{ cluster.cluster_id }}: {{ cluster.rule_name }} size={{ cluster.cells|length }}
{% endfor %}
{% else %}
- none
{% endif %}
"""


def render_placement_hints_report(result: PlacementHintsResult) -> str:
    """Render a human-readable placement-hints report.

    Parameters
    ----------
    result : PlacementHintsResult
        Result to render.

    Returns
    -------
    str
        Rendered report text.
    """
    return Template(PlacementHintsReportTemplate.text).render(result=result)

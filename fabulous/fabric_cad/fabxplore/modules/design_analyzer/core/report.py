"""Render human-readable reports for design analyzer results."""

from fabulous.fabric_cad.fabxplore.modules.design_analyzer.core.models import (
    DesignAnalysisResult,
)
from fabulous.fabric_cad.fabxplore.modules.design_analyzer.core.taxonomy import (
    DEFAULT_TAXONOMY,
    AnalyzerTaxonomy,
)


def render_design_analysis_report(
    result: DesignAnalysisResult,
    max_type_rows: int = 24,
    taxonomy: AnalyzerTaxonomy | None = None,
) -> str:
    """Render a comprehensive user-facing report from analysis result data.

    Parameters
    ----------
    result : DesignAnalysisResult
        Full analysis result bundle.
    max_type_rows : int
        Maximum number of cell-type rows shown in the histogram section.
    taxonomy : AnalyzerTaxonomy | None
        Optional taxonomy object for family ordering and chain section layout.
        If ``None``, the default taxonomy is used.

    Returns
    -------
    str
        Fully rendered multi-section report.
    """
    used_taxonomy: AnalyzerTaxonomy = taxonomy or DEFAULT_TAXONOMY
    stats = result.stats
    char = result.characterization

    total = max(stats.total_cells, 1)

    lines: list[str] = []
    lines.append("Design Analyzer Report")
    lines.append(f"Top Module: {result.top_name}")
    lines.append("")

    lines.append("Executive Summary")
    lines.append(f"- Total cells: {stats.total_cells}")
    lines.append(f"- Total top-level ports: {stats.total_ports}")
    lines.append(f"- Total unique signal bits: {stats.total_nets}")
    lines.append(
        "- Netlist style mix: "
        f"coarse={stats.coarse_internal_cells}, "
        f"fine={stats.fine_gate_cells}, custom={stats.custom_cells}"
    )
    lines.append(
        "- Main characterization tags: "
        + (", ".join(tag.value for tag in char.tags) if char.tags else "none")
    )
    lines.append("")

    lines.append("Composition")
    lines.append(
        f"- Combinational cells: {stats.combinational_cells} "
        f"({100.0 * stats.combinational_cells / total:.1f}%)"
    )
    lines.append(
        f"- Sequential cells: {stats.sequential_cells} "
        f"({100.0 * stats.sequential_cells / total:.1f}%)"
    )
    lines.append(
        f"- Memory cells: {stats.memory_cells} "
        f"({100.0 * stats.memory_cells / total:.1f}%)"
    )
    lines.append(
        f"- Unclassified cells: {stats.unknown_cells} "
        f"({100.0 * stats.unknown_cells / total:.1f}%)"
    )
    lines.append("")

    lines.append("Control Signals")
    lines.append(f"- Clock-like port refs: {stats.clock_port_refs}")
    lines.append(f"- Reset-like port refs: {stats.reset_port_refs}")
    lines.append(f"- Set-like port refs: {stats.set_port_refs}")
    lines.append(f"- Enable-like port refs: {stats.enable_port_refs}")
    lines.append("")

    lines.append("Primitive Family Breakdown")
    for family in used_taxonomy.report_family_order:
        value = stats.family_counts.get(family, 0)
        lines.append(f"- {family.value}: {value} ({100.0 * value / total:.1f}%)")
    lines.append("")

    lines.append("Connectivity")
    lines.append(
        f"- Fanin (avg/max): {stats.avg_fanin:.2f} / "
        f"{stats.max_fanin} predecessor cells"
    )
    lines.append(
        f"- Fanout (avg/max): {stats.avg_fanout:.2f} / "
        f"{stats.max_fanout} successor cells"
    )

    if stats.chain_metrics:
        lines.append("- Chain-oriented metrics:")
        for family in used_taxonomy.chain_families:
            metric = stats.chain_metrics.get(family)
            if metric is None:
                continue
            lines.append(
                "  "
                f"{family.value}: candidates={metric.candidate_cells}, "
                f"largest_component={metric.largest_component}, "
                f"longest_path={metric.longest_path}"
            )
    lines.append("")

    lines.append("Most Frequent Cell Types")
    if not stats.cell_type_counts:
        lines.append("- none")
    else:
        sorted_types = sorted(
            stats.cell_type_counts.items(),
            key=lambda item: (-item[1], item[0]),
        )
        for idx, (cell_type, count) in enumerate(sorted_types):
            if idx >= max_type_rows:
                break
            lines.append(f"- {cell_type}: {count} ({100.0 * count / total:.1f}%)")
    lines.append("")

    lines.append("Observations")
    if char.observations:
        for obs in char.observations:
            lines.append(f"- {obs}")
    else:
        lines.append("- No additional observations.")
    lines.append("")

    lines.append("Warnings")
    if char.warnings:
        for warning in char.warnings:
            lines.append(f"- {warning}")
    else:
        lines.append("- No warnings.")
    lines.append("")

    lines.append("Recommendations")
    if char.recommendations:
        for recommendation in char.recommendations:
            lines.append(f"- {recommendation}")
    else:
        lines.append("- No specific recommendations.")

    return "\n".join(lines) + "\n"

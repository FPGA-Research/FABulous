"""Report rendering for routing-demand evaluation."""

from __future__ import annotations

from typing import TYPE_CHECKING

from jinja2 import Environment

from fabulous.fabric_cad.fabxplore.modules.routing_demand_evaluator.core.models import (  # noqa: E501
    DemandCategory,
    DemandClassName,
    DemandKind,
)

if TYPE_CHECKING:
    from fabulous.fabric_cad.fabxplore.modules.routing_demand_evaluator.core.models import (  # noqa: E501
        DemandClassStats,
        DemandRouteResult,
        RoutingDemandEvaluatorResult,
    )

_DEMAND_CATEGORIES = {
    DemandClassName.BEL_INPUT_REACHABILITY: DemandCategory.ESSENTIAL,
    DemandClassName.BEL_OUTPUT_ESCAPE: DemandCategory.ESSENTIAL,
    DemandClassName.MATRIX_ROW_COVERAGE: DemandCategory.ESSENTIAL,
    DemandClassName.HIERARCHY_INTEGRITY: DemandCategory.ESSENTIAL,
    DemandClassName.BEL_INPUT_SOURCE_COVERAGE: DemandCategory.STRESS,
    DemandClassName.MATRIX_SOURCE_USEFULNESS: DemandCategory.STRESS,
    DemandClassName.LOCAL_FEEDBACK: DemandCategory.STRESS,
    DemandClassName.NEIGHBOR_FEEDBACK: DemandCategory.STRESS,
    DemandClassName.STRAIGHT_ROUTING: DemandCategory.STRESS,
    DemandClassName.TURN_ROUTING: DemandCategory.STRESS,
    DemandClassName.SHORT_TO_LONG: DemandCategory.STRESS,
    DemandClassName.LONG_TO_SHORT: DemandCategory.STRESS,
    DemandClassName.MULTI_HOP: DemandCategory.STRESS,
    DemandClassName.ROUTING_REDUNDANCY: DemandCategory.STRESS,
    DemandClassName.BEL_INPUT_FANOUT: DemandCategory.STRESS,
    DemandClassName.CONTROL_REACHABILITY: DemandCategory.SPECIAL,
    DemandClassName.CONTROL_NET: DemandCategory.SPECIAL,
    DemandClassName.CARRY_CHAIN: DemandCategory.SPECIAL,
    DemandClassName.DSP_RAM_ACCESS: DemandCategory.SPECIAL,
    DemandClassName.IO_ACCESS: DemandCategory.SPECIAL,
    DemandClassName.RANDOM_LOCAL: DemandCategory.RANDOM,
    DemandClassName.RANDOM_MEDIUM: DemandCategory.RANDOM,
    DemandClassName.RANDOM_LONG: DemandCategory.RANDOM,
}

_REPORT_ENV = Environment(
    autoescape=False,
    keep_trailing_newline=True,
    lstrip_blocks=True,
    trim_blocks=True,
)

REPORT_TEMPLATE = """\
# Routing Demand Evaluator Report

Tile: {{ result.matrix.tile_name }}
Directory: {{ result.matrix.tile_dir }}
Switch matrix: {{ result.matrix.switch_matrix }}

## Summary
- status: {{ status }}
- opt: {{ result.options.opt }}
- optimizer: {{ result.options.optimizer }}
- demand_profile: {{ result.demand_profile.profile_name }}
- router: {{ result.options.router }}
- demands: {{ result.stats.total_demands }}
- hard demands passed: {{ hard_pass_summary }}
- hard demands failed: {{ result.stats.hard_failed }} / {{ result.stats.hard_demands }}
- hard failure rate: {{ hard_failure_rate }}
- soft demands passed: {{ soft_pass_summary }}
- soft demands failed: {{ result.stats.soft_failed }} / {{ result.stats.soft_demands }}
- failed sinks: {{ result.stats.failed_sinks }}
- soft failure rate: {{ soft_failure_rate }}
- original PIPs: {{ result.stats.original_pips }}
- final PIPs: {{ result.stats.final_pips }}
- matrix config bits: {{ result.stats.matrix_config_bits }}
- total config bits: {{ total_config_bits }}
- average routed sink path length: {{ average_path_length }}

## Router
- router_max_iterations: {{ result.options.router_max_iterations }}
- router_present_cost_multiplier: {{ result.options.router_present_cost_multiplier }}
- router_history_cost_increment: {{ result.options.router_history_cost_increment }}
- router_base_resource_capacity: {{ result.options.router_base_resource_capacity }}
- iterations used: {{ result.router_stats.iterations_used }}
- congested resources: {{ result.router_stats.congested_resources }}
- max resource usage: {{ result.router_stats.max_resource_usage }}
- failed sinks: {{ result.router_stats.failed_sinks }}

{{ report_sections }}"""

_REPORT_TEMPLATE = _REPORT_ENV.from_string(REPORT_TEMPLATE)


def render_routing_demand_report(
    result: RoutingDemandEvaluatorResult,
) -> str:
    """Render a routing-demand evaluator report.

    Parameters
    ----------
    result : RoutingDemandEvaluatorResult
        Structured evaluator result.

    Returns
    -------
    str
        Markdown report.
    """
    return (
        _REPORT_TEMPLATE.render(
            result=result,
            status=_status(result),
            hard_pass_summary=(
                f"{result.stats.hard_passed_count} / {result.stats.hard_demands} "
                f"({_percent(result.stats.hard_pass_rate)})"
            ),
            hard_failure_rate=_percent(result.stats.hard_failure_rate),
            soft_pass_summary=(
                f"{result.stats.soft_passed_count} / {result.stats.soft_demands} "
                f"({_percent(result.stats.soft_pass_rate)})"
            ),
            soft_failure_rate=_percent(result.stats.soft_failure_rate),
            total_config_bits=(
                f"{result.stats.total_config_bits} / {result.stats.config_capacity}"
            ),
            average_path_length=f"{result.stats.average_path_length:.2f}",
            report_sections=_report_sections(result),
        ).rstrip()
        + "\n"
    )


def _report_sections(result: RoutingDemandEvaluatorResult) -> str:
    """Render all post-router report sections.

    Parameters
    ----------
    result : RoutingDemandEvaluatorResult
        Evaluation result.

    Returns
    -------
    str
        Rendered section text.
    """
    return "".join(
        [
            _section_text(_congestion_section(result)),
            _section_text(
                _demand_section("Essential Checks", result, DemandCategory.ESSENTIAL)
            ),
            _section_text(
                _demand_section("Stress Checks", result, DemandCategory.STRESS)
            ),
            _section_text(
                _demand_section("Special Checks", result, DemandCategory.SPECIAL)
            ),
            _section_text(
                _demand_section("Random Checks", result, DemandCategory.RANDOM)
            ),
            _section_text(_random_bucket_section(result)),
            _section_text(_failed_examples_section(result)),
            _section_text(
                _usage_section(
                    "Most Used Resources",
                    _top_items(result.resource_usage),
                )
            ),
            _section_text(
                _usage_section("Most Used PIPs", _top_items(result.pip_usage))
            ),
            _section_text(_warnings_section(result)),
        ]
    )


def _section_text(lines: list[str]) -> str:
    """Render section lines for insertion into the Jinja2 report template.

    Parameters
    ----------
    lines : list[str]
        Preformatted section lines.

    Returns
    -------
    str
        Section text with one trailing blank line, or an empty string.
    """
    if not lines:
        return ""
    return "\n".join(lines).rstrip() + "\n\n"


def _warnings_section(result: RoutingDemandEvaluatorResult) -> list[str]:
    """Render warning lines.

    Parameters
    ----------
    result : RoutingDemandEvaluatorResult
        Evaluation result.

    Returns
    -------
    list[str]
        Warning section lines.
    """
    if not result.warnings:
        return []
    lines = ["## Warnings"]
    lines.extend(
        f"- {_explain_warning(warning, result)}" for warning in result.warnings
    )
    lines.append("")
    return lines


def _status(result: RoutingDemandEvaluatorResult) -> str:
    """Return the top-level status string.

    Parameters
    ----------
    result : RoutingDemandEvaluatorResult
        Evaluation result.

    Returns
    -------
    str
        Status label.
    """
    if not result.hard_demands_passed:
        return "FAIL"
    if result.soft_failure_rate > result.options.report_max_soft_failure_rate:
        return "PASS WITH WARNINGS"
    return "PASS"


def _demand_section(
    title: str,
    result: RoutingDemandEvaluatorResult,
    category: DemandCategory,
) -> list[str]:
    """Render one demand-result section.

    Parameters
    ----------
    title : str
        Section title.
    result : RoutingDemandEvaluatorResult
        Evaluation result.
    category : DemandCategory
        Demand category to include.

    Returns
    -------
    list[str]
        Rendered lines.
    """
    stats = [
        item
        for item in result.class_stats
        if _category_for_class(item.demand_class) == category
    ]
    lines = [f"## {title}"]
    if not stats:
        lines.extend(["- none", ""])
        return lines
    lines.extend(_stats_table(stats))
    lines.append("")
    return lines


def _stats_table(stats: list[DemandClassStats]) -> list[str]:
    """Render demand-class statistics as a padded Markdown table.

    Parameters
    ----------
    stats : list[DemandClassStats]
        Demand-class statistics.

    Returns
    -------
    list[str]
        Markdown table lines.
    """
    rows = [
        [
            item.demand_class,
            str(item.kind),
            str(item.passed),
            str(item.failed),
            _percent(item.pass_rate, digits=1),
            f"{item.average_path_length:.2f}",
        ]
        for item in stats
    ]
    return _markdown_table(
        headers=[
            "Demand class",
            "Type",
            "Passed",
            "Failed",
            "Pass rate",
            "Avg routed sink path",
        ],
        rows=rows,
        aligns=["left", "left", "right", "right", "right", "right"],
    )


def _random_bucket_section(result: RoutingDemandEvaluatorResult) -> list[str]:
    """Render random-bucket candidate statistics.

    Parameters
    ----------
    result : RoutingDemandEvaluatorResult
        Evaluation result.

    Returns
    -------
    list[str]
        Rendered lines.
    """
    if not result.random_bucket_stats:
        return []
    rows = [
        [
            item.demand_class,
            str(item.candidate_pairs),
            str(item.reachable_pairs),
            str(item.generated_demands),
        ]
        for item in result.random_bucket_stats
    ]
    return [
        "## Random Bucket Coverage",
        *_markdown_table(
            headers=[
                "Demand class",
                "Candidate pairs",
                "Reachable pairs",
                "Generated",
            ],
            rows=rows,
            aligns=["left", "right", "right", "right"],
        ),
        "",
    ]


def _failed_examples_section(result: RoutingDemandEvaluatorResult) -> list[str]:
    """Render failed demand examples.

    Parameters
    ----------
    result : RoutingDemandEvaluatorResult
        Evaluation result.

    Returns
    -------
    list[str]
        Rendered lines.
    """
    failed_examples = _representative_failed_examples(result)
    lines = ["## Failed Demand Examples"]
    if not failed_examples:
        lines.extend(["- none", ""])
        return lines
    for item in failed_examples:
        lines.append(
            f"- {item.demand.demand_id} ({item.demand.demand_class}): "
            f"{item.demand.source} -> {', '.join(item.demand.sinks)}; "
            f"reason={item.failure_reason}"
        )
    lines.append("")
    return lines


def _congestion_section(result: RoutingDemandEvaluatorResult) -> list[str]:
    """Render routed-resource congestion details.

    Parameters
    ----------
    result : RoutingDemandEvaluatorResult
        Evaluation result.

    Returns
    -------
    list[str]
        Rendered lines.
    """
    capacity = result.options.router_base_resource_capacity
    usage = _intermediate_resource_usage(result)
    congested = _congested_resources(usage, capacity)
    affected = _congestion_affected_results(result, congested)
    hard_affected = [item for item in affected if item.demand.kind == DemandKind.HARD]
    soft_affected = [item for item in affected if item.demand.kind == DemandKind.SOFT]
    lines = [
        "## Congestion",
        f"- resource capacity: {capacity}",
        f"- congested resources: {len(congested)}",
        f"- max intermediate resource usage: {max(usage.values(), default=0)}",
        f"- routed demands through congested resources: {len(affected)}",
        f"- hard demands through congested resources: {len(hard_affected)}",
        f"- soft demands through congested resources: {len(soft_affected)}",
        "",
    ]
    if not congested:
        lines.extend(["### Most Congested Resources", "- none", ""])
        return lines

    resource_rows = [
        [name, str(count), str(count - capacity)] for name, count in congested[:10]
    ]
    lines.extend(
        [
            "### Most Congested Resources",
            *_markdown_table(
                headers=["Resource", "Usage", "Overuse"],
                rows=resource_rows,
                aligns=["left", "right", "right"],
            ),
            "",
        ]
    )
    class_rows = _congestion_class_rows(result, congested, capacity)
    if class_rows:
        lines.extend(
            [
                "### Congestion By Demand Class",
                *_markdown_table(
                    headers=[
                        "Demand class",
                        "Routed",
                        "Congested",
                        "Congested rate",
                        "Max overuse",
                    ],
                    rows=class_rows,
                    aligns=["left", "right", "right", "right", "right"],
                ),
                "",
            ]
        )
    return lines


def _intermediate_resource_usage(
    result: RoutingDemandEvaluatorResult,
) -> dict[str, int]:
    """Count intermediate resource usage from routed paths.

    Parameters
    ----------
    result : RoutingDemandEvaluatorResult
        Evaluation result.

    Returns
    -------
    dict[str, int]
        Usage count by intermediate node.
    """
    usage: dict[str, int] = {}
    for demand_result in result.demand_results:
        for path in demand_result.paths:
            for node in path.nodes[1:-1]:
                usage[node] = usage.get(node, 0) + 1
    return usage


def _congested_resources(
    usage: dict[str, int],
    capacity: int,
) -> list[tuple[str, int]]:
    """Return resources over capacity.

    Parameters
    ----------
    usage : dict[str, int]
        Usage count by resource.
    capacity : int
        Resource capacity.

    Returns
    -------
    list[tuple[str, int]]
        Congested resource names and usage counts.
    """
    return sorted(
        [(name, count) for name, count in usage.items() if count > capacity],
        key=lambda item: (-(item[1] - capacity), -item[1], item[0]),
    )


def _congestion_affected_results(
    result: RoutingDemandEvaluatorResult,
    congested: list[tuple[str, int]],
) -> list[DemandRouteResult]:
    """Return routed demands that use at least one congested resource.

    Parameters
    ----------
    result : RoutingDemandEvaluatorResult
        Evaluation result.
    congested : list[tuple[str, int]]
        Congested resources.

    Returns
    -------
    list[DemandRouteResult]
        Routed demand results passing through congested resources.
    """
    congested_names = {name for name, _count in congested}
    if not congested_names:
        return []
    affected: list[DemandRouteResult] = []
    for demand_result in result.demand_results:
        if not demand_result.routed:
            continue
        if any(
            node in congested_names
            for path in demand_result.paths
            for node in path.nodes[1:-1]
        ):
            affected.append(demand_result)
    return affected


def _congestion_class_rows(
    result: RoutingDemandEvaluatorResult,
    congested: list[tuple[str, int]],
    capacity: int,
) -> list[list[str]]:
    """Return demand-class congestion rows.

    Parameters
    ----------
    result : RoutingDemandEvaluatorResult
        Evaluation result.
    congested : list[tuple[str, int]]
        Congested resources.
    capacity : int
        Resource capacity.

    Returns
    -------
    list[list[str]]
        Markdown table rows.
    """
    overuse_by_resource = {name: count - capacity for name, count in congested}
    rows: list[list[str]] = []
    for stats in result.class_stats:
        routed_results = [
            item
            for item in result.demand_results
            if item.routed and item.demand.demand_class == stats.demand_class
        ]
        if not routed_results:
            continue
        congested_results = []
        max_overuse = 0
        for item in routed_results:
            overuse = max(
                (
                    overuse_by_resource.get(node, 0)
                    for path in item.paths
                    for node in path.nodes[1:-1]
                ),
                default=0,
            )
            if overuse > 0:
                congested_results.append(item)
                max_overuse = max(max_overuse, overuse)
        rows.append(
            [
                stats.demand_class,
                str(len(routed_results)),
                str(len(congested_results)),
                _percent(len(congested_results) / len(routed_results), digits=1),
                str(max_overuse),
            ]
        )
    return rows


def _representative_failed_examples(
    result: RoutingDemandEvaluatorResult,
    per_class: int = 2,
    total: int = 20,
) -> list[DemandRouteResult]:
    """Return failed examples spread across demand classes.

    Parameters
    ----------
    result : RoutingDemandEvaluatorResult
        Evaluation result.
    per_class : int
        Maximum failed examples per demand class.
    total : int
        Maximum failed examples overall.

    Returns
    -------
    list[DemandRouteResult]
        Representative failed demand results.
    """
    failed = [item for item in result.demand_results if not item.routed]
    selected: list[DemandRouteResult] = []
    seen_classes: set[str] = set()
    for item in failed:
        demand_class = str(item.demand.demand_class)
        if demand_class in seen_classes:
            continue
        selected.append(item)
        seen_classes.add(demand_class)
        if len(selected) >= total:
            return selected

    counts: dict[str, int] = {}
    for item in selected:
        demand_class = str(item.demand.demand_class)
        counts[demand_class] = counts.get(demand_class, 0) + 1
    for item in failed:
        demand_class = str(item.demand.demand_class)
        if counts.get(demand_class, 0) >= per_class:
            continue
        if item in selected:
            continue
        selected.append(item)
        counts[demand_class] = counts.get(demand_class, 0) + 1
        if len(selected) >= total:
            return selected
    return selected


def _usage_section(title: str, items: list[tuple[str, int]]) -> list[str]:
    """Render a top-usage section.

    Parameters
    ----------
    title : str
        Section title.
    items : list[tuple[str, int]]
        Usage items.

    Returns
    -------
    list[str]
        Rendered lines.
    """
    lines = [f"## {title}"]
    if not items:
        lines.append("- none")
    else:
        lines.extend(f"- {name}: {count}" for name, count in items)
    lines.append("")
    return lines


def _markdown_table(
    headers: list[str],
    rows: list[list[str]],
    aligns: list[str],
) -> list[str]:
    """Render a padded Markdown table.

    Parameters
    ----------
    headers : list[str]
        Header labels.
    rows : list[list[str]]
        Table rows.
    aligns : list[str]
        Alignment hints: ``left`` or ``right``.

    Returns
    -------
    list[str]
        Markdown table lines.
    """
    widths = [
        max(len(headers[index]), *(len(row[index]) for row in rows))
        for index in range(len(headers))
    ]
    lines = [
        "| " + " | ".join(_pad(headers, widths, aligns)) + " |",
        "| "
        + " | ".join(
            _separator(width, align)
            for width, align in zip(widths, aligns, strict=True)
        )
        + " |",  # noqa: E501
    ]
    for row in rows:
        lines.append("| " + " | ".join(_pad(row, widths, aligns)) + " |")
    return lines


def _pad(values: list[str], widths: list[int], aligns: list[str]) -> list[str]:
    """Pad table values.

    Parameters
    ----------
    values : list[str]
        Cell values.
    widths : list[int]
        Column widths.
    aligns : list[str]
        Alignment hints.

    Returns
    -------
    list[str]
        Padded values.
    """
    return [
        value.rjust(width) if align == "right" else value.ljust(width)
        for value, width, align in zip(values, widths, aligns, strict=True)
    ]


def _separator(width: int, align: str) -> str:
    """Return a Markdown alignment separator.

    Parameters
    ----------
    width : int
        Column width.
    align : str
        Alignment hint.

    Returns
    -------
    str
        Separator text.
    """
    if align == "right":
        fill = "-" * max(width - 1, 2)
        return f"{fill}:"
    return "-" * max(width, 3)


def _top_items(values: dict[str, int]) -> list[tuple[str, int]]:
    """Return top usage items.

    Parameters
    ----------
    values : dict[str, int]
        Usage dictionary.

    Returns
    -------
    list[tuple[str, int]]
        Top ten usage items.
    """
    return sorted(values.items(), key=lambda item: (-item[1], item[0]))[:10]


def _category_for_class(demand_class: str) -> DemandCategory:
    """Return the report category for one demand class.

    Parameters
    ----------
    demand_class : str
        Demand class name.

    Returns
    -------
    DemandCategory
        Report category.
    """
    try:
        return _DEMAND_CATEGORIES[DemandClassName(demand_class)]
    except ValueError:
        return DemandCategory.STRESS


def _explain_warning(warning: str, result: RoutingDemandEvaluatorResult) -> str:
    """Add context to known warning shapes.

    Parameters
    ----------
    warning : str
        Warning text.
    result : RoutingDemandEvaluatorResult
        Evaluation result.

    Returns
    -------
    str
        Warning with additional context when available.
    """
    prefix = "Demand class generated no demands: "
    if not warning.startswith(prefix):
        return warning
    demand_class = warning.removeprefix(prefix)
    random_stats = {item.demand_class: item for item in result.random_bucket_stats}.get(
        demand_class
    )
    if random_stats is None:
        return f"{warning} (not applicable or no classified terminals matched)"
    if random_stats.candidate_pairs == 0:
        return f"{warning} (no distance-matching candidate pairs)"
    if random_stats.reachable_pairs == 0:
        return f"{warning} (candidate pairs exist, but none are reachable)"
    return f"{warning} (reachable candidates exist; demand budget may be exhausted)"


def _percent(value: float, digits: int = 2) -> str:
    """Format a unit value as a percentage.

    Parameters
    ----------
    value : float
        Unit value.
    digits : int
        Decimal digits.

    Returns
    -------
    str
        Percentage string.
    """
    return f"{value * 100.0:.{digits}f}%"

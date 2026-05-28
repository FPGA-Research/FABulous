"""Render reports for FABulous nextpnr fabric routing.

The nextpnr JSON report already carries structured metrics such as utilization, Fmax,
and critical paths. This module turns that structured result plus the router paths and
subprocess status into a concise Markdown report for architecture-flow logging and
accumulated pass summaries.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from jinja2 import Environment

if TYPE_CHECKING:
    from fabulous.fabric_cad.fabxplore.pnr.pnr_modules.nextpnr.core.models import (
        NextpnrRouterResult,
    )

_REPORT_ENV = Environment(
    autoescape=False,
    keep_trailing_newline=True,
    lstrip_blocks=True,
    trim_blocks=True,
)

REPORT_TEMPLATE = """\
# Fabric Router Report

## Summary
- status: {{ status }}
- top: {{ result.top_name }}
- nextpnr: {{ result.nextpnr_exec }}
- return code: {{ result.command_result.returncode }}
- output directory: {{ result.paths.out_dir }}
- json: {{ result.paths.json_path }}
- pcf: {{ result.paths.pcf_path }}
- fasm: {{ result.paths.fasm_path }}
- report: {{ result.paths.report_path }}
- used cells: {{ used_cells }}

## Utilization
{{ utilization_table }}

## Timing
- fmax entries: {{ fmax_count }}
- critical paths: {{ critical_path_count }}
{{ nextpnr_output_section }}
{% if result.warnings %}

## Warnings
{% for warning in result.warnings %}
- {{ warning }}
{% endfor %}
{% endif %}
"""

_REPORT_TEMPLATE = _REPORT_ENV.from_string(REPORT_TEMPLATE)


def render_nextpnr_router_report(result: NextpnrRouterResult) -> str:
    """Render a human-readable nextpnr router report.

    Parameters
    ----------
    result : NextpnrRouterResult
        Structured router result.

    Returns
    -------
    str
        Markdown report.
    """
    utilization = result.nextpnr_report.get("utilization", {})
    rows = _utilization_rows(utilization)
    return (
        _REPORT_TEMPLATE.render(
            result=result,
            status="PASS" if result.passed else "FAIL",
            utilization_table=_format_utilization_table(rows),
            used_cells=sum(row["used"] for row in rows),
            fmax_count=len(result.nextpnr_report.get("fmax", {})),
            critical_path_count=len(result.nextpnr_report.get("critical_paths", [])),
            nextpnr_output_section=_nextpnr_output_section(result),
        ).rstrip()
        + "\n"
    )


def _utilization_rows(utilization: object) -> list[dict[str, Any]]:
    """Normalize nextpnr utilization data for report rendering.

    Parameters
    ----------
    utilization : object
        Raw ``utilization`` value from the nextpnr JSON report.

    Returns
    -------
    list[dict[str, Any]]
        Sorted row dictionaries with ``name``, ``used``, ``available``, and
        ``percent`` fields.
    """
    if not isinstance(utilization, dict):
        return []

    rows: list[dict[str, Any]] = []
    for name, values in sorted(utilization.items()):
        if not isinstance(values, dict):
            continue
        used = _as_int(values.get("used"))
        available = _as_int(values.get("available"))
        rows.append(
            {
                "name": name,
                "used": used,
                "available": available,
                "percent": _format_utilization(used, available),
            }
        )
    return rows


def _as_int(value: object) -> int:
    """Convert a report value to an integer when possible.

    Parameters
    ----------
    value : object
        Raw report value.

    Returns
    -------
    int
        Parsed integer, or zero when the value is absent or invalid.
    """
    try:
        return int(value) if value is not None else 0
    except (TypeError, ValueError):
        return 0


def _format_utilization(used: int, available: int) -> str:
    """Format utilization as a percentage or ``n/a``.

    Parameters
    ----------
    used : int
        Used resource count.
    available : int
        Available resource count.

    Returns
    -------
    str
        Formatted utilization percentage.
    """
    if available <= 0:
        return "n/a"
    return f"{(used / available) * 100:.2f}%"


def _format_utilization_table(rows: list[dict[str, Any]]) -> str:
    """Format utilization rows as an aligned Markdown table.

    Parameters
    ----------
    rows : list[dict[str, Any]]
        Normalized utilization rows.

    Returns
    -------
    str
        Aligned Markdown table, or ``"- none"`` when empty.
    """
    if not rows:
        return "- none"

    headers = ["Cell Type", "Used", "Available", "Utilization"]
    table_rows = [
        [
            str(row["name"]),
            str(row["used"]),
            str(row["available"]),
            str(row["percent"]),
        ]
        for row in rows
    ]
    widths = [
        max(len(headers[index]), *(len(row[index]) for row in table_rows))
        for index in range(len(headers))
    ]
    return "\n".join(
        [
            _format_table_row(headers, widths),
            _format_separator_row(widths),
            *(_format_table_row(row, widths) for row in table_rows),
        ]
    )


def _format_table_row(row: list[str], widths: list[int]) -> str:
    """Format one aligned Markdown table row.

    Parameters
    ----------
    row : list[str]
        Cell values.
    widths : list[int]
        Column widths.

    Returns
    -------
    str
        Formatted Markdown row.
    """
    return (
        f"| {row[0]:<{widths[0]}} | {row[1]:>{widths[1]}} | "
        f"{row[2]:>{widths[2]}} | {row[3]:>{widths[3]}} |"
    )


def _format_separator_row(widths: list[int]) -> str:
    """Format one aligned Markdown table separator row.

    Parameters
    ----------
    widths : list[int]
        Column widths.

    Returns
    -------
    str
        Markdown separator row with numeric columns right-aligned.
    """
    return (
        f"| {'-' * widths[0]} | {'-' * (widths[1] - 1)}: | "
        f"{'-' * (widths[2] - 1)}: | {'-' * (widths[3] - 1)}: |"
    )


def _nextpnr_output_section(result: NextpnrRouterResult) -> str:
    """Render captured nextpnr output for the report.

    Parameters
    ----------
    result : NextpnrRouterResult
        Router result containing captured process output.

    Returns
    -------
    str
        Report section text, or an empty string when disabled.
    """
    if not result.options.report_output:
        return ""

    stdout = _limit_lines(
        result.command_result.stdout,
        result.options.report_output_max_lines,
    )
    stderr = _limit_lines(
        result.command_result.stderr,
        result.options.report_output_max_lines,
    )
    if not stdout and not stderr:
        return "\n## nextpnr Output\n- none"
    return "\n".join(
        [
            "",
            "## nextpnr Output",
            "",
            _format_output_block("stdout", stdout),
            "",
            _format_output_block("stderr", stderr),
        ]
    )


def _format_output_block(name: str, text: str) -> str:
    """Format one captured nextpnr output stream.

    Parameters
    ----------
    name : str
        Stream label.
    text : str
        Stream text.

    Returns
    -------
    str
        Markdown subsection with fenced output.
    """
    if not text:
        return f"### {name}\n- none"
    return f"### {name}\n```text\n{text.rstrip()}\n```"


def _limit_lines(text: str, max_lines: int | None) -> str:
    """Limit text to its trailing lines.

    Parameters
    ----------
    text : str
        Text to limit.
    max_lines : int | None
        Maximum number of trailing lines. ``None`` keeps all lines.

    Returns
    -------
    str
        Original or truncated text.
    """
    if max_lines is None:
        return text
    if max_lines == 0:
        return ""
    lines = text.splitlines()
    if len(lines) <= max_lines:
        return text
    return "\n".join(lines[-max_lines:])

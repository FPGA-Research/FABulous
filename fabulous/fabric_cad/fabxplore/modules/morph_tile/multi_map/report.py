"""Render compact multi-map reports.

The report mirrors the morph-tile text style while using multi-map-specific statistics.
"""

from fabulous.fabric_cad.fabxplore.modules.morph_tile.multi_map.models import (
    MultiMapResult,
)


def render_multi_map_report(result: MultiMapResult) -> str:
    """Render a human-readable report.

    Parameters
    ----------
    result : MultiMapResult
        Completed multi-map result.

    Returns
    -------
    str
        Report text.
    """
    stats = result.stats
    selector = _selector_metadata(result)
    return "\n".join(
        [
            "Multi-map report",
            f"- top: {result.top_name}",
            f"- tile: {result.tile_top_name}",
            f"- sampled groups: {stats.total_groups}",
            f"- checked groups: {stats.checked_groups}",
            f"- SAT matches total: {stats.sat_matches_total}",
            f"- SAT matches stored: {stats.matched_groups}",
            f"- selector: {selector.get('selector', 'unknown')}",
            f"- selector status: {selector.get('status', 'unknown')}",
            f"- selector fallback used: {selector.get('fallback_used', 'unknown')}",
            f"- selector time: {_format_seconds(selector.get('wall_time_s'))}",
            f"- selected groups: {stats.selected_groups}",
            f"- replaced LUTs: {stats.replaced_luts}",
            f"- cache hits: {stats.cache_hits}",
            f"- cache misses: {stats.cache_misses}",
        ]
    )


def _selector_metadata(result: MultiMapResult) -> dict[str, object]:
    """Return selector metadata from a result.

    Parameters
    ----------
    result : MultiMapResult
        Completed multi-map result.

    Returns
    -------
    dict[str, object]
        Selector metadata dictionary, or an empty dictionary.
    """
    selector = result.metadata.get("selector")
    return selector if isinstance(selector, dict) else {}


def _format_seconds(value: object) -> str:
    """Format a selector runtime value.

    Parameters
    ----------
    value : object
        Optional numeric seconds.

    Returns
    -------
    str
        Human-readable seconds.
    """
    if not isinstance(value, int | float):
        return "n/a"
    return f"{float(value):.3f}s"

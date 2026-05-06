"""Render human-readable reports for LUT layering runs."""

from jinja2 import Environment

from fabulous.fabric_cad.fabxplore.modules.lut_layering.core.models import (
    LayeredLutPlacement,
    LeftoverSlot,
    LutLayeringConfig,
    LutLayeringStats,
)

_REPORT_ENV = Environment(
    autoescape=False,
    keep_trailing_newline=True,
    lstrip_blocks=True,
    trim_blocks=True,
)

REPORT_TEMPLATE = """\
LUT Layering
Configuration
- Overlay top: {{ config.overlay_top_name }}
- Overlay files: {{ overlay_files }}
- Base top: {{ config.top_name }}
- Overlay prefix: {{ config.overlay_prefix }}
- Base prefix: {{ config.base_prefix if config.base_prefix is not none else "none" }}
- Overlay LUT size: {{ overlay_lut_size }}

Inventory Before Layering
- Candidate leftover slots: {{ stats.slots_before }}
- Reusable effective leftover width: {{ stats.reusable_leftover_before }}
{% if slots %}
- Slots by effective width:
{% for label, count in slot_rows %}
  - {{ label }}: {{ count }} slots
{% endfor %}
{% else %}
- Note: no usable leftover slots were available.
{% endif %}

Overlay Consumption
- Overlay LUTs: {{ stats.overlay_luts }}
- Overlay LUT input width total: {{ stats.overlay_lut_inputs }}
{% if stats.overlay_width_count %}
- Overlay LUTs by width:
{% for label, count in overlay_rows %}
  - {{ label }}: {{ count }} cells
{% endfor %}
{% endif %}
- Injected overlay LUTs: {{ stats.injected_luts }}

Inventory After Layering
- Reusable effective leftover width: {{ stats.reusable_leftover_after }}
{% if stats.remaining_width_count %}
- Remaining slots by effective width:
{% for label, count in remaining_rows %}
  - {{ label }}: {{ count }} slots
{% endfor %}
{% endif %}

Placements
{% if placements %}
{% for placement in placements %}
- {{ placement.overlay_cell_id }} (LUT{{ placement.overlay_width }})
  -> {{ placement.host_packed_id }} with {{ placement.host_cell_id }};
  remaining effective width={{ placement.leftover_width_after }}
{% endfor %}
{% else %}
- No overlay LUTs were injected.
{% endif %}
"""

_REPORT_TEMPLATE = _REPORT_ENV.from_string(REPORT_TEMPLATE)


def render_layering_report(
    config: LutLayeringConfig,
    stats: LutLayeringStats,
    slots: tuple[LeftoverSlot, ...],
    placements: tuple[LayeredLutPlacement, ...],
    overlay_lut_size: int,
) -> str:
    """Render a report block for one layering run.

    Parameters
    ----------
    config : LutLayeringConfig
        Configuration used by the layering run.
    stats : LutLayeringStats
        Aggregate counters to display.
    slots : tuple[LeftoverSlot, ...]
        Candidate slots before layering.
    placements : tuple[LayeredLutPlacement, ...]
        Applied overlay placements.
    overlay_lut_size : int
        LUT size used when mapping the overlay design.

    Returns
    -------
    str
        Rendered report text.
    """
    return _REPORT_TEMPLATE.render(
        config=config,
        stats=stats,
        slots=slots,
        placements=placements,
        overlay_lut_size=overlay_lut_size,
        overlay_files=", ".join(str(path) for path in config.overlay_verilog_paths),
        slot_rows=tuple(sorted(_slot_width_count(slots).items())),
        overlay_rows=tuple(sorted(stats.overlay_width_count.items())),
        remaining_rows=tuple(sorted(stats.remaining_width_count.items())),
    ).rstrip()


def _slot_width_count(slots: tuple[LeftoverSlot, ...]) -> dict[str, int]:
    """Return candidate-slot counts grouped by effective width label.

    Parameters
    ----------
    slots : tuple[LeftoverSlot, ...]
        Slots to summarize.

    Returns
    -------
    dict[str, int]
        Counts keyed as ``"LUTN"``.
    """
    counts: dict[str, int] = {}
    for slot in slots:
        label = f"LUT{slot.effective_leftover_width}"
        counts[label] = counts.get(label, 0) + 1
    return counts

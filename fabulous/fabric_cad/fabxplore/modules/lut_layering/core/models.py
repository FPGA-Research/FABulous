"""Typed data models for LUT layering.

The layering stage consumes a packed LUT-combinator mapping result and a second user
design. It maps the second design to logical LUTs, injects those LUTs into unused halves
of existing fractional LUT cells, and returns an updated mapping plus a report-oriented
summary.
"""

from dataclasses import dataclass, field
from pathlib import Path

from fabulous.fabric_cad.fabxplore.modules.lut_combinator.core.architecture import (
    FracLutArchitecture,
)
from fabulous.fabric_cad.fabxplore.modules.lut_combinator.core.models import (
    LogicalLutCell,
    LutSpec,
    MappingResult,
)
from fabulous.fabric_cad.fabxplore.modules.lut_layering.core.json_merge import (
    PreparedOverlayJson,
)


@dataclass(frozen=True)
class LutLayeringConfig:
    """Configure one LUT layering run.

    Attributes
    ----------
    overlay_verilog_paths : list[Path]
        Verilog source files for the overlay design.
    overlay_top_name : str
        Top module name of the overlay design.
    base_mapping : MappingResult
        Latest LUT-combinator mapping of the base design.
    architecture : FracLutArchitecture
        Fractional LUT architecture used to rebuild changed packed cells.
    top_name : str
        Top module name of the already packed base design.
    overlay_prefix : str
        Prefix added to overlay ports, netnames, and cell names before merging.
    base_prefix : str | None
        Optional prefix added to base top-level ports and netnames. Use
        ``None`` to keep base names unchanged.
    lut_spec : LutSpec
        LUT parser conventions used for overlay LUT cells.
    overlay_lut_size : int | None
        Manual maximum LUT size for mapping the overlay design. If set, the
        inventory-aware retry loop is skipped and this exact size is used.
    overlay_mapper_max_tries : int
        Number of inventory-aware ABC9 cost-vector attempts before the forced
        fallback mapping is tried.
    overlay_mapper_cost_scale : int
        Integer cost baseline used when generating ABC9 LUT cost vectors.
    overlay_mapper_size_penalty : float
        Exponent-like multiplier that makes larger LUTs more expensive even
        when corresponding leftover slots exist.
    overlay_mapper_retry_penalty : float
        Extra larger-LUT penalty multiplier applied after each failed
        inventory-aware attempt.
    overlay_mapper_fallback_lut_size : int
        Final forced maximum LUT size if all inventory-aware attempts fail.
        Defaults to 2, because LUT2 cells can be hosted by every reusable slot
        with capacity at least two.
    debug : bool
        Enable verbose pyosys output for the temporary overlay synthesis bridge.
    """

    overlay_verilog_paths: list[Path]
    overlay_top_name: str
    base_mapping: MappingResult
    architecture: FracLutArchitecture
    top_name: str
    overlay_prefix: str = "design1_"
    base_prefix: str | None = "design0_"
    lut_spec: LutSpec = field(default_factory=LutSpec)
    overlay_lut_size: int | None = None
    overlay_mapper_max_tries: int = 4
    overlay_mapper_cost_scale: int = 100
    overlay_mapper_size_penalty: float = 1.4
    overlay_mapper_retry_penalty: float = 1.8
    overlay_mapper_fallback_lut_size: int = 2
    debug: bool = False


@dataclass(frozen=True)
class OverlayMappingAttempt:
    """Describe one overlay LUT mapping attempt.

    Attributes
    ----------
    index : int
        Zero-based attempt index in execution order.
    name : str
        Human-readable attempt label.
    lut_size : int
        Maximum LUT size requested from ABC9.
    cost_vector : tuple[int, ...] | None
        ABC9 cost vector used for this attempt. ``None`` means plain
        ``abc9 -lut N`` mapping.
    capacity_fits : bool
        Whether the overlay LUT width multiset can fit the leftover slot
        capacity multiset.
    placement_fits : bool
        Whether the full architecture-aware placement succeeded.
    overlay_width_count : dict[str, int]
        Overlay LUT histogram produced by this attempt.
    note : str
        Short outcome detail for reports and diagnostics.
    """

    index: int
    name: str
    lut_size: int
    cost_vector: tuple[int, ...] | None = None
    capacity_fits: bool = False
    placement_fits: bool = False
    overlay_width_count: dict[str, int] = field(default_factory=dict)
    note: str = ""


@dataclass(frozen=True)
class LeftoverSlot:
    """Describe one usable leftover slot inside a packed base cell.

    Attributes
    ----------
    cell_index : int
        Index of the host cell in ``MappingResult.mapped_cells``.
    packed_id : str
        Instance name of the host fractional LUT cell.
    host_cell_id : str
        Logical LUT currently placed in the host.
    host_width : int
        Input width of the host logical LUT.
    effective_leftover_width : int
        Maximum overlay LUT input width that can be added to this host.
    nominal_leftover_width : int
        Report-only leftover width before select-as-data effective adjustment.
    """

    cell_index: int
    packed_id: str
    host_cell_id: str
    host_width: int
    effective_leftover_width: int
    nominal_leftover_width: int


@dataclass(frozen=True)
class LayeredLutPlacement:
    """Describe one overlay LUT injected into a base leftover slot.

    Attributes
    ----------
    overlay_cell_id : str
        Prefixed overlay LUT instance name.
    overlay_width : int
        Input width of the overlay LUT.
    host_packed_id : str
        Base FRAC instance receiving the overlay LUT.
    host_cell_id : str
        Existing base logical LUT sharing the rebuilt FRAC cell.
    consumed_width : int
        Overlay LUT width consumed from the slot.
    leftover_width_after : int
        Remaining effective leftover width in the rebuilt host.
    """

    overlay_cell_id: str
    overlay_width: int
    host_packed_id: str
    host_cell_id: str
    consumed_width: int
    leftover_width_after: int


@dataclass(frozen=True)
class OverlayMappingSelection:
    """Bundle the accepted overlay mapping candidate.

    Attributes
    ----------
    prepared_overlay : PreparedOverlayJson
        Prefix-renamed and bit-remapped overlay JSON ready to merge.
    overlay_luts : tuple[LogicalLutCell, ...]
        Overlay LUT cells produced by the accepted mapping attempt.
    placements : tuple[LayeredLutPlacement, ...]
        Overlay-to-leftover placements for the accepted mapping.
    updated_mapping : MappingResult
        Base mapping after injecting overlay LUTs into selected FRAC cells.
    selected_attempt : OverlayMappingAttempt
        Attempt metadata for the accepted overlay mapping.
    attempts : tuple[OverlayMappingAttempt, ...]
        All attempts tried before and including the accepted mapping.
    """

    prepared_overlay: PreparedOverlayJson
    overlay_luts: tuple[LogicalLutCell, ...]
    placements: tuple[LayeredLutPlacement, ...]
    updated_mapping: MappingResult
    selected_attempt: OverlayMappingAttempt
    attempts: tuple[OverlayMappingAttempt, ...]


@dataclass(frozen=True)
class LutLayeringStats:
    """Aggregate counters for one LUT layering run.

    Attributes
    ----------
    slots_before : int
        Number of candidate leftover slots before layering.
    reusable_leftover_before : int
        Total effective leftover width before layering.
    overlay_luts : int
        Number of overlay LUTs produced by overlay synthesis.
    overlay_lut_inputs : int
        Sum of overlay LUT input widths.
    injected_luts : int
        Number of overlay LUTs successfully injected.
    reusable_leftover_after : int
        Total effective leftover width after layering.
    overlay_width_count : dict[str, int]
        Overlay LUT histogram by width label.
    remaining_width_count : dict[str, int]
        Remaining slot-capacity histogram after layering.
    """

    slots_before: int = 0
    reusable_leftover_before: int = 0
    overlay_luts: int = 0
    overlay_lut_inputs: int = 0
    injected_luts: int = 0
    reusable_leftover_after: int = 0
    overlay_width_count: dict[str, int] = field(default_factory=dict)
    remaining_width_count: dict[str, int] = field(default_factory=dict)


@dataclass(frozen=True)
class LutLayeringResult:
    """Bundle the updated mapping and layering report data.

    Attributes
    ----------
    mapping : MappingResult
        Updated base mapping after overlay LUTs were injected.
    stats : LutLayeringStats
        Aggregate counters for report generation.
    placements : tuple[LayeredLutPlacement, ...]
        Applied overlay-to-leftover placements.
    report_summary : str
        Human-readable report block.
    overlay_luts : tuple[LogicalLutCell, ...]
        Prefixed overlay LUTs considered by the layerer.
    selected_attempt : OverlayMappingAttempt
        Overlay mapping attempt accepted by the layerer.
    attempts : tuple[OverlayMappingAttempt, ...]
        All attempts tried before the selected mapping.
    """

    mapping: MappingResult
    stats: LutLayeringStats
    placements: tuple[LayeredLutPlacement, ...]
    report_summary: str
    overlay_luts: tuple[LogicalLutCell, ...]
    selected_attempt: OverlayMappingAttempt
    attempts: tuple[OverlayMappingAttempt, ...]

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
        Maximum LUT size for mapping the overlay design. If ``None``, the
        layerer derives the size from the available leftover inventory.
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
    debug: bool = False


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
    """

    mapping: MappingResult
    stats: LutLayeringStats
    placements: tuple[LayeredLutPlacement, ...]
    report_summary: str
    overlay_luts: tuple[LogicalLutCell, ...]

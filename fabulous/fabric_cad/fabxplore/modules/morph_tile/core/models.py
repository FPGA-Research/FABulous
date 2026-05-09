"""Typed models for morph-tile cut solving.

The cut solver uses SAT-based equivalence to check whether a target configurable tile
can implement a single LUT truth table. These models keep the public result compact
while preserving the decoded mappings that are useful for later morph-tile flows.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from fabulous.fabric_cad.fabxplore.modules.sat_fab.result import EquivResult


@dataclass(frozen=True)
class CutSolveResult:
    """Store the decoded result of one cut-solving run.

    Attributes
    ----------
    sat : bool
        Whether the requested LUT function can be implemented.
    input_mapping : dict[str, str]
        Mapping from candidate tile input names to logical LUT input names.
    scoped_input_mapping : dict[str, str]
        Same mapping with SAT-fab circuit role prefixes.
    output_mapping : dict[str, str]
        Mapping from logical LUT output names to selected candidate tile output
        names.
    scoped_output_mapping : dict[str, str]
        Same mapping with SAT-fab circuit role prefixes.
    config_bits : dict[str, bool | None]
        Decoded external configuration bit values for the candidate circuit.
        ``None`` means the SAT solution did not constrain that bit.
    raw_result : EquivResult | None
        Underlying SAT-fab result for advanced inspection.
    """

    sat: bool
    input_mapping: dict[str, str] = field(default_factory=dict)
    scoped_input_mapping: dict[str, str] = field(default_factory=dict)
    output_mapping: dict[str, str] = field(default_factory=dict)
    scoped_output_mapping: dict[str, str] = field(default_factory=dict)
    config_bits: dict[str, bool | None] = field(default_factory=dict)
    raw_result: EquivResult | None = None


@dataclass(frozen=True)
class MorphTileReplacement:
    """Describe one LUT replaced by a morph-tile instance.

    Attributes
    ----------
    original_cell_id : str
        Original Yosys ``$lut`` instance name.
    replacement_cell_id : str
        New morph-tile instance name.
    width : int
        Width of the replaced LUT.
    init : int
        INIT value of the replaced LUT.
    input_mapping : dict[str, str]
        Candidate tile input to logical LUT input mapping.
    output_mapping : dict[str, str]
        Logical LUT output to selected candidate tile output mapping.
    config_bits : dict[str, bool | None]
        Solved configuration values.
    """

    original_cell_id: str
    replacement_cell_id: str
    width: int
    init: int
    input_mapping: dict[str, str]
    output_mapping: dict[str, str]
    config_bits: dict[str, bool | None]


@dataclass(frozen=True)
class MorphTileLutCell:
    """Represent one LUT cell extracted from the source design.

    Attributes
    ----------
    cell_id : str
        Cell name in the selected top module.
    width : int
        LUT input width.
    init : int
        Parsed LSB-first INIT value.
    """

    cell_id: str
    width: int
    init: int


@dataclass(frozen=True)
class MorphTileDesign:
    """Internal morph-tile view of a Yosys top module.

    Attributes
    ----------
    top_name : str
        Name of the top module that was read.
    lut_cells : tuple[MorphTileLutCell, ...]
        LUT cells found in stable module order.
    """

    top_name: str
    lut_cells: tuple[MorphTileLutCell, ...]


@dataclass(frozen=True)
class MorphTileStats:
    """Aggregate counters for one morph-tile mapping run.

    Attributes
    ----------
    total_luts : int
        Total ``$lut`` cells in the processed top module.
    candidate_luts : int
        LUTs whose widths were considered for morphing.
    replaced_luts : int
        Candidate LUTs successfully replaced.
    failed_luts : int
        Candidate LUTs that SAT could not implement.
    skipped_luts : int
        LUTs ignored because their width was not considered or the replacement
        limit was reached.
    skipped_width_luts : int
        LUTs ignored because their width was not selected.
    skipped_limit_luts : int
        Candidate LUTs ignored after the replacement limit was reached.
    cache_hits : int
        Number of candidate checks served by the solver cache.
    cache_misses : int
        Number of unique ``(width, init)`` checks sent to the solver.
    replacements_by_width : dict[str, int]
        Replaced LUT histogram by width label.
    failures_by_width : dict[str, int]
        Failed LUT histogram by width label.
    mapped_init_count : dict[str, int]
        Most common replaced INIT functions, keyed as ``LUTW:0xINIT``.
    """

    total_luts: int = 0
    candidate_luts: int = 0
    replaced_luts: int = 0
    failed_luts: int = 0
    skipped_luts: int = 0
    skipped_width_luts: int = 0
    skipped_limit_luts: int = 0
    cache_hits: int = 0
    cache_misses: int = 0
    replacements_by_width: dict[str, int] = field(default_factory=dict)
    failures_by_width: dict[str, int] = field(default_factory=dict)
    mapped_init_count: dict[str, int] = field(default_factory=dict)


@dataclass(frozen=True)
class MorphTileResult:
    """Return data for one morph-tile mapper run.

    Attributes
    ----------
    top_name : str
        Processed top module.
    tile_top_name : str
        Morph-tile module instantiated for replacements.
    considered_lut_widths : list[int]
        LUT widths considered by the mapper.
    max_replacements : int | None
        Optional replacement cap.
    use_canonical_cache : bool
        Whether cache keys use permutation-canonical INIT values.
    stats : MorphTileStats
        Summary counters.
    replacements : tuple[MorphTileReplacement, ...]
        Applied replacements.
    report_summary : str
        Human-readable report.
    """

    top_name: str
    tile_top_name: str
    considered_lut_widths: list[int]
    max_replacements: int | None
    use_canonical_cache: bool
    stats: MorphTileStats
    replacements: tuple[MorphTileReplacement, ...]
    report_summary: str = ""

    @property
    def replaced_total_percent(self) -> float:
        """Return replacement percentage over all LUTs.

        Returns
        -------
        float
            ``100 * replaced_luts / total_luts`` or ``0.0`` for empty designs.
        """
        if self.stats.total_luts <= 0:
            return 0.0
        return (100.0 * self.stats.replaced_luts) / float(self.stats.total_luts)

    @property
    def replaced_checked_candidate_percent(self) -> float:
        """Return replacement percentage over checked candidates.

        Returns
        -------
        float
            ``100 * replaced_luts / candidate_luts`` or ``0.0`` when no
            candidate was checked. ``candidate_luts`` is affected by
            ``max_replacements`` because candidates after the cap are skipped.
        """
        if self.stats.candidate_luts <= 0:
            return 0.0
        return (100.0 * self.stats.replaced_luts) / float(self.stats.candidate_luts)

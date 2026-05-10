"""Typed models for morph-tile cut solving.

The cut solver uses SAT-based equivalence to check whether a target configurable tile
can implement one source-design cut. These models keep the public result compact while
preserving decoded mappings for later morph-tile flows.
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
        Whether the requested cut function can be implemented.
    input_mapping : dict[str, str]
        Mapping from candidate tile input names to logical spec input names.
    scoped_input_mapping : dict[str, str]
        Same mapping with SAT-fab circuit role prefixes.
    output_mapping : dict[str, str]
        Mapping from logical spec output names to selected candidate tile output
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
class CellPortBitRef:
    """Reference one bit of a port on the original netlist cell.

    Attributes
    ----------
    port : str
        Original cell port name without a leading backslash.
    index : int
        Bit index within the original port signal.
    """

    port: str
    index: int = 0


@dataclass(frozen=True)
class ReplacementPortRef:
    """Describe a signal used by a replacement tile port.

    Attributes
    ----------
    constant : int | None
        Constant bit value when this reference is tied to ``0`` or ``1``.
    cell_port : CellPortBitRef | None
        Original-cell port bit to reuse when the signal comes from the replaced
        cell.
    """

    constant: int | None = None
    cell_port: CellPortBitRef | None = None

    @classmethod
    def const(cls, value: int | bool) -> ReplacementPortRef:
        """Build a constant replacement-port reference.

        Parameters
        ----------
        value : int | bool
            Boolean-like constant value.

        Returns
        -------
        ReplacementPortRef
            Constant signal reference.
        """
        return cls(constant=1 if bool(value) else 0)

    @classmethod
    def cell_port_bit(cls, port: str, index: int = 0) -> ReplacementPortRef:
        """Build an original-cell port-bit reference.

        Parameters
        ----------
        port : str
            Original cell port name without a leading backslash.
        index : int
            Bit index within the original port.

        Returns
        -------
        ReplacementPortRef
            Port-bit signal reference.
        """
        return cls(cell_port=CellPortBitRef(port=port, index=index))


@dataclass(frozen=True)
class MorphTileReplacement:
    """Describe one source cell replaced by a morph-tile instance.

    Attributes
    ----------
    original_cell_id : str
        Original Yosys cell instance name.
    replacement_cell_id : str
        New morph-tile instance name.
    width : int
        Width-like value of the replaced cut, used for report compatibility.
    init : int
        INIT-like value of the replaced cut, used for report compatibility.
    input_mapping : dict[str, str]
        Decoded SAT candidate tile input to spec input mapping.
    output_mapping : dict[str, str]
        Decoded SAT spec output to selected candidate tile output mapping.
    input_ports : dict[str, ReplacementPortRef]
        Concrete replacement tile input port wiring.
    output_ports : dict[str, ReplacementPortRef]
        Concrete replacement tile output port wiring.
    config_bits : dict[str, bool | None]
        Solved configuration values.
    """

    original_cell_id: str
    replacement_cell_id: str
    width: int
    init: int
    input_mapping: dict[str, str]
    output_mapping: dict[str, str]
    input_ports: dict[str, ReplacementPortRef]
    output_ports: dict[str, ReplacementPortRef]
    config_bits: dict[str, bool | None]


@dataclass(frozen=True)
class MorphTileNetlistCell:
    """Represent one generic netlist cell in the source design.

    Attributes
    ----------
    cell_id : str
        Cell name in the selected top module.
    cell_type : str
        Cell type without a leading Yosys escape backslash.
    parameters : dict[str, str]
        Cell parameters normalized to string values.
    connections : dict[str, tuple[str, ...]]
        Cell port connections normalized to string net tokens.
    """

    cell_id: str
    cell_type: str
    parameters: dict[str, str]
    connections: dict[str, tuple[str, ...]]


@dataclass(frozen=True)
class MorphTileDesign:
    """Internal morph-tile view of a Yosys top module.

    Attributes
    ----------
    top_name : str
        Name of the top module that was read.
    cells : tuple[MorphTileNetlistCell, ...]
        Cells found in stable module order.
    """

    top_name: str
    cells: tuple[MorphTileNetlistCell, ...]


@dataclass(frozen=True)
class MorphTileStats:
    """Aggregate counters for one morph-tile mapping run.

    Attributes
    ----------
    total_candidates : int
        Source-design candidates yielded by all enabled circuit adapters.
    checked_candidates : int
        Candidates selected for SAT solving.
    replaced_candidates : int
        Candidates successfully replaced.
    failed_candidates : int
        Checked candidates that SAT could not implement.
    skipped_candidates : int
        Candidates ignored because filters did not select them or the
        replacement limit was reached.
    skipped_filter_candidates : int
        Candidates ignored by adapter-local filters.
    skipped_limit_candidates : int
        Candidates ignored after the replacement limit was reached.
    cache_hits : int
        Number of candidate checks served by the solver cache.
    cache_misses : int
        Number of unique checks sent to the solver.
    replacements_by_width : dict[str, int]
        Replaced candidate histogram by width label.
    failures_by_width : dict[str, int]
        Failed candidate histogram by width label.
    mapped_init_count : dict[str, int]
        Most common replaced INIT-like signatures.
    """

    total_candidates: int = 0
    checked_candidates: int = 0
    replaced_candidates: int = 0
    failed_candidates: int = 0
    skipped_candidates: int = 0
    skipped_filter_candidates: int = 0
    skipped_limit_candidates: int = 0
    cache_hits: int = 0
    cache_misses: int = 0
    replacements_by_width: dict[str, int] = field(default_factory=dict)
    failures_by_width: dict[str, int] = field(default_factory=dict)
    mapped_init_count: dict[str, int] = field(default_factory=dict)

    @property
    def total_luts(self) -> int:
        """Return the legacy total-LUT counter alias.

        Returns
        -------
        int
            ``total_candidates``.
        """
        return self.total_candidates

    @property
    def candidate_luts(self) -> int:
        """Return the legacy checked-LUT counter alias.

        Returns
        -------
        int
            ``checked_candidates``.
        """
        return self.checked_candidates

    @property
    def replaced_luts(self) -> int:
        """Return the legacy replaced-LUT counter alias.

        Returns
        -------
        int
            ``replaced_candidates``.
        """
        return self.replaced_candidates

    @property
    def failed_luts(self) -> int:
        """Return the legacy failed-LUT counter alias.

        Returns
        -------
        int
            ``failed_candidates``.
        """
        return self.failed_candidates

    @property
    def skipped_luts(self) -> int:
        """Return the legacy skipped-LUT counter alias.

        Returns
        -------
        int
            ``skipped_candidates``.
        """
        return self.skipped_candidates

    @property
    def skipped_width_luts(self) -> int:
        """Return the legacy skipped-width counter alias.

        Returns
        -------
        int
            ``skipped_filter_candidates``.
        """
        return self.skipped_filter_candidates

    @property
    def skipped_limit_luts(self) -> int:
        """Return the legacy skipped-limit counter alias.

        Returns
        -------
        int
            ``skipped_limit_candidates``.
        """
        return self.skipped_limit_candidates


@dataclass(frozen=True)
class MorphTileResult:
    """Return data for one morph-tile mapper run.

    Attributes
    ----------
    top_name : str
        Processed top module.
    tile_top_name : str
        Morph-tile module instantiated for replacements.
    filter_summary : dict[str, list[str]]
        User-facing filters selected by enabled circuit adapters.
    max_replacements : int | None
        Optional replacement cap.
    stats : MorphTileStats
        Summary counters.
    replacements : tuple[MorphTileReplacement, ...]
        Applied replacements.
    report_summary : str
        Human-readable report.
    """

    top_name: str
    tile_top_name: str
    filter_summary: dict[str, list[str]]
    max_replacements: int | None
    stats: MorphTileStats
    replacements: tuple[MorphTileReplacement, ...]
    report_summary: str = ""

    @property
    def replaced_total_percent(self) -> float:
        """Return replacement percentage over all LUTs.

        Returns
        -------
        float
            ``100 * replaced_candidates / total_candidates`` or ``0.0`` for
            empty designs.
        """
        if self.stats.total_candidates <= 0:
            return 0.0
        return (100.0 * self.stats.replaced_candidates) / float(
            self.stats.total_candidates
        )

    @property
    def replaced_checked_candidate_percent(self) -> float:
        """Return replacement percentage over checked candidates.

        Returns
        -------
        float
            ``100 * replaced_candidates / checked_candidates`` or ``0.0`` when
            no candidate was checked. ``checked_candidates`` is affected by
            ``max_replacements`` because candidates after the cap are skipped.
        """
        if self.stats.checked_candidates <= 0:
            return 0.0
        return (100.0 * self.stats.replaced_candidates) / float(
            self.stats.checked_candidates
        )

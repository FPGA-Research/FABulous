"""Typed data models for LUT decomposition.

The decomposer keeps a pure-Python representation of selected Yosys ``$lut`` cells,
computes a replacement plan, and lets the writer apply that plan to the live pyosys
design. These models are the contract between those steps.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from fabulous.fabric_cad.fabxplore.modules.morph_tile.core.models import (
        ReplacementPortRef,
    )


@dataclass(frozen=True)
class LutDecomposerCell:
    """Represent one extracted Yosys ``$lut`` cell.

    Attributes
    ----------
    cell_id : str
        Cell name in the selected top module.
    width : int
        LUT input width.
    init : int
        Parsed LSB-first truth-table INIT.
    input_bits : tuple[str, ...]
        Generic signal tokens connected to input port ``A``.
    output_bit : str
        Generic signal token connected to output port ``Y``.
    """

    cell_id: str
    width: int
    init: int
    input_bits: tuple[str, ...]
    output_bit: str


@dataclass(frozen=True)
class LutDecomposerDesign:
    """Internal view of the selected module.

    Attributes
    ----------
    top_name : str
        Top module name.
    lut_cells : tuple[LutDecomposerCell, ...]
        Extracted LUT cells in stable reader order.
    """

    top_name: str
    lut_cells: tuple[LutDecomposerCell, ...]


@dataclass(frozen=True)
class MuxSolveKey:
    """Cache key for one mux primitive capability solve.

    Attributes
    ----------
    data_inputs : int
        Number of abstract cofactor data inputs.
    select_inputs : int
        Number of abstract select inputs.
    """

    data_inputs: int
    select_inputs: int


@dataclass(frozen=True)
class MuxSolveResult:
    """Solved routing/configuration for one mux shape.

    Attributes
    ----------
    sat : bool
        Whether the mux primitive can realize the requested shape.
    input_mapping : dict[str, str]
        Candidate mux input port to abstract spec source name.
    output_mapping : dict[str, str]
        Abstract spec output to candidate mux output port.
    config_bits : dict[str, bool | None]
        Solved config values keyed by config port name.
    cache_hit : bool
        Whether this result came from the shape cache.
    """

    sat: bool
    input_mapping: dict[str, str] = field(default_factory=dict)
    output_mapping: dict[str, str] = field(default_factory=dict)
    config_bits: dict[str, bool | None] = field(default_factory=dict)
    cache_hit: bool = False


@dataclass(frozen=True)
class LutCofactor:
    """Generated leaf LUT cofactor.

    Attributes
    ----------
    index : int
        Cofactor index selected by high LUT input bits.
    init : int
        Leaf LUT INIT.
    cell_id : str
        Generated leaf cell name.
    output_wire_id : str
        Generated wire name that carries the cofactor result.
    """

    index: int
    init: int
    cell_id: str
    output_wire_id: str


@dataclass(frozen=True)
class LutDecomposition:
    """Replacement plan for one high-width LUT.

    Attributes
    ----------
    original_cell_id : str
        Original high-width LUT cell.
    source_width : int
        Original LUT width.
    leaf_lut_width : int
        Width of generated cofactor LUTs.
    cofactors : tuple[LutCofactor, ...]
        Generated leaf LUTs.
    mux_cell_id : str
        Generated mux instance name.
    mux_input_ports : dict[str, ReplacementPortRef]
        Mux input port mapping.
    mux_output_ports : dict[str, ReplacementPortRef]
        Mux output port mapping.
    mux_config_bits : dict[str, bool | None]
        Solved mux config values.
    mux_shape : MuxSolveKey
        Mux shape used by this decomposition.
    """

    original_cell_id: str
    source_width: int
    leaf_lut_width: int
    cofactors: tuple[LutCofactor, ...]
    mux_cell_id: str
    mux_input_ports: dict[str, ReplacementPortRef]
    mux_output_ports: dict[str, ReplacementPortRef]
    mux_config_bits: dict[str, bool | None]
    mux_shape: MuxSolveKey


@dataclass(frozen=True)
class LutDecomposerStats:
    """Summary counters for one decomposition run.

    Attributes
    ----------
    total_luts : int
        Total extracted ``$lut`` cells.
    candidate_luts : int
        LUTs whose width is selected for decomposition.
    decomposed_luts : int
        Successfully decomposed LUTs.
    skipped_width_luts : int
        LUTs skipped because their width was not selected.
    failed_luts : int
        Selected LUTs that could not be decomposed.
    mux_solves : int
        Number of SAT mux-shape solves performed.
    mux_cache_hits : int
        Number of mux-shape cache hits.
    generated_leaf_luts : int
        Number of generated cofactor LUTs.
    """

    total_luts: int = 0
    candidate_luts: int = 0
    decomposed_luts: int = 0
    skipped_width_luts: int = 0
    failed_luts: int = 0
    mux_solves: int = 0
    mux_cache_hits: int = 0
    generated_leaf_luts: int = 0


@dataclass(frozen=True)
class LutDecomposerResult:
    """Complete decomposition result.

    Attributes
    ----------
    top_name : str
        Processed top module.
    source_lut_widths : tuple[int, ...]
        Selected source LUT widths.
    leaf_lut_width : int
        Generated leaf LUT width.
    decompositions : tuple[LutDecomposition, ...]
        Planned and applied decompositions.
    stats : LutDecomposerStats
        Summary counters.
    report_summary : str
        Human-readable report text.
    """

    top_name: str
    source_lut_widths: tuple[int, ...]
    leaf_lut_width: int
    decompositions: tuple[LutDecomposition, ...]
    stats: LutDecomposerStats
    report_summary: str = ""

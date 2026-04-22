"""Typed model objects used by the design analyzer pipeline.

This module defines immutable netlist model classes plus mutable analysis result
containers. The analyzer maps Yosys JSON into these classes first and then performs all
metrics and reporting steps purely on this internal representation.
"""

from dataclasses import dataclass, field

from fabulous.fabric_cad.fabxplore.modules.design_analyzer.core.taxonomy import (
    CellFamily,
    DesignTag,
)


@dataclass(frozen=True)
class DesignAnalyzerConfig:
    """Configuration knobs for one design analyzer run.

    Attributes
    ----------
    top_name : str | None
        Optional explicit top module name. If ``None``, the parser picks the
        module with the largest cell count.
    include_chain_metrics : bool
        If ``True``, compute chain-oriented metrics (for example AND/OR depth)
        using connectivity analysis.
    max_type_rows : int
        Maximum number of cell types shown in the rendered report table.
    progress : bool
        If ``True``, emit progress updates through the logger.
    """

    top_name: str | None = None
    include_chain_metrics: bool = True
    max_type_rows: int = 24
    progress: bool = True


@dataclass(frozen=True)
class ModulePort:
    """Port description for the selected top-level module.

    Attributes
    ----------
    name : str
        Port name in the selected module.
    direction : str
        Port direction as encoded by Yosys JSON (``input``, ``output``, or
        ``inout``).
    bits : tuple[str, ...]
        Normalized bit identifiers connected to this port.
    """

    name: str
    direction: str
    bits: tuple[str, ...]


@dataclass(frozen=True)
class LogicalCell:
    """Normalized internal representation of one cell instance.

    Attributes
    ----------
    cell_id : str
        Instance identifier in the selected module.
    cell_type : str
        Cell type string (for example ``$mux`` or ``$_MUX_``).
    parameters : dict[str, str]
        Stringified cell parameters.
    attributes : dict[str, str]
        Stringified cell attributes.
    connections : dict[str, tuple[str, ...]]
        Port-to-bit-vector mapping with normalized bit identifiers.
    port_directions : dict[str, str]
        Direction map per port. Missing Yosys metadata is inferred by parser
        heuristics.
    input_bits : tuple[str, ...]
        Flattened input bits for fast graph and fanin analysis.
    output_bits : tuple[str, ...]
        Flattened output bits for fast graph and fanout analysis.
    inout_bits : tuple[str, ...]
        Flattened inout bits.
    """

    cell_id: str
    cell_type: str
    parameters: dict[str, str]
    attributes: dict[str, str]
    connections: dict[str, tuple[str, ...]]
    port_directions: dict[str, str]
    input_bits: tuple[str, ...]
    output_bits: tuple[str, ...]
    inout_bits: tuple[str, ...]


@dataclass(frozen=True)
class TopModuleNetlist:
    """Parsed top-module netlist model used by the analyzer.

    Attributes
    ----------
    creator : str
        ``creator`` value from Yosys JSON.
    top_name : str
        Selected top-module name.
    ports : tuple[ModulePort, ...]
        Top-level module ports.
    cells : tuple[LogicalCell, ...]
        All cells in the selected top module.
    bit_to_netname : dict[str, str]
        Best-effort mapping from bit ids to readable net names.
    """

    creator: str
    top_name: str
    ports: tuple[ModulePort, ...]
    cells: tuple[LogicalCell, ...]
    bit_to_netname: dict[str, str]


@dataclass(frozen=True)
class ChainMetric:
    """Connectivity metric for one logic family.

    Attributes
    ----------
    family : CellFamily
        Logic family name for this metric.
    candidate_cells : int
        Number of cells that belong to this family.
    largest_component : int
        Largest weakly-connected component size in the family subgraph.
    longest_path : int
        Longest path estimate in the condensed family graph.
    """

    family: CellFamily
    candidate_cells: int
    largest_component: int
    longest_path: int


@dataclass
class DesignAnalysisStats:
    """Aggregated raw metrics computed for one analyzed design.

    Attributes
    ----------
    total_cells : int
        Total number of cells in the selected top module.
    total_ports : int
        Total number of top-level ports.
    total_nets : int
        Number of unique non-constant bits touched by cells/ports.
    coarse_internal_cells : int
        Count of coarse Yosys internal cells (``$...``).
    fine_gate_cells : int
        Count of fine Yosys gate-level cells (``$_..._``).
    custom_cells : int
        Count of non-Yosys-prefixed/custom cell types.
    combinational_cells : int
        Count of cells classified as combinational.
    sequential_cells : int
        Count of cells classified as sequential.
    memory_cells : int
        Count of cells classified as memory structures.
    unknown_cells : int
        Count of cells that could not be classified safely.
    family_counts : dict[CellFamily, int]
        Family counters (mux/arithmetic/reduction/etc.).
    cell_type_counts : dict[str, int]
        Histogram of exact cell types.
    chain_metrics : dict[CellFamily, ChainMetric]
        Chain/connectivity metrics per selected family.
    max_fanin : int
        Maximum number of unique predecessor cells for one cell.
    avg_fanin : float
        Average unique predecessor count.
    max_fanout : int
        Maximum number of unique successor cells for one cell.
    avg_fanout : float
        Average unique successor count.
    clock_port_refs : int
        Number of sequential-cell port references classified as clock-like.
    reset_port_refs : int
        Number of sequential-cell port references classified as reset-like.
    set_port_refs : int
        Number of sequential-cell port references classified as set-like.
    enable_port_refs : int
        Number of sequential-cell port references classified as enable-like.
    """

    total_cells: int = 0
    total_ports: int = 0
    total_nets: int = 0

    coarse_internal_cells: int = 0
    fine_gate_cells: int = 0
    custom_cells: int = 0

    combinational_cells: int = 0
    sequential_cells: int = 0
    memory_cells: int = 0
    unknown_cells: int = 0

    family_counts: dict[CellFamily, int] = field(default_factory=dict)
    cell_type_counts: dict[str, int] = field(default_factory=dict)
    chain_metrics: dict[CellFamily, ChainMetric] = field(default_factory=dict)

    max_fanin: int = 0
    avg_fanin: float = 0.0
    max_fanout: int = 0
    avg_fanout: float = 0.0
    clock_port_refs: int = 0
    reset_port_refs: int = 0
    set_port_refs: int = 0
    enable_port_refs: int = 0


@dataclass
class DesignCharacterization:
    """Human-focused interpretation of raw analyzer metrics.

    Attributes
    ----------
    tags : tuple[DesignTag, ...]
        Compact labels that summarize the design style.
    observations : tuple[str, ...]
        Human-readable observations derived from analysis metrics.
    warnings : tuple[str, ...]
        Potential caveats or data-quality notes for this analysis.
    recommendations : tuple[str, ...]
        Actionable hints for architecture exploration.
    """

    tags: tuple[DesignTag, ...] = ()
    observations: tuple[str, ...] = ()
    warnings: tuple[str, ...] = ()
    recommendations: tuple[str, ...] = ()


@dataclass
class DesignAnalysisResult:
    """Final analysis output bundle for one design.

    Attributes
    ----------
    top_name : str
        Analyzed top module name.
    stats : DesignAnalysisStats
        Full set of computed statistics.
    characterization : DesignCharacterization
        Human-readable interpretation of statistics.
    metadata : dict[str, str]
        Additional metadata (for example parser/analyzer version tags).
    report_summary : str | None
        Pre-rendered user report string.
    """

    top_name: str
    stats: DesignAnalysisStats
    characterization: DesignCharacterization
    metadata: dict[str, str] = field(default_factory=dict)
    report_summary: str | None = None

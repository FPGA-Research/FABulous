"""Define typed model objects shared across the LUT mapping pipeline.

This module centralizes enums, dataclasses, and JSON helper utilities used by parser,
mapper, transform, and report layers.
"""

import re
from dataclasses import dataclass, field
from enum import StrEnum


@dataclass(frozen=True)
class LutSpec:
    """Capture LUT-specific parsing patterns and conventions.

    This enum centralizes regular expressions and constants used to identify
    and manipulate LUT cells within the netlist parsing process.

    Note that Bus patterns are converted to tuples of individual nets by the parser,
    so the regexes should match the individual net names rather than the entire bus.
    Like "A":[1,2,3] would be "A0":[1], "A1":[2], "A2":[3] in the JSON.
    Single-bit like "A":[1] would be "A":[1] in the JSON.

    Attributes
    ----------
    lut_re : re.Pattern
        Regular expression to match LUT cell types and extract their width.
    init_name : str
        Parameter name used for LUT truth-table initialization.
    input_re : re.Pattern
        Regular expression to identify LUT input port names.
    output_ports : set[str]
        Set of valid output port names for LUT cells.
    """

    lut_re: re.Pattern = re.compile(r"^\$lut$")
    init_name: str = "LUT"
    input_re: re.Pattern = re.compile(r"^A\d+$")
    output_ports: set[str] = frozenset({"O", "Q", "Y"})


class MatchingMode(StrEnum):
    """Enumerate graph matching strategies used by pair selection.

    The value is passed through config into the packer where it selects
    the corresponding NetworkX matching routine.

    Attributes
    ----------
    MAX_WEIGHT
        Use maximum-weight matching to optimize for LUT count reduction.
    MAXIMAL
        Use maximal matching for faster execution without optimality guarantees.
    """

    MAX_WEIGHT = "max_weight"
    MAXIMAL = "maximal"


@dataclass(frozen=True)
class LogicalLutCell:
    """Represent a single logical LUT instance from source netlist data.

    The parser normalizes LUT cells into this compact form so architecture
    and packing logic can work on typed values instead of raw JSON blobs.

    Attributes
    ----------
    cell_id : str
        Original instance identifier.
    cell_type : str
        LUT type name (for example ``"LUT4"``).
    input_nets : tuple[str, ...]
        Ordered source input net names.
    output_net : str
        Source output net name.
    init : int
        Truth-table INIT bits encoded as integer.
    width : int
        LUT input width.
    """

    cell_id: str
    cell_type: str
    input_nets: tuple[str, ...]
    output_net: str
    init: int
    width: int


@dataclass(frozen=True)
class CellPlacement:
    """Capture placement of one logical LUT into one architecture slot.

    The mapping is expressed both as slot pin indices and symbolic source
    names (for example ``I0``/``A0``) used later for reporting/export.

    Attributes
    ----------
    cell : LogicalLutCell
        Logical LUT cell being placed.
    slot_name : str
        Slot label inside packed macro (for example ``"L0"``).
    input_to_slot_pin : tuple[int, ...]
        Source input to slot-pin index mapping.
    input_to_slot_source : tuple[str, ...]
        Source input to slot source-name mapping.
    """

    cell: LogicalLutCell
    slot_name: str
    input_to_slot_pin: tuple[int, ...]
    input_to_slot_source: tuple[str, ...]


@dataclass(frozen=True)
class PairBinding:
    """Describe a validated two-LUT placement into one fractional macro.

    This structure stores per-side placements and final external pin/output
    wiring after feasibility checks have succeeded.

    Attributes
    ----------
    placement0 : CellPlacement
        Placement information for side ``L0``.
    placement1 : CellPlacement
        Placement information for side ``L1``.
    external_pin_nets : dict[str, str]
        Macro input pin name to net mapping.
    output_pin_nets : dict[str, str]
        Macro output pin name to net mapping.
    """

    placement0: CellPlacement
    placement1: CellPlacement
    external_pin_nets: dict[str, str]
    output_pin_nets: dict[str, str]


@dataclass(frozen=True)
class FracLutCellParameters:
    """Represent the stable parameter schema emitted for one FRAC LUT cell.

    Attributes map one-to-one to Verilog parameters on the generated
    fractional LUT cell. Use `as_dict` when writing these values into a
    `PackedCell` or JSON netlist.

    Attributes
    ----------
    meta_data : str
        Encoded metadata string for this cell instance.
    lut_size : int
        The size if the fractional LUT inside the macro.
    num_shared_inputs : int
        The number of shared inputs between the two LUTs in this macro.
    l0_cell_id : str
        The cell_id of the logical LUT placed in side L0.
    l1_cell_id : str
        The cell_id of the logical LUT placed in side L1.
    l0_init : str
        The INIT value for the LUT placed in side L0, encoded as a hex string.
    l1_init : str
        The INIT value for the LUT placed in side L1, encoded as a hex string.
    select_as_data_capable : bool
        Whether this cell can support the select-as-data dual-LUT pairing mode
        based on its shared input configuration.
    select_as_data_used : bool
        Whether the select-as-data mode is actually used in this
        cell's configuration.
    effective_shared_inputs : int | None
        The effective number of shared inputs used for this cell, which may
        differ from the original num_shared_inputs in cases where select-as-data
        mode is enabled and allows for more flexible pairing.
    cut_shared_index : int
        The index at which the shared inputs are cut between the two LUTs, used
        for determining how inputs are distributed in the macro.
    mux_select_config : int
        An integer encoding the configuration of the internal multiplexer select
        signals for this cell.
    """

    meta_data: str
    lut_size: int
    num_shared_inputs: int
    l0_cell_id: str
    l1_cell_id: str
    l0_init: str
    l1_init: str
    select_as_data_capable: bool = False
    select_as_data_used: bool = False
    effective_shared_inputs: int | None = None
    cut_shared_index: int = -1
    mux_select_config: int = 0

    def as_dict(self) -> dict[str, str]:
        """Return parameters using the exact emitted Verilog parameter names."""
        effective_shared_inputs = (
            self.num_shared_inputs
            if self.effective_shared_inputs is None
            else self.effective_shared_inputs
        )
        return {
            "META_DATA": self.meta_data,
            "LUT_SIZE": str(self.lut_size),
            "NUM_SHARED_INPUTS": str(self.num_shared_inputs),
            "L0_CELL_ID": self.l0_cell_id,
            "L1_CELL_ID": self.l1_cell_id,
            "L0_INIT": self.l0_init,
            "L1_INIT": self.l1_init,
            "SELECT_AS_DATA_CAPABLE": ("1" if self.select_as_data_capable else "0"),
            "SELECT_AS_DATA_USED": "1" if self.select_as_data_used else "0",
            "EFFECTIVE_SHARED_INPUTS": str(effective_shared_inputs),
            "CUT_SHARED_INDEX": str(self.cut_shared_index),
            "MUX_SELECT_CONFIG": str(self.mux_select_config),
        }


@dataclass(frozen=True)
class PackedCell:
    """Represent one emitted packed architecture macro instance.

    This combines placement provenance, external connectivity, and emitted
    parameter values needed for JSON and Verilog output generation.

    Attributes
    ----------
    packed_id : str
        Packed macro instance identifier.
    architecture_name : str
        Emitted cell type name (for example ``"FRAC_LUT5"``).
    placements : tuple[CellPlacement, ...]
        Source placement records consumed by this macro.
    external_pin_nets : dict[str, str]
        Input pin to net mapping for macro instance.
    output_pin_nets : dict[str, str]
        Output pin to net mapping for macro instance.
    parameters : dict[str, str]
        Parameter dictionary serialized to output netlist.
    frac_lut_parameters : FracLutCellParameters
        Strongly-typed parameter values for this cell instance, which can be
        converted to the raw dict form in `parameters` for output but are more
        convenient to work with in the mapper and report generation.
    leftover_lut_width : int
        Remaining LUT width after packing.
        This is a measure of how much LUT resource is left
        unused in the macro and can be used for report
        generation and architecture efficiency analysis.
    """

    packed_id: str
    architecture_name: str
    placements: tuple[CellPlacement, ...]
    external_pin_nets: dict[str, str]
    output_pin_nets: dict[str, str]
    parameters: dict[str, str]
    frac_lut_parameters: FracLutCellParameters
    leftover_lut_width: int


@dataclass(frozen=True)
class NetlistModel:
    """Hold parser output for LUT-focused netlist processing.

    The parser extracts only LUTs relevant for packing and the selected
    top module name into this immutable container.

    Attributes
    ----------
    top_name : str
        Parsed top-level module name.
    lut_cells : tuple[LogicalLutCell, ...]
        Tuple of parsed logical LUT cells.
    """

    top_name: str
    lut_cells: tuple[LogicalLutCell, ...]


@dataclass
class MappingStats:
    """Store aggregate counters describing one mapping execution.

    Fields summarize before/after counts and mapped/pass-through totals
    for report generation and quick result inspection.

    Attributes
    ----------
    total_luts_before : int
        Number of LUT cells before mapping.
    total_cells_after : int
        Number of resulting cells considered in mapping output summary.
    mapped_groups : int
        Count of packed macro instances.
    mapped_luts : int
        Number of logical LUTs consumed by packed groups.
    passthrough_luts : int
        Number of LUTs left ungrouped by mapper.
    source_type_count : dict[str, int]
        Source LUT type histogram based on the width of the LUTs.
    passthrough_type_count : dict[str, int]
        Resulting LUT type histogram for passthrough LUTs.
    result_type_count : dict[str, int]
        Resulting LUT type histogram for all LUTs.
    """

    total_luts_before: int = 0
    total_cells_after: int = 0
    mapped_groups: int = 0
    mapped_luts: int = 0
    passthrough_luts: int = 0
    source_type_count: dict[str, int] = field(default_factory=dict)
    passthrough_type_count: dict[str, int] = field(default_factory=dict)
    result_type_count: dict[str, int] = field(default_factory=dict)


@dataclass
class MappingResult:
    """Bundle complete mapping outputs and metadata for one run.

    This object is the primary return type from mapper/combinator APIs and
    includes packed cells, passthrough LUTs, stats, and extra metadata.

    Attributes
    ----------
    architecture_name : str
        Target architecture name used for packed cells.
    top_name : str
        Top-level module name processed.
    mapped_cells : list[PackedCell]
        Packed macro cells emitted by the mapper.
    passthrough_luts : list[LogicalLutCell]
        LUTs not consumed by packing.
    stats : MappingStats
        Aggregate mapping counters.
    metadata : dict
        Additional execution metadata.
    report_summary : str | None
        Optional pre-formatted report summary for display.
    """

    architecture_name: str
    top_name: str
    mapped_cells: list[PackedCell]
    passthrough_luts: list[LogicalLutCell]
    stats: MappingStats
    metadata: dict = field(default_factory=dict)
    report_summary: str | None = None

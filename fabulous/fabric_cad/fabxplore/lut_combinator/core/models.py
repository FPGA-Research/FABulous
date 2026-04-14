"""Define typed model objects shared across the LUT mapping pipeline.

This module centralizes enums, dataclasses, and JSON helper utilities used by parser,
mapper, transform, and report layers.
"""

import re
from dataclasses import dataclass, field
from enum import Enum, StrEnum


class LutSpec(Enum):
    """Capture LUT-specific parsing patterns and conventions.

    This enum centralizes regular expressions and constants used to identify
    and manipulate LUT cells within the netlist parsing process.

    Attributes
    ----------
    LUT_RE : re.Pattern
        Regular expression to match LUT cell types and extract their width.
    INIT_NAME : str
        Parameter name used for LUT truth-table initialization.
    INPUT_RE : re.Pattern
        Regular expression to identify LUT input port names.
    OUTPUT_PORTS : set[str]
        Set of valid output port names for LUT cells.
    """

    LUT_RE: re.Pattern = re.compile(r"^LUT(\d+)$")
    INIT_NAME: str = "INIT"
    INPUT_RE: re.Pattern = re.compile(r"^I\d+$")
    OUTPUT_PORTS: set[str] = frozenset({"O", "Q", "Y"})


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
    """

    packed_id: str
    architecture_name: str
    placements: tuple[CellPlacement, ...]
    external_pin_nets: dict[str, str]
    output_pin_nets: dict[str, str]
    parameters: dict[str, str]


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
        Source LUT type histogram.
    """

    total_luts_before: int = 0
    total_cells_after: int = 0
    mapped_groups: int = 0
    mapped_luts: int = 0
    passthrough_luts: int = 0
    source_type_count: dict[str, int] = field(default_factory=dict)


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
    """

    architecture_name: str
    top_name: str
    mapped_cells: list[PackedCell]
    passthrough_luts: list[LogicalLutCell]
    stats: MappingStats
    metadata: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        """Convert the mapping result into a JSON-safe dictionary.

        The output is stable and report-friendly, with sorted maps where
        relevant and reduced objects for packed and passthrough cells.

        Attributes
        ----------
        None

        Returns
        -------
        dict
            JSON-serializable representation of this mapping result.
        """
        return {
            "architecture": self.architecture_name,
            "top": self.top_name,
            "stats": {
                "total_luts_before": self.stats.total_luts_before,
                "total_cells_after": self.stats.total_cells_after,
                "mapped_groups": self.stats.mapped_groups,
                "mapped_luts": self.stats.mapped_luts,
                "passthrough_luts": self.stats.passthrough_luts,
                "source_type_count": dict(sorted(self.stats.source_type_count.items())),
            },
            "metadata": _json_safe_dict(self.metadata),
            "mapped_cells": [
                {
                    "packed_id": cell.packed_id,
                    "architecture": cell.architecture_name,
                    "external_pins": dict(sorted(cell.external_pin_nets.items())),
                    "output_pins": dict(sorted(cell.output_pin_nets.items())),
                    "parameters": dict(sorted(cell.parameters.items())),
                    "placements": [
                        {
                            "cell_id": plc.cell.cell_id,
                            "cell_type": plc.cell.cell_type,
                            "slot_name": plc.slot_name,
                            "input_nets": list(plc.cell.input_nets),
                            "output_net": plc.cell.output_net,
                            "input_to_slot_pin": list(plc.input_to_slot_pin),
                            "input_to_slot_source": list(plc.input_to_slot_source),
                        }
                        for plc in cell.placements
                    ],
                }
                for cell in self.mapped_cells
            ],
            "passthrough_luts": [
                {
                    "cell_id": lut.cell_id,
                    "cell_type": lut.cell_type,
                    "inputs": list(lut.input_nets),
                    "output": lut.output_net,
                    "init": hex(lut.init),
                    "width": lut.width,
                }
                for lut in self.passthrough_luts
            ],
        }


def _json_safe_dict(data: dict) -> dict:
    """Convert a metadata dictionary to JSON-safe values.

    Keys starting with ``"_"`` are omitted to avoid leaking internal-only
    entries in exported result payloads.

    Parameters
    ----------
    data : dict
        Input metadata dictionary.

    Returns
    -------
    dict
        Filtered dictionary with recursively normalized values.
    """
    return {k: _json_safe(v) for k, v in data.items() if not k.startswith("_")}


def _json_safe(value: object) -> object:
    """Normalize arbitrary Python values into JSON-serializable form.

    Primitive types pass through unchanged; containers are processed
    recursively; unknown objects are converted via ``str(value)``.

    Parameters
    ----------
    value : object
        Value to normalize for JSON serialization.

    Returns
    -------
    object
        JSON-safe value or structure.
    """
    if isinstance(value, (str | int | float | bool)) or value is None:
        return value
    if isinstance(value, dict):
        return {str(k): _json_safe(v) for k, v in value.items()}
    if isinstance(value, (list | tuple | set)):
        return [_json_safe(v) for v in value]
    return str(value)

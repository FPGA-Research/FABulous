"""Basic Element of Logic (BEL) definition module.

This module contains the `Bel` class which represents a Basic Element of Logic in the
FPGA fabric.
BELs are the fundamental building blocks that can be placed and configured within tiles,
such as LUTs, flip-flops, and other logic elements.
"""

from dataclasses import dataclass, field
from pathlib import Path

from fabulous.custom_exception import InvalidState
from fabulous.fabric_definition.define import IO, HDLType
from fabulous.fabric_definition.yosys_obj import YosysJson, YosysModule

# Yosys cell types whose internal input->output path is sequential (broken by a
# register or memory) and therefore is NOT a combinational timing arc.
REGISTER_CELL_PREFIXES = (
    "$dff",
    "$adff",
    "$sdff",
    "$dffsr",
    "$dlatch",
    "$adlatch",
    "$sr",
    "$mem",
    "$_DFF",
    "$_SDFF",
    "$_DLATCH",
    "$_SR",
)


def _cell_is_sequential(cell_type: str, submodules: dict[str, YosysModule]) -> bool:
    """Return whether a cell type breaks the combinational path with a register.

    Parameters
    ----------
    cell_type : str
        The cell's module/primitive type name.
    submodules : dict[str, YosysModule]
        Sibling module definitions from the same netlist, keyed by module name.
        A custom primitive is sequential when its own definition contains a
        register cell.

    Returns
    -------
    bool
        True if the cell holds state (register/latch/memory).
    """
    if cell_type.startswith(REGISTER_CELL_PREFIXES):
        return True
    submodule = submodules.get(cell_type)
    if submodule is None:
        return False
    return any(
        cell.type.startswith(REGISTER_CELL_PREFIXES)
        for cell in submodule.cells.values()
    )


def _comb_arcs_from_module(
    module: YosysModule, submodules: dict[str, YosysModule]
) -> set[tuple[str, str]]:
    """Extract combinational input->output port arcs from a parsed module.

    Parameters
    ----------
    module : YosysModule
        The parsed netlist module to analyze.
    submodules : dict[str, YosysModule]
        Sibling module definitions from the same netlist (the resolved
        primitive library), used to classify each instantiated cell's direction
        and sequential-ness.

    Returns
    -------
    set[tuple[str, str]]
        Combinational `(input_port, output_port)` arcs in module-local names.
    """
    import networkx as nx

    graph = nx.DiGraph()
    for cell in module.cells.values():
        directions = cell.port_directions
        if not directions or _cell_is_sequential(cell.type, submodules):
            continue
        input_bits = [
            bit
            for port, bits in cell.connections.items()
            if directions.get(port) == "input"
            for bit in bits
            if isinstance(bit, int)
        ]
        output_bits = [
            bit
            for port, bits in cell.connections.items()
            if directions.get(port) == "output"
            for bit in bits
            if isinstance(bit, int)
        ]
        for source_bit in input_bits:
            for sink_bit in output_bits:
                graph.add_edge(source_bit, sink_bit)

    input_name: dict[int, str] = {}
    output_name: dict[int, str] = {}
    for port, detail in module.ports.items():
        multibit = len(detail.bits) > 1
        for index, bit in enumerate(detail.bits):
            if not isinstance(bit, int):
                continue
            name = f"{port}{index}" if multibit else port
            if detail.direction == "input":
                input_name[bit] = name
            elif detail.direction == "output":
                output_name[bit] = name

    arcs: set[tuple[str, str]] = set()
    for in_bit, in_port in input_name.items():
        reachable = nx.descendants(graph, in_bit) if in_bit in graph else set()
        for out_bit, out_port in output_name.items():
            if out_bit in reachable:
                arcs.add((in_port, out_port))
    return arcs


@dataclass
class Bel:
    """Information about a single BEL.

    The information is parsed from the directory of the BEL in the CSV definition file.
    There are some things to be noted:

    - The parsed name will contain the prefix of the bel.
    - The `sharedPort` attribute is a list of Tuples with the name of the port and
      IO information, which is not expanded out yet.
    - If a port is marked as both shared and external, the port is considered as shared,
      as a result, signals like UserCLK will be in the shared port list,
      but not in the external port list.

    Parameters
    ----------
    src : Path
        The source directory path of the BEL.
    prefix : str
        The prefix of the BEL.
    module_name : str
        The name of the module in the BEL.
    internal : list[tuple[str, IO]]
        List of internal ports with their IO direction.
    external : list[tuple[str, IO]]
        List of external ports with their IO direction.
    configPort : list[tuple[str, IO]]
        List of configuration ports with their IO direction.
    sharedPort : list[tuple[str, IO]]
        List of shared ports with their IO direction.
    configBit : int
        The number of configuration bits of the BEL.
    belMap : dict[str, dict]
        The feature map of the BEL.
    userCLK : bool
        Whether the BEL has userCLK port.
    ports_vectors : dict[str, dict[str, tuple[IO, int]]]
        Dictionary structure to save vectorized port information.
    carry : dict[str, dict[IO, str]]
        Carry chains by name.
    localShared : dict[str, tuple[str, IO]]
        Local shared ports of the BEL.
    yosys_json : YosysJson | None
        Parsed Yosys netlist of the BEL, used for combinational-arc analysis.
        Default is None.

    Attributes
    ----------
    src : Path
        The source directory of the BEL given in the CSV file.
    prefix : str
        The prefix of the BEL given in the CSV file.
    name : str
        The name of the BEL, extracted from the source directory.
    module_name : str
        The name of the module in the bel.
        For verlog we can extract this from the RTL.
        For VHDL this is currently the same as name.
    filetype : HDLType
        The file type of the BEL.
    inputs : list[str]
        All the normal input ports of the BEL.
    outputs : list[str]
        All the normal output ports of the BEL.
    externalInput : list[str]
        All the external input ports of the BEL.
    externalOutput : list[str]
        All the external output ports of the BEL.
    configPort : list[tuple[str, IO]]
        All the config ports of the BEL.
    sharedPort : list[tuple[str, IO]]
        All the shared ports of the BEL.
    configBit : int
        The number of config bits of the BEL.
    language : str
        Language of the BEL. Currently only VHDL and Verilog are supported.
    belFeatureMap : dict[str, dict]
        The feature map of the BEL.
    withUserCLK : bool
        Whether the BEL has userCLK port. Default is False.
    ports_vectors: dict[str, dict[str, tuple[IO, int]]]
        Dict structure to save vectorized port information
        {<porttype>:{<portname>:(IO, <portwidth>)}}
    carry : dict[str, dict[IO, str]]
        Carry chains by name.
        carry_name : {direction : port_name}
    localShared: dict[str,tuple[str, IO]]
        {RESET/ENABLE,(portname, IO)}
        Local shared ports of the BEL.
        Are only shared in the Tile, not in the fabric.
    yosys_json : YosysJson | None
        Parsed Yosys netlist of the BEL, used for combinational-arc analysis.

    Raises
    ------
    ValueError
        If the file type is not recognized (not .sv, .v, .vhd, or .vhdl).
    """

    src: Path
    prefix: str
    name: str
    module_name: str
    filetype: HDLType
    inputs: list[str]
    outputs: list[str]
    externalInput: list[str]
    externalOutput: list[str]
    configPort: list[tuple[str, IO]]
    sharedPort: list[tuple[str, IO]]
    configBit: int
    language: str
    belFeatureMap: dict[str, dict] = field(default_factory=dict)
    withUserCLK: bool = False
    ports_vectors: dict[str, dict[str, tuple[IO, int]]] = field(default_factory=dict)
    carry: dict[str, dict[IO, str]] = field(default_factory=dict)
    localShared: dict[str, tuple[str, IO]] = field(default_factory=dict)
    yosys_json: YosysJson | None = None

    def __init__(
        self,
        src: Path,
        prefix: str,
        module_name: str,
        internal: list[tuple[str, IO]],
        external: list[tuple[str, IO]],
        configPort: list[tuple[str, IO]],
        sharedPort: list[tuple[str, IO]],
        configBit: int,
        belMap: dict[str, dict],
        userCLK: bool,
        ports_vectors: dict[str, dict[str, tuple[IO, int]]],
        carry: dict[str, dict[IO, str]],
        localShared: dict[str, tuple[str, IO]],
        yosys_json: YosysJson | None = None,
    ) -> None:
        self.src = src
        self.prefix = prefix
        self.name = src.stem
        self.module_name = module_name
        self.inputs = [p for p, io in internal if io == IO.INPUT]
        self.outputs = [p for p, io in internal if io == IO.OUTPUT]
        self.externalInput = [p for p, io in external if io == IO.INPUT]
        self.externalOutput = [p for p, io in external if io == IO.OUTPUT]
        self.configPort = configPort
        self.sharedPort = sharedPort
        self.configBit = configBit
        self.belFeatureMap = belMap
        self.withUserCLK = userCLK
        self.ports_vectors = ports_vectors
        if self.src.suffix in [".sv", ".v"]:
            self.language = "verilog"
            self.filetype = HDLType.VERILOG
        elif self.src.suffix in [".vhd", ".vhdl"]:
            self.language = "vhdl"
            self.filetype = HDLType.VHDL
        else:
            raise ValueError(f"Unknown file type {self.src.suffix} for BEL {self.src}")
        self.carry = carry
        self.localShared = localShared
        self.yosys_json = yosys_json

    def get_comb_arcs(self) -> set[tuple[str, str]]:
        """Return this BEL's combinational input->output arcs in BEL-local names.

        The parsed netlist (`yosys_json`) already carries the BEL's instantiated
        primitives resolved against the fabric models_pack, so the sub-cell
        directions and sequential-ness are read straight from it; no arguments
        are needed.

        Returns
        -------
        set[tuple[str, str]]
            Combinational `(input_port, output_port)` arcs in BEL-local names.

        Raises
        ------
        InvalidState
            The BEL has no parsed netlist, or its module is missing from it.
        """
        if self.yosys_json is None:
            raise InvalidState(
                f"BEL {self.name} has no parsed netlist (yosys_json); cannot "
                f"extract combinational arcs."
            )
        module = self.yosys_json.modules.get(self.module_name)
        if module is None:
            raise InvalidState(
                f"Module {self.module_name} not found in the parsed netlist of "
                f"BEL {self.name}."
            )

        return _comb_arcs_from_module(module, self.yosys_json.modules)

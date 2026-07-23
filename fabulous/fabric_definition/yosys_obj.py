"""Object representation of the Yosys Json file."""

import json
import re
from dataclasses import dataclass, field
from functools import cached_property
from itertools import product
from pathlib import Path
from typing import Any, Literal

import networkx as nx
from loguru import logger

from fabulous.custom_exception import InvalidFileType, InvalidState
from fabulous.fabulous_settings import get_context
from fabulous.tools.ghdl import GhdlTool
from fabulous.tools.yosys import YosysTool

"""
Type alias for Yosys bit vectors containing integers or logic values.

BitVector represents signal values in Yosys netlists as lists containing
integers (for signal IDs) or logic state strings ("0", "1", "x", "z").
"""
BitVector = list[int | Literal["0", "1", "x", "z"]]
KeyValue = dict[str, str | int]

# Yosys cell types whose internal input->output path is broken by a register,
# latch, or memory and therefore is NOT a combinational timing arc. This mirrors
# Yosys's own stateful-primitive naming; write_json emits no sequential flag, so
# the taxonomy has to be enumerated somewhere and this is its single home.
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


@dataclass
class YosysPortDetails:
    """Represents port details in a Yosys module.

    Attributes
    ----------
    direction : Literal["input", "output", "inout"]
        Port direction.
    bits : BitVector
        Bit vector representing the port's signals.
    offset : int
        Bit offset for multi-bit ports.
    upto : int
        Upper bound for bit ranges.
    signed : int
        Whether the port is signed (0=unsigned, 1=signed).
    """

    direction: Literal["input", "output", "inout"]
    bits: BitVector
    offset: int = 0
    upto: int = 0
    signed: int = 0


@dataclass
class YosysCellDetails:
    """Represents a cell instance in a Yosys module.

    Cells are instantiated components like logic gates, flip-flops, or
    user-defined modules.

    Attributes
    ----------
    hide_name : Literal[1, 0]
        Whether to hide the cell name in output (1=hide, 0=show).
    type : str
        Cell type/primitive name (e.g., "AND", "DFF", custom module name).
    parameters : KeyValue
        Cell parameters as string key-value pairs.
    attributes : KeyValue
        Cell attributes including metadata and synthesis directives.
    connections : dict[str, BitVector]
        Port connections mapping port names to bit vectors.
    port_directions : dict[str, Literal["input", "output", "inout"]], optional
        Direction of each port. Default is empty dict.
    model : str, optional
        Associated model name. Default is "".
    module_reference : YosysModule | None
        The module this cell instantiates, or None for a leaf primitive or an
        unresolved blackbox. A cell references its type by name only, so the
        owning netlist resolves this link once every module exists. Default is
        None.
    """

    hide_name: Literal[1, 0]
    type: str
    parameters: KeyValue
    attributes: KeyValue
    connections: dict[str, BitVector]
    port_directions: dict[str, Literal["input", "output", "inout"]] = field(
        default_factory=dict
    )
    model: str = ""
    module_reference: "YosysModule | None" = field(
        default=None, compare=False, repr=False
    )

    @property
    def is_register_primitive(self) -> bool:
        """Whether this cell is a Yosys register, latch, or memory primitive.

        Returns
        -------
        bool
            True if the cell's `type` matches a known stateful Yosys primitive.
        """
        return self.type.startswith(REGISTER_CELL_PREFIXES)

    @cached_property
    def is_sequential(self) -> bool:
        """Whether this cell breaks the combinational path with a register.

        True when the cell is a stateful primitive itself, or when it
        instantiates a submodule that holds state anywhere in its hierarchy. The
        cell owns its resolved `submodule` link, so it answers this without the
        netlist. Cached, since the netlist never changes after parsing.

        Returns
        -------
        bool
            True if the cell holds state (register, latch, or memory).
        """
        if self.is_register_primitive:
            return True
        return self.module_reference is not None and self.module_reference.is_sequential

    def port_bits(self, direction: Literal["input", "output", "inout"]) -> list[int]:
        """Return the integer net bits wired to ports of the given direction.

        Parameters
        ----------
        direction : Literal["input", "output", "inout"]
            Port direction to select.

        Returns
        -------
        list[int]
            Net bit ids on the cell's ports of that direction.
        """
        return [
            bit
            for port, bits in self.connections.items()
            if self.port_directions.get(port) == direction
            for bit in bits
            if isinstance(bit, int)
        ]


@dataclass
class YosysMemoryDetails:
    """Represents memory block details in a Yosys module.

    Memory blocks are inferred or explicitly instantiated memory elements.

    Attributes
    ----------
    hide_name : Literal[1, 0]
        Whether to hide the memory name in output (1=hide, 0=show).
    attributes : KeyValue
        Memory attributes and metadata.
    width : int
        Data width in bits.
    start_offset : int
        Starting address offset.
    size : int
        Memory size (number of addressable locations).
    """

    hide_name: Literal[1, 0]
    attributes: KeyValue
    width: int
    start_offset: int
    size: int


@dataclass
class YosysNetDetails:
    """Represents net/wire details in a Yosys module.

    Nets are the connections between cells and ports in the design.

    Attributes
    ----------
    hide_name : Literal[1, 0]
        Whether to hide the net name in output (1=hide, 0=show).
    bits : BitVector
        Bit vector representing the net's signals.
    attributes : KeyValue
        Net attributes including unused bit information.
    offset : int
        Bit offset for multi-bit nets.
    upto : int
        Upper bound for bit ranges.
    signed : int
        Whether the net is signed (0=unsigned, 1=signed).
    """

    hide_name: Literal[1, 0]
    bits: BitVector
    attributes: KeyValue
    offset: int = 0
    upto: int = 0
    signed: int = 0


@dataclass
class YosysModule:
    """Represents a module in a Yosys design.

    A module contains the structural description of a digital circuit including
    its interface (ports), internal components (cells), memory blocks, and
    interconnections (nets).

    Parameters
    ----------
    attributes : KeyValue
        Module attributes dictionary.
    parameter_default_values : KeyValue
        Parameter defaults dictionary.
    ports : dict[str, YosysPortDetails]
        Ports dictionary (will be converted to YosysPortDetails objects).
    cells : dict[str, YosysCellDetails]
        Cells dictionary (will be converted to YosysCellDetails objects).
    memories : dict[str, YosysMemoryDetails]
        Memories dictionary (will be converted to YosysMemoryDetails objects).
    netnames : dict[str, YosysNetDetails]
        Netnames dictionary (will be converted to YosysNetDetails objects).

    Attributes
    ----------
    attributes : KeyValue
        Module attributes and metadata (e.g., "top" for top module).
    parameter_default_values : KeyValue
        Default values for module parameters.
    ports : dict[str, YosysPortDetails]
        Dictionary mapping port names to YosysPortDetails.
    cells : dict[str, YosysCellDetails]
        Dictionary mapping cell names to YosysCellDetails.
    memories : dict[str, YosysMemoryDetails]
        Dictionary mapping memory names to YosysMemoryDetails.
    netnames : dict[str, YosysNetDetails]
        Dictionary mapping net names to YosysNetDetails.
    """

    attributes: KeyValue
    parameter_default_values: KeyValue
    ports: dict[str, YosysPortDetails]
    cells: dict[str, YosysCellDetails]
    memories: dict[str, YosysMemoryDetails]
    netnames: dict[str, YosysNetDetails]

    def __init__(
        self,
        *,
        attributes: KeyValue,
        parameter_default_values: KeyValue,
        ports: dict[str, YosysPortDetails],
        cells: dict[str, YosysCellDetails],
        memories: dict[str, YosysMemoryDetails],
        netnames: dict[str, YosysNetDetails],
    ) -> None:
        self.attributes = attributes
        self.parameter_default_values = parameter_default_values
        self.ports = {k: YosysPortDetails(**v) for k, v in ports.items()}
        self.cells = {k: YosysCellDetails(**v) for k, v in cells.items()}
        self.memories = {k: YosysMemoryDetails(**v) for k, v in memories.items()}
        self.netnames = {k: YosysNetDetails(**v) for k, v in netnames.items()}

    @cached_property
    def is_sequential(self) -> bool:
        """Whether this module contains a register anywhere in its hierarchy.

        Traverses its own cells, following each cell's resolved `submodule` link
        into the sub-hierarchy. The netlist is not flattened, so a register can
        be nested several submodules deep. The module structure never changes
        after parsing, so the result is cached on first access.

        Returns
        -------
        bool
            True if any cell, transitively, is a register, latch, or memory
            primitive.
        """
        return any(cell.is_sequential for cell in self.cells.values())


@dataclass
class YosysJson:
    """Root object representing a complete Yosys JSON file.

    Load and parse a HDL file to a Yosys JSON object.

    This class provides the main interface for loading and analyzing Yosys JSON
    netlists. It contains all modules in the design and provides utility methods
    for common netlist analysis tasks.

    Parameters
    ----------
    path : Path
        Path to a HDL file.
    run_hierarchy : bool
        Whether to run `hierarchy -auto-top`, which prunes modules unreachable
        from the chosen top. Set to `False` to keep every module of a
        multi-module library (e.g. a primitive pack). Default is `True`.

    Attributes
    ----------
    srcPath : Path
        Path to the source JSON file.
    creator : str
        Tool that created the JSON (usually "Yosys").
    modules : dict[str, YosysModule]
        Dictionary mapping module names to YosysModule objects.
    models : dict
        Dictionary of behavioral models (implementation-specific).

    Raises
    ------
    FileNotFoundError
        If the JSON file doesn't exist.
    InvalidFileType
        If the file type is not .vhd, .vhdl, .v, or .sv.
    ValueError
        If there is a miss match in the VHDL entity and the Yosys top module.
    """

    srcPath: Path
    creator: str
    modules: dict[str, YosysModule]
    models: dict

    def __init__(self, path: Path, run_hierarchy: bool = True) -> None:
        if not path.exists():
            raise FileNotFoundError(f"File {path} does not exist")
        if path.suffix not in {".vhd", ".vhdl", ".v", ".sv"}:
            raise InvalidFileType(
                f"Unsupported HDL file type: {path.suffix}. "
                f"Supported types are .vhd, .vhdl, .v, .sv"
            )

        self.srcPath = path.absolute()
        json_file = self.srcPath.with_suffix(".json")

        # VHDL is elaborated to Verilog by GHDL first; Verilog/SystemVerilog is
        # read by Yosys directly.
        if self.srcPath.suffix in {".vhd", ".vhdl"}:
            verilog = GhdlTool.synthesize_to_verilog(
                self.srcPath, get_context().models_pack
            )
            yosys_src = self.srcPath.with_suffix(".v")
            yosys_src.write_text(verilog)
            # GHDL already fed models_pack in as a source, so the emitted Verilog
            # is self-contained; the Yosys pass below must not augment it again.
            convert_models_pack = None
        else:
            yosys_src = self.srcPath
            # Resolve the source's instantiated fabric primitives against
            # models_pack so the parsed netlist is self-contained for arc
            # analysis. models_pack is one per-project file keyed to proj_lang,
            # so it is always same-language with the source here; skip it when
            # parsing models_pack itself or when hierarchy pruning is disabled.
            models_pack = get_context().models_pack
            if (
                run_hierarchy
                and models_pack is not None
                and models_pack != self.srcPath
            ):
                convert_models_pack = models_pack
            else:
                convert_models_pack = None
        YosysTool.convert_to_json(
            yosys_src,
            json_file,
            models_pack=convert_models_pack,
            run_hierarchy=run_hierarchy,
        )
        with json_file.open() as f:
            o = json.load(f)
        self.creator = o.get("creator", "")  # Use .get() for safety
        # Provide default empty dicts for potentially missing keys in module data
        self.modules = {
            k: YosysModule(
                attributes=v.get("attributes", {}),
                parameter_default_values=v.get("parameter_default_values", {}),
                ports=v.get("ports", {}),
                cells=v.get("cells", {}),
                memories=v.get("memories", {}),  # Provide default for memories
                netnames=v.get("netnames", {}),  # Provide default for netnames
            )
            for k, v in o.get("modules", {}).items()  # Use .get() for safety
        }
        for module in self.modules.values():
            for cell in module.cells.values():
                cell.module_reference = self.modules.get(cell.type)

        self.models = o.get("models", {})  # Use .get() for safety

        # Post-process VHDL file for now. Once VHDL is updated, we can remove this.
        if self.srcPath.suffix in [".vhd", ".vhdl"]:
            vhdl_content = self.srcPath.read_text()

            if r := re.search(r"entity\s+(\w+)\s+is", vhdl_content):
                module_name = r.group(1)
            else:
                raise ValueError(f"Could not find entity name in {self.srcPath}")

            module = self.modules.get(module_name)
            if not module:
                raise ValueError(
                    f"Module {module_name} not found in Yosys JSON for {self.srcPath}"
                )

            if r := re.search(r"\(\*.*?BelMap(.*?) \*\)", vhdl_content):
                res = r.group(1).split(",")
                res = [x.strip() for x in res]
                res = [x for x in res if x]  # Remove empty strings
                res = dict(x.split("=", 1) for x in res)
                # FIXME: This is a workaround for the VHDL parser until GHDL
                # fixes the issue that all attributes are converted to lowercase.
                # https://github.com/ghdl/ghdl/issues/3067
                _update_dict_ignore_case(module.attributes, res)
                _update_dict_ignore_case(
                    module.attributes, {"BelMap": True, "FABulous": True}
                )

            # because yosys reverses the order of attributes, we need to do the same
            module.attributes = dict(reversed(list(module.attributes.items())))

            ports_entry = []
            port_start = False
            for i in vhdl_content.splitlines():
                if re.search(r"^\s*port \(", i, flags=re.IGNORECASE):
                    port_start = True
                if port_start and re.search(r"^\s*\);\s*", i):
                    port_start = False
                if port_start:
                    ports_entry.append(i)

            for p in ports_entry:
                if r := re.search(r"(\w+)\s*:.*? --\s*\(\* (.*?) \*\)", p):
                    port_name = r.group(1)
                    attribute_entries = r.group(2).split(",")
                    module.netnames[port_name].attributes.update(
                        {x.strip(): 1 for x in attribute_entries}
                    )
                if r := re.search(r"(\w+)\s*:.*? --.*", p):
                    port_name = r.group(1)

                    if "EXTERNAL" in p:
                        module.netnames[port_name].attributes["EXTERNAL"] = 1
                    if "SHARED_PORT" in p:
                        module.netnames[port_name].attributes["SHARED_PORT"] = 1
                    if "GLOBAL" in p:
                        module.netnames[port_name].attributes["GLOBAL"] = 1

    def getTopModule(self) -> tuple[str, YosysModule]:
        """Find and return the top-level module in the design.

        The top module is identified by having a "top" attribute. If no "top"
        module is found, falls back to the first module with a "blackbox"
        attribute (e.g. for BEL definitions that only contain a blackbox module).

        Returns
        -------
        tuple[str, YosysModule]
            A tuple containing:
            - The name of the top-level module (str)
            - The YosysModule object for the top-level module

        Raises
        ------
        ValueError
            If no top or blackbox module is found in the design.
        """
        for name, module in self.modules.items():
            if "top" in module.attributes:
                return name, module
        for name, module in self.modules.items():
            if "blackbox" in module.attributes:
                logger.info(f"No top module found, using blackbox module '{name}'")
                return name, module
        raise ValueError("No top module found in Yosys JSON")

    def isTopModuleNet(self, net: int) -> bool:
        """Check if a net ID corresponds to a top-level module port.

        Parameters
        ----------
        net : int
            Net ID to check.

        Returns
        -------
        bool
            True if the net is connected to a top module port, False otherwise.
        """
        for module in self.modules.values():
            for pDetail in module.ports.values():
                if net in pDetail.bits:
                    return True
        return False

    def getNetPortSrcSinks(
        self, net: int
    ) -> tuple[tuple[str, str], list[tuple[str, str]]]:
        """Find the source and sink connections for a given net.

        This method analyzes the netlist to determine what drives a net (source)
        and what it connects to (sinks).

        Parameters
        ----------
        net : int
            Net ID to analyze.

        Returns
        -------
        tuple[tuple[str, str], list[tuple[str, str]]]
            A tuple containing:
            - Source: (cell_name, port_name) tuple for the driving cell/port
            - Sinks: List of (cell_name, port_name) tuples for driven cells/ports

        Raises
        ------
        ValueError
            If net is not found or has multiple drivers.

        Notes
        -----
        If no driver is found, the source will be ("", "z") indicating
        a high-impedance or undriven net.
        """
        src: list[tuple[str, str]] = []
        sinks: list[tuple[str, str]] = []
        for module in self.modules.values():
            for cell_name, cell_details in module.cells.items():
                for conn_name, conn_details in cell_details.connections.items():
                    if net in conn_details:
                        if cell_details.port_directions[conn_name] == "output":
                            src.append((cell_name, conn_name))
                        else:
                            sinks.append((cell_name, conn_name))

        if len(sinks) == 0:
            raise ValueError(
                f"Net {net} not found in Yosys JSON or is a top module port output"
            )

        if len(src) == 0:
            src.append(("", "z"))

        if len(src) > 1:
            raise ValueError(f"Multiple driver found for net {net}: {src}")

        return src[0], sinks

    def comb_arcs(self, module_name: str) -> set[tuple[str, str]]:
        """Extract combinational input->output port arcs from a module.

        Each combinational cell is modelled as a full input-bit -> output-bit
        crossbar, so a path through chained cells becomes a path in the net-bit
        graph. Sequential cells are skipped, so their input and output cones stay
        disconnected and no false arc runs through a register.

        Parameters
        ----------
        module_name : str
            Name of the module in this netlist to analyse.

        Returns
        -------
        set[tuple[str, str]]
            Combinational `(input_port, output_port)` arcs in module-local names.

        Raises
        ------
        InvalidState
            If `module_name` is not present in this netlist.
        """
        module = self.modules.get(module_name)
        if module is None:
            raise InvalidState(
                f"Module {module_name} not found in the parsed netlist {self.srcPath}."
            )

        graph = nx.DiGraph()
        for cell in module.cells.values():
            if not cell.port_directions or cell.is_sequential:
                continue
            graph.add_edges_from(
                product(cell.port_bits("input"), cell.port_bits("output"))
            )

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
            if in_bit not in graph:
                continue
            for out_bit in nx.descendants(graph, in_bit) & output_name.keys():
                arcs.add((in_port, output_name[out_bit]))
        return arcs


def _update_dict_ignore_case(
    original: dict[str, Any], updates: dict[str, Any]
) -> dict[str, Any]:
    """Update a dictionary with another dictionary, ignoring key case.

    Parameters
    ----------
    original : dict[str, Any]
        The original dictionary to be updated.
    updates : dict[str, Any]
        The dictionary containing updates.

    Returns
    -------
    dict[str, Any]
        The updated dictionary with keys from `updates` applied to `original`,
        ignoring case differences.
    """
    lower_original = {k.lower(): k for k in original}

    for key, value in updates.items():
        lower_key = key.lower()
        if lower_key in lower_original:
            # overwrite existing key (case-insensitive)
            original.pop(lower_original[lower_key])
        original[key] = value

    return original

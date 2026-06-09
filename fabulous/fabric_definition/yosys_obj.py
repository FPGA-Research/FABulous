"""Object representation of the Yosys Json file."""

import functools
import json
import re
from collections.abc import Iterator
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal, NamedTuple, Self

from loguru import logger

from fabulous.custom_exception import InvalidFileType
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

    def bit_names(self, name: str) -> list[str]:
        """Bit-blasted node names for this port.

        A single-bit scalar port yields ``[name]``; a multi-bit bus yields
        ``name[offset + i]`` for each bit, matching the bit-blasted node names
        used elsewhere (e.g. a timing graph built from the same netlist).

        Parameters
        ----------
        name : str
            The port name (the key under which this port is stored).

        Returns
        -------
        list[str]
            Node names for each bit of the port, in declaration order.
        """
        if len(self.bits) == 1 and self.offset == 0:
            return [name]
        return [f"{name}[{self.offset + i}]" for i in range(len(self.bits))]


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

    def port_names(self, direction: Literal["input", "output", "inout"]) -> list[str]:
        """Bit-blasted port node names filtered by direction.

        Parameters
        ----------
        direction : Literal["input", "output", "inout"]
            Port direction to select.

        Returns
        -------
        list[str]
            Bit-blasted node names of every port with the given direction, in
            declaration order.
        """
        names: list[str] = []
        for name, port in self.ports.items():
            if port.direction == direction:
                names.extend(port.bit_names(name))
        return names

    @functools.cached_property
    def bit_to_net(self) -> dict[int, str]:
        """Map each net-id bit to its readable net name.

        Single-bit scalar wires map to the bare name; bus bits map to
        ``name[offset + i]``. Named wires (``hide_name == 0``) win over
        Yosys-generated names so the result matches the source netlist.

        Returns
        -------
        dict[int, str]
            Mapping from net-id to net name.
        """
        bit_to_net: dict[int, str] = {}
        for prefer_named in (True, False):
            for name, net in self.netnames.items():
                if (net.hide_name == 0) != prefer_named:
                    continue
                if len(net.bits) == 1 and net.offset == 0:
                    bit = net.bits[0]
                    if isinstance(bit, int):
                        bit_to_net.setdefault(bit, name)
                    continue
                for i, bit in enumerate(net.bits):
                    if isinstance(bit, int):
                        bit_to_net.setdefault(bit, f"{name}[{net.offset + i}]")
        return bit_to_net

    def pin_nets(self, cell_name: str) -> dict[str, list[str]]:
        """Map each pin of a cell to the net name of each of its bits.

        Resolves the cell's connection bit vectors against this module's
        bit-to-net map, returning one net name per bit in connection order. A
        single-bit pin yields a one-element list; a bus yields one entry per
        bit. Constant logic bits become ``1'b<value>`` and bits with no named
        net fall back to ``$net<id>``.

        Returning a list per pin (rather than collapsing a bus into a single
        ``{a,b,...}`` string) keeps the per-bit net names individually
        comparable, so callers that match nets never have to parse a packed
        string.

        Parameters
        ----------
        cell_name : str
            Name of the cell instance within this module.

        Returns
        -------
        dict[str, list[str]]
            Mapping from pin name to the net name of each of its bits, in bit
            order.
        """
        bit_to_net = self.bit_to_net
        result: dict[str, list[str]] = {}
        for pin, bits in self.cells[cell_name].connections.items():
            nets: list[str] = []
            for bit in bits:
                if isinstance(bit, int):
                    nets.append(bit_to_net.get(bit, f"$net{bit}"))
                else:
                    nets.append(f"1'b{bit}")
            result[pin] = nets
        return result


class InstanceRef(NamedTuple):
    """A single instance located in the module hierarchy.

    Yielded by :meth:`YosysJson.walk_instances` for every instance encountered
    while walking the hierarchy.

    Attributes
    ----------
    path : str
        Hierarchical instance path (without the top module name).
    module : YosysModule
        The parent module that directly contains this instance.
    module_name : str
        Name (type) of that parent module.
    inst_name : str
        The instance (cell) name within the parent module.
    cell : YosysCellDetails
        The cell details for this instance.
    """

    path: str
    module: YosysModule
    module_name: str
    inst_name: str
    cell: YosysCellDetails

    def pin_nets(self) -> dict[str, list[str]]:
        """Pin-to-net mapping for this instance.

        Returns
        -------
        dict[str, list[str]]
            Mapping from pin name to the net name of each of its bits (see
            :meth:`YosysModule.pin_nets`).
        """
        return self.module.pin_nets(self.inst_name)


@dataclass
class YosysJson:
    """Root object representing a complete Yosys JSON file.

    Load and parse a HDL file to a Yosys JSON object.

    This class provides the main interface for loading and analyzing Yosys JSON
    netlists. It contains all modules in the design and provides utility methods
    for common netlist analysis tasks, including hierarchy navigation (finding
    modules and instances, resolving hierarchical pins, mapping instance pins to
    nets). Hierarchy walks start from ``top_name`` and join path segments with
    ``hier_sep``.

    Parameters
    ----------
    path : Path
        Path to a HDL file.
    top_name : str | None, optional
        Name of the top-level module to start hierarchy walks from. When None
        (the default) it is resolved lazily from the netlist via
        :meth:`getTopModule`.
    hier_sep : str, optional
        Separator used to join and split hierarchical instance/pin paths
        (default ``/``, the Yosys convention). The SDF-driven timing flow passes
        the divider declared in the SDF header.

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
    hier_sep : str
        Separator for hierarchical instance/pin paths.

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
    hier_sep: str = "/"

    def __init__(
        self, path: Path, top_name: str | None = None, hier_sep: str = "/"
    ) -> None:
        if not path.exists():
            raise FileNotFoundError(f"File {path} does not exist")
        if path.suffix not in {".vhd", ".vhdl", ".v", ".sv"}:
            raise InvalidFileType(
                f"Unsupported HDL file type: {path.suffix}. "
                f"Supported types are .vhd, .vhdl, .v, .sv"
            )

        self.srcPath = path.absolute()
        self.hier_sep = hier_sep
        # An explicit name shadows the lazy ``top_name`` cached_property; leaving
        # it unset defers resolution to getTopModule() on first access.
        if top_name is not None:
            self.top_name = top_name
        json_file = self.srcPath.with_suffix(".json")

        # VHDL files are converted to Verilog by GHDL, so use .v suffix for yosys
        # Verilog/SystemVerilog files use their original suffix
        if self.srcPath.suffix in {".vhd", ".vhdl"}:
            verilog = GhdlTool.synthesize_to_verilog(
                self.srcPath, get_context().models_pack
            )
            yosys_src = self.srcPath.with_suffix(".v")
            yosys_src.write_text(verilog)
        else:
            yosys_src = self.srcPath

        YosysTool.convert_to_json(yosys_src, json_file)
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

    @classmethod
    def from_modules(
        cls,
        modules: dict[str, YosysModule],
        top_name: str | None = None,
        hier_sep: str = "/",
    ) -> Self:
        """Build a YosysJson from already-parsed modules, bypassing Yosys.

        Use this when the modules are available without a source file (for
        example loaded from a committed JSON fixture), so the netlist-query API
        can be exercised without invoking Yosys.

        Parameters
        ----------
        modules : dict[str, YosysModule]
            The parsed modules keyed by module name.
        top_name : str | None, optional
            Name of the top-level module. When None it is resolved lazily via
            :meth:`getTopModule`.
        hier_sep : str, optional
            Separator for hierarchical instance/pin paths (default ``/``).

        Returns
        -------
        Self
            A YosysJson backed by the given modules.
        """
        obj = cls.__new__(cls)
        obj.srcPath = None
        obj.creator = ""
        obj.modules = modules
        obj.models = {}
        obj.hier_sep = hier_sep
        if top_name is not None:
            obj.top_name = top_name
        return obj

    @functools.cached_property
    def top_name(self) -> str:
        """Name of the top-level module hierarchy walks start from.

        Resolved from the netlist via :meth:`getTopModule`. An explicit name
        passed at construction is stored as an instance attribute that shadows
        this property.

        Returns
        -------
        str
            The top-level module name.
        """
        return self.getTopModule()[0]

    @property
    def input_ports(self) -> list[str]:
        """Bit-blasted input port node names of the top module.

        Returns
        -------
        list[str]
            Input port node names, in declaration order.
        """
        return self.modules[self.top_name].port_names("input")

    @property
    def output_ports(self) -> list[str]:
        """Bit-blasted output port node names of the top module.

        Returns
        -------
        list[str]
            Output port node names, in declaration order.
        """
        return self.modules[self.top_name].port_names("output")

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

    def find_verilog_modules_regex(self, name_pattern: str) -> list[str]:
        """Find Verilog module names matching a regex pattern.

        Parameters
        ----------
        name_pattern : str
            Regular expression pattern to match module names.

        Returns
        -------
        list[str]
            List of module names matching the regex pattern.
        """
        name_re = re.compile(name_pattern)
        return [name for name in self.modules if name_re.search(name)]

    def walk_instances(
        self, module_name: str | None = None, prefix: str = ""
    ) -> Iterator[InstanceRef]:
        """Depth-first walk of the instance hierarchy.

        Yield an `InstanceRef` for every instance reachable from
        `module_name` (defaulting to the top module), descending into submodule
        instances. Std-cell (leaf) instances are yielded but not descended into.
        Each instance is yielded before its own children (pre-order).

        Parameters
        ----------
        module_name : str | None, optional
            Module to start the walk from. Defaults to the top module.
        prefix : str, optional
            Hierarchical path prefix accumulated during recursion.

        Yields
        ------
        InstanceRef
            One reference per instance, depth-first in declaration order.
        """
        name = module_name if module_name is not None else self.top_name
        module = self.modules.get(name)
        if module is None:
            return
        for inst_name, cell in module.cells.items():
            path = f"{prefix}{self.hier_sep}{inst_name}" if prefix else inst_name
            yield InstanceRef(path, module, name, inst_name, cell)
            if cell.type in self.modules:
                yield from self.walk_instances(cell.type, path)

    def find_instances_by_regex(
        self, inst_regex: str, filter_regex: str | None = None
    ) -> list[InstanceRef]:
        """Find instances whose hierarchical path matches a regex.

        Walk the hierarchy from `top_name` and return an `InstanceRef`
        for every instance whose path (without the top module name) matches
        `inst_regex`, optionally narrowed by `filter_regex`.

        Parameters
        ----------
        inst_regex : str
            Regular expression to match hierarchical instance paths.
        filter_regex : str | None
            Optional regular expression to further filter the matched paths.

        Returns
        -------
        list[InstanceRef]
            One reference per matching instance.
        """
        pattern = re.compile(inst_regex)
        filter_pattern = re.compile(filter_regex) if filter_regex is not None else None
        return [
            ref
            for ref in self.walk_instances()
            if pattern.search(ref.path)
            and (filter_pattern is None or filter_pattern.search(ref.path))
        ]

    def net_to_pin_paths_for_instance_resolved(
        self, instance: InstanceRef
    ) -> dict[str, list[str]]:
        """Map each net on an instance to its resolved leaf pin paths.

        For every net connected to one of the instance's pins, collect the leaf
        std-cell pin paths that net reaches inside the instance's subtree. A pin
        on a leaf std-cell instance resolves to itself; a pin on a submodule
        instance is followed through the hierarchy (a submodule port name becomes
        the net name inside that submodule) down to every leaf std-cell pin it is
        wired to, fanning out to several leaf pins when the net branches.

        The instance is taken as-is, so its `path` must be relative to the top
        module (as produced by `walk_instances` / `find_instances_by_regex`).

        Parameters
        ----------
        instance : InstanceRef
            The instance to resolve, as yielded by `walk_instances` or returned
            by `find_instances_by_regex`.

        Returns
        -------
        dict[str, list[str]]
            Mapping from net names to lists of resolved leaf pin paths.
        """
        sep = self.hier_sep

        def leaf_pins(
            module_name: str, net_name: str, prefix: str, visited: set
        ) -> list[str]:
            """Collect leaf pins in `module_name` wired to `net_name`."""
            key = (module_name, net_name, prefix)
            if key in visited:
                return []
            visited.add(key)
            module = self.modules.get(module_name)
            if module is None:
                return []
            pins: list[str] = []
            for inst_name, cell in module.cells.items():
                for pin, nets in module.pin_nets(inst_name).items():
                    if net_name not in nets:
                        continue
                    child_prefix = f"{prefix}{sep}{inst_name}"
                    if cell.type in self.modules:
                        pins.extend(leaf_pins(cell.type, pin, child_prefix, visited))
                    else:
                        pins.append(f"{child_prefix}{sep}{pin}")
            return pins

        result: dict[str, list[str]] = {}
        for pin, nets in instance.pin_nets().items():
            for net in nets:
                # A net can appear on more than one pin of the instance, so
                # accumulate rather than overwrite to avoid losing a pin's
                # resolved leaf paths.
                if instance.cell.type in self.modules:
                    result.setdefault(net, []).extend(
                        leaf_pins(instance.cell.type, pin, instance.path, set())
                    )
                else:
                    # The instance is itself a leaf std-cell: the pin is the endpoint.
                    result.setdefault(net, []).append(f"{instance.path}{sep}{pin}")
        return result


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

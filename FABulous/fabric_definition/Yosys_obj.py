"""Object representation of the Yosys Json file."""

import json
import re
import subprocess
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal

from FABulous.custom_exception import InvalidFileType
from FABulous.FABulous_settings import get_context

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
    RuntimeError
        If Yosys or GHDL fails to process the file.
    ValueError
        If there is a miss match in the VHDL entity and the Yosys top module.
    """

    srcPath: Path
    creator: str
    modules: dict[str, YosysModule]
    models: dict

    def __init__(self, path: Path) -> None:
        if not path.exists():
            raise FileNotFoundError(f"File {path} does not exist")
        if path.suffix not in {".vhd", ".vhdl", ".v", ".sv"}:
            raise InvalidFileType(
                f"Unsupported HDL file type: {path.suffix}. "
                f"Supported types are .vhd, .vhdl, .v, .sv"
            )

        self.srcPath = path.absolute()
        yosys = get_context().yosys_path
        ghdl = get_context().ghdl_path
        json_file = self.srcPath.with_suffix(".json")

        # FIXME: a fake file to ensure things working with 1.3
        temp: Path = Path(tempfile.gettempdir())
        temp = temp / "my_package.vhd"
        temp.touch()
        temp.write_text("package my_package is\nend package;\n")
        if self.srcPath.suffix in {".vhd", ".vhdl"}:
            runCmd = [
                f"{ghdl!s}",
                "--synth",
                "--std=08",
                "--out=verilog",
                str(temp),
                f"{get_context().models_pack!s}",
                f"{self.srcPath}",
                "-e",
                f"{self.srcPath.stem}",
            ]
            try:
                r = subprocess.run(runCmd, check=True, capture_output=True)
                self.srcPath.with_suffix(".v").write_text(r.stdout.decode())
            except subprocess.CalledProcessError as e:
                raise RuntimeError(
                    f"Failed to run GHDL on {self.srcPath}: {e.stderr.decode()} "
                    f"run cmd: {' '.join(runCmd)}"
                ) from e
        runCmd = [
            f"{yosys!s}",
            "-q",
            (
                "-p "
                f"read_verilog -sv {self.srcPath.with_suffix('.v')}; "
                "hierarchy -auto-top; "
                "proc -noopt; "
                f"write_json -compat-int {json_file}"
            ),
        ]
        try:
            subprocess.run(runCmd, check=True, capture_output=True)
        except subprocess.CalledProcessError as e:
            raise RuntimeError(
                f"Failed to run Yosys on {self.srcPath}: {e.stderr.decode()}"
            ) from e
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

    def getTopModule(self) -> tuple[str, YosysModule]:
        """Find and return the top-level module in the design.

        The top module is identified by having a "top" attribute.

        Returns
        -------
        tuple[str, YosysModule]
            A tuple containing:
            - The name of the top-level module (str)
            - The YosysModule object for the top-level module

        Raises
        ------
        ValueError
            If no top module is found in the design.
        """
        for name, module in self.modules.items():
            if "top" in module.attributes:
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

import json
import os
import re
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

from loguru import logger

from FABulous.FABulous_CLI.helper import check_if_application_exists

"""
Type alias for Yosys bit vectors containing integers or logic values.

BitVector represents signal values in Yosys netlists as lists containing
integers (for signal IDs) or logic state strings ("0", "1", "x", "z").
"""
BitVector = list[int | Literal["0", "1", "x", "z"]]


@dataclass
class YosysPortDetails:
    """
    Represents port details in a Yosys module.

    Attributes
    ----------
    direction : {"input", "output", "inout"}
        Port direction.
    bits : BitVector
        Bit vector representing the port's signals.
    offset : int, default 0
        Bit offset for multi-bit ports.
    upto : int, default 0
        Upper bound for bit ranges.
    signed : int, default 0
        Whether the port is signed (0=unsigned, 1=signed).
    """

    direction: Literal["input", "output", "inout"]
    bits: BitVector
    offset: int = 0
    upto: int = 0
    signed: int = 0


@dataclass
class YosysCellDetails:
    """
    Represents a cell instance in a Yosys module.

    Cells are instantiated components like logic gates, flip-flops, or
    user-defined modules.

    Attributes
    ----------
    hide_name : {0, 1}
        Whether to hide the cell name in output (1=hide, 0=show).
    type : str
        Cell type/primitive name (e.g., "AND", "DFF", custom module name).
    parameters : dict[str, str]
        Cell parameters as string key-value pairs.
    attributes : dict[str, str | int]
        Cell attributes including metadata and synthesis directives.
    connections : dict[str, BitVector]
        Port connections mapping port names to bit vectors.
    port_directions : dict[str, {"input", "output", "inout"}], optional
        Direction of each port. Default is empty dict.
    model : str, optional
        Associated model name. Default is "".
    """

    hide_name: Literal[1, 0]
    type: str
    parameters: dict[str, str]
    attributes: dict[str, str | int]
    connections: dict[str, BitVector]
    port_directions: dict[str, Literal["input", "output", "inout"]] = field(default_factory=dict)
    model: str = ""


@dataclass
class YosysMemoryDetails:
    """
    Represents memory block details in a Yosys module.

    Memory blocks are inferred or explicitly instantiated memory elements.

    Attributes
    ----------
    hide_name : {0, 1}
        Whether to hide the memory name in output (1=hide, 0=show).
    attributes : dict[str, str]
        Memory attributes and metadata.
    width : int
        Data width in bits.
    start_offset : int
        Starting address offset.
    size : int
        Memory size (number of addressable locations).
    """

    hide_name: Literal[1, 0]
    attributes: dict[str, str]
    width: int
    start_offset: int
    size: int


@dataclass
class YosysNetDetails:
    """
    Represents net/wire details in a Yosys module.

    Nets are the connections between cells and ports in the design.

    Attributes
    ----------
    hide_name : {0, 1}
        Whether to hide the net name in output (1=hide, 0=show).
    bits : BitVector
        Bit vector representing the net's signals.
    attributes : dict[str, str]
        Net attributes including unused bit information.
    offset : int, default 0
        Bit offset for multi-bit nets.
    upto : int, default 0
        Upper bound for bit ranges.
    signed : int, default 0
        Whether the net is signed (0=unsigned, 1=signed).
    """

    hide_name: Literal[1, 0]
    bits: BitVector
    attributes: dict[str, str]
    offset: int = 0
    upto: int = 0
    signed: int = 0


@dataclass
class YosysModule:
    """
    Represents a module in a Yosys design.

    A module contains the structural description of a digital circuit including
    its interface (ports), internal components (cells), memory blocks, and
    interconnections (nets).

    Attributes
    ----------
    attributes : dict[str, str | int]
        Module attributes and metadata (e.g., "top" for top module).
    parameter_default_values : dict[str, str | int]
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

    attributes: dict[str, str | int]
    parameter_default_values: dict[str, str | int]
    ports: dict[str, YosysPortDetails]
    cells: dict[str, YosysCellDetails]
    memories: dict[str, YosysMemoryDetails]
    netnames: dict[str, YosysNetDetails]

    def __init__(self, *, attributes, parameter_default_values, ports, cells, memories, netnames):
        """
        Initialize a YosysModule from parsed JSON data.

        Parameters
        ----------
        attributes : dict
            Module attributes dictionary.
        parameter_default_values : dict
            Parameter defaults dictionary.
        ports : dict
            Ports dictionary (will be converted to YosysPortDetails objects).
        cells : dict
            Cells dictionary (will be converted to YosysCellDetails objects).
        memories : dict
            Memories dictionary (will be converted to YosysMemoryDetails objects).
        netnames : dict
            Netnames dictionary (will be converted to YosysNetDetails objects).
        """
        self.attributes = attributes
        self.parameter_default_values = parameter_default_values
        self.ports = {k: YosysPortDetails(**v) for k, v in ports.items()}
        self.cells = {k: YosysCellDetails(**v) for k, v in cells.items()}
        self.memories = {k: YosysMemoryDetails(**v) for k, v in memories.items()}
        self.netnames = {k: YosysNetDetails(**v) for k, v in netnames.items()}


@dataclass
class YosysJson:
    """
    Root object representing a complete Yosys JSON file.

    This class provides the main interface for loading and analyzing Yosys JSON
    netlists. It contains all modules in the design and provides utility methods
    for common netlist analysis tasks.

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
    """

    srcPath: Path
    creator: str
    modules: dict[str, YosysModule]
    models: dict

    def __init__(self, path: Path):
        """
        Load and parse a HDL file to a Yosys JSON object.

        Parameters
        ----------
        path : Path
            Path to a HDL file.

        Raises
        ------
        FileNotFoundError
            If the JSON file doesn't exist.
        json.JSONDecodeError
            If the file contains invalid JSON.
        ValueError
            If the HDL file type is unsupported.
        """

        self.srcPath = path
        yosys = check_if_application_exists(os.getenv("FAB_YOSYS_PATH", "yosys"))

        json_file = self.srcPath.with_suffix(".json")

        if self.srcPath.suffix in [".v", ".sv"]:
            runCmd = [
                yosys,
                "-q",
                f"-p read_verilog -sv {self.srcPath}; proc -noopt; write_json -compat-int {json_file}",
            ]
        elif self.srcPath.suffix in [".vhd", ".vhdl"]:
            runCmd = [
                yosys,
                "-m",
                "ghdl-q",
                f"-p ghdl {self.srcPath}; proc -noopt; write_json -compat-int {json_file}",
            ]
        else:
            raise ValueError(f"Unsupported HDL file type: {self.srcPath.suffix}")
        try:
            subprocess.run(runCmd, check=True)
        except subprocess.CalledProcessError as e:
            logger.opt(exception=subprocess.CalledProcessError(1, runCmd)).error(f"Failed to run yosys command: {e}")

        with open(json_file, "r") as f:
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

    def getTopModule(self) -> YosysModule:
        """
        Find and return the top-level module in the design.

        The top module is identified by having a "top" attribute.

        Returns
        -------
        YosysModule
            The top-level module.

        Raises
        ------
        ValueError
            If no top module is found in the design.
        """
        for module in self.modules.values():
            if "top" in module.attributes:
                return module
        raise ValueError("No top module found in Yosys JSON")

    def isTopModuleNet(self, net: int) -> bool:
        """
        Check if a net ID corresponds to a top-level module port.

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


    def getNetPortSrcSinks(self, net: int) -> tuple[tuple[str, str], list[tuple[str, str]]]:
        """
        Find the source and sink connections for a given net.

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
            raise ValueError(f"Net {net} not found in Yosys JSON or is a top module port output")

        if len(src) == 0:
            src.append(("", "z"))

        if len(src) > 1:
            raise ValueError(f"Multiple driver found for net {net}: {src}")

        return src[0], sinks

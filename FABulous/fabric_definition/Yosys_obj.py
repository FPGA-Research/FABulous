import json
import os
import re
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

from loguru import logger

from FABulous.FABulous_CLI.helper import check_if_application_exists

"""Type alias for Yosys bit vectors containing integers or logic values."""
BitVector = list[int | Literal["0", "1", "x", "z"]]


@dataclass
class YosysPortDetails:
    """
    Represents port details in a Yosys module.

    Attributes:
        direction: Port direction - "input", "output", or "inout"
        bits: Bit vector representing the port's signals
        offset: Bit offset for multi-bit ports (default: 0)
        upto: Upper bound for bit ranges (default: 0)
        signed: Whether the port is signed (0=unsigned, 1=signed, default: 0)
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

    Cells are instantiated components like logic gates, flip-flops, or user-defined modules.

    Attributes:
        hide_name: Whether to hide the cell name in output (1=hide, 0=show)
        type: Cell type/primitive name (e.g., "AND", "DFF", custom module name)
        parameters: Cell parameters as string key-value pairs
        attributes: Cell attributes including metadata and synthesis directives
        connections: Port connections mapping port names to bit vectors
        port_directions: Direction of each port ("input", "output", "inout")
        model: Associated model name (optional, default: "")
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

    Attributes:
        hide_name: Whether to hide the memory name in output (1=hide, 0=show)
        attributes: Memory attributes and metadata
        width: Data width in bits
        start_offset: Starting address offset
        size: Memory size (number of addressable locations)
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

    Attributes:
        hide_name: Whether to hide the net name in output (1=hide, 0=show)
        bits: Bit vector representing the net's signals
        attributes: Net attributes including unused bit information
        offset: Bit offset for multi-bit nets (default: 0)
        upto: Upper bound for bit ranges (default: 0)
        signed: Whether the net is signed (0=unsigned, 1=signed, default: 0)
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

    Attributes:
        attributes: Module attributes and metadata (e.g., "top" for top module)
        parameter_default_values: Default values for module parameters
        ports: Dictionary mapping port names to YosysPortDetails
        cells: Dictionary mapping cell names to YosysCellDetails
        memories: Dictionary mapping memory names to YosysMemoryDetails
        netnames: Dictionary mapping net names to YosysNetDetails
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

        Args:
            attributes: Module attributes dictionary
            parameter_default_values: Parameter defaults dictionary
            ports: Ports dictionary (will be converted to YosysPortDetails objects)
            cells: Cells dictionary (will be converted to YosysCellDetails objects)
            memories: Memories dictionary (will be converted to YosysMemoryDetails objects)
            netnames: Netnames dictionary (will be converted to YosysNetDetails objects)
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

    Attributes:
        srcPath: Path to the source JSON file
        creator: Tool that created the JSON (usually "Yosys")
        modules: Dictionary mapping module names to YosysModule objects
        models: Dictionary of behavioral models (implementation-specific)
    """

    srcPath: Path
    creator: str
    modules: dict[str, YosysModule]
    models: dict

    def __init__(self, path: Path):
        """
        Load and parse a HDL file to a Yosys JSON object.

        Args:
            path: Path to a HDL file

        Raises:
            FileNotFoundError: If the JSON file doesn't exist
            json.JSONDecodeError: If the file contains invalid JSON
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

        Returns:
            YosysModule: The top-level module

        Raises:
            ValueError: If no top module is found in the design
        """
        for module in self.modules.values():
            if "top" in module.attributes:
                return module
        raise ValueError("No top module found in Yosys JSON")

    def isTopModuleNet(self, net: int) -> bool:
        """
        Check if a net ID corresponds to a top-level module port.

        Args:
            net: Net ID to check

        Returns:
            bool: True if the net is connected to a top module port, False otherwise
        """
        for module in self.modules.values():
            for pDetail in module.ports.values():
                if net in pDetail.bits:
                    return True
        return False

    def isNetUsed(self, net: int) -> bool:
        """
        Determine if a net is actually used in the design.

        This method checks the "unused_bits" attribute to determine if a specific
        net bit is marked as unused by Yosys optimization.

        Args:
            net: Net ID to check

        Returns:
            bool: True if the net is used, False if it's marked as unused
        """
        for module in self.modules.values():
            for net_name, net_details in module.netnames.items():
                if net in net_details.bits and "unused_bits" in net_details.attributes:
                    if r := re.search(r"\w+\[(\d+)\]", net_name):
                        if int(r.group(1)) in [int(i) for i in net_details.attributes["unused_bits"].split(" ")]:
                            return False

                    else:
                        if "0 " in net_details.attributes["unused_bits"]:
                            return False
        return True

    def getNetPortSrcSinks(self, net: int) -> tuple[tuple[str, str], list[tuple[str, str]]]:
        """
        Find the source and sink connections for a given net.

        This method analyzes the netlist to determine what drives a net (source)
        and what it connects to (sinks).

        Args:
            net: Net ID to analyze

        Returns:
            tuple: A tuple containing:
                - Source: (cell_name, port_name) tuple for the driving cell/port
                - Sinks: List of (cell_name, port_name) tuples for driven cells/ports

        Raises:
            ValueError: If net is not found or has multiple drivers

        Note:
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

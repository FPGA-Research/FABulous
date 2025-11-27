"""Basic Element of Logic (BEL) definition module.

This module contains the `Bel` class which represents a Basic Element of Logic in the
FPGA fabric.
BELs are the fundamental building blocks that can be placed and configured within tiles,
such as LUTs, flip-flops, and other logic elements.
"""

from dataclasses import dataclass, field
from pathlib import Path

from FABulous.fabric_definition.define import IO, HDLType


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

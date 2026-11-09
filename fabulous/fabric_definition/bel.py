"""Basic Element of Logic (BEL) definition module.

This module contains the `Bel` class which represents a Basic Element of Logic in the
FPGA fabric.
BELs are the fundamental building blocks that can be placed and configured within tiles,
such as LUTs, flip-flops, and other logic elements.
"""

from dataclasses import dataclass, field
from pathlib import Path

from fabulous.fabric_definition.define import IO, HDLType
from fabulous.fabric_definition.port import BelPort


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
    input_ports : list[BelPort]
        The internal input ports of the BEL. Each port's `name` includes `prefix`.
    output_ports : list[BelPort]
        The internal output ports of the BEL. Each port's `name` includes `prefix`.
    external_input_ports : list[BelPort]
        The external input ports of the BEL. Each port's `name` includes `prefix`.
    external_output_ports : list[BelPort]
        The external output ports of the BEL. Each port's `name` includes `prefix`.
    user_clk_port : BelPort | None
        The `UserCLK` clock port, or None when the BEL has none.

    Raises
    ------
    ValueError
        If the file type is not recognized (not .sv, .v, .vhd, or .vhdl), or an
        internal or external port name does not start with `prefix`.
    """

    src: Path
    prefix: str
    name: str
    module_name: str
    filetype: HDLType
    configPort: list[tuple[str, IO]]
    sharedPort: list[tuple[str, IO]]
    configBit: int
    language: str
    belFeatureMap: dict[str, dict] = field(default_factory=dict)
    withUserCLK: bool = False
    ports_vectors: dict[str, dict[str, tuple[IO, int]]] = field(default_factory=dict)
    carry: dict[str, dict[IO, str]] = field(default_factory=dict)
    localShared: dict[str, tuple[str, IO]] = field(default_factory=dict)
    # Ports compare by identity, so they stay out of `Bel` equality.
    input_ports: list[BelPort] = field(default_factory=list, compare=False)
    output_ports: list[BelPort] = field(default_factory=list, compare=False)
    external_input_ports: list[BelPort] = field(default_factory=list, compare=False)
    external_output_ports: list[BelPort] = field(default_factory=list, compare=False)
    user_clk_port: BelPort | None = field(default=None, compare=False)

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
        for port, _ in internal + external:
            if not port.startswith(prefix):
                raise ValueError(
                    f"Port {port} of BEL {src} does not start with prefix {prefix}"
                )
        self.input_ports = [
            BelPort(p.removeprefix(prefix), io, 1, prefix=prefix)
            for p, io in internal
            if io == IO.INPUT
        ]
        self.output_ports = [
            BelPort(p.removeprefix(prefix), io, 1, prefix=prefix)
            for p, io in internal
            if io == IO.OUTPUT
        ]
        self.external_input_ports = [
            BelPort(p.removeprefix(prefix), io, 1, prefix=prefix, external=True)
            for p, io in external
            if io == IO.INPUT
        ]
        self.external_output_ports = [
            BelPort(p.removeprefix(prefix), io, 1, prefix=prefix, external=True)
            for p, io in external
            if io == IO.OUTPUT
        ]
        self.user_clk_port = (
            BelPort("UserCLK", IO.INPUT, 1, is_clock=True, net="UserCLK")
            if userCLK
            else None
        )
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

"""Basic Element of Logic (BEL) definition module.

This module contains the `Bel` class which represents a Basic Element of Logic in the
FPGA fabric.
BELs are the fundamental building blocks that can be placed and configured within tiles,
such as LUTs, flip-flops, and other logic elements.
"""

from collections.abc import Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Self

from fabulous.fabric_definition.define import IO, BelRole, HDLType
from fabulous.fabric_definition.port import BelPort
from fabulous.fabric_definition.timing import Ns, ns

# Placeholder BEL timing (ns), mirroring nextpnr's historical hardcoded constants
# (fabulous.cc, seed_default_estimates).
LUT_DELAY = ns(3.0)
CARRY_CICO_DELAY = ns(0.2)
CARRY_I_DELAY = ns(1.0)
FF_SETUP = ns(2.5)
FF_HOLD = ns(0.1)
FF_CLK_TO_Q = ns(1.0)
IO_SETUP = ns(2.5)
IO_HOLD = ns(0.1)
IO_CLK_TO_OUT = ns(2.5)


@dataclass(frozen=True, slots=True)
class FeatureIs:
    """BEL config feature `feature` is set or cleared.

    Attributes
    ----------
    feature : str
        Key of `Bel.belFeatureMap`.
    enabled : bool
        Whether the feature is set.
    """

    feature: str
    enabled: bool


@dataclass(frozen=True, slots=True)
class AnyConnected:
    """The arc is active when any of `ports` is routed.

    Attributes
    ----------
    ports : tuple[BelPort, ...]
        BEL ports of which at least one must be connected.
    """

    ports: tuple[BelPort, ...]


type Condition = tuple[FeatureIs, ...] | AnyConnected
"""A conjunction of feature tests, or a connectivity test; `()` is unconditional."""


@dataclass(frozen=True, slots=True)
class ClockArc:
    """A BEL clock input.

    Attributes
    ----------
    clock : BelPort
        Clock port.
    when : Condition
        Activation condition.
    """

    clock: BelPort
    when: Condition = ()


@dataclass(frozen=True, slots=True)
class DelayArc:
    """A combinational BEL arc.

    Attributes
    ----------
    src : BelPort
        Input port.
    dst : BelPort
        Output port.
    delay : Ns
        Arc delay.
    when : Condition
        Activation condition.
    """

    src: BelPort
    dst: BelPort
    delay: Ns
    when: Condition = ()


@dataclass(frozen=True, slots=True)
class SetupHoldArc:
    """Setup and hold of a registered BEL input.

    Attributes
    ----------
    data : BelPort
        Data port.
    clock : BelPort
        Clock port.
    setup : Ns
        Setup time.
    hold : Ns
        Hold time.
    when : Condition
        Activation condition.
    """

    data: BelPort
    clock: BelPort
    setup: Ns
    hold: Ns
    when: Condition = ()


@dataclass(frozen=True, slots=True)
class ClockToOutArc:
    """Clock-to-output delay of a registered BEL output.

    Attributes
    ----------
    out : BelPort
        Output port.
    clock : BelPort
        Clock port.
    delay : Ns
        Clock-to-output delay.
    when : Condition
        Activation condition.
    """

    out: BelPort
    clock: BelPort
    delay: Ns
    when: Condition = ()


@dataclass(frozen=True, slots=True)
class BelArcs:
    """All timing arcs of one BEL, grouped by kind in `bel.v3` order.

    Attributes
    ----------
    clocks : tuple[ClockArc, ...]
        Clock inputs.
    delays : tuple[DelayArc, ...]
        Combinational arcs.
    checks : tuple[SetupHoldArc, ...]
        Register input checks.
    clock_to_outs : tuple[ClockToOutArc, ...]
        Register outputs.
    """

    clocks: tuple[ClockArc, ...] = ()
    delays: tuple[DelayArc, ...] = ()
    checks: tuple[SetupHoldArc, ...] = ()
    clock_to_outs: tuple[ClockToOutArc, ...] = ()

    def __post_init__(self) -> None:
        """Check that no two clock ports share a pin name.

        Raises
        ------
        ValueError
            If two clock ports share a pin name.
        """
        names = [arc.clock.pin_name for arc in self.clocks]
        if len(set(names)) != len(names):
            raise ValueError(f"Clock ports share a pin name: {names}")

    @classmethod
    def placeholder(
        cls,
        *,
        role: BelRole,
        inputs: Sequence[BelPort],
        outputs: Sequence[BelPort],
        clock: BelPort | None = None,
    ) -> Self:
        """Return the hardcoded arcs nextpnr historically used for a BEL role.

        nextpnr times a logic cell on the pins of its own `FABULOUS_LC` cell
        (`CLK`, `Ci`, `Co`, `I1`, `I2`, `O`), whether or not the fabric BEL has
        them. An arc uses the BEL's port when it has one of that name, and a
        port that belongs to no BEL otherwise.

        Parameters
        ----------
        role : BelRole
            The BEL's role.
        inputs : Sequence[BelPort]
            Input ports of the BEL.
        outputs : Sequence[BelPort]
            Output ports of the BEL.
        clock : BelPort | None
            The BEL's `UserCLK` port, if it has one.

        Returns
        -------
        Self
            Logic-cell, input-pass or output-pass arcs; no arcs for other BELs.
        """
        clk = clock or BelPort.free("UserCLK", IO.INPUT)
        own = {port.pin_name: port for port in (*inputs, *outputs)}

        def port(name: str, io: IO) -> BelPort:
            """Return the BEL's port `name`, or a free one.

            Parameters
            ----------
            name : str
                The nextpnr pin name.
            io : IO
                The pin direction.

            Returns
            -------
            BelPort
                The port.
            """
            return own.get(name) or BelPort.free(name, io)

        def numbered(ports: Sequence[BelPort], letter: str) -> list[BelPort]:
            """Return the ports named `letter` followed by a number.

            Parameters
            ----------
            ports : Sequence[BelPort]
                Ports of the BEL.
            letter : str
                `I` or `O`.

            Returns
            -------
            list[BelPort]
                The matching ports, in order.
            """
            return [
                p
                for p in ports
                if p.pin_name.startswith(letter) and p.pin_name[1:].isdigit()
            ]

        match role:
            case BelRole.LOGIC_CELL:
                lut_inputs = numbered(inputs, "I")
                ci, co = port("Ci", IO.INPUT), port("Co", IO.OUTPUT)
                out = port("O", IO.OUTPUT)
                ff_on, ff_off = FeatureIs("FF", True), FeatureIs("FF", False)
                i0mux = FeatureIs("I0MUX", True)
                carry = AnyConnected((ci, co))
                return cls(
                    clocks=(ClockArc(clk, when=(ff_on,)),),
                    delays=(
                        # Combinational (LUT) mode: active when the FF is disabled.
                        *(
                            DelayArc(p, out, LUT_DELAY, when=(ff_off,))
                            for p in lut_inputs
                        ),
                        DelayArc(ci, out, LUT_DELAY, when=(ff_off, i0mux)),
                        DelayArc(ci, co, CARRY_CICO_DELAY, when=carry),
                        DelayArc(port("I1", IO.INPUT), co, CARRY_I_DELAY, when=carry),
                        DelayArc(port("I2", IO.INPUT), co, CARRY_I_DELAY, when=carry),
                    ),
                    checks=(
                        *(
                            SetupHoldArc(p, clk, FF_SETUP, FF_HOLD, when=(ff_on,))
                            for p in lut_inputs
                        ),
                        SetupHoldArc(ci, clk, FF_SETUP, FF_HOLD, when=(ff_on, i0mux)),
                    ),
                    clock_to_outs=(
                        ClockToOutArc(out, clk, FF_CLK_TO_Q, when=(ff_on,)),
                    ),
                )
            case BelRole.FABRIC_OUTPUT:
                return cls(
                    checks=tuple(
                        SetupHoldArc(p, clk, IO_SETUP, IO_HOLD)
                        for p in numbered(inputs, "I")
                    )
                )
            case BelRole.FABRIC_INPUT:
                return cls(
                    clock_to_outs=tuple(
                        ClockToOutArc(p, clk, IO_CLK_TO_OUT)
                        for p in numbered(outputs, "O")
                    )
                )
            case BelRole.FABRIC_INOUT | BelRole.OTHER:
                return cls()


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
    role : BelRole
        How place and route treats the BEL.

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
    role : BelRole
        How place and route treats the BEL, from its `ROLE` HDL attribute.
    arcs : BelArcs | None
        Timing arcs of the BEL, set by the placeholder timing or by
        characterisation. None until one of them ran. Not part of equality.

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
    role: BelRole = BelRole.OTHER
    arcs: BelArcs | None = field(default=None, compare=False)

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
        role: BelRole,
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
        self.role = role
        self.arcs = None

    @property
    def is_fabric_pin(self) -> bool:
        """Whether a design's I/O can be constrained to the BEL.

        Returns
        -------
        bool
            True for the fabric pin roles `FABRIC_INPUT`, `FABRIC_OUTPUT` and
            `FABRIC_INOUT`.
        """
        return self.role in (
            BelRole.FABRIC_INPUT,
            BelRole.FABRIC_OUTPUT,
            BelRole.FABRIC_INOUT,
        )

    def get_arcs(self) -> BelArcs:
        """Return the timing arcs of the BEL.

        Returns
        -------
        BelArcs
            The arcs.

        Raises
        ------
        ValueError
            If no timing is set on the BEL.
        """
        if self.arcs is None:
            raise ValueError(f"BEL {self.prefix}{self.name} has no timing arcs.")
        return self.arcs

    def placeholder_arcs(self) -> BelArcs:
        """Return the arcs nextpnr historically hardcoded for this BEL's role.

        Returns
        -------
        BelArcs
            The placeholder arcs, see `BelArcs.placeholder`.
        """
        return BelArcs.placeholder(
            role=self.role,
            inputs=self.input_ports,
            outputs=self.output_ports,
            clock=self.user_clk_port,
        )

    @property
    def is_logic_cell(self) -> bool:
        """Whether the BEL is a logic cell.

        Returns
        -------
        bool
            True when the role is `BelRole.LOGIC_CELL`.
        """
        return self.role is BelRole.LOGIC_CELL

    @property
    def cell_type(self) -> str:
        """The place-and-route cell type of the BEL.

        Returns
        -------
        str
            `FABULOUS_LC` for a logic cell, else the BEL name.
        """
        return "FABULOUS_LC" if self.is_logic_cell else self.name

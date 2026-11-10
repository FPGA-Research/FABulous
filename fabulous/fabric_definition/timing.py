"""Timing data types of the fabric model: delays, pips and BEL timing arcs.

Pure data in fabric terms: switch-matrix and tile wire names, BEL ports and BEL
config features. The nextpnr spelling of names and conditions lives only in
`fabulous.fabric_cad.gen_nextpnr_model`.
"""

from dataclasses import dataclass
from decimal import Decimal
from typing import NewType

from fabulous.fabric_definition.port import BelPort

Ns = NewType("Ns", Decimal)


def ns(value: float) -> Ns:
    """Return `value` in nanoseconds, keeping its Python `repr` text.

    The stored text is the printed text, so the placeholder `8`, the constant
    `3.0` and a characterised `0.123` print through one path. A float parsed from
    decimal text of at most 15 significant digits gets that exact value back.

    Parameters
    ----------
    value : float
        Delay in nanoseconds.

    Returns
    -------
    Ns
        The delay as an exact decimal.
    """
    return Ns(Decimal(repr(value)))


@dataclass(frozen=True, slots=True)
class SwitchPip:
    """A switch-matrix pip, mux input to mux output.

    Attributes
    ----------
    src : str
        Mux input wire.
    dst : str
        Mux output wire.
    """

    src: str
    dst: str


@dataclass(frozen=True, slots=True)
class WirePip:
    """A tile wire from `src` in this tile to `dst` in the tile at its offset.

    Attributes
    ----------
    src : str
        Wire source in this tile.
    dst : str
        Wire destination in the tile at the wire offset.
    """

    src: str
    dst: str


type Pip = SwitchPip | WirePip


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

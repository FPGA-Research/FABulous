"""Timing data types of the fabric model: delays, pips and BEL timing arcs.

Pure data in fabric terms (switch-matrix wire names, BEL port names, BEL config
features). The nextpnr
spelling of names and conditions lives only in
`fabulous.fabric_cad.gen_npnr_model`.
"""

from dataclasses import dataclass
from decimal import Decimal
from typing import NewType

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
class BelPin:
    """A BEL port bit; `bit is None` for a scalar port.

    Attributes
    ----------
    port : str
        Port name without the BEL prefix.
    bit : int | None
        Bit index of a vector port.
    """

    port: str
    bit: int | None = None

    @property
    def name(self) -> str:
        """The flattened port name, as `Bel.inputs` spells it (`I3`).

        Returns
        -------
        str
            `port` for a scalar port, else `port` followed by `bit`.
        """
        return self.port if self.bit is None else f"{self.port}{self.bit}"


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
    """The arc is active when any of `pins` is routed.

    Attributes
    ----------
    pins : tuple[BelPin, ...]
        BEL pins of which at least one must be connected.
    """

    pins: tuple[BelPin, ...]


type Condition = tuple[FeatureIs, ...] | AnyConnected
"""A conjunction of feature tests, or a connectivity test; `()` is unconditional."""


@dataclass(frozen=True, slots=True)
class ClockArc:
    """A BEL clock input.

    Attributes
    ----------
    clock : BelPin
        Clock pin.
    when : Condition
        Activation condition.
    """

    clock: BelPin
    when: Condition = ()


@dataclass(frozen=True, slots=True)
class DelayArc:
    """A combinational BEL arc.

    Attributes
    ----------
    src : BelPin
        Input pin.
    dst : BelPin
        Output pin.
    delay : Ns
        Arc delay.
    when : Condition
        Activation condition.
    """

    src: BelPin
    dst: BelPin
    delay: Ns
    when: Condition = ()


@dataclass(frozen=True, slots=True)
class SetupHoldArc:
    """Setup and hold of a registered BEL input.

    Attributes
    ----------
    data : BelPin
        Data pin.
    clock : BelPin
        Clock pin.
    setup : Ns
        Setup time.
    hold : Ns
        Hold time.
    when : Condition
        Activation condition.
    """

    data: BelPin
    clock: BelPin
    setup: Ns
    hold: Ns
    when: Condition = ()


@dataclass(frozen=True, slots=True)
class ClockToOutArc:
    """Clock-to-output delay of a registered BEL output.

    Attributes
    ----------
    out : BelPin
        Output pin.
    clock : BelPin
        Clock pin.
    delay : Ns
        Clock-to-output delay.
    when : Condition
        Activation condition.
    """

    out: BelPin
    clock: BelPin
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

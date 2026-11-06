"""Timing database of a fabric: pip delays and BEL timing arcs.

Pure data in fabric terms (BEL port names, switch-matrix wire names, BEL
config features). The nextpnr spelling of names and conditions lives only in
`fabulous.fabric_cad.gen_npnr_model`.
"""

from collections.abc import Iterator, Mapping
from dataclasses import dataclass
from decimal import Decimal
from typing import NewType

from fabulous.fabric_definition.bel import Bel

Ns = NewType("Ns", Decimal)


def ns(value: float) -> Ns:
    """Return `value` in nanoseconds, keeping its Python `repr` text.

    The stored text is the printed text, so the placeholder `8`, the constant
    `3.0` and a characterised `0.123` print through one path.

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


def switch_pips(connections: Mapping[str, list[str]]) -> Iterator[SwitchPip]:
    """Yield the pips of a switch matrix in `connections` order.

    Parameters
    ----------
    connections : Mapping[str, list[str]]
        Switch-matrix connections, mux output to its inputs.

    Yields
    ------
    SwitchPip
        One pip per mux input.
    """
    for dst, sources in connections.items():
        for src in sources:
            yield SwitchPip(src=src, dst=dst)


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


@dataclass(frozen=True, slots=True)
class PipTiming:
    """Pip delays per tile type and per supertile type.

    Attributes
    ----------
    tiles : Mapping[str, Mapping[Pip, Ns]]
        Delays of every switch and wire pip, keyed by tile type name.
    super_tiles : Mapping[str, Mapping[SwitchPip, Ns]]
        Delays of supertile switch-matrix pips, keyed by supertile type name.
    """

    tiles: Mapping[str, Mapping[Pip, Ns]]
    super_tiles: Mapping[str, Mapping[SwitchPip, Ns]]

    def tile_delay(self, tile: str, pip: Pip) -> Ns:
        """Return the delay of `pip` in tile type `tile`.

        Parameters
        ----------
        tile : str
            Tile type name.
        pip : Pip
            The pip.

        Returns
        -------
        Ns
            The pip delay.

        Raises
        ------
        ValueError
            If the tile type or the pip has no delay.
        """
        if tile not in self.tiles:
            raise ValueError(f"No pip timing for tile {tile!r}.")
        if pip not in self.tiles[tile]:
            raise ValueError(f"No delay for {pip} in tile {tile!r}.")
        return self.tiles[tile][pip]

    def super_tile_delay(self, super_tile: str, pip: SwitchPip) -> Ns:
        """Return the delay of a switch pip of supertile type `super_tile`.

        Parameters
        ----------
        super_tile : str
            Supertile type name.
        pip : SwitchPip
            The pip.

        Returns
        -------
        Ns
            The pip delay.

        Raises
        ------
        ValueError
            If the supertile type or the pip has no delay.
        """
        if super_tile not in self.super_tiles:
            raise ValueError(f"No pip timing for supertile {super_tile!r}.")
        if pip not in self.super_tiles[super_tile]:
            raise ValueError(f"No delay for {pip} in supertile {super_tile!r}.")
        return self.super_tiles[super_tile][pip]


@dataclass(frozen=True, slots=True)
class BelTiming:
    """BEL arcs per tile type and per supertile type.

    Attributes
    ----------
    tiles : Mapping[str, Mapping[str, BelArcs]]
        Arcs keyed by tile type name, then by `Bel.instance_name`.
    super_tiles : Mapping[str, Mapping[str, BelArcs]]
        Arcs keyed by supertile type name, then by `Bel.instance_name`.
    """

    tiles: Mapping[str, Mapping[str, BelArcs]]
    super_tiles: Mapping[str, Mapping[str, BelArcs]]

    def tile_arcs(self, tile: str, bel: Bel) -> BelArcs:
        """Return the arcs of `bel` in tile type `tile`.

        Parameters
        ----------
        tile : str
            Tile type name.
        bel : Bel
            The BEL.

        Returns
        -------
        BelArcs
            The BEL arcs.

        Raises
        ------
        ValueError
            If the tile type or the BEL has no arcs.
        """
        if tile not in self.tiles:
            raise ValueError(f"No BEL timing for tile {tile!r}.")
        if bel.instance_name not in self.tiles[tile]:
            raise ValueError(f"No timing for BEL {bel.instance_name!r} in {tile!r}.")
        return self.tiles[tile][bel.instance_name]

    def super_tile_arcs(self, super_tile: str, bel: Bel) -> BelArcs:
        """Return the arcs of `bel` in supertile type `super_tile`.

        Parameters
        ----------
        super_tile : str
            Supertile type name.
        bel : Bel
            The BEL.

        Returns
        -------
        BelArcs
            The BEL arcs.

        Raises
        ------
        ValueError
            If the supertile type or the BEL has no arcs.
        """
        if super_tile not in self.super_tiles:
            raise ValueError(f"No BEL timing for supertile {super_tile!r}.")
        if bel.instance_name not in self.super_tiles[super_tile]:
            raise ValueError(
                f"No timing for BEL {bel.instance_name!r} in {super_tile!r}."
            )
        return self.super_tiles[super_tile][bel.instance_name]


@dataclass(frozen=True, slots=True)
class TimingDb:
    """Complete timing of a fabric: every pip and every BEL has a value.

    Attributes
    ----------
    pips : PipTiming
        Pip delays.
    bels : BelTiming
        BEL arcs.
    clock_arrival : Ns
        Clock arrival at every flop; fabric-wide, so zero skew.
    """

    pips: PipTiming
    bels: BelTiming
    clock_arrival: Ns

"""Timing database of a fabric: pip delays and the clock arrival.

Pure data in fabric terms (switch-matrix wire names). BEL arcs live on
`fabulous.fabric_definition.bel.Bel.arcs`.
"""

from collections.abc import Iterator, Mapping
from dataclasses import dataclass

from fabulous.fabric_definition.timing import Ns


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
class TimingDb:
    """Pip delays and clock arrival of a fabric: every pip has a value.

    Attributes
    ----------
    pips : PipTiming
        Pip delays.
    clock_arrival : Ns
        Clock arrival at every flop; fabric-wide, so zero skew.
    """

    pips: PipTiming
    clock_arrival: Ns

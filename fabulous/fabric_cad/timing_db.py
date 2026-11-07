"""Timing database of a fabric: wire pip delays and the clock arrival.

Pure data in fabric terms (tile wire names). BEL arcs live on
`fabulous.fabric_definition.bel.Bel.arcs` and switch-matrix pip delays on
`fabulous.fabric_definition.switch_matrix.SwitchMatrix.pip_delays`.
"""

from collections.abc import Mapping
from dataclasses import dataclass

from fabulous.fabric_definition.timing import Ns, SwitchPip


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
class PipTiming:
    """Wire pip delays per tile type.

    Attributes
    ----------
    tiles : Mapping[str, Mapping[WirePip, Ns]]
        Delays of every wire pip of every placement, keyed by tile type name.
    """

    tiles: Mapping[str, Mapping[WirePip, Ns]]

    def tile_delay(self, tile: str, pip: WirePip) -> Ns:
        """Return the delay of `pip` in tile type `tile`.

        Parameters
        ----------
        tile : str
            Tile type name.
        pip : WirePip
            The wire pip.

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


@dataclass(frozen=True, slots=True)
class TimingDb:
    """Wire pip delays and clock arrival of a fabric: every wire pip has a value.

    Attributes
    ----------
    pips : PipTiming
        Wire pip delays.
    clock_arrival : Ns
        Clock arrival at every flop; fabric-wide, so zero skew.
    """

    pips: PipTiming
    clock_arrival: Ns

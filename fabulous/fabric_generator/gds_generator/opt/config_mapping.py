"""Assign configuration latches to the nearest frame crosspoint.

A configuration latch takes its data from `FrameData[i]` and its enable from
`FrameStrobe[j]`, so it sits logically on crosspoint `(i, j)` of the frame grid.
The tile's `ConfigMem` decides which logical configuration bit each crosspoint
holds, and nothing else in the tile depends on that choice. After placement the
latch of every bit has a position, and so does every frame line, since
`FrameData[i]` spans the tile between its west and east pins and `FrameStrobe[j]`
between its south and north pins. Reassigning bits to crosspoints so that each
latch is near the lines it hangs from shortens the frame nets without changing
what the tile computes. The assignment is a rectangular linear assignment, so
`scipy.optimize.linear_sum_assignment` solves it exactly.
"""

from collections.abc import Iterable
from dataclasses import dataclass

import numpy as np
from scipy.optimize import linear_sum_assignment

from fabulous.custom_exception import GDSFlowError
from fabulous.fabric_definition.configmem import ConfigMem, Crosspoint
from fabulous.fabric_definition.tile_interface import Axis, BusKind, BusPair
from fabulous.fabric_generator.gds_generator.opt.placement import (
    INDEXED_PIN,
    PlacedInstance,
    Placement,
)


@dataclass(frozen=True)
class FrameGrid:
    """Where each frame line runs, in microns, indexed by its bus index."""

    data_y: dict[int, float]
    strobe_x: dict[int, float]

    @property
    def frame_bits_per_row(self) -> int:
        """Number of frame data lines."""
        return len(self.data_y)

    @property
    def max_frames_per_col(self) -> int:
        """Number of frame strobe lines."""
        return len(self.strobe_x)

    def position(self, crosspoint: Crosspoint) -> tuple[float, float]:
        """Return the crosspoint location in microns."""
        return self.strobe_x[crosspoint.frame], self.data_y[crosspoint.data_bit]

    def crosspoints(self) -> list[Crosspoint]:
        """Return every crosspoint in flat frame order, then data bit order."""
        return [
            Crosspoint(frame, data_bit)
            for frame in sorted(self.strobe_x)
            for data_bit in sorted(self.data_y)
        ]


@dataclass(frozen=True)
class ConfigMapping:
    """One assignment of configuration bits to frame crosspoints."""

    crosspoint_of_bit: dict[int, Crosspoint]
    distance_before: float
    distance_after: float
    unplaced_bits: tuple[int, ...]

    def to_config_mem(self, current: ConfigMem) -> ConfigMem:
        """Express the mapping as a configuration memory of the same grid.

        Parameters
        ----------
        current : ConfigMem
            The memory the placement implements, whose grid and frame names
            the proposal keeps.

        Returns
        -------
        ConfigMem
            One frame per strobe line, empty frames included.
        """
        return current.rebuilt_with(
            {crosspoint: bit for bit, crosspoint in self.crosspoint_of_bit.items()}
        )


@dataclass(frozen=True)
class FrameLines:
    """The two chain pairs the crosspoint grid is built on."""

    data: BusPair
    strobe: BusPair

    @classmethod
    def from_pairs(cls, pairs: Iterable[BusPair]) -> "FrameLines":
        """Pick the frame data and frame strobe pairs out of a tile's pairs.

        Parameters
        ----------
        pairs : Iterable[BusPair]
            The tile's bus pairs.

        Returns
        -------
        FrameLines
            The data and strobe pairs.

        Raises
        ------
        GDSFlowError
            If either chain is missing from the pairs.
        """
        by_kind = {pair.kind: pair for pair in pairs}
        try:
            return cls(by_kind[BusKind.FRAME_DATA], by_kind[BusKind.FRAME_STROBE])
        except KeyError as exc:
            raise GDSFlowError(
                f"The tile's pairs carry no {exc.args[0].value} chain"
            ) from exc


@dataclass(frozen=True)
class LatchPins:
    """A configuration latch and which of its pins hang on the two frame lines."""

    instance: str
    data_pin: str
    strobe_pin: str


def _indexed_pins(placement: Placement, bus: str, axis: Axis) -> dict[int, float]:
    """Return the across-border coordinate of every `bus[n]` pin, by index."""
    pins: dict[int, tuple[float, float]] = {}
    for name, pin in placement.pins.items():
        if (match := INDEXED_PIN.match(name)) and match["bus"] == bus:
            pins[int(match["index"])] = (pin.x, pin.y)
    return {
        index: xy[1] if axis is Axis.HORIZONTAL else xy[0] for index, xy in pins.items()
    }


def frame_grid(placement: Placement, lines: FrameLines) -> FrameGrid:
    """Locate every frame line from its two border pins.

    A data line runs at the mean y of its entry and exit pins, a strobe line
    at the mean x of its two.

    Parameters
    ----------
    placement : Placement
        The placed tile.
    lines : FrameLines
        The data and strobe chain pairs.

    Returns
    -------
    FrameGrid
        Line positions indexed by bus index.

    Raises
    ------
    GDSFlowError
        If an entry pin has no matching exit pin, since the line then does not
        span the tile and the crosspoint model does not hold.
    """
    positions: list[dict[int, float]] = []
    for pair in (lines.data, lines.strobe):
        entry = _indexed_pins(placement, pair.second, pair.axis)
        exit_ = _indexed_pins(placement, pair.first, pair.axis)
        if not entry or set(entry) != set(exit_):
            raise GDSFlowError(
                f"{pair.second} pins {sorted(entry)} and {pair.first} pins "
                f"{sorted(exit_)} do not pair up, so the frame lines do not span "
                "the tile."
            )
        positions.append({index: (entry[index] + exit_[index]) / 2 for index in entry})
    return FrameGrid(data_y=positions[0], strobe_x=positions[1])


def latch_pins(placement: Placement, lines: FrameLines) -> dict[Crosspoint, LatchPins]:
    """Identify the configuration latches structurally, with their frame pins.

    A leaf cell reached from `FrameData[i]` through buffers and also reached
    from `FrameStrobe[j]` is the latch at crosspoint `(i, j)`; the pin through
    which each line reaches it is recorded so the latch can be moved to other
    lines later. Names play no part, because Yosys names a latch output net
    after whichever public wire it prefers.

    Parameters
    ----------
    placement : Placement
        The placed tile.
    lines : FrameLines
        The data and strobe chain pairs.

    Returns
    -------
    dict[Crosspoint, LatchPins]
        The latch and its two frame pins at each occupied crosspoint.

    Raises
    ------
    GDSFlowError
        If no latch is reached, if a cell hangs from two lines of the same
        bus, if a frame line reaches a cell that is not a latch, or if two
        latches share a crosspoint.
    """
    data_bus, strobe_bus = lines.data.second, lines.strobe.second
    line_of_cell: dict[str, dict[str, tuple[int, str]]] = {}
    for bus in (data_bus, strobe_bus):
        for name in placement.pins:
            if not ((match := INDEXED_PIN.match(name)) and match["bus"] == bus):
                continue
            index = int(match["index"])
            for cell, pin in placement.leaf_pins(placement.net_of_port(name).name):
                hangs_from = line_of_cell.setdefault(cell, {})
                if bus in hangs_from and hangs_from[bus][0] != index:
                    raise GDSFlowError(
                        f"Cell {cell} hangs from {bus}[{hangs_from[bus][0]}] and "
                        f"{bus}[{index}]; a configuration latch takes one line "
                        "of each bus."
                    )
                hangs_from[bus] = (index, pin)

    latches: dict[Crosspoint, LatchPins] = {}
    for cell, reached in sorted(line_of_cell.items()):
        if set(reached) != {data_bus, strobe_bus}:
            raise GDSFlowError(
                f"Cell {cell} is reached from {sorted(reached)} only; every leaf on "
                "a frame line is expected to be a configuration latch."
            )
        (data_bit, data_pin) = reached[data_bus]
        (frame, strobe_pin) = reached[strobe_bus]
        crosspoint = Crosspoint(frame, data_bit)
        if (other := latches.get(crosspoint)) is not None:
            raise GDSFlowError(
                f"Cells {other.instance} and {cell} both sit on {data_bus}"
                f"[{data_bit}] x {strobe_bus}[{frame}]."
            )
        latches[crosspoint] = LatchPins(cell, data_pin, strobe_pin)

    if not latches:
        raise GDSFlowError(
            f"No configuration latch was reached from the {data_bus} and "
            f"{strobe_bus} ports. The Verilog synthesis flow is the only one "
            "verified to keep the latch structure this walk relies on."
        )
    return latches


def reconnections(
    pins: dict[Crosspoint, LatchPins],
    bit_at: dict[Crosspoint, int],
    mapping: ConfigMapping,
    lines: FrameLines,
) -> dict[str, dict[str, str]]:
    """Return the port net each latch pin must sit on to implement `mapping`.

    The targets are absolute, so applying them to a netlist implementing any
    earlier mapping yields the proposal, and a pin already on its target is
    left alone by the applier.

    Parameters
    ----------
    pins : dict[Crosspoint, LatchPins]
        The latches found in the placement, by their current crosspoint.
    bit_at : dict[Crosspoint, int]
        The logical bit at each crosspoint under the mapping the placement
        implements.
    mapping : ConfigMapping
        The proposal.
    lines : FrameLines
        The data and strobe chain pairs the target nets are named after.

    Returns
    -------
    dict[str, dict[str, str]]
        `{instance: {pin: net}}` for every latch.

    Raises
    ------
    GDSFlowError
        If a latch sits on a crosspoint the mapping does not allocate.
    """
    result: dict[str, dict[str, str]] = {}
    for crosspoint, latch in pins.items():
        if (bit := bit_at.get(crosspoint)) is None:
            raise GDSFlowError(
                f"Latch {latch.instance} sits on FrameData[{crosspoint.data_bit}] x "
                f"FrameStrobe[{crosspoint.frame}], which the ConfigMem CSV does not "
                "allocate."
            )
        target = mapping.crosspoint_of_bit[bit]
        result[latch.instance] = {
            latch.data_pin: f"{lines.data.second}[{target.data_bit}]",
            latch.strobe_pin: f"{lines.strobe.second}[{target.frame}]",
        }
    return result


def _distance(instance: PlacedInstance, position: tuple[float, float]) -> float:
    """Return the Manhattan distance from an instance centre to a point."""
    return abs(instance.x - position[0]) + abs(instance.y - position[1])


def solve_config_mapping(
    placement: Placement, config_mem: ConfigMem, lines: FrameLines
) -> ConfigMapping:
    """Assign every logical bit to a crosspoint near its placed latch.

    Placed latches take the crosspoints that minimise the summed Manhattan
    distance between each latch and its crosspoint. Bits whose latch synthesis
    removed keep no position, so they take the crosspoints left over, in flat
    grid order, which keeps every bit allocated exactly once.

    Parameters
    ----------
    placement : Placement
        The placed tile.
    config_mem : ConfigMem
        The mapping the placement implements.
    lines : FrameLines
        The data and strobe chain pairs.

    Returns
    -------
    ConfigMapping
        The new crosspoint of every bit and the distance sums before and after.

    Raises
    ------
    GDSFlowError
        If a placed latch sits on a crosspoint the CSV does not allocate, or if
        the grid cannot hold every bit.
    """
    grid = frame_grid(placement, lines)
    bit_at = config_mem.bit_at
    latches = {
        crosspoint: placement.instances[pins.instance]
        for crosspoint, pins in latch_pins(placement, lines).items()
    }
    if unknown := sorted(set(latches) - set(bit_at)):
        raise GDSFlowError(
            f"Latches sit on crosspoints the ConfigMem CSV does not allocate: "
            f"{[(c.data_bit, c.frame) for c in unknown]}"
        )

    all_bits = sorted(bit_at.values())
    crosspoints = grid.crosspoints()
    if len(all_bits) > len(crosspoints):
        raise GDSFlowError(
            f"{len(all_bits)} configuration bits do not fit the "
            f"{len(crosspoints)} crosspoints of the frame grid."
        )

    placed = sorted(
        (bit_at[crosspoint], latch) for crosspoint, latch in latches.items()
    )
    distance_before = sum(
        _distance(latch, grid.position(crosspoint))
        for crosspoint, latch in latches.items()
    )
    cost = np.array(
        [
            [_distance(latch, grid.position(c)) for c in crosspoints]
            for _, latch in placed
        ]
    )
    rows, cols = linear_sum_assignment(cost)
    crosspoint_of_bit = {
        placed[row][0]: crosspoints[col] for row, col in zip(rows, cols, strict=True)
    }
    distance_after = float(cost[rows, cols].sum())

    taken = set(crosspoint_of_bit.values())
    free = iter(c for c in crosspoints if c not in taken)
    unplaced = tuple(bit for bit in all_bits if bit not in crosspoint_of_bit)
    for bit in unplaced:
        crosspoint_of_bit[bit] = next(free)

    return ConfigMapping(
        crosspoint_of_bit=crosspoint_of_bit,
        distance_before=distance_before,
        distance_after=distance_after,
        unplaced_bits=unplaced,
    )

"""Assign configuration latches to the crosspoints that shorten the frame nets.

A configuration latch takes its data from `FrameData[i]` and its enable from
`FrameStrobe[j]`, so it sits logically on crosspoint `(i, j)` of the frame grid.
The tile's `ConfigMem` decides which logical configuration bit each crosspoint
holds, and nothing else in the tile depends on that choice, so reassigning bits
to crosspoints shortens the frame nets without changing what the tile computes.

`FrameData[i]` reaches from its west pin to its east pin whatever the mapping
does, so it is modelled as a horizontal trunk whose length is fixed and whose
only variable cost is the stubs joining its latches to it; `FrameStrobe[j]` runs
vertically and costs the stubs of its own. Total stub length is what this module
minimises. Written against a trunk at `y_i` and one at `x_j`, the cost of putting
a latch on crosspoint `(i, j)` is `|y - y_i| + |x - x_j|`, the Manhattan distance
to a point, so for fixed trunks the choice is a rectangular linear assignment and
`scipy.optimize.linear_sum_assignment` solves it to global optimality. The trunks
are then the free variables, and the exact minimiser of `sum |y - y_i|` over a
group is its median, so the two steps alternate until the assignment repeats.
Both steps lower the same cost, which makes the alternation monotone, though it
converges on a local optimum and not a global one.

The crosspoints are virtual. They divide the die evenly and take their order,
not their positions, from the border pins, because a default pin order bunches a
whole bus into one corner of the tile, where distance to a pin intersection says
nothing about which latches belong on the same net.
"""

from collections.abc import Iterable
from dataclasses import dataclass
from typing import NamedTuple, Self

import numpy as np
from scipy.optimize import linear_sum_assignment

from fabulous.custom_exception import GDSFlowError
from fabulous.fabric_definition.configmem import ConfigMem, Crosspoint
from fabulous.fabric_definition.tile_interface import Axis, BusKind, BusPair
from fabulous.fabric_generator.gds_generator.opt.placement import (
    INDEXED_PIN,
    Placement,
)


@dataclass(frozen=True)
class FrameGrid:
    """Where each frame net's trunk runs, in microns, indexed by its bus index."""

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


class MappingMetrics(NamedTuple):
    """What one solve moved: the frame-net stub length, and what it left."""

    stub_before: float
    stub_after: float
    unplaced_bits: tuple[int, ...]


@dataclass(frozen=True)
class FrameLines:
    """The two chain pairs the crosspoint grid is built on."""

    data: BusPair
    strobe: BusPair

    @classmethod
    def from_pairs(cls, pairs: Iterable[BusPair]) -> Self:
        """Pick the frame data and frame strobe pairs out of a tile's pairs.

        Parameters
        ----------
        pairs : Iterable[BusPair]
            The tile's bus pairs.

        Returns
        -------
        Self
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


@dataclass(frozen=True)
class FrameBorders:
    """Both border pins of every frame net, on the axis its trunk does not run."""

    data_y: dict[int, tuple[float, float]]
    strobe_x: dict[int, tuple[float, float]]


def frame_borders(placement: Placement, lines: FrameLines) -> FrameBorders:
    """Pair up the two border pins of every frame net.

    The pins anchor the trunk as much as the latches do, so they count as
    terminals when a trunk is placed.

    Parameters
    ----------
    placement : Placement
        The placed tile.
    lines : FrameLines
        The data and strobe chain pairs.

    Returns
    -------
    FrameBorders
        The entry and exit coordinate of every net, indexed by bus index.

    Raises
    ------
    GDSFlowError
        If an entry pin has no matching exit pin, since the net then does not
        span the tile and the trunk model does not hold.
    """
    ends: list[dict[int, tuple[float, float]]] = []
    for pair in (lines.data, lines.strobe):
        entry = _indexed_pins(placement, pair.second, pair.axis)
        exit_ = _indexed_pins(placement, pair.first, pair.axis)
        if not entry or set(entry) != set(exit_):
            raise GDSFlowError(
                f"{pair.second} pins {sorted(entry)} and {pair.first} pins "
                f"{sorted(exit_)} do not pair up, so the frame nets do not span "
                "the tile."
            )
        ends.append({index: (entry[index], exit_[index]) for index in entry})
    return FrameBorders(data_y=ends[0], strobe_x=ends[1])


def _spread(
    ends: dict[int, tuple[float, float]], lo: float, hi: float
) -> dict[int, float]:
    """Give each index an even band of `lo` to `hi`, ranked by its two pins' mean.

    The mean only decides the order, so it matters solely when a tile's two
    borders are ordered differently from each other.
    """
    ranked = sorted(ends, key=lambda index: sum(ends[index]))
    step = (hi - lo) / len(ranked)
    return {index: lo + step * (rank + 0.5) for rank, index in enumerate(ranked)}


def frame_grid(placement: Placement, lines: FrameLines) -> FrameGrid:
    """Spread the frame trunks evenly over the die, in border-pin order.

    This is where the alternation starts, before any group has a median to sit
    on. The bands keep the order the border pins give the nets so that a
    proposal reads the same way round as the tile is wired, but not their
    positions, which a default pin order leaves bunched in one corner.

    Parameters
    ----------
    placement : Placement
        The placed tile.
    lines : FrameLines
        The data and strobe chain pairs.

    Returns
    -------
    FrameGrid
        Trunk positions indexed by bus index.
    """
    x0, y0, x1, y1 = placement.die
    borders = frame_borders(placement, lines)
    return FrameGrid(
        data_y=_spread(borders.data_y, y0, y1),
        strobe_x=_spread(borders.strobe_x, x0, x1),
    )


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
    proposal: ConfigMem,
    lines: FrameLines,
) -> dict[str, dict[str, str]]:
    """Return the port net each latch pin must sit on to implement `proposal`.

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
    proposal : ConfigMem
        The memory the latches must implement.
    lines : FrameLines
        The data and strobe chain pairs the target nets are named after.

    Returns
    -------
    dict[str, dict[str, str]]
        `{instance: {pin: net}}` for every latch.

    Raises
    ------
    GDSFlowError
        If a latch sits on a crosspoint the proposal does not allocate.
    """
    result: dict[str, dict[str, str]] = {}
    for crosspoint, latch in pins.items():
        if (bit := bit_at.get(crosspoint)) is None:
            raise GDSFlowError(
                f"Latch {latch.instance} sits on FrameData[{crosspoint.data_bit}] x "
                f"FrameStrobe[{crosspoint.frame}], which the ConfigMem CSV does not "
                "allocate."
            )
        target = proposal.crosspoint_of[bit]
        result[latch.instance] = {
            latch.data_pin: f"{lines.data.second}[{target.data_bit}]",
            latch.strobe_pin: f"{lines.strobe.second}[{target.frame}]",
        }
    return result


_ALTERNATION_LIMIT = 20
"""Alternations to spend on the trunks before taking the assignment in hand.

Both steps lower the same cost, so stopping early keeps a usable assignment and
only leaves some of the gain unclaimed.
"""


def _fit_trunks(
    positions: np.ndarray,
    group: np.ndarray,
    ends: dict[int, tuple[float, float]],
    indices: list[int],
) -> tuple[np.ndarray, float]:
    """Return each group's cheapest trunk and the stub length it leaves.

    The median of a group's terminals is the exact minimiser of the summed
    distance to them, and the border pins count among those terminals.
    """
    trunks = np.empty(len(indices))
    stub = 0.0
    for rank, index in enumerate(indices):
        terminals = np.concatenate((positions[group == rank], np.asarray(ends[index])))
        trunks[rank] = np.median(terminals)
        stub += float(np.abs(terminals - trunks[rank]).sum())
    return trunks, stub


def _assign(
    xs: np.ndarray, ys: np.ndarray, trunk_x: np.ndarray, trunk_y: np.ndarray
) -> tuple[np.ndarray, np.ndarray]:
    """Put each latch on the crosspoint whose two trunks cost it least.

    Returns the rank of the strobe and of the data trunk taken by each latch.
    """
    cost = (
        np.abs(xs[:, None] - trunk_x[None, :])[:, :, None]
        + np.abs(ys[:, None] - trunk_y[None, :])[:, None, :]
    ).reshape(len(xs), -1)
    rows, cols = linear_sum_assignment(cost)
    flat = np.empty(len(xs), dtype=int)
    flat[rows] = cols
    return flat // len(trunk_y), flat % len(trunk_y)


def solve_config_mapping(
    placement: Placement, config_mem: ConfigMem, lines: FrameLines
) -> tuple[ConfigMem, MappingMetrics]:
    """Assign every logical bit to a crosspoint that shortens its frame nets.

    Placed latches take the crosspoints that minimise the total length of the
    stubs joining them to their frame trunks, solved exactly for fixed trunks
    and alternated with the median that fits each trunk to the group it ended
    up with. Bits whose latch synthesis removed keep no position, so they take
    the crosspoints left over, in flat grid order, which keeps every bit
    allocated exactly once.

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
    tuple[ConfigMem, MappingMetrics]
        The proposed memory, keeping the grid and frame names of `config_mem`,
        and the stub length before and after the move.

    Raises
    ------
    GDSFlowError
        If a placed latch sits on a crosspoint the CSV does not allocate, or if
        the grid cannot hold every bit.
    """
    grid = frame_grid(placement, lines)
    borders = frame_borders(placement, lines)
    bit_at = config_mem.bit_at
    found = latch_pins(placement, lines)
    if unknown := sorted(set(found) - set(bit_at)):
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

    frames, data_bits = sorted(grid.strobe_x), sorted(grid.data_y)
    frame_rank = {index: rank for rank, index in enumerate(frames)}
    data_rank = {index: rank for rank, index in enumerate(data_bits)}
    placed = sorted(found, key=lambda crosspoint: bit_at[crosspoint])
    latches = [placement.instances[found[crosspoint].instance] for crosspoint in placed]
    xs = np.array([latch.x for latch in latches])
    ys = np.array([latch.y for latch in latches])

    _, was_x = _fit_trunks(
        xs, np.array([frame_rank[c.frame] for c in placed]), borders.strobe_x, frames
    )
    _, was_y = _fit_trunks(
        ys, np.array([data_rank[c.data_bit] for c in placed]), borders.data_y, data_bits
    )
    stub_before = was_x + was_y

    trunk_x = np.array([grid.strobe_x[index] for index in frames])
    trunk_y = np.array([grid.data_y[index] for index in data_bits])
    on_frame, on_data = _assign(xs, ys, trunk_x, trunk_y)
    for _ in range(_ALTERNATION_LIMIT):
        trunk_x, _ = _fit_trunks(xs, on_frame, borders.strobe_x, frames)
        trunk_y, _ = _fit_trunks(ys, on_data, borders.data_y, data_bits)
        next_frame, next_data = _assign(xs, ys, trunk_x, trunk_y)
        settled = np.array_equal(next_frame, on_frame) and np.array_equal(
            next_data, on_data
        )
        on_frame, on_data = next_frame, next_data
        if settled:
            break

    _, now_x = _fit_trunks(xs, on_frame, borders.strobe_x, frames)
    _, now_y = _fit_trunks(ys, on_data, borders.data_y, data_bits)
    stub_after = now_x + now_y
    crosspoint_of_bit = {
        bit_at[crosspoint]: Crosspoint(frames[int(frame)], data_bits[int(data_bit)])
        for crosspoint, frame, data_bit in zip(placed, on_frame, on_data, strict=True)
    }

    taken = set(crosspoint_of_bit.values())
    free = iter(c for c in crosspoints if c not in taken)
    unplaced = tuple(bit for bit in all_bits if bit not in crosspoint_of_bit)
    for bit in unplaced:
        crosspoint_of_bit[bit] = next(free)

    proposal = config_mem.rebuilt_with(
        {crosspoint: bit for bit, crosspoint in crosspoint_of_bit.items()}
    )
    return proposal, MappingMetrics(stub_before, stub_after, unplaced)

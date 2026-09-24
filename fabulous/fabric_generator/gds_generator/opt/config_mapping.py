"""Assign configuration latches to the crosspoints that shorten the frame nets.

A latch takes its data from `FrameData[i]` and its enable from `FrameStrobe[j]`,
so it sits on crosspoint `(i, j)`, and nothing else in the tile depends on which
logical bit a crosspoint holds. With the trunks fixed the choice is a
rectangular linear assignment, solved exactly by
`scipy.optimize.linear_sum_assignment`; the exact minimiser of the trunk
positions is then the median of each group, so the two steps alternate to a
local optimum. The crosspoints are virtual and evenly spaced, taking their order
but not their positions from the border pins, because a default pin order
bunches a whole bus into one corner of the tile where distance to a pin says
nothing about which latches belong on the same net.
"""

from dataclasses import dataclass
from typing import NamedTuple

import numpy as np
from scipy.optimize import linear_sum_assignment

from fabulous.custom_exception import GDSFlowError
from fabulous.fabric_definition.configmem import ConfigMem, Crosspoint
from fabulous.fabric_definition.define import FRAME_DATA, FRAME_STROBE
from fabulous.fabric_generator.gds_generator.opt.placement import (
    PlacedLatch,
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


def frame_grid(placement: Placement) -> FrameGrid:
    """Spread the frame trunks evenly over the die, in border-pin order.

    This is where the alternation starts, before any group has a median to sit
    on. The bands keep the order the border pins give the nets so that a
    proposal reads the same way round as the tile is wired, but not their
    positions, which a default pin order leaves bunched in one corner.

    Parameters
    ----------
    placement : Placement
        The placed tile.

    Returns
    -------
    FrameGrid
        Trunk positions indexed by bus index.
    """
    x0, y0, x1, y1 = placement.die
    return FrameGrid(
        data_y=_spread(placement.data_y, y0, y1),
        strobe_x=_spread(placement.strobe_x, x0, x1),
    )


def reconnections(
    latches: tuple[PlacedLatch, ...],
    bit_at: dict[Crosspoint, int],
    proposal: ConfigMem,
) -> dict[str, dict[str, str]]:
    """Return the port net each latch pin must sit on to implement `proposal`.

    The targets are absolute, so applying them to a netlist implementing any
    earlier mapping yields the proposal, and a pin already on its target is
    left alone by the applier.

    Parameters
    ----------
    latches : tuple[PlacedLatch, ...]
        The latches the dump found, each on the crosspoint it currently holds.
    bit_at : dict[Crosspoint, int]
        The logical bit at each crosspoint under the mapping the placement
        implements.
    proposal : ConfigMem
        The memory the latches must implement.

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
    for latch in latches:
        crosspoint = latch.crosspoint
        if (bit := bit_at.get(crosspoint)) is None:
            raise GDSFlowError(
                f"Latch {latch.instance} sits on FrameData[{crosspoint.data_bit}] x "
                f"FrameStrobe[{crosspoint.frame}], which the ConfigMem CSV does not "
                "allocate."
            )
        target = proposal.crosspoint_of[bit]
        result[latch.instance] = {
            latch.data_pin: f"{FRAME_DATA}[{target.data_bit}]",
            latch.strobe_pin: f"{FRAME_STROBE}[{target.frame}]",
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
    placement: Placement, config_mem: ConfigMem
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
    grid = frame_grid(placement)
    bit_at = config_mem.bit_at
    found = {latch.crosspoint: latch for latch in placement.latches}
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
    xs = np.array([found[crosspoint].x for crosspoint in placed])
    ys = np.array([found[crosspoint].y for crosspoint in placed])

    _, was_x = _fit_trunks(
        xs, np.array([frame_rank[c.frame] for c in placed]), placement.strobe_x, frames
    )
    _, was_y = _fit_trunks(
        ys,
        np.array([data_rank[c.data_bit] for c in placed]),
        placement.data_y,
        data_bits,
    )
    stub_before = was_x + was_y

    trunk_x = np.array([grid.strobe_x[index] for index in frames])
    trunk_y = np.array([grid.data_y[index] for index in data_bits])
    on_frame, on_data = _assign(xs, ys, trunk_x, trunk_y)
    for _ in range(_ALTERNATION_LIMIT):
        trunk_x, _ = _fit_trunks(xs, on_frame, placement.strobe_x, frames)
        trunk_y, _ = _fit_trunks(ys, on_data, placement.data_y, data_bits)
        next_frame, next_data = _assign(xs, ys, trunk_x, trunk_y)
        settled = np.array_equal(next_frame, on_frame) and np.array_equal(
            next_data, on_data
        )
        on_frame, on_data = next_frame, next_data
        if settled:
            break

    _, now_x = _fit_trunks(xs, on_frame, placement.strobe_x, frames)
    _, now_y = _fit_trunks(ys, on_data, placement.data_y, data_bits)
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

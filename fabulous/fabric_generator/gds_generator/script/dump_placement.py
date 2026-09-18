"""Find the configuration latches of a placed tile and write where they sit.

A latch is the leaf cell reached from both a `FrameData` and a `FrameStrobe`
port, walking any single-input single-output cell through as a buffer. The walk
is direction-free, which is what lets a port, its feed-through buffer and the
matching output port count as one net, and it goes by connectivity rather than
names, because Yosys names a latch output net after whichever public wire it
prefers. It runs here because OpenDB already holds the connectivity; the
assignment cannot, since the OpenROAD interpreter has no scipy.
"""

import json
import re
from collections import deque
from pathlib import Path

import click
from librelane.scripts.odbpy.reader import click_odb

from fabulous.fabric_definition.define import (
    FRAME_DATA,
    FRAME_DATA_OUT,
    FRAME_STROBE,
    FRAME_STROBE_OUT,
)
from fabulous.fabric_generator.gds_generator.script.odb_protocol import (
    OdbReaderLike,
    odbBlockLike,
    odbBoxLike,
    odbInstLike,
    odbITermLike,
    odbNetLike,
)

INDEXED_PIN = re.compile(r"^(?P<bus>.+)\[(?P<index>\d+)\]$")
"""A block port of a bus, `bus[index]`."""

_SUPPLY_TYPES = frozenset({"POWER", "GROUND"})


def _centre(box: odbBoxLike, dbu: float) -> tuple[float, float]:
    """Return the centre of a database box in microns."""
    return (
        (box.xMin() + box.xMax()) / 2 / dbu,
        (box.yMin() + box.yMax()) / 2 / dbu,
    )


def _signal_iterms(inst: odbInstLike) -> list[odbITermLike]:
    """Return the instance pins carrying a signal, supply pins dropped."""
    return [
        iterm
        for iterm in inst.getITerms()
        if iterm.getSigType() not in _SUPPLY_TYPES and iterm.getNet() is not None
    ]


def _is_buffer(inst: odbInstLike) -> bool:
    """Return True for a cell with exactly one signal input and one output."""
    iterms = _signal_iterms(inst)
    return len(iterms) == 2 and {t.getIoType() for t in iterms} == {"INPUT", "OUTPUT"}


def _is_leaf(inst: odbInstLike) -> bool:
    """Return True for a multi-pin cell that is not a buffer."""
    return len(_signal_iterms(inst)) >= 2 and not _is_buffer(inst)


def leaf_pins(net: odbNetLike) -> set[tuple[str, str]]:
    """Return `(instance, pin)` of every leaf terminal on `net`'s logical net.

    Parameters
    ----------
    net : odbNetLike
        One net of the logical net.

    Returns
    -------
    set[tuple[str, str]]
        Every terminal of a leaf cell reached through buffers from `net`.
    """
    seen: set[str] = {net.getName()}
    queue: deque[odbNetLike] = deque([net])
    found: set[tuple[str, str]] = set()
    while queue:
        current = queue.popleft()
        for iterm in current.getITerms():
            if iterm.getSigType() in _SUPPLY_TYPES:
                continue
            inst = iterm.getInst()
            if _is_leaf(inst):
                found.add((inst.getName(), iterm.getMTerm().getName()))
                continue
            if not _is_buffer(inst):
                continue
            for other in _signal_iterms(inst):
                joined = other.getNet()
                if joined is not None and joined.getName() not in seen:
                    seen.add(joined.getName())
                    queue.append(joined)
    return found


def _indexed_ports(
    block: odbBlockLike, bus: str, dbu: float
) -> dict[int, tuple[float, float]]:
    """Return the centre of every `bus[n]` port, by index.

    Parameters
    ----------
    block : odbBlockLike
        The placed block.
    bus : str
        Name of the bus whose ports are wanted.
    dbu : float
        Database units per micron.

    Returns
    -------
    dict[int, tuple[float, float]]
        The centre of each index's port.

    Raises
    ------
    ValueError
        If a matching port has no placed pin.
    """
    ports: dict[int, tuple[float, float]] = {}
    for bterm in block.getBTerms():
        name = bterm.getName()
        match = INDEXED_PIN.match(name)
        if not match or match["bus"] != bus:
            continue
        bpins = bterm.getBPins()
        if not bpins:
            raise ValueError(
                f"Port {name} has no placed pin. Run this step after IO placement."
            )
        ports[int(match["index"])] = _centre(bpins[0].getBBox(), dbu)
    return ports


def frame_borders(
    block: odbBlockLike, dbu: float, *, bus: str, out_bus: str, horizontal: bool
) -> dict[int, list[float]]:
    """Pair both border coordinates of every net of a frame bus, by index.

    A horizontal chain's pins differ in y and a vertical chain's in x, since the
    coordinate along a chain is the same at both of its border pins, so only the
    across-border coordinate is reported.

    Parameters
    ----------
    block : odbBlockLike
        The placed block.
    dbu : float
        Database units per micron.
    bus : str
        Name of the entry bus.
    out_bus : str
        Name of the matching exit bus.
    horizontal : bool
        Whether the chain runs across the tile, which selects the y coordinate.

    Returns
    -------
    dict[int, list[float]]
        The entry and exit coordinate of each index.

    Raises
    ------
    ValueError
        If an entry port has no matching exit port, since the net then does not
        span the tile and the trunk model does not hold.
    """
    entry = _indexed_ports(block, bus, dbu)
    exit_ = _indexed_ports(block, out_bus, dbu)
    if not entry or set(entry) != set(exit_):
        raise ValueError(
            f"{bus} ports {sorted(entry)} and {out_bus} ports {sorted(exit_)} do "
            "not pair up, so the frame nets do not span the tile."
        )
    axis = 1 if horizontal else 0
    return {index: [entry[index][axis], exit_[index][axis]] for index in entry}


def find_latches(block: odbBlockLike, dbu: float) -> list[dict]:
    """Locate every configuration latch by the two frame lines that reach it.

    Parameters
    ----------
    block : odbBlockLike
        The placed block.
    dbu : float
        Database units per micron.

    Returns
    -------
    list[dict]
        One record per latch, carrying its crosspoint, its position and the pin
        each frame line reaches it through, in crosspoint order.

    Raises
    ------
    ValueError
        If a frame port is on no net, if a cell hangs from two lines of the same
        bus, if a frame line reaches a cell that is not a latch, if two latches
        share a crosspoint, if a latch is unplaced, or if no latch is reached.
    """
    reached: dict[str, dict[str, tuple[int, str]]] = {}
    for bus in (FRAME_DATA, FRAME_STROBE):
        for bterm in block.getBTerms():
            match = INDEXED_PIN.match(bterm.getName())
            if not match or match["bus"] != bus:
                continue
            net = bterm.getNet()
            if net is None:
                raise ValueError(f"Port {bterm.getName()} is not on any signal net.")
            index = int(match["index"])
            for cell, pin in leaf_pins(net):
                hangs_from = reached.setdefault(cell, {})
                if bus in hangs_from and hangs_from[bus][0] != index:
                    raise ValueError(
                        f"Cell {cell} hangs from {bus}[{hangs_from[bus][0]}] and "
                        f"{bus}[{index}]; a configuration latch takes one line "
                        "of each bus."
                    )
                hangs_from[bus] = (index, pin)

    latches: dict[tuple[int, int], dict] = {}
    for cell, lines in sorted(reached.items()):
        if set(lines) != {FRAME_DATA, FRAME_STROBE}:
            raise ValueError(
                f"Cell {cell} is reached from {sorted(lines)} only; every leaf on "
                "a frame line is expected to be a configuration latch."
            )
        data_bit, data_pin = lines[FRAME_DATA]
        frame, strobe_pin = lines[FRAME_STROBE]
        if (other := latches.get((frame, data_bit))) is not None:
            raise ValueError(
                f"Cells {other['instance']} and {cell} both sit on "
                f"{FRAME_DATA}[{data_bit}] x {FRAME_STROBE}[{frame}]."
            )
        inst = block.findInst(cell)
        if inst is None or not inst.isPlaced():
            raise ValueError(
                f"Latch {cell} is not placed. Run this step after placement."
            )
        x, y = _centre(inst.getBBox(), dbu)
        latches[frame, data_bit] = {
            "frame": frame,
            "data_bit": data_bit,
            "instance": cell,
            "x": x,
            "y": y,
            "data_pin": data_pin,
            "strobe_pin": strobe_pin,
        }

    if not latches:
        raise ValueError(
            f"No configuration latch was reached from the {FRAME_DATA} and "
            f"{FRAME_STROBE} ports. The Verilog synthesis flow is the only one "
            "verified to keep the latch structure this walk relies on."
        )
    return [latches[key] for key in sorted(latches)]


def dump_block(block: odbBlockLike, dbu: float) -> dict:
    """Collect the die, the frame border pins and the placed latches.

    Parameters
    ----------
    block : odbBlockLike
        The placed block.
    dbu : float
        Database units per micron, used to report every coordinate in microns.

    Returns
    -------
    dict
        The JSON-ready payload with `die`, `data_y`, `strobe_x` and `latches`.
    """
    die = block.getDieArea()
    return {
        "die": [
            die.xMin() / dbu,
            die.yMin() / dbu,
            die.xMax() / dbu,
            die.yMax() / dbu,
        ],
        "data_y": frame_borders(
            block, dbu, bus=FRAME_DATA, out_bus=FRAME_DATA_OUT, horizontal=True
        ),
        "strobe_x": frame_borders(
            block, dbu, bus=FRAME_STROBE, out_bus=FRAME_STROBE_OUT, horizontal=False
        ),
        "latches": find_latches(block, dbu),
    }


@click.command()
@click.option(
    "--placement-out",
    required=True,
    type=click.Path(dir_okay=False, writable=True, path_type=Path),
    help="Destination JSON file.",
)
@click_odb
def dump_placement(reader: OdbReaderLike, placement_out: Path) -> None:
    """Write the crosspoint grid of the placed block to JSON."""
    payload = dump_block(reader.block, reader.dbunits)
    placement_out.write_text(json.dumps(payload))


if __name__ == "__main__":
    dump_placement()

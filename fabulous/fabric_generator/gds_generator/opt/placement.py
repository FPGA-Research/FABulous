"""Placed geometry of a hardened tile, read back from the ASIC flow.

`Placement` is the in-memory form of the JSON that `FABulous.DumpPlacement`
writes. Both post-placement optimisations work on it through one connectivity
walk: a single-input single-output cell is traversed as a buffer, so the nets it
joins form one logical net, and the leaves of a logical net are the cells on it
that are neither buffers nor single-pin cells. The walk is direction-free, which
is what lets an input port, its feed-through buffer and the matching output port
land in one logical net.
"""

import json
import re
from collections import defaultdict
from dataclasses import dataclass
from functools import cached_property
from pathlib import Path
from typing import Literal, get_args

from fabulous.custom_exception import GDSFlowError

PinIO = Literal["INPUT", "OUTPUT", "INOUT"]

INDEXED_PIN = re.compile(r"^(?P<bus>.+)\[(?P<index>\d+)\]$")
"""A placed pin of a bus, `bus[index]`."""

_PIN_IO_VALUES: frozenset[str] = frozenset(get_args(PinIO))


def _pin_io(value: str, where: str) -> PinIO:
    """Narrow a dumped IO type string, naming `where` it came from on failure."""
    if value not in _PIN_IO_VALUES:
        raise GDSFlowError(f"{where}: unknown IO type {value!r}")
    return value  # type: ignore[return-value]


@dataclass(frozen=True)
class PlacedInstance:
    """A placed cell, located by the centre of its bounding box in microns."""

    name: str
    master: str
    x: float
    y: float


@dataclass(frozen=True)
class PlacedPin:
    """A placed block port, located by the centre of its pin shape in microns."""

    name: str
    io: PinIO
    x: float
    y: float


@dataclass(frozen=True)
class Terminal:
    """One instance pin on a net."""

    instance: str
    pin: str
    io: PinIO


@dataclass(frozen=True)
class PlacedNet:
    """A signal net with the block ports and instance pins it connects."""

    name: str
    ports: tuple[str, ...]
    terminals: tuple[Terminal, ...]


@dataclass(frozen=True)
class Placement:
    """Die, instances, ports and signal nets of a placed block."""

    die: tuple[float, float, float, float]
    instances: dict[str, PlacedInstance]
    pins: dict[str, PlacedPin]
    nets: dict[str, PlacedNet]

    @classmethod
    def from_json(cls, path: Path) -> "Placement":
        """Load a dump written by `FABulous.DumpPlacement`.

        A port or terminal whose IO type is not INPUT, OUTPUT or INOUT fails
        the load with a ValueError naming it.

        Parameters
        ----------
        path : Path
            The JSON file the dump step wrote.

        Returns
        -------
        Placement
            The loaded geometry and connectivity.
        """
        raw = json.loads(path.read_text())
        x0, y0, x1, y1 = (float(v) for v in raw["die"])
        instances = {
            name: PlacedInstance(name, entry["master"], entry["x"], entry["y"])
            for name, entry in raw["instances"].items()
        }
        pins = {
            name: PlacedPin(
                name, _pin_io(entry["io"], f"port {name}"), entry["x"], entry["y"]
            )
            for name, entry in raw["pins"].items()
        }
        nets = {
            name: PlacedNet(
                name,
                tuple(entry["bterms"]),
                tuple(
                    Terminal(
                        instance, pin, _pin_io(io, f"net {name} pin {instance}/{pin}")
                    )
                    for instance, pin, io in entry["iterms"]
                ),
            )
            for name, entry in raw["nets"].items()
        }
        return cls((x0, y0, x1, y1), instances, pins, nets)

    @property
    def width(self) -> float:
        """Die width in microns."""
        return self.die[2] - self.die[0]

    @property
    def height(self) -> float:
        """Die height in microns."""
        return self.die[3] - self.die[1]

    @cached_property
    def _terminals_by_instance(self) -> dict[str, tuple[tuple[str, Terminal], ...]]:
        """Index every (net, terminal) by the instance the terminal belongs to."""
        grouped: dict[str, list[tuple[str, Terminal]]] = defaultdict(list)
        for net in self.nets.values():
            for terminal in net.terminals:
                grouped[terminal.instance].append((net.name, terminal))
        return {name: tuple(entries) for name, entries in grouped.items()}

    @cached_property
    def _net_by_port(self) -> dict[str, str]:
        """Index the net name carrying each block port."""
        return {port: net.name for net in self.nets.values() for port in net.ports}

    def is_buffer(self, instance: str) -> bool:
        """Return True for a cell with exactly one signal input and one output."""
        entries = self._terminals_by_instance.get(instance, ())
        return len(entries) == 2 and {t.io for _, t in entries} == {"INPUT", "OUTPUT"}

    def is_leaf(self, instance: str) -> bool:
        """Return True for a multi-pin cell that is not a buffer."""
        return len(
            self._terminals_by_instance.get(instance, ())
        ) >= 2 and not self.is_buffer(instance)

    def net_of_port(self, port: str) -> PlacedNet:
        """Return the net a block port sits on.

        Parameters
        ----------
        port : str
            Name of the block port.

        Returns
        -------
        PlacedNet
            The signal net carrying the port.

        Raises
        ------
        GDSFlowError
            If no signal net carries the port.
        """
        if (net_name := self._net_by_port.get(port)) is None:
            raise GDSFlowError(f"Port {port} is not on any signal net")
        return self.nets[net_name]

    def logical_net(self, net: str) -> frozenset[str]:
        """Return the names of every net joined to `net` through buffers."""
        seen: set[str] = set()
        stack = [net]
        while stack:
            current = stack.pop()
            if current in seen:
                continue
            seen.add(current)
            for terminal in self.nets[current].terminals:
                if not self.is_buffer(terminal.instance):
                    continue
                for other_net, _ in self._terminals_by_instance[terminal.instance]:
                    if other_net not in seen:
                        stack.append(other_net)
        return frozenset(seen)

    def leaves(self, net: str) -> tuple[PlacedInstance, ...]:
        """Return the leaf cells of the logical net containing `net`, by name."""
        names = {
            terminal.instance
            for member in self.logical_net(net)
            for terminal in self.nets[member].terminals
            if self.is_leaf(terminal.instance)
        }
        return tuple(self.instances[name] for name in sorted(names))

    def leaf_pins(self, net: str) -> tuple[tuple[str, str], ...]:
        """Return every leaf terminal of the logical net containing `net`.

        Parameters
        ----------
        net : str
            Name of one net of the logical net.

        Returns
        -------
        tuple[tuple[str, str], ...]
            `(instance, pin)` of every terminal of a leaf cell on the logical
            net, sorted, so a caller can move the pin the net reaches.
        """
        return tuple(
            sorted(
                (terminal.instance, terminal.pin)
                for member in self.logical_net(net)
                for terminal in self.nets[member].terminals
                if self.is_leaf(terminal.instance)
            )
        )

    def ports_of_logical_net(self, net: str) -> frozenset[str]:
        """Return every block port on the logical net containing `net`."""
        return frozenset(
            port for member in self.logical_net(net) for port in self.nets[member].ports
        )

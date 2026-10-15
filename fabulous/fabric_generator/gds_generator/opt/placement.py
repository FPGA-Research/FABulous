"""The crosspoint grid of a hardened tile, read back from the ASIC flow.

`Placement` is the in-memory form of the JSON that `FABulous.DumpPlacement`
writes: the die, the two border coordinates of every frame net, and one
`PlacedLatch` per occupied crosspoint. The walk that identifies a latch runs in
the OpenROAD interpreter, so nothing here re-derives connectivity.
"""

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Self

from fabulous.custom_exception import GDSFlowError
from fabulous.fabric_definition.configmem import Crosspoint


@dataclass(frozen=True)
class PlacedLatch:
    """A placed configuration latch and the frame pins that reach it.

    The two pin names are what lets a proposal move the latch to other frame
    lines without re-reading the netlist.
    """

    crosspoint: Crosspoint
    instance: str
    x: float
    y: float
    data_pin: str
    strobe_pin: str


@dataclass(frozen=True)
class Placement:
    """Die, frame border pins and placed latches of a hardened tile.

    `data_y` and `strobe_x` give the entry and exit coordinate of each frame net
    on the axis its trunk does not run along, which is the only coordinate that
    differs between the two border pins of one chain.
    """

    die: tuple[float, float, float, float]
    data_y: dict[int, tuple[float, float]]
    strobe_x: dict[int, tuple[float, float]]
    latches: tuple[PlacedLatch, ...]

    @classmethod
    def from_json(cls, path: Path) -> Self:
        """Load a dump written by `FABulous.DumpPlacement`.

        Parameters
        ----------
        path : Path
            The JSON file the dump step wrote.

        Returns
        -------
        Self
            The loaded grid.

        Raises
        ------
        GDSFlowError
            If the file is missing a field the dump always writes, which means
            a different version of the step wrote it.
        """
        raw = json.loads(path.read_text())
        try:
            return cls(
                die=tuple(raw["die"]),  # type: ignore[arg-type]
                data_y={int(k): tuple(v) for k, v in raw["data_y"].items()},  # type: ignore[misc]
                strobe_x={int(k): tuple(v) for k, v in raw["strobe_x"].items()},  # type: ignore[misc]
                latches=tuple(
                    PlacedLatch(
                        crosspoint=Crosspoint(entry["frame"], entry["data_bit"]),
                        instance=entry["instance"],
                        x=entry["x"],
                        y=entry["y"],
                        data_pin=entry["data_pin"],
                        strobe_pin=entry["strobe_pin"],
                    )
                    for entry in raw["latches"]
                ),
            )
        except (KeyError, TypeError) as exc:
            raise GDSFlowError(
                f"{path} is not a FABulous placement dump: {exc}"
            ) from exc

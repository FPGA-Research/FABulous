"""Dump the placed geometry and signal connectivity of a block to JSON.

The OpenROAD interpreter has no scipy, so this script only extracts. Every
algorithm that reads the dump lives on the librelane side in
`fabulous.fabric_generator.gds_generator.opt`.
"""

import json
from pathlib import Path

import click
from librelane.scripts.odbpy.reader import click_odb

from fabulous.fabric_generator.gds_generator.script.odb_protocol import (
    OdbReaderLike,
    odbBlockLike,
    odbBoxLike,
)

_SUPPLY_TYPES = frozenset({"POWER", "GROUND"})


def _centre(box: odbBoxLike, dbu: float) -> tuple[float, float]:
    """Return the centre of a database box in microns."""
    return (
        (box.xMin() + box.xMax()) / 2 / dbu,
        (box.yMin() + box.yMax()) / 2 / dbu,
    )


def dump_block(block: odbBlockLike, dbu: float) -> dict:
    """Collect die, instances, ports and signal nets of a placed block.

    Supply nets and supply terminals are dropped, so every listed terminal
    carries a signal.

    Parameters
    ----------
    block : odbBlockLike
        The placed block.
    dbu : float
        Database units per micron, used to report every coordinate in microns.

    Returns
    -------
    dict
        The JSON-ready payload with `die`, `instances`, `pins` and `nets`.

    Raises
    ------
    ValueError
        If an instance is unplaced or a signal port has no placed pin, since
        both mean the block has not been through placement.
    """
    die = block.getDieArea()
    instances: dict[str, dict] = {}
    for inst in block.getInsts():
        if not inst.isPlaced():
            raise ValueError(
                f"Instance {inst.getName()} is not placed. Run this step after "
                "placement."
            )
        x, y = _centre(inst.getBBox(), dbu)
        instances[inst.getName()] = {
            "master": inst.getMaster().getName(),
            "x": x,
            "y": y,
        }

    pins: dict[str, dict] = {}
    for bterm in block.getBTerms():
        if bterm.getSigType() in _SUPPLY_TYPES:
            continue
        bpins = bterm.getBPins()
        if not bpins:
            raise ValueError(
                f"Port {bterm.getName()} has no placed pin. Run this step after "
                "IO placement."
            )
        x, y = _centre(bpins[0].getBBox(), dbu)
        pins[bterm.getName()] = {"io": bterm.getIoType(), "x": x, "y": y}

    nets: dict[str, dict] = {}
    for net in block.getNets():
        if net.getSigType() in _SUPPLY_TYPES:
            continue
        nets[net.getName()] = {
            "bterms": [bterm.getName() for bterm in net.getBTerms()],
            "iterms": [
                [
                    iterm.getInst().getName(),
                    iterm.getMTerm().getName(),
                    iterm.getIoType(),
                ]
                for iterm in net.getITerms()
                if iterm.getSigType() not in _SUPPLY_TYPES
            ],
        }

    return {
        "die": [
            die.xMin() / dbu,
            die.yMin() / dbu,
            die.xMax() / dbu,
            die.yMax() / dbu,
        ],
        "instances": instances,
        "pins": pins,
        "nets": nets,
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
    """Write the placed geometry and connectivity of the block to JSON."""
    payload = dump_block(reader.block, reader.dbunits)
    placement_out.write_text(json.dumps(payload))


if __name__ == "__main__":
    dump_placement()

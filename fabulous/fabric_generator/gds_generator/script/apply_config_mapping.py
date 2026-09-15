"""Move configuration latch pins onto the frame port nets a mapping proposed.

Runs in the OpenROAD interpreter on the ODB `Floorplan` built from the
synthesised netlist. Only pins whose net differs from the target move, and a
pin that is not directly on a frame port net is reported rather than moved,
because the walk that produced the list never looked past such a driver.
"""

import json
import re
from pathlib import Path

import click
from librelane.scripts.odbpy.reader import click_odb

from fabulous.fabric_generator.gds_generator.script.odb_protocol import (
    OdbReaderLike,
    odbBlockLike,
)

FRAME_PORT_NET = re.compile(r"^(FrameData|FrameStrobe)\[\d+\]$")


def apply(
    block: odbBlockLike, targets: dict[str, dict[str, str]]
) -> tuple[int, list[str]]:
    """Connect every listed latch pin to the frame port net named for it.

    Parameters
    ----------
    block : odbBlockLike
        The block to rewire.
    targets : dict[str, dict[str, str]]
        `{instance: {pin: net}}`, the absolute target of every latch pin.

    Returns
    -------
    tuple[int, list[str]]
        How many pins moved and one message per pin that could not be moved.
    """
    moved = 0
    errors: list[str] = []
    for instance_name, pins in targets.items():
        inst = block.findInst(instance_name)
        if inst is None:
            errors.append(f"instance {instance_name} is not in the block")
            continue
        for pin_name, net_name in pins.items():
            iterm = inst.findITerm(pin_name)
            if iterm is None:
                errors.append(f"{instance_name} has no pin {pin_name}")
                continue
            current = iterm.getNet()
            current_name = None if current is None else current.getName()
            on_frame_port = (
                current is not None
                and current_name is not None
                and FRAME_PORT_NET.match(current_name) is not None
                and any(
                    bterm.getName() == current_name for bterm in current.getBTerms()
                )
            )
            if not on_frame_port:
                errors.append(
                    f"{instance_name}/{pin_name} sits on net {current_name}, not "
                    "directly on a frame port net"
                )
                continue
            if current_name == net_name:
                continue
            target = block.findNet(net_name)
            if target is None:
                errors.append(f"target net {net_name} is not in the block")
                continue
            iterm.disconnect()
            iterm.connect(target)
            moved += 1
    return moved, errors


@click.command()
@click.option(
    "--reconnect",
    required=True,
    type=click.Path(exists=True, dir_okay=False, readable=True, path_type=Path),
    help="JSON reconnection list, `{instance: {pin: net}}`.",
)
@click.option(
    "--report",
    required=True,
    type=click.Path(dir_okay=False, writable=True, path_type=Path),
    help="Destination JSON report.",
)
@click_odb
def apply_reconnections(reader: OdbReaderLike, reconnect: Path, report: Path) -> None:
    """Rewire the block and report what moved, leaving the verdict to the step."""
    moved, errors = apply(reader.block, json.loads(reconnect.read_text()))
    report.write_text(json.dumps({"reconnected": moved, "errors": errors}))


if __name__ == "__main__":
    apply_reconnections()

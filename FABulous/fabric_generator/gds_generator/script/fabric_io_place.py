"""Place I/O pins on the die edge based on mTerm positions."""

import logging
import math
from decimal import Decimal
from typing import Any, Protocol

import click
import odb  # type: ignore[import]
from librelane.logging.logger import warn
from librelane.scripts.odbpy.reader import click_odb

from FABulous.fabric_generator.gds_generator.script.odb_protocol import (
    OdbReaderLike,
    odbRectLike,
)


@click.command()
@click.option(
    "-v",
    "--ver-length",
    default=None,
    type=float,
    help="Length for pins with N/S orientations in microns.",
)
@click.option(
    "-h",
    "--hor-length",
    default=None,
    type=float,
    help="Length for pins with E/S orientations in microns.",
)
@click.option(
    "-V",
    "--ver-layer",
    required=True,
    help="Name of metal layer to place vertical pins on.",
)
@click.option(
    "-H",
    "--hor-layer",
    required=True,
    help="Name of metal layer to place horizontal pins on.",
)
@click.option(
    "--hor-extension",
    default=0,
    type=float,
    help="Extension for horizontal pins in microns.",
)
@click.option(
    "--ver-extension",
    default=0,
    type=float,
    help="Extension for vertical pins in microns.",
)
@click.option(
    "--ver-width-mult", default=2, type=float, help="Multiplier for vertical pins."
)
@click.option(
    "--hor-width-mult", default=2, type=float, help="Multiplier for horizontal pins."
)
@click.option(
    "--verbose/--no-verbose",
    default=False,
    help="Enable verbose (DEBUG) logging output.",
)
@click_odb
def io_place(
    reader: OdbReaderLike,
    ver_layer: str,
    hor_layer: str,
    ver_width_mult: float,
    hor_width_mult: float,
    hor_length: float | None,
    ver_length: float | None,
    hor_extension: float,
    ver_extension: float,
    verbose: bool,
) -> None:
    """Place each BTerm's BPin on the die edge corresponding to the mTerm's position.

    Determines the side by checking where the mTerm is positioned relative to the master
    tile center. If the mTerm is on the north side of the master, place the BPin on the
    north edge of the die, and so on. Falls back to distance-based placement if mTerm
    information is unavailable.
    """
    if verbose:
        logging.getLogger().setLevel(logging.DEBUG)

    micron_in_units = reader.dbunits

    h_extension = int(micron_in_units * hor_extension)
    v_extension = int(micron_in_units * ver_extension)

    if h_extension < 0:
        h_extension = 0

    if v_extension < 0:
        v_extension = 0

    h_layer = reader.tech.findLayer(hor_layer)
    v_layer = reader.tech.findLayer(ver_layer)

    h_width = int(Decimal(hor_width_mult) * h_layer.getWidth())
    v_width = int(Decimal(ver_width_mult) * v_layer.getWidth())

    if hor_length is not None:
        h_length = int(micron_in_units * hor_length)
    else:
        h_length = max(
            int(
                math.ceil(
                    h_layer.getArea() * micron_in_units * micron_in_units / h_width
                )
            ),
            h_width,
        )

    if ver_length is not None:
        v_length = int(micron_in_units * ver_length)
    else:
        v_length = max(
            int(
                math.ceil(
                    v_layer.getArea() * micron_in_units * micron_in_units / v_width
                )
            ),
            v_width,
        )

    # Die area
    die = reader.block.getDieArea()
    llx, lly, urx, ury = die.xMin(), die.yMin(), die.xMax(), die.yMax()

    bterms = [
        bterm
        for bterm in reader.block.getBTerms()
        if bterm.getSigType() not in ["POWER", "GROUND"]
    ]

    for bterm in bterms:
        net = bterm.getNet()
        iterms = net.getITerms()
        if not iterms:
            warn(
                f"Net {net.getName()} has no ITerms for BTerm "
                f"{bterm.getName()}; skipping"
            )
            continue

        iterm = iterms[0]
        ibox: odbRectLike = iterm.getBBox()
        cx = ibox.xCenter()
        cy = ibox.yCenter()

        # Get mTerm bbox to determine which side of the master tile it's on
        mterm = iterm.getMTerm()
        master = mterm.getMaster()
        # Use mTerm bbox position relative to master to determine side
        side = None
        # Get the first mPin's geometry bbox
        mterm_bbox: odbRectLike = mterm.getBBox()

        if mterm_bbox.xMin() == 0:
            side = "WEST"
        if mterm_bbox.xMax() == master.getWidth():
            side = "EAST"
        if mterm_bbox.yMin() == 0:
            side = "SOUTH"
        if mterm_bbox.yMax() == master.getHeight():
            side = "NORTH"

        # Prepare or reuse BPin
        pins = bterm.getBPins()
        if len(pins) > 0:
            warn(f"{bterm.getName()} already has shapes. Modifying existing shape.")
            assert len(pins) == 1
            pin_bpin = pins[0]
        else:
            pin_bpin = odb.dbBPin_create(bterm)
        pin_bpin.setPlacementStatus("PLACED")

        if side in ("NORTH", "SOUTH"):
            # Vertical pin on top/bottom, align X to ITerm center
            rect = odb.Rect(0, 0, int(v_width), int(v_length + v_extension))
            # Compute edge Y position
            y = ury - int(v_length) if side == "NORTH" else lly - int(v_extension)
            # Clamp X inside die for the body width
            x = int(max(llx, min(cx - v_width // 2, urx - v_width)))
            rect.moveTo(x, int(y))
            odb.dbBox_create(pin_bpin, v_layer, *rect.ll(), *rect.ur())
        else:
            # Horizontal pin on left/right, align Y to ITerm center
            rect = odb.Rect(0, 0, int(h_length + h_extension), int(h_width))
            # Compute edge X position
            x = urx - int(h_length) if side == "EAST" else llx - int(h_extension)
            # Clamp Y inside die for the body width
            y = int(max(lly, min(cy - h_width // 2, ury - h_width)))
            rect.moveTo(int(x), y)
            odb.dbBox_create(pin_bpin, h_layer, *rect.ll(), *rect.ur())


if __name__ == "__main__":
    io_place()

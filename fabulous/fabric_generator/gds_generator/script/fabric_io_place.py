"""Place fabric-level signal BPins by stamping connected ITerm mTerm geometry."""

import click
import odb  # type: ignore[import]
from librelane.logging.logger import info, warn
from librelane.scripts.odbpy.reader import click_odb

from fabulous.fabric_generator.gds_generator.script.odb_protocol import OdbReaderLike


@click.command()
@click_odb
def io_place(reader: OdbReaderLike) -> None:
    """Stamp signal BTerm's BPin with the geometry of its driving/sinking ITerms."""
    stamped = 0
    deleted = 0
    for bterm in list(reader.block.getBTerms()):
        if bterm.getSigType() in ("POWER", "GROUND"):
            continue

        net = bterm.getNet()
        if net is None:
            continue

        existing = bterm.getBPins()
        if existing:
            warn(
                f"BTerm {bterm.getName()} already has {len(existing)} BPin(s); "
                "leaving them in place."
            )
            continue

        iterms = list(net.getITerms())
        if not iterms:
            odb.dbBTerm.destroy(bterm)
            if not net.getITerms() and not net.getBTerms():
                odb.dbNet.destroy(net)
            deleted += 1
            continue

        bpin = odb.dbBPin_create(bterm)
        for iterm in iterms:
            inst = iterm.getInst()
            inst_x, inst_y = inst.getLocation()
            for mpin in iterm.getMTerm().getMPins():
                for db in mpin.getGeometry():
                    odb.dbBox_create(
                        bpin,
                        db.getTechLayer(),
                        inst_x + db.xMin(),
                        inst_y + db.yMin(),
                        inst_x + db.xMax(),
                        inst_y + db.yMax(),
                    )
        bpin.setPlacementStatus("FIRM")
        stamped += 1

    info(f"Stamped {stamped} signal BPins; deleted {deleted} orphan BTerms.")


if __name__ == "__main__":
    io_place()

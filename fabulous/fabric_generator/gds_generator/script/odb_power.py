"""OpenDB script to connect power rails for FABulous fabric."""
#
# Original src: https://github.com/mole99/librelane_plugin_fabulous/blob/main/librelane_plugin_fabulous/scripts/odb_power.py
# OpenDB script for custom Power for FABulous fabric
# This script places vertical PDN straps on top
# of already existing straps in order to tell OpenROAD
# that they should be considered connected and are pins
#
# Copyright (c) 2023 Sylvain Munaut <tnt@246tNt.com>
# Copyright (c) 2025 Leo Moser <leo.moser@pm.me>
# Copyright (c) 2026 FABulous Contributors
# SPDX-License-Identifier: Apache-2.0
#

from typing import Any

import click
import odb
from librelane.logging.logger import info
from librelane.scripts.odbpy.reader import click_odb


@click.option(
    "--power-names",
    default=None,
    type=str,
    multiple=True,
    help="The name(s) of the power port(s). Repeat the option for multiple ports.",
)
@click.option(
    "--ground-names",
    default=None,
    type=str,
    multiple=True,
    help="The name(s) of the ground port(s). Repeat the option for multiple ports.",
)
@click.command()
@click_odb
def power(
    reader: Any,  # noqa: ANN401
    power_names: tuple[str],
    ground_names: tuple[str],
) -> None:
    """Cycle through VDD_NETS and GND_NETS for the tiles using a custom script."""
    info(f"propagated VDD_NETS are {power_names}")
    info(f"propagated GND_NETS are {ground_names}")

    # todo: run on multi-power test case
    for power_name in power_names:
        propagate_supply_net(reader, power_name, "POWER")

    for ground_name in ground_names:
        propagate_supply_net(reader, ground_name, "GROUND")


def propagate_supply_net(
    reader: Any,  # noqa: ANN401
    supply_name: str,
    supply_type: str,
) -> None:
    """Connect single  power rail for the tiles using a custom script."""
    # Create nets, if they don't exist yet
    net = reader.block.findNet(supply_name)
    if net is None:
        # Create net
        net = odb.dbNet.create(reader.block, supply_name)
        net.setSpecial()
        net.setSigType(supply_type)
        info(f"Created {supply_name} with type {supply_type}")

    supply_net = reader.block.findNet(supply_name)

    # Create wires
    supply_wire = odb.dbSWire.create(supply_net, "ROUTED")

    # Create bterms (top-level)
    supply_bterm = odb.dbBTerm.create(supply_net, supply_name)
    supply_bterm.setIoType("INOUT")
    supply_bterm.setSigType(supply_net.getSigType())
    supply_bterm.setSpecial()
    supply_bpin = odb.dbBPin_create(supply_bterm)

    # Connect instance-iterms to power nets,
    # draw the wires and pins
    for blk_inst in reader.block.getInsts():
        info(f"Instance: {blk_inst.getName()}")
        for iterm in blk_inst.getITerms():
            iterm_name = iterm.getMTerm().getName()
            iterm_sigtype = iterm.getMTerm().getSigType()

            if iterm_name == supply_name:
                info(f"Connecting {iterm_name} of type {iterm_sigtype}")
                iterm.connect(supply_net)

        inst_master = blk_inst.getMaster()

        # Now, for each power/ground mterm
        # Copy the geomtry of the pins to wires and top-level pins
        for master_mterm in inst_master.getMTerms():
            if master_mterm.getName() == supply_name:
                for mterm_mpins in master_mterm.getMPins():
                    for mpins_dbox in mterm_mpins.getGeometry():
                        metal_layer = mpins_dbox.getTechLayer()

                        if master_mterm.getName() == supply_name:
                            odb.dbSBox_create(
                                supply_wire,
                                metal_layer,
                                blk_inst.getLocation()[0] + mpins_dbox.xMin(),
                                blk_inst.getLocation()[1] + mpins_dbox.yMin(),
                                blk_inst.getLocation()[0] + mpins_dbox.xMax(),
                                blk_inst.getLocation()[1] + mpins_dbox.yMax(),
                                "STRIPE",
                            )
                            odb.dbBox_create(
                                supply_bpin,
                                metal_layer,
                                blk_inst.getLocation()[0] + mpins_dbox.xMin(),
                                blk_inst.getLocation()[1] + mpins_dbox.yMin(),
                                blk_inst.getLocation()[0] + mpins_dbox.xMax(),
                                blk_inst.getLocation()[1] + mpins_dbox.yMax(),
                            )

    supply_bpin.setPlacementStatus("FIRM")


if __name__ == "__main__":
    power()

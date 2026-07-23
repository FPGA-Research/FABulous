"""PCF constraint template generation for FABulous FPGA fabrics.

The `template.pcf` lists every constrainable I/O site on a fabric as a
commented `set_io` stub, grouped per tile and supertile. A user copies the
sites they need into their own PCF and replaces `<net>` with the top-level
port of their design.

Locations use the slash form (`X0Y0/A`) that the nextpnr `fabulous` uarch
accepts. Bidirectional I/O is addressed by its tile-slot letter, while
`InPass4`/`OutPass4` BELs are addressed by their port prefix (e.g.
`RAM2FAB_D0`), matching the uarch's BEL renaming.
"""

import string
from pathlib import Path

from fabulous.fabric_definition.bel import Bel
from fabulous.fabric_definition.fabric import Fabric

# I/O BEL primitives that can be constrained from a PCF. `InPass4`/`OutPass4`
# BELs are renamed by the nextpnr `fabulous` uarch to their port prefix, so
# their PCF slot is that prefix rather than the tile-slot letter.
_PORT_NAMED_IO_BEL_NAMES = frozenset(
    {
        "InPass4_frame_config",
        "OutPass4_frame_config",
        "InPass4_frame_config_mux",
        "OutPass4_frame_config_mux",
    }
)
_IO_BEL_NAMES = _PORT_NAMED_IO_BEL_NAMES | {"IO_1_bidirectional_frame_config_pass"}

_TEMPLATE_HEADER = [
    "# FABulous PCF template: every constrainable I/O site on this fabric.",
    "# Uncomment a line and replace <net> with the top-level port of your",
    "# design that maps to it. Synthesize with -iopad so each port has an",
    "# I/O buffer for nextpnr to constrain.",
]


def _io_bel_slot(bel: Bel, letter: str) -> str:
    """Return the nextpnr BEL slot name used in a `set_io` location.

    Mirrors the `fabulous` uarch naming: bidirectional I/O keeps its tile-slot
    letter, while `InPass4`/`OutPass4` BELs are addressed by their port
    prefix (e.g. `RAM2FAB_D0`).

    Parameters
    ----------
    bel : Bel
        The I/O BEL being constrained.
    letter : str
        The tile-slot letter (`A`, `B`, ...) of the BEL.

    Returns
    -------
    str
        The slot name to use after the `X<col>Y<row>/` prefix.
    """
    if bel.name in _PORT_NAMED_IO_BEL_NAMES:
        return bel.prefix.rsplit("_", 1)[0]
    return letter


def gen_pcf_template(fabric: Fabric) -> str:
    """Generate the fabric's `template.pcf` constraint template.

    Parameters
    ----------
    fabric : Fabric
        Fabric object containing tile information.

    Returns
    -------
    str
        The PCF template, listing every constrainable I/O site as a commented
        `set_io` stub grouped per tile and supertile.
    """
    constrain_str = list(_TEMPLATE_HEADER)

    for y, row in enumerate(fabric.tile):
        for x, tile in enumerate(row):
            if tile is None:
                continue
            tile_io_sites = []
            for i, bel in enumerate(tile.bels):
                if bel.name in _IO_BEL_NAMES:
                    letter = string.ascii_uppercase[i]
                    slot = _io_bel_slot(bel, letter)
                    tile_io_sites.append(f"# set_io <net> X{x}Y{y}/{slot}")
            if tile_io_sites:
                constrain_str.append(f"# Tile X{x}Y{y}")
                constrain_str.extend(tile_io_sites)

    for base_fx, base_fy, super_tile in fabric.iter_super_tile_placements():
        if not super_tile.bels:
            continue

        tx_local, ty_local = super_tile.get_master_tile_coords()
        ftx = base_fx + tx_local
        fty = base_fy + ty_local

        bel_offset = len(fabric.tile[fty][ftx].bels)
        super_tile_io_sites = []
        for i, bel in enumerate(super_tile.bels):
            if bel.externalInput or bel.externalOutput:
                letter = string.ascii_uppercase[bel_offset + i]
                slot = _io_bel_slot(bel, letter)
                super_tile_io_sites.append(f"# set_io <net> X{ftx}Y{fty}/{slot}")
        if super_tile_io_sites:
            constrain_str.append(f"# SuperTile {super_tile.name} X{ftx}Y{fty}")
            constrain_str.extend(super_tile_io_sites)

    return "\n".join(constrain_str)


def write_pcf_template(fabric: Fabric, output_file: Path) -> None:
    """Write the `template.pcf` constraint template for the given fabric.

    Parameters
    ----------
    fabric : Fabric
        Fabric object containing tile information.
    output_file : Path
        File to write the PCF template to.
    """
    output_file.write_text(gen_pcf_template(fabric), encoding="utf-8")

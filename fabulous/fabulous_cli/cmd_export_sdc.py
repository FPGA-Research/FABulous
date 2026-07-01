"""Export SDC command implementation for the FABulous CLI.

This module builds a tile's switch-matrix connectivity graph, selects a
feedback-vertex set, and writes `set_disable_timing` constraints that break
combinational loops so STA can level-order the timing graph.
"""

import argparse
from pathlib import Path
from typing import TYPE_CHECKING

from cmd2 import Cmd, Cmd2ArgumentParser, with_argparser, with_category
from loguru import logger

from fabulous.custom_exception import CommandError
from fabulous.fabric_cad.gen_sdc import (
    FVS_BATCH_FRACTION,
    FVS_SINGLE_MAX,
    export_tile_sdc,
)
from fabulous.fabric_definition.supertile import SuperTile

if TYPE_CHECKING:
    from fabulous.fabric_definition.tile import Tile
    from fabulous.fabulous_cli.fabulous_cli import FABulous_CLI

CMD_FABRIC_FLOW = "Fabric Flow"

export_sdc_parser = Cmd2ArgumentParser()
export_sdc_parser.add_argument(
    "tile",
    type=str,
    help="Export a loop-break SDC for this tile's switch matrix",
    completer=lambda self: self.fab.getTiles(),
)
export_sdc_parser.add_argument(
    "-o",
    "--output",
    type=Path,
    default=None,
    help="Override the output SDC file path",
    completer=Cmd.path_complete,
)
export_sdc_parser.add_argument(
    "--fvs-single-max",
    type=int,
    default=FVS_SINGLE_MAX,
    help=(
        "Strongly connected components up to this size are reduced one vertex "
        f"per round (default: {FVS_SINGLE_MAX})"
    ),
)
export_sdc_parser.add_argument(
    "--fvs-batch-fraction",
    type=float,
    default=FVS_BATCH_FRACTION,
    help=(
        "Fraction of vertices removed per round from larger components "
        f"(default: {FVS_BATCH_FRACTION})"
    ),
)


@with_category(CMD_FABRIC_FLOW)
@with_argparser(export_sdc_parser)
def do_export_sdc(self: "FABulous_CLI", args: argparse.Namespace) -> None:
    """Export an SDC that breaks a tile's combinational loops for STA.

    Builds the tile's switch-matrix connectivity graph, selects a
    feedback-vertex set, and writes `set_disable_timing` constraints. A super
    tile expands to one SDC per constituent sub-tile, since each sub-tile owns
    its own switch matrix. Each SDC goes to its tile directory unless
    `-o`/`--output` overrides it; for a super tile `-o` is treated as the
    destination directory. Raises `CommandError` if the fabric is not loaded or
    `tile` names a tile that is not in the fabric.
    """
    if not self.fabricLoaded:
        raise CommandError("Need to load fabric first")

    fabric = self.fabulousAPI.fabric
    try:
        resolved = fabric.getTileByName(args.tile)
    except KeyError as e:
        raise CommandError(str(e)) from e

    if isinstance(resolved, SuperTile):
        tile_names = [t.name for t in resolved.tiles]
    else:
        tile_names = [resolved.name]

    # The intra-tile jump wires (tile.wireList) are populated only on the
    # placed grid instances, not on the tileDic/SuperTile definitions, so
    # resolve each name to its placed instance.
    placed: dict[str, Tile] = {}
    for row in fabric.tile:
        for tile in row:
            if tile is not None and tile.name in tile_names:
                placed.setdefault(tile.name, tile)

    missing = [name for name in tile_names if name not in placed]
    if missing:
        raise CommandError(f"Tile(s) not placed in the fabric: {', '.join(missing)}")

    multi = len(tile_names) > 1
    for name in tile_names:
        tile = placed[name]
        if args.output is None:
            out = tile.matrixDir.parent / f"{name}_loop_break.sdc"
        elif multi:
            out = args.output / f"{name}_loop_break.sdc"
        else:
            out = args.output
        export_tile_sdc(
            tile,
            out,
            single_max=args.fvs_single_max,
            batch_fraction=args.fvs_batch_fraction,
        )
        logger.info(f"Exported loop-break SDC to {out}")

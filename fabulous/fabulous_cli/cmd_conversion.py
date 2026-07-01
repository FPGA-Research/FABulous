"""Switch matrix conversion commands for the FABulous CLI.

This module provides the `list_to_csv` and `csv_to_list` commands, which convert a
switch matrix between its `.list` connection-pair form and its `.csv` matrix-grid
form. They delegate to the conversion helpers in `gen_helper` and add no fabric flow
of their own, so they are available without a loaded fabric.
"""

import argparse
from pathlib import Path
from typing import TYPE_CHECKING

from cmd2 import Cmd, Cmd2ArgumentParser, with_argparser, with_category
from loguru import logger

from fabulous.custom_exception import CommandError
from fabulous.fabric_generator.gen_fabric.gen_helper import (
    bootstrap_matrix_from_list,
    bootstrap_switch_matrix,
    csv_to_list,
    list_to_csv,
)

if TYPE_CHECKING:
    from fabulous.fabulous_cli.fabulous_cli import FABulous_CLI

CMD_TOOLS = "Tools"

list_to_csv_parser = Cmd2ArgumentParser()
list_to_csv_parser.add_argument(
    "list_file",
    type=Path,
    help="The .list switch matrix file to convert",
    completer=Cmd.path_complete,
)
list_to_csv_parser.add_argument(
    "csv_file",
    type=Path,
    nargs=argparse.OPTIONAL,
    default=None,
    help="Output .csv file (defaults to the list file with a .csv suffix)",
    completer=Cmd.path_complete,
)
list_to_csv_parser.add_argument(
    "--tile",
    "-t",
    type=str,
    default=None,
    help="Bootstrap the full port grid from this tile in the loaded fabric "
    "instead of deriving ports from the list file (requires load_fabric)",
    completer=lambda self: self.fab.getTiles(),
)
list_to_csv_parser.add_argument(
    "--preserve-order",
    action="store_true",
    default=False,
    help="Encode the mux input order as per-row 1-based indices instead of 1",
)

csv_to_list_parser = Cmd2ArgumentParser()
csv_to_list_parser.add_argument(
    "csv_file",
    type=Path,
    help="The .csv switch matrix file to convert",
    completer=Cmd.path_complete,
)
csv_to_list_parser.add_argument(
    "list_file",
    type=Path,
    nargs=argparse.OPTIONAL,
    default=None,
    help="Output .list file (defaults to the csv file with a .list suffix)",
    completer=Cmd.path_complete,
)


@with_category(CMD_TOOLS)
@with_argparser(list_to_csv_parser)
def do_list_to_csv(self: "FABulous_CLI", args: argparse.Namespace) -> None:
    """Convert a .list switch matrix file into its .csv matrix representation.

    Without `--tile` the port set is derived from the connections in the
    list file. With `--tile` the full port grid of that tile in the loaded
    fabric is used, matching what fabric generation produces.
    """
    list_file = args.list_file
    csv_file = args.csv_file or list_file.with_suffix(".csv")

    if args.tile:
        if not self.fabricLoaded:
            raise CommandError("Need to load fabric first")
        tile = self.fabulousAPI.fabric.getTileByName(args.tile)
        logger.info(f"Bootstrapping switch matrix grid from tile {args.tile}")
        bootstrap_switch_matrix(tile, csv_file)
    else:
        logger.warning(
            "Bootstrapping switch matrix grid from list file. Port might be incomplete."
        )
        tile_name = list_file.stem.removesuffix("_switch_matrix")
        bootstrap_matrix_from_list(list_file, csv_file, tile_name)

    list_to_csv(list_file, csv_file, args.preserve_order)
    logger.info(f"Converted {list_file} to {csv_file}")


@with_category(CMD_TOOLS)
@with_argparser(csv_to_list_parser)
def do_csv_to_list(_self: "FABulous_CLI", args: argparse.Namespace) -> None:
    """Convert a .csv switch matrix file into its .list representation."""
    csv_file = args.csv_file
    list_file = args.list_file or csv_file.with_suffix(".list")

    csv_to_list(csv_file, list_file)
    logger.info(f"Converted {csv_file} to {list_file}")

"""Helper inspection commands for the FABulous REPL.

Small commands that print fabric objects (Bels, tiles) to the console for
inspection. Grouped as a CommandSet so they can be registered and, in future,
managed independently of the core REPL.
"""

import pprint
from typing import Annotated

from cmd2 import with_annotated, with_category
from cmd2.annotated import Argument
from loguru import logger

from fabulous.custom_exception import CommandError
from fabulous.fabulous_repl.command_set_base import CMD_HELPER, ReplCommandSet


def _safe_pformat(obj: object) -> str:
    """Pretty-print `obj` for logging through loguru's colorized sink."""
    text = pprint.pformat(obj, width=200)
    return text.replace("{", "{{").replace("}", "}}").replace("<", r"\<")


class HelperCommandSet(ReplCommandSet):
    """Commands for inspecting fabric objects from the REPL."""

    @with_category(CMD_HELPER)
    @with_annotated
    def do_print_bel(
        self,
        bel: Annotated[
            str,
            Argument(
                help_text="A Bel",
                completer=lambda self: [
                    bel.name for bel in self._cmd.fabulousAPI.getBels()
                ],
            ),
        ],
    ) -> None:
        """Print a Bel object to the console."""
        repl = self._cmd
        if not repl.fabric_loaded:
            raise CommandError("Need to load fabric first")

        for bel_obj in repl.fabulousAPI.getBels():
            if bel_obj.name == bel:
                logger.info(f"\n{_safe_pformat(bel_obj)}")
                return
        raise CommandError(f"Bel {bel} not found in fabric")

    @with_category(CMD_HELPER)
    @with_annotated
    def do_print_tile(
        self,
        tile: Annotated[
            str,
            Argument(
                help_text="A tile",
                completer=lambda self: [
                    tile.name for tile in self._cmd.fabulousAPI.getTiles()
                ],
            ),
        ],
    ) -> None:
        """Print a tile object to the console."""
        repl = self._cmd
        if not repl.fabric_loaded:
            raise CommandError("Need to load fabric first")

        if (tile_obj := repl.fabulousAPI.getTile(tile)) or (
            tile_obj := repl.fabulousAPI.getSuperTile(tile)
        ):
            logger.info(f"\n{_safe_pformat(tile_obj)}")
        else:
            raise CommandError(f"Tile {tile} not found in fabric")

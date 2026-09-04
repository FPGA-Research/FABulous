"""Helper inspection commands for the FABulous REPL.

Small commands that print fabric objects (Bels, tiles) to the console for
inspection, or register RTL as custom primitives. Grouped as a CommandSet so
they can be registered and, in future, managed independently of the core REPL.
"""

import pprint
from pathlib import Path
from typing import Annotated

from cmd2 import Choices, Cmd, CompletionItem, with_annotated
from cmd2.annotated import Argument, Option
from loguru import logger

from fabulous.custom_exception import CommandError
from fabulous.fabric_generator.gen_fabric.fabric_automation import addBelsToPrim
from fabulous.fabric_generator.parser.parse_hdl import parseBelFile
from fabulous.fabulous_repl.command_set_base import CMD_HELPER, ReplCommandSet


def _safe_pformat(obj: object) -> str:
    """Pretty-print `obj` for logging through loguru's colorized sink."""
    text = pprint.pformat(obj, width=200)
    return text.replace("{", "{{").replace("}", "}}").replace("<", r"\<")


class HelperCommandSet(ReplCommandSet):
    """Commands for inspecting fabric objects from the REPL."""

    DEFAULT_CATEGORY = CMD_HELPER

    @with_annotated
    def do_print_bel(
        self,
        bel: Annotated[
            str,
            Argument(
                help_text="A Bel",
                choices_provider=lambda self: Choices(
                    [
                        CompletionItem(bel.name)
                        for bel in self._cmd.fabulousAPI.getBels()
                    ]
                ),
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

    @with_annotated
    def do_print_tile(
        self,
        tile: Annotated[
            str,
            Argument(
                help_text="A tile",
                choices_provider=lambda self: Choices(
                    [
                        CompletionItem(tile.name)
                        for tile in self._cmd.fabulousAPI.getTiles()
                    ]
                ),
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

    @with_annotated
    def do_add_as_custom_prim(
        self,
        rtl_files: Annotated[
            list[Path],
            Argument(
                help_text="RTL (BEL) files to add as blackbox primitives",
                completer=Cmd.path_complete,
            ),
        ],
        support_vectors: Annotated[
            bool,
            Option(
                "--support-vectors",
                "-v",
                help_text="Emit vector ports instead of scalar ports",
            ),
        ] = False,
        overwrite: Annotated[
            bool,
            Option(
                "--overwrite",
                "-f",
                help_text="Replace primitives that are already in the prims file",
            ),
        ] = False,
    ) -> None:
        """Add RTL files as blackbox primitives to `user_design/custom_prims.v`."""
        repl = self._cmd
        rtl_files = [f if f.is_absolute() else repl.projectDir / f for f in rtl_files]
        missing = [f for f in rtl_files if not f.is_file()]
        if missing:
            raise CommandError(f"File(s) not found: {', '.join(map(str, missing))}")

        prims_file = repl.projectDir / "user_design" / "custom_prims.v"
        addBelsToPrim(
            prims_file,
            [parseBelFile(f) for f in rtl_files],
            support_vectors,
            overwrite,
        )

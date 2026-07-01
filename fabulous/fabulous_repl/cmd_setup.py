"""Setup and project-management commands for the FABulous REPL.

Install tooling, load a fabric, and clone tiles.
"""

import re
from pathlib import Path
from typing import Annotated

from cmd2 import Cmd, with_annotated, with_category
from cmd2.annotated import Argument, Option
from loguru import logger

from fabulous.fabulous_repl.command_set_base import (
    CMD_FABRIC_FLOW,
    CMD_GUI,
    CMD_HELPER,
    CMD_SETUP,
    CMD_USER_DESIGN_FLOW,
    ReplCommandSet,
)
from fabulous.fabulous_repl.helper import (
    allow_blank,
    clone_tile_directory,
    install_fabulator,
    install_oss_cad_suite,
    register_tile_in_fabric_csv,
    resolve_tile,
)
from fabulous.fabulous_settings import get_context


class SetupCommandSet(ReplCommandSet):
    """Install tooling, load a fabric, and clone tiles."""

    @with_category(CMD_SETUP)
    @allow_blank
    @with_annotated
    def do_install_oss_cad_suite(
        self,
        destination_folder: Annotated[
            Path | None,
            Argument(help_text="Destination folder for the installation"),
        ] = None,
        update: Annotated[
            bool,
            Option(
                "--update",
                help_text="Update/override existing installation, if exists",
            ),
        ] = False,
    ) -> None:
        """Download and extract the latest OSS CAD suite.

        The installation will set the `FAB_OSS_CAD_SUITE` environment variable
        in the `.env` file.
        """
        dest_dir = (
            destination_folder if destination_folder is not None else get_context().root
        )
        install_oss_cad_suite(dest_dir, update)

    @with_category(CMD_SETUP)
    @allow_blank
    @with_annotated
    def do_install_FABulator(
        self,
        destination_folder: Annotated[
            Path | None,
            Argument(help_text="Destination folder for the installation"),
        ] = None,
    ) -> None:
        """Download and install the latest version of FABulator.

        Sets the the FABULATOR_ROOT environment variable in the .env file.
        """
        dest_dir = (
            destination_folder if destination_folder is not None else get_context().root
        )

        if not install_fabulator(dest_dir):
            raise RuntimeError("FABulator installation failed")

        logger.info("FABulator successfully installed")

    @with_category(CMD_SETUP)
    @allow_blank
    @with_annotated
    def do_load_fabric(
        self,
        file: Annotated[
            Path | None, Argument(help_text="Path to the target file")
        ] = None,
    ) -> None:
        """Load 'fabric.csv' file and generate an internal representation of the fabric.

        Parse input arguments and set a few internal variables to assist fabric
        generation.
        """
        repl = self._cmd
        # if no argument is given will use the one set by set_fabric_csv
        # else use the argument

        logger.info("Loading fabric")
        if file is None:
            if repl.csvFile.exists():
                logger.info(
                    "Found fabric.csv in the project directory loading that file as "
                    "the definition of the fabric"
                )
                repl.fabulousAPI.loadFabric(repl.csvFile)
            else:
                raise FileNotFoundError(
                    f"No argument is given and the csv file is set at {repl.csvFile}, "
                    "but the file does not exist"
                )
        else:
            repl.fabulousAPI.loadFabric(file)
            repl.csvFile = file

        repl.fabric_loaded = True
        tile_by_path = [
            f.stem for f in (repl.projectDir / "Tile/").iterdir() if f.is_dir()
        ]
        tile_by_fabric = list(repl.fabulousAPI.fabric.tileDic.keys())
        super_tile_by_fabric = list(repl.fabulousAPI.fabric.superTileDic.keys())
        repl.all_tile = list(
            set(tile_by_path) & set(tile_by_fabric + super_tile_by_fabric)
        )

        if not repl.all_tile:
            logger.error(
                "No tiles found in the project tiles directory that match the tiles "
                "defined in the fabric.csv"
            )
            raise ValueError

        proj_dir = get_context().proj_dir
        if (proj_dir / f"{repl.fabulousAPI.fabric.name}_geometry.csv").exists():
            repl.enable_category(CMD_GUI)

        repl.enable_category(CMD_FABRIC_FLOW)
        repl.enable_category(CMD_USER_DESIGN_FLOW)
        repl.enable_category(CMD_HELPER)
        logger.info("Complete")

    @with_category(CMD_SETUP)
    @with_annotated
    def do_clone_tile(
        self,
        src_tile: Annotated[
            str,
            Argument(
                help_text=(
                    "Name of the tile to clone (looked up in Tile/) or path to "
                    "a tile dir"
                )
            ),
        ],
        dst_tile: Annotated[
            str,
            Argument(
                help_text=(
                    "Name for the cloned tile (placed in Tile/) or path to "
                    "destination dir"
                )
            ),
        ],
        no_register: Annotated[
            bool,
            # store_true (not the inferred BooleanOptionalAction): a flag literally
            # named --no-register would otherwise be read as the negation form and
            # set False, inverting the intended "present means skip" semantics.
            Option(
                "--no-register",
                action="store_true",
                help_text="Skip adding the new tile to fabric.csv",
            ),
        ] = False,
    ) -> None:
        """Clone a tile or supertile directory and register it in fabric.csv.

        Copies the source tile directory to a new destination directory, renaming
        all files and replacing all internal references to match the new tile name.
        Also appends the required Tile/Supertile entries to fabric.csv.

        Notes
        -----
        Only works correctly for tiles that follow the default FABulous tile
        naming scheme, where the tile name is used as a prefix for all files
        and internal references (e.g. `LUT4AB.csv`,
        `LUT4AB_switch_matrix.list`).
        """
        repl = self._cmd
        tile_dir = repl.projectDir / "Tile"
        src_dir = resolve_tile(src_tile, tile_dir)
        dst_dir = resolve_tile(dst_tile, tile_dir)

        if not src_dir.is_dir():
            logger.error(f"Tile '{src_tile}' not found at {src_dir}")
            return
        if not (src_dir / f"{src_dir.name}.csv").exists():
            logger.error(
                f"'{src_tile}' at {src_dir} is not a valid FABulous tile"
                f" (missing {src_dir.name}.csv)"
            )
            return
        if not re.fullmatch(r"[A-Za-z][A-Za-z0-9_]*", dst_dir.name):
            logger.error(
                f"'{dst_tile}' is not a valid tile name"
                " (must start with a letter, contain only letters, digits, underscores)"
            )
            return
        if dst_dir.exists():
            logger.error(f"Destination '{dst_tile}' already exists at {dst_dir}")
            return

        clone_tile_directory(src_dir, dst_dir, src_dir.name, dst_dir.name)
        logger.info(f"Cloned tile '{src_tile}' -> '{dst_tile}'")

        if not no_register:
            register_tile_in_fabric_csv(repl.csvFile, dst_dir)
            logger.info(f"Updated {repl.csvFile} with entries for '{dst_tile}'")

    @with_category(CMD_SETUP)
    @with_annotated
    def do_list_to_csv(
        self,
        # Named `input`/`output` because the parameter name is the CLI
        # argument name shown in help; renaming would change the interface.
        input: Annotated[  # noqa: A002
            Path,
            Argument(help_text="Input switch matrix file", completer=Cmd.path_complete),
        ],
        output: Annotated[
            Path,
            Argument(
                help_text="Output switch matrix file", completer=Cmd.path_complete
            ),
        ],
        preserve_list_order: Annotated[
            bool,
            Option(
                "--preserve-list-order",
                action="store_true",
                help_text="Keep the mux-input order (MSB-first) so the conversion is "
                "order-faithful; otherwise inputs fall back to column order (legacy)",
            ),
        ] = False,
    ) -> None:
        """Convert a `.list` switch matrix file to `.csv`."""
        logger.info(
            "Format conversion only; connectivity is not validated against any "
            "tile configuration."
        )
        self._cmd.fabulousAPI.add_list_to_matrix(input, output, preserve_list_order)
        logger.info(f"Converted {input} to {output}")

    @with_category(CMD_SETUP)
    @with_annotated
    def do_csv_to_list(
        self,
        # Named `input`/`output` because the parameter name is the CLI
        # argument name shown in help; renaming would change the interface.
        input: Annotated[  # noqa: A002
            Path,
            Argument(help_text="Input switch matrix file", completer=Cmd.path_complete),
        ],
        output: Annotated[
            Path,
            Argument(
                help_text="Output switch matrix file", completer=Cmd.path_complete
            ),
        ],
        preserve_list_order: Annotated[
            bool,
            Option(
                "--preserve-list-order",
                action="store_true",
                help_text="Keep the mux-input order (MSB-first) so the conversion is "
                "order-faithful; otherwise inputs fall back to column order (legacy)",
            ),
        ] = False,
    ) -> None:
        """Convert a `.csv` switch matrix file to `.list`."""
        logger.info(
            "Format conversion only; connectivity is not validated against any "
            "tile configuration."
        )
        self._cmd.fabulousAPI.add_matrix_to_list(input, output, preserve_list_order)
        logger.info(f"Converted {input} to {output}")

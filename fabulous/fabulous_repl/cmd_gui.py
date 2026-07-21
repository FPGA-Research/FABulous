"""GUI-launcher commands for the FABulous REPL.

Launch the FABulator, OpenROAD, and KLayout GUIs.
"""

import argparse
import shutil
import subprocess as sp
import tempfile
from pathlib import Path
from typing import Annotated, cast

from cmd2 import with_annotated, with_category
from cmd2.annotated import Argument, Option
from loguru import logger

from fabulous.custom_exception import CommandError, EnvironmentNotSet
from fabulous.fabulous_repl.command_set_base import (
    CMD_GUI,
    CMD_TOOLS,
    ReplCommandSet,
)
from fabulous.fabulous_repl.helper import (
    get_file_path,
)
from fabulous.fabulous_settings import get_context

# klayout layer property file naming differs by PDK:
# - ihp-sg13g2 ships sg13g2.lyp under its single-variant install dir.
# - gf180mcu ships a single gf180mcu.lyp shared by every variant (A/B/C/D).
# - Other PDKs (e.g. sky130A/B) follow the variant-name convention.
KLAYOUT_LAYER_FILE_NAMES: dict[str, str] = {
    "ihp-sg13g2": "sg13g2.lyp",
    "gf180mcuA": "gf180mcu.lyp",
    "gf180mcuB": "gf180mcu.lyp",
    "gf180mcuC": "gf180mcu.lyp",
    "gf180mcuD": "gf180mcu.lyp",
}


class GuiCommandSet(ReplCommandSet):
    """Launch the FABulator, OpenROAD, and KLayout GUIs."""

    @with_category(CMD_GUI)
    def do_start_FABulator(self, *_ignored: str) -> None:
        """Start FABulator if an installation can be found.

        If no installation can be found, a warning is produced.
        """
        repl = self._cmd
        logger.info("Checking for FABulator installation")
        fabulator_root = get_context().fabulator_root
        if shutil.which("mvn") is None:
            raise FileNotFoundError(
                "Application mvn (Java Maven) not found in PATH",
                " please install it to use FABulator",
            )

        if fabulator_root is None:
            logger.warning("FABULATOR_ROOT environment variable not set.")
            logger.warning(
                "Install FABulator (https://github.com/FPGA-Research-Manchester/FABulator)"
                " and set the FABULATOR_ROOT environment variable to the root directory"
                " to use this feature."
            )
            return

        if not Path(fabulator_root).exists():
            raise EnvironmentNotSet(
                f"FABULATOR_ROOT environment variable set to {fabulator_root} "
                "but the directory does not exist."
            )

        logger.info(f"Found FABulator installation at {fabulator_root}")
        logger.info("Trying to start FABulator...")

        startup_cmd = ["mvn", "-f", f"{fabulator_root}/pom.xml", "javafx:run"]
        try:
            if repl.verbose:
                # log FABulator output to the FABulous shell
                sp.Popen(startup_cmd)
            else:
                # discard FABulator output
                sp.Popen(startup_cmd, stdout=sp.DEVNULL, stderr=sp.DEVNULL)

        except sp.SubprocessError as e:
            raise CommandError(
                "Failed to start FABulator. Please ensure that the FABULATOR_ROOT "
                "environment variable is set correctly and that FABulator is installed."
            ) from e

    @with_annotated
    @with_category(CMD_TOOLS)
    def do_start_openroad_gui(
        self,
        file: Annotated[str | None, Argument(help_text="file to open")] = None,
        tile: Annotated[
            str | None,
            Option(
                "--tile",
                help_text="launch GUI to view a specific tile",
                completer=lambda self: [
                    tile.name for tile in self._cmd.fabulousAPI.getTiles()
                ],
            ),
        ] = None,
        fabric: Annotated[
            bool, Option("--fabric", help_text="launch GUI to view the entire fabric")
        ] = False,
        last_run: Annotated[
            bool, Option("--last-run", help_text="launch GUI to view last run")
        ] = False,
        head: Annotated[
            int, Option("--head", help_text="number of item to select from")
        ] = 10,
    ) -> None:
        """Start OpenROAD GUI if an installation can be found.

        If no installation can be found, a warning is produced.
        """
        repl = self._cmd
        logger.info("Checking for OpenROAD installation")
        openroad = get_context().openroad_path
        file_name: str
        if fabric and tile is not None:
            raise CommandError("Please specify either --fabric or --tile, not both")

        if file is None:
            db_file: str = get_file_path(
                repl.projectDir,
                argparse.Namespace(last_run=last_run, fabric=fabric, tile=tile),
                "odb",
                show_count=head,
            )
        else:
            db_file = file
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".tcl", delete=False
        ) as script_file:
            # script_file.name contains the full filesystem path to the temp file
            script_file.write(f"read_db {db_file}\n")
            file_name = script_file.name
        logger.info(f"Start OpenROAD GUI with odb: {db_file}")
        try:
            sp.run(
                [
                    str(openroad),
                    "-gui",
                    str(file_name),
                ]
            )
        finally:
            Path(file_name).unlink(missing_ok=True)

    @with_annotated
    @with_category(CMD_TOOLS)
    def do_start_klayout_gui(
        self,
        file: Annotated[str | None, Argument(help_text="file to open")] = None,
        tile: Annotated[
            str | None,
            Option(
                "--tile",
                help_text="launch GUI to view a specific tile",
                completer=lambda self: [
                    tile.name for tile in self._cmd.fabulousAPI.getTiles()
                ],
            ),
        ] = None,
        fabric: Annotated[
            bool, Option("--fabric", help_text="launch GUI to view the entire fabric")
        ] = False,
        last_run: Annotated[
            bool, Option("--last-run", help_text="launch GUI to view last run")
        ] = False,
        head: Annotated[
            int, Option("--head", help_text="number of item to select from")
        ] = 10,
    ) -> None:
        """Start KLayout GUI if an installation can be found.

        If no installation can be found, a warning is produced.
        """
        repl = self._cmd
        logger.info("Checking for klayout installation")
        klayout = get_context().klayout_path
        if fabric and tile is not None:
            raise CommandError("Please specify either --fabric or --tile, not both")
        if file is None:
            gds_file: str = get_file_path(
                repl.projectDir,
                argparse.Namespace(last_run=last_run, fabric=fabric, tile=tile),
                "gds",
                show_count=head,
            )
        else:
            gds_file = file
        pdk_name = cast("str", get_context().pdk)
        pdk_root = cast("Path", get_context().pdk_root)
        layer_file_name = KLAYOUT_LAYER_FILE_NAMES.get(pdk_name, f"{pdk_name}.lyp")
        layer_file = (
            pdk_root / pdk_name / "libs.tech" / "klayout" / "tech" / layer_file_name
        )
        logger.info(f"Start klayout GUI with gds: {gds_file}")
        logger.info(f"Layer property file: {layer_file!s}")
        sp.run(
            [
                str(klayout),
                "-l",
                str(layer_file),
                gds_file,
            ]
        )

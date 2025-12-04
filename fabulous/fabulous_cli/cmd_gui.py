"""GUI command implementation for the FABulous CLI.

This module provides the GUI command functionality for the FABulous command-line
interface. It implements a unified `gui` command with subcommands for different
GUI tools:
- fabulator: FABulator visual fabric editor
- openroad: OpenROAD GUI for viewing .odb database files
- klayout: KLayout GUI for viewing .gds layout files

The GUI command uses Typer's native subcommand support to provide a clean
hierarchical command structure.

Note: These functions are designed to be called from FABulous_CLI instance methods,
so they receive 'self' as the first parameter.
"""

import shutil
import subprocess as sp
import tempfile
from pathlib import Path
from typing import TYPE_CHECKING, Annotated

import typer
from cmd2 import with_category
from loguru import logger

from fabulous.custom_exception import CommandError, EnvironmentNotSet
from fabulous.fabulous_settings import get_context

if TYPE_CHECKING:
    from fabulous.fabulous_cli.fabulous_cli import FABulous_CLI

CMD_GUI = "GUI"


def _gui_fabulator(self: "FABulous_CLI") -> None:
    """Start FABulator if an installation can be found.

    Parameters
    ----------
    self : FABulous_CLI
        The CLI instance with access to settings and context.

    Raises
    ------
    FileNotFoundError
        If Maven (mvn) is not found in PATH.
    EnvironmentNotSet
        If FABULATOR_ROOT environment variable points to non-existent directory.
    CommandError
        If FABulator fails to start.
    """
    logger.info("Checking for FABulator installation")
    fabulatorRoot = get_context().fabulator_root
    if shutil.which("mvn") is None:
        raise FileNotFoundError(
            "Application mvn (Java Maven) not found in PATH",
            " please install it to use FABulator",
        )

    if fabulatorRoot is None:
        logger.warning("FABULATOR_ROOT environment variable not set.")
        logger.warning(
            "Install FABulator (https://github.com/FPGA-Research-Manchester/FABulator)"
            " and set the FABULATOR_ROOT environment variable to the root directory"
            " to use this feature."
        )
        return

    if not Path(fabulatorRoot).exists():
        raise EnvironmentNotSet(
            f"FABULATOR_ROOT environment variable set to {fabulatorRoot} "
            "but the directory does not exist."
        )

    logger.info(f"Found FABulator installation at {fabulatorRoot}")
    logger.info("Trying to start FABulator...")

    startupCmd = ["mvn", "-f", f"{fabulatorRoot}/pom.xml", "javafx:run"]
    try:
        if self.verbose:
            # log FABulator output to the FABulous shell
            sp.Popen(startupCmd)
        else:
            # discard FABulator output
            sp.Popen(startupCmd, stdout=sp.DEVNULL, stderr=sp.DEVNULL)

    except sp.SubprocessError as e:
        raise CommandError(
            "Failed to start FABulator. Please ensure that the FABULATOR_ROOT "
            "environment variable is set correctly and that FABulator is installed."
        ) from e


def _gui_openroad(
    self: "FABulous_CLI",
    file: Annotated[
        str | None,
        typer.Argument(help="file to open"),
    ] = None,
    tile: Annotated[
        str | None,
        typer.Option("--tile", help="launch GUI to view a specific tile"),
    ] = None,
    fabric: Annotated[
        bool,
        typer.Option("--fabric", help="launch GUI to view the entire fabric"),
    ] = False,
    last_run: Annotated[
        bool,
        typer.Option("--last-run", help="launch GUI to view last run"),
    ] = False,
    head: Annotated[
        int,
        typer.Option("--head", help="number of item to select from"),
    ] = 10,
) -> None:
    # ruff: noqa: E501
    """Start OpenROAD GUI if an installation can be found.

    Parameters
    ----------
    self : "FABulous_CLI"
        The CLI instance with access to settings and context.
    file : Annotated[str | None, typer.Argument(help="file to open")]
        Optional path to .odb file to open.
    tile : Annotated[str | None, typer.Option("--tile", help="launch GUI to view a specific tile")]
        Optional tile name to view.
    fabric : Annotated[bool, typer.Option("--fabric", help="launch GUI to view the entire fabric")]
        Whether to view the entire fabric.
    last_run : Annotated[bool, typer.Option("--last-run", help="launch GUI to view last run")]
        Whether to view the last run.
    head : Annotated[int, typer.Option("--head", help="number of item to select from")]
        Number of items to select from.

    Raises
    ------
    CommandError
        If both --fabric and --tile are specified.
    """
    logger.info("Checking for OpenROAD installation")
    openroad = get_context().openroad_path
    file_name: str
    if fabric and tile is not None:
        raise CommandError("Please specify either --fabric or --tile, not both")

    if file is None:
        db_file: str = self._get_file_path(
            "odb", tile=tile, fabric=fabric, last_run=last_run, show_count=head
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
    sp.run(
        [
            str(openroad),
            "-gui",
            str(file_name),
        ]
    )


def _gui_klayout(
    self: "FABulous_CLI",
    file: Annotated[
        str | None,
        typer.Argument(help="file to open"),
    ] = None,
    tile: Annotated[
        str | None,
        typer.Option("--tile", help="launch GUI to view a specific tile"),
    ] = None,
    fabric: Annotated[
        bool,
        typer.Option("--fabric", help="launch GUI to view the entire fabric"),
    ] = False,
    last_run: Annotated[
        bool,
        typer.Option("--last-run", help="launch GUI to view last run"),
    ] = False,
    head: Annotated[
        int,
        typer.Option("--head", help="number of item to select from"),
    ] = 10,
) -> None:
    # ruff: noqa: E501
    """Start klayout GUI if an installation can be found.

    Parameters
    ----------
    self : "FABulous_CLI"
        The CLI instance with access to settings and context.
    file : Annotated[str | None, typer.Argument(help="file to open")]
        Optional path to .gds file to open.
    tile : Annotated[str | None, typer.Option("--tile", help="launch GUI to view a specific tile")]
        Optional tile name to view.
    fabric : Annotated[bool, typer.Option("--fabric", help="launch GUI to view the entire fabric")]
        Whether to view the entire fabric.
    last_run : Annotated[bool, typer.Option("--last-run", help="launch GUI to view last run")]
        Whether to view the last run.
    head : Annotated[int, typer.Option("--head", help="number of item to select from")]
        Number of items to select from.

    Raises
    ------
    CommandError
        If both --fabric and --tile are specified.
    """
    logger.info("Checking for klayout installation")
    klayout = get_context().klayout_path
    if fabric and tile is not None:
        raise CommandError("Please specify either --fabric or --tile, not both")

    if file is None:
        gds_file: str = self._get_file_path(
            "gds", tile=tile, fabric=fabric, last_run=last_run, show_count=head
        )
    else:
        gds_file = file
    if get_context().pdk == "ihp-sg13g2":
        layer_file = (
            (get_context().pdk_root) / "libs.tech" / "klayout" / "tech" / "sg12g2.lyp"
        )
    else:
        layer_file = (
            (get_context().pdk_root)
            / "libs.tech"
            / "klayout"
            / "tech"
            / f"{get_context().pdk}.lyp"
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


@with_category(CMD_GUI)
def do_gui(self: "FABulous_CLI") -> typer.Typer:
    """GUI tools for viewing and editing FABulous designs.

    Parameters
    ----------
    self : FABulous_CLI
        The CLI instance with access to settings and context.

    Returns
    -------
    typer.Typer
        A Typer application instance with GUI subcommands registered.

    Examples
    --------
        gui fabulator
        gui openroad --last-run
        gui klayout --tile MyTile
        gui openroad my_design.odb
    """
    app = typer.Typer(help="GUI tools for FABulous")

    # Create wrapper functions without 'self' parameter for Typer
    # These wrappers call the actual implementation functions with self bound
    def fabulator_wrapper() -> None:
        """Start FABulator GUI."""
        return _gui_fabulator(self)

    def openroad_wrapper(
        file: Annotated[str | None, typer.Argument(help="file to open")] = None,
        tile: Annotated[
            str | None,
            typer.Option("--tile", help="launch GUI to view a specific tile"),
        ] = None,
        fabric: Annotated[
            bool, typer.Option("--fabric", help="launch GUI to view the entire fabric")
        ] = False,
        last_run: Annotated[
            bool, typer.Option("--last-run", help="launch GUI to view last run")
        ] = False,
        head: Annotated[
            int, typer.Option("--head", help="number of item to select from")
        ] = 10,
    ) -> None:
        """Start OpenROAD GUI."""
        return _gui_openroad(self, file, tile, fabric, last_run, head)

    def klayout_wrapper(
        file: Annotated[str | None, typer.Argument(help="file to open")] = None,
        tile: Annotated[
            str | None,
            typer.Option("--tile", help="launch GUI to view a specific tile"),
        ] = None,
        fabric: Annotated[
            bool, typer.Option("--fabric", help="launch GUI to view the entire fabric")
        ] = False,
        last_run: Annotated[
            bool, typer.Option("--last-run", help="launch GUI to view last run")
        ] = False,
        head: Annotated[
            int, typer.Option("--head", help="number of item to select from")
        ] = 10,
    ) -> None:
        """Start KLayout GUI."""
        return _gui_klayout(self, file, tile, fabric, last_run, head)

    # Register the wrapper functions as subcommands
    app.command(name="fabulator")(fabulator_wrapper)
    app.command(name="openroad")(openroad_wrapper)
    app.command(name="klayout")(klayout_wrapper)

    return app

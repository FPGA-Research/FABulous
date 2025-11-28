# Copyright 2021 University of Manchester
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#      http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
#
# SPDX-License-Identifier: Apache-2.0
"""FABulous command-line interface module.

This module provides the main command-line interface for the FABulous FPGA framework. It
includes interactive and batch mode support for fabric generation, bitstream creation,
simulation, and project management.
"""

import argparse
import csv
import os
import pickle
import pprint
import subprocess as sp
import sys
import tkinter as tk
import traceback
from collections.abc import Callable
from pathlib import Path
from typing import Annotated, Literal, cast

import typer
from cmd2 import (
    Cmd,
    Settable,
    Statement,
    categorize,
    with_category,
)
from FABulous_bit_gen import genBitstream
from loguru import logger
from pick import pick

from fabulous.custom_exception import CommandError, InvalidFileType
from fabulous.fabric_generator.code_generator.code_generator_Verilog import (
    VerilogCodeGenerator,
)
from fabulous.fabric_generator.code_generator.code_generator_VHDL import (
    VHDLCodeGenerator,
)
from fabulous.fabric_generator.gds_generator.steps.tile_optimisation import OptMode
from fabulous.fabric_generator.gen_fabric.fabric_automation import (
    generateCustomTileConfig,
)
from fabulous.fabric_generator.parser.parse_csv import parseTilesCSV
from fabulous.fabulous_api import FABulous_API
from fabulous.fabulous_cli import cmd_gui, cmd_synthesis
from fabulous.fabulous_cli.helper import (
    CommandPipeline,
    copy_verilog_files,
    install_fabulator,
    install_oss_cad_suite,
    make_hex,
    remove_dir,
)
from fabulous.fabulous_cli.typer_cli_plugin import Cmd2TyperPlugin, CompleterSpec
from fabulous.fabulous_settings import get_context

META_DATA_DIR = ".FABulous"

CMD_SETUP = "Setup"
CMD_FABRIC_FLOW = "Fabric Flow"
CMD_USER_DESIGN_FLOW = "User Design Flow"
CMD_HELPER = "Helper"
CMD_OTHER = "Other"
CMD_GUI = "GUI"
CMD_SCRIPT = "Script"
CMD_TOOLS = "Tools"


INTO_STRING = rf"""
     ______      ____        __
    |  ____/\   |  _ \      | |
    | |__ /  \  | |_) |_   _| | ___  _   _ ___
    |  __/ /\ \ |  _ <| | | | |/ _ \| | | / __|
    | | / ____ \| |_) | |_| | | (_) | |_| \__ \
    |_|/_/    \_\____/ \__,_|_|\___/ \__,_|___/


Welcome to FABulous shell
You have started the FABulous shell with following options:
{" ".join(sys.argv[1:])}

Type help or ? to list commands
To see documentation for a command type:
    help <command>
or
    ?<command>

To execute a shell command type:
    shell <command>
or
    !<command>

The shell support tab completion for commands and files

To run the complete FABulous flow with the default project, run the following command:
    run_FABulous_fabric
    run_FABulous_bitstream ./user_design/sequential_16bit_en.v
    run_simulation fst ./user_design/sequential_16bit_en.bin
"""


class FABulous_CLI(Cmd2TyperPlugin):
    """FABulous command-line interface for FPGA fabric generation and management.

    This class provides an interactive and non-interactive command-line interface
    for the FABulous FPGA framework. It supports fabric generation, bitstream creation,
    project management, and various utilities for FPGA development workflow.

    Parameters
    ----------
    writerType : str | None
        The writer type to use for generating fabric.
    force : bool
        If True, force operations without confirmation, by default False
    interactive : bool
        If True, run in interactive CLI mode, by default False
    verbose : bool
        If True, enable verbose logging, by default False
    debug : bool
        If True, enable debug logging, by default False

    Attributes
    ----------
    intro : str
        Introduction message displayed when CLI starts
    prompt : str
        Command prompt string displayed to users
    fabulousAPI : FABulous_API
        Instance of the FABulous API for fabric operations
    projectDir : pathlib.Path
        Current project directory path
    top : str
        Top-level module name for synthesis
    allTile : list[str]
        List of all tile names in the current fabric
    csvFile : pathlib.Path
        Path to the fabric CSV definition file
    extension : str
        File extension for HDL files ("v" for Verilog, "vhd" for VHDL)
    script : str
        Batch script commands to execute
    force : bool
        If true, force operations without confirmation
    interactive : bool
        If true, run in interactive CLI mode

    Notes
    -----
    This CLI extends the cmd.Cmd class to provide command completion, help system,
    and command history. It supports both interactive mode and batch script execution.
    """

    # All commands have been migrated to Typer
    typer_skip_commands: set[str] = set()

    intro: str = INTO_STRING
    prompt: str = "FABulous> "
    fabulousAPI: FABulous_API
    projectDir: Path
    top: str
    allTile: list[str]
    csvFile: Path
    extension: str = "v"
    script: str = ""
    force: bool = False
    interactive: bool = True
    max_job: int = 4
    fabricLoaded: bool = False

    def __init__(
        self,
        writerType: str | None,
        force: bool = False,
        interactive: bool = False,
        verbose: bool = False,
        debug: bool = False,
        max_job: int = 8,
    ) -> None:
        """Initialize the FABulous CLI instance.

        Parameters
        ----------
        writerType : str | None
            Type of writer to use for output generation.
        force : bool
            Force execution without confirmation prompts.
        interactive : bool
            Enable interactive mode for user input.
        verbose : bool
            Enable verbose logging output.
        debug : bool
            Enable debug mode for detailed logging.
        max_job : int
            Maximum number of parallel jobs (-1 for CPU count).
        """
        super().__init__(
            persistent_history_file=f"{get_context().proj_dir}/{META_DATA_DIR}/.fabulous_history",
            allow_cli_args=False,
        )
        self.self_in_py = True
        logger.info(f"Running at: {get_context().proj_dir}")

        if max_job == -1:
            if c := os.cpu_count():
                self.max_job = c
            else:
                logger.warning("Unable to determine CPU count, defaulting to 4")
                self.max_job = 4
        else:
            self.max_job = max_job

        if writerType == "verilog":
            self.fabulousAPI = FABulous_API(VerilogCodeGenerator())
        elif writerType == "vhdl":
            self.fabulousAPI = FABulous_API(VHDLCodeGenerator())
        else:
            logger.critical(
                f"Invalid writer type: {writerType}\n"
                "Valid options are 'verilog' or 'vhdl'"
            )
            sys.exit(1)

        self.projectDir = get_context().proj_dir
        self.add_settable(
            Settable("projectDir", Path, "The directory of the project", self)
        )

        self.tiles = []
        self.superTiles = []
        self.csvFile = Path(self.projectDir / "fabric.csv").resolve()
        self.add_settable(
            Settable(
                "csvFile", Path, "The fabric file ", self, completer=Cmd.path_complete
            )
        )

        self.verbose = verbose
        self.add_settable(Settable("verbose", bool, "verbose output", self))

        self.force = force
        self.add_settable(Settable("force", bool, "force execution", self))

        self.interactive = interactive
        self.debug = debug
        if e := get_context().editor:
            logger.info("Setting to use editor from .FABulous/.env file")
            self.editor = e

        if isinstance(self.fabulousAPI.writer, VHDLCodeGenerator):
            self.extension = "vhdl"
        else:
            self.extension = "v"

        categorize(self.do_alias, CMD_OTHER)
        categorize(self.do_edit, CMD_OTHER)
        categorize(self.do_shell, CMD_OTHER)
        categorize(self.do_exit, CMD_OTHER)
        categorize(self.do_quit, CMD_OTHER)
        categorize(self.do_q, CMD_OTHER)
        categorize(self.do_set, CMD_OTHER)
        categorize(self.do_history, CMD_OTHER)
        categorize(self.do_shortcuts, CMD_OTHER)
        categorize(self.do_help, CMD_OTHER)
        categorize(self.do_macro, CMD_OTHER)
        categorize(self.do_run_tcl, CMD_SCRIPT)
        categorize(self.do_run_pyscript, CMD_SCRIPT)

        self.tcl = tk.Tcl()
        for fun in dir(self.__class__):
            f = getattr(self, fun)
            if fun.startswith("do_") and callable(f):
                name = fun.strip("do_")

                # Create a wrapper that calls through onecmd
                def create_tcl_wrapper(cmd_name: str) -> Callable[..., None]:
                    """Create a TCL command wrapper for the given command name.

                    Parameters
                    ----------
                    cmd_name : str
                        Name of the command to wrap.

                    Returns
                    -------
                    Callable[..., None]
                        Wrapper function that routes TCL calls to cmd2's onecmd.
                    """

                    def tcl_wrapper(*args: object, **_kwargs: object) -> None:
                        """Execute the command through cmd2's onecmd interface.

                        Parameters
                        ----------
                        *args : object
                            Positional arguments passed to the command.
                        **_kwargs : object
                            Keyword arguments (unused but required by TCL).
                        """
                        try:
                            # Build the command string with arguments
                            if args:
                                cmd_str = f"{cmd_name} {' '.join(str(a) for a in args)}"
                            else:
                                cmd_str = cmd_name
                            # Call through onecmd to use Typer's argument parsing
                            self.onecmd(cmd_str)
                        except Exception:  # noqa: BLE001 - Catching all exceptions is ok here
                            import traceback

                            traceback.print_exc()
                            logger.error(
                                "TCL command failed. Please check the logs for details."
                            )
                            raise

                    return tcl_wrapper

                self.tcl.createcommand(name, create_tcl_wrapper(name))

        self.disable_category(
            CMD_FABRIC_FLOW, "Fabric Flow commands are disabled until fabric is loaded"
        )
        self.disable_category(
            CMD_USER_DESIGN_FLOW,
            "User Design Flow commands are disabled until fabric is loaded",
        )
        self.disable_category(
            CMD_GUI, "GUI commands are disabled until gen_gen_geometry is run"
        )
        self.disable_category(
            CMD_HELPER, "Helper commands are disabled until fabric is loaded"
        )

    def onecmd(
        self, statement: Statement | str, *, add_to_history: bool = True
    ) -> bool:
        """Override the onecmd method to handle exceptions."""
        try:
            return super().onecmd(statement, add_to_history=add_to_history)
        except Exception as e:  # noqa: BLE001 - Catching all exceptions is ok here
            logger.debug(traceback.format_exc())
            logger.opt(exception=e).error(str(e).replace("<", r"\<"))
            self.exit_code = 1
            if self.interactive:
                return None
            return not self.force

    # Completer methods for tab completion
    def complete_tile_names(
        self, _text: str, _line: str, _begidx: int, _endidx: int
    ) -> list[str]:
        """Complete tile names from the loaded fabric."""
        if not self.fabricLoaded:
            return []
        return [tile.name for tile in self.fabulousAPI.getTiles()]

    def do_exit(self, *_ignored: str) -> bool:
        """Exit the FABulous shell and log info message."""
        logger.info("Exiting FABulous shell")
        return True

    def do_quit(self, *_ignored: str) -> None:
        """Exit the FABulous shell and log info message."""
        self.onecmd_plus_hooks("exit")

    def do_q(self, *_ignored: str) -> None:
        """Exit the FABulous shell and log info message."""
        self.onecmd_plus_hooks("exit")

    # Create a proper method reference that preserves docstring and attributes
    def do_synthesis(self, *args: object, **kwargs: object) -> None:
        """Run Yosys synthesis for the specified Verilog files.

        Performs FPGA synthesis using Yosys with the nextpnr JSON backend to synthesize
        Verilog designs and generate nextpnr-compatible JSON files for place-and-route
        with nextpnr.
        """
        return cmd_synthesis.do_synthesis(self, *args, **kwargs)

    # Copy over the original function's annotations and category decorator
    do_synthesis.__annotations__ = cmd_synthesis.do_synthesis.__annotations__
    do_synthesis.__wrapped__ = cmd_synthesis.do_synthesis

    @with_category(CMD_SETUP)
    def do_install_oss_cad_suite(
        self,
        destination_folder: Annotated[
            Path | None,
            typer.Argument(help="Destination folder for the installation"),
            CompleterSpec(Cmd.path_complete),
        ] = None,
        update: Annotated[
            bool,
            typer.Option(help="Update/override existing installation, if exists"),
        ] = False,
    ) -> None:
        """Download and extract the latest OSS CAD suite.

        The installation will set the `FAB_OSS_CAD_SUITE` environment variable
        in the `.env` file.
        """
        if destination_folder is None:
            dest_dir = get_context().user_config_dir
        else:
            dest_dir = destination_folder

        install_oss_cad_suite(dest_dir, update)

    @with_category(CMD_SETUP)
    def do_install_FABulator(
        self,
        destination_folder: Annotated[
            Path | None,
            typer.Argument(help="Destination folder for the installation"),
            CompleterSpec(Cmd.path_complete),
        ] = None,
    ) -> None:
        """Download and install the latest version of FABulator.

        Sets the the FABULATOR_ROOT environment variable in the .env file.
        """
        if destination_folder is None:
            dest_dir = get_context().root
        else:
            dest_dir = destination_folder

        if not install_fabulator(dest_dir):
            raise RuntimeError("FABulator installation failed")

        logger.info("FABulator successfully installed")

    @with_category(CMD_SETUP)
    def do_load_fabric(
        self,
        file: Annotated[
            Path | None,
            typer.Argument(help="Path to the target file"),
            CompleterSpec(Cmd.path_complete),
        ] = None,
    ) -> None:
        """Load 'fabric.csv' file and generate an internal representation of the fabric.

        Parse input arguments and set a few internal variables to assist fabric
        generation.
        """
        # if no argument is given will use the one set by set_fabric_csv
        # else use the argument

        logger.info("Loading fabric")
        # Handle empty string from TCL/cmd2 as None
        if file is None or (isinstance(file, str | Path) and str(file) == ""):
            if self.csvFile.exists():
                logger.info(
                    "Found fabric.csv in the project directory loading that file as "
                    "the definition of the fabric"
                )
                self.fabulousAPI.loadFabric(self.csvFile)
            else:
                raise FileNotFoundError(
                    f"No argument is given and the csv file is set at {self.csvFile}, "
                    "but the file does not exist"
                )
        else:
            file_path = Path(file) if isinstance(file, str) else file
            self.fabulousAPI.loadFabric(file_path)
            self.csvFile = file_path

        self.fabricLoaded = True
        tileByPath = [
            f.stem for f in (self.projectDir / "Tile/").iterdir() if f.is_dir()
        ]
        tileByFabric = list(self.fabulousAPI.fabric.tileDic.keys())
        superTileByFabric = list(self.fabulousAPI.fabric.superTileDic.keys())
        self.allTile = list(set(tileByPath) & set(tileByFabric + superTileByFabric))

        proj_dir = get_context().proj_dir
        if (proj_dir / "eFPGA_geometry.csv").exists():
            self.enable_category(CMD_GUI)

        self.enable_category(CMD_FABRIC_FLOW)
        self.enable_category(CMD_USER_DESIGN_FLOW)
        logger.info("Complete")

    @with_category(CMD_HELPER)
    def do_print_bel(
        self,
        bel_name: Annotated[
            str,
            typer.Argument(help="Name of the BEL to print"),
        ],
    ) -> None:
        """Print a Bel object to the console."""
        if not self.fabricLoaded:
            raise CommandError("Need to load fabric first")

        bels = self.fabulousAPI.getBels()
        for i in bels:
            if i.name == bel_name:
                logger.info(f"\n{pprint.pformat(i, width=200)}")
                return
        raise CommandError(f"Bel {bel_name} not found in fabric")

    @with_category(CMD_HELPER)
    def do_print_tile(
        self,
        tile_name: Annotated[
            str,
            typer.Argument(help="Tile to print"),
            CompleterSpec(complete_tile_names),
        ],
    ) -> None:
        """Print a tile object to the console."""
        if not self.fabricLoaded:
            raise CommandError("Need to load fabric first")

        if (tile := self.fabulousAPI.getTile(tile_name)) or (
            tile := self.fabulousAPI.getSuperTile(tile_name)
        ):
            logger.info(f"\n{pprint.pformat(tile, width=200)}")
        else:
            raise CommandError(f"Tile {tile_name} not found in fabric")

    @with_category(CMD_FABRIC_FLOW)
    def do_gen_config_mem(
        self,
        tiles: Annotated[
            list[str],
            typer.Argument(help="A list of tile to generate configuration memory"),
            CompleterSpec(complete_tile_names),
        ],
    ) -> None:
        """Generate configuration memory of the given tile.

        Parsing input arguments and calling `genConfigMem`.

        Logs generation processes for each specified tile.
        """
        logger.info(f"Generating Config Memory for {' '.join(tiles)}")
        for i in tiles:
            logger.info(f"Generating configMem for {i}")
            self.fabulousAPI.setWriterOutputFile(
                self.projectDir / f"Tile/{i}/{i}_ConfigMem.{self.extension}"
            )
            self.fabulousAPI.genConfigMem(
                i, self.projectDir / f"Tile/{i}/{i}_ConfigMem.csv"
            )
        logger.info("ConfigMem generation complete")

    @with_category(CMD_FABRIC_FLOW)
    def do_gen_switch_matrix(
        self,
        tiles: Annotated[
            list[str],
            typer.Argument(help="A list of tile to generate swtich matrix"),
            CompleterSpec(complete_tile_names),
        ],
    ) -> None:
        """Generate switch matrix of given tile.

        Parsing input arguments and calling `genSwitchMatrix`.

        Also logs generation process for each specified tile.
        """
        logger.info(f"Generating switch matrix for {' '.join(tiles)}")
        for i in tiles:
            logger.info(f"Generating switch matrix for {i}")
            self.fabulousAPI.setWriterOutputFile(
                self.projectDir / f"Tile/{i}/{i}_switch_matrix.{self.extension}"
            )
            self.fabulousAPI.genSwitchMatrix(i)
        logger.info("Switch matrix generation complete")

    @with_category(CMD_FABRIC_FLOW)
    def do_gen_tile(
        self,
        tiles: Annotated[
            list[str],
            typer.Argument(help="A list of tile name to generate tile"),
            CompleterSpec(complete_tile_names),
        ],
    ) -> None:
        """Generate given tile with switch matrix and configuration memory.

        Parsing input arguments, call functions such as `genSwitchMatrix` and
        `genConfigMem`. Handle both regular tiles and super tiles with sub-tiles.

        Also logs generation process for each specified tile and sub-tile.
        """
        logger.info(f"Generating tile {' '.join(tiles)}")
        for t in tiles:
            if subTiles := [
                f.stem
                for f in (self.projectDir / f"Tile/{t}").iterdir()
                if f.is_dir() and f.name != "macro"
            ]:
                logger.info(
                    f"{t} is a super tile, generating {t} with sub tiles "
                    f"{' '.join(subTiles)}"
                )
                for st in subTiles:
                    # Gen switch matrix
                    logger.info(f"Generating switch matrix for tile {t}")
                    logger.info(f"Generating switch matrix for {st}")
                    self.fabulousAPI.setWriterOutputFile(
                        f"{self.projectDir}/Tile/{t}/{st}/{st}_switch_matrix.{self.extension}"
                    )
                    self.fabulousAPI.genSwitchMatrix(st)
                    logger.info(f"Generated switch matrix for {st}")

                    # Gen config mem
                    logger.info(f"Generating configMem for tile {t}")
                    logger.info(f"Generating ConfigMem for {st}")
                    self.fabulousAPI.setWriterOutputFile(
                        f"{self.projectDir}/Tile/{t}/{st}/{st}_ConfigMem.{self.extension}"
                    )
                    self.fabulousAPI.genConfigMem(
                        st, self.projectDir / f"Tile/{t}/{st}/{st}_ConfigMem.csv"
                    )
                    logger.info(f"Generated configMem for {st}")

                    # Gen tile
                    logger.info(f"Generating subtile for tile {t}")
                    logger.info(f"Generating subtile {st}")
                    self.fabulousAPI.setWriterOutputFile(
                        f"{self.projectDir}/Tile/{t}/{st}/{st}.{self.extension}"
                    )
                    self.fabulousAPI.genTile(st)
                    logger.info(f"Generated subtile {st}")

                # Gen super tile
                logger.info(f"Generating super tile {t}")
                self.fabulousAPI.setWriterOutputFile(
                    f"{self.projectDir}/Tile/{t}/{t}.{self.extension}"
                )
                self.fabulousAPI.genSuperTile(t)
                logger.info(f"Generated super tile {t}")
                continue

            # Gen switch matrix
            self.do_gen_switch_matrix([t])

            # Gen config mem
            self.do_gen_config_mem([t])

            logger.info(f"Generating tile {t}")
            # Gen tile
            self.fabulousAPI.setWriterOutputFile(
                f"{self.projectDir}/Tile/{t}/{t}.{self.extension}"
            )
            self.fabulousAPI.genTile(t)
            logger.info(f"Generated tile {t}")

        logger.info("Tile generation complete")

    @with_category(CMD_FABRIC_FLOW)
    def do_gen_all_tile(self) -> None:
        """Generate all tiles by calling `do_gen_tile`."""
        logger.info("Generating all tiles")
        self.do_gen_tile(self.allTile)
        logger.info("All tiles generation complete")

    @with_category(CMD_FABRIC_FLOW)
    def do_gen_fabric(self) -> None:
        """Generate fabric based on the loaded fabric.

        Calling `gen_all_tile` and `genFabric`.

        Logs start and completion of fabric generation process.
        """
        logger.info(f"Generating fabric {self.fabulousAPI.fabric.name}")
        self.onecmd_plus_hooks("gen_all_tile")
        if self.exit_code != 0:
            raise CommandError("Tile generation failed")
        self.fabulousAPI.setWriterOutputFile(
            f"{self.projectDir}/Fabric/{self.fabulousAPI.fabric.name}.{self.extension}"
        )
        self.fabulousAPI.genFabric()
        logger.info("Fabric generation complete")

    @with_category(CMD_FABRIC_FLOW)
    def do_gen_geometry(
        self,
        padding: Annotated[
            int,
            typer.Argument(
                help="Padding value for geometry generation (4-32)", min=4, max=32
            ),
        ] = 8,
    ) -> None:
        """Generate geometry of fabric for FABulator.

        Checking if fabric is loaded, and calling 'genGeometry' and passing on padding
        value. Default padding is '8'.

        Also logs geometry generation, the used padding value and any warning about
        faulty padding arguments, as well as errors if the fabric is not loaded or the
        padding is not within the valid range of 4 to 32.
        """
        logger.info(f"Generating geometry for {self.fabulousAPI.fabric.name}")
        geomFile = f"{self.projectDir}/{self.fabulousAPI.fabric.name}_geometry.csv"
        self.fabulousAPI.setWriterOutputFile(geomFile)

        self.fabulousAPI.genGeometry(padding)
        logger.info("Geometry generation complete")
        logger.info(f"{geomFile} can now be imported into FABulator")

    @with_category(CMD_GUI)
    def do_start_FABulator(self) -> None:
        """Start FABulator if an installation can be found.

        .. deprecated::
            Use 'gui fabulator' instead. This command is deprecated and will be
            removed in a future version.

        If no installation can be found, a warning is produced.
        """
        logger.warning(
            "DEPRECATED: 'start_FABulator' is deprecated. Use 'gui fabulator' instead."
        )
        return cmd_gui._gui_fabulator(self)  # noqa: SLF001

    def do_gui(self) -> typer.Typer:
        """GUI tools for viewing and editing FABulous designs.

        Available subcommands:
            fabulator - Start FABulator GUI for visual fabric editing
            openroad  - Start OpenROAD GUI to view .odb database files
            klayout   - Start KLayout GUI to view .gds layout files

        Examples
        --------
            gui fabulator
            gui openroad --last-run
            gui klayout --tile MyTile
            gui openroad my_design.odb
        """
        return cmd_gui.do_gui(self)

    # Copy over the original function's annotations and category decorator
    do_gui.__annotations__ = cmd_gui.do_gui.__annotations__
    do_gui.__wrapped__ = cmd_gui.do_gui

    @with_category(CMD_FABRIC_FLOW)
    def do_gen_bitStream_spec(self) -> None:
        """Generate bitstream specification of the fabric.

        By calling `genBitStreamSpec` and saving the specification to a binary and CSV
        file.

        Also logs the paths of the output files.
        """
        logger.info("Generating bitstream specification")
        specObject = self.fabulousAPI.genBitStreamSpec()

        logger.info(f"output file: {self.projectDir}/{META_DATA_DIR}/bitStreamSpec.bin")
        with Path(f"{self.projectDir}/{META_DATA_DIR}/bitStreamSpec.bin").open(
            "wb"
        ) as outFile:
            pickle.dump(specObject, outFile)

        logger.info(f"output file: {self.projectDir}/{META_DATA_DIR}/bitStreamSpec.csv")
        with Path(f"{self.projectDir}/{META_DATA_DIR}/bitStreamSpec.csv").open(
            "w", encoding="utf-8", newline="\n"
        ) as f:
            w = csv.writer(f)
            for key1 in specObject["TileSpecs"]:
                w.writerow([key1])
                for key2, val in specObject["TileSpecs"][key1].items():
                    w.writerow([key2, val])
        logger.info("Bitstream specification generation complete")

    @with_category(CMD_FABRIC_FLOW)
    def do_gen_top_wrapper(self) -> None:
        """Generate top wrapper of the fabric by calling `genTopWrapper`."""
        logger.info("Generating top wrapper")
        self.fabulousAPI.setWriterOutputFile(
            f"{self.projectDir}/Fabric/{self.fabulousAPI.fabric.name}_top.{self.extension}"
        )
        self.fabulousAPI.genTopWrapper()
        logger.info("Top wrapper generation complete")

    @with_category(CMD_FABRIC_FLOW)
    def do_run_FABulous_fabric(self) -> None:
        """Generate the fabric based on the CSV file.

        Create bitstream specification of the fabric, top wrapper of the fabric, Nextpnr
        model of the fabric and geometry information of the fabric.
        """
        logger.info("Running FABulous")

        success = (
            CommandPipeline(self)
            .add_step("gen_io_fabric")
            .add_step("gen_fabric", "Fabric generation failed")
            .add_step("gen_bitStream_spec", "Bitstream specification generation failed")
            .add_step("gen_top_wrapper", "Top wrapper generation failed")
            .add_step("gen_model_npnr", "Nextpnr model generation failed")
            .add_step("gen_geometry", "Geometry generation failed")
            .execute()
        )

        if success:
            logger.info("FABulous fabric flow complete")

    @with_category(CMD_FABRIC_FLOW)
    def do_gen_model_npnr(self) -> None:
        """Generate Nextpnr model of fabric.

        By parsing various required files for place and route such as `pips.txt`,
        `bel.txt`, `bel.v2.txt` and `template.pcf`. Output files are written to the
        directory specified by `metaDataDir` within `projectDir`.

        Logs output file directories.
        """
        logger.info("Generating npnr model")
        npnrModel = self.fabulousAPI.genRoutingModel()
        logger.info(f"output file: {self.projectDir}/{META_DATA_DIR}/pips.txt")
        with Path(f"{self.projectDir}/{META_DATA_DIR}/pips.txt").open("w") as f:
            f.write(npnrModel[0])

        logger.info(f"output file: {self.projectDir}/{META_DATA_DIR}/bel.txt")
        with Path(f"{self.projectDir}/{META_DATA_DIR}/bel.txt").open("w") as f:
            f.write(npnrModel[1])

        logger.info(f"output file: {self.projectDir}/{META_DATA_DIR}/bel.v2.txt")
        with Path(f"{self.projectDir}/{META_DATA_DIR}/bel.v2.txt").open("w") as f:
            f.write(npnrModel[2])

        logger.info(f"output file: {self.projectDir}/{META_DATA_DIR}/template.pcf")
        with Path(f"{self.projectDir}/{META_DATA_DIR}/template.pcf").open("w") as f:
            f.write(npnrModel[3])

        logger.info("Generated npnr model")

    @with_category(CMD_USER_DESIGN_FLOW)
    def do_place_and_route(
        self,
        file: Annotated[
            Path,
            typer.Argument(help="Path to the target file"),
            CompleterSpec(Cmd.path_complete),
        ],
    ) -> None:
        """Run place and route with Nextpnr for a given JSON file.

        Generated by Yosys, which requires a Nextpnr model and JSON file first,
        generated by `synthesis`.

        Also logs place and route error, file not found error and type error.
        """
        logger.info(f"Running Placement and Routing with Nextpnr for design {file}")
        path = Path(file)
        parent = path.parent
        json_file = path.name
        top_module_name = path.stem

        if path.suffix != ".json":
            raise InvalidFileType(
                "No json file provided. Usage: place_and_route <json_file>"
            )

        fasm_file = top_module_name + ".fasm"
        log_file = top_module_name + "_npnr_log.txt"

        if parent == "":
            parent = "."

        if (
            not Path(f"{self.projectDir}/.FABulous/pips.txt").exists()
            or not Path(f"{self.projectDir}/.FABulous/bel.txt").exists()
        ):
            raise FileNotFoundError(
                "Pips and Bel files are not found, please run model_gen_npnr first"
            )

        if Path(f"{self.projectDir}/{parent}").exists():
            # TODO rewriting the fab_arch script so no need to copy file for work around
            npnr = get_context().nextpnr_path
            if f"{json_file}" in [
                str(i.name) for i in Path(f"{self.projectDir}/{parent}").iterdir()
            ]:
                runCmd = [
                    f"FAB_ROOT={self.projectDir}",
                    f"{npnr!s}",
                    "--uarch",
                    "fabulous",
                    "--json",
                    f"{self.projectDir}/{parent}/{json_file}",
                    "-o",
                    f"fasm={self.projectDir}/{parent}/{fasm_file}",
                    "--verbose",
                    "--log",
                    f"{self.projectDir}/{parent}/{log_file}",
                ]
                result = sp.run(
                    " ".join(runCmd),
                    stdout=sys.stdout,
                    stderr=sp.STDOUT,
                    check=True,
                    shell=True,
                )
                if result.returncode != 0:
                    raise CommandError("Nextpnr failed with non-zero exit code")

            else:
                raise FileNotFoundError(
                    f'Cannot find file "{json_file}" in path '
                    f'"{self.projectDir}/{parent}/". '
                    "This file is generated by running Yosys with Nextpnr backend "
                    "(e.g. synthesis)."
                )

            logger.info("Placement and Routing completed")
        else:
            raise FileNotFoundError(
                f"Directory {self.projectDir}/{parent} does not exist. "
                "Please check the path and try again."
            )

    @with_category(CMD_USER_DESIGN_FLOW)
    def do_gen_bitStream_binary(
        self,
        file: Annotated[
            Path,
            typer.Argument(help="Path to the target file"),
            CompleterSpec(Cmd.path_complete),
        ],
    ) -> None:
        """Generate bitstream of a given design.

        Using FASM file and pre-generated bitstream specification file
        `bitStreamSpec.bin`. Requires bitstream specification before use by running
        `gen_bitStream_spec` and place and route file generated by running
        `place_and_route`.

        Also logs output file directory, Bitstream generation error and file not found
        error.
        """
        parent = file.parent
        fasm_file = file.name
        top_module_name = file.stem

        if file.suffix != ".fasm":
            raise InvalidFileType(
                "No fasm file provided. Usage: gen_bitStream_binary <fasm_file>"
            )

        bitstream_file = top_module_name + ".bin"

        if not (self.projectDir / ".FABulous/bitStreamSpec.bin").exists():
            raise FileNotFoundError(
                "Cannot find bitStreamSpec.bin file, which is generated by running "
                "gen_bitStream_spec"
            )

        if not (self.projectDir / f"{parent}/{fasm_file}").exists():
            raise FileNotFoundError(
                f"Cannot find {self.projectDir}/{parent}/{fasm_file} file which is "
                "generated by running place_and_route. "
                "Potentially Place and Route Failed."
            )

        logger.info(f"Generating Bitstream for design {self.projectDir}/{file}")
        logger.info(f"Outputting to {self.projectDir}/{parent}/{bitstream_file}")

        try:
            genBitstream(
                f"{self.projectDir}/{parent}/{fasm_file}",
                f"{self.projectDir}/.FABulous/bitStreamSpec.bin",
                f"{self.projectDir}/{parent}/{bitstream_file}",
            )

        except Exception as e:  # noqa: BLE001
            raise CommandError(
                f"Bitstream generation failed for "
                f"{self.projectDir}/{parent}/{fasm_file}. "
                "Please check the logs for more details."
            ) from e

        logger.info("Bitstream generated")

    @with_category(CMD_USER_DESIGN_FLOW)
    def do_run_simulation(
        self,
        trace_format: Annotated[
            Literal["vcd", "fst"],
            typer.Argument(help="Output format of the simulation"),
        ] = "fst",
        file: Annotated[
            Path,
            typer.Argument(help="Path to the bitstream file"),
            CompleterSpec(Cmd.path_complete),
        ] = Path(),
    ) -> None:
        """Simulate given FPGA design using Icarus Verilog (iverilog).

        If <fst> is specified, waveform files in FST format will generate, <vcd> with
        generate VCD format. The bitstream_file argument should be a binary file
        generated by 'gen_bitStream_binary'. Verilog files from 'Tile' and 'Fabric'
        directories are copied to the temporary directory 'tmp', 'tmp' is deleted on
        simulation end.

        Also logs simulation error and file not found error and value error.
        """
        # Convert string to Path if needed (for TCL compatibility)
        file_path = Path(file) if isinstance(file, str) else file

        if not file_path.is_relative_to(self.projectDir):
            bitstreamPath = self.projectDir / file_path
        else:
            bitstreamPath = file_path
        topModule = bitstreamPath.stem
        if bitstreamPath.suffix != ".bin":
            raise InvalidFileType(
                "No bitstream file specified. "
                "Usage: run_simulation <format> <bitstream_file>"
            )

        if not bitstreamPath.exists():
            raise FileNotFoundError(
                f"Cannot find {bitstreamPath} file which is generated by running "
                "gen_bitStream_binary. Potentially the bitstream generation failed."
            )

        waveform_format = trace_format
        defined_option = f"CREATE_{waveform_format.upper()}"

        designFile = topModule + ".v"
        topModuleTB = topModule + "_tb"
        testBench = topModuleTB + ".v"
        vvpFile = topModuleTB + ".vvp"

        logger.info(f"Running simulation for {designFile}")

        testPath = Path(self.projectDir / "Test")
        buildDir = testPath / "build"
        fabricFilesDir = buildDir / "fabric_files"

        buildDir.mkdir(exist_ok=True)
        fabricFilesDir.mkdir(exist_ok=True)

        copy_verilog_files(self.projectDir / "Tile", fabricFilesDir)
        copy_verilog_files(self.projectDir / "Fabric", fabricFilesDir)
        file_list = [str(i) for i in fabricFilesDir.glob("*.v")]

        iverilog = get_context().iverilog_path
        runCmd = [
            f"{iverilog}",
            "-D",
            f"{defined_option}",
            "-s",
            f"{topModuleTB}",
            "-o",
            f"{buildDir}/{vvpFile}",
            *file_list,
            f"{bitstreamPath.parent}/{designFile}",
            f"{testPath}/{testBench}",
        ]
        if self.verbose or self.debug:
            logger.info(f"Running simulation with {trace_format} format")
            logger.info(f"Running command: {' '.join(runCmd)}")

        result = sp.run(runCmd, check=True)
        if result.returncode != 0:
            raise CommandError(
                f"Simulation failed for {designFile}. "
                "Please check the logs for more details."
            )

        # bitstream hex file is used for simulation so it'll be created in the
        # test directory
        bitstreamHexPath = (buildDir.parent / bitstreamPath.stem).with_suffix(".hex")
        if self.verbose or self.debug:
            logger.info(f"Make hex file {bitstreamHexPath}")
        make_hex(bitstreamPath, bitstreamHexPath)
        vvp = get_context().vvp_path

        # $plusargs is used to pass the bitstream hex and waveform path to the testbench
        vvpArgs = [
            f"+output_waveform={testPath / topModule}.{waveform_format}",
            f"+bitstream_hex={bitstreamHexPath}",
        ]
        if waveform_format == "fst":
            vvpArgs.append("-fst")

        runCmd = [f"{vvp!s}", f"{buildDir}/{vvpFile}"]
        runCmd.extend(vvpArgs)
        if self.verbose or self.debug:
            logger.info(f"Running command: {' '.join(runCmd)}")

        result = sp.run(runCmd, check=True)
        remove_dir(buildDir)
        if result.returncode != 0:
            raise CommandError(
                f"Simulation failed for {designFile}. "
                "Please check the logs for more details."
            )

        logger.info("Simulation finished")

    @with_category(CMD_USER_DESIGN_FLOW)
    def do_run_FABulous_bitstream(
        self,
        file: Annotated[
            Path,
            typer.Argument(help="Path to design file"),
            CompleterSpec(Cmd.path_complete),
        ],
    ) -> None:
        """Run FABulous to generate bitstream on a given design.

        Does this by calling synthesis, place and route, bitstream generation functions.
        Requires Verilog file specified by <top_module_file>.

        Also logs usage error and file not found error.
        """
        file_path_no_suffix = file.parent / file.stem

        if file.suffix != ".v":
            raise InvalidFileType(
                "No verilog file provided. "
                "Usage: run_FABulous_bitstream <top_module_file>"
            )

        json_file_path = file_path_no_suffix.with_suffix(".json")
        fasm_file_path = file_path_no_suffix.with_suffix(".fasm")

        do_synth_args = str(file)

        primsLib = f"{self.projectDir}/user_design/custom_prims.v"
        if Path(primsLib).exists():
            do_synth_args += f" -extra-plib {primsLib}"
        else:
            logger.info("No external primsLib found.")

        success = (
            CommandPipeline(self)
            .add_step(f"synthesis {do_synth_args}")
            .add_step(f"place_and_route {json_file_path}")
            .add_step(f"gen_bitStream_binary {fasm_file_path}")
            .execute()
        )
        if success:
            logger.info("FABulous bitstream generation complete")

    @with_category(CMD_SCRIPT)
    def do_run_tcl(
        self,
        file: Annotated[
            Path,
            typer.Argument(help="Path to the tcl script file"),
            CompleterSpec(Cmd.path_complete),
        ],
    ) -> None:
        """Execute TCL script relative to the project directory.

        Specified by <tcl_scripts>. Use the 'tk' module to create TCL commands.

        Also logs usage errors and file not found errors.
        """
        # Convert to Path if needed (for script/command line compatibility)
        file_path = Path(file) if not isinstance(file, Path) else file

        if not file_path.exists():
            raise FileNotFoundError(
                f"Cannot find {file_path} file, please check the path and try again."
            )

        if self.force:
            logger.warning(
                "TCL script does not work with force mode, TCL will stop on first error"
            )

        logger.info(f"Execute TCL script {file_path}")

        with file_path.open() as f:
            script = f.read()
        self.tcl.eval(script)

        logger.info("TCL script executed")

    @with_category(CMD_SCRIPT)
    def do_run_script(
        self,
        file: Annotated[
            Path,
            typer.Argument(help="Path to the fabulous script file"),
            CompleterSpec(Cmd.path_complete),
        ],
    ) -> None:
        """Execute script."""
        # Convert to Path if needed (for script/command line compatibility)
        file_path = Path(file) if not isinstance(file, Path) else file

        if not file_path.exists():
            raise FileNotFoundError(
                f"Cannot find {file_path} file, please check the path and try again."
            )

        logger.info(f"Execute script {file_path}")

        with file_path.open() as f:
            for i in f:
                if i.startswith("#"):
                    continue
                self.onecmd_plus_hooks(i.strip())
                if self.exit_code != 0:
                    if not self.force:
                        raise CommandError(
                            f"Script execution failed at line: {i.strip()}"
                        )
                    logger.error(
                        f"Script execution failed at line: {i.strip()} "
                        "but continuing due to force mode"
                    )

        logger.info("Script executed")

    @with_category(CMD_USER_DESIGN_FLOW)
    def do_gen_user_design_wrapper(
        self,
        user_design: Annotated[
            Path,
            typer.Argument(help="Path to user design file"),
            CompleterSpec(Cmd.path_complete),
        ],
        user_design_top_wrapper: Annotated[
            Path,
            typer.Argument(help="Output path for user design top wrapper"),
            CompleterSpec(Cmd.path_complete),
        ],
    ) -> None:
        """Generate a user design wrapper for the specified user design.

        This command creates a wrapper module that interfaces the user design
        with the FPGA fabric, handling signal connections and naming conventions.

        Parameters
        ----------
        user_design : Path
            Path to the user design file
        user_design_top_wrapper : Path
            Path for the generated wrapper file

        Raises
        ------
        CommandError
            If the fabric has not been loaded yet.
        """
        if not self.fabricLoaded:
            raise CommandError("Need to load fabric first")
        project_dir = get_context().proj_dir
        self.fabulousAPI.generateUserDesignTopWrapper(
            project_dir
            / (Path(user_design) if isinstance(user_design, str) else user_design),
            project_dir
            / (
                Path(user_design_top_wrapper)
                if isinstance(user_design_top_wrapper, str)
                else user_design_top_wrapper
            ),
        )

    @with_category(CMD_TOOLS)
    def do_generate_custom_tile_config(
        self,
        tile_path: Annotated[
            Path,
            typer.Argument(help="Path to the target tile directory"),
            CompleterSpec(Cmd.path_complete),
        ],
        no_switch_matrix: Annotated[
            bool,
            typer.Option(
                "--no-switch-matrix",
                "-nosm",
                help="Do not generate a Tile Switch Matrix",
            ),
        ] = False,
    ) -> None:
        """Generate a custom tile configuration for a given tile folder.

        Or path to bel folder. A tile `.csv` file and a switch matrix `.list` file will
        be generated.

        The provided path may contain bel files, which will be included in the generated
        tile .csv file as well as the generated switch matrix .list file.
        """
        # Convert string to Path if needed (for TCL compatibility)
        tile_path_obj = Path(tile_path) if isinstance(tile_path, str) else tile_path

        if not tile_path_obj.is_dir():
            logger.error(f"{tile_path_obj} is not a directory or does not exist")
            return

        tile_csv = generateCustomTileConfig(tile_path_obj)

        if not no_switch_matrix:
            parseTilesCSV(tile_csv)

    @with_category(CMD_FABRIC_FLOW)
    def do_gen_io_tiles(
        self,
        tiles: Annotated[
            list[str],
            typer.Argument(help="A list of tile"),
            CompleterSpec(complete_tile_names),
        ],
    ) -> None:
        """Generate I/O BELs for specified tiles.

        This command generates Input/Output Basic Elements of Logic (BELs) for the
        specified tiles, enabling external connectivity for the FPGA fabric.

        Parameters
        ----------
        tiles : list[str]
            List of tile names to generate I/O BELs for
        """
        if tiles:
            for tile in tiles:
                self.fabulousAPI.genIOBelForTile(tile)

    @with_category(CMD_FABRIC_FLOW)
    def do_gen_io_fabric(self) -> None:
        """Generate I/O BELs for the entire fabric.

        This command generates Input/Output Basic Elements of Logic (BELs) for all
        applicable tiles in the fabric, providing external connectivity
        across the entire FPGA design.

        Parameters
        ----------
        _args : str
            Command arguments (unused for this command).
        """
        self.fabulousAPI.genFabricIOBels()

    @with_category(CMD_FABRIC_FLOW)
    def do_gen_tile_macro(
        self,
        tile: Annotated[
            str,
            typer.Argument(help="A tile"),
            CompleterSpec(complete_tile_names),
        ],
        optimise: Annotated[
            OptMode | None,
            typer.Option("--optimise", "-opt", help="Optimize the GDS layout"),
        ] = None,
        override: Annotated[
            Path | None,
            typer.Option("--override", help="Override the GDS layout"),
        ] = None,
    ) -> None:
        """Generate GDSII files for a specific tile.

        This command generates GDSII files for the specified tile using the
        librelane flow. The output is placed in `<project>/Tile/<tile>/macro/`.

        Use --optimise to enable iterative tile size optimization. Available modes:
        balance (default), find_min_width, find_min_height, large, no_opt.

        Parameters
        ----------
        tile : str
            Name of the tile to generate GDSII files for
        optimise : OptMode
            Optimization mode for tile sizing
        override : Path
            Override the GDS layout
        """
        tile_dir = self.projectDir / "Tile" / tile
        pin_order_file = tile_dir / f"{tile}_io_pin_order.yaml"

        if not tile_dir.exists():
            logger.error(f"Tile directory {tile_dir} does not exist")
            return

        if tile_obj := self.fabulousAPI.getTile(tile):
            self.fabulousAPI.gen_io_pin_order_config(tile_obj, pin_order_file)
        else:
            super_tile = self.fabulousAPI.getSuperTile(tile)
            if super_tile is None:
                logger.error(f"Tile {tile} not found in fabric definition")
                return
            self.fabulousAPI.gen_io_pin_order_config(super_tile, pin_order_file)

        self.fabulousAPI.genTileMacro(
            tile_dir,
            pin_order_file,
            tile_dir / "macro",
            optimisation=optimise if optimise is not None else OptMode.NO_OPT,
            base_config_path=self.projectDir / "Tile" / "include" / "gds_config.yaml",
            config_override_path=override if override else tile_dir / "gds_config.yaml",
        )

    @with_category(CMD_FABRIC_FLOW)
    def do_gen_all_tile_macros(
        self,
        parallel: Annotated[
            bool,
            typer.Option("--parallel", "-p", help="Generate tile macros in parallel"),
        ] = False,
        optimise: Annotated[
            OptMode | None,
            typer.Option(
                "--optimise", "-opt", help="Optimize the GDS layout of all tiles"
            ),
        ] = None,
    ) -> None:
        """Generate GDSII files for all tiles in the fabric.

        Iterates through all unique tiles and generates GDSII for each. Use --parallel
        to compile tiles concurrently for faster builds. Use --optimise to enable tile
        size optimization (balance mode by default).
        """
        commands = CommandPipeline(self)
        for i in sorted(self.allTile):
            if optimise:
                commands.add_step(f"gen_tile_macro {i} --optimise {optimise.value}")
            else:
                commands.add_step(f"gen_tile_macro {i}")
        if not parallel:
            commands.execute()
        else:
            commands.execute_parallel()

    @with_category(CMD_FABRIC_FLOW)
    def do_gen_fabric_macro(self) -> None:
        """Generate GDSII files for the entire fabric by stitching tiles.

        Assembles all pre-compiled tile macros into a complete fabric layout. Requires
        tile GDS files to be generated first using gen_tile_macro or
        gen_all_tile_macros. Configuration is read from Fabric/gds_config.yaml.
        """
        tile_macro_root = self.projectDir / "Tile"
        tile_macro_paths: dict[str, Path] = {}

        for tile_dir in tile_macro_root.iterdir():
            if not tile_dir.is_dir():
                continue
            macro_dir = tile_dir / "macro" / "final_views"
            if macro_dir.exists():
                tile_macro_paths[tile_dir.name] = macro_dir

        if not tile_macro_paths:
            logger.error(
                "No tile macro directories found. Generate tile GDS results first."
            )
            return

        (self.projectDir / "gds").mkdir(exist_ok=True)
        (self.projectDir / "Fabric" / "macro").mkdir(exist_ok=True)
        self.fabulousAPI.fabric_stitching(
            tile_macro_paths,
            self.projectDir / "Fabric" / f"{self.fabulousAPI.fabric.name}.v",
            self.projectDir / "Fabric" / "macro",
            base_config_path=self.projectDir / "Fabric" / "gds_config.yaml",
        )

    @with_category(CMD_FABRIC_FLOW)
    def do_run_FABulous_eFPGA_macro(self) -> None:
        """Run the full automated FABulous eFPGA macro generation flow.

        This is the recommended approach for production. It automatically:
        1. Compiles all tiles with multiple optimization modes in parallel
        2. Uses NLP optimization to find optimal tile dimensions
        3. Recompiles tiles with optimal dimensions
        4. Stitches all tiles into the final fabric

        The flow minimizes total fabric area while ensuring all tiles stitch
        correctly (matching row heights and column widths).
        """
        (self.projectDir / "Fabric" / "macro").mkdir(exist_ok=True)
        self.fabulousAPI.full_fabric_automation(
            self.projectDir,
            self.projectDir / "Fabric" / "macro",
            base_config_path=self.projectDir / "Fabric" / "gds_config.yaml",
        )

    def _get_file_path(
        self,
        file_extension_or_args: str | argparse.Namespace,
        file_extension: str | None = None,
        tile: str | None = None,
        fabric: bool = False,
        last_run: bool = False,
        show_count: int = 10,
    ) -> str:
        """Get the file path for the specified file extension.

        Supports both old argparse.Namespace signature and new direct parameters.
        """
        # Handle old signature (args, file_extension)
        if isinstance(file_extension_or_args, argparse.Namespace):
            args = file_extension_or_args
            actual_extension = file_extension if file_extension else ""
            tile = args.tile if hasattr(args, "tile") else None
            fabric = args.fabric if hasattr(args, "fabric") else False
            last_run = args.last_run if hasattr(args, "last_run") else False
            show_count = int(args.head) if hasattr(args, "head") else 10
        else:
            # New signature (file_extension, tile, fabric, last_run, show_count)
            actual_extension = file_extension_or_args

        def get_latest(directory: Path, file_extension: str) -> str:
            """Get the latest modified file in a directory."""
            files = list(directory.glob(f"**/*.{file_extension}"))
            if not files:
                raise FileNotFoundError("cannot find relevant file")
            latest_file = max(files, key=lambda f: f.stat().st_mtime)
            return str(latest_file)

        def get_option(f: Path, file_extension: str) -> str:
            """Prompt user to select a file from a list of recent matches.

            Parameters
            ----------
            f : Path
                Directory path to search in.
            file_extension : str
                File extension to filter by.

            Returns
            -------
            str
                Path to the selected file as a string.
            """
            title = "Select which file to view"
            files_list = sorted(
                f.glob(f"**/*.{file_extension}"),
                key=lambda f: f.stat().st_mtime,
                reverse=True,
            )[:show_count]
            if not files_list:
                raise FileNotFoundError("cannot find relevant file")
            _, idx = pick(
                list(map(lambda x: str(x.relative_to(self.projectDir)), files_list)),
                title,
            )
            return str(files_list[cast("int", idx)])

        file: str = ""
        if last_run:
            if fabric:
                file = get_latest(self.projectDir / "Fabric", actual_extension)
            elif tile is not None:
                file = get_latest(self.projectDir / "Tile" / tile, actual_extension)
            else:
                file = get_latest(self.projectDir, actual_extension)
        else:
            if fabric:
                file = get_option(self.projectDir / "Fabric", actual_extension)
            elif tile is not None:
                file = get_option(self.projectDir / "Tile" / tile, actual_extension)
            elif tile is None and not fabric:
                file = get_option(self.projectDir, actual_extension)

        if not file:
            raise FileNotFoundError("cannot find relevant file")

        return file

    @with_category(CMD_TOOLS)
    def do_start_openroad_gui(
        self,
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
        """Start OpenROAD GUI if an installation can be found.

        .. deprecated::
            Use 'gui openroad' instead. This command is deprecated and will be
            removed in a future version.

        If no installation can be found, a warning is produced.
        """
        logger.warning(
            "DEPRECATED: 'start_openroad_gui' is deprecated. "
            "Use 'gui openroad' instead."
        )
        return cmd_gui._gui_openroad(  # noqa: SLF001
            self, file, tile, fabric, last_run, head
        )

    @with_category(CMD_TOOLS)
    def do_start_klayout_gui(
        self,
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
        """Start klayout GUI if an installation can be found.

        .. deprecated::
            Use 'gui klayout' instead. This command is deprecated and will be
            removed in a future version.

        If no installation can be found, a warning is produced.
        """
        logger.warning(
            "DEPRECATED: 'start_klayout_gui' is deprecated. Use 'gui klayout' instead."
        )
        return cmd_gui._gui_klayout(  # noqa: SLF001
            self, file, tile, fabric, last_run, head
        )

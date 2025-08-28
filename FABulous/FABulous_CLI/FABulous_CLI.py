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

import argparse
import os
import pprint
import subprocess as sp
import sys
import tkinter as tk
import traceback
from pathlib import Path

from cmd2 import (
    Cmd,
    Cmd2ArgumentParser,
    Settable,
    Statement,
    categorize,
    with_argparser,
    with_category,
)
from loguru import logger

from FABulous.custom_exception import CommandError, EnvironmentNotSet
from FABulous.fabric_generator.code_generator.code_generator_Verilog import (
    VerilogCodeGenerator,
)
from FABulous.fabric_generator.code_generator.code_generator_VHDL import (
    VHDLCodeGenerator,
)
from FABulous.fabric_generator.gen_fabric.fabric_automation import (
    generateCustomTileConfig,
)
from FABulous.fabric_generator.parser.parse_csv import parseTilesCSV
from FABulous.FABulous_API import FABulous_API
from FABulous.FABulous_CLI import cmd_synthesis
from FABulous.FABulous_CLI.helper import (
    allow_blank,
    install_oss_cad_suite,
    wrap_with_except_handling,
)
from FABulous.FABulous_settings import FABulousSettings

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


class FABulous_CLI(Cmd):
    intro: str = INTO_STRING
    prompt: str = "FABulous> "
    fabulousAPI: FABulous_API
    projectDir: Path
    enteringDir: Path
    top: str
    allTile: list[str]
    csvFile: Path
    extension: str = "v"
    script: str = ""
    force: bool = False
    interactive: bool = True

    def __init__(
        self,
        writerType: str | None,
        projectDir: Path,
        enteringDir: Path,
        force: bool = False,
        interactive: bool = False,
    ) -> None:
        """Initialises the FABulous shell instance.

        Determines file extension based on the type of writer used in 'fab'
        and sets fabricLoaded to true if 'fab' has 'fabric' attribute.

        Parameters
        ----------
        writerType : str
            The writer type to use for generating fabric.
        projectDir : Path
            Path to the project directory.
        script : str, optional
            Path to optional Tcl script to be executed, by default ""
        """
        super().__init__(
            persistent_history_file=f"{FABulousSettings().proj_dir}/{META_DATA_DIR}/.fabulous_history",
            allow_cli_args=False,
        )
        self.enteringDir = enteringDir

        if writerType == "verilog":
            self.fabulousAPI = FABulous_API(
                VerilogCodeGenerator(), projectDir=projectDir
            )
        elif writerType == "vhdl":
            self.fabulousAPI = FABulous_API(VHDLCodeGenerator(), projectDir=projectDir)
        else:
            logger.critical(
                f"Invalid writer type: {writerType}\n Valid options are 'verilog' or 'vhdl'"
            )
            sys.exit(1)

        self.projectDir = projectDir.absolute()
        self.add_settable(
            Settable("projectDir", Path, "The directory of the project", self)
        )

        self.tiles = []
        self.superTiles = []
        self.csvFile = Path(projectDir / "fabric.csv")
        self.add_settable(
            Settable(
                "csvFile", Path, "The fabric file ", self, completer=Cmd.path_complete
            )
        )

        self.verbose = False
        self.add_settable(Settable("verbose", bool, "verbose output", self))

        self.force = force
        self.add_settable(Settable("force", bool, "force execution", self))

        self.interactive = interactive

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
                self.tcl.createcommand(name, wrap_with_except_handling(f))

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
                return False
            return not self.force

    def do_exit(self, *_ignored: str) -> bool:
        """Exits the FABulous shell and logs info message."""
        logger.info("Exiting FABulous shell")
        os.chdir(self.enteringDir)
        return True

    do_quit = do_exit
    do_q = do_exit

    # Import do_synthesis from cmd_synthesis
    do_synthesis = cmd_synthesis.do_synthesis

    filePathOptionalParser = Cmd2ArgumentParser()
    filePathOptionalParser.add_argument(
        "file",
        type=Path,
        help="Path to the target file",
        default="",
        nargs=argparse.OPTIONAL,
        completer=Cmd.path_complete,
    )

    filePathRequireParser = Cmd2ArgumentParser()
    filePathRequireParser.add_argument(
        "file", type=Path, help="Path to the target file", completer=Cmd.path_complete
    )

    userDesignRequireParser = Cmd2ArgumentParser()
    userDesignRequireParser.add_argument(
        "user_design",
        type=Path,
        help="Path to user design file",
        completer=Cmd.path_complete,
    )
    userDesignRequireParser.add_argument(
        "user_design_top_wrapper",
        type=Path,
        help="Output path for user design top wrapper",
        completer=Cmd.path_complete,
    )

    tile_list_parser = Cmd2ArgumentParser()
    tile_list_parser.add_argument(
        "tiles",
        type=str,
        help="A list of tile",
        nargs="+",
        completer=lambda self: self.fab.getTiles(),
    )

    tile_single_parser = Cmd2ArgumentParser()
    tile_single_parser.add_argument(
        "tile",
        type=str,
        help="A tile",
        completer=lambda self: self.fab.getTiles(),
    )

    install_oss_cad_suite_parser = Cmd2ArgumentParser()
    install_oss_cad_suite_parser.add_argument(
        "destination_folder",
        type=str,
        help="Destination folder for the installation",
        default="",
        completer=Cmd.path_complete,
        nargs=argparse.OPTIONAL,
    )
    install_oss_cad_suite_parser.add_argument(
        "update_existing",
        type=bool,
        help="Update/override existing installation, if exists",
        default=False,
        nargs=argparse.OPTIONAL,
    )

    @with_category(CMD_SETUP)
    @allow_blank
    @with_argparser(install_oss_cad_suite_parser)
    def do_install_oss_cad_suite(self, args: argparse.Namespace) -> None:
        """Downloads and extracts the latest OSS CAD suite.

        Sets the the FAB_OSS_CAD_SUITE environment variable in the .env file.
        """
        if args.destination_folder == "":
            root_setting = FABulousSettings().root
            dest_dir = root_setting if root_setting is not None else Path.cwd()
        else:
            dest_dir = Path(args.destination_folder)

        install_oss_cad_suite(dest_dir, args.update_existing)

    @with_category(CMD_SETUP)
    @allow_blank
    @with_argparser(filePathOptionalParser)
    def do_load_fabric(self, args: argparse.Namespace) -> None:
        """Loads 'fabric.csv' file and generates an internal representation of the
        fabric. Does this by parsing input arguments, sets an internal state to indicate
        that fabric is loaded and determines the available tiles by comparing
        directories in the project with tiles defined by fabric.

        Logs error if no CSV file is found.
        """
        # if no argument is given will use the one set by set_fabric_csv
        # else use the argument

        logger.info("Loading fabric")
        if args.file == Path():
            if self.csvFile.exists():
                logger.info(
                    "Found fabric.csv in the project directory loading that file as the definition of the fabric"
                )
                self.fabulousAPI.loadFabric(self.csvFile)
            else:
                raise FileNotFoundError(
                    "No argument is given and the csv file is set but the file does not exist"
                )
        else:
            self.fabulousAPI.loadFabric(args.file)
            self.csvFile = args.file

        self.fabricLoaded = True
        tileByPath = [
            f.stem for f in (self.projectDir / "Tile/").iterdir() if f.is_dir()
        ]
        tileByFabric = list(self.fabulousAPI.fabric.tileDic.keys())
        superTileByFabric = list(self.fabulousAPI.fabric.superTileDic.keys())
        self.allTile = list(set(tileByPath) & set(tileByFabric + superTileByFabric))

        self.enable_category(CMD_FABRIC_FLOW)
        self.enable_category(CMD_USER_DESIGN_FLOW)
        logger.info("Complete")

    bel_name_parser = Cmd2ArgumentParser()
    bel_name_parser.add_argument("bel_name", help="Name of the BEL to print")

    @with_category(CMD_HELPER)
    @with_argparser(bel_name_parser)
    def do_print_bel(self, args: argparse.Namespace) -> None:
        """Prints a Bel object to the console."""
        if not self.fabricLoaded:
            raise CommandError("Need to load fabric first")

        bels = self.fabulousAPI.getBels()
        for i in bels:
            if i.name == args.bel_name:
                logger.info(f"\n{pprint.pformat(i, width=200)}")
                return
        raise CommandError(f"Bel {args.bel_name} not found in fabric")

    @with_category(CMD_HELPER)
    @with_argparser(tile_single_parser)
    def do_print_tile(self, args: argparse.Namespace) -> None:
        """Prints a tile object to the console."""

        if not self.fabricLoaded:
            raise CommandError("Need to load fabric first")

        if (tile := self.fabulousAPI.getTile(args.tile)) or (
            tile := self.fabulousAPI.getSuperTile(args.tile)
        ):
            logger.info(f"\n{pprint.pformat(tile, width=200)}")
        else:
            raise CommandError(f"Tile {args.tile} not found in fabric")

    @with_category(CMD_FABRIC_FLOW)
    @with_argparser(tile_list_parser)
    def do_gen_config_mem(self, args: argparse.Namespace) -> None:
        """Generates configuration memory of the given tile by by parsing input
        arguments and calling 'genConfigMem'.

        Logs generation processes for each specified tile.
        """
        logger.info(f"Generating Config Memory for {' '.join(args.tiles)}")
        for i in args.tiles:
            logger.info(f"Generating configMem for {i}")
            self.fabulousAPI.setWriterOutputFile(
                self.projectDir / f"Tile/{i}/{i}_ConfigMem.{self.extension}"
            )
            self.fabulousAPI.genConfigMem(
                i, self.projectDir / f"Tile/{i}/{i}_ConfigMem.csv"
            )
        logger.info("ConfigMem generation complete")

    @with_category(CMD_FABRIC_FLOW)
    @with_argparser(tile_list_parser)
    def do_gen_switch_matrix(self, args: argparse.Namespace) -> None:
        """Generates switch matrix of given tile by parsing input arguments and calling
        'genSwitchMatrix'.

        Also logs generation process for each specified tile.
        """
        logger.info(f"Generating switch matrix for {' '.join(args.tiles)}")
        for i in args.tiles:
            logger.info(f"Generating switch matrix for {i}")
            self.fabulousAPI.setWriterOutputFile(
                self.projectDir / f"Tile/{i}/{i}_switch_matrix.{self.extension}"
            )
            self.fabulousAPI.genSwitchMatrix(i)
        logger.info("Switch matrix generation complete")

    @with_category(CMD_FABRIC_FLOW)
    @with_argparser(tile_list_parser)
    def do_gen_tile(self, args: argparse.Namespace) -> None:
        """Generates given tile with switch matrix and configuration memory by parsing
        input arguments, calls functions such as 'genSwitchMatrix' and 'genConfigmem'.
        Handles both regular tiles and super tiles with sub-tiles.

        Also logs generation process for each specified tile and sub-tile.
        """

        logger.info(f"Generating tile {' '.join(args.tiles)}")
        for t in args.tiles:
            if subTiles := [
                f.stem for f in (self.projectDir / f"Tile/{t}").iterdir() if f.is_dir()
            ]:
                logger.info(
                    f"{t} is a super tile, generating {t} with sub tiles {' '.join(subTiles)}"
                )
                for st in subTiles:
                    # Gen switch matrix
                    logger.info(f"Generating switch matrix for tile {t}")
                    logger.info(f"Generating switch matrix for {st}")
                    self.fabulousAPI.setWriterOutputFile(
                        self.projectDir
                        / f"Tile/{t}/{st}/{st}_switch_matrix.{self.extension}"
                    )
                    self.fabulousAPI.genSwitchMatrix(st)
                    logger.info(f"Generated switch matrix for {st}")

                    # Gen config mem
                    logger.info(f"Generating configMem for tile {t}")
                    logger.info(f"Generating ConfigMem for {st}")
                    self.fabulousAPI.setWriterOutputFile(
                        self.projectDir
                        / f"Tile/{t}/{st}/{st}_ConfigMem.{self.extension}"
                    )
                    self.fabulousAPI.genConfigMem(
                        st, self.projectDir / f"Tile/{t}/{st}/{st}_ConfigMem.csv"
                    )
                    logger.info(f"Generated configMem for {st}")

                    # Gen tile
                    logger.info(f"Generating subtile for tile {t}")
                    logger.info(f"Generating subtile {st}")
                    self.fabulousAPI.setWriterOutputFile(
                        self.projectDir / f"Tile/{t}/{st}/{st}.{self.extension}"
                    )
                    self.fabulousAPI.genTile(st)
                    logger.info(f"Generated subtile {st}")

                # Gen super tile
                logger.info(f"Generating super tile {t}")
                self.fabulousAPI.setWriterOutputFile(
                    self.projectDir / f"Tile/{t}/{t}.{self.extension}"
                )
                self.fabulousAPI.genSuperTile(t)
                logger.info(f"Generated super tile {t}")
                continue

            # Gen switch matrix
            self.do_gen_switch_matrix(t)

            # Gen config mem
            self.do_gen_config_mem(t)

            logger.info(f"Generating tile {t}")
            # Gen tile
            self.fabulousAPI.setWriterOutputFile(
                self.projectDir / f"Tile/{t}/{t}.{self.extension}"
            )
            self.fabulousAPI.genTile(t)
            logger.info(f"Generated tile {t}")

        logger.info("Tile generation complete")

    @with_category(CMD_FABRIC_FLOW)
    def do_gen_all_tile(self, *_ignored: str) -> None:
        """Generates all tiles using the API."""
        logger.info("Generating all tiles")
        self.fabulousAPI.genAllTiles(self.allTile)
        logger.info("All tiles generation complete")

    @with_category(CMD_FABRIC_FLOW)
    def do_gen_fabric(self, *_ignored: str) -> None:
        """Generates fabric based on the loaded fabric by calling 'do_gen_all_tile' and
        'genFabric'.

        Logs start and completion of fabric generation process.
        """
        logger.info(f"Generating fabric {self.fabulousAPI.fabric.name}")
        self.onecmd_plus_hooks("gen_all_tile")
        if self.exit_code != 0:
            raise CommandError("Tile generation failed")
        self.fabulousAPI.setWriterOutputFile(
            self.projectDir / f"Fabric/{self.fabulousAPI.fabric.name}.{self.extension}"
        )
        self.fabulousAPI.genFabric()
        logger.info("Fabric generation complete")

    geometryParser = Cmd2ArgumentParser()
    geometryParser.add_argument(
        "padding",
        type=int,
        help="Padding value for geometry generation",
        choices=range(4, 33),
        metavar="[4-32]",
        nargs="?",
        default=8,
    )

    @with_category(CMD_FABRIC_FLOW)
    @allow_blank
    @with_argparser(geometryParser)
    def do_gen_geometry(self, args: argparse.Namespace) -> None:
        """Generates geometry of fabric for FABulator by checking if fabric is loaded,
        and calling 'genGeometry' and passing on padding value. Default padding is '8'.

        Also logs geometry generation, the used padding value and any warning about
        faulty padding arguments, as well as errors if the fabric is not loaded or the
        padding is not within the valid range of 4 to 32.
        """
        logger.info(f"Generating geometry for {self.fabulousAPI.fabric.name}")
        geomFile = self.projectDir / f"{self.fabulousAPI.fabric.name}_geometry.csv"
        self.fabulousAPI.setWriterOutputFile(geomFile)

        self.fabulousAPI.genGeometry(args.padding)
        logger.info("Geometry generation complete")
        logger.info(f"{geomFile} can now be imported into FABulator")

    @with_category(CMD_GUI)
    def do_start_FABulator(self, *_ignored: str) -> None:
        """Starts FABulator if an installation can be found.

        If no installation can be found, a warning is produced.
        """
        logger.info("Checking for FABulator installation")
        fabulatorRoot = FABulousSettings().fabulator_root

        if fabulatorRoot is None:
            logger.warning("FABULATOR_ROOT environment variable not set.")
            logger.warning(
                "Install FABulator (https://github.com/FPGA-Research-Manchester/FABulator) "
                "and set the FABULATOR_ROOT environment variable to the root directory to use this feature."
            )
            return

        if not Path(fabulatorRoot).exists():
            raise EnvironmentNotSet(
                f"FABULATOR_ROOT environment variable set to {fabulatorRoot} but the directory does not exist."
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
                "Failed to start FABulator. Please ensure that the FABULATOR_ROOT environment variable is set correctly "
                "and that FABulator is installed."
            ) from e

    @with_category(CMD_FABRIC_FLOW)
    def do_gen_bitStream_spec(self, *_ignored: str) -> None:
        """Generates bitstream specification using the API."""
        logger.info("Generating bitstream specification")
        self.fabulousAPI.saveBitStreamSpec()
        logger.info("Bitstream specification generation complete")

    @with_category(CMD_FABRIC_FLOW)
    def do_gen_top_wrapper(self, *_ignored: str) -> None:
        """Generates top wrapper of the fabric by calling 'genTopWrapper'."""
        logger.info("Generating top wrapper")
        self.fabulousAPI.setWriterOutputFile(
            self.projectDir
            / f"Fabric/{self.fabulousAPI.fabric.name}_top.{self.extension}"
        )
        self.fabulousAPI.genTopWrapper()
        logger.info("Top wrapper generation complete")

    @with_category(CMD_FABRIC_FLOW)
    def do_run_FABulous_fabric(self, *_ignored: str) -> None:
        """Generates the fabric using the complete FABulous fabric flow from the API."""
        logger.info("Running FABulous")
        success = self.fabulousAPI.runFABulousFabricFlow()
        if not success:
            raise CommandError("FABulous fabric flow failed")

    @with_category(CMD_FABRIC_FLOW)
    def do_gen_model_npnr(self, *_ignored: str) -> None:
        """Generates Nextpnr model using the API."""
        logger.info("Generating npnr model")
        self.fabulousAPI.saveRoutingModel()
        logger.info("Generated npnr model")

    @with_category(CMD_USER_DESIGN_FLOW)
    @with_argparser(filePathRequireParser)
    def do_place_and_route(self, args: argparse.Namespace) -> None:
        """Runs place and route using the API."""
        self.fabulousAPI.runPlaceAndRoute(args.file)

    @with_category(CMD_USER_DESIGN_FLOW)
    @with_argparser(filePathRequireParser)
    def do_gen_bitStream_binary(self, args: argparse.Namespace) -> None:
        """Generates bitstream using the API."""
        self.fabulousAPI.generateBitstream(args.file)

    simulation_parser = Cmd2ArgumentParser()
    simulation_parser.add_argument(
        "format",
        choices=["vcd", "fst"],
        default="fst",
        help="Output format of the simulation",
    )
    simulation_parser.add_argument(
        "file",
        type=Path,
        completer=Cmd.path_complete,
        help="Path to the bitstream file",
    )

    @with_category(CMD_USER_DESIGN_FLOW)
    @with_argparser(simulation_parser)
    def do_run_simulation(self, args: argparse.Namespace) -> None:
        """Simulate using the API."""
        if not args.file.is_relative_to(self.projectDir):
            bitstreamPath = self.projectDir / Path(args.file)
        else:
            bitstreamPath = args.file
        self.fabulousAPI.runSimulation(bitstreamPath, args.format)

    @with_category(CMD_USER_DESIGN_FLOW)
    @with_argparser(filePathRequireParser)
    def do_run_FABulous_bitstream(self, args: argparse.Namespace) -> None:
        """Runs FABulous bitstream generation flow using the API.

        Note: This is a simplified version. The synthesis step would need
        to be implemented separately as it involves external tools.
        """
        logger.info("Running FABulous bitstream flow")

        # Check for external primitives library
        primsLib = self.projectDir / "user_design/custom_prims.v"
        if primsLib.exists():
            logger.info(f"Found external primsLib: {primsLib}")
        else:
            logger.info("No external primsLib found.")

        # Note: Synthesis step would be handled here before calling the API flow
        logger.warning("Synthesis step needs to be implemented separately")

        # For now, just try to run the flow assuming synthesis was done
        success = self.fabulousAPI.runFABulousBitstreamFlow(args.file)
        if not success:
            raise CommandError("FABulous bitstream generation failed")

    @with_category(CMD_SCRIPT)
    @with_argparser(filePathRequireParser)
    def do_run_tcl(self, args: argparse.Namespace) -> None:
        """Executes TCL script relative to the project directory, specified by
        <tcl_scripts>. Uses the 'tk' module to create TCL commands.

        Also logs usage errors and file not found errors.
        """
        if not args.file.exists():
            raise FileNotFoundError(
                f"Cannot find {args.file} file, please check the path and try again."
            )

        if self.force:
            logger.warning(
                "TCL script does not work with force mode, TCL will stop on first error"
            )

        logger.info(f"Execute TCL script {args.file}")

        with Path(args.file).open() as f:
            script = f.read()
        self.tcl.eval(script)

        logger.info("TCL script executed")

    @with_category(CMD_SCRIPT)
    @with_argparser(filePathRequireParser)
    def do_run_script(self, args: argparse.Namespace) -> None:
        """Executes script."""
        if not args.file.exists():
            raise FileNotFoundError(
                f"Cannot find {args.file} file, please check the path and try again."
            )

        logger.info(f"Execute script {args.file}")

        with Path(args.file).open() as f:
            for i in f:
                self.onecmd_plus_hooks(i.strip())
                if self.exit_code != 0:
                    if not self.force:
                        raise CommandError(
                            f"Script execution failed at line: {i.strip()}"
                        )
                    logger.error(
                        f"Script execution failed at line: {i.strip()} but continuing due to force mode"
                    )

        logger.info("Script executed")

    @with_category(CMD_USER_DESIGN_FLOW)
    @with_argparser(userDesignRequireParser)
    def do_gen_user_design_wrapper(self, args: argparse.Namespace) -> None:
        if not self.fabricLoaded:
            raise CommandError("Need to load fabric first")

        self.fabulousAPI.generateUserDesignTopWrapper(
            args.user_design, args.user_design_top_wrapper
        )

    gen_tile_parser = Cmd2ArgumentParser()
    gen_tile_parser.add_argument(
        "tile_path",
        type=Path,
        help="Path to the target tile directory",
        completer=Cmd.path_complete,
    )

    gen_tile_parser.add_argument(
        "--no-switch-matrix",
        "-nosm",
        help="Do not generate a Tile Switch Matrix",
        action="store_true",
    )

    @with_category(CMD_TOOLS)
    @with_argparser(gen_tile_parser)
    def do_generate_custom_tile_config(self, args: argparse.Namespace) -> None:
        """Generates a custom tile configuration for a given tile folder or path to bel
        folder. A tile .csv file and a switch matrix .list file will be generated.

        The provided path may contain bel files, which will be included in the generated
        tile .csv file as well as the generated switch matrix .list file.
        """

        if not args.tile_path.is_dir():
            logger.error(f"{args.tile_path} is not a directory or does not exist")
            return

        tile_csv = generateCustomTileConfig(args.tile_path)

        if not args.no_switch_matrix:
            parseTilesCSV(tile_csv)

    @with_category(CMD_FABRIC_FLOW)
    @with_argparser(tile_list_parser)
    def do_gen_io_tiles(self, args: argparse.Namespace) -> None:
        if args.tiles:
            for tile in args.tiles:
                self.fabulousAPI.genIOBelForTile(tile)

    @with_category(CMD_FABRIC_FLOW)
    @allow_blank
    def do_gen_io_fabric(self, _args: str) -> None:
        self.fabulousAPI.genFabricIOBels()

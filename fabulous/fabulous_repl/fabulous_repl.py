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
import sys
import tkinter as tk
import traceback
from collections.abc import Callable
from decimal import Decimal
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

from fabulous.custom_exception import CommandError, InvalidFileType
from fabulous.fabric_cad.gen_npnr_model import PLACEMENT_ESTIMATE_TEXT
from fabulous.fabric_generator.code_generator.code_generator_Verilog import (
    VerilogCodeGenerator,
)
from fabulous.fabric_generator.code_generator.code_generator_VHDL import (
    VHDLCodeGenerator,
)
from fabulous.fabric_generator.gds_generator.steps.tile_area_opt import OptMode
from fabulous.fabric_generator.gen_fabric.fabric_automation import (
    generateCustomTileConfig,
)
from fabulous.fabric_generator.parser.parse_csv import parseTilesCSV
from fabulous.fabulous_api import FABulous_API
from fabulous.fabulous_repl import cmd_compile_design, cmd_run_simulation
from fabulous.fabulous_repl.cmd_gui import GuiCommandSet
from fabulous.fabulous_repl.cmd_helper import HelperCommandSet
from fabulous.fabulous_repl.cmd_macro import MacroFlowCommandSet
from fabulous.fabulous_repl.cmd_script import ScriptCommandSet
from fabulous.fabulous_repl.cmd_setup import SetupCommandSet
from fabulous.fabulous_repl.cmd_timing import TimingCommandSet
from fabulous.fabulous_repl.helper import (
    CommandPipeline,
    allow_blank,
    wrap_with_except_handling,
)
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
CMD_TIMING_MODEL = "Timing Characterization"

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
    run_fab
    compile_design ./user_design/sequential_16bit_en.v
    run_simulation fst ./user_design/sequential_16bit_en.bin
"""


class FABulousREPL(Cmd):
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
    max_job : int
        Maximum number of parallel jobs, -1 to use all CPU cores, by default 4

    Attributes
    ----------
    intro : str
        Introduction message displayed when CLI starts
    prompt : str
        Command prompt string displayed to users
    fabulousAPI : FABulous_API
        Instance of the FABulous API for fabric operations
    projectDir : Path
        Current project directory path
    top : str
        Top-level module name for synthesis
    all_tile : list[str]
        List of all tile names in the current fabric
    csvFile : Path
        Path to the fabric CSV definition file
    extension : str
        File extension for HDL files ("v" for Verilog, "vhd" for VHDL)
    script : str
        Batch script commands to execute
    force : bool
        If true, force operations without confirmation
    interactive : bool
        If true, run in interactive CLI mode
    max_job : int
        Maximum number of parallel jobs for tile generation
    do_compile_design : Callable
        Method to compile user design through synthesis, PnR, and bitstream generation
    filePathOptionalParser : Cmd2ArgumentParser
        Argument parser for commands with an optional file path argument
    filePathRequireParser : Cmd2ArgumentParser
        Argument parser for commands with a required file path argument
    userDesignRequireParser : Cmd2ArgumentParser
        Argument parser for commands requiring a user design file path
    tile_list_parser : Cmd2ArgumentParser
        Argument parser for commands accepting a list of tile names
    tile_single_parser : Cmd2ArgumentParser
        Argument parser for commands accepting a single tile name
    clone_tile_parser : Cmd2ArgumentParser
        Argument parser for the clone_tile command
    install_oss_cad_suite_parser : Cmd2ArgumentParser
        Argument parser for the install-oss-cad-suite command
    geometryParser : Cmd2ArgumentParser
        Argument parser for the gen_geometry command
    do_run_simulation : Callable
        Method to run simulation of a compiled user design
    gen_tile_parser : Cmd2ArgumentParser
        Argument parser for the gen_tile command
    gds_parser : Cmd2ArgumentParser
        Argument parser for the run_gds command
    io_pin_config_parser : Cmd2ArgumentParser
        Argument parser for the gen_io_pin_config command
    gui_parser : Cmd2ArgumentParser
        Argument parser for the open_gui command

    Notes
    -----
    This CLI extends the cmd.Cmd class to provide command completion, help system,
    and command history. It supports both interactive mode and batch script execution.
    """

    intro: str = INTO_STRING
    prompt: str = "FABulous> "
    fabulousAPI: FABulous_API
    projectDir: Path
    top: str
    all_tile: list[str]
    csvFile: Path
    extension: str = "v"
    script: str = ""
    force: bool = False
    interactive: bool = True
    max_job: int = 4

    def __init__(
        self,
        writerType: str | None,
        force: bool = False,
        interactive: bool = False,
        verbose: bool = False,
        debug: bool = False,
        max_job: int = 4,
    ) -> None:
        super().__init__(
            persistent_history_file=f"{get_context().proj_dir}/{META_DATA_DIR}/.fabulous_history",
            allow_cli_args=False,
            command_sets=[
                HelperCommandSet(),
                ScriptCommandSet(),
                SetupCommandSet(),
                GuiCommandSet(),
                TimingCommandSet(),
                MacroFlowCommandSet(),
            ],
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
        categorize(self.do_run_pyscript, CMD_SCRIPT)

        self.tcl = tk.Tcl()
        # get_all_commands() includes commands provided by CommandSets, which are
        # bound to the instance (not the class), so iterating the class would miss them.
        for command in self.get_all_commands():
            func = getattr(self, f"do_{command}")
            self.tcl.createcommand(command, wrap_with_except_handling(func))

        self.disable_category(
            CMD_FABRIC_FLOW, "Fabric Flow commands are disabled until fabric is loaded"
        )
        self.disable_category(
            CMD_USER_DESIGN_FLOW,
            "User Design Flow commands are disabled until fabric is loaded",
        )
        self.disable_category(
            CMD_GUI, "GUI commands are disabled until gen_geometry is run"
        )
        self.disable_category(
            CMD_HELPER, "Helper commands are disabled until fabric is loaded"
        )

    def onecmd(
        self, statement: Statement | str, *, add_to_history: bool = True
    ) -> bool:
        """Override the onecmd method to handle exceptions."""
        self.exit_code = 0
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
        """Exit the FABulous shell and log info message."""
        logger.info("Exiting FABulous shell")
        return True

    def do_quit(self, *_ignored: str) -> None:
        """Exit the FABulous shell and log info message."""
        self.onecmd_plus_hooks("exit")

    def do_q(self, *_ignored: str) -> None:
        """Exit the FABulous shell and log info message."""
        self.onecmd_plus_hooks("exit")

    # Legacy synthesis parser — kept for backwards compatibility with existing
    # scripts that pass flags like -extra-plib, -nofsm, etc. directly.
    _synthesis_parser = Cmd2ArgumentParser(
        description="[DEPRECATED] Use 'compile_design --synth-only' instead."
    )
    _synthesis_parser.add_argument(
        "files",
        type=Path,
        nargs="+",
        completer=Cmd.path_complete,
    )
    _synthesis_parser.add_argument("-top", type=str, default="top_wrapper")
    _synthesis_parser.add_argument("-auto-top", action="store_true")
    _synthesis_parser.add_argument("-blif", type=Path)
    _synthesis_parser.add_argument("-edif", type=Path)
    _synthesis_parser.add_argument("-json", type=Path)
    _synthesis_parser.add_argument("-lut", type=str, default="4")
    _synthesis_parser.add_argument("-plib", type=str)
    _synthesis_parser.add_argument("-extra-plib", type=Path, action="append")
    _synthesis_parser.add_argument("-extra-map", type=Path, action="append")
    _synthesis_parser.add_argument("-encfile", type=Path)
    _synthesis_parser.add_argument("-nofsm", action="store_true")
    _synthesis_parser.add_argument("-noalumacc", action="store_true")
    _synthesis_parser.add_argument(
        "-carry", type=str, default="none", choices=["none", "ha"]
    )
    _synthesis_parser.add_argument("-noregfile", action="store_true")
    _synthesis_parser.add_argument("-iopad", action="store_true")
    _synthesis_parser.add_argument("-complex-dff", action="store_true")
    _synthesis_parser.add_argument("-noflatten", action="store_true")
    _synthesis_parser.add_argument("-nordff", action="store_true")
    _synthesis_parser.add_argument("-noshare", action="store_true")
    _synthesis_parser.add_argument("-run", type=str)
    _synthesis_parser.add_argument("-no-rw-check", action="store_true")

    @with_category(CMD_USER_DESIGN_FLOW)
    @with_argparser(_synthesis_parser)
    def do_synthesis(self, args: argparse.Namespace) -> None:
        """Run Yosys synthesis for the specified Verilog files.

        deprecated: Use ``compile_design --synth-only`` instead.
        """
        logger.warning(
            "The 'synthesis' command is deprecated. Use 'compile_design' instead."
        )

        # Translate legacy flags into --synth-extra-args for compile_design
        extra = []
        if args.blif:
            extra.append(f"-blif {args.blif}")
        if args.edif:
            extra.append(f"-edif {args.edif}")
        if args.lut:
            extra.append(f"-lut {args.lut}")
        if args.plib:
            extra.append(f"-plib {args.plib}")
        if args.extra_plib:
            extra.extend(f"-extra-plib {p}" for p in args.extra_plib)
        if args.extra_map:
            extra.extend(f"-extra-map {m}" for m in args.extra_map)
        if args.encfile:
            extra.append(f"-encfile {args.encfile}")
        if args.nofsm:
            extra.append("-nofsm")
        if args.noalumacc:
            extra.append("-noalumacc")
        if args.carry and args.carry != "none":
            extra.append(f"-carry {args.carry}")
        if args.noregfile:
            extra.append("-noregfile")
        if args.iopad:
            extra.append("-iopad")
        if args.complex_dff:
            extra.append("-complex-dff")
        if args.noflatten:
            extra.append("-noflatten")
        if args.nordff:
            extra.append("-nordff")
        if args.noshare:
            extra.append("-noshare")
        if args.run:
            extra.append(f"-run {args.run}")
        if args.no_rw_check:
            extra.append("-no-rw-check")

        cmd = f"compile_design {' '.join(str(f) for f in args.files)} --synth-only"
        if args.top != "top_wrapper":
            cmd += f" -top {args.top}"
        if args.json:
            cmd += f" -json {args.json}"
        if extra:
            cmd += f' --synth-extra-args "{" ".join(extra)}"'

        self.onecmd_plus_hooks(cmd)

    do_compile_design: Callable = cmd_compile_design.do_compile_design

    filePathOptionalParser: Cmd2ArgumentParser = Cmd2ArgumentParser()
    filePathOptionalParser.add_argument(
        "file",
        type=Path,
        help="Path to the target file",
        default="",
        nargs=argparse.OPTIONAL,
        completer=Cmd.path_complete,
    )

    filePathRequireParser: Cmd2ArgumentParser = Cmd2ArgumentParser()
    filePathRequireParser.add_argument(
        "file", type=Path, help="Path to the target file", completer=Cmd.path_complete
    )

    userDesignRequireParser: Cmd2ArgumentParser = Cmd2ArgumentParser()
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

    tile_list_parser: Cmd2ArgumentParser = Cmd2ArgumentParser()
    tile_list_parser.add_argument(
        "tiles",
        type=str,
        help="A list of tile",
        nargs="+",
        completer=lambda self: self.fab.getTiles(),
    )

    tile_single_parser: Cmd2ArgumentParser = Cmd2ArgumentParser()
    tile_single_parser.add_argument(
        "tile",
        type=str,
        help="A tile",
        completer=lambda self: self.fab.getTiles(),
    )

    clone_tile_parser: Cmd2ArgumentParser = Cmd2ArgumentParser()
    clone_tile_parser.add_argument(
        "src_tile",
        type=str,
        help="Name of the tile to clone (looked up in Tile/) or path to a tile dir",
    )
    clone_tile_parser.add_argument(
        "dst_tile",
        type=str,
        help="Name for the cloned tile (placed in Tile/) or path to destination dir",
    )
    clone_tile_parser.add_argument(
        "--no-register",
        action="store_true",
        default=False,
        help="Skip adding the new tile to fabric.csv",
    )

    install_oss_cad_suite_parser: Cmd2ArgumentParser = Cmd2ArgumentParser()
    install_oss_cad_suite_parser.add_argument(
        "destination_folder",
        type=Path,
        help="Destination folder for the installation",
        default="",
        completer=Cmd.path_complete,
        nargs=argparse.OPTIONAL,
    )
    install_oss_cad_suite_parser.add_argument(
        "update",
        type=bool,
        help="Update/override existing installation, if exists",
        default=False,
        nargs=argparse.OPTIONAL,
    )

    @with_category(CMD_FABRIC_FLOW)
    @with_argparser(tile_list_parser)
    def do_gen_config_mem(self, args: argparse.Namespace) -> None:
        """Generate configuration memory of the given tile.

        Parsing input arguments and calling `genConfigMem`.

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
        """Generate switch matrix of given tile.

        Parsing input arguments and calling `genSwitchMatrix`.

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
        """Generate given tile with switch matrix and configuration memory.

        Parsing input arguments, call functions such as `genSwitchMatrix` and
        `genConfigMem`. Handle both regular tiles and super tiles with sub-tiles.

        Also logs generation process for each specified tile and sub-tile.
        """
        logger.info(f"Generating tile {' '.join(args.tiles)}")
        for t in args.tiles:
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

                # Gen supertile switch matrix (no-op if no supertile_matrix file)
                logger.info(f"Generating switch matrix for super tile {t}")
                self.fabulousAPI.setWriterOutputFile(
                    f"{self.projectDir}/Tile/{t}/{t}_switch_matrix.{self.extension}"
                )
                self.fabulousAPI.gen_super_tile_switch_matrix(t)
                logger.info(f"Generated switch matrix for super tile {t}")

                # Gen supertile ConfigMem (no-op if no ST config bits)
                logger.info(f"Generating ConfigMem for super tile {t}")
                self.fabulousAPI.setWriterOutputFile(
                    f"{self.projectDir}/Tile/{t}/{t}_ConfigMem.{self.extension}"
                )
                self.fabulousAPI.gen_super_tile_config_mem(t)
                logger.info(f"Generated ConfigMem for super tile {t}")

                # Gen super tile
                logger.info(f"Generating super tile {t}")
                self.fabulousAPI.setWriterOutputFile(
                    f"{self.projectDir}/Tile/{t}/{t}.{self.extension}"
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
                f"{self.projectDir}/Tile/{t}/{t}.{self.extension}"
            )
            self.fabulousAPI.genTile(t)
            logger.info(f"Generated tile {t}")

        logger.info("Tile generation complete")

    @with_category(CMD_FABRIC_FLOW)
    def do_gen_all_tile(self, *_ignored: str) -> None:
        """Generate all tiles by calling `do_gen_tile`."""
        logger.info("Generating all tiles")
        self.do_gen_tile(" ".join(self.all_tile))
        logger.info("All tiles generation complete")

    @with_category(CMD_FABRIC_FLOW)
    def do_gen_fabric(self, *_ignored: str) -> None:
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

    geometryParser: Cmd2ArgumentParser = Cmd2ArgumentParser()
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
        """Generate geometry of fabric for FABulator.

        Checking if fabric is loaded, and calling 'genGeometry' and passing on padding
        value. Default padding is '8'.

        Also logs geometry generation, the used padding value and any warning about
        faulty padding arguments, as well as errors if the fabric is not loaded or the
        padding is not within the valid range of 4 to 32.
        """
        logger.info(f"Generating geometry for {self.fabulousAPI.fabric.name}")
        geom_file = f"{self.projectDir}/{self.fabulousAPI.fabric.name}_geometry.csv"
        self.fabulousAPI.setWriterOutputFile(geom_file)

        self.fabulousAPI.genGeometry(args.padding)
        logger.info("Geometry generation complete")
        logger.info(f"{geom_file} can now be imported into FABulator")

    @with_category(CMD_FABRIC_FLOW)
    def do_gen_bitStream_spec(self, *_ignored: str) -> None:
        """Generate bitstream specification of the fabric.

        By calling `genBitStreamSpec` and saving the specification to a binary and CSV
        file.

        Also logs the paths of the output files.
        """
        logger.info("Generating bitstream specification")
        spec_object = self.fabulousAPI.genBitStreamSpec()

        logger.info(f"output file: {self.projectDir}/{META_DATA_DIR}/bitStreamSpec.bin")
        with Path(f"{self.projectDir}/{META_DATA_DIR}/bitStreamSpec.bin").open(
            "wb"
        ) as outFile:
            pickle.dump(spec_object, outFile)

        logger.info(f"output file: {self.projectDir}/{META_DATA_DIR}/bitStreamSpec.csv")
        with Path(f"{self.projectDir}/{META_DATA_DIR}/bitStreamSpec.csv").open(
            "w", encoding="utf-8", newline="\n"
        ) as f:
            w = csv.writer(f)
            for key1 in spec_object["TileSpecs"]:
                w.writerow([key1])
                for key2, val in spec_object["TileSpecs"][key1].items():
                    w.writerow([key2, val])
        logger.info("Bitstream specification generation complete")

    @with_category(CMD_FABRIC_FLOW)
    def do_gen_top_wrapper(self, *_ignored: str) -> None:
        """Generate top wrapper of the fabric by calling `genTopWrapper`."""
        logger.info("Generating top wrapper")
        self.fabulousAPI.setWriterOutputFile(
            f"{self.projectDir}/Fabric/{self.fabulousAPI.fabric.name}_top.{self.extension}"
        )
        self.fabulousAPI.genTopWrapper()
        logger.info("Top wrapper generation complete")

    @with_category(CMD_FABRIC_FLOW)
    def do_run_fab(self, *_ignored: str) -> None:
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
    def do_run_FABulous_fabric(self, *_ignored: str) -> None:
        """Generate the fabric based on the CSV file.

        deprecated: Use ``run_fab`` instead.
        """
        logger.warning(
            "The 'run_FABulous_fabric' command is deprecated. Use 'run_fab' instead."
        )
        self.do_run_fab()

    @with_category(CMD_FABRIC_FLOW)
    def do_gen_model_npnr(self, *_ignored: str) -> None:
        """Generate Nextpnr model of fabric.

        By parsing various required files for place and route such as `pips.txt`,
        `bel.txt`, `bel.v2.txt` and `template.pcf`. Output files are written to the
        directory specified by `metaDataDir` within `projectDir`.

        Logs output file directories.
        """
        logger.info("Generating npnr model")
        npnr_model = self.fabulousAPI.gen_routing_model()
        logger.info(f"output file: {self.projectDir}/{META_DATA_DIR}/pips.txt")
        with Path(f"{self.projectDir}/{META_DATA_DIR}/pips.txt").open("w") as f:
            f.write(npnr_model[0])

        logger.info(f"output file: {self.projectDir}/{META_DATA_DIR}/bel.txt")
        with Path(f"{self.projectDir}/{META_DATA_DIR}/bel.txt").open("w") as f:
            f.write(npnr_model[1])

        logger.info(f"output file: {self.projectDir}/{META_DATA_DIR}/bel.v2.txt")
        with Path(f"{self.projectDir}/{META_DATA_DIR}/bel.v2.txt").open("w") as f:
            f.write(npnr_model[2])

        logger.info(f"output file: {self.projectDir}/{META_DATA_DIR}/bel.v3.txt")
        with Path(f"{self.projectDir}/{META_DATA_DIR}/bel.v3.txt").open("w") as f:
            f.write(npnr_model[3])

        logger.info(f"output file: {self.projectDir}/{META_DATA_DIR}/template.pcf")
        with Path(f"{self.projectDir}/{META_DATA_DIR}/template.pcf").open("w") as f:
            f.write(npnr_model[4])

        estimatePath = Path(f"{self.projectDir}/{META_DATA_DIR}/placement_estimate.txt")
        logger.info(f"output file: {estimatePath}")
        estimatePath.write_text(PLACEMENT_ESTIMATE_TEXT)

        logger.info("Generated npnr model")

    @with_category(CMD_USER_DESIGN_FLOW)
    @with_argparser(filePathRequireParser)
    def do_place_and_route(self, args: argparse.Namespace) -> None:
        """Run place and route with Nextpnr for a given JSON file.

        deprecated: Use ``compile_design --pnr-only`` instead.
        """
        logger.warning(
            "The 'place_and_route' command is deprecated. "
            "Use 'compile_design --pnr-only' instead."
        )

        path = Path(args.file)
        if path.suffix != ".json":
            raise InvalidFileType(
                "No json file provided. Usage: place_and_route <json_file>"
            )

        self.onecmd_plus_hooks(f"compile_design {path} --pnr-only")

    @with_category(CMD_USER_DESIGN_FLOW)
    @with_argparser(filePathRequireParser)
    def do_gen_bitStream_binary(self, args: argparse.Namespace) -> None:
        """Generate bitstream of a given design.

        deprecated: Use ``compile_design`` which includes bitstream generation.
        """
        logger.warning(
            "The 'gen_bitStream_binary' command is deprecated. "
            "Use 'compile_design' instead, which includes bitstream generation."
        )

        if args.file.suffix != ".fasm":
            raise InvalidFileType(
                "No fasm file provided. Usage: gen_bitStream_binary <fasm_file>"
            )

        self.onecmd_plus_hooks(f"compile_design {args.file} --bitgen-only")

    do_run_simulation: Callable = cmd_run_simulation.do_run_simulation

    @with_category(CMD_USER_DESIGN_FLOW)
    @with_argparser(filePathRequireParser)
    def do_run_FABulous_bitstream(self, args: argparse.Namespace) -> None:
        """Run FABulous to generate bitstream on a given design.

        deprecated: Use ``compile_design`` instead.
        """
        logger.warning(
            "The 'run_FABulous_bitstream' command is deprecated. "
            "Use 'compile_design' instead."
        )

        if args.file.suffix not in [".v", ".sv"]:
            raise InvalidFileType(
                "No Verilog or SystemVerilog file provided. "
                "Usage: run_FABulous_bitstream <top_module_file>"
            )

        self.onecmd_plus_hooks(f"compile_design {args.file}")

    @with_category(CMD_SCRIPT)
    @with_argparser(filePathRequireParser)
    def do_run_script(self, args: argparse.Namespace) -> None:
        """Execute script."""
        if not args.file.exists():
            raise FileNotFoundError(
                f"Cannot find {args.file} file, please check the path and try again."
            )

        logger.info(f"Execute script {args.file}")

        with Path(args.file).open() as f:
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
    @with_argparser(userDesignRequireParser)
    def do_gen_user_design_wrapper(self, args: argparse.Namespace) -> None:
        """Generate a user design wrapper for the specified user design.

        This command creates a wrapper module that interfaces the user design
        with the FPGA fabric, handling signal connections and naming conventions.

        Parameters
        ----------
        args : argparse.Namespace
            Command arguments containing:
            - user_design: Path to the user design file
            - user_design_top_wrapper: Path for the generated wrapper file

        Raises
        ------
        CommandError
            If the fabric has not been loaded yet.
        """
        if not self.fabric_loaded:
            raise CommandError("Need to load fabric first")
        project_dir = get_context().proj_dir
        self.fabulousAPI.generateUserDesignTopWrapper(
            project_dir / Path(args.user_design),
            project_dir / args.user_design_top_wrapper,
        )

    gen_tile_parser: Cmd2ArgumentParser = Cmd2ArgumentParser()
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
        """Generate a custom tile configuration for a given tile folder.

        Or path to bel folder. A tile `.csv` file and a switch matrix `.list` file will
        be generated.

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
        """Generate I/O BELs for specified tiles.

        This command generates Input/Output Basic Elements of Logic (BELs) for the
        specified tiles, enabling external connectivity for the FPGA fabric.

        Parameters
        ----------
        args : argparse.Namespace
            Command arguments containing:
            - tiles: List of tile names to generate I/O BELs for
        """
        if args.tiles:
            for tile in args.tiles:
                self.fabulousAPI.genIOBelForTile(tile)

    @with_category(CMD_FABRIC_FLOW)
    @allow_blank
    def do_gen_io_fabric(self, _args: str) -> None:
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

    gds_parser: Cmd2ArgumentParser = Cmd2ArgumentParser()
    gds_parser.add_argument(
        "tile",
        type=str,
        help="A tile",
        completer=lambda self: self.fab.getTiles(),
    )
    gds_parser.add_argument(
        "--optimise",
        "-opt",
        type=OptMode,
        nargs="?",
        const=OptMode.BALANCE,
        default=OptMode.NO_OPT,
        help="Optimize the GDS layout. Available modes: "
        + ", ".join(m.value for m in OptMode),
    )
    gds_parser.add_argument(
        "--override",
        help="Override config with a custom YAML config file",
        type=Path,
    )
    gds_parser.add_argument(
        "--fix-width",
        type=Decimal,
        default=None,
        metavar="WIDTH",
        help="Lock the tile width to WIDTH and minimise the height "
        "(implies --optimise find_min_height).",
    )
    gds_parser.add_argument(
        "--fix-height",
        type=Decimal,
        default=None,
        metavar="HEIGHT",
        help="Lock the tile height to HEIGHT and minimise the width "
        "(implies --optimise find_min_width).",
    )
    gds_parser.add_argument(
        "--io-pin-config", help="Path to a custom IO pin config YAML file", type=Path
    )

    io_pin_config_parser: Cmd2ArgumentParser = Cmd2ArgumentParser()
    io_pin_config_parser.add_argument(
        "tile",
        type=str,
        help="A tile or supertile",
        completer=lambda self: self.all_tile,
    )
    io_pin_config_parser.add_argument(
        "output",
        type=Path,
        help="Output path for the generated IO pin config YAML",
        nargs=argparse.OPTIONAL,
        completer=Cmd.path_complete,
    )

    @with_category(CMD_FABRIC_FLOW)
    @with_argparser(io_pin_config_parser)
    def do_gen_io_pin_config(self, args: argparse.Namespace) -> None:
        """Generate an IO pin configuration YAML file for a tile or supertile."""
        logger.info(f"Generating IO pin config for {args.tile}")

        tile = self.fabulousAPI.getTile(args.tile)
        if tile is None:
            logger.error(f"Tile {args.tile} not found in fabric definition")
            return

        output_path = args.output
        if output_path is None:
            output_path = (
                self.projectDir / "Tile" / args.tile / f"{args.tile}_io_pin_order.yaml"
            )

        output_path.parent.mkdir(parents=True, exist_ok=True)
        self.fabulousAPI.gen_io_pin_order_config(tile, output_path)

        logger.info(f"Generated IO pin config at {output_path}")
        logger.info("IO pin config generation complete")

    gui_parser: Cmd2ArgumentParser = Cmd2ArgumentParser()
    gui_parser.add_argument("file", nargs="?", help="file to open", default=None)
    gui_parser.add_argument(
        "--tile",
        help="launch GUI to view a specific tile",
        default=None,
        completer=lambda self: self.fab.getTiles(),
    )
    gui_parser.add_argument(
        "--fabric",
        help="launch GUI to view the entire fabric",
        default=False,
        action="store_true",
    )
    gui_parser.add_argument(
        "--last-run", help="launch GUI to view last run", action="store_true"
    )

    gui_parser.add_argument(
        "--head",
        help="number of item to select from",
        default=10,
    )

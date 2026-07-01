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
import os
import sys
import tkinter as tk
import traceback
from collections.abc import Callable
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
from fabulous.fabric_generator.code_generator.code_generator_Verilog import (
    VerilogCodeGenerator,
)
from fabulous.fabric_generator.code_generator.code_generator_VHDL import (
    VHDLCodeGenerator,
)
from fabulous.fabulous_api import FABulous_API
from fabulous.fabulous_repl import cmd_compile_design, cmd_run_simulation
from fabulous.fabulous_repl.cmd_fabric_gen import FabricGenCommandSet
from fabulous.fabulous_repl.cmd_gui import GuiCommandSet
from fabulous.fabulous_repl.cmd_helper import HelperCommandSet
from fabulous.fabulous_repl.cmd_macro import MacroFlowCommandSet
from fabulous.fabulous_repl.cmd_script import ScriptCommandSet
from fabulous.fabulous_repl.cmd_setup import SetupCommandSet
from fabulous.fabulous_repl.cmd_timing import TimingCommandSet
from fabulous.fabulous_repl.helper import (
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
    do_run_simulation : Callable
        Method to run simulation of a compiled user design
    gen_tile_parser : Cmd2ArgumentParser
        Argument parser for the gen_tile command
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
                FabricGenCommandSet(),
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

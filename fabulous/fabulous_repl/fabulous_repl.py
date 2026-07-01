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

import os
import sys
import tkinter as tk
import traceback
from pathlib import Path
from typing import Annotated

from cmd2 import (
    Cmd,
    Settable,
    Statement,
    categorize,
    with_annotated,
    with_category,
)
from cmd2.annotated import Argument
from loguru import logger

from fabulous.custom_exception import CommandError
from fabulous.fabric_generator.code_generator.code_generator_Verilog import (
    VerilogCodeGenerator,
)
from fabulous.fabric_generator.code_generator.code_generator_VHDL import (
    VHDLCodeGenerator,
)
from fabulous.fabulous_api import FABulous_API
from fabulous.fabulous_repl.cmd_fabric_gen import FabricGenCommandSet
from fabulous.fabulous_repl.cmd_gui import GuiCommandSet
from fabulous.fabulous_repl.cmd_helper import HelperCommandSet
from fabulous.fabulous_repl.cmd_macro import MacroFlowCommandSet
from fabulous.fabulous_repl.cmd_script import ScriptCommandSet
from fabulous.fabulous_repl.cmd_setup import SetupCommandSet
from fabulous.fabulous_repl.cmd_timing import TimingCommandSet
from fabulous.fabulous_repl.cmd_user_design import UserDesignCommandSet
from fabulous.fabulous_repl.command_set_base import (
    CMD_FABRIC_FLOW,
    CMD_GUI,
    CMD_HELPER,
    CMD_OTHER,
    CMD_SCRIPT,
    CMD_USER_DESIGN_FLOW,
    META_DATA_DIR,
)
from fabulous.fabulous_repl.helper import (
    wrap_with_except_handling,
)
from fabulous.fabulous_settings import get_context

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
        If True, run in interactive REPL mode, by default False
    verbose : bool
        If True, enable verbose logging, by default False
    debug : bool
        If True, enable debug logging, by default False
    max_job : int
        Maximum number of parallel jobs, -1 to use all CPU cores, by default 4

    Attributes
    ----------
    intro : str
        Introduction message displayed when REPL starts
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
        If true, run in interactive REPL mode
    max_job : int
        Maximum number of parallel jobs for tile generation

    Notes
    -----
    This REPL extends the cmd.Cmd class to provide command completion, help system,
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
                MacroFlowCommandSet(),
                GuiCommandSet(),
                TimingCommandSet(),
                UserDesignCommandSet(),
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

    @with_category(CMD_SCRIPT)
    @with_annotated
    def do_run_script(
        self,
        file: Annotated[Path, Argument(help_text="Path to the target file")],
    ) -> None:
        """Execute script."""
        if not file.exists():
            raise FileNotFoundError(
                f"Cannot find {file} file, please check the path and try again."
            )

        logger.info(f"Execute script {file}")

        with file.open() as f:
            for line in f:
                if line.startswith("#"):
                    continue
                self.onecmd_plus_hooks(line.strip())
                if self.exit_code != 0:
                    if not self.force:
                        raise CommandError(
                            f"Script execution failed at line: {line.strip()}"
                        )
                    logger.error(
                        f"Script execution failed at line: {line.strip()} "
                        "but continuing due to force mode"
                    )

        logger.info("Script executed")

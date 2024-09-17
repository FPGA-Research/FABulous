#!/usr/bin/env python

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
import cmd
import csv
import os
import pickle
import platform
import pprint
import readline
import shutil
import subprocess as sp
import sys
import tkinter as tk
import traceback
from contextlib import redirect_stdout
from glob import glob
from pathlib import PurePosixPath, PureWindowsPath, Path
from typing import List, Literal
from dotenv import load_dotenv

from loguru import logger

from FABulous.fabric_generator.code_generation_Verilog import VerilogWriter
from FABulous.fabric_generator.code_generation_VHDL import VHDLWriter
from FABulous.FABulous_API import FABulous

readline.set_completer_delims(" \t\n")
histfile = ""
histfile_size = 1000
MAX_BITBYTES = 16384
metaDataDir = ".FABulous"


def setup_logger(verbosity: int):
    # Remove the default logger to avoid duplicate logs
    logger.remove()

    # Define logger format
    if verbosity >= 1:
        log_format = (
            "<level>{level:}</level> | "
            "<cyan>[{time:DD-MM-YYYY HH:mm:ss]}</cyan> | "
            "<green>[{name}</green>:<green>{function}</green>:<green>{line}]</green> - "
            "<level>{message}</level>"
        )
    else:
        log_format = "<level>{level:}</level> | " "<level>{message}</level>"

    # Add logger to write logs to stdout
    logger.add(sys.stdout, format=log_format, level="DEBUG", colorize=True)


def setup_global_env_vars(args: argparse.Namespace) -> None:
    """
    Set up global  environment variables

    Parameters
    ----------
    args : argparse.Namespace
        Command line arguments
    """
    # Set FAB_ROOT environment variable
    fabulousRoot = os.getenv("FAB_ROOT")
    if fabulousRoot is None:
        os.environ["FAB_ROOT"] = str(Path(__file__).resolve().parent)
        logger.info("FAB_ROOT environment variable not set!")
        logger.info(f"Using {fabulousRoot} as FAB_ROOT")
    else:
        # If there is the FABulous folder in the FAB_ROOT, then set the FAB_ROOT to the FABulous folder
        if Path(fabulousRoot).exists():
            if Path(fabulousRoot).joinpath("FABulous").exists():
                fabulousRoot = str(Path(fabulousRoot).joinpath("FABulous"))
            os.environ["FAB_ROOT"] = fabulousRoot
        else:
            logger.error(
                f"FAB_ROOT environment variable set to {fabulousRoot} but the directory does not exist"
            )
            sys.exit()

        logger.info(f"FAB_ROOT set to {fabulousRoot}")

    # Load the .env file and make env variables available globally
    if args.globalDotEnv:
        gde = Path(args.globalDotEnv)
        if gde.is_file():
            load_dotenv(gde)
            logger.info(f"Load global .env file from {gde}")
        elif gde.joinpath(".env").exists() and gde.joinpath(".env").is_file():
            load_dotenv(gde.joinpath(".env"))
            logger.info(f"Load global .env file from {gde.joinpath('.env')}")
        else:
            logger.warning(f"No global .env file found at {gde}")
    elif (
        Path(os.getenv("FAB_ROOT")).joinpath(".env").exists()
        and Path(os.getenv("FAB_ROOT")).joinpath(".env").is_file()
    ):
        load_dotenv(Path(os.getenv("FAB_ROOT")).joinpath(".env"))
        logger.info(f"Loaded global .env file from {fabulousRoot}/.env")
    else:
        logger.warning("No global .env file found")

    # Set project directory env var, this can not be saved in the .env file,
    # since it can change if the project folder is moved
    if not os.getenv("FAB_PROJ_DIR"):
        os.environ["FAB_PROJ_DIR"] = args.project_dir


def setup_project_env_vars(args: argparse.Namespace) -> None:
    """
    Set up environment variables for the project

    Parameters
    ----------
    args : argparse.Namespace
        Command line arguments
    """
    # Load the .env file and make env variables available globally
    fabDir = Path(os.getenv("FAB_PROJ_DIR")).joinpath(".FABulous")
    if args.projectDotEnv:
        pde = Path(args.projectDotEnv)
        if pde.exists() and pde.is_file():
            load_dotenv(pde)
            logger.info(f"Loaded global .env file from pde")
    elif fabDir.joinpath(".env").exists() and fabDir.joinpath(".env").is_file():
        load_dotenv(fabDir.joinpath(".env"))
        logger.info(f"Loaded project .env file from {fabDir}/.env')")
    else:
        logger.warning("No project .env file found")

    # Overwrite project language param, if writer is specified as command line argument
    if args.writer:
        os.environ["FAB_PROJ_LANG"] = args.writer


def create_project(project_dir, type: Literal["verilog", "vhdl"] = "verilog"):
    """Creates a FABulous project containing all required files by copying
    the appropriate project template and the synthesis directory.

    File structure as follows:
        FABulous_project_template --> project_dir/
        fabic_cad/synth --> project_dir/Test/synth

    Parameters
    ----------
    project_dir : str
        Directory where the project will be created.
    type : Literal["verilog", "vhdl"], optional
        The type of project to create ("verilog" or "vhdl"), by default "verilog".
    """
    if os.path.exists(project_dir):
        logger.error("Project directory already exists!")
        sys.exit()
    else:
        os.mkdir(f"{project_dir}")

    os.mkdir(f"{project_dir}/.FABulous")
    fabulousRoot = os.getenv("FAB_ROOT")

    shutil.copytree(
        f"{fabulousRoot}/fabric_files/FABulous_project_template_{type}/",
        f"{project_dir}/",
        dirs_exist_ok=True,
    )
    shutil.copytree(
        f"{fabulousRoot}/fabric_cad/synth",
        f"{project_dir}/Test/synth",
        dirs_exist_ok=True,
    )

    with open(os.path.join(project_dir, ".FABulous/.env"), "w") as env_file:
        env_file.write(f"FAB_PROJ_LANG={type}\n")

    adjust_directory_in_verilog_tb(project_dir)


def copy_verilog_files(src, dst):
    """Copies all Verilog files from source directory to the destination directory.

    Parameters
    ----------
    src : str
        Source directory.
    dst : str
        Destination directory
    """
    for root, _, files in os.walk(src):
        for file in files:
            if file.endswith(".v"):
                source_path = os.path.join(root, file)
                destination_path = os.path.join(dst, file)
                shutil.copy(source_path, destination_path)


def remove_dir(path):
    """Removes a directory and all its contents.

    If the directory cannot be removed, logs OS error.

    Parameters
    ----------
    path : str
        Path of the directory to remove.
    """
    try:
        shutil.rmtree(path)
        pass
    except OSError as e:
        logger.error(f"{e}")


def make_hex(binfile, outfile):
    """Converts a binary file into hex file.

    If the binary file exceeds MAX_BITBYTES, logs error.

    Parameters
    ----------
    binfile : str
        Path to binary file.
    outfile : str
        Path to ouput hex file.
    """
    with open(binfile, "rb") as f:
        bindata = f.read()

    if len(bindata) > MAX_BITBYTES:
        logger.error("Binary file too big.")
        return

    with open(outfile, "w") as f:
        for i in range(MAX_BITBYTES):
            if i < len(bindata):
                print(f"{bindata[i]:02x}", file=f)
            else:
                print("0", file=f)


def adjust_directory_in_verilog_tb(project_dir):
    """Adjusts directory paths in a Verilog testbench file by replacing
    the string "PROJECT_DIR" in the project_template with the actual
    project directory.

    Parameters
    ----------
    project_dir : str
        Projet directory where the testbench file is located.
    """
    with open(
        f"{os.getenv('FAB_ROOT')}/fabric_files/FABulous_project_template_verilog/Test/sequential_16bit_en_tb.v",
        "rt",
    ) as fin:
        with open(f"{project_dir}/Test/sequential_16bit_en_tb.v", "wt") as fout:
            for line in fin:
                fout.write(line.replace("PROJECT_DIR", f"{project_dir}"))


def get_path(path):
    """Returns system-specific path object.

    Parameters
    ----------
    path : str
        File system path.

    Returns
    -------
    PurePath
        System-specific path object (PurePosixPath or PureWindowsPath)

    Raises
    ------
    NotImplementedError
        If the operating system is not supported.
    """
    system = platform.system()
    # Darwin corresponds to MacOS, which also uses POSIX-style paths
    if system == "Linux" or system == "Darwin":
        return PurePosixPath(path)
    elif system == "Windows":
        return PureWindowsPath(path)
    else:
        logger.error(f"Unsupported operating system: {system}")
        raise NotImplementedError


class PlaceAndRouteError(Exception):
    """An exception to be thrown when place and route fails."""


class SynthesisError(Exception):
    """An exception to be thrown when synthesis fails."""


class BitstreamGenerationError(Exception):
    """An exception to be thrown when the bitstream generation fails."""


class FABulousShell(cmd.Cmd):
    intro: str = f"""

    ______      ____        __
    |  ____/\   |  _ \      | |
    | |__ /  \  | |_) |_   _| | ___  _   _ ___
    |  __/ /\ \ |  _ <| | | | |/ _ \| | | / __|
    | | / ____ \| |_) | |_| | | (_) | |_| \__ \\
    |_|/_/    \_\____/ \__,_|_|\___/ \__,_|___/


Welcome to FABulous shell
You have started the FABulous shell with following options:
{' '.join(sys.argv[1:])}

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
    load_fabric
    run_FABulous_fabric
    run_FABulous_bitstream ./user_design/sequential_16bit_en.v
    """
    prompt: str = "FABulous> "
    fabricGen: FABulous
    projectDir: str
    top: str
    allTile: List[str]
    csvFile: str
    extension: str = "v"
    fabricLoaded: bool = False
    script: str = ""

    def __init__(self, fab: FABulous, projectDir: str, script: str = ""):
        """Initialises the FABulous shell instance.

        Determines file extension based on the type of writer used in 'fab'
        and sets fabricLoaded to true if 'fab' has 'fabric' attribute.

        Parameters
        ----------
        fab : FABulous
            Instance of the FABulous class used for fabric generation.
        projectDir : str
            Path to the project directory.
        script : str, optional
            Path to optional Tcl script to be executed, by default ""
        """
        super().__init__()
        self.fabricGen = fab
        self.projectDir = projectDir
        self.tiles = []
        self.superTiles = []
        self.csvFile = ""
        self.script = script
        self.verbose = False
        if isinstance(self.fabricGen.writer, VHDLWriter):
            self.extension = "vhdl"
        else:
            self.extension = "v"

        if hasattr(fab, "fabric"):
            self.fabricLoaded = True

    def preloop(self) -> None:
        """Execution before entering main command loop.
        Reads command history in 'histfile' if it exists, sets up exception
        handling for Tcl commands, executes Tcl scripts and if Tcl script
        contains 'exit' command, shell exits with code 0.
        """
        # File does not exist when the shell is started the first time after creating a new project
        if os.path.exists(histfile):
            readline.read_history_file(histfile)

        def wrap_with_except_handling(fun_to_wrap):
            """Decorator function that wraps 'fun_to_wrap' with exception handling.

            Parameters
            ----------
            fun_to_wrap : callable
                The function to be wrapped with exception handling.
            """

            def inter(*args, **varargs):
                """Wrapped function that executes 'fun_to_wrap' with arguments
                and exception handling.

                Parameters
                ----------
                *args : tuple
                    Positional arguments to pass to 'fun_to_wrap'.
                **varags : dict
                    Keyword arguments to pass to 'fun_to_wrap'.
                """
                try:
                    fun_to_wrap(*args, **varargs)
                except:
                    import traceback

                    traceback.print_exc()
                    sys.exit(1)

            return inter

        tcl = tk.Tcl()
        script = ""
        if self.script != "":
            with open(self.script, "r") as f:
                script = f.read()
            for fun in dir(self.__class__):
                if fun.startswith("do_"):
                    name = fun.strip("do_")
                    tcl.createcommand(
                        name, wrap_with_except_handling(getattr(self, fun))
                    )

        # os.chdir(os.getenv('FAB_PROJ_DIR'))
        tcl.eval(script)

        if "exit" in script:
            exit(0)

    def postloop(self):
        """Excecution after exiting main command loop.
        Sets history length for readline using 'histfile_size' and
        writes command history to '.fabulous_history' file.
        """
        readline.set_history_length(histfile_size)
        histfile = f"{self.projectDir}/.FABulous/.fabulous_history"
        readline.write_history_file(histfile)

    def precmd(self, line: str) -> str:
        """Pre-processes command line before execution.

        Checks if fabric is loaded before allowing commands 'gen' or 'run'.

        If fabric is not loaded and command requires it, logs error and prevents
        execution.

        Parameters
        ----------
        line : str
            Command line input to pre-process

        Returns
        -------
        str
            Processed command line input, modified or empty if execution blocked.
        """
        if (
            ("gen" in line or "run" in line)
            and not self.fabricLoaded
            and "help" not in line
            and "?" not in line
        ):
            logger.error("Fabric not loaded")
            return ""
        return line

    def onecmd(self, line):
        try:
            return super().onecmd(line)
        except:
            print(traceback.format_exc())
            return False

    def emptyline(self):
        """Overrides the emptyline method, when pressing enter on an empty
        command line input it will have no effect.
        """
        pass

    def parse(self, line: str) -> List[str]:
        """Parses command line into list of tokens.
        Splits the input line based on whitespace.

        Parameters
        ----------
        line : str
            Command line input to parse.

        Returns
        -------
        List[str]
            List of tokens extraced from the input line.
        """
        return line.split()

    def _complete_path(self, path):
        """Completes partial or full file path.

        If 'path' is a directory, returns list of files and directories inside.

        If 'path' is a file, reutrns a list containing the file itself.

        Parameters
        ----------
        path : str
            Partial or full path to complete.

        Returns
        -------
        List[str]
            List of possible completions for given 'path'
        """
        if os.path.isdir(path):
            return glob(os.path.join(path, "*"))
        else:
            return glob(path + "*")

    def _complete_tileName(self, text):
        """Completes partial tile name using list of all tiles.

        Finds tile names from 'self.allTile' that start with provided 'text'.

        Parameters
        ----------
        text : srt
            Partial text of tile name to complete.

        Returns
        -------
        List[str]
            List of tile names from 'self.allTile' starting with 'text'
        """
        return [t for t in self.allTile if t.startswith(text)]

    def do_shell(self, args):
        """Runs a shell command, if no command is provided prints prompt,
        if command execution fails, logs error message.

        Parameters
        ----------
        args : str
            Shell command to be exectued.
        """
        if not args:
            logger.error("Please provide a command to run")
            return

        try:
            sp.run(args, shell=True)
        except sp.CalledProcessError:
            logger.error("Could not execute the requested command.")
            return

    def do_exit(self, *ignore):
        """Exits the FABulous shell and logs info message.

        Parameters
        ----------
        *ignore : tuple
            Arguments passed will be ignored.

        Returns
        -------
        bool
            Always returns True to indicate the shell will exit.
        """
        logger.info("Exiting FABulous shell")
        return True

    def do_load_fabric(self, args=""):
        """Loads 'fabric.csv' file and generates an internal representation
        of the fabric. Does this by parsing input arguments, sets an internal
        state to indicate that fabric is loaded and determines the available tiles
        by comparing directories in the project with tiles defined by fabric.

        Logs error if no CSV file is found.

        Usage:
            load_fabric /path/to/fabric.csv
            load_fabric <defaults to path in 'set_fabric_csv'>

        Parameters
        ----------
        args : str, optional
            Path to the CSV file to load. If unavailable will use
            path set by 'set_fabric_csv' or looks for 'fabric.csv'
            in project directory, by default ""
        """
        args = self.parse(args)
        # if no argument is given will use the one set by set_fabric_csv
        # else use the argument
        logger.info("Loading fabric")
        if len(args) == 0:
            if self.csvFile != "" and os.path.exists(self.csvFile):
                self.fabricGen.loadFabric(self.csvFile)
            elif os.path.exists(f"{self.projectDir}/fabric.csv"):
                logger.info(
                    "Found fabric.csv in the project directory loading that file as the definition of the fabric"
                )
                self.fabricGen.loadFabric(f"{self.projectDir}/fabric.csv")
                self.csvFile = f"{self.projectDir}/fabric.csv"
            else:
                logger.error(
                    "No argument is given and no csv file is set or the file does not exist"
                )
                return
        else:
            self.fabricGen.loadFabric(args[0])
            self.csvFile = args[0]

        self.fabricLoaded = True
        # self.projectDir = os.path.split(self.csvFile)[0]
        tileByPath = [
            f.name for f in os.scandir(f"{self.projectDir}/Tile/") if f.is_dir()
        ]
        tileByFabric = list(self.fabricGen.fabric.tileDic.keys())
        superTileByFabric = list(self.fabricGen.fabric.superTileDic.keys())
        self.allTile = list(set(tileByPath) & set(tileByFabric + superTileByFabric))
        logger.info("Complete")

    def complete_load_fabric(self, text, *ignored):
        return self._complete_path(text)

    def do_print_bel(self, args):
        """Prints a Bel object to the console.

        Usage:
            print_bel <bel_name>

        Parameters
        ----------
        args : str
            Name of the Bel object to print.
        """
        args = self.parse(args)
        if len(args) != 1:
            logger.error("Please provide a Bel name")
            return

        if not self.fabricLoaded:
            logger.error("Need to load fabric first")
            return

        bels = self.fabricGen.getBels()
        for i in bels:
            if i.name == args[0]:
                logger.info(f"\n{pprint.pformat(i, width=200)}")
                return
        logger.error("Bel not found")

    def complete_print_bel(self, text, *ignored):
        return [i.name for i in self.fabricGen.getBels() if i.name.startswith(text)]

    def do_print_tile(self, args):
        """Prints a tile object to the console.

        Usage:
            print_tile <tile_name>

        Parameters
        ----------
        args : str
            Name of the tile object to print.
        """
        args = self.parse(args)
        if len(args) != 1:
            logger.error("Please provide a tile name")
            return

        if not self.fabricLoaded:
            logger.error("Need to load fabric first")
            return

        if tile := self.fabricGen.getTile(args[0]):
            logger.info(f"\n{pprint.pformat(tile, width=200)}")
        elif tile := self.fabricGen.getSuperTile(args[0]):
            logger.info(f"\n{pprint.pformat(tile, width=200)}")
        else:
            logger.error("Tile not found")

    def complete_print_tile(self, text, *ignored):
        return self._complete_tileName(text)

    def do_set_fabric_csv(self, args):
        """Sets the CSV file to be used for fabric generation.

        Usage:
            set_fabric_csv /path/to/fabric.csv

        Parameters
        ----------
        args : str
            Path to CSV file to be set.
        """
        args = self.parse(args)
        self.csvFile = args[0]

    def complete_set_fabric_csv(self, text, *ignored):
        return self._complete_path(text)

    def do_gen_config_mem(self, args):
        """Generates configuration memory of the given tile by
        by parsing input arguments and calling 'genConfigMem'.

        Logs generation processes for each specified tile.

        Usage:
            gen_config_mem

        Parameters
        ----------
        args : str
            Names of tiles which generate the configuration memory.
        """
        args = self.parse(args)
        logger.info(f"Generating Config Memory for {' '.join(args)}")
        for i in args:
            logger.info(f"Generating configMem for {i}")
            self.fabricGen.setWriterOutputFile(
                f"{self.projectDir}/Tile/{i}/{i}_ConfigMem.{self.extension}"
            )
            self.fabricGen.genConfigMem(
                i, f"{self.projectDir}/Tile/{i}/{i}_ConfigMem.csv"
            )
        logger.info("Generating configMem complete")

    def complete_gen_config_mem(self, text, *ignored):
        return self._complete_tileName(text)

    def do_gen_switch_matrix(self, args):
        """Generates switch matrix of given tile by parsing input arguments
        and calling 'genSwitchMatrix'.

        Also logs generation process for each specified tile.

        Usage:
            gen_switch_matrix

        Parameters
        ----------
        args : str
            Name of tiles which generate the switch matrix.
        """
        args = self.parse(args)
        logger.info(f"Generating switch matrix for {' '.join(args)}")
        for i in args:
            logger.info(f"Generating switch matrix for {i}")
            self.fabricGen.setWriterOutputFile(
                f"{self.projectDir}/Tile/{i}/{i}_switch_matrix.{self.extension}"
            )
            self.fabricGen.genSwitchMatrix(i)
        logger.info("Switch matrix generation complete")

    def complete_gen_switch_matrix(self, text, *ignored):
        return self._complete_tileName(text)

    def do_gen_tile(self, args):
        """Generates given tile with switch matrix and configuration memory
        by parsing input arguments, calls functions such as 'genSwitchMatrix' and
        'genConfigmem'. Handles both regular tiles and super tiles with sub-tiles.

        Also logs generation process for each specified tile and sub-tile.

        Usage:
            gen_tile

        Parameters
        ----------
        args : str
            Names of tiles to be generated.
        """
        if not isinstance(args, list):
            args = self.parse(args)
        logger.info(f"Generating tile {' '.join(args)}")
        for t in args:
            if subTiles := [
                f.name for f in os.scandir(f"{self.projectDir}/Tile/{t}") if f.is_dir()
            ]:
                logger.info(
                    f"{t} is a super tile, generating {t} with sub tiles {' '.join(subTiles)}"
                )
                for st in subTiles:
                    # Gen switch matrix
                    logger.info(f"Generating switch matrix for tile {t}")
                    logger.info(f"Generating switch matrix for {st}")
                    self.fabricGen.setWriterOutputFile(
                        f"{self.projectDir}/Tile/{t}/{st}/{st}_switch_matrix.{self.extension}"
                    )
                    self.fabricGen.genSwitchMatrix(st)
                    logger.info(f"Generated switch matrix for {st}")

                    # Gen config mem
                    logger.info(f"Generating configMem for tile {t}")
                    logger.info(f"Generating ConfigMem for {st}")
                    self.fabricGen.setWriterOutputFile(
                        f"{self.projectDir}/Tile/{t}/{st}/{st}_ConfigMem.{self.extension}"
                    )
                    self.fabricGen.genConfigMem(
                        st, f"{self.projectDir}/Tile/{t}/{st}/{st}_ConfigMem.csv"
                    )
                    logger.info(f"Generated configMem for {st}")

                    # Gen tile
                    logger.info(f"Generating subtile for tile {t}")
                    logger.info(f"Generating subtile {st}")
                    self.fabricGen.setWriterOutputFile(
                        f"{self.projectDir}/Tile/{t}/{st}/{st}.{self.extension}"
                    )
                    self.fabricGen.genTile(st)
                    logger.info(f"Generated subtile {st}")

                # Gen super tile
                logger.info(f"Generating super tile {t}")
                self.fabricGen.setWriterOutputFile(
                    f"{self.projectDir}/Tile/{t}/{t}.{self.extension}"
                )
                self.fabricGen.genSuperTile(t)
                logger.info(f"Generated super tile {t}")
                continue

            # Gen switch matrix
            self.do_gen_switch_matrix(t)

            # Gen config mem
            self.do_gen_config_mem(t)

            logger.info(f"Generating tile {t}")
            # Gen tile
            self.fabricGen.setWriterOutputFile(
                f"{self.projectDir}/Tile/{t}/{t}.{self.extension}"
            )
            self.fabricGen.genTile(t)
            logger.info(f"Generated tile {t}")

        logger.info("Tile generation complete")

    def complete_gen_tile(self, text: str, *ignored):
        return self._complete_tileName(text)

    def do_gen_all_tile(self, *ignored):
        """Generates all tiles by calling 'do_gen_tile'.

        Usage:
            gen_all_tile

        Parameters
        ----------
        *ignored : tuple
            Ignores additional arguments.
        """
        logger.info("Generating all tiles")
        self.do_gen_tile(self.allTile)
        logger.info("Generated all tiles")

    def do_gen_fabric(self, *ignored):
        """Generates fabric based on the loaded fabric by calling
        'do_gen_all_tile' and 'genFabric'. Logs start and completion of
        fabric generation process.

        Usage:
            gen_fabric

        Parameters
        ----------
        *ignored : tuple
            Ignores additional arguments.
        """
        logger.info(f"Generating fabric {self.fabricGen.fabric.name}")
        self.do_gen_all_tile()
        self.fabricGen.setWriterOutputFile(
            f"{self.projectDir}/Fabric/{self.fabricGen.fabric.name}.{self.extension}"
        )
        self.fabricGen.genFabric()
        logger.info("Fabric generation complete")

    def do_gen_geometry(self, *vargs):
        """Generates geometry of fabric for FABulator by checking if fabric
        is loaded, and calling 'genGeometry' and passing on padding value. Default
        padding is '8'.

        Also logs geometry generation, the used padding value and any warning about faulty padding arguments,
        as well as errors if the fabric is not loaded or the padding is not within the valid range of 4 to 32.

        Usage:
            gen_geometry [defaults to 8]
            gen_geometry [4-32]

        Parameters
        ----------
        *vargs : tuple
            Optional padding argument. Should be an integer between 4 and 32.

        Returns
        -------
        str
            Returns empty string if fabric is not loaded.
        """
        if not self.fabricLoaded:
            logger.error("Fabric not loaded")
            return ""

        logger.info(f"Generating geometry for {self.fabricGen.fabric.name}")
        geomFile = f"{self.projectDir}/{self.fabricGen.fabric.name}_geometry.csv"
        self.fabricGen.setWriterOutputFile(geomFile)

        paddingDefault = 8
        if len(vargs) == 1 and vargs[0] != "":
            try:
                padding = int(vargs[0])
                logger.info(f"Setting padding to {padding}")
            except ValueError:
                logger.warning(
                    f"Faulty padding argument, defaulting to {paddingDefault}"
                )
                padding = paddingDefault
        else:
            logger.info(f"No padding specified, defaulting to {paddingDefault}")
            padding = paddingDefault

        if 4 <= padding <= 32:
            self.fabricGen.genGeometry(padding)
            logger.info("Geometry generation complete")
            logger.info(f"{geomFile} can now be imported into FABulator")
        else:
            logger.error("padding has to be between 4 and 32 inclusively!")

    def do_start_FABulator(self, *ignored):
        """Starts FABulator if an installation can be found.
        If no installation can be found, a warning is produced.

        Usage:
            start_FABulator

        Parameters
        ----------
        *ignored : tuple
            Ignores additional arguments.

        """
        logger.info("Checking for FABulator installation")
        fabulatorRoot = os.getenv("FABULATOR_ROOT")

        if fabulatorRoot is None:
            logger.warning("FABULATOR_ROOT environment variable not set.")
            logger.warning(
                "Install FABulator (https://github.com/FPGA-Research-Manchester/FABulator) "
                "and set the FABULATOR_ROOT environment variable to the root directory to use this feature."
            )
            return

        if not os.path.exists(fabulatorRoot):
            logger.error(
                f"FABULATOR_ROOT environment variable set to {fabulatorRoot} but the directory does not exist."
            )
            return

        logger.info(f"Found FABulator installation at {fabulatorRoot}")
        logger.info(f"Trying to start FABulator...")

        startupCmd = ["mvn", "-f", f"{fabulatorRoot}/pom.xml", "javafx:run"]
        try:
            if self.verbose:
                # log FABulator output to the FABulous shell
                sp.Popen(startupCmd)
            else:
                # discard FABulator output
                sp.Popen(startupCmd, stdout=sp.DEVNULL, stderr=sp.DEVNULL)

        except sp.SubprocessError:
            logger.error("Startup of FABulator failed.")

    def do_gen_bitStream_spec(self, *ignored):
        """Generates bitstream specification of the fabric by calling
        'genBitStreamspec' and saving the specification to a binary and CSV file.

        Also logs the paths of the output files.

        Usage:
            gen_bitStream_spec

        Parameters
        ----------
        *ignored : tuple
            Ignores additional arguments.
        """
        logger.info("Generating bitstream specification")
        specObject = self.fabricGen.genBitStreamSpec()

        logger.info(f"output file: {self.projectDir}/{metaDataDir}/bitStreamSpec.bin")
        with open(
            f"{self.projectDir}/{metaDataDir}/bitStreamSpec.bin", "wb"
        ) as outFile:
            pickle.dump(specObject, outFile)

        logger.info(f"output file: {self.projectDir}/{metaDataDir}/bitStreamSpec.csv")
        with open(f"{self.projectDir}/{metaDataDir}/bitStreamSpec.csv", "w") as f:
            w = csv.writer(f)
            for key1 in specObject["TileSpecs"]:
                w.writerow([key1])
                for key2, val in specObject["TileSpecs"][key1].items():
                    w.writerow([key2, val])
        logger.info("Generated bitstream specification")

    def do_gen_top_wrapper(self, *ignored):
        """Generates top wrapper of the fabric by calling 'genTopWrapper'.

        Usage:
            gen_top_wrapper

        Parameters
        ----------
        *ignored : tuple
            Ignores additional arguments.
        """
        logger.info("Generating top wrapper")
        self.fabricGen.setWriterOutputFile(
            f"{self.projectDir}/Fabric/{self.fabricGen.fabric.name}_top.{self.extension}"
        )
        self.fabricGen.genTopWrapper()
        logger.info("Generated top wrapper")

    def do_run_FABulous_fabric(self, *ignored):
        """Generates the fabric based on the CSV file, creates bitstream specification
        of the fabric, top wrapper of the fabric, Nextpnr model of the fabric and
        geometry information of the fabric. Does this by calling the respective functions
        'do_gen_[function]'.

        Usage:
            run_FABulous_fabric

        Returns
        -------
        int
            Returns 0 on completion.
        """
        logger.info("Running FABulous")
        self.do_gen_fabric()
        self.do_gen_bitStream_spec()
        self.do_gen_top_wrapper()
        self.do_gen_model_npnr()
        self.do_gen_geometry()
        logger.info("FABulous fabric flow complete")
        return 0

    def do_gen_model_npnr(self, *ignored):
        """Generates Nextpnr model of fabric by parsing various required files
        for place and route such as 'pips.txt', 'bel.txt', 'bel.v2.txt' and
        'templace.pcf'. Output files are written to the directory specified by
        'metaDataDir' within 'projectDir'.

        Logs output file directories.

        Usage:
            gen_model_npnr

        Parameters
        ----------
        *ignored : tuple
            Ignores additional arguments.

        """
        logger.info("Generating npnr model")
        npnrModel = self.fabricGen.genRoutingModel()
        logger.info(f"output file: {self.projectDir}/{metaDataDir}/pips.txt")
        with open(f"{self.projectDir}/{metaDataDir}/pips.txt", "w") as f:
            f.write(npnrModel[0])

        logger.info(f"output file: {self.projectDir}/{metaDataDir}/bel.txt")
        with open(f"{self.projectDir}/{metaDataDir}/bel.txt", "w") as f:
            f.write(npnrModel[1])

        logger.info(f"output file: {self.projectDir}/{metaDataDir}/bel.v2.txt")
        with open(f"{self.projectDir}/{metaDataDir}/bel.v2.txt", "w") as f:
            f.write(npnrModel[2])

        logger.info(f"output file: {self.projectDir}/{metaDataDir}/template.pcf")
        with open(f"{self.projectDir}/{metaDataDir}/template.pcf", "w") as f:
            f.write(npnrModel[3])

        logger.info("Generated npnr model")

    # TODO update once have transition the model gen to object based
    # def do_gen_model_npnr_pair(self):
    #     """(Currently not working!)

    #     Generates a pair Nextpnr (npnr) model of
    #     the fabric by calling 'GetFabric' and 'genFabricObject' then saving
    #     the npnr components in their respective files.

    #     Also logs the path of the output files.

    #     Usage:
    #         gen_model_npnr_pair

    #     """
    #     logger.info("Generating pair npnr model")
    #     if self.csvFile:
    #         FabricFile = [i.strip("\n").split(",") for i in open(self.csvFile)]
    #         fabric = GetFabric(FabricFile)
    #         fabricObject = genFabricObject(fabric, FabricFile)
    #         pipFile = open(f"{self.projectDir}/{metaDataDir}/pips.txt", "w")
    #         belFile = open(f"{self.projectDir}/{metaDataDir}/bel.txt", "w")
    #         pairFile = open(f"{self.projectDir}/{metaDataDir}/wirePairs.csv", "w")
    #         constraintFile = open(f"{self.projectDir}/{metaDataDir}/template.pcf", "w")

    #         npnrModel = model_gen_npnr.genNextpnrModelOld(fabricObject, False)

    #         pipFile.write(npnrModel[0])
    #         belFile.write(npnrModel[1])
    #         constraintFile.write(npnrModel[2])
    #         pairFile.write(npnrModel[3])

    #         pipFile.close()
    #         belFile.close()
    #         constraintFile.close()
    #         pairFile.close()

    #     else:
    #         logger.error(
    #             "Need to call sec_fabric_csv before running model_gen_npnr_pair"
    #         )
    #     logger.info("Generated pair npnr model")

    def do_synthesis(self, args):
        """Runs Yosys using Nextpnr JSON backend to synthesise the Verilog design specified
        by <top_module_file> and generates a Nextpnr-compatible JSON file for further place
        and route process.

        Also logs usage errors or synthesis failures.

        Usage:
            synthesis <top_module_file>

        Parameters
        ----------
        args : str
            Command-line argument specifying top module Verilog file.

        Raises
        ------
        TypeError
            If number of arguments is not exactly 1.
        SynthesisError
            If synthesis process fails.
        """
        args = self.parse(args)
        if len(args) != 1:
            logger.error("Usage: synthesis <top_module_file>")
            print(args)
            raise TypeError(
                f"do_synthesis takes exactly one argument ({len(args)} given)"
            )
        logger.info(f"Running synthesis that targeting Nextpnr with design {args[0]}")
        path = get_path(args[0])
        parent = path.parent
        verilog_file = path.name
        top_module_name = path.stem
        if path.suffix != ".v":
            logger.error(
                """
                No verilog file provided.
                Usage: synthesis <top_module_file>
                """
            )
            return

        json_file = top_module_name + ".json"
        runCmd = [
            f"{os.getenv('FAB_YOSYS_PATH', 'yosys')}",
            "-p",
            f"synth_fabulous -top top_wrapper -json {self.projectDir}/{parent}/{json_file}",
            f"{self.projectDir}/{parent}/{verilog_file}",
            f"{self.projectDir}/{parent}/top_wrapper.v",
        ]
        try:
            sp.run(runCmd, check=True)
            logger.info("Synthesis completed")
        except sp.CalledProcessError:
            logger.error("Synthesis failed")
            raise SynthesisError

    def complete_synthesis(self, text, *ignored):
        return self._complete_path(text)

    def do_place_and_route(self, args):
        """Runs place and route with Nextpnr for a given JSON file generated by Yosys,
        which requires a Nextpnr model and JSON file first, generated by 'synthesis'.

        Also logs place and route error, file not found error and type error.

        Usage:
            place_and_route <json_file>

        Parameters
        ----------
        args : str
            Path to the JSON file generated by Yosys during synthesis.

        Raises
        ------
        TypeError
            If number of arguments is not exactly 1.
        FileNotFoundError
            If JSON, Pips or Bel required for place and route cannot be found.
        PlaceAndRouteError
            When process exits with a non-zero exit status indicating failure.
        """
        args = self.parse(args)
        if len(args) != 1:
            logger.error(
                "Usage: place_and_route_ <json_file> (<json_file> is generated by Yosys. Generate it by running `synthesis`.)"
            )
            raise TypeError(
                f"do_place_and_route takes exactly one argument ({len(args)} given)"
            )
        logger.info(f"Running Placement and Routing with Nextpnr for design {args[0]}")
        path = get_path(args[0])
        parent = path.parent
        json_file = path.name
        top_module_name = path.stem

        if path.suffix != ".json":
            logger.error(
                """
                No json file provided.
                Usage: place_and_route <json_file> (<json_file> is generated by Yosys. Generate it by running `synthesis`.)
                """
            )
            return

        fasm_file = top_module_name + ".fasm"
        log_file = top_module_name + "_npnr_log.txt"

        if parent == "":
            parent = "."

        if not os.path.exists(
            f"{self.projectDir}/.FABulous/pips.txt"
        ) or not os.path.exists(f"{self.projectDir}/.FABulous/bel.txt"):
            logger.error(
                "Pips and Bel files are not found, please run model_gen_npnr first"
            )
            raise FileNotFoundError

        if os.path.exists(f"{self.projectDir}/{parent}"):
            # TODO rewriting the fab_arch script so no need to copy file for work around
            if f"{json_file}" in os.listdir(f"{self.projectDir}/{parent}"):
                runCmd = [
                    f"FAB_ROOT={self.projectDir}",
                    f"{os.getenv('FAB_NEXTPNR_PATH', 'nextpnr-generic')}",
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
                try:
                    sp.run(
                        " ".join(runCmd),
                        stdout=sys.stdout,
                        stderr=sp.STDOUT,
                        check=True,
                        shell=True,
                    )
                except sp.CalledProcessError:
                    logger.error("Placement and Routing failed.")
                    raise PlaceAndRouteError

            else:
                logger.error(
                    f'Cannot find file "{json_file}" in path "./{parent}/", which is generated by running Yosys with Nextpnr backend (e.g. synthesis).'
                )
                raise FileNotFoundError

            logger.info("Placement and Routing completed")
        else:
            logger.error(f"Directory {self.projectDir}/{parent} does not exist.")
            raise FileNotFoundError

    def complete_place_and_route(self, text, *ignored):
        return self._complete_path(text)

    def do_gen_bitStream_binary(self, args):
        """Generates bitstream of a given design using FASM file and pre-generated
        bitstream specification file 'bitStreamSpec.bin'. Requires bitstream specification
        before use by running 'gen_bitStream_spec' and place and route file generated
        by running 'place_and_route'.

        Also logs output file directory, Bitstream generation error and file not found error.

        Usage:
            gen_bitStream_binary <fasm_file>

        Raises
        ------
        BitstreamGenerationError
            When 'bit_gen' exits with a non-zero exit status indicating failure.
        """
        args = self.parse(args)
        if len(args) != 1:
            logger.error("Usage: gen_bitStream_binary <fasm_file>")
            return
        path = get_path(args[0])
        parent = path.parent
        fasm_file = path.name
        top_module_name = path.stem

        if path.suffix != ".fasm":
            logger.error(
                """
                No fasm file provided.
                Usage: gen_bitStream_binary <fasm_file>
                """
            )
            return

        bitstream_file = top_module_name + ".bin"

        if not os.path.exists(f"{self.projectDir}/.FABulous/bitStreamSpec.bin"):
            logger.error(
                "Cannot find bitStreamSpec.bin file, which is generated by running gen_bitStream_spec"
            )
            return

        if not os.path.exists(f"{self.projectDir}/{parent}/{fasm_file}"):
            logger.error(
                f"Cannot find {self.projectDir}/{parent}/{fasm_file} file which is generated by running place_and_route. Potentially Place and Route Failed."
            )
            return

        logger.info(f"Generating Bitstream for design {self.projectDir}/{path}")
        logger.info(f"Outputting to {self.projectDir}/{parent}/{bitstream_file}")
        runCmd = [
            "bit_gen",
            "-genBitstream",
            f"{self.projectDir}/{parent}/{fasm_file}",
            f"{self.projectDir}/.FABulous/bitStreamSpec.bin",
            f"{self.projectDir}/{parent}/{bitstream_file}",
        ]
        try:
            sp.run(runCmd, check=True)
        except sp.CalledProcessError:
            logger.error("Bitstream generation failed")
            raise BitstreamGenerationError

        logger.info("Bitstream generated")

    def complete_gen_bitStream_binary(self, text, *ignored):
        return self._complete_path(text)

    def do_run_simulation(self, args):
        """Simulate given FPGA design using Icarus Verilog (iverilog).

        If <fst> is specified, waveform files in FST format will generate, <vcd>
        with generate VCD format. The bitstream_file argument should be a binary file
        generated by 'gen_bitStream_binary'. Verilog files from 'Tile' and 'Fabric'
        directories are copied to the temporary directory 'tmp', 'tmp' is deleted
        on simulation end.

        Also logs simulation error and file not found error and value error.

        Usage:
            run_simulation [<fst|vcd>] <bitstream_file>

        Parameters
        ----------
        args : List[str]
            Arguments provided for simulation.
        """
        args = self.parse(args)
        bitsream_arg = ""
        optional_arg = ""
        if len(args) == 1:
            bitsream_arg = args[0]
        elif len(args) == 2:
            optional_arg = args[0]
            bitsream_arg = args[1]
        else:
            logger.error("Usage: run_simulation [<fst|vcd>] <bitstream_file>")
            return

        path, bitstream = os.path.split(bitsream_arg)
        if len(bitstream.split(".")) != 2:
            logger.error(
                """
                No bitstream file specified.
                Usage: run_simulation [<fst|vcd>] <bitstream_file>
                """
            )
            return
        top_module, file_ending = bitstream.split(".")
        if file_ending != "bin":
            logger.error(
                """
                No bitstream file specified.
                Usage: run_simulation <bitstream_file>
                """
            )
            return
        if not os.path.exists(f"{self.projectDir}/{path}/"):
            logger.error(
                f"Cannot find {self.projectDir}/{path}/{bitstream} file which is generated by running gen_bitStream_binary. Potentially the bitstream generation failed."
            )
            return

        defined_option = ""
        if optional_arg == "fst":
            defined_option = "CREATE_FST"
        elif optional_arg == "vcd":
            defined_option = "CREATE_VCD"
        elif optional_arg == "":
            defined_option = ""
        else:
            logger.error(
                """
                Wrong optional argument specified.
                Usage: run_simulation <bitstream_file>
                """
            )
            return

        design_file = top_module + ".v"
        top_module_tb = top_module + "_tb"
        test_bench = top_module_tb + ".v"
        vvp_file = top_module_tb + ".vvp"
        bitstream_hex = top_module + ".hex"

        tmp_dir = f"{self.projectDir}/{path}/tmp/"
        os.makedirs(f"{self.projectDir}/{path}/tmp", exist_ok=True)
        copy_verilog_files(f"{self.projectDir}/Tile/", tmp_dir)
        copy_verilog_files(f"{self.projectDir}/Fabric/", tmp_dir)
        file_list = [
            os.path.join(tmp_dir, filename) for filename in os.listdir(tmp_dir)
        ]

        try:
            runCmd = [
                f"os.getenv('FAB_IVERILOG_PATH', 'iverilog')",
                "-D",
                f"{defined_option}",
                "-s",
                f"{top_module_tb}",
                "-o",
                f"{self.projectDir}/{path}/{vvp_file}",
                *file_list,
                f"{self.projectDir}/{path}/{design_file}",
                f"{self.projectDir}/Test/{test_bench}",
            ]
            sp.run(runCmd, check=True)

        except sp.CalledProcessError:
            logger.error("Simulation failed")
            remove_dir(f"{self.projectDir}/{path}/tmp")
            return

        make_hex(
            f"{self.projectDir}/{path}/{bitstream}",
            f"{self.projectDir}/{path}/{bitstream_hex}",
        )

        try:
            runCmd = [
                f"{os.getenv('FAB_VVP_PATH', 'vvp')}",
                f"{self.projectDir}/{path}/{vvp_file}",
            ]
            sp.run(runCmd, check=True)
        except sp.CalledProcessError:
            logger.error("Simulation failed")
            remove_dir(f"{self.projectDir}/{path}/tmp")
            return

        remove_dir(f"{self.projectDir}/{path}/tmp")
        logger.info("Simulation finished")

    def complete_run_simulation(self, text, *ignored):
        return self._complete_path(text)

    def do_run_FABulous_bitstream(self, *args):
        """
        Runs FABulous to generate bitstream on a given design starting from synthesis.

        Does this by calling synthesis, place and route, bitstream generation functions.
        Requires Verilog file specified by <top_module_file>.

        Also logs usage error and file not found error.

        Usage:
            run_FABulous_bitstream <top_module_file>

        """
        if len(args) != 1:
            logger.error("Usage: run_FABulous_bitstream <top_module_file>")
            return

        verilog_file_path = get_path(args[0])
        file_path_no_suffix = verilog_file_path.parent / verilog_file_path.stem

        if verilog_file_path.suffix != ".v":
            logger.error(
                """
                No verilog file provided.
                Usage: run_FABulous_bitstream <top_module_file>
                """
            )
            return

        json_file_path = file_path_no_suffix.with_suffix(".json")
        fasm_file_path = file_path_no_suffix.with_suffix(".fasm")

        self.do_synthesis(str(verilog_file_path))
        self.do_place_and_route(str(json_file_path))
        self.do_gen_bitStream_binary(str(fasm_file_path))

    def complete_run_FABulous_bitstream(self, text, line, *ignored):
        return self._complete_path(text)

    def do_tcl(self, args):
        """Executes TCL script relative to the project directory, specified by
        <tcl_scripts>. Uses the 'tk' module to create TCL commands.

        Also logs usage errors and file not found errors.

        Usage:
            tcl <tcl_scripts>

        Parameters
        ----------
        args : str
            Path to the TCL script.
        """
        args = self.parse(args)
        if len(args) != 1:
            logger.error("Usage: tcl <tcl_script>")
            return
        path_str = args[0]
        path = get_path(path_str)
        name = path.stem
        if not os.path.exists(path_str):
            logger.error(f"Cannot find {path_str}")
            return

        logger.info(f"Execute TCL script {path_str}")
        tcl = tk.Tcl()
        for fun in dir(self.__class__):
            if fun.startswith("do_"):
                name = fun.strip("do_")
                tcl.createcommand(name, getattr(self, fun))

        tcl.evalfile(path_str)
        logger.info("TCL script executed")

    def complete_tcl(self, text, *ignored):
        return self._complete_path(text)


def main():
    """Main function to run command line interface for FABulous,
    sets up argument parsing, initialises required components and handles
    FABulous CLI execution.

    Also logs terminal output and if .FABulous folder is missing.

    Command line arguments
    ----------------------
    Project_dir : str
        Directory path to project folder.
    -c, --createProject :  bool
        Flag to create new project.
    -csv : str, optional
        Log all the output from the terminal.
    -s, --script: str, optional
        Run FABulous with FABulous script.
    -log : str, optional
        Log all the output from the terminal.
    -w, --writer : <'verilog', 'vhdl'>, optional
        Set type of HDL code generated. Currently supports .V and .VHDL (Default .V)
    -md, --metaDataDir : str, optional
        Set output directory for metadata files, e.g. pip.txt, bel.txt
    -v, --verbose : bool, optional
        Show detailed log information including function and line number.
    -gde, --globalDotEnv : str, optional
        Set global .env file path. Default is $FAB_ROOT/.env
    -pde, --projectDotEnv : str, optional
        Set project .env file path. Default is $FAB_PROJ_DIR/.env
    """
    parser = argparse.ArgumentParser(
        description="The command line interface for FABulous"
    )

    parser.add_argument("project_dir", help="The directory to the project folder")

    parser.add_argument(
        "-c",
        "--createProject",
        default=False,
        action="store_true",
        help="Create a new project",
    )

    parser.add_argument(
        "-csv", default="", nargs=1, help="Log all the output from the terminal"
    )

    parser.add_argument(
        "-s", "--script", default="", help="Run FABulous with a FABulous script"
    )

    parser.add_argument(
        "-log",
        default=False,
        nargs="?",
        const="FABulous.log",
        help="Log all the output from the terminal",
    )

    parser.add_argument(
        "-w",
        "--writer",
        default="verilog",
        choices=["verilog", "vhdl"],
        help="Set the type of HDL code generated by the tool. Currently support Verilog and VHDL (Default using Verilog)",
    )

    parser.add_argument(
        "-md",
        "--metaDataDir",
        default=".FABulous",
        nargs=1,
        help="Set the output directory for the meta data files eg. pip.txt, bel.txt",
    )
    parser.add_argument(
        "-v",
        "--verbose",
        default=False,
        action="count",
        help="Show detailed log information including function and line number. For -vv additionally output from "
        "FABulator is logged to the shell for the start_FABulator command",
    )
    parser.add_argument(
        "-gde",
        "--globalDotEnv",
        nargs=1,
        help="Set the global .env file path. Default is $FAB_ROOT/.env",
    )
    parser.add_argument(
        "-pde",
        "--projectDotEnv",
        nargs=1,
        help="Set the project .env file path. Default is $FAB_PROJ_DIR/.env",
    )

    args = parser.parse_args()

    setup_logger(args.verbose)

    setup_global_env_vars(args)

    args.top = os.getenv("FAB_PROJ_DIR").split("/")[-1]

    if args.createProject:
        create_project(os.getenv("FAB_PROJ_DIR"), args.writer)
        exit(0)

    if not os.path.exists(f"{os.getenv('FAB_PROJ_DIR')}/.FABulous"):
        logger.error(
            "The directory provided is not a FABulous project as it does not have a .FABulous folder"
        )
        exit(-1)
    else:
        setup_project_env_vars(args)

        if os.getenv("FAB_PROJ_LANG") == "vhdl":
            writer = VHDLWriter()
        elif os.getenv("FAB_PROJ_LANG") == "verilog":
            writer = VerilogWriter()
        else:
            logger.error(
                f"Invalid projct language specified: {os.getenv('FAB_PROJ_LANG')}"
            )
            raise ValueError(
                f"Invalid projct language specified: {os.getenv('FAB_PROJ_LANG')}"
            )

        fabShell = FABulousShell(
            FABulous(writer, fabricCSV=args.csv), os.getenv("FAB_PROJ_DIR"), args.script
        )
        if args.verbose == 2:
            fabShell.verbose = True

        if args.metaDataDir:
            metaDataDir = args.metaDataDir

        histfile = os.path.expanduser(
            f"{os.getenv('FAB_PROJ_DIR')}/{metaDataDir}/.fabulous_history"
        )
        readline.write_history_file(histfile)

        if args.log:
            with open(args.log, "w") as log:
                with redirect_stdout(log):
                    fabShell.cmdloop()
        else:
            fabShell.cmdloop()


if __name__ == "__main__":
    main()

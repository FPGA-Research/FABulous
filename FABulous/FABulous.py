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
import logging
import os
import pickle
import platform
import re
import readline
import shutil
import subprocess as sp
import sys
import tkinter as tk
import traceback
from contextlib import redirect_stdout
from glob import glob
from pathlib import PurePosixPath, PureWindowsPath
from typing import List, Literal

import docker
import FABulous.fabric_generator.model_generation_npnr as model_gen_npnr
from FABulous.fabric_generator.code_generation_Verilog import VerilogWriter
from FABulous.fabric_generator.code_generation_VHDL import VHDLWriter
from FABulous.fabric_generator.utilities import GetFabric, genFabricObject
from FABulous.FABulous_API import FABulous

readline.set_completer_delims(" \t\n")
histfile = ""
histfile_size = 1000

MAX_BITBYTES = 16384

logger = logging.getLogger(__name__)
logging.basicConfig(
    format="[%(levelname)s]-%(asctime)s - %(message)s", level=logging.INFO
)

metaDataDir = ".FABulous"

fabulousRoot = os.getenv("FAB_ROOT")
if fabulousRoot is None:
    fabulousRoot = os.path.dirname(os.path.realpath(__file__))
    logger.warning("FAB_ROOT environment variable not set!")
    logger.warning(f"Using {fabulousRoot} as FAB_ROOT")
else:
    if not os.path.exists(fabulousRoot):
        logger.error(
            f"FAB_ROOT environment variable set to {fabulousRoot} but the directory does not exist"
        )
        sys.exit()
    else:
        if os.path.exists(f"{fabulousRoot}/FABulous"):
            fabulousRoot = f"{fabulousRoot}/FABulous"

    logger.info(f"FAB_ROOT set to {fabulousRoot}")


# Create a FABulous Verilog project that contains all the required files
def create_project(project_dir, type: Literal["verilog", "vhdl"] = "verilog"):
    if os.path.exists(project_dir):
        print("Project directory already exists!")
        sys.exit()
    else:
        os.mkdir(f"{project_dir}")

    os.mkdir(f"{project_dir}/.FABulous")

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

    adjust_directory_in_verilog_tb(project_dir)


def copy_verilog_files(src, dst):
    for root, _, files in os.walk(src):
        for file in files:
            if file.endswith(".v"):
                source_path = os.path.join(root, file)
                destination_path = os.path.join(dst, file)
                shutil.copy(source_path, destination_path)


def remove_dir(path):
    try:
        shutil.rmtree(path)
        pass
    except OSError as e:
        logger.error(f"{e}")


def make_hex(binfile, outfile):
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
    with open(
        f"{fabulousRoot}/fabric_files/FABulous_project_template_verilog/Test/sequential_16bit_en_tb.v",
        "rt",
    ) as fin:
        with open(f"{project_dir}/Test/sequential_16bit_en_tb.v", "wt") as fout:
            for line in fin:
                fout.write(line.replace("PROJECT_DIR", f"{project_dir}"))


def get_path(path):
    system = platform.system()
    # Darwin corresponds to MacOS, which also uses POSIX-style paths
    if system == "Linux" or system == "Darwin":
        return PurePosixPath(path)
    elif system == "Windows":
        return PureWindowsPath(path)
    else:
        raise NotImplementedError(f"Unsupported operating system: {system}")


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
    run_FABulous_bitstream npnr ./user_design/sequential_16bit_en.v
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
        super().__init__()
        self.fabricGen = fab
        self.projectDir = projectDir
        self.tiles = []
        self.superTiles = []
        self.csvFile = ""
        self.script = script
        if isinstance(self.fabricGen.writer, VHDLWriter):
            self.extension = "vhdl"
        else:
            self.extension = "v"

        if hasattr(fab, "fabric"):
            self.fabricLoaded = True

    def preloop(self) -> None:

        # File does not exist when the shell is started the first time after creating a new project
        if os.path.exists(histfile):
            readline.read_history_file(histfile)

        def wrap_with_except_handling(fun_to_wrap):
            def inter(*args, **varargs):
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

        # os.chdir(args.project_dir)
        tcl.eval(script)

        if "exit" in script:
            exit(0)

    def postloop(self):
        readline.set_history_length(histfile_size)
        readline.write_history_file(histfile)

    def precmd(self, line: str) -> str:
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

    # override the emptyline method, so empty command will just do nothing
    def emptyline(self):
        pass

    def parse(self, line: str) -> List[str]:
        return line.split()

    def _complete_path(self, path):
        if os.path.isdir(path):
            return glob(os.path.join(path, "*"))
        else:
            return glob(path + "*")

    def _complete_tileName(self, text):
        return [t for t in self.allTile if t.startswith(text)]

    def do_shell(self, args):
        "Run a shell command"
        if not args:
            print("Please provide a command to run")
            return

        try:
            sp.run(args, shell=True)
        except sp.CalledProcessError:
            logger.error("Could not execute the requested command.")
            return

    def do_exit(self, *ignore):
        "exit FABulous shell"
        logger.info("Exiting FABulous shell")
        return True

    def do_load_fabric(self, args=""):
        "load csv file and generate an internal representation of the fabric"
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

    # TODO REMOVE once have transition the model gen to object based
    def do_set_fabric_csv(self, args):
        "set the csv file to be used for fabric generation"
        args = self.parse(args)
        self.csvFile = args[0]

    def complete_set_fabric_csv(self, text, *ignored):
        return self._complete_path(text)

    def do_gen_config_mem(self, args):
        "Generate the configuration memory of the given tile"
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
        logger.info(f"Generating configMem complete")

    def complete_gen_config_mem(self, text, *ignored):
        return self._complete_tileName(text)

    def do_gen_switch_matrix(self, args):
        "Generate switch matrix of the given tile"
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
        "Generate the given tile with the switch matrix and configuration memory"
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
        "Generate all tiles"
        logger.info("Generating all tiles")
        self.do_gen_tile(self.allTile)
        logger.info("Generated all tiles")

    def do_gen_fabric(self, *ignored):
        "Generate the fabric base on the loaded fabric"
        logger.info(f"Generating fabric {self.fabricGen.fabric.name}")
        self.do_gen_all_tile()
        self.fabricGen.setWriterOutputFile(
            f"{self.projectDir}/Fabric/{self.fabricGen.fabric.name}.{self.extension}"
        )
        self.fabricGen.genFabric()
        logger.info("Fabric generation complete")

    def do_gen_geometry(self, *vargs):
        "Generate the geometry of the fabric for the FABulous Editor.    Usage: gen_geometry [padding]"

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
            logger.info(f"{geomFile} can now be imported into the FABulous Editor")
        else:
            logger.error("padding has to be between 4 and 32 inclusively!")

    def do_gen_bitStream_spec(self, *ignored):
        "Generate the bitstream specification of the fabric"
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
        "Generate the top wrapper of the fabric"
        logger.info("Generating top wrapper")
        self.fabricGen.setWriterOutputFile(
            f"{self.projectDir}/Fabric/{self.fabricGen.fabric.name}_top.{self.extension}"
        )
        self.fabricGen.genTopWrapper()
        logger.info("Generated top wrapper")

    def do_run_FABulous_fabric(self, *ignored):
        "Generate the fabric base on the CSV file, create the bitstream specification of the fabric, top wrapper of the fabric, Nextpnr model of the fabric and geometry information of the fabric."
        logger.info("Running FABulous")
        self.do_gen_fabric()
        self.do_gen_bitStream_spec()
        self.do_gen_top_wrapper()
        self.do_gen_model_npnr()
        self.do_gen_geometry()
        logger.info("FABulous fabric flow complete")
        return 0

    def do_gen_model_npnr(self, *ignored):
        "Generate a npnr model of the fabric"
        logger.info("Generating npnr model")
        npnrModel = self.fabricGen.genModelNpnr()
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

    # TODO updater once have transition the model gen to object based
    def do_gen_model_npnr_pair(self):
        "Generate a pair npnr model of the fabric. (Currently not working)"
        logger.info("Generating pair npnr model")
        if self.csvFile:
            FabricFile = [i.strip("\n").split(",") for i in open(self.csvFile)]
            fabric = GetFabric(FabricFile)
            fabricObject = genFabricObject(fabric, FabricFile)
            pipFile = open(f"{self.projectDir}/{metaDataDir}/pips.txt", "w")
            belFile = open(f"{self.projectDir}/{metaDataDir}/bel.txt", "w")
            pairFile = open(f"{self.projectDir}/{metaDataDir}/wirePairs.csv", "w")
            constraintFile = open(f"{self.projectDir}/{metaDataDir}/template.pcf", "w")

            npnrModel = model_gen_npnr.genNextpnrModelOld(fabricObject, False)

            pipFile.write(npnrModel[0])
            belFile.write(npnrModel[1])
            constraintFile.write(npnrModel[2])
            pairFile.write(npnrModel[3])

            pipFile.close()
            belFile.close()
            constraintFile.close()
            pairFile.close()

        else:
            print("Need to call sec_fabric_csv before running model_gen_npnr_pair")
        logger.info("Generated pair npnr model")

    def do_gen_model_vpr(self, args):
        "Generate a vpr model of the fabric"
        args = self.parse(args)
        if len(args) > 1:
            logger.error(f"Usage: gen_model_vpr [path_to_custom_xml]")
            return

        if len(args) == 0:
            args = ""
        else:
            args = args[0]

        logger.info("Generating vpr model")
        vprModel = self.fabricGen.genModelVPR(args)
        logger.info(f"Output file: {self.projectDir}/{metaDataDir}/architecture.xml")
        with open(f"{self.projectDir}/{metaDataDir}/architecture.xml", "w") as f:
            f.write(vprModel)

        routingResourceInfo = self.fabricGen.genModelVPRRoutingResource()
        # Write the routing resource graph
        vprRoutingResource = routingResourceInfo[0]
        logger.info(
            f"Output file: {self.projectDir}/{metaDataDir}/routing_resource.xml"
        )
        with open(f"{self.projectDir}/{metaDataDir}/routing_resource.xml", "w") as f:
            f.write(vprRoutingResource)

        # Write maxWidth.txt
        vprMaxWidth = routingResourceInfo[1]
        logger.info(f"Output file: {self.projectDir}/{metaDataDir}/maxWidth.txt")
        with open(f"{self.projectDir}/{metaDataDir}/maxWidth.txt", "w") as f:
            f.write(str(vprMaxWidth))

        vprConstrain = self.fabricGen.genModelVPRConstrains()
        logger.info(f"Output file: {self.projectDir}/{metaDataDir}/fab_constraints.xml")
        with open(f"{self.projectDir}/{metaDataDir}/fab_constraints.xml", "w") as f:
            f.write(vprConstrain)

        logger.info("Generated vpr model")

    def complete_gen_model_vpr(self, text, *ignored):
        return self._complete_path(text)

    def do_hls_create_project(self):
        if not os.path.exists(f"./HLS"):
            os.makedirs(f"./HLS")

        with open(f"{self.projectDir}/HLS/config.tcl", "w") as f:
            f.write(f"source /root/legup-4.0/examples/legup.tcl\n")

        name = get_path(self.projectDir).name
        with open(f"{self.projectDir}/HLS/Makefile", "w") as f:
            f.write(f"NAME = {name}\n")
            f.write(f"LOCAL_CONFIG = -legup-config=/root/{name}/config.tcl\n")
            f.write("LEVEL = /root/legup-4.0/examples\n")
            f.write("include /root/legup-4.0/examples/Makefile.common\n")
            f.write("include /root/legup-4.0/examples/Makefile.ancillary\n")
            f.write(f"OUTPUT_PATH=/root/{name}/generated_file\n")

        with open(f"./HLS/{name}.c", "w") as f:
            f.write(
                '#include <stdio.h>\nint main() {\n    printf("Hello World");\n    return 0;\n}'
            )

        os.chmod(f"./HLS/config.tcl", 0o666)
        os.chmod(f"./HLS/Makefile", 0o666)
        os.chmod(f"./HLS/{name}.c", 0o666)

    def do_hls_generate_verilog(self):
        name = get_path(self.projectDir).name
        # create folder for the generated file
        if not os.path.exists(f"./HLS/generated_file"):
            os.mkdir(f"{name}/generated_file")
        else:
            os.system(f"rm -rf ./create_HLS_project/generated_file/*")

        client = docker.from_env()
        containers = client.containers.run(
            "legup:latest",
            f"make -C /root/{name} ",
            volumes=[
                f"{os.path.abspath(os.getcwd())}/{self.projectDir}/HLS/:/root/{name}"
            ],
        )

        print(containers.decode("utf-8"))

        # move all the generated files into a folder
        for f in os.listdir(f"./HLS"):
            if (
                not f.endswith(".v")
                and not f.endswith(".c")
                and not f.endswith(".h")
                and not f.endswith("_labeled.c")
                and not f.endswith(".tcl")
                and f != "Makefile"
                and os.path.isfile(f"./HLS/{f}")
            ):
                shutil.move(f"./HLS/{f}", f"./HLS/generated_file/")

            if f.endswith("_labeled.c"):
                shutil.move(f"./HLS/{f}", f"./HLS/generated_file/")

        try:
            os.chmod(f"./HLS/{name}.v", 0o666)
            with open(f"./HLS/{name}.v", "r") as f:
                content = f.read()
                content = re.sub(r"(if .*? \$finish; end)", r"//\1", content)
                content = re.sub(r"(@\(.*?\);)", r"//\1", content)
                content = re.sub(r"(\$write.*?;)", r"//\1", content)
                content = re.sub(r"(\$display.*?;)", r"//\1", content)
                content = re.sub(r"(\$finish;)", r"//\1", content)
                with open(f"./HLS/{name}.v", "w") as f:
                    f.write(content)
            s = (
                f"module {name}(\n"
                "    reset,\n"
                "    start,\n"
                "    finish,\n"
                "    waitrequest,\n"
                "    return_val\n"
                ");\n"
                "input reset;\n"
                "input start;\n"
                "output wire finish;\n"
                "input waitrequest;\n"
                "output wire[31:0] return_val;\n"
                "wire clk;\n"
                "(* keep *) Global_Clock inst_clk (.CLK(clk));\n"
                "(* keep *) top inst_top(.clk(clk), .reset(reset), .start(start),\n"
                "    .finish(finish), .waitrequest(waitrequest), .return_val(return_val));\n"
                "\n"
                "endmodule\n"
            )
            with open(f"./HLS/{name}.v", "a") as f:
                f.write("\n")
                f.write(s)
        except:
            print(
                "Verilog file is not generated, potentialy due to the error in the C code"
            )
            exit(-1)

    def do_synthesis_npnr(self, args):
        "Run synthesis with Yosys using Nextpnr JSON backend Usage: synthesis_npnr <top_module_file>"
        args = self.parse(args)
        if len(args) != 1:
            logger.error("Usage: synthesis_npnr <top_module_file>")
            raise TypeError(
                f"do_place_and_route_npnr takes exactly one argument ({len(args)} given)"
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
                Usage: synthesis_npnr <top_module_file>
                """
            )
            return

        json_file = top_module_name + ".json"
        runCmd = [
            "yosys",
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

    def complete_synthesis_npnr(self, text, *ignored):
        return self._complete_path(text)

    def do_synthesis_blif(self, args):
        "Run synthesis with Yosys using VPR BLIF backend Usage: synthesis_blif <top_module_file>"
        args = self.parse(args)
        if len(args) != 1:
            logger.error("Usage: synthesis_blif <top_module_file>")
            raise TypeError(
                f"do_place_and_route_npnr takes exactly one argument ({len(args)} given)"
            )
        logger.info(f"Running synthesis that targeting BLIF with design {args[0]}")

        path = get_path(args[0])
        parent = path.parent
        verilog_file = path.name
        top_module_name = path.stem
        if path.suffix != ".v":
            logger.error(
                """
                No verilog file provided.
                Usage: synthesis_blif <top_module_file>
                """
            )
            return

        blif_file = top_module_name + ".blif"
        runCmd = [
            "yosys",
            "-p",
            f"synth_fabulous -top top_wrapper -blif {self.projectDir}/{parent}/{blif_file} -vpr",
            f"{self.projectDir}/{parent}/{verilog_file}",
            f"{self.projectDir}/{parent}/top_wrapper.v",
        ]
        try:
            sp.run(runCmd, check=True)
            logger.info("Synthesis completed.")
        except sp.CalledProcessError:
            logger.error("Synthesis failed.")
            raise SynthesisError

    def complete_synthesis_blif(self, text, *ignored):
        return self._complete_path(text)

    def do_place_and_route_npnr(self, args):
        """
        Run place and route with Nextpnr. Need to generate a Nextpnr model first.
        Usage: place_and_route_npnr <json_file>
        <json_file> is generated by Yosys. Generate it by running synthesis_npnr
        """
        args = self.parse(args)
        if len(args) != 1:
            logger.error(
                "Usage: place_and_route_npnr <json_file> (<json_file> is generated by Yosys. Generate it by running synthesis_npnr.)"
            )
            raise TypeError(
                f"do_place_and_route_npnr takes exactly one argument ({len(args)} given)"
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
                Usage: place_and_route_npnr <json_file> (<json_file> is generated by Yosys. Generate it by running synthesis_npnr.)
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
                    f"nextpnr-generic",
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
                    logger.error(f"Placement and Routing failed.")
                    raise PlaceAndRouteError

            else:
                logger.error(
                    f'Cannot find file "{json_file}" in path "./{parent}/", which is generated by running Yosys with Nextpnr backend (e.g. synthesis_npnr).'
                )
                raise FileNotFoundError

            logger.info("Placement and Routing completed")
        else:
            logger.error(f"Directory {self.projectDir}/{parent} does not exist.")
            raise FileNotFoundError

    def complete_place_and_route_npnr(self, text, *ignored):
        return self._complete_path(text)

    def do_place_and_route_vpr(self, args):
        "Run place and route with VPR. Need to generate a VPR model first. Usage: place_and_route_vpr <blif_file> (Currently not working)"
        args = self.parse(args)
        if len(args) != 1:
            logger.error("Usage: place_and_route_vpr <blif_file>")
            raise TypeError(
                f"do_place_and_route_npnr takes exactly one argument ({len(args)} given)"
            )
        logger.info(f"Running Placement and Routing with vpr for design {args[0]}")
        path = get_path(args[0])
        blif_file = path.name

        if os.path.exists(f"{self.projectDir}/user_design/{blif_file}"):
            if not os.getenv("VTR_ROOT"):
                logger.error(
                    "VTR_ROOT is not set, please set it to the VPR installation directory"
                )
                exit(-1)

            vtr_root = os.getenv("VTR_ROOT")

            runCmd = [
                f"{vtr_root}/vpr/vpr",
                f"{self.projectDir}/.FABulous/architecture.xml",
                f"{self.projectDir}/user_design/{blif_file}",
                "--read_rr_graph",
                f".FABulous/routing_resources.xml",
                "--echo_file",
                "on",
                "--route_chan_width",
                "16",
            ]
            try:
                sp.run(runCmd, check=True)
            except sp.CalledProcessError:
                logger.error("Placement and Routing failed.")
                raise PlaceAndRouteError
        else:
            logger.error(
                f"Cannot find {blif_file}, which is generated by running Yosys with blif backend"
            )
            raise FileNotFoundError
        logger.info("Placement and Routing completed")

    def complete_place_and_route_vpr(self, text, *ignored):
        return self._complete_path(text)

    def do_gen_bitStream_binary(self, args):
        "Generate the bitstream of a given design. Need to generate bitstream specification before use. Usage: gen_bitStream_binary <fasm_file>"
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
                f"Cannot find {self.projectDir}/{parent}/{fasm_file} file which is generated by running place_and_route_npnr or place_and_route_vpr. Potentially Place and Route Failed."
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
        """
        Simulate the given design. Need to generate the bitstream before use.
        Usage: run_simulation [<fst|vcd>] <bitstream_file>
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
                "iverilog",
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
            if optional_arg  == "fst":
                runCmd = ["vvp", f"{self.projectDir}/{path}/{vvp_file}", "-fst"]
            else:
                runCmd = ["vvp", f"{self.projectDir}/{path}/{vvp_file}"]
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
        "Run FABulous to generate a bitstream on a given design starting from synthesis. Usage: run_FABulous_bitstream <npnr|vpr> <top_module_file> (vpr flow currently not working)"
        if len(args) == 1:
            args = self.parse(args[0])
            if len(args) != 2:
                logger.error(
                    "Usage: run_FABulous_bitstream <npnr|vpr> <top_module_file>"
                )
                return
        elif len(args) != 2:
            logger.error("Usage: run_FABulous_bitstream <npnr|vpr> <top_module_file>")
            return

        verilog_file_path = get_path(args[1])
        file_path_no_suffix = verilog_file_path.parent / verilog_file_path.stem

        if verilog_file_path.suffix != ".v":
            logger.error(
                """
                No verilog file provided.
                Usage: run_FABulous_bitstream <npnr|vpr> <top_module_file>
                """
            )
            return

        json_file_path = file_path_no_suffix.with_suffix(".json")
        blif_file_path = file_path_no_suffix.with_suffix(".blif")
        fasm_file_path = file_path_no_suffix.with_suffix(".fasm")

        if args[0] == "vpr":
            self.do_synthesis_blif(str(verilog_file_path))
            self.do_place_and_route_vpr(str(blif_file_path))
            self.do_gen_bitStream_binary(str(fasm_file_path))
        elif args[0] == "npnr":
            self.do_synthesis_npnr(str(verilog_file_path))
            self.do_place_and_route_npnr(str(json_file_path))
            self.do_gen_bitStream_binary(str(fasm_file_path))
        else:
            logger.error("Usage: run_FABulous_bitstream <npnr|vpr> <top_module_file>")
            return

        return 0

    def complete_run_FABulous_bitstream(self, text, line, *ignored):
        value = ["npnr", "vpr"]
        if "npnr" not in line and "vpr" not in line:
            return [i for i in value if i.startswith(text)]
        return self._complete_path(text)

    def do_tcl(self, args):
        """Execute a TCL script. The directory in the script is relative to the project directory."""
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
    if sys.version_info < (3, 9, 0):
        print("Need Python 3.9 or above to run FABulous")
        exit(-1)
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

    args = parser.parse_args()

    args.top = args.project_dir.split("/")[-1]

    if args.createProject:
        create_project(args.project_dir, args.writer)
        exit(0)

    if not os.path.exists(f"{args.project_dir}/.FABulous"):
        print(
            "The directory provided is not a FABulous project as it does not have a .FABulous folder"
        )
        exit(-1)
    else:
        writer = VerilogWriter()
        if args.writer == "vhdl":
            writer = VHDLWriter()
        if args.writer == "verilog":
            writer = VerilogWriter()

        fabShell = FABulousShell(
            FABulous(writer, fabricCSV=args.csv), args.project_dir, args.script
        )

        if args.metaDataDir:
            metaDataDir = args.metaDataDir

        histfile = os.path.expanduser(
            f"{args.project_dir}/{metaDataDir}/.fabulous_history"
        )

        if args.log:
            with open(args.log, "w") as log:
                with redirect_stdout(log):
                    fabShell.cmdloop()
        else:
            fabShell.cmdloop()


if __name__ == "__main__":
    main()

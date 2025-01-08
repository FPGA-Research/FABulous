import argparse
import os
from contextlib import redirect_stdout
from pathlib import Path

from loguru import logger

from FABulous.fabric_generator.code_generation_Verilog import VerilogWriter
from FABulous.fabric_generator.code_generation_VHDL import VHDLWriter
from FABulous.FABulous_API import FABulous_API
from FABulous.FABulous_CLI.FABulous_CLI import INTO_STRING, FABulous_CLI
from FABulous.FABulous_CLI.helper import (
    create_project,
    setup_global_env_vars,
    setup_logger,
    setup_project_env_vars,
)


def main():
    """Main function to start the command line interface of FABulous,
    sets up argument parsing, initialises required components and handles
    start the FABulous CLI.

    Also logs terminal output and if .FABulous folder is missing.

    Command line arguments
    ----------------------
    Project_dir : str
        Directory path to project folder.
    -c, --createProject :  bool
        Flag to create new project.
    -fs, --FABulousScript: str, optional
        Run FABulous with a FABulous script.
    -ts, --TCLscript: str, optional
        Run FABulous with a TCL script.
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
        "-fs",
        "--FABulousScript",
        default="",
        help="Run FABulous with a FABulous script. A FABulous script is a text file containing only FABulous commands"
        "This will automatically exit the CLI once the command finish execution, and the exit will always happen gracefully.",
        type=Path,
    )
    parser.add_argument(
        "-ts",
        "--TCLScript",
        default="",
        help="Run FABulous with a TCL script. A TCL script is a text file containing a mix of TCL commands and FABulous commands."
        "This will automatically exit the CLI once the command finish execution, and the exit will always happen gracefully.",
        type=Path,
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

    parser.add_argument("--debug", action="store_true", help="Enable debug mode")

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
            logger.debug("VHDL writer selected")
        elif os.getenv("FAB_PROJ_LANG") == "verilog":
            writer = VerilogWriter()
            logger.debug("Verilog writer selected")
        else:
            logger.error(
                f"Invalid projct language specified: {os.getenv('FAB_PROJ_LANG')}"
            )
            raise ValueError(
                f"Invalid projct language specified: {os.getenv('FAB_PROJ_LANG')}"
            )

        fabShell = FABulous_CLI(
            FABulous_API(writer),
            Path(os.getenv("FAB_PROJ_DIR")),
            FABulousScript=args.FABulousScript,
            TCLScript=args.TCLScript,
        )
        fabShell.debug = args.debug
        if args.verbose == 2:
            fabShell.verbose = True
        if args.metaDataDir:
            metaDataDir = args.metaDataDir

        if args.log:
            with open(args.log, "w") as log:
                with redirect_stdout(log):
                    fabShell.cmdloop()
        else:
            fabShell.cmdloop(INTO_STRING)


if __name__ == "__main__":
    main()

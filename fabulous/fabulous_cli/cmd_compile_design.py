"""Compile design command implementation for the FABulous CLI.

This module provides a unified compile flow (synthesis -> PnR -> bitgen) for the
FABulous command-line interface. It delegates execution to a compile Taskfile, passing
all necessary variables for Yosys synthesis, nextpnr place-and-route, and bitstream
generation.
"""

import argparse
import subprocess
from pathlib import Path
from typing import TYPE_CHECKING

from cmd2 import Cmd, Cmd2ArgumentParser, with_argparser, with_category
from loguru import logger

from fabulous.fabulous_cli.helper import run_task
from fabulous.fabulous_settings import get_context

if TYPE_CHECKING:
    from fabulous.fabulous_cli.fabulous_cli import FABulous_CLI

CMD_USER_DESIGN_FLOW = "User Design Flow"

compile_design_parser = Cmd2ArgumentParser(
    description="Compile a user design through the full flow: synthesis, "
    "place-and-route, and bitstream generation. "
    "Commonly used synth_fabulous flags (pass via --synth-extra-args): "
    "-nofsm, -noflatten, -extra-plib <file>. "
    "Run with --yosys-synth-help or --nextpnr-help for full tool documentation."
)
compile_design_parser.add_argument(
    "files",
    type=Path,
    help="Path to the target files.",
    completer=Cmd.path_complete,
    nargs="+",
)
compile_design_parser.add_argument(
    "-top",
    type=str,
    help="Use the specified module as the top module (default='top_wrapper').",
    default="top_wrapper",
)
compile_design_parser.add_argument(
    "-json",
    type=Path,
    help="Write the design to the specified JSON file. "
    "If not specified, defaults to <first_file_stem>.json.",
    completer=Cmd.path_complete,
)

# Compile flow control — each --*-only flag runs exactly that step.
# Without any flag the full flow (synth + PnR + bitgen) is executed.
compile_design_parser.add_argument(
    "--synth-only",
    help="Only run synthesis.",
    action="store_true",
)
compile_design_parser.add_argument(
    "--pnr-only",
    help="Only run place-and-route (JSON must already exist).",
    action="store_true",
)
compile_design_parser.add_argument(
    "--bitgen-only",
    help="Only run bitstream generation (FASM must already exist).",
    action="store_true",
)

# Extra arguments passed directly to the tools
compile_design_parser.add_argument(
    "--synth-extra-args",
    type=str,
    default="",
    help="Extra arguments appended to the synth_fabulous command "
    "(e.g. '-nofsm -extra-plib prims.v').",
)
compile_design_parser.add_argument(
    "--yosys-extra-args",
    type=str,
    default="",
    help="Extra arguments passed to the Yosys CLI itself (before the -p flag).",
)
compile_design_parser.add_argument(
    "--nextpnr-extra-args",
    type=str,
    default="",
    help="Extra arguments passed to the nextpnr CLI.",
)

# Tool help flags
compile_design_parser.add_argument(
    "--yosys-synth-help",
    help="Print the full synth_fabulous help from Yosys and exit.",
    action="store_true",
)
compile_design_parser.add_argument(
    "--nextpnr-help",
    help="Print the full nextpnr help and exit.",
    action="store_true",
)


def _print_tool_help(tool_path: Path | str, args: list[str], tool_name: str) -> None:
    """Run a tool with the given arguments to print its help output.

    Parameters
    ----------
    tool_path : Path | str
        Path to the tool binary.
    args : list[str]
        Arguments to pass to the tool (e.g. ["-p", "help synth_fabulous"]).
    tool_name : str
        Human-readable tool name for error messages.
    """
    try:
        subprocess.run(
            [str(tool_path), *args],
            check=False,
        )
    except FileNotFoundError:
        logger.error(
            f"{tool_name} not found at '{tool_path}'. "
            "Ensure it is installed and on PATH."
        )


@with_category(CMD_USER_DESIGN_FLOW)
@with_argparser(compile_design_parser)
def do_compile_design(self: "FABulous_CLI", args: argparse.Namespace) -> None:
    """Compile a user design through synthesis, PnR, and bitstream generation.

    This function orchestrates the full compile flow by delegating to a compile
    Taskfile. It resolves input file paths, builds the synthesis command, and invokes
    the appropriate task(s) depending on the selected mode (full compile, synth-only,
    pnr-only, or no-bitgen).
    """
    # Handle help flags
    if args.yosys_synth_help:
        ctx = get_context()
        _print_tool_help(ctx.yosys_path, ["-p", "help synth_fabulous"], "Yosys")
        return
    if args.nextpnr_help:
        ctx = get_context()
        _print_tool_help(ctx.nextpnr_path, ["--help"], "nextpnr")
        return

    logger.info(f"Compiling design with files {[str(i) for i in args.files]}")

    # Resolve file paths
    p: Path
    paths: list[Path] = []
    for p in args.files:
        if not p.is_absolute():
            p = self.projectDir / p
        resolvePath: Path = p.absolute()
        if resolvePath.exists():
            paths.append(resolvePath)
        else:
            logger.error(f"{resolvePath} does not exist")
            return

    # Determine output file paths — must be absolute because the task
    # runs with cwd=.FABulous/, so relative paths would resolve wrong.
    json_file = args.json or paths[0].with_suffix(".json")
    if not json_file.is_absolute():
        json_file = (self.projectDir / json_file).resolve()
    fasm_file = json_file.with_suffix(".fasm")
    log_file = json_file.parent / (json_file.with_suffix("").name + "_npnr_log.txt")

    # Build synth command (skip in pnr-only mode where it's unused)
    synth_cmd = ""
    if not args.pnr_only:
        synth_parts = [
            "synth_fabulous",
            f"-top {args.top}",
            f"-json {args.json}" if args.json else f"-json {json_file}",
        ]

        # Auto-include custom primitives library if present
        custom_prims = self.projectDir / "user_design" / "custom_prims.v"
        if custom_prims.exists():
            synth_parts.append(f"-extra-plib {custom_prims}")
            logger.info(f"Including custom primitives: {custom_prims}")

        if args.synth_extra_args:
            synth_parts.append(args.synth_extra_args)

        synth_cmd = " ".join(synth_parts)

    # Check that compile Taskfile exists
    task_dir = self.projectDir / ".FABulous"
    tf_name = "compile.Taskfile.yml"
    compile_taskfile = task_dir / tf_name
    if not compile_taskfile.exists():
        raise FileNotFoundError(
            f"Compile Taskfile not found at {compile_taskfile}. "
            "Please ensure the project is set up correctly."
        )

    # Build task variables
    ctx = get_context()
    task_vars: dict[str, str] = {
        "YOSYS_PATH": str(ctx.yosys_path),
        "NEXTPNR_PATH": str(ctx.nextpnr_path),
        "FAB_PROJ_ROOT": str(self.projectDir),
        "SYNTH_CMD": synth_cmd,
        "DESIGN_FILES": " ".join(str(p) for p in paths),
        "TOP_WRAPPER_FILE": str(self.projectDir / "user_design" / "top_wrapper.v"),
        "JSON_FILE": str(json_file),
        "FASM_FILE": str(fasm_file),
        "LOG_FILE": str(log_file),
        "YOSYS_EXTRA_ARGS": args.yosys_extra_args,
        "NEXTPNR_EXTRA_ARGS": args.nextpnr_extra_args,
        "NEXTPNR_VERBOSE": "--verbose" if (self.verbose or self.debug) else "",
    }

    # Determine which task(s) to run
    if args.synth_only:
        run_task("compile-yosys", task_dir, task_vars, taskfile=tf_name)
    elif args.pnr_only:
        run_task("compile-nextpnr", task_dir, task_vars, taskfile=tf_name)
    elif args.bitgen_only:
        run_task("compile-bitgen", task_dir, task_vars, taskfile=tf_name)
    else:
        run_task("compile-design", task_dir, task_vars, taskfile=tf_name)

    logger.info("Compile flow completed successfully.")

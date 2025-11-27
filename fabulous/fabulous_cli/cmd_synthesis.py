"""Synthesis command implementation for the FABulous CLI.

This module provides the synthesis command functionality for the FABulous command-line
interface. It implements Yosys-based FPGA synthesis targeting the nextpnr place-and-
route tool, with support for various synthesis options and output formats.

The synthesis flow includes multiple stages, from reading the Verilog files through
final netlist generation, with options for LUT mapping, FSM optimization, carry chain
mapping, and memory inference.
"""

import argparse
import subprocess as sp
from pathlib import Path
from typing import TYPE_CHECKING

from cmd2 import Cmd, Cmd2ArgumentParser, with_argparser, with_category
from loguru import logger

from FABulous.custom_exception import CommandError
from FABulous.FABulous_settings import get_context

if TYPE_CHECKING:
    from FABulous.FABulous_CLI.FABulous_CLI import FABulous_CLI

CMD_USER_DESIGN_FLOW = "User Design Flow"
HELP = """
Runs Yosys using the Nextpnr JSON backend to synthesise the Verilog design
specified by <files> and generates a Nextpnr-compatible JSON file for the
further place and route process. By default the name of the JSON file generated
will be <first_file_provided_stem>.json.

Also logs usage errors or synthesis failures.

The following commands are executed by when executing the synthesis command:
    read_verilog <"projectDir"/user_design/top_wrapper.v>
    read_verilog <file>                 (for each file in files)
    read_verilog  -lib +/fabulous/prims.v
    read_verilog -lib <extra_plib.v>    (for each -extra-plib)

    begin:
        hierarchy -check
        proc

    flatten:    (unless -noflatten)
        flatten
        tribuf -logic
        deminout

    coarse:
        tribuf -logic
        deminout
        opt_expr
        opt_clean
        check
        opt -nodffe -nosdff
        fsm          (unless -nofsm)
        opt
        wreduce
        peepopt
        opt_clean
        techmap -map +/cmp2lut.v -map +/cmp2lcu.v     (if -lut)
        alumacc      (unless -noalumacc)
        share        (unless -noshare)
        opt
        memory -nomap
        opt_clean

    map_ram:    (unless -noregfile)
        memory_libmap -lib +/fabulous/ram_regfile.txt
        techmap -map +/fabulous/regfile_map.v

    map_ffram:
        opt -fast -mux_undef -undriven -fine
        memory_map
        opt -undriven -fine

    map_gates:
        opt -full
        techmap -map +/techmap.v -map +/fabulous/arith_map.v -D ARITH_<carry>
        opt -fast

    map_iopad:    (if -iopad)
        opt -full
        iopadmap -bits -outpad $__FABULOUS_OBUF I:PAD -inpad $__FABULOUS_IBUF O:PAD
            -toutpad IO_1_bidirectional_frame_config_pass ~T:I:PAD
            -tinoutpad IO_1_bidirectional_frame_config_pass ~T:O:I:PAD A:top
            (skip if '-noiopad')
        techmap -map +/fabulous/io_map.v

    map_ffs:
        dfflegalize -cell $_DFF_P_ 0 -cell $_DLATCH_?_ x    without -complex-dff
        techmap -map +/fabulous/latches_map.v
        techmap -map +/fabulous/ff_map.v
        techmap -map <extra_map.v>...    (for each -extra-map)
        clean

    map_luts:
        abc -lut 4 -dress
        clean

    map_cells:
        techmap -D LUT_K=4 -map +/fabulous/cells_map.v
        clean

    check:
        hierarchy -check
        stat

    blif:
        opt_clean -purge
        write_blif -attr -cname -conn -param <file-name>

    json:
        write_json <file-name>
"""

synthesis_parser = Cmd2ArgumentParser(description=HELP)
synthesis_parser.add_argument(
    "files",
    type=Path,
    help="Path to the target files.",
    completer=Cmd.path_complete,
    nargs="+",
)
synthesis_parser.add_argument(
    "-top",
    type=str,
    help="Use the specified module as the top module (default='top_wrapper').",
    default="top_wrapper",
)
synthesis_parser.add_argument(
    "-auto-top",
    help="Automatically determine the top of the design hierarchy.",
    action="store_true",
)
synthesis_parser.add_argument(
    "-blif",
    type=Path,
    help="Write the design to the specified BLIF file. "
    "Writing of an output file is omitted if this parameter is not specified.",
    completer=Cmd.path_complete,
)
synthesis_parser.add_argument(
    "-edif",
    type=Path,
    help="Write the design to the specified EDIF file. "
    "Writing of an output file is omitted if this parameter is not specified.",
    completer=Cmd.path_complete,
)
synthesis_parser.add_argument(
    "-json",
    type=Path,
    help="Write the design to the specified JSON file. "
    "If this parameter is not specified it will default to <first_file_stem>.json",
    completer=Cmd.path_complete,
)
synthesis_parser.add_argument(
    "-lut",
    type=str,
    default="4",
    help="Perform synthesis for a k-LUT architecture (default 4).",
)
synthesis_parser.add_argument(
    "-plib",
    type=str,
    help="Use the specified Verilog file as a primitive library.",
    completer=Cmd.path_complete,
)
synthesis_parser.add_argument(
    "-extra-plib",
    type=Path,
    help="Use the specified Verilog file for extra primitives "
    "(can be specified multiple times).",
    action="append",
    completer=Cmd.path_complete,
)
synthesis_parser.add_argument(
    "-extra-map",
    type=Path,
    help="Use the specified Verilog file for extra techmap rules "
    "(can be specified multiple times).",
    action="append",
    completer=Cmd.path_complete,
)
synthesis_parser.add_argument(
    "-encfile",
    type=Path,
    help="Passed to 'fsm_recode' via 'fsm'.",
    completer=Cmd.path_complete,
)
synthesis_parser.add_argument(
    "-nofsm",
    help="Do not run FSM optimization.",
    action="store_true",
)
synthesis_parser.add_argument(
    "-noalumacc",
    help="Do not run 'alumacc' pass. I.e., keep arithmetic operators in "
    "their direct form ($add, $sub, etc.).",
    action="store_true",
)
synthesis_parser.add_argument(
    "-carry",
    type=str,
    required=False,
    choices=["none", "ha"],
    default="none",
    help="Carry mapping style (none, half-adders, ...) default=none.",
)
synthesis_parser.add_argument(
    "-noregfile",
    help="Do not map register files.",
    action="store_true",
)
synthesis_parser.add_argument(
    "-iopad",
    help="Enable automatic insertion of IO buffers (otherwise a wrapper with "
    "manually inserted and constrained IO should be used.)",
    action="store_true",
)
synthesis_parser.add_argument(
    "-complex-dff",
    help="Enable support for FFs with enable and synchronous SR "
    "(must also be supported by the target fabric).",
    action="store_true",
)
synthesis_parser.add_argument(
    "-noflatten",
    help="Do not flatten the design after elaboration.",
    action="store_true",
)
synthesis_parser.add_argument(
    "-nordff",
    help="Passed to 'memory'. Prohibits merging of FFs into memory read ports.",
    action="store_true",
)
synthesis_parser.add_argument(
    "-noshare",
    help="Do not run SAT-based resource sharing",
    action="store_true",
)
synthesis_parser.add_argument(
    "-run",
    type=str,
    help="Only run the commands between the labels (see above). An empty from label is "
    "synonymous to 'begin',"
    " and empty to label is synonymous to the end of the command list.",
)
synthesis_parser.add_argument(
    "-no-rw-check",
    help="Marks all recognized read ports as 'return don't-care value on read/write"
    "collision' (same result as setting 'no_rw_check' attribute on all memories).",
    action="store_true",
)


@with_category(CMD_USER_DESIGN_FLOW)
@with_argparser(synthesis_parser)
def do_synthesis(self: "FABulous_CLI", args: argparse.Namespace) -> None:
    """Run Yosys synthesis for the specified Verilog files.

    Performs FPGA synthesis using Yosys with the nextpnr JSON backend
    to synthesize Verilog designs and generate nextpnr-compatible JSON files for
    place and route. It supports various synthesis options including LUT architecture,
    FSM optimization, carry mapping, and different output formats.

    Parameters
    ----------
    self : FABulous_CLI
        The CLI instance containing project and fabric information.
    args : argparse.Namespace
        Command arguments containing:
        - files: List of Verilog files to synthesize
        - top: Top module name (default: 'top_wrapper')
        - auto_top: Whether to automatically determine top module
        - json: Output JSON file path
        - blif: Output BLIF file path (optional)
        - edif: Output EDIF file path (optional)
        - lut: LUT architecture size (default: 4)
        - And various other synthesis options

    Notes
    -----
    The synthesis process includes multiple stages: hierarchy checking,
    flattening, coarse synthesis, RAM mapping, gate mapping, FF mapping,
    LUT mapping, and final netlist generation. See the module docstring
    for detailed synthesis flow information.
    """
    logger.info(
        f"Running synthesis targeting Nextpnr with design{[str(i) for i in args.files]}"
    )

    p: Path
    paths: list[Path] = []
    for p in args.files:
        if not p.is_absolute():
            p = self.projectDir / p
        resolvePath: Path = p.absolute()
        if resolvePath.exists():
            paths.append(resolvePath)
        else:
            logger.error(f"{resolvePath} does not exists")
            return

    json_file = paths[0].with_suffix(".json")
    yosys = get_context().yosys_path

    cmd = [
        "synth_fabulous",
        f"-top {args.top}",
        f"-blif {args.blif}" if args.blif else "",
        f"-edif {args.edif}" if args.edif else "",
        f"-json {args.json}" if args.json else f"-json {json_file}",
        f"-lut {args.lut}" if args.lut else "",
        f"-plib {args.plib}" if args.plib else "",
        (
            " ".join([f"-extra-plib {i}" for i in args.extra_plib])
            if args.extra_plib
            else ""
        ),
        " ".join([f"-extra-map {i}" for i in args.extra_map]) if args.extra_map else "",
        f"-encfile {args.encfile}" if args.encfile else "",
        "-nofsm" if args.nofsm else "",
        "-noalumacc" if args.noalumacc else "",
        f"-carry {args.carry}" if args.carry else "",
        "-noregfile" if args.noregfile else "",
        "-iopad" if args.iopad else "",
        "-complex-dff" if args.complex_dff else "",
        "-noflatten" if args.noflatten else "",
        "-noshare" if args.noshare else "",
        f"-run {args.run}" if args.run else "",
        "-no-rw-check" if args.no_rw_check else "",
    ]

    cmd = " ".join([i for i in cmd if i != ""])

    runCmd = [
        f"{yosys!s}",
        "-p",
        f"{cmd}",
        f"{self.projectDir}/user_design/top_wrapper.v",
        *[str(i) for i in paths],
    ]
    logger.debug(f"{runCmd}")
    result = sp.run(runCmd, check=True)

    if result.returncode != 0:
        logger.opt(exception=CommandError()).error(
            "Synthesis failed with non-zero return code."
        )
    logger.info("Synthesis command executed successfully.")

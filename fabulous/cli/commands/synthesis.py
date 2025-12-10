"""Synthesis command implementation for the FABulous CLI.

This module provides the synthesis command functionality for the FABulous command-line
interface. It implements Yosys-based FPGA synthesis targeting the nextpnr place-and-
route tool, with support for various synthesis options and output formats.

The synthesis flow includes multiple stages, from reading the Verilog files through
final netlist generation, with options for LUT mapping, FSM optimization, carry chain
mapping, and memory inference.
"""

import subprocess as sp
from pathlib import Path
from typing import Annotated, Literal

import typer
from cmd2 import Cmd, with_category
from loguru import logger

from fabulous.cli.plugin import CompleterSpec
from fabulous.utils.exceptions import CommandError
from fabulous.utils.settings import get_context

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


@with_category(CMD_USER_DESIGN_FLOW)
def do_synthesis(
    self: Cmd,
    files: Annotated[
        list[Path],
        typer.Argument(help="Path to the target files."),
        CompleterSpec(Cmd.path_complete),
    ],
    top: Annotated[
        str,
        typer.Option(
            "--top",
            "-top",
            help="Use the specified module as the top module (default='top_wrapper').",
        ),
    ] = "top_wrapper",
    _auto_top: Annotated[
        bool,
        typer.Option(
            "--auto-top",
            "-auto-top",
            help="Automatically determine the top of the design hierarchy.",
        ),
    ] = False,
    blif: Annotated[
        Path | None,
        typer.Option(
            "--blif", "-blif", help="Write the design to the specified BLIF file."
        ),
    ] = None,
    edif: Annotated[
        Path | None,
        typer.Option(
            "--edif", "-edif", help="Write the design to the specified EDIF file."
        ),
    ] = None,
    json: Annotated[
        Path | None,
        typer.Option(
            "--json",
            "-json",
            help=(
                "Write the design to the specified JSON file. "
                "If not specified, defaults to <first_file_stem>.json"
            ),
        ),
    ] = None,
    lut: Annotated[
        str,
        typer.Option(
            "--lut",
            "-lut",
            help="Perform synthesis for a k-LUT architecture (default 4).",
        ),
    ] = "4",
    plib: Annotated[
        str | None,
        typer.Option(
            "--plib",
            "-plib",
            help="Use the specified Verilog file as a primitive library.",
        ),
    ] = None,
    extra_plib: Annotated[
        list[Path] | None,
        typer.Option(
            "--extra-plib",
            "-extra-plib",
            help=(
                "Use the specified Verilog file for extra primitives "
                "(can be specified multiple times)."
            ),
        ),
    ] = None,
    extra_map: Annotated[
        list[Path] | None,
        typer.Option(
            "--extra-map",
            "-extra-map",
            help=(
                "Use the specified Verilog file for extra techmap rules "
                "(can be specified multiple times)."
            ),
        ),
    ] = None,
    encfile: Annotated[
        Path | None,
        typer.Option("--encfile", "-encfile", help="Passed to 'fsm_recode' via 'fsm'."),
    ] = None,
    nofsm: Annotated[
        bool,
        typer.Option("--nofsm", "-nofsm", help="Do not run FSM optimization."),
    ] = False,
    noalumacc: Annotated[
        bool,
        typer.Option(
            "--noalumacc",
            "-noalumacc",
            help=(
                "Do not run 'alumacc' pass. I.e., keep arithmetic operators "
                "in their direct form ($add, $sub, etc.)."
            ),
        ),
    ] = False,
    carry: Annotated[
        Literal["none", "ha"],
        typer.Option(
            "--carry",
            "-carry",
            help="Carry mapping style (none, half-adders, ...) default=none.",
        ),
    ] = "none",
    noregfile: Annotated[
        bool,
        typer.Option("--noregfile", "-noregfile", help="Do not map register files."),
    ] = False,
    iopad: Annotated[
        bool,
        typer.Option(
            "--iopad", "-iopad", help="Enable automatic insertion of IO buffers."
        ),
    ] = False,
    complex_dff: Annotated[
        bool,
        typer.Option(
            "--complex-dff",
            "-complex-dff",
            help="Enable support for FFs with enable and synchronous SR.",
        ),
    ] = False,
    noflatten: Annotated[
        bool,
        typer.Option(
            "--noflatten",
            "-noflatten",
            help="Do not flatten the design after elaboration.",
        ),
    ] = False,
    _nordff: Annotated[
        bool,
        typer.Option(
            "--nordff",
            "-nordff",
            help="Passed to 'memory'. Prohibits merging of FFs into memory read ports.",
        ),
    ] = False,
    noshare: Annotated[
        bool,
        typer.Option(
            "--noshare", "-noshare", help="Do not run SAT-based resource sharing"
        ),
    ] = False,
    run: Annotated[
        str | None,
        typer.Option("--run", "-run", help="Only run the commands between the labels."),
    ] = None,
    no_rw_check: Annotated[
        bool,
        typer.Option(
            "--no-rw-check",
            "-no-rw-check",
            help=(
                "Marks all recognized read ports as "
                "'return don't-care value on read/write collision'."
            ),
        ),
    ] = False,
) -> None:
    """Run Yosys synthesis for the specified Verilog files.

    Performs FPGA synthesis using Yosys with the nextpnr JSON backend to synthesize
    Verilog designs and generate nextpnr-compatible JSON files for place and route. It
    supports various synthesis options including LUT architecture, FSM optimization,
    carry mapping, and different output formats.
    """
    logger.info(
        f"Running synthesis targeting Nextpnr with design{[str(i) for i in files]}"
    )

    p: Path
    paths: list[Path] = []
    for p in files:
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
        f"-top {top}",
        f"-blif {blif}" if blif else "",
        f"-edif {edif}" if edif else "",
        f"-json {json}" if json else f"-json {json_file}",
        f"-lut {lut}" if lut else "",
        f"-plib {plib}" if plib else "",
        (" ".join([f"-extra-plib {i}" for i in extra_plib]) if extra_plib else ""),
        " ".join([f"-extra-map {i}" for i in extra_map]) if extra_map else "",
        f"-encfile {encfile}" if encfile else "",
        "-nofsm" if nofsm else "",
        "-noalumacc" if noalumacc else "",
        f"-carry {carry}" if carry else "",
        "-noregfile" if noregfile else "",
        "-iopad" if iopad else "",
        "-complex-dff" if complex_dff else "",
        "-noflatten" if noflatten else "",
        "-noshare" if noshare else "",
        f"-run {run}" if run else "",
        "-no-rw-check" if no_rw_check else "",
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

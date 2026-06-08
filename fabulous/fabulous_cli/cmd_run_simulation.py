"""Run-simulation command implementation for the FABulous CLI.

RTL simulation exercises the behavioural fabric FABulous emits. Gate-level
simulation (``--gl``) reuses the *same* testbench and bitstream but swaps the
inner fabric core ``eFPGA`` and its tiles for the post-place-and-route netlists
hardened by the GDS flow, linked against the PDK standard-cell models. The
behavioural wrapper ``eFPGA_top`` (with its configuration controller) is kept,
so the existing ``<design>_tb.v`` drives the mixed-level DUT unchanged.
"""

import argparse
import subprocess as sp
from pathlib import Path
from typing import TYPE_CHECKING

from cmd2 import Cmd, Cmd2ArgumentParser, with_argparser, with_category
from loguru import logger

from fabulous.custom_exception import InvalidFileType
from fabulous.fabulous_cli.helper import make_hex, run_task
from fabulous.fabulous_settings import get_context

if TYPE_CHECKING:
    from fabulous.fabulous_cli.fabulous_cli import FABulous_CLI

CMD_USER_DESIGN_FLOW = "User Design Flow"

# Default PDK standard-cell library per PDK; override with --gl-sim-libs for a
# PDK or install layout not covered here.
_SCL_BY_PDK: dict[str, str] = {
    "ihp-sg13g2": "sg13g2_stdcell",
    "sky130A": "sky130_fd_sc_hd",
    "gf180mcuD": "gf180mcu_fd_sc_mcu7t5v0",
}


def resolve_sim_libs(project: Path, overrides: list[str]) -> list[Path]:
    """Resolve the PDK standard-cell Verilog sim models for ``project``.

    Honours ``overrides`` (files or globs) first; otherwise takes the active
    PDK and its install root from the FABulous context (which resolves
    ``FAB_PDK`` / ``FAB_PDK_ROOT`` and the ciel install) and globs
    ``<pdk_root>/<pdk>/libs.ref/<scl>/verilog/`` for ``<scl>.v`` plus any
    ``*udp*.v`` / ``primitives.v`` companion (sky130 and gf180 ship their UDPs
    in a separate ``primitives.v``; IHP inlines them).

    Parameters
    ----------
    project : Path
        Root of a hardened FABulous project; used to anchor relative override
        globs.
    overrides : list[str]
        Explicit sim-cell library files or globs. When non-empty, PDK
        auto-resolution is skipped.

    Returns
    -------
    list[Path]
        Verilog cell-model files for the simulator.

    Raises
    ------
    FileNotFoundError
        If an override matches nothing, or the resolved PDK sim file is missing.
    ValueError
        If the context has no PDK or PDK root, or the PDK has no known default
        standard-cell library.
    """
    if overrides:
        resolved: list[Path] = []
        for spec in overrides:
            path = Path(spec).expanduser()
            if path.is_file():
                resolved.append(path.resolve())
                continue
            anchor = path if path.is_absolute() else project / path
            matches = sorted(Path(anchor.anchor or "/").glob(str(anchor).lstrip("/")))
            if not matches:
                raise FileNotFoundError(f"--gl-sim-libs {spec} matched no files")
            resolved.extend(m.resolve() for m in matches)
        return resolved

    ctx = get_context()
    pdk = ctx.pdk
    if not pdk:
        raise ValueError(
            "Cannot resolve PDK sim libs: set FAB_PDK in the project .env, or "
            "pass --gl-sim-libs explicitly."
        )
    scl = _SCL_BY_PDK.get(pdk)
    if scl is None:
        raise ValueError(
            f"No default standard-cell library known for PDK '{pdk}'. Pass "
            "--gl-sim-libs to point at the cell models directly."
        )
    if ctx.pdk_root is None:
        raise ValueError(
            f"Cannot resolve PDK_ROOT for '{pdk}'. Set FAB_PDK_ROOT in the "
            "project .env, install the PDK via ciel, or pass --gl-sim-libs."
        )

    verilog_root = ctx.pdk_root / pdk / "libs.ref" / scl / "verilog"
    primary = verilog_root / f"{scl}.v"
    if not primary.exists():
        raise FileNotFoundError(f"PDK sim file {primary} is missing.")
    companions = sorted(
        set(verilog_root.glob("*udp*.v")) | set(verilog_root.glob("primitives.v"))
    )
    return [primary, *companions]


def collect_gl_sources(project: Path, sim_lib_overrides: list[str]) -> list[Path]:
    """Resolve every Verilog source the gate-level simulator needs.

    Returns one self-contained source list so the caller can hand it to
    iverilog directly (no extra ``find`` in the Taskfile):

    - the behavioural wrapper that keeps driving configuration (``Fabric/*.v``:
      ``eFPGA_top``, the config controller, ``Frame_*``, ``BlockRAM``,
      ``models_pack`` ...). The behavioural core ``eFPGA.v`` is excluded because
      the gate-level ``eFPGA.nl.v`` replaces it.
    - the post-PnR fabric netlist (``Fabric/macro/final_views`` holds exactly one
      ``*.nl.v``, structural, instantiating tile macros by name),
    - every tile netlist (``Tile/<tile>/macro/final_views/nl/<tile>.nl.v``),
    - the PDK cell models the netlists bind against.

    Parameters
    ----------
    project : Path
        Root of a FABulous project hardened through the GDS flow.
    sim_lib_overrides : list[str]
        Explicit PDK sim-cell library files or globs; skips auto-resolution.

    Returns
    -------
    list[Path]
        Behavioural wrapper, fabric netlist, tile netlists, then PDK cell
        models, in that order.

    Raises
    ------
    FileNotFoundError
        If the fabric netlist or tile netlists are missing (the GDS flow has
        not been run).
    ValueError
        If more than one fabric netlist is present.
    """
    macro_root = project / "Fabric" / "macro" / "final_views"
    fabric_netlists = sorted(macro_root.rglob("*.nl.v"))
    if not fabric_netlists:
        raise FileNotFoundError(
            f"No fabric netlist under {macro_root}. Run `gen_fabric_macro` "
            "against the project before gate-level simulation."
        )
    if len(fabric_netlists) > 1:
        joined = ", ".join(str(p.relative_to(project)) for p in fabric_netlists)
        raise ValueError(f"Multiple fabric netlists; refusing to guess: {joined}")

    tile_netlists = sorted((project / "Tile").glob("*/macro/final_views/nl/*.nl.v"))
    if not tile_netlists:
        raise FileNotFoundError(
            f"No tile netlists under {project / 'Tile'}/*/macro/final_views/nl/. "
            "Run `gen_all_tile_macros` first."
        )

    # Behavioural wrapper Verilog directly under Fabric/ (not the macro/ tree).
    # Exclude the behavioural fabric core; the gate-level netlist replaces it.
    behavioural = sorted(
        p for p in (project / "Fabric").glob("*.v") if p.name != "eFPGA.v"
    )

    sim_libs = resolve_sim_libs(project, sim_lib_overrides)
    logger.info(
        f"GL sources: {len(behavioural)} behavioural wrapper + 1 fabric netlist "
        f"+ {len(tile_netlists)} tile netlists + {len(sim_libs)} PDK sim file(s)"
    )
    return [*behavioural, *fabric_netlists, *tile_netlists, *sim_libs]


run_simulation_parser = Cmd2ArgumentParser()
run_simulation_parser.add_argument(
    "format",
    choices=["vcd", "fst"],
    default="fst",
    help="Output format of the simulation",
)
run_simulation_parser.add_argument(
    "file",
    type=Path,
    completer=Cmd.path_complete,
    help="Path to the bitstream file",
)
run_simulation_parser.add_argument(
    "-d",
    "--design",
    default="",
    help="Design name to simulate (default: inferred from bitstream filename)",
)
run_simulation_parser.add_argument(
    "-s",
    "--simulator",
    default="",
    choices=["nvc", "ghdl", "auto", ""],
    help="VHDL simulator to use: nvc, ghdl, or auto (default: auto-detect)",
)
run_simulation_parser.add_argument(
    "-if",
    "--extra-iverilog-flag",
    default="",
    help="Extra flags to pass to iverilog (Verilog projects)",
)
run_simulation_parser.add_argument(
    "-nf",
    "--extra-nvc-flag",
    default="",
    help="Extra flags to pass to NVC (VHDL projects)",
)
run_simulation_parser.add_argument(
    "-gf",
    "--extra-ghdl-flag",
    default="",
    help="Extra flags to pass to GHDL (VHDL projects)",
)
run_simulation_parser.add_argument(
    "--gl",
    action="store_true",
    help="Gate-level (mixed-level) simulation: keep the behavioural wrapper but "
    "swap the fabric core for the hardened post-PnR netlist. Verilog only; the "
    "project must have been run through `gen_fabric_macro`.",
)
run_simulation_parser.add_argument(
    "--gl-sim-libs",
    action="append",
    default=[],
    metavar="FILE_OR_GLOB",
    help="Verilog sim-cell library file or glob (repeatable). Overrides PDK "
    "auto-resolution from FAB_PDK / FAB_PDK_ROOT. Only used with --gl.",
)


@with_category(CMD_USER_DESIGN_FLOW)
@with_argparser(run_simulation_parser)
def do_run_simulation(self: "FABulous_CLI", args: argparse.Namespace) -> None:
    """Simulate given FPGA design.

    Uses Taskfile.yml (preferred) or falls back to Make (deprecated). The
    bitstream_file argument should be a binary file generated by
    'compile_design'. With ``--gl`` the hardened fabric netlist replaces the
    behavioural core for gate-level simulation.
    """
    if args.file.is_relative_to(self.projectDir):
        bitstreamPath = args.file
    else:
        bitstreamPath = self.projectDir / args.file

    if bitstreamPath.suffix != ".bin":
        raise InvalidFileType(
            "No bitstream file specified. "
            "Usage: run_simulation <format> <bitstream_file>"
        )

    if not bitstreamPath.exists():
        raise FileNotFoundError(
            f"Cannot find {bitstreamPath} file which is generated by running "
            "compile_design. Potentially the bitstream generation failed."
        )

    testPath = self.projectDir / "Test"
    taskfile = testPath / "Taskfile.yml"
    makefile = testPath / "Makefile"

    design_name = args.design or bitstreamPath.stem

    # Prepare build directory and convert .bin to .hex for simulation
    buildDir = testPath / "build"
    buildDir.mkdir(parents=True, exist_ok=True)
    hexPath = buildDir / f"{design_name}.hex"
    make_hex(bitstreamPath, hexPath)
    logger.info(f"Converted {bitstreamPath} to {hexPath}")

    task_vars = {
        "WAVEFORM_TYPE": args.format,
        "DESIGN": design_name,
        "BITSTREAM_BIN": str(bitstreamPath.resolve()),
    }
    if args.simulator:
        task_vars["SIMULATOR"] = args.simulator
    if args.extra_iverilog_flag:
        task_vars["EXTRA_IVERILOG_FLAGS"] = args.extra_iverilog_flag
    if args.extra_nvc_flag:
        task_vars["EXTRA_NVC_FLAGS"] = args.extra_nvc_flag
    if args.extra_ghdl_flag:
        task_vars["EXTRA_GHDL_FLAGS"] = args.extra_ghdl_flag

    if args.gl:
        if self.extension == "vhdl":
            raise InvalidFileType(
                "Gate-level simulation is Verilog-only: the hardened netlists "
                "and PDK cell models are Verilog, which nvc/ghdl cannot "
                "co-simulate with a VHDL wrapper."
            )
        if not taskfile.exists():
            raise FileNotFoundError(
                f"No Taskfile.yml found in {testPath}. Gate-level simulation "
                "requires the Taskfile flow."
            )
        gl_sources = collect_gl_sources(self.projectDir, args.gl_sim_libs)
        task_vars["GL_SOURCES"] = " ".join(str(p) for p in gl_sources)
        logger.info(f"Running gate-level simulation for {design_name} via Taskfile")
        run_task(
            "run-gl-simulation",
            task_dir=testPath,
            task_vars=task_vars,
            verbose=self.verbose or self.debug,
        )
        logger.info("Gate-level simulation finished")
        return

    if taskfile.exists():
        logger.info(f"Running simulation for {design_name} via Taskfile")
        run_task(
            "run-simulation",
            task_dir=testPath,
            task_vars=task_vars,
            verbose=self.verbose or self.debug,
        )
    elif makefile.exists():
        logger.warning(
            "Taskfile.yml not found, falling back to Makefile. "
            "Makefiles are deprecated and will be removed in the next release. "
            "Please migrate to Taskfile.yml."
        )
        make_cmd = ["make", "-C", str(testPath), "run_simulation"]
        if self.verbose or self.debug:
            logger.info(f"Running command: {' '.join(make_cmd)}")
        sp.run(make_cmd, check=True)
    else:
        raise FileNotFoundError(
            f"No Taskfile.yml or Makefile found in {testPath}. "
            "Please ensure the project Test directory is set up correctly."
        )

    logger.info("Simulation finished")

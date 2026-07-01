"""User design flow commands for the FABulous REPL.

Synthesis, place-and-route, bitstream generation, simulation, and user
design wrapper generation.
"""

import subprocess as sp
from pathlib import Path
from typing import Annotated, Literal

from cmd2 import with_annotated, with_category
from cmd2.annotated import Argument, Option
from loguru import logger

from fabulous.custom_exception import CommandError, InvalidFileType
from fabulous.fabulous_repl.command_set_base import CMD_USER_DESIGN_FLOW, ReplCommandSet
from fabulous.fabulous_repl.helper import make_hex, run_task
from fabulous.fabulous_settings import get_context


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
        sp.run(
            [str(tool_path), *args],
            check=False,
        )
    except FileNotFoundError:
        logger.error(
            f"{tool_name} not found at '{tool_path}'. "
            "Ensure it is installed and on PATH."
        )


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


class UserDesignCommandSet(ReplCommandSet):
    """User design flow: synthesis through bitstream and simulation."""

    @with_category(CMD_USER_DESIGN_FLOW)
    @with_annotated
    def do_synthesis(  # noqa: PLR0913, C901
        self,
        files: Annotated[list[Path], Argument(help_text="Verilog source files")],
        top: Annotated[str, Option("-top")] = "top_wrapper",
        auto_top: Annotated[bool, Option("-auto-top")] = False,
        blif: Annotated[Path | None, Option("-blif")] = None,
        edif: Annotated[Path | None, Option("-edif")] = None,
        json_file: Annotated[Path | None, Option("-json")] = None,
        lut: Annotated[str, Option("-lut")] = "4",
        plib: Annotated[str | None, Option("-plib")] = None,
        extra_plib: Annotated[
            list[Path] | None, Option("-extra-plib", action="append")
        ] = None,
        extra_map: Annotated[
            list[Path] | None, Option("-extra-map", action="append")
        ] = None,
        encfile: Annotated[Path | None, Option("-encfile")] = None,
        nofsm: Annotated[bool, Option("-nofsm")] = False,
        noalumacc: Annotated[bool, Option("-noalumacc")] = False,
        carry: Annotated[Literal["none", "ha"], Option("-carry")] = "none",
        noregfile: Annotated[bool, Option("-noregfile")] = False,
        iopad: Annotated[bool, Option("-iopad")] = False,
        complex_dff: Annotated[bool, Option("-complex-dff")] = False,
        noflatten: Annotated[bool, Option("-noflatten")] = False,
        nordff: Annotated[bool, Option("-nordff")] = False,
        noshare: Annotated[bool, Option("-noshare")] = False,
        run: Annotated[str | None, Option("-run")] = None,
        no_rw_check: Annotated[bool, Option("-no-rw-check")] = False,
    ) -> None:
        """Run Yosys synthesis for the specified Verilog files.

        deprecated: Use ``compile_design --synth-only`` instead.
        """
        repl = self._cmd
        del auto_top  # accepted for backwards compat; not forwarded to compile_design
        logger.warning(
            "The 'synthesis' command is deprecated. Use 'compile_design' instead."
        )

        # Translate legacy flags into --synth-extra-args for compile_design
        extra = []
        if blif:
            extra.append(f"-blif {blif}")
        if edif:
            extra.append(f"-edif {edif}")
        if lut:
            extra.append(f"-lut {lut}")
        if plib:
            extra.append(f"-plib {plib}")
        if extra_plib:
            extra.extend(f"-extra-plib {p}" for p in extra_plib)
        if extra_map:
            extra.extend(f"-extra-map {m}" for m in extra_map)
        if encfile:
            extra.append(f"-encfile {encfile}")
        if nofsm:
            extra.append("-nofsm")
        if noalumacc:
            extra.append("-noalumacc")
        if carry and carry != "none":
            extra.append(f"-carry {carry}")
        if noregfile:
            extra.append("-noregfile")
        if iopad:
            extra.append("-iopad")
        if complex_dff:
            extra.append("-complex-dff")
        if noflatten:
            extra.append("-noflatten")
        if nordff:
            extra.append("-nordff")
        if noshare:
            extra.append("-noshare")
        if run:
            extra.append(f"-run {run}")
        if no_rw_check:
            extra.append("-no-rw-check")

        cmd = f"compile_design {' '.join(str(f) for f in files)} --synth-only"
        if top != "top_wrapper":
            cmd += f" -top {top}"
        if json_file:
            cmd += f" -json {json_file}"
        if extra:
            cmd += f' --synth-extra-args "{" ".join(extra)}"'

        repl.onecmd_plus_hooks(cmd)

    @with_category(CMD_USER_DESIGN_FLOW)
    @with_annotated
    def do_place_and_route(
        self,
        file: Annotated[Path, Argument(help_text="Path to the target file")],
    ) -> None:
        """Run place and route with Nextpnr for a given JSON file.

        deprecated: Use ``compile_design --pnr-only`` instead.
        """
        repl = self._cmd
        logger.warning(
            "The 'place_and_route' command is deprecated. "
            "Use 'compile_design --pnr-only' instead."
        )

        if file.suffix != ".json":
            raise InvalidFileType(
                "No json file provided. Usage: place_and_route <json_file>"
            )

        repl.onecmd_plus_hooks(f"compile_design {file} --pnr-only")

    @with_category(CMD_USER_DESIGN_FLOW)
    @with_annotated
    def do_gen_bitStream_binary(
        self,
        file: Annotated[Path, Argument(help_text="Path to the target file")],
    ) -> None:
        """Generate bitstream of a given design.

        deprecated: Use ``compile_design`` which includes bitstream generation.
        """
        repl = self._cmd
        logger.warning(
            "The 'gen_bitStream_binary' command is deprecated. "
            "Use 'compile_design' instead, which includes bitstream generation."
        )

        if file.suffix != ".fasm":
            raise InvalidFileType(
                "No fasm file provided. Usage: gen_bitStream_binary <fasm_file>"
            )

        repl.onecmd_plus_hooks(f"compile_design {file} --bitgen-only")

    @with_category(CMD_USER_DESIGN_FLOW)
    @with_annotated
    def do_run_FABulous_bitstream(
        self,
        file: Annotated[Path, Argument(help_text="Path to the target file")],
    ) -> None:
        """Run FABulous to generate bitstream on a given design.

        deprecated: Use ``compile_design`` instead.
        """
        repl = self._cmd
        logger.warning(
            "The 'run_FABulous_bitstream' command is deprecated. "
            "Use 'compile_design' instead."
        )

        if file.suffix not in [".v", ".sv"]:
            raise InvalidFileType(
                "No Verilog or SystemVerilog file provided. "
                "Usage: run_FABulous_bitstream <top_module_file>"
            )

        repl.onecmd_plus_hooks(f"compile_design {file}")

    # Overrides cmd2's built-in run_script (which cmd2 also invokes internally for
    # the `@` relative-script shortcut). Because it shadows a built-in, it cannot
    # be moved into a CommandSet, which cmd2 forbids from replacing existing
    # attributes.

    @with_category(CMD_USER_DESIGN_FLOW)
    @with_annotated
    def do_gen_user_design_wrapper(
        self,
        user_design: Annotated[Path, Argument(help_text="Path to user design file")],
        user_design_top_wrapper: Annotated[
            Path, Argument(help_text="Output path for user design top wrapper")
        ],
    ) -> None:
        """Generate a wrapper that connects the user design to the fabric."""
        repl = self._cmd
        if not repl.fabric_loaded:
            raise CommandError("Need to load fabric first")
        project_dir = get_context().proj_dir
        repl.fabulousAPI.generateUserDesignTopWrapper(
            project_dir / user_design,
            project_dir / user_design_top_wrapper,
        )

    @with_category(CMD_USER_DESIGN_FLOW)
    @with_annotated
    def do_compile_design(
        self,
        files: Annotated[list[Path], Argument(help_text="Path to the target files.")],
        top: Annotated[
            str,
            Option(
                "-top",
                help_text=(
                    "Use the specified module as the top module "
                    "(default='top_wrapper')."
                ),
            ),
        ] = "top_wrapper",
        json: Annotated[
            Path | None,
            Option(
                "-json",
                help_text=(
                    "Write the design to the specified JSON file. "
                    "If not specified, defaults to <first_file_stem>.json."
                ),
            ),
        ] = None,
        synth_only: Annotated[
            bool, Option("--synth-only", help_text="Only run synthesis.")
        ] = False,
        pnr_only: Annotated[
            bool,
            Option(
                "--pnr-only",
                help_text="Only run place-and-route (JSON must already exist).",
            ),
        ] = False,
        bitgen_only: Annotated[
            bool,
            Option(
                "--bitgen-only",
                help_text="Only run bitstream generation (FASM must already exist).",
            ),
        ] = False,
        synth_extra_args: Annotated[
            str,
            Option(
                "--synth-extra-args",
                help_text=(
                    "Extra arguments appended to the synth_fabulous command "
                    "(e.g. '-nofsm -extra-plib prims.v')."
                ),
            ),
        ] = "",
        yosys_extra_args: Annotated[
            str,
            Option(
                "--yosys-extra-args",
                help_text=(
                    "Extra arguments passed to the Yosys CLI itself "
                    "(before the -p flag)."
                ),
            ),
        ] = "",
        nextpnr_extra_args: Annotated[
            str,
            Option(
                "--nextpnr-extra-args",
                help_text="Extra arguments passed to the nextpnr CLI.",
            ),
        ] = "",
        log: Annotated[
            Path | None, Option("-log", help_text="Set log output file path")
        ] = None,
        fasm: Annotated[
            Path | None, Option("-fasm", help_text="Set fasm output file path")
        ] = None,
        bin_file: Annotated[
            Path | None, Option("-bin", help_text="Set bit file output file path")
        ] = None,
        yosys_synth_help: Annotated[
            bool,
            Option(
                "--yosys-synth-help",
                help_text="Print the full synth_fabulous help from Yosys and exit.",
            ),
        ] = False,
        nextpnr_help: Annotated[
            bool,
            Option("--nextpnr-help", help_text="Print the full nextpnr help and exit."),
        ] = False,
    ) -> None:
        """Compile a user design through synthesis, PnR, and bitstream generation.

        This function orchestrates the full compile flow by delegating to a compile
        Taskfile. It resolves input file paths, builds the synthesis command, and
        invokes the appropriate task(s) depending on the selected mode (full
        compile, synth-only, pnr-only, or no-bitgen).
        """
        repl = self._cmd
        if yosys_synth_help:
            ctx = get_context()
            _print_tool_help(ctx.yosys_path, ["-p", "help synth_fabulous"], "Yosys")
            return
        if nextpnr_help:
            ctx = get_context()
            _print_tool_help(ctx.nextpnr_path, ["--help"], "nextpnr")
            return

        logger.info(f"Compiling design with files {[str(i) for i in files]}")

        p: Path
        paths: list[Path] = []
        for p in files:
            if not p.is_absolute():
                p = repl.projectDir / p
            resolvePath: Path = p.absolute()
            if resolvePath.exists():
                paths.append(resolvePath)
            else:
                logger.error(f"{resolvePath} does not exist")
                return

        # Output paths must be absolute: the task runs with cwd=.FABulous/.
        json_file = json or paths[0].with_suffix(".json")
        if not json_file.is_absolute():
            json_file = (repl.projectDir / json_file).resolve()

        fasm_file = fasm or json_file.with_suffix(".fasm")
        if not fasm_file.is_absolute():
            fasm_file = (repl.projectDir / fasm_file).resolve()

        log_file = log or json_file.parent / (
            json_file.with_suffix("").name + "_npnr_log.txt"
        )
        if not log_file.is_absolute():
            log_file = (repl.projectDir / log_file).resolve()

        bin_file = bin_file or fasm_file.with_suffix(".bin")
        if not bin_file.is_absolute():
            bin_file = (repl.projectDir / bin_file).resolve()

        task_dir = repl.projectDir / "Test"
        compile_taskfile = task_dir / "Taskfile.yml"
        if not compile_taskfile.exists():
            raise FileNotFoundError(
                f"Compile Taskfile not found at {compile_taskfile}. "
                "Please ensure the project is set up correctly."
            )

        ctx = get_context()
        task_vars: dict[str, str] = {
            "YOSYS_PATH": str(ctx.yosys_path),
            "NEXTPNR_PATH": str(ctx.nextpnr_path),
            "FAB_PROJ_ROOT": str(repl.projectDir),
            "DESIGN": paths[0].stem,
            "TOP_WRAPPER": top,
            "DESIGN_FILES": " ".join(str(p) for p in paths),
            "TOP_WRAPPER_FILE": str(repl.projectDir / "user_design" / "top_wrapper.v"),
            "JSON_FILE": str(json_file),
            "FASM_FILE": str(fasm_file),
            "BIN_FILE": str(bin_file),
            "LOG_FILE": str(log_file),
            "SYNTH_EXTRA_ARGS": synth_extra_args,
            "YOSYS_EXTRA_ARGS": yosys_extra_args,
            "NEXTPNR_EXTRA_ARGS": nextpnr_extra_args,
            "NEXTPNR_VERBOSE": "--verbose" if (repl.verbose or repl.debug) else "",
        }

        if synth_only:
            run_task("run-yosys", task_dir, task_vars)
        elif pnr_only:
            run_task("run-nextpnr", task_dir, task_vars)
        elif bitgen_only:
            run_task("run-bitgen", task_dir, task_vars)
        else:
            run_task("build-test-design", task_dir, task_vars)

        logger.info("Compile flow completed successfully.")

    @with_category(CMD_USER_DESIGN_FLOW)
    @with_annotated
    def do_run_simulation(
        self,
        output_format: Annotated[
            Literal["vcd", "fst"],
            Argument(
                help_text="Output format of the simulation",
                metavar="format",
            ),
        ],
        file: Annotated[Path, Argument(help_text="Path to the bitstream file")],
        design: Annotated[
            str,
            Option(
                "--design",
                "-d",
                help_text=(
                    "Design name to simulate "
                    "(default: inferred from bitstream filename)"
                ),
            ),
        ] = "",
        simulator: Annotated[
            Literal["nvc", "ghdl", "auto", ""],
            Option(
                "--simulator",
                "-s",
                help_text=(
                    "VHDL simulator to use: nvc, ghdl, or auto (default: auto-detect)"
                ),
            ),
        ] = "",
        extra_iverilog_flag: Annotated[
            str,
            Option(
                "--extra-iverilog-flag",
                "-if",
                help_text="Extra flags to pass to iverilog (Verilog projects)",
            ),
        ] = "",
        extra_nvc_flag: Annotated[
            str,
            Option(
                "--extra-nvc-flag",
                "-nf",
                help_text="Extra flags to pass to NVC (VHDL projects)",
            ),
        ] = "",
        extra_ghdl_flag: Annotated[
            str,
            Option(
                "--extra-ghdl-flag",
                "-gf",
                help_text="Extra flags to pass to GHDL (VHDL projects)",
            ),
        ] = "",
        gl: Annotated[
            bool,
            Option(
                "--gl",
                help_text=(
                    "Gate-level (mixed-level) simulation: keep the behavioural "
                    "wrapper but swap the fabric core for the hardened post-PnR "
                    "netlist. Verilog only; the project must have been run "
                    "through `gen_fabric_macro`."
                ),
            ),
        ] = False,
        gl_sim_libs: Annotated[
            list[str] | None,
            Option(
                "--gl-sim-libs",
                action="append",
                metavar="FILE_OR_GLOB",
                help_text=(
                    "Verilog sim-cell library file or glob (repeatable). Overrides PDK "
                    "auto-resolution from FAB_PDK / FAB_PDK_ROOT. Only used with --gl."
                ),
            ),
        ] = None,
    ) -> None:
        """Simulate given FPGA design.

        Uses Taskfile.yml (preferred) or falls back to Make (deprecated). The
        bitstream_file argument should be a binary file generated by
        'compile_design'. With ``--gl`` the hardened fabric netlist replaces the
        behavioural core for gate-level simulation.
        """
        repl = self._cmd
        if file.is_relative_to(repl.projectDir):
            bitstream_path = file
        else:
            bitstream_path = repl.projectDir / file

        if bitstream_path.suffix != ".bin":
            raise InvalidFileType(
                "No bitstream file specified. "
                "Usage: run_simulation <format> <bitstream_file>"
            )

        if not bitstream_path.exists():
            raise FileNotFoundError(
                f"Cannot find {bitstream_path} file which is generated by running "
                "compile_design. Potentially the bitstream generation failed."
            )

        test_path = repl.projectDir / "Test"
        taskfile = test_path / "Taskfile.yml"
        makefile = test_path / "Makefile"

        design_name = design or bitstream_path.stem

        # Prepare build directory and convert .bin to .hex for simulation
        build_dir = test_path / "build"
        build_dir.mkdir(parents=True, exist_ok=True)
        hex_path = build_dir / f"{design_name}.hex"
        make_hex(bitstream_path, hex_path)
        logger.info(f"Converted {bitstream_path} to {hex_path}")

        task_vars = {
            "WAVEFORM_TYPE": output_format,
            "DESIGN": design_name,
            "BITSTREAM_BIN": str(bitstream_path.resolve()),
        }
        if simulator:
            task_vars["SIMULATOR"] = simulator
        if extra_iverilog_flag:
            task_vars["EXTRA_IVERILOG_FLAGS"] = extra_iverilog_flag
        if extra_nvc_flag:
            task_vars["EXTRA_NVC_FLAGS"] = extra_nvc_flag
        if extra_ghdl_flag:
            task_vars["EXTRA_GHDL_FLAGS"] = extra_ghdl_flag

        if gl:
            if repl.extension == "vhdl":
                raise InvalidFileType(
                    "Gate-level simulation is Verilog-only: the hardened netlists "
                    "and PDK cell models are Verilog, which nvc/ghdl cannot "
                    "co-simulate with a VHDL wrapper."
                )
            if not taskfile.exists():
                raise FileNotFoundError(
                    f"No Taskfile.yml found in {test_path}. Gate-level simulation "
                    "requires the Taskfile flow."
                )
            gl_sources = collect_gl_sources(repl.projectDir, gl_sim_libs or [])
            task_vars["GL_SOURCES"] = " ".join(str(p) for p in gl_sources)
            logger.info(f"Running gate-level simulation for {design_name} via Taskfile")
            run_task(
                "run-gl-simulation",
                task_dir=test_path,
                task_vars=task_vars,
                verbose=repl.verbose or repl.debug,
            )
            logger.info("Gate-level simulation finished")
            return

        if taskfile.exists():
            logger.info(f"Running simulation for {design_name} via Taskfile")
            run_task(
                "run-simulation",
                task_dir=test_path,
                task_vars=task_vars,
                verbose=repl.verbose or repl.debug,
            )
        elif makefile.exists():
            logger.warning(
                "Taskfile.yml not found, falling back to Makefile. "
                "Makefiles are deprecated and will be removed in the next release. "
                "Please migrate to Taskfile.yml."
            )
            make_cmd = ["make", "-C", str(test_path), "run_simulation"]
            if repl.verbose or repl.debug:
                logger.info(f"Running command: {' '.join(make_cmd)}")
            sp.run(make_cmd, check=True)
        else:
            raise FileNotFoundError(
                f"No Taskfile.yml or Makefile found in {test_path}. "
                "Please ensure the project Test directory is set up correctly."
            )

        logger.info("Simulation finished")

"""FABulous command-line interface entry point.

This module provides the main entry point for the FABulous FPGA framework command-line
interface. It handles argument parsing, project setup, and CLI initialization.
"""

import platform
import sys
from importlib.metadata import version
from pathlib import Path
from typing import Annotated

import click
import typer
from loguru import logger
from packaging.version import Version

from fabulous.custom_exception import PipelineCommandError
from fabulous.fabric_definition.define import HDLType
from fabulous.fabulous_cli import FABulous_CLI
from fabulous.fabulous_cli.helper import (
    CommandPipeline,
    create_project,
    install_fabulator,
    install_oss_cad_suite,
    setup_logger,
    update_project_version,
)
from fabulous.fabulous_settings import (
    FAB_USER_CONFIG_DIR,
    get_context,
    init_context,
)

APP_NAME = "FABulous"

app = typer.Typer(
    rich_markup_mode="rich",
    help=(
        "[bold blue]FABulous FPGA Fabric Generator[/bold blue]\n\n"
        "A command line interface for FABulous FPGA fabric generation and management."
    ),
    no_args_is_help=True,
)


def version_callback(value: bool) -> None:
    """Print version information and exit."""
    if value:
        package_version = Version(version("FABulous-FPGA"))
        typer.echo(f"FABulous CLI {package_version.base_version}")
        raise typer.Exit


def validate_project_directory(value: str) -> Path | None:
    """Validate the project directory."""
    if not (Path(value) / ".FABulous").exists():
        raise ValueError(f"{value} is not a valid FABulous project")
    return Path(value)


ProjectDirType = Annotated[
    Path | None,
    typer.Option(
        "--project-dir",
        "-p",
        help="Directory path to project folder",
        parser=validate_project_directory,
        resolve_path=True,
        exists=True,
    ),
]

WriterType = Annotated[
    HDLType,
    typer.Option(
        "--writer",
        "-w",
        help="Set type of HDL code generated. System Verilog is not supported yet.",
        case_sensitive=False,
    ),
]

ForceType = Annotated[bool, typer.Option("--force", help="Enable force mode")]


GLOBAL_FLAGS = {
    "--verbose",
    "-v",
    "--debug",
    "--log",
    "--global-dot-env",
    "-gde",
    "--project-dot-env",
    "-pde",
}


def reorder_options(argv: list[str]) -> list[str]:
    """Reorder global flags to be before subcommands.

    Rules:
    - Only flags whose (base) token (before any '=') is in GLOBAL_FLAGS are moved.
    - Supports both --opt=value and --opt value forms (second handled heuristically:
      if the next token does not start with '-' it is treated as that flag's value).
    - Flags already before the subcommand are left untouched.
    - Order among moved flags is preserved relative to their appearance after
      the subcommand.
    - If no registered subcommand is present, argv is returned unchanged.
    """
    if (
        len(argv) == 2
        and Path(argv[1]).exists()
        and (Path(argv[1]) / ".FABulous").exists()
    ):
        return ["FABulous", "--project-dir", argv[1], "start"]

    if len(argv) < 3:
        return argv

    command_names = {c.name for c in app.registered_commands}

    # Find first subcommand occurrence
    cmd_index = None
    for i, tok in enumerate(argv[1:], start=1):
        if tok in command_names:
            cmd_index = i
            break
    if cmd_index is None:
        return argv  # No subcommand -> nothing to reorder

    before = argv[:cmd_index]  # program + any already-leading global flags
    command = argv[cmd_index]
    after = argv[cmd_index + 1 :]

    moved: list[str] = []
    remaining: list[str] = []
    i = 0

    while i < len(after):
        tok = after[i]
        base = tok.split("=", 1)[0] if tok.startswith("--") else tok
        if base in GLOBAL_FLAGS:
            # Move the flag
            moved.append(tok)
            # If value is separated (no '=' and next token not an option),
            # treat as value
            if "=" not in tok and (i + 1) < len(after):
                nxt = after[i + 1]
                if not nxt.startswith("-"):
                    moved.append(nxt)
                    i += 1
        else:
            remaining.append(tok)
        i += 1

    if not moved:
        return argv

    return before + moved + [command] + remaining


@app.callback()
def common_options(
    ctx: typer.Context,
    project_dir: ProjectDirType = None,
    _version: Annotated[
        bool | None,
        typer.Option(
            "--version",
            help="Show version information",
            callback=version_callback,
            is_eager=True,
        ),
    ] = None,
    verbose: Annotated[
        int,
        typer.Option(
            "--verbose",
            "-v",
            count=True,
            help="Show detailed log information",
        ),
    ] = 0,
    debug: Annotated[
        bool | None,
        typer.Option(
            "--debug/--no-debug", help="Enable/disable debug mode", envvar="FAB_DEBUG"
        ),
    ] = None,
    log_file: Annotated[
        Path | None, typer.Option("--log", help="Log all output to file")
    ] = None,
    global_dot_env: Annotated[
        Path | None,
        typer.Option("--global-dot-env", "-gde", help="Set global .env file path"),
    ] = None,
    project_dot_env: Annotated[
        Path | None,
        typer.Option("--project-dot-env", "-pde", help="Set project .env file path"),
    ] = None,
) -> None:
    """Provide common options for all FABulous commands."""
    setup_logger(
        verbose,
        debug or False,
        log_file=log_file or Path(),
    )

    if (s := ctx.invoked_subcommand) and (
        s.startswith("install") or s == "create-project" or s == "c"
    ):
        return

    if "--help" in sys.argv:
        return

    init_context(
        project_dir=project_dir or Path().cwd(),
        global_dot_env=global_dot_env,
        project_dot_env=project_dot_env,
    )


def check_version_compatibility(_: Path) -> None:
    """Check version compatibility between package and project."""
    settings = get_context()
    project_version = settings.proj_version
    package_version = Version(version("FABulous-FPGA"))

    if package_version.release < project_version.release:
        logger.error(
            f"Version incompatible! FABulous-FPGA version: {package_version}, "
            f"Project version: {project_version}\n"
            r'Please run "FABulous \<project_dir> --update-project-version" '
            r"to update the project version."
        )
        raise typer.Exit(1) from None

    if project_version.major != package_version.major:
        logger.error(
            f"Major version mismatch! FABulous-FPGA major version: "
            f"{package_version.major}, Project major version: {project_version.major}\n"
            "This may lead to compatibility issues. Please ensure the project is "
            "compatible with the current FABulous-FPGA version."
        )


@app.command("create-project")
@app.command("c", hidden=True)
def create_project_cmd(
    project_dir: Annotated[Path, typer.Argument(help="Directory to create a project")],
    writer: WriterType = HDLType.VERILOG,
    overwrite: bool = False,
) -> None:
    """Create a new FABulous project.

    Alias: c
    """
    if project_dir.exists() and not overwrite:
        delete_existing = typer.confirm(
            f"Project directory {project_dir} already exists. Overwrite?"
        )
        if not delete_existing:
            logger.info("Project creation cancelled.")
            raise typer.Exit(0)
    create_project(project_dir, writer)
    logger.info(f"FABulous project created successfully at {project_dir}")


@app.command("install-oss-cad-suite")
def install_oss_cad_suite_cmd(
    directory: Annotated[
        Path | None, typer.Argument(help="Directory to install oss-cad-suite in")
    ] = None,
) -> None:
    """Install the oss-cad-suite in the specified directory.

    This will create a new directory called oss-cad-suite and install the suite there.
    If the directory already exists, it will be replaced. This also automatically adds
    the FAB_OSS_CAD_SUITE env var in the global FABulous .env file.
    """
    if directory is None:
        directory = FAB_USER_CONFIG_DIR

    install_oss_cad_suite(directory)
    logger.info(f"oss-cad-suite installed successfully at {directory}")


@app.command("install-fabulator")
def install_fabulator_cmd(
    directory: Annotated[
        Path | None, typer.Argument(help="Directory to install FABulator in")
    ] = None,
) -> None:
    """Install FABulator in the specified directory.

    This will create a new directory FABulator and install the suite there. If the
    directory already exists, it will be replaced. This also automatically adds the
    FABULATOR_ROOT env var in the global FABulous .env file.
    """
    if directory is None:
        directory = FAB_USER_CONFIG_DIR

    install_fabulator(directory)

    logger.info(f"FABulator installed successfully at {directory}")


@app.command("install-nix")
def install_nix_cmd() -> None:
    """Install Nix."""
    import shutil
    import subprocess

    if which := shutil.which("nix"):
        logger.warning(
            f"Nix is already installed at {which}, skipping installation."
            "Please follow the docs to setup the nix cache!"
        )
        return

    try:
        subprocess.run(
            "curl -L https://nixos.org/nix/install | sh", shell=True, check=True
        )
        logger.info("Nix installed successfully")
        config_path = Path().home() / ".config" / "nix" / "nix.conf"
        if (not config_path.exists()) or (
            config_path.exists() and (config_path.stat().st_size == 0)
        ):
            config_path.parent.mkdir(parents=True, exist_ok=True)
            config_path.write_text(
                "extra-experimental-features = nix-command flakes\n"
                "extra-substituters = https://nix-cache.fossi-foundation.org\n"
                "extra-trusted-public-keys = nix-cache.fossi-foundation.org:"
                "3+K59iFwXqKsL7BNu6Guy0v+uTlwsxYQxjspXzqLYQs="
            )
            logger.info("Nix binary cache configured successfully")
        else:
            logger.warning(
                f"Nix config file {config_path} already exists and is not empty, "
                "skipping binary cache configuration"
            )
    except subprocess.CalledProcessError as e:
        logger.error(f"Failed to install Nix: {e}")
        raise typer.Exit(1) from None


@app.command("update-project-version")
def update_project_version_cmd() -> None:
    """Update project version to match package version."""
    logger.info(f"Using {get_context().proj_dir} directory as project directory")
    if not update_project_version(get_context().proj_dir):
        logger.error(
            "Failed to update project version. Please check the logs for more details."
        )
        raise typer.Exit(1)
    logger.info("Project version updated successfully")


@app.command("script")
def script_cmd(
    script_file: Annotated[
        Path,
        typer.Argument(
            help="Script file to execute",
            resolve_path=True,
            exists=True,
            dir_okay=False,
        ),
    ],
    script_type: Annotated[
        str,
        typer.Option(
            "--type",
            "-t",
            help="Override script type detection",
            click_type=click.Choice(["fabulous", "tcl"]),
        ),
    ] = "tcl",
    force: ForceType = False,
) -> None:
    """Execute a script file with auto-detection of script type.

    Automatically detects whether the script is a FABulous (.fab, .fs) or TCL (.tcl)
    script based on file extension and content. You can override the detection with
    --type.

    If no project directory is specified, uses the current directory.
    """
    # Initialize context
    script_file = script_file.absolute()
    fab_CLI = FABulous_CLI(
        writerType=get_context().proj_lang,
        force=force,
        debug=get_context().debug,
    )
    # Change to project directory

    # Try to load fabric, but don't fail if it's not a valid FABulous project
    fab_CLI.onecmd_plus_hooks("load_fabric")

    # Check if script file exists before trying to execute
    if not script_file.exists():
        logger.error(f"Script file {script_file} does not exist")
        raise typer.Exit(1)

    # Execute the script based on type
    if (
        script_file.suffix.lower() in [".fab", ".fs"] and script_type is None
    ) or script_type == "fabulous":
        fab_CLI.onecmd_plus_hooks(f"run_script {script_file.absolute()}")
        if fab_CLI.exit_code:
            logger.error(
                f"FABulous script {script_file} execution failed with "
                f"exit code {fab_CLI.exit_code}"
            )
            raise typer.Exit(fab_CLI.exit_code)
        logger.info(f"FABulous script {script_file} executed successfully")
    elif (
        script_file.suffix.lower() == ".tcl" and script_type is None
    ) or script_type == "tcl":
        fab_CLI.onecmd_plus_hooks(f"run_tcl {script_file.absolute()}")
        if fab_CLI.exit_code:
            logger.error(
                f"TCL script {script_file} execution failed with "
                f"exit code {fab_CLI.exit_code}"
            )
            raise typer.Exit(fab_CLI.exit_code)
        logger.info(f"TCL script {script_file} executed successfully")
    else:
        logger.error(f"Unknown script type: {script_type}")
        raise typer.Exit(1)


@app.command("start")
@app.command("s", hidden=True)
def start_cmd(force: ForceType = False) -> None:
    """Start FABulous in interactive mode. Alias: s.

    This is the main command for running FABulous in interactive mode or with scripts.
    If no project directory is specified, uses the current directory.
    """
    fab_CLI = FABulous_CLI(
        get_context().proj_lang,
        force=force,
        interactive=True,
        verbose=get_context().verbose >= 2,
        debug=get_context().debug,
    )
    fab_CLI.onecmd_plus_hooks("load_fabric")
    fab_CLI.cmdloop()


@app.command("run")
@app.command("r", hidden=True)
def run_cmd(
    commands: Annotated[
        list[str] | None,
        typer.Argument(
            help=(
                "Commands to execute (separated by semicolon + whitespace: "
                "'cmd1; cmd2')"
            ),
            parser=lambda cmds: [
                cmd.strip() for cmd in cmds.split("; ") if cmd.strip()
            ],
            callback=lambda cmds: cmds[0] if cmds else None,
        ),
    ] = None,
    force: ForceType = False,
) -> None:
    """Run commands directly in a FABulous project.

    Alias: r
    """
    fab_CLI = FABulous_CLI(
        get_context().proj_lang,
        force=force,
        interactive=True,
        verbose=get_context().verbose >= 2,
        debug=get_context().debug,
    )

    # Change to project directory
    logger.info(f"Setting current working directory to: {get_context().proj_dir}")
    fab_CLI.onecmd_plus_hooks("load_fabric")
    # Ensure commands is a list
    if isinstance(commands, str):
        commands = [commands]
    if commands is None or commands == [""] or commands == []:
        logger.warning("No commands provided, exiting")
        return

    # Create and execute command pipeline
    pipeline = CommandPipeline(fab_CLI, force=force)

    # Add all commands to pipeline
    for cmd in commands:
        pipeline.add_step(cmd, f"Command '{cmd}' execution failed")

    try:
        # Execute pipeline
        success = pipeline.execute()

        if success:
            logger.info(f'Commands "{"; ".join(commands)}" executed successfully')
        else:
            logger.error(
                f"Commands completed with errors (exit code {pipeline.get_exit_code()})"
            )

    except PipelineCommandError:
        # Handle any pipeline errors that weren't caught by force flag
        # Don't log additional error message as CommandPipeline already logged it
        raise typer.Exit(1) from None

    # Always report the final exit code, even with --force
    final_exit_code = pipeline.get_exit_code()
    if final_exit_code != 0:
        raise typer.Exit(final_exit_code)


def main() -> None:
    """Entry point for the application."""
    # Check for Windows and show warning (before any command processing)
    if platform.system() == "Windows":
        from pydantic_settings import BaseSettings, SettingsConfigDict

        # Always show warning for Windows systems
        logger.warning(
            "FABulous is not officially supported on native Windows. "
            "You are using it at your own risk - errors may occur.\n"
            "For the best experience, please use Windows Subsystem for Linux (WSL).\n"
            "For more information, visit: https://docs.microsoft.com/en-us/windows/wsl/install"
        )

        # Since the init_context of FABulousSettings context happens
        # only on actual command execution, but we want this to be executed
        # for every run on Windows, we create a minimal settings here,
        # to check if the user has already acknowledged the warning.
        class MinimalSettings(BaseSettings):
            model_config = SettingsConfigDict(
                env_prefix="FAB_",
                case_sensitive=False,
                env_file=str(FAB_USER_CONFIG_DIR / ".env"),
                env_file_encoding="utf-8",
            )
            windows_warning_acknowledged: bool = False

        settings = MinimalSettings()

        if not settings.windows_warning_acknowledged:
            # Ask user if they want to continue
            continue_anyway = typer.confirm(
                "Do you want to continue anyway?", default=False
            )

            if not continue_anyway:
                logger.info("Exiting. Please use WSL for the best experience.")
                sys.exit(0)

            # Ask if they want to remember this choice
            remember = typer.confirm(
                "Do you want to remember this choice? (Will be saved to global .env)",
                default=True,
            )

            if remember:
                from fabulous.fabulous_settings import add_var_to_global_env

                add_var_to_global_env("FAB_WINDOWS_WARNING_ACKNOWLEDGED", "true")
                logger.info(
                    "Choice saved. You won't be prompted again, "
                    "but the warning will still be shown."
                )

    try:
        if len(sys.argv) == 1:
            app()
        sys.argv = reorder_options(sys.argv)
        for i in sys.argv[1:]:
            if i in [i.name for i in app.registered_commands] or i == "--help":
                app()
                break
        else:
            convert_legacy_args_with_deprecation_warning()
    except typer.Exit as e:
        sys.exit(e.exit_code)
    except Exception as e:  # noqa: BLE001 General overall capture
        logger.error(f"Unexpected error: {e}")
        sys.exit(1)


def convert_legacy_args_with_deprecation_warning() -> None:
    """Convert legacy argparse arguments to new Typer commands."""
    import argparse
    import sys
    from pathlib import Path

    parser = argparse.ArgumentParser(
        description="The command line interface for FABulous"
    )

    create_group = parser.add_mutually_exclusive_group()

    create_group.add_argument(
        "-c",
        "--createProject",
        default=False,
        action="store_true",
        help="Create a new project",
    )

    create_group.add_argument(
        "-iocs",
        "--install_oss_cad_suite",
        help=(
            "Install the oss-cad-suite in the directory."
            "This will create a new directory called oss-cad-suite in the provided "
            "directory and install the oss-cad-suite there."
            "If there is already a directory called oss-cad-suite, it will be removed "
            "and replaced with a new one."
            "This will also automatically add the FAB_OSS_CAD_SUITE env var in the "
            "global FABulous .env file. "
        ),
        action="store_true",
        default=False,
    )

    script_group = parser.add_mutually_exclusive_group()

    parser.add_argument(
        "project_dir",
        default="",
        nargs="?",
        help="The directory to the project folder",
    )

    script_group.add_argument(
        "-fs",
        "--FABulousScript",
        default=None,
        help=(
            "Run FABulous with a FABulous script. A FABulous script is a text file "
            "containing only FABulous commands. This will automatically exit the CLI "
            "once the command finish execution, and the exit will always happen "
            "gracefully."
        ),
        type=Path,
    )

    script_group.add_argument(
        "-ts",
        "--TCLScript",
        default=None,
        help=(
            "Run FABulous with a TCL script. A TCL script is a text file containing "
            "a mix of TCL commands and FABulous commands. This will automatically exit "
            "the CLI once the command finish execution, and the exit will always happen"
            "gracefully."
        ),
        type=Path,
    )

    script_group.add_argument(
        "-p",
        "--commands",
        type=str,
        help=(
            "execute <commands> (to chain commands, separate them with semicolon + "
            "whitespace: 'cmd1; cmd2')"
        ),
    )

    parser.add_argument(
        "-log",
        default="",
        type=Path,
        nargs="?",
        const="FABulous.log",
        help="Log all the output from the terminal",
    )

    parser.add_argument(
        "-w",
        "--writer",
        choices=["verilog", "vhdl"],
        type=lambda s: s.lower(),
        help=(
            "Set the type of HDL code generated by the tool. Currently support Verilog "
            "and VHDL (Default using Verilog)"
        ),
        default="verilog",
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
        help=(
            "Show detailed log information including function and line number. For -vv "
            "additionally output from FABulator is logged to the shell for the "
            "start_FABulator command"
        ),
    )

    parser.add_argument(
        "-gde",
        "--globalDotEnv",
        help="Set the global .env file path. Default is ~/.config/FABulous/.env",
        type=Path,
    )

    parser.add_argument(
        "-pde",
        "--projectDotEnv",
        help="Set the project .env file path. Default is $FAB_PROJ_DIR/.env",
        type=Path,
    )

    parser.add_argument(
        "--force",
        action="store_true",
        help=(
            "Force the command to run and ignore any errors. This feature does not "
            "work for the TCLScript argument"
        ),
    )

    parser.add_argument("--debug", action="store_true", help="Enable debug mode")

    parser.add_argument(
        "--version",
        action="version",
        version=f"FABulous CLI {Version(version('FABulous-FPGA')).base_version}",
    )

    parser.add_argument(
        "--update-project-version",
        action="store_true",
        help="Update the project version to match the FABulous package version",
    )

    args = parser.parse_args()

    setup_logger(args.verbose, args.debug, log_file=args.log)

    # Show deprecation warning
    logger.warning(
        "You are using deprecated argparse-style arguments. "
        "Please migrate to the new typer-based commands:\n"
        r"  FABulous --createProject \<dir> → FABulous create-project \<dir>"
        "\n"
        r"  FABulous --install_oss_cad_suite → FABulous install-oss-cad-suite \<dir>"
        "\n"
        r"  FABulous \<project_dir> --commands \<cmd> → FABulous -p \<project_dir> run "
        r"\<cmd>"
        "\n"
        r"  FABulous \<project_dir>  → FABulous -p \<project_dir> start"
        "\n"
        r"  FABulous \<project_dir> --debug  → FABulous --debug start \<project_dir>"
        "\n"
        "  See 'FABulous --help' for more information."
    )

    project_dir = Path(args.project_dir).resolve().absolute()

    if args.createProject:
        # Convert to: FABulous create-project <project_dir>
        if not args.project_dir:
            logger.error("Project directory is required when creating a project")
            raise typer.Exit(2) from None
        create_project_cmd(project_dir, HDLType[args.writer.upper()])
        sys.exit(0)

    if args.install_oss_cad_suite:
        # Convert to: FABulous install-oss-cad-suite <directory> [options]
        install_oss_cad_suite_cmd(project_dir)
        sys.exit(0)

    common_options(
        ctx=typer.Context(click.Command("legacy_args")),
        project_dir=project_dir if args.project_dir else None,
        verbose=args.verbose,
        debug=args.debug,
        log_file=args.log,
        global_dot_env=args.globalDotEnv,
        project_dot_env=args.projectDotEnv,
    )
    if args.update_project_version:
        update_project_version_cmd(project_dir)
    elif args.FABulousScript:
        # Convert legacy --FABulousScript to new typer script command
        # Use the new Typer script command internally
        # Pass None when no project directory provided to trigger dotenv resolution
        try:
            script_cmd(
                script_file=args.FABulousScript,
                script_type="fabulous",
                force=args.force,
            )
        except typer.Exit as e:
            sys.exit(e.exit_code)
    elif args.TCLScript:
        # Convert legacy --TCLScript to new typer script command
        # Use the new Typer script command internally
        # Pass None when no project directory provided to trigger dotenv resolution
        try:
            script_cmd(
                script_file=args.TCLScript,
                script_type="tcl",
                force=args.force,
            )
        except typer.Exit as e:
            sys.exit(e.exit_code)
    elif args.commands is not None:
        # Convert legacy --commands to new typer run command
        # Parse commands first to handle empty case
        parsed_commands = [
            cmd.strip() for cmd in args.commands.split("; ") if cmd.strip()
        ]

        # Handle empty commands case - exit gracefully
        if not parsed_commands:
            logger.info("No commands provided, exiting")
            sys.exit(0)

        # Use the new Typer run command internally
        # Pass None when no project directory provided to trigger dotenv resolution
        try:
            run_cmd(
                commands=parsed_commands,
                force=args.force,
            )
        except typer.Exit as e:
            sys.exit(e.exit_code)
    else:
        # Convert legacy start to new typer start command
        # Use the new Typer start command internally
        # Pass None when no project directory provided to trigger dotenv resolution
        try:
            start_cmd(force=args.force)
        except typer.Exit as e:
            sys.exit(e.exit_code)

    sys.exit(0)


if __name__ == "__main__":
    main()

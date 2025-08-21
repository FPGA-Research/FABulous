import os
import sys
from dataclasses import dataclass
from importlib.metadata import version
from pathlib import Path
from typing import Annotated, Literal, cast

import click
import typer
from loguru import logger
from packaging.version import Version

from FABulous.custom_exception import PipelineCommandError
from FABulous.fabric_definition.define import HDLType
from FABulous.FABulous_CLI import FABulous_CLI
from FABulous.FABulous_CLI.helper import (
    CommandPipeline,
    create_project,
    install_oss_cad_suite,
    setup_logger,
    update_project_version,
)
from FABulous.FABulous_settings import get_context, init_context

APP_NAME = "FABulous"

app = typer.Typer(
    rich_markup_mode="rich",
    help="[bold blue]FABulous FPGA Fabric Generator[/bold blue]\n\nA command line interface for FABulous FPGA fabric generation and management.",
    no_args_is_help=True,
)


@dataclass
class SharedContext:
    """Context object to hold shared CLI options."""

    verbose: int = 0
    debug: bool = False
    log_file: Path | None = None
    global_dot_env: Path | None = None
    project_dot_env: Path | None = None
    force: bool = False
    writer: str = "verilog"


shared_state = SharedContext()


def version_callback(value: bool) -> None:
    """Print version information and exit."""
    if value:
        package_version = Version(version("FABulous-FPGA"))
        typer.echo(f"FABulous CLI {package_version.base_version}")
        raise typer.Exit


def validate_project_directory(raw_project_dir: str | Path) -> Path:
    """Validate that the project directory exists and is a valid FABulous project."""
    project_dir = Path(raw_project_dir)

    if (project_dir / ".FABulous").exists():
        return project_dir

    logger.error(
        "The directory provided or current directory is not a FABulous project"
        "as it does not have a .FABulous folder"
    )
    raise typer.Exit(1) from None


ProjectDirType = Annotated[
    Path,
    typer.Argument(
        help="Directory path to project folder",
        parser=validate_project_directory,
        callback=lambda v: logger.info(f"Setting current working directory to: {v}"),
        resolve_path=True,
        exists=True,
    ),
]


@app.callback()
def common_options(
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
            "--verbose", "-v", count=True, help="Show detailed log information"
        ),
    ] = 0,
    debug: Annotated[bool, typer.Option("--debug", help="Enable debug mode")] = False,
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
    force: Annotated[
        bool, typer.Option("--force", help="Force command execution and ignore errors")
    ] = False,
    writer: Annotated[
        HDLType,
        typer.Option(
            "--writer",
            "-w",
            help="Set type of HDL code generated",
            case_sensitive=False,
        ),
    ] = HDLType.VERILOG,
) -> None:
    """Common options for all FABulous commands."""

    shared_state.verbose = verbose
    shared_state.debug = debug
    shared_state.log_file = log_file
    shared_state.global_dot_env = global_dot_env
    shared_state.project_dot_env = project_dot_env
    shared_state.force = force
    shared_state.writer = writer
    setup_logger(
        shared_state.verbose,
        shared_state.debug,
        log_file=shared_state.log_file or Path(),
    )


def check_version_compatibility(_: Path) -> None:
    """Check version compatibility between package and project."""
    settings = get_context()
    project_version = settings.proj_version
    package_version = Version(version("FABulous-FPGA"))

    if package_version.release < project_version.release:
        logger.error(
            f"Version incompatible! FABulous-FPGA version: {package_version}, Project version: {project_version}\n"
            r'Please run "FABulous <project_dir> --update-project-version" to update the project version.'
        )
        raise typer.Exit(1) from None

    if project_version.major != package_version.major:
        logger.error(
            f"Major version mismatch! FABulous-FPGA major version: {package_version.major}, Project major version: {project_version.major}\n"
            "This may lead to compatibility issues. Please ensure the project is compatible with the current FABulous-FPGA version."
        )


@app.command("create-project")
@app.command("c", hidden=True)
def create_project_cmd(
    project_dir: Annotated[
        Path, typer.Argument(help="Directory to create a project")
    ] = Path(),
) -> None:
    """Create a new FABulous project.

    Alias: c
    """
    try:
        init_context(None)
        create_project(
            project_dir, cast("Literal['verilog', 'vhdl']", shared_state.writer)
        )
        logger.info(f"FABulous project created successfully at {project_dir}")
    except Exception as e:
        logger.error(f"Failed to create FABulous project: {e}")
        raise typer.Exit(1) from e


@app.command("install-oss-cad-suite")
def install_oss_cad_suite_cmd(
    directory: Annotated[
        Path, typer.Argument(help="Directory to install oss-cad-suite in")
    ],
) -> None:
    """Install the oss-cad-suite in the specified directory.

    This will create a new directory called oss-cad-suite and install the suite there.
    If the directory already exists, it will be replaced. This also automatically adds
    the FAB_OSS_CAD_SUITE env var in the global FABulous .env file.
    """

    try:
        init_context(None)
        install_oss_cad_suite(directory)
        logger.info(f"oss-cad-suite installed successfully at {directory}")
    except Exception as e:
        logger.error(f"Failed to install oss-cad-suite: {e}")
        raise typer.Exit(1) from e


@app.command("update-project-version")
def update_project_version_cmd(
    project_dir: ProjectDirType = Path(),
) -> None:
    """Update project version to match package version."""

    logger.info(f"Using {project_dir} directory as project directory")
    if not update_project_version(project_dir):
        logger.error(
            "Failed to update project version. Please check the logs for more details."
        )
        raise typer.Exit(1) from None
    logger.info("Project version updated successfully")


@app.command("script")
def script_cmd(
    project_dir: ProjectDirType = Path(),
    script_file: Annotated[
        Path, typer.Argument(help="Script file to execute", resolve_path=True)
    ] = Path(),
    script_type: Annotated[
        str,
        typer.Option(
            "--type",
            "-t",
            help="Override script type detection",
            click_type=click.Choice(["fabulous", "tcl"]),
        ),
    ] = "tcl",
) -> None:
    """Execute a script file with auto-detection of script type.

    Automatically detects whether the script is a FABulous (.fab, .fs) or TCL (.tcl)
    script based on file extension and content. You can override the detection with
    --type.

    If no project directory is specified, uses the current directory.
    """
    # Initialize context
    entering_dir = Path.cwd()
    os.chdir(project_dir)
    init_context(
        project_dir=project_dir,
        global_dot_env=shared_state.global_dot_env,
        project_dot_env=shared_state.project_dot_env,
    )
    fab_CLI = FABulous_CLI(
        shared_state.writer,
        project_dir,
        force=shared_state.force,
    )
    fab_CLI.debug = shared_state.debug
    # Change to project directory

    # Try to load fabric, but don't fail if it's not a valid FABulous project
    fab_CLI.onecmd_plus_hooks("load_fabric")

    # Check if script file exists before trying to execute
    if not script_file.exists():
        logger.error(f"Script file {script_file} does not exist")
        os.chdir(entering_dir)
        sys.exit(1)

    # Execute the script based on type
    if (
        script_file.suffix.lower() in [".fab", ".fs"] and script_type is None
    ) or script_type == "fabulous":
        fab_CLI.onecmd_plus_hooks(f"run_script {script_file.absolute()}")
        if fab_CLI.exit_code:
            logger.error(
                f"FABulous script {script_file} execution failed with exit code {fab_CLI.exit_code}"
            )
            os.chdir(entering_dir)
            sys.exit(fab_CLI.exit_code)
        else:
            logger.info(f"FABulous script {script_file} executed successfully")
    elif (
        script_file.suffix.lower() == ".tcl" and script_type is None
    ) or script_type == "tcl":
        fab_CLI.onecmd_plus_hooks(f"run_tcl {script_file.absolute()}")
        if fab_CLI.exit_code:
            logger.error(
                f"TCL script {script_file} execution failed with exit code {fab_CLI.exit_code}"
            )
            os.chdir(entering_dir)
            sys.exit(fab_CLI.exit_code)
        else:
            logger.info(f"TCL script {script_file} executed successfully")
    else:
        os.chdir(entering_dir)
        logger.error(f"Unknown script type: {script_type}")
        sys.exit(1)


@app.command("start")
def start_cmd(project_dir: ProjectDirType = Path()) -> None:
    """Run FABulous with the specified project and options.

    This is the main command for running FABulous in interactive mode or with scripts.
    If no project directory is specified, uses the current directory.
    """

    # Initialize the global context with settings
    settings = init_context(
        project_dir=project_dir,
        global_dot_env=shared_state.global_dot_env,
        project_dot_env=shared_state.project_dot_env,
    )
    entering_dir = Path.cwd()
    fab_CLI = FABulous_CLI(
        settings.proj_lang,
        project_dir,
        force=shared_state.force,
        interactive=True,
        verbose=shared_state.verbose >= 2,
        debug=shared_state.debug,
    )
    fab_CLI.debug = shared_state.debug

    # Change to project directory
    os.chdir(project_dir)
    fab_CLI.onecmd_plus_hooks("load_fabric")
    fab_CLI.cmdloop()
    os.chdir(entering_dir)


@app.command("run")
def run_cmd(
    project_dir: ProjectDirType = Path(),
    commands: Annotated[
        list[str] | None,
        typer.Argument(
            help="Commands to execute (separated by semicolon + whitespace: 'cmd1; cmd2')",
            parser=lambda cmds: [
                cmd.strip() for cmd in cmds.split("; ") if cmd.strip()
            ],
        ),
    ] = None,
) -> None:
    settings = init_context(
        project_dir=project_dir,
        global_dot_env=shared_state.global_dot_env,
        project_dot_env=shared_state.project_dot_env,
    )
    entering_dir = Path.cwd()

    fab_CLI = FABulous_CLI(
        settings.proj_lang,
        project_dir,
        force=shared_state.force,
        interactive=True,
        verbose=shared_state.verbose >= 2,
        debug=shared_state.debug,
    )
    fab_CLI.debug = shared_state.debug

    # Change to project directory
    logger.info(f"Setting current working directory to: {project_dir}")
    os.chdir(project_dir)
    fab_CLI.onecmd_plus_hooks("load_fabric")

    # Ensure commands is a list
    if isinstance(commands, str):
        commands = [commands]
    if commands is None:
        return

    # Create and execute command pipeline
    pipeline = CommandPipeline(fab_CLI, force=shared_state.force)

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
        os.chdir(entering_dir)
        raise typer.Exit(1) from None

    os.chdir(entering_dir)

    # Always report the final exit code, even with --force
    final_exit_code = pipeline.get_exit_code()
    if final_exit_code != 0:
        raise typer.Exit(final_exit_code)


def main() -> None:
    if sys.argv[1] not in [i.name for i in app.registered_commands]:
        # Convert legacy arguments to new typer command format with deprecation warning
        convert_legacy_args_with_deprecation_warning()
    else:
        # Use the new Typer interface
        app()


def convert_legacy_args_with_deprecation_warning() -> None:
    """Convert legacy argparse arguments to new Typer commands with deprecation
    warning."""
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
        help="Install the oss-cad-suite in the directory."
        "This will create a new directory called oss-cad-suite in the provided"
        "directory and install the oss-cad-suite there."
        "If there is already a directory called oss-cad-suite, it will be removed and replaced with a new one."
        "This will also automatically add the FAB_OSS_CAD_SUITE env var in the global FABulous .env file. ",
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
        help="Run FABulous with a FABulous script. A FABulous script is a text file containing only FABulous commands"
        "This will automatically exit the CLI once the command finish execution, and the exit will always happen gracefully.",
        type=Path,
    )

    script_group.add_argument(
        "-ts",
        "--TCLScript",
        default=None,
        help="Run FABulous with a TCL script. A TCL script is a text file containing a mix of TCL commands and FABulous commands."
        "This will automatically exit the CLI once the command finish execution, and the exit will always happen gracefully.",
        type=Path,
    )

    script_group.add_argument(
        "-p",
        "--commands",
        type=str,
        help="execute <commands> (to chain commands, separate them with semicolon + whitespace: 'cmd1; cmd2')",
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
        choices=list(HDLType),
        help="Set the type of HDL code generated by the tool. Currently support Verilog and VHDL (Default using Verilog)",
        default=HDLType.VERILOG,
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
        help="Set the global .env file path. Default is $FAB_ROOT/.env",
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
        help="Force the command to run and ignore any errors. This feature does not work for the TCLScript argument",
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

    common_options(
        verbose=args.verbose,
        debug=args.debug,
        log_file=args.log,
        global_dot_env=args.globalDotEnv,
        project_dot_env=args.projectDotEnv,
        force=args.force,
        writer=args.writer if args.writer is not None else HDLType.VERILOG,
    )

    setup_logger(args.verbose, args.debug, log_file=args.log)

    # Show deprecation warning
    logger.warning(
        "You are using deprecated argparse-style arguments. "
        "Please migrate to the new typer-based commands:\n"
        r"  FABulous --createProject \<dir> → FABulous create-project \<dir>"
        "\n"
        r"  FABulous --install_oss_cad_suite → FABulous install-oss-cad-suite \<dir>"
        "\n"
        r"  FABulous \<project_dir> --commands \<cmd> → FABulous run \<project_dir> \<cmd>"
        "\n"
        r"  FABulous \<project_dir>  → FABulous start \<project_dir>"
        "\n"
        "  See 'FABulous --help' for more information."
    )

    project_dir = Path(args.project_dir).resolve().absolute()

    if args.createProject:
        # Convert to: FABulous create-project <project_dir>
        if not args.project_dir:
            logger.error("Project directory is required when creating a project")
            sys.exit(2)
        create_project_cmd(project_dir)

    elif args.install_oss_cad_suite:
        # Convert to: FABulous install-oss-cad-suite <directory> [options]
        install_oss_cad_suite_cmd(project_dir)
    elif args.update_project_version:
        update_project_version_cmd(project_dir)
    elif args.FABulousScript:
        # For FABulous scripts, allow running without a valid project directory
        # The script_cmd function will handle cases where no valid project exists
        if args.project_dir:
            # Only validate if a project directory was explicitly provided
            try:
                validated_project_dir = validate_project_directory(project_dir)
            except typer.Exit as e:
                sys.exit(e.exit_code)
        else:
            # Use current directory when no project directory is provided
            validated_project_dir = Path.cwd()
        script_cmd(validated_project_dir, args.FABulousScript, script_type="fabulous")
    elif args.TCLScript:
        # For TCL scripts, allow running without a valid project directory
        # The script_cmd function will handle cases where no valid project exists
        if args.project_dir:
            # Only validate if a project directory was explicitly provided
            try:
                validated_project_dir = validate_project_directory(project_dir)
            except typer.Exit as e:
                sys.exit(e.exit_code)
        else:
            # Use current directory when no project directory is provided
            validated_project_dir = Path.cwd()
        script_cmd(validated_project_dir, args.TCLScript, script_type="tcl")
    elif args.commands:
        # Validate project directory manually since we're bypassing Typer's validation
        try:
            validated_project_dir = validate_project_directory(project_dir)
        except typer.Exit as e:
            sys.exit(e.exit_code)
        # Parse commands manually since we're bypassing Typer's argument parsing
        parsed_commands = [
            cmd.strip() for cmd in args.commands.split("; ") if cmd.strip()
        ]
        run_cmd(
            project_dir=validated_project_dir,
            commands=parsed_commands,
        )
    else:
        # For legacy compatibility - if no project_dir specified, use current dir
        if args.project_dir:
            # Validate project directory manually since we're bypassing Typer's validation
            try:
                validated_project_dir = validate_project_directory(project_dir)
            except typer.Exit as e:
                sys.exit(e.exit_code)
            start_cmd(project_dir=validated_project_dir)
        else:
            start_cmd(project_dir=Path.cwd())

    sys.exit(0)


if __name__ == "__main__":
    main()

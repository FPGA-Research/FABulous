import os
from importlib.metadata import version
from pathlib import Path
from typing import Annotated, Literal

import click
import typer
from loguru import logger
from packaging.version import Version

from FABulous.FABulous_CLI.helper import (
    create_project,
    install_oss_cad_suite,
    setup_logger,
)
from FABulous.FABulous_settings import FABulousCliSettings

# Using direct parameter passing instead of global context for cleaner architecture

app = typer.Typer(
    rich_markup_mode="rich",
    help="[bold blue]FABulous FPGA Fabric Generator[/bold blue]\n\nA command line interface for FABulous FPGA fabric generation and management.",
    no_args_is_help=True,
)


def version_callback(value: bool) -> None:
    """Print version information and exit."""
    if value:
        package_version = Version(version("FABulous-FPGA"))
        typer.echo(f"FABulous CLI {package_version.base_version}")
        raise typer.Exit


# Simplified shared options - no callbacks needed, pass parameters directly
CommonVerbose = Annotated[
    int,
    typer.Option("--verbose", "-v", count=True, help="Show detailed log information"),
]
CommonDebug = Annotated[bool, typer.Option("--debug", help="Enable debug mode")]
CommonLogFile = Annotated[
    Path | None, typer.Option("--log", help="Log all output to file")
]
CommonForce = Annotated[
    bool, typer.Option("--force", help="Force command execution and ignore errors")
]
CommonWriter = Annotated[
    str | None, typer.Option("--writer", "-w", help="Set type of HDL code generated")
]
CommonGlobalDotEnv = Annotated[
    Path | None,
    typer.Option("--global-dot-env", "-gde", help="Set global .env file path"),
]
CommonProjectDotEnv = Annotated[
    Path | None,
    typer.Option("--project-dot-env", "-pde", help="Set project .env file path"),
]


def detect_script_type(script_path: Path) -> str:
    """Detect script type based on file extension and content."""
    # Check by file extension first
    suffix = script_path.suffix.lower()
    if suffix in [".fab", ".fs"]:
        return "fabulous"
    if suffix in [".tcl"]:
        return "tcl"

    return "fabulous"


def setup_environment_and_logging(
    project_dir: Path,
    global_dot_env: Path | None = None,
    project_dot_env: Path | None = None,
    verbose: int = 0,
    debug: bool = False,
    log_file: Path | None = None,
    writer: str | None = None,
) -> FABulousCliSettings:
    """Set up environment variables and logging configuration using Pydantic settings.

    Returns:
        FABulousCliSettings instance with all environment variables loaded
    """
    # Setup logger first
    setup_logger(verbose, debug, log_file=log_file or Path())

    # Create settings instance with custom .env file handling
    return FABulousCliSettings.create_with_env_files(
        project_dir=project_dir,
        global_dot_env=global_dot_env,
        project_dot_env=project_dot_env,
        verbose=verbose,
        debug=debug,
        log_file=log_file,
        force=False,  # Will be overridden by CLI args when needed
        writer=writer,
    )


def validate_project_directory(project_dir: Path) -> Path:
    """Validate that the project directory exists and is a valid FABulous project."""
    if not project_dir.exists():
        logger.error(f"The directory provided does not exist: {project_dir}")
        raise typer.Exit(1)

    if not (project_dir / ".FABulous").exists():
        logger.error(
            "The directory provided is not a FABulous project as it does not have a .FABulous folder"
        )
        raise typer.Exit(1)

    return project_dir


def check_version_compatibility(_: Path) -> None:
    """Check version compatibility between package and project."""
    from FABulous.FABulous_settings import FABulousSettings

    project_version = FABulousSettings().proj_version
    package_version = Version(version("FABulous-FPGA"))

    if package_version.release < project_version.release:
        logger.error(
            f"Version incompatible! FABulous-FPGA version: {package_version}, Project version: {project_version}\n"
            r'Please run "FABulous <project_dir> --update-project-version" to update the project version.'
        )
        raise typer.Exit(1)

    if project_version.major != package_version.major:
        logger.error(
            f"Major version mismatch! FABulous-FPGA major version: {package_version.major}, Project major version: {project_version.major}\n"
            "This may lead to compatibility issues. Please ensure the project is compatible with the current FABulous-FPGA version."
        )


@app.command(
    "create-project",
    help="Create a new FABulous project.",
    context_settings={"allow_extra_args": True, "ignore_unknown_options": True},
)
def create_project_cmd(
    project_dir: Annotated[
        Path, typer.Argument(help="Directory path to create the project in")
    ],
    writer: Annotated[
        str,
        typer.Option(
            "--writer",
            "-w",
            help="Set type of HDL code generated",
            click_type=click.Choice(["verilog", "vhdl"]),
        ),
    ] = "verilog",
    verbose: CommonVerbose = 0,
    debug: CommonDebug = False,
    log_file: CommonLogFile = None,
) -> None:
    """Create a new FABulous project."""
    setup_logger(verbose, debug, log_file=log_file or Path())

    project_dir = project_dir.absolute().resolve()
    # Type check for mypy - we know writer is valid due to typer.Choice constraint
    writer_typed: Literal["verilog", "vhdl"] = writer  # type: ignore
    create_project(project_dir, writer_typed)
    logger.info(f"Successfully created FABulous project at {project_dir}")


@app.command("install-oss-cad-suite")
def install_oss_cad_suite_cmd(
    directory: Annotated[
        Path, typer.Argument(help="Directory to install oss-cad-suite in")
    ],
    verbose: CommonVerbose = 0,
    debug: CommonDebug = False,
    log_file: CommonLogFile = None,
) -> None:
    """Install the oss-cad-suite in the specified directory.

    This will create a new directory called oss-cad-suite and install the suite there.
    If the directory already exists, it will be replaced. This also automatically adds
    the FAB_OSS_CAD_SUITE env var in the global FABulous .env file.
    """
    setup_logger(verbose, debug, log_file=log_file or Path())

    directory = directory.absolute().resolve()
    install_oss_cad_suite(directory, True)
    logger.info(f"Successfully installed oss-cad-suite at {directory}")


@app.command("script")
def script_cmd(
    project_dir: Annotated[
        Path, typer.Argument(help="Directory path to project folder")
    ],
    script_file: Annotated[Path, typer.Argument(help="Script file to execute")],
    script_type: Annotated[
        str | None,
        typer.Option(
            "--type", "-t", help="Override script type detection (fabulous|tcl)"
        ),
    ] = None,
    verbose: CommonVerbose = 0,
    debug: CommonDebug = False,
    log_file: CommonLogFile = None,
    global_dot_env: CommonGlobalDotEnv = None,
    project_dot_env: CommonProjectDotEnv = None,
    force: CommonForce = False,
    writer: CommonWriter = None,
    update_project_version: Annotated[
        bool,
        typer.Option(
            "--update-project-version",
            help="Update project version to match package version",
        ),
    ] = False,
    _version: Annotated[
        bool | None,
        typer.Option(
            "--version",
            callback=version_callback,
            is_eager=True,
            help="Show version and exit",
        ),
    ] = None,
) -> None:
    """Execute a script file with auto-detection of script type.

    Automatically detects whether the script is a FABulous (.fab, .fs) or TCL (.tcl)
    script based on file extension and content. You can override the detection with
    --type.
    """
    # Detect script type if not explicitly provided
    if script_type is None:
        script_type = detect_script_type(script_file)
        logger.info(f"Auto-detected script type: {script_type}")
    else:
        if script_type not in ["fabulous", "tcl"]:
            logger.error("Script type must be either 'fabulous' or 'tcl'")
            raise typer.Exit(1)
        logger.info(f"Using user-specified script type: {script_type}")

    # Setup logging using parameters
    setup_logger(verbose, debug, log_file=log_file or Path())

    # Create settings directly from parameters
    settings = FABulousCliSettings.create_with_env_files(
        project_dir=project_dir,
        global_dot_env=global_dot_env,
        project_dot_env=project_dot_env,
        verbose=verbose,
        debug=debug,
        log_file=log_file,
        force=force,
        writer=writer,
    )

    # Validate project directory
    project_dir = validate_project_directory(project_dir)

    # Handle project version update
    if update_project_version:
        from FABulous.FABulous_CLI.helper import (
            update_project_version as update_version_func,
        )

        if not update_version_func(project_dir):
            logger.error(
                "Failed to update project version. Please check the logs for more details."
            )
            raise typer.Exit(1)
        logger.info("Project version updated successfully")
        return

    # Check version compatibility
    check_version_compatibility(project_dir)

    # Initialize CLI using settings
    from FABulous.FABulous_CLI.FABulous_CLI import FABulous_CLI

    fab_CLI = FABulous_CLI(
        settings.proj_lang,
        project_dir,
        Path.cwd(),
        force=force,
    )
    fab_CLI.debug = debug

    # Change to project directory
    logger.info(f"Setting current working directory to: {project_dir}")
    os.chdir(project_dir)
    fab_CLI.onecmd_plus_hooks("load_fabric")

    # Execute script based on type
    if script_type == "tcl":
        fab_CLI.onecmd_plus_hooks(f"run_tcl {script_file.absolute()}")
        script_name = "TCL script"
    else:  # fabulous
        fab_CLI.onecmd_plus_hooks(f"run_script {script_file.absolute()}")
        script_name = "FABulous script"

    if fab_CLI.exit_code:
        logger.error(
            f"{script_name} {script_file} execution failed with exit code {fab_CLI.exit_code}"
        )
    else:
        logger.info(f"{script_name} {script_file} executed successfully")

    raise typer.Exit(fab_CLI.exit_code)


@app.command()
def run(
    project_dir: Annotated[
        Path | None, typer.Argument(help="Directory path to project folder")
    ] = None,
    fabulous_script: Annotated[
        Path | None,
        typer.Option(
            "--fabulous-script", "-fs", help="Run FABulous with a FABulous script"
        ),
    ] = None,
    tcl_script: Annotated[
        Path | None,
        typer.Option("--tcl-script", "-ts", help="Run FABulous with a TCL script"),
    ] = None,
    commands: Annotated[
        str | None,
        typer.Option("--commands", "-p", help="Execute commands (separate with '; ')"),
    ] = None,
    verbose: CommonVerbose = 0,
    debug: CommonDebug = False,
    log_file: CommonLogFile = None,
    global_dot_env: CommonGlobalDotEnv = None,
    project_dot_env: CommonProjectDotEnv = None,
    force: CommonForce = False,
    writer: CommonWriter = None,
    update_project_version: Annotated[
        bool,
        typer.Option(
            "--update-project-version",
            help="Update project version to match package version",
        ),
    ] = False,
    _version: Annotated[
        bool | None,
        typer.Option(
            "--version",
            callback=version_callback,
            is_eager=True,
            help="Show version and exit",
        ),
    ] = None,
) -> None:
    """Run FABulous with the specified project and options.

    This is the main command for running FABulous in interactive mode or with scripts.
    """
    # Determine project directory - CLI arg takes precedence, fallback to current dir
    if project_dir is None:
        project_dir = Path.cwd()
    else:
        project_dir = project_dir.absolute().resolve()

    # Setup logging using parameters
    setup_logger(verbose, debug, log_file=log_file or Path())

    # Create settings directly from parameters (avoids environment variable manipulation)
    settings = FABulousCliSettings.create_with_env_files(
        project_dir=project_dir,
        global_dot_env=global_dot_env,
        project_dot_env=project_dot_env,
        verbose=verbose,
        debug=debug,
        log_file=log_file,
        force=force,
        writer=writer,
    )

    # Validate project directory
    project_dir = validate_project_directory(project_dir)

    # Handle project version update
    if update_project_version:
        from FABulous.FABulous_CLI.helper import (
            update_project_version as update_version_func,
        )

        if not update_version_func(project_dir):
            logger.error(
                "Failed to update project version. Please check the logs for more details."
            )
            raise typer.Exit(1)
        logger.info("Project version updated successfully")
        return

    # Check version compatibility
    check_version_compatibility(project_dir)

    # Initialize CLI using settings
    from FABulous.FABulous_CLI.FABulous_CLI import FABulous_CLI

    fab_CLI = FABulous_CLI(
        settings.proj_lang,
        project_dir,
        Path.cwd(),
        force=force,
    )
    fab_CLI.debug = debug

    # Change to project directory
    logger.info(f"Setting current working directory to: {project_dir}")
    os.chdir(project_dir)
    fab_CLI.onecmd_plus_hooks("load_fabric")

    # Handle different execution modes
    if commands is not None:  # Check for None instead of truthy to handle empty string
        # Execute commands mode
        command_list = [cmd.strip() for cmd in commands.split("; ") if cmd.strip()]
        if command_list:  # Only execute if there are actual commands
            for cmd in command_list:
                fab_CLI.onecmd_plus_hooks(cmd)
                if fab_CLI.exit_code and not force:
                    logger.error(
                        f"Command '{cmd}' execution failed with exit code {fab_CLI.exit_code}"
                    )
                    raise typer.Exit(fab_CLI.exit_code)
            logger.info(f'Commands "{"; ".join(command_list)}" executed successfully')
        else:
            logger.info("No commands to execute")
        # Exit with the CLI exit code (could be non-zero if force was used and there were errors)
        raise typer.Exit(fab_CLI.exit_code)

    if fabulous_script:
        # Execute FABulous script mode
        fab_CLI.onecmd_plus_hooks(f"run_script {fabulous_script.absolute()}")
        if fab_CLI.exit_code:
            logger.error(
                f"FABulous script {fabulous_script} execution failed with exit code {fab_CLI.exit_code}"
            )
        else:
            logger.info(f"FABulous script {fabulous_script} executed successfully")
        raise typer.Exit(fab_CLI.exit_code)

    if tcl_script:
        # Execute TCL script mode
        fab_CLI.onecmd_plus_hooks(f"run_tcl {tcl_script.absolute()}")
        if fab_CLI.exit_code:
            logger.error(
                f"TCL script {tcl_script} execution failed with exit code {fab_CLI.exit_code}"
            )
        else:
            logger.info(f"TCL script {tcl_script} executed successfully")
        raise typer.Exit(fab_CLI.exit_code)

    # Interactive mode
    fab_CLI.interactive = True
    if verbose >= 2:
        fab_CLI.verbose = True

    fab_CLI.cmdloop()


def main() -> None:
    """Main entry point for the FABulous CLI."""
    import sys

    # Check if we have legacy argparse-style arguments for backward compatibility
    legacy_args = [
        "--createProject",
        "--install_oss_cad_suite",
        "--FABulousScript",
        "--TCLScript",
        "--commands",
        "--writer",
        "--verbose",
        "--debug",
        "--log",
        "--globalDotEnv",
        "--projectDotEnv",
        "--force",
        "--updateProjectVersion",
        "--version",
    ]

    if len(sys.argv) > 1 and any(arg in legacy_args for arg in sys.argv):
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

    # Show deprecation warning
    logger.warning(
        "You are using deprecated argparse-style arguments. "
        "Please migrate to the new typer-based commands:\n"
        "  --createProject <dir> → FABulous create-project <dir>\n"
        "  --install_oss_cad_suite → FABulous install-oss-cad-suite <dir>\n"
        "  <project_dir> --commands <cmd> → FABulous run <project_dir> --commands <cmd>\n"
        "  See 'FABulous --help' for more information."
    )

    # Create a parser that matches the original argparse interface
    parser = argparse.ArgumentParser(
        description="The command line interface for FABulous"
    )

    create_group = parser.add_mutually_exclusive_group()
    create_group.add_argument(
        "-c",
        "--createProject",
        action="store_true",
        default=False,
        help="Create a new project",
    )
    create_group.add_argument(
        "-iocs",
        "--install_oss_cad_suite",
        action="store_true",
        default=False,
        help="Install the oss-cad-suite in the directory",
    )

    script_group = parser.add_mutually_exclusive_group()
    parser.add_argument(
        "project_dir", default="", nargs="?", help="The directory to the project folder"
    )
    script_group.add_argument(
        "-fs",
        "--FABulousScript",
        default=None,
        nargs=1,
        type=Path,
        help="Run FABulous with a FABulous script",
    )
    script_group.add_argument(
        "-ts",
        "--TCLScript",
        default=None,
        nargs=1,
        type=Path,
        help="Run FABulous with a TCL script",
    )
    script_group.add_argument(
        "-p", "--commands", default=None, help="Execute commands (separate with '; ')"
    )

    parser.add_argument(
        "-w",
        "--writer",
        choices=["verilog", "vhdl"],
        default=None,
        help="Set type of HDL code generated",
    )
    parser.add_argument(
        "-v",
        "--verbose",
        action="count",
        default=0,
        help="Show detailed log information",
    )
    parser.add_argument(
        "--debug", action="store_true", default=False, help="Enable debug mode"
    )
    parser.add_argument("--log", "-log", type=Path, help="Log all output to file")
    parser.add_argument(
        "-gde", "--globalDotEnv", type=Path, help="Set global .env file path"
    )
    parser.add_argument(
        "-pde", "--projectDotEnv", type=Path, help="Set project .env file path"
    )
    parser.add_argument(
        "--force", action="store_true", default=False, help="Force command execution"
    )
    parser.add_argument(
        "--updateProjectVersion",
        action="store_true",
        default=False,
        help="Update project version",
    )
    parser.add_argument(
        "--version", action="store_true", default=False, help="Show version and exit"
    )

    # Parse the legacy arguments
    args = parser.parse_args()

    # Convert to new Typer command format and execute
    if args.version:
        from importlib.metadata import version

        from packaging.version import Version

        package_version = Version(version("FABulous-FPGA"))
        logger.info(f"FABulous CLI {package_version.base_version}")
        sys.exit(0)

    elif args.createProject:
        # Convert to: FABulous create-project <project_dir> [options]
        if not args.project_dir:
            logger.error("Project directory is required when creating a project")
            sys.exit(2)
        project_dir = Path(args.project_dir)
        try:
            create_project_cmd(
                project_dir=project_dir,
                writer=args.writer or "verilog",
                verbose=args.verbose,
                debug=args.debug,
                log_file=args.log,
            )
            sys.exit(0)
        except typer.Exit as e:
            sys.exit(e.exit_code)

    elif args.install_oss_cad_suite:
        # Convert to: FABulous install-oss-cad-suite <directory> [options]
        directory = Path(args.project_dir) if args.project_dir else Path.cwd()
        try:
            install_oss_cad_suite_cmd(
                directory=directory,
                verbose=args.verbose,
                debug=args.debug,
                log_file=args.log,
            )
            sys.exit(0)
        except typer.Exit as e:
            sys.exit(e.exit_code)

    else:
        # Convert to: FABulous run <project_dir> [options]
        try:
            run(
                project_dir=Path(args.project_dir) if args.project_dir else None,
                fabulous_script=args.FABulousScript[0] if args.FABulousScript else None,
                tcl_script=args.TCLScript[0] if args.TCLScript else None,
                commands=args.commands,
                writer=args.writer,
                verbose=args.verbose,
                debug=args.debug,
                log_file=args.log,
                global_dot_env=args.globalDotEnv,
                project_dot_env=args.projectDotEnv,
                force=args.force,
                update_project_version=args.updateProjectVersion,
            )
            # If we get here without an exception, exit with success
            sys.exit(0)
        except typer.Exit as e:
            sys.exit(e.exit_code)


if __name__ == "__main__":
    main()

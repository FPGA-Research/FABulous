"""Helper functions for FABulous."""

import functools
import os
import platform
import re
import shutil
import sys
import tarfile
import tempfile
from collections.abc import Callable, Sequence
from importlib import resources
from importlib.metadata import version
from importlib.resources.abc import Traversable
from pathlib import Path
from typing import TYPE_CHECKING, Any, Literal

import requests
from dotenv import get_key, set_key
from loguru import logger
from packaging.version import Version

from FABulous.custom_exception import PipelineCommandError
from FABulous.FABulous_settings import FAB_USER_CONFIG_DIR

if TYPE_CHECKING:
    from loguru import Record

    from FABulous.FABulous_CLI.FABulous_CLI import FABulous_CLI

MAX_BITBYTES = 16384


def setup_logger(verbosity: int, debug: bool, log_file: Path = Path()) -> None:
    """Setup logger for FABulous."""
    # Remove the default logger to avoid duplicate logs
    logger.remove()

    # Define a custom formatting function that has access to 'verbosity'
    def custom_format_function(record: "Record") -> str:
        # Construct the standard part of the log message based on verbosity
        level = f"<level>{record['level'].name}</level> | "
        time = f"<cyan>[{record['time']:DD-MM-YYYY HH:mm:ss}]</cyan> | "
        name = f"<green>[{record['name']}</green>"
        func = f"<green>{record['function']}</green>"
        line = f"<green>{record['line']}</green>"
        msg = f"<level>{record['message']}</level>"
        exc = ""
        if record["exception"] and record["exception"].type:
            exc = (
                f"<bg red><white>{record['exception'].type.__name__}</white>"
                f"</bg red> | "
            )

        final_log = f"{level}{exc}{msg}\n"
        if verbosity >= 1:
            final_log = f"{level}{time}{name}:{func}:{line} - {exc}{msg}\n"

        if os.getenv("FABULOUS_TESTING", None):
            final_log = f"{record['level'].name}: {record['message']}\n"
        return final_log

    # Determine the log level for the sink
    log_level_to_set = "DEBUG" if debug else "INFO"

    # Add logger to write logs to stdout using the custom formatter
    if log_file != Path():
        logger.add(
            log_file, format=custom_format_function, level=log_level_to_set, catch=False
        )
    else:
        logger.add(
            sys.stdout,
            format=custom_format_function,
            level=log_level_to_set,
            colorize=True,
            catch=False,
        )


def create_project(
    project_dir: Path, lang: Literal["verilog", "vhdl"] = "verilog"
) -> None:
    """Creates a FABulous project containing all required files by copying the common
    files and the appropriate project template. Replces the {HDL_SUFFIX} placeholder in
    all tile csv files with the appropriate file extension. Creates a .FABulous
    directory in the project. Also creates a .env file in the project directory with the
    project language.

    File structure as follows:
        FABulous_project_template --> project_dir/
        fabic_cad/synth --> project_dir/Test/synth

    Parameters
    ----------
    project_dir : Path
        Directory where the project will be created.
    lang : Literal["verilog", "vhdl"], optional
        The language of project to create ("verilog" or "vhdl"), by default "verilog".
    """
    logger.info(project_dir)

    if lang not in ["verilog", "vhdl"]:
        raise ValueError(f"Unsupported language: {lang}")

    # Copy the project template using importlib.resources
    try:
        common_template_ref = (
            resources.files("FABulous.fabric_files")
            / "FABulous_project_template_common"
        )
        lang_template_ref = (
            resources.files("FABulous.fabric_files")
            / f"FABulous_project_template_{lang}"
        )

        # Check if templates exist
        if not common_template_ref.is_dir():
            raise FileNotFoundError("Common template not found in package resources")
        if not lang_template_ref.is_dir():
            raise FileNotFoundError(
                f"Language template ({lang}) not found in package resources"
            )

    except (ImportError, AttributeError) as e:
        raise FileNotFoundError(
            f"Unable to access fabric templates from package: {e}"
        ) from e

    if project_dir.exists():
        logger.error("Project directory already exists!")
        sys.exit(1)
    else:
        project_dir.mkdir(parents=True, exist_ok=True)
        (project_dir / ".FABulous").mkdir(parents=True, exist_ok=True)

    # Copy templates from package resources using shutil.copytree
    # Use a robust approach that works in all environments
    def _copy_template_safely(template_ref: Traversable, target_dir: Path) -> None:
        """Copy template files safely, handling different installation environments."""
        try:
            # Try direct copy first (works in development/editable installs)
            with resources.as_file(template_ref) as template_src:
                shutil.copytree(template_src, target_dir, dirs_exist_ok=True)
        except (OSError, PermissionError, shutil.Error) as e:
            # Fallback: extract to temp directory first (works with wheels, frozen apps)
            logger.debug(f"Direct copy failed ({e}), using temp directory fallback")
            with tempfile.TemporaryDirectory() as temp_dir:
                temp_template = Path(temp_dir) / "template"
                with resources.as_file(template_ref) as template_src:
                    shutil.copytree(template_src, temp_template)
                shutil.copytree(temp_template, target_dir, dirs_exist_ok=True)

    # Copy common template first
    _copy_template_safely(common_template_ref, project_dir)

    # Copy language-specific template (may overwrite some common files)
    _copy_template_safely(lang_template_ref, project_dir)

    # Replace {HDL_SUFFIX} placeholder in all tile csv files
    new_suffix = "v" if lang == "verilog" else "vhdl"
    for file_path in project_dir.rglob("*.csv"):
        content = file_path.read_text()
        new_content = re.sub(r"\{HDL_SUFFIX\}", new_suffix, content)
        file_path.write_text(new_content)

    env_file = project_dir / ".FABulous" / ".env"
    set_key(env_file, "FAB_PROJ_LANG", lang)
    set_key(env_file, "FAB_PROJ_VERSION", version("FABulous-FPGA"))
    set_key(env_file, "FAB_PROJ_VERSION_CREATED", version("FABulous-FPGA"))
    set_key(
        env_file,
        "FAB_MODEL_PACK",
        str(project_dir / "Fabric" / f"model_pack.{new_suffix}"),
    )

    logger.info(f"New FABulous project created in {project_dir} with {lang} language.")


def copy_verilog_files(src: Path, dst: Path) -> None:
    """Copies all Verilog files from source directory to the destination directory.

    Parameters
    ----------
    src : str
        Source directory.
    dst : str
        Destination directory
    """

    for file_path in src.rglob("*.v"):
        destination_path = dst / file_path.name
        shutil.copy(file_path, destination_path)


def remove_dir(path: Path) -> None:
    """Removes a directory and all its contents.

    If the directory cannot be removed, logs OS error.

    Parameters
    ----------
    path : str
        Path of the directory to remove.
    """
    try:
        shutil.rmtree(path)
    except OSError as e:
        logger.error(f"{e}")


def make_hex(binfile: Path, outfile: Path) -> None:
    """Converts a binary file into hex file.

    If the binary file exceeds MAX_BITBYTES, logs error.

    Parameters
    ----------
    binfile : str
        Path to binary file.
    outfile : str
        Path to ouput hex file.
    """
    with Path(binfile).open("rb") as f:
        bindata = f.read()

    if len(bindata) > MAX_BITBYTES:
        logger.error("Binary file too big.")
        return

    with Path(outfile).open("w") as f:
        for i in range(MAX_BITBYTES):
            if i < len(bindata):
                print(f"{bindata[i]:02x}", file=f)
            else:
                print("0", file=f)


def wrap_with_except_handling(fun_to_wrap: Callable) -> Callable:
    """Decorator function that wraps 'fun_to_wrap' with exception handling.

    Parameters
    ----------
    fun_to_wrap : callable
        The function to be wrapped with exception handling.
    """

    def inter(*args: Any, **varargs: Any) -> None:  # noqa: ANN401
        """Wrapped function that executes 'fun_to_wrap' with arguments and exception
        handling.

        Parameters
        ----------
        *args : tuple
            Positional arguments to pass to 'fun_to_wrap'.
        **varags : dict
            Keyword arguments to pass to 'fun_to_wrap'.
        """
        try:
            fun_to_wrap(*args, **varargs)
        except Exception:  # noqa: BLE001 - Catching all exceptions is ok here
            import traceback

            traceback.print_exc()
            logger.error("TCL command failed. Please check the logs for details.")
            raise Exception from Exception  # noqa: TRY002 - Raising a new exception with the original traceback

    return inter


def allow_blank(func: Callable) -> Callable:
    @functools.wraps(func)
    def _check_blank(*args: Sequence[str]) -> None:
        if len(args) == 1:
            func(*args, "")
        else:
            func(*args)

    return _check_blank


def install_oss_cad_suite(destination_folder: Path, update: bool = False) -> None:
    """Downloads and extracts the latest OSS CAD Suite. Sets the the FAB_OSS_CAD_SUITE
    environment variable in the .env file.

    Parameters
    ----------
        destination_folder: Path
            The folder where the OSS CAD Suite will be installed.
        update : bool
            If True, it will update the existing installation if it exists.

    Raises
    ------
        FileExistsError
            If the folder already exists and update is not set to True.
        requests.RequestException
            If the download fails or the request to GitHub fails.
        ValueError
            If the operating system or architecture is not supported.
            If no valid archive is found for the current OS and architecture.
            If the file format of the downloaded archive is unsupported.
    """
    github_releases_url = (
        "https://api.github.com/repos/YosysHQ/oss-cad-suite-build/releases/latest"
    )
    response = requests.get(github_releases_url)
    system = platform.system().lower()
    machine = platform.machine().lower()
    url = None

    # check if oss-cad-suite folder already exists
    ocs_folder = destination_folder / "oss-cad-suite"
    if ocs_folder.is_dir():
        if update:
            logger.warning(f"Updating existing installation in {ocs_folder.absolute()}")
            # remove existing files:
            for root, dirs, files in ocs_folder.walk(top_down=False):
                for name in files:
                    (root / name).unlink()
                for name in dirs:
                    (root / name).rmdir()
            ocs_folder.rmdir()
        else:
            raise FileExistsError(
                f"The folder {ocs_folder} already exists. Please set the update flag, "
                f"remove it or choose a different folder."
            )
    else:
        if not destination_folder.is_dir():
            logger.info(f"Creating folder {destination_folder.absolute()}")
            Path.mkdir(destination_folder, exist_ok=True)
        else:
            logger.info(
                f"Installing OSS-CAD-Suite to folder {destination_folder.absolute()}"
            )

    # format system and machine to match the OSS-CAD-Suite release naming
    if system not in ["linux", "windows", "darwin"]:
        raise ValueError(
            f"Unsupported operating system {system}. "
            f"Please install OSS-CAD-Suite manually."
        )
    if machine in ["x86_64", "amd64"]:
        machine = "x64"
    elif machine in ["aarch64", "arm64"]:
        machine = "arm64"
    else:
        raise ValueError(
            f"Unsupported architecture {machine}. "
            f"Please install OSS-CAD-Suite manually."
        )

    if response.status_code == 200:
        latest_release = response.json()
    else:
        raise ConnectionError(
            f"Failed to fetch latest OSS-CAD-Suite release: {response.status_code}"
        )

    # find the right release for the current system
    for asset in latest_release.get("assets", []):
        if ("tar.gz" in asset["name"] or "tgz" in asset["name"]) and (
            machine in asset["name"].lower() and system in asset["name"].lower()
        ):
            url = asset["browser_download_url"]
            break  # we assume that the first match is the right one
    if url is None or url == "":  # Changed == None to is None
        raise ValueError("No valid archive found in the latest release.")

    # Download the file
    ocs_archive = destination_folder / url.split("/")[-1]
    logger.info(f"Downloading OSS-CAD-Suite {url}")
    response = requests.get(url, stream=True)

    if response.status_code == 200:
        with Path(ocs_archive).open("wb") as file:
            file.writelines(response.iter_content(chunk_size=8192))
    else:
        raise ConnectionError(f"Failed to download file: {response.status_code}")

    # Extract the archive
    logger.info(f"Extracting OSS-CAD-Suite to {destination_folder.absolute()}")
    if ocs_archive.suffix in [".tar.gz", ".tgz"]:
        with tarfile.open(ocs_archive, "r:gz") as tar:
            tar.extractall(path=destination_folder)
    else:
        raise ValueError(
            f"Unsupported file format. Please extract {ocs_archive} manually."
        )

    logger.info(f"Remove archive {ocs_archive}")
    ocs_archive.unlink()

    # Use user config directory for global .env file
    user_config_dir = FAB_USER_CONFIG_DIR
    user_config_dir.mkdir(parents=True, exist_ok=True)
    env_file = user_config_dir / ".env"
    if not env_file.exists():
        env_file.touch()
    set_key(env_file, "FAB_OSS_CAD_SUITE", str(ocs_folder.absolute()))

    # export oss-cad-suite to PATH
    os.environ["PATH"] += os.pathsep + str(ocs_folder / "bin")

    logger.info("OSS CAD Suite setup completed successfully.")


def update_project_version(project_dir: Path) -> bool:
    env_file = project_dir / ".FABulous" / ".env"

    project_version = get_key(env_file, "FAB_PROJ_VERSION")

    if project_version is None:
        logger.error("VERSION not found in .env file.")
        return False

    project_version = Version(project_version)
    package_version = Version(version("FABulous-FPGA"))
    if package_version.major != project_version.major:
        logger.error(
            "There is a major version mismatch, cannot update project version."
        )
        return False

    set_key(env_file, "FAB_PROJ_VERSION", str(package_version))
    return True


class CommandPipeline:
    """Helper class to manage command execution with error handling."""

    def __init__(self, cli_instance: "FABulous_CLI", force: bool = False) -> None:
        self.cli = cli_instance
        self.steps = []
        self.force = force
        self.final_exit_code = 0

    def add_step(
        self, command: str, error_message: str = "Command failed"
    ) -> "CommandPipeline":
        """Add a command step to the pipeline."""
        self.steps.append((command, error_message))
        return self

    def execute(self) -> bool:
        """Execute all steps in the pipeline.

        Returns:
            bool: True if all commands succeeded, False if any failed.

        Raises:
            PipelineCommandError: If any command fails and force=False.
        """

        for command, error_message in self.steps:
            self.cli.onecmd_plus_hooks(command)
            if self.cli.exit_code != 0:
                self.final_exit_code = self.cli.exit_code
                logger.error(
                    f"Command '{command}' execution failed with exit code "
                    f"{self.cli.exit_code}"
                )

                if not self.force:
                    raise PipelineCommandError(error_message)

        return self.final_exit_code == 0

    def get_exit_code(self) -> int:
        """Get the final exit code from pipeline execution."""
        return self.final_exit_code

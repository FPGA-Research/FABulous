import argparse
import functools
import os
import platform
import requests
import shutil
import sys
import tarfile
from pathlib import Path
from typing import Literal

from dotenv import load_dotenv
from loguru import logger

MAX_BITBYTES = 16384


def setup_logger(verbosity: int):
    # Remove the default logger to avoid duplicate logs
    logger.remove()

    # Define logger format
    if verbosity >= 1:
        log_format = (
            "<level>{level:}</level> | "
            "<cyan>[{time:DD-MM-YYYY HH:mm:ss]}</cyan> | "
            "<green>[{name}</green>:<green>{function}</green>:<green>{line}]</green> - "
            "<level>{message}</level>"
        )
    else:
        log_format = "<level>{level:}</level> | <level>{message}</level>"

    # Add logger to write logs to stdout
    logger.add(sys.stdout, format=log_format, level="DEBUG", colorize=True)


def setup_global_env_vars(args: argparse.Namespace) -> None:
    """Set up global  environment variables.

    Parameters
    ----------
    args : argparse.Namespace
        Command line arguments
    """
    # Set FAB_ROOT environment variable
    fabulousRoot = os.getenv("FAB_ROOT")
    if fabulousRoot is None:
        fabulousRoot = str(Path(__file__).resolve().parent.parent)
        os.environ["FAB_ROOT"] = fabulousRoot
        logger.info("FAB_ROOT environment variable not set!")
        logger.info(f"Using {fabulousRoot} as FAB_ROOT")
    else:
        # If there is the FABulous folder in the FAB_ROOT, then set the FAB_ROOT to the FABulous folder
        if Path(fabulousRoot).exists():
            if Path(fabulousRoot).joinpath("FABulous").exists():
                fabulousRoot = str(Path(fabulousRoot).joinpath("FABulous"))
            os.environ["FAB_ROOT"] = fabulousRoot
        else:
            logger.error(
                f"FAB_ROOT environment variable set to {fabulousRoot} but the directory does not exist"
            )
            sys.exit()

        logger.info(f"FAB_ROOT set to {fabulousRoot}")

    # Load the .env file and make env variables available globally
    if p := os.getenv("FAB_ROOT"):
        fabDir = Path(p)
    else:
        raise Exception("FAB_ROOT environment variable not set")
    if args.globalDotEnv:
        gde = Path(args.globalDotEnv)
        if gde.is_file():
            load_dotenv(gde)
            logger.info(f"Load global .env file from {gde}")
        elif gde.joinpath(".env").exists() and gde.joinpath(".env").is_file():
            load_dotenv(gde.joinpath(".env"))
            logger.info(f"Load global .env file from {gde.joinpath('.env')}")
        else:
            logger.warning(f"No global .env file found at {gde}")
    elif fabDir.joinpath(".env").exists() and fabDir.joinpath(".env").is_file():
        load_dotenv(fabDir.joinpath(".env"))
        logger.info(f"Loaded global .env file from {fabulousRoot}/.env")
    elif (
        fabDir.parent.joinpath(".env").exists()
        and fabDir.parent.joinpath(".env").is_file()
    ):
        load_dotenv(fabDir.parent.joinpath(".env"))
        logger.info(f"Loaded global .env file from {fabDir.parent.joinpath('.env')}")
    else:
        logger.info("No global .env file found")

    # Set project directory env var, this can not be saved in the .env file,
    # since it can change if the project folder is moved
    if not os.getenv("FAB_PROJ_DIR"):
        os.environ["FAB_PROJ_DIR"] = args.project_dir

    # Export oss-cad-suite bin path to PATH
    if ocs_path := os.getenv("FAB_OSS_CAD_SUITE"):
        os.environ["PATH"] += os.pathsep + ocs_path + "/bin"


def setup_project_env_vars(args: argparse.Namespace) -> None:
    """Set up environment variables for the project.

    Parameters
    ----------
    args : argparse.Namespace
        Command line arguments
    """
    # Load the .env file and make env variables available globally
    if p := os.getenv("FAB_PROJ_DIR"):
        fabDir = Path(p) / ".FABulous"
    else:
        raise Exception("FAB_PROJ_DIR environment variable not set")

    if args.projectDotEnv:
        pde = Path(args.projectDotEnv)
        if pde.exists() and pde.is_file():
            load_dotenv(pde)
            logger.info("Loaded global .env file from pde")
    elif fabDir.joinpath(".env").exists() and fabDir.joinpath(".env").is_file():
        load_dotenv(fabDir.joinpath(".env"))
        logger.info(f"Loaded project .env file from {fabDir}/.env')")
    elif (
        fabDir.parent.joinpath(".env").exists()
        and fabDir.parent.joinpath(".env").is_file()
    ):
        load_dotenv(fabDir.parent.joinpath(".env"))
        logger.info(f"Loaded project .env file from {fabDir.parent.joinpath('.env')}")
    else:
        logger.warning("No project .env file found")

    # Overwrite project language param, if writer is specified as command line argument
    if args.writer and args.writer != os.getenv("FAB_PROJ_LANG"):
        logger.warning(
            f"Overwriting project language for current run, from {os.getenv('FAB_PROJ_LANG')} to {args.writer}, which was specified as command line argument"
        )
        os.environ["FAB_PROJ_LANG"] = args.writer


def create_project(project_dir, type: Literal["verilog", "vhdl"] = "verilog"):
    """Creates a FABulous project containing all required files by copying the
    appropriate project template and the synthesis directory.

    File structure as follows:
        FABulous_project_template --> project_dir/
        fabic_cad/synth --> project_dir/Test/synth

    Parameters
    ----------
    project_dir : str
        Directory where the project will be created.
    type : Literal["verilog", "vhdl"], optional
        The type of project to create ("verilog" or "vhdl"), by default "verilog".
    """
    if os.path.exists(project_dir):
        logger.error("Project directory already exists!")
        sys.exit()
    else:
        os.mkdir(f"{project_dir}")

    # set default type, since "None" overwrites the default value
    if not type:
        type = "verilog"

    os.mkdir(f"{project_dir}/.FABulous")
    fabulousRoot = os.getenv("FAB_ROOT")

    shutil.copytree(
        f"{fabulousRoot}/fabric_files/FABulous_project_template_{type}/",
        f"{project_dir}/",
        dirs_exist_ok=True,
    )

    with open(os.path.join(project_dir, ".FABulous/.env"), "w") as env_file:
        env_file.write(f"FAB_PROJ_LANG={type}\n")

    logger.info(f"New FABulous project created in {project_dir} with {type} language.")


def copy_verilog_files(src: Path, dst: Path):
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


def remove_dir(path: Path):
    """Removes a directory and all its contents.

    If the directory cannot be removed, logs OS error.

    Parameters
    ----------
    path : str
        Path of the directory to remove.
    """
    try:
        shutil.rmtree(path)
        pass
    except OSError as e:
        logger.error(f"{e}")


def make_hex(binfile: Path, outfile: Path):
    """Converts a binary file into hex file.

    If the binary file exceeds MAX_BITBYTES, logs error.

    Parameters
    ----------
    binfile : str
        Path to binary file.
    outfile : str
        Path to ouput hex file.
    """
    with open(binfile, "rb") as f:
        bindata = f.read()

    if len(bindata) > MAX_BITBYTES:
        logger.error("Binary file too big.")
        return

    with open(outfile, "w") as f:
        for i in range(MAX_BITBYTES):
            if i < len(bindata):
                print(f"{bindata[i]:02x}", file=f)
            else:
                print("0", file=f)


def check_if_application_exists(application: str, throw_exception: bool = True) -> Path:
    """Checks if an application is installed on the system.

    Parameters
    ----------
    application : str
        Name of the application to check.
    throw_exception : bool, optional
        If True, throws an exception if the application is not installed, by default True

    Returns
    -------
    Path
        Path to  the application, if installed.

    Raises
    ------
    Exception
        If the application is not installed and throw_exception is True.
    """
    path = shutil.which(application)
    if path is not None:
        return Path(path)
    else:
        logger.error(
            f"{application} is not installed. Please install it or set FAB_<APPLICATION>_PATH in the .env file."
        )
        if throw_exception:
            raise Exception(f"{application} is not installed.")


def wrap_with_except_handling(fun_to_wrap):
    """Decorator function that wraps 'fun_to_wrap' with exception handling.

    Parameters
    ----------
    fun_to_wrap : callable
        The function to be wrapped with exception handling.
    """

    def inter(*args, **varargs):
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
        except Exception:
            import traceback

            traceback.print_exc()
            sys.exit(1)

    return inter


def allow_blank(func):
    @functools.wraps(func)
    def _check_blank(*args):
        if len(args) == 1:
            func(*args, "")
        else:
            func(*args)

    return _check_blank


def install_oss_cad_suite(destination_folder: Path, update: bool = False):
    """Downloads and extracts the latest OSS CAD Suite. Sets the the FAB_OSS_CAD_SUITE
    environment variable in the .env file.

    Parameters
    ----------
        destination_folder: Path
            The folder where the OSS CAD Suite will be installed.
        update : bool
            If True, it will update the existing installation if it exists.

    Raises:
    -------
        Exception
            If the folder already exists and update is not set to True.
            If the download fails.
            If the request to GitHub fails.
        ValueError
            If the operating system or architecture is not supported.
            If no valid archive is found for the current OS and architecture.
            No valid archive of OSS-CAD-Suite found in the latest release.
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
            raise Exception(
                f"The folder {ocs_folder} already exists. Please set the update flag, remove it or choose a different folder."
            )
    else:
        if not destination_folder.is_dir():
            logger.info(f"Creating folder {destination_folder.absolute()}")
            os.makedirs(destination_folder, exist_ok=True)
        else:
            logger.info(
                f"Installing OSS-CAD-Suite to folder {destination_folder.absolute()}"
            )

    # format system and machine to match the OSS-CAD-Suite release naming
    if system not in ["linux", "windows", "darwin"]:
        raise ValueError(
            f"Unsupported operating system {system}. Please install OSS-CAD-Suite manually."
        )
    if machine in ["x86_64", "amd64"]:
        machine = "x64"
    elif machine in ["aarch64", "arm64"]:
        machine = "arm64"
    else:
        raise ValueError(
            f"Unsupported architecture {machine}. Please install OSS-CAD-Suite manually."
        )

    if response.status_code == 200:
        latest_release = response.json()
    else:
        raise Exception(
            f"Failed to fetch latest OSS-CAD-Suite release: {response.status_code}"
        )

    # find the right release for the current system
    for asset in latest_release.get("assets", []):
        if "tar.gz" in asset["name"] or "tgz" in asset["name"]:
            if machine in asset["name"].lower() and system in asset["name"].lower():
                url = asset["browser_download_url"]
                break  # we assume that the first match is the right one
    if url == None or url == "":
        raise ValueError("No valid archive found in the latest release.")

    # Download the file
    ocs_archive = destination_folder / url.split("/")[-1]
    logger.info(f"Downloading OSS-CAD-Suite {url}")
    response = requests.get(url, stream=True)

    if response.status_code == 200:
        with open(ocs_archive, "wb") as file:
            for chunk in response.iter_content(chunk_size=8192):
                file.write(chunk)
    else:
        raise Exception(f"Failed to download file: {response.status_code}")

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

    env_file = Path(os.getenv("FAB_ROOT")) / ".env"
    env_cont = ""
    if env_file.is_file():
        logger.info(f"Updating FAB_OSS_CAD_SUITE in .env file {env_file}")
        env_cont = env_file.read_text()
        env_cont = env_cont.split("\n")
        for line in env_cont:
            if "FAB_OSS_CAD_SUITE" in line:
                env_cont.remove(line)
        env_cont.append(f"FAB_OSS_CAD_SUITE={ocs_folder.absolute()}")
    else:
        logger.info(f"Creating .env file {env_file}")
        env_cont = [f"FAB_OSS_CAD_SUITE={ocs_folder.absolute()}"]

    env_file.write_text("\n".join(env_cont))

    # export oss-cad-suite to PATH
    os.environ["PATH"] += os.pathsep + str((ocs_folder / "bin"))

    logger.info("OSS CAD Suite setup completed successfully.")

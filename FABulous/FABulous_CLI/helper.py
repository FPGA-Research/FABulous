import argparse
import functools
import os
import shutil
import sys
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
        logger.warning("No global .env file found")

    # Set project directory env var, this can not be saved in the .env file,
    # since it can change if the project folder is moved
    if not os.getenv("FAB_PROJ_DIR"):
        os.environ["FAB_PROJ_DIR"] = args.project_dir


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

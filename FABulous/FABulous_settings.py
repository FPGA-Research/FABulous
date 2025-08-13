import argparse
import os
import sys
from importlib.metadata import version
from pathlib import Path
from shutil import which

from dotenv import load_dotenv
from loguru import logger
from packaging.version import Version
from pydantic import field_validator
from pydantic_core.core_schema import FieldValidationInfo  # type: ignore
from pydantic_settings import BaseSettings, SettingsConfigDict

from FABulous.custom_exception import EnvironmentNotSet
from FABulous.fabric_definition.define import HDLType


class FABulousSettings(BaseSettings):
    """Application settings.

    Tool paths are resolved lazily during validation so that environment variable setup
    (including PATH updates for oss-cad-suite) can occur beforehand.
    """

    model_config = SettingsConfigDict(env_prefix="FAB_", case_sensitive=False)

    root: Path | None = None
    yosys_path: Path | None = None
    nextpnr_path: Path | None = None
    iverilog_path: Path | None = None
    vvp_path: Path | None = None
    ghdl_path: Path | None = None

    # Project related
    proj_dir: Path = Path.cwd()
    fabulator_root: Path | None = None
    oss_cad_suite: Path | None = None
    proj_version_created: Version = Version("0.0.1")
    proj_version: Version = Version(version("FABulous-FPGA"))

    proj_lang: HDLType = HDLType.VERILOG
    switch_matrix_debug_signal: bool = False
    model_pack: Path | None = None

    @field_validator("proj_version_created", mode="before")
    @classmethod
    def parse_version_created(cls, value: str | Version) -> Version:
        """Parse version created from string or Version object."""
        if isinstance(value, str):
            return Version(value)
        return value

    @field_validator("proj_version", mode="before")
    @classmethod
    def parse_version(cls, value: str | Version) -> Version:
        """Parse version from string or Version object."""
        if isinstance(value, str):
            return Version(value)
        return value

    @field_validator("model_pack", mode="before")
    @classmethod
    def parse_model_pack(
        cls, value: str | Path | None, info: FieldValidationInfo
    ) -> Path | None:  # type: ignore[override]
        """Validate and normalise model_pack path based on project language.

        Uses already-validated proj_lang from info.data when available. Accepts None /
        empty string to mean unset.
        """
        if value in (None, ""):
            return None
        path = Path(value)
        # Retrieve previously validated proj_lang (falls back to default enum value)
        proj_lang = info.data.get("proj_lang", HDLType.VERILOG)
        try:
            # If provided as string earlier but not validated yet
            if isinstance(proj_lang, str):
                proj_lang = HDLType[proj_lang.upper()]
        except KeyError:
            raise ValueError(
                "Invalid project language while validating model_pack"
            ) from None

        if proj_lang in {HDLType.VERILOG, HDLType.SYSTEM_VERILOG}:
            if path.suffix not in {".v", ".sv"}:
                raise ValueError(
                    "Model pack for Verilog/System Verilog must be a .v or .sv file"
                )
        elif proj_lang == HDLType.VHDL and path.suffix not in {".vhdl", ".vhd"}:
            raise ValueError("Model pack for VHDL must be a .vhdl or .vhd file")
        return path

    @field_validator("root", mode="after")
    @classmethod
    def is_dir(cls, value: Path) -> Path:
        """Check if inputs is a directory."""
        if not value.is_dir():
            raise ValueError(f"{value} is not a valid directory")
        return value

    @field_validator("proj_lang", mode="after")
    @classmethod
    def validate_proj_lang(cls, value: str) -> str:
        """Validate the project language."""
        if value not in ["verilog", "vhdl"]:
            raise ValueError("Project language must be either 'verilog' or 'vhdl'.")
        return value

    @field_validator("proj_lang", mode="before")
    @classmethod
    def validate_proj_lang(cls, value: str | HDLType) -> HDLType:
        """Validate and normalise the project language to HDLType enum."""
        if isinstance(value, HDLType):
            return value
        key = value.strip().upper()
        # Allow common aliases
        alias_map = {
            "VERILOG": "VERILOG",
            "V": "VERILOG",
            "SYSTEM_VERILOG": "SYSTEM_VERILOG",
            "SV": "SYSTEM_VERILOG",
            "VHDL": "VHDL",
            "VHD": "VHDL",
        }
        key = alias_map.get(key, key)
        return HDLType[key]

    # Resolve external tool paths only after object creation (post env setup)
    @field_validator(
        "yosys_path",
        "nextpnr_path",
        "iverilog_path",
        "vvp_path",
        "ghdl_path",
        mode="before",
    )
    @classmethod
    def resolve_tool_paths(
        cls, value: Path | None, info: FieldValidationInfo
    ) -> Path | None:  # type: ignore[override]
        if value is not None:
            return value
        tool_map = {
            "yosys_path": "yosys",
            "nextpnr_path": "nextpnr-generic",
            "iverilog_path": "iverilog",
            "vvp_path": "vvp",
            "ghdl_path": "ghdl",
        }
        tool = tool_map.get(info.field_name, None)  # type: ignore[attr-defined]
        if tool is None:
            return value
        tool_path = which(tool)
        if tool_path is not None:
            return Path(tool_path).resolve()

        logger.warning(
            f"{tool} not found in PATH during settings initialisation. Some features may be unavailable."
        )
        return None


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
        # Prefer the package directory (the one containing fabric_files) as FAB_ROOT
        pkg_dir = Path(__file__).parent.resolve()
        if pkg_dir.joinpath("fabric_files").exists():
            fabulousRoot = str(pkg_dir)
        else:  # Fallback to previous behaviour (repository root)
            fabulousRoot = str(Path(__file__).parent.parent.resolve())
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
        raise EnvironmentNotSet("FAB_ROOT environment variable not set")
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
        os.environ["FAB_PROJ_DIR"] = str(Path(args.project_dir).absolute())

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
        raise EnvironmentNotSet("FAB_PROJ_DIR environment variable not set")

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

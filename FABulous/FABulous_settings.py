"""FABulous settings management and environment configuration.

This module handles configuration settings for the FABulous FPGA framework, including
tool paths, project settings, and environment variable management.
"""

import os
from importlib.metadata import version as meta_version
from pathlib import Path
from shutil import which

import typer
from dotenv import set_key
from loguru import logger
from packaging.version import Version
from pydantic import Field, ValidationInfo, field_validator
from pydantic_settings import (
    BaseSettings,
    SettingsConfigDict,
)

from FABulous.fabric_definition.define import HDLType

# User configuration directory for FABulous
FAB_USER_CONFIG_DIR = Path(typer.get_app_dir("FABulous", force_posix=True))


class FABulousSettings(BaseSettings):
    """FABulous settings.

    Tool paths are resolved lazily during validation so that environment variable setup
    (including PATH updates for oss-cad-suite) can occur beforehand.
    """

    model_config = SettingsConfigDict(env_prefix="FAB_", case_sensitive=False)

    user_config_dir: Path = Field(default_factory=lambda: FAB_USER_CONFIG_DIR)

    oss_cad_suite: Path | None = None
    yosys_path: Path | str = Field(default="yosys", validate_default=True)
    nextpnr_path: Path | str = Field(default="nextpnr-generic", validate_default=True)
    iverilog_path: Path | str = Field(default="iverilog", validate_default=True)
    vvp_path: Path | str = Field(default="vvp", validate_default=True)
    ghdl_path: Path | str = Field(default="ghdl", validate_default=True)
    fabulator_root: Path | None = None

    proj_dir: Path = Field(default_factory=Path.cwd)
    proj_lang: HDLType = HDLType.VERILOG
    models_pack: Path | None = None
    switch_matrix_debug_signal: bool = False
    proj_version_created: Version = Version("0.0.1")
    proj_version: Version = Version(meta_version("FABulous-FPGA"))
    version: Version = Field(
        default=Version(meta_version("FABulous-FPGA")),
        deprecated=True,
        description="Deprecated, use proj_version instead",
    )

    # CLI options
    debug: bool = False
    verbose: int = 0
    editor: str | None = None

    # Windows warning acknowledgement
    windows_warning_acknowledged: bool = False

    @field_validator("oss_cad_suite", mode="before")
    @classmethod
    def parse_oss_cad_suite_path(cls, value: Path | str | None) -> Path | None:
        """Parse oss-cad-suite path and publish it to $PATH.

        Parses the oss-cad-suite path from env var and publishes it to PATH before the
        init of other tools, that then can be found in PATH.
        """
        if value is None:
            return None

        ocs_path = None
        if isinstance(value, str):
            ocs_path = Path(value).absolute()
        elif isinstance(value, Path):
            ocs_path = value.absolute()

        if ocs_path.is_dir():
            if (ocs_path / "bin").is_dir():
                ocs_path = ocs_path / "bin"
            logger.info(f"Using oss-cad-suite path: {ocs_path}")

            # Add the oss-cad-suite bin folder to PATH
            os.environ["PATH"] += os.pathsep + ocs_path.as_posix()
            return ocs_path

        logger.warning(
            f"Could not find oss-cad-suite path{ocs_path}, ignoring setting."
        )
        return None

    @field_validator("proj_version", "proj_version_created", "version", mode="before")
    @classmethod
    def parse_version_str(cls, value: str | Version) -> Version:
        """Parse version from string or Version object."""
        if isinstance(value, str):
            return Version(value)
        return value

    @field_validator("models_pack", mode="after")
    @classmethod
    def parse_models_pack(cls, value: Path | None, info: ValidationInfo) -> Path | None:  # type: ignore[override]
        """Validate and normalise models_pack path based on project language.

        Uses already-validated proj_lang from info.data when available. Accepts None /
        empty string to mean unset.
        """
        proj_lang = info.data.get("proj_lang")
        if value is None or value == "":
            if p := info.data.get("proj_dir"):
                p = Path(p).absolute()
            else:
                raise ValueError("Project directory is not set.")
            if proj_lang == HDLType.VHDL:
                mp = p / "Fabric" / "my_lib.vhdl"
                if mp.exists():
                    logger.warning(
                        f"Models pack path is not set. Guessing models pack as: {mp}"
                    )
                    return mp
                mp = p / "Fabric" / "models_pack.vhdl"
                if mp.exists():
                    logger.warning(
                        f"Models pack path is not set. Guessing models pack as: {mp}"
                    )
                    return mp
                logger.warning(
                    "Cannot find a suitable models pack. "
                    "This might lead to error if not set."
                )

            if proj_lang in {HDLType.VERILOG, HDLType.SYSTEM_VERILOG}:
                mp = p / "Fabric" / "models_pack.v"
                if mp.exists():
                    logger.warning(
                        f"Models pack path is not set. Guessing models pack as: {mp}"
                    )
                    return mp
                logger.warning(
                    "Cannot find a suitable models pack. "
                    "This might lead to error if not set."
                )

            return None

        if not value.is_file():
            # models_pack path is by default as a relative path starting from proj_dir
            # This can cause errors if FABulous is called from a different working dir
            # So we have to puzzle the models_pack path back together from there.
            if proj_dir := info.data.get("proj_dir"):
                proj_dir = Path(proj_dir).absolute()
                if not proj_dir.exists():
                    raise ValueError(f"Project directory {proj_dir} does not exist.")
            else:
                raise ValueError("Project directory is not set.")

            # Check if `project_dir` is not an absolute path and
            # in the models_pack path, since in the default it is
            # put there as folder.
            if not value.is_absolute() and proj_dir.name in value.parts:
                parts = list(value.parts)
                index = parts.index(proj_dir.name)
                value = proj_dir.joinpath(*parts[index + 1 :])
                if not value.is_file():
                    raise ValueError(
                        f"Models pack file does not exist: {value}"
                        " Check your FAB_MODELS_PACK env var setting."
                    )
            else:
                raise ValueError(
                    f"Models pack file does not exist: {value}"
                    " Check your FAB_MODELS_PACK env var setting."
                )

        # Retrieve previously validated proj_lang (falls back to default enum value)
        try:
            # If provided as string earlier but not validated yet
            if isinstance(proj_lang, str):
                proj_lang = HDLType[proj_lang.upper()]
        except KeyError:
            raise ValueError(
                "Invalid project language while validating models_pack"
            ) from None

        if proj_lang in {
            HDLType.VERILOG,
            HDLType.SYSTEM_VERILOG,
        } and value.suffix not in {".v", ".sv"}:
            raise ValueError(
                "Models pack for Verilog/System Verilog must be a .v or .sv file"
            )
        if proj_lang == HDLType.VHDL and value.suffix not in {".vhdl", ".vhd"}:
            raise ValueError("Models pack for VHDL must be a .vhdl or .vhd file")
        return value.absolute()

    @field_validator("user_config_dir", mode="after")
    @classmethod
    def ensure_user_config_dir(cls, value: Path | None) -> Path | None:
        """Ensure user config directory exists, creating if necessary."""
        if value is None:
            return None
        # Create the directory if it doesn't exist
        value.mkdir(parents=True, exist_ok=True)
        return value

    @field_validator("proj_dir", mode="after")
    @classmethod
    def is_valid_project_dir(cls, value: Path | None) -> Path | None:
        """Check if project_dir is a valid directory."""
        if value is None:
            raise ValueError("Project directory is not set.")
        if not (Path(value) / ".FABulous").exists():
            raise ValueError(f"{value} is not a FABulous project")
        return value.resolve()

    @field_validator("proj_lang", mode="before")
    @classmethod
    def parse_proj_lang(cls, value: str | HDLType) -> str | HDLType:
        """Parse project language from string or HDLType enum."""
        if isinstance(value, HDLType):
            return value
        if isinstance(value, str):
            return value.strip().lower()
        raise ValueError("Project language must be a string or HDLType enum")

    @field_validator("proj_lang", mode="after")
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
        if key not in alias_map:
            raise ValueError(f"Invalid project language: {value}")
        return HDLType[alias_map[key]]

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
        cls, value: Path | str | None, info: ValidationInfo
    ) -> Path | str:
        """Resolve tool paths by checking if tools are available in `PATH`.

        This method is used as a field validator to automatically resolve tool paths
        during settings initialization. If a tool path is not explicitly provided,
        it searches for the tool in the system `PATH`.

        Parameters
        ----------
        value : Path | str | None
            The explicitly provided tool path, if any.
        info : ValidationInfo
            Validation context containing field information.

        Returns
        -------
        Path | str
            The resolved path to the tool if found, tool name otherwise.

        Notes
        -----
        This method logs a warning if a tool is not found in `PATH`, as some
        features may be unavailable without the tool.
        """
        if isinstance(value, Path):
            return value
        if isinstance(value, str) and value != "" and Path(value).exists():
            return Path(value).resolve()
        tool_map = {
            "yosys_path": "yosys",
            "nextpnr_path": "nextpnr-generic",
            "iverilog_path": "iverilog",
            "vvp_path": "vvp",
            "ghdl_path": "ghdl",
        }
        tool = tool_map.get(info.field_name, None)  # type: ignore[attr-defined]
        tool_path = which(tool)
        if tool_path is not None:
            return Path(tool_path).resolve()

        logger.warning(
            f"{tool} not found in PATH during settings initialisation. "
            f"Some features may be unavailable."
        )
        return tool_map[info.field_name]


# Module-level singleton pattern for settings management
_context_instance: FABulousSettings | None = None


def init_context(
    project_dir: Path | None = None,
    global_dot_env: Path | None = None,
    project_dot_env: Path | None = None,
    api_mode: bool = False,
) -> FABulousSettings:
    """Initialize the global FABulous context with settings.

    This function gathers .env files and lets the pydantic-settings system handle
    project directory resolution.

    Parameters
    ----------
    project_dir : Path | None
        Project directory path (if None, uses cwd)
    global_dot_env : Path | None
        Path to a global .env file (if any)
    project_dot_env : Path | None
        Path to a project-specific .env file (if any)
    api_mode: bool
        If True, skips all validation for API mode

    Returns
    -------
    FABulousSettings
        The initialized FABulousSettings instance
    """
    global _context_instance

    # Gather .env files in priority order
    env_files: list[Path] = []

    if api_mode:
        logger.debug("API mode: skipping all validation")
        return FABulousSettings.model_construct()

    # 1. User config .env file (global)
    user_config_env = FAB_USER_CONFIG_DIR / ".env"
    if user_config_env.exists():
        env_files.append(user_config_env)
        logger.debug(f"Loading user config .env file from {user_config_env}")

    # 2. User-provided global .env file
    if global_dot_env is not None and global_dot_env.exists():
        env_files.append(global_dot_env)
        logger.info(f"Loading global .env file from {global_dot_env}")
    else:
        if global_dot_env is not None:
            logger.warning(
                f"Explicit Global .env file: {global_dot_env} is provided, "
                "but this is not found, this entry is ignored"
            )

    # 3. cwd project dir .env
    if project_dir is None and (Path().cwd() / ".FABulous" / ".env").exists():
        env_files.append(Path().cwd() / ".FABulous" / ".env")
        logger.debug("Loading project .env file from cwd")

    # 4. explicit project dir .env
    if project_dir is not None and (project_dir / ".FABulous" / ".env").exists():
        env_files.append(project_dir / ".FABulous" / ".env")
        logger.debug(f"Loading project .env file from project_dir: {project_dir}")

    # 5. User-provided project .env file (highest .env priority)
    if project_dot_env and project_dot_env.exists():
        env_files.append(project_dot_env)
        logger.info(f"Loading project .env file from {project_dot_env}")
    else:
        if project_dot_env is not None:
            logger.warning(
                f"Explicit project .env file: {project_dot_env} is provided, "
                "but this is not found, this entry is ignored"
            )

    if project_dir:
        _context_instance = FABulousSettings(
            proj_dir=project_dir, _env_file=tuple(env_files)
        )
    else:
        _context_instance = FABulousSettings(_env_file=tuple(env_files))

    return _context_instance


def get_context() -> FABulousSettings:
    """Get the global FABulous context.

    Returns
    -------
    FABulousSettings
        The current FABulousSettings instance
    """
    global _context_instance

    if _context_instance is None:
        _context_instance = init_context(api_mode=True)
    return _context_instance


def reset_context() -> None:
    """Reset the global context (primarily for testing)."""
    global _context_instance
    _context_instance = None
    logger.debug("FABulous context reset")


def add_var_to_global_env(key: str, value: str) -> None:
    """Add or update a key-value pair to the global .env file.

    Parameters
    ----------
    key: str
        The environment variable key to add or update.
    value: str
        The value to set for the environment variable.
    """
    # Use user config directory for global .env file
    user_config_dir = FAB_USER_CONFIG_DIR

    if not user_config_dir.exists():
        logger.info(f"Creating user config directory at {user_config_dir}")
        user_config_dir.mkdir(parents=True, exist_ok=True)

    env_file = user_config_dir / ".env"
    if not env_file.exists():
        env_file.touch()
    set_key(env_file, key, value)

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

    yosys_path: Path | None = None
    nextpnr_path: Path | None = None
    iverilog_path: Path | None = None
    vvp_path: Path | None = None
    ghdl_path: Path | None = None
    fabulator_root: Path | None = None
    oss_cad_suite: Path | None = None

    proj_dir: Path = Field(default_factory=Path.cwd)
    proj_lang: str = "verilog"
    model_pack: Path | None = None
    switch_matrix_debug_signal: bool = False
    proj_version_created: Version = Version("0.0.1")
    proj_version: Version = Version(meta_version("FABulous-FPGA"))
    version: Version = Field(
        default=Version(meta_version("FABulous-FPGA")),
        deprecated=True,
        description="Deprecated, use proj_version instead",
    )

    @field_validator("proj_version", "proj_version_created", "version", mode="before")
    @classmethod
    def parse_version_str(cls, value: str | Version) -> Version:
        """Parse version from string or Version object."""
        if isinstance(value, str):
            return Version(value)
        return value

    @field_validator("model_pack", mode="after")
    @classmethod
    def parse_model_pack(cls, value: Path | None, info: ValidationInfo) -> Path | None:  # type: ignore[override]
        """Validate and normalise model_pack path based on project language.

        Uses already-validated proj_lang from info.data when available. Accepts None /
        empty string to mean unset.
        """

        proj_lang = info.data.get("proj_lang")
        if value is None or value == "":
            if p := info.data.get("proj_dir"):
                p = Path(p)
            else:
                raise ValueError("Project directory is not set.")
            if proj_lang == HDLType.VHDL:
                mp = p / "Fabric" / "my_lib.vhdl"
                if mp.exists():
                    logger.warning(
                        f"Model pack path is not set. Guessing model pack as: {mp}"
                    )
                    return mp
                mp = p / "Fabric" / "model_pack.vhdl"
                if mp.exists():
                    logger.warning(
                        f"Model pack path is not set. Guessing model pack as: {mp}"
                    )
                    return mp
                logger.warning(
                    "Cannot find a suitable model pack. "
                    "This might lead to error if not set."
                )

            if proj_lang in {HDLType.VERILOG, HDLType.SYSTEM_VERILOG}:
                mp = p / "Fabric" / "models_pack.v"
                if mp.exists():
                    logger.warning(
                        f"Model pack path is not set. Guessing model pack as: {mp}"
                    )
                    return mp
                logger.warning(
                    "Cannot find a suitable model pack. "
                    "This might lead to error if not set."
                )

            return None

        # Retrieve previously validated proj_lang (falls back to default enum value)
        try:
            # If provided as string earlier but not validated yet
            if isinstance(proj_lang, str):
                proj_lang = HDLType[proj_lang.upper()]
        except KeyError:
            raise ValueError(
                "Invalid project language while validating model_pack"
            ) from None

        if proj_lang in {
            HDLType.VERILOG,
            HDLType.SYSTEM_VERILOG,
        } and value.suffix not in {".v", ".sv"}:
            raise ValueError(
                "Model pack for Verilog/System Verilog must be a .v or .sv file"
            )
        if proj_lang == HDLType.VHDL and value.suffix not in {".vhdl", ".vhd"}:
            raise ValueError("Model pack for VHDL must be a .vhdl or .vhd file")
        return value

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
        cls, value: Path | None, info: ValidationInfo
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
            f"{tool} not found in PATH during settings initialisation. "
            f"Some features may be unavailable."
        )
        return None


# Module-level singleton pattern for settings management
_context_instance: FABulousSettings | None = None


def init_context(
    project_dir: Path | None = None,
    global_dot_env: Path | None = None,
    project_dot_env: Path | None = None,
) -> FABulousSettings:
    """Initialize the global FABulous context with settings.

    This function gathers .env files and lets the pydantic-settings system handle
    project directory resolution.

    Args:
        global_dot_env: Global .env file path
        project_dot_env: Project .env file path
        explicit_project_dir: Explicitly provided project directory (highest priority)

    Returns:
        The initialized FABulousSettings instance
    """
    global _context_instance

    # Gather .env files in priority order
    env_files: list[Path] = []

    # 1. User config .env file (global)
    user_config_env = FAB_USER_CONFIG_DIR / ".env"
    if user_config_env.exists():
        env_files.append(user_config_env)

    # 2. User-provided global .env file
    if global_dot_env:
        if global_dot_env.exists():
            env_files.append(global_dot_env)
        else:
            logger.warning(
                f"Global .env file not found: {global_dot_env} this is ignored"
            )
    if global_dot_env and global_dot_env.exists():
        env_files.append(global_dot_env)
    elif global_dot_env is not None:
        logger.warning(
            f"Global .env file not found: {global_dot_env} this entry is ignored"
        )

    # 3. cwd project dir .env
    if project_dir is None:
        if (Path().cwd() / ".FABulous" / ".env").exists():
            env_files.append(Path().cwd() / ".FABulous" / ".env")
        elif project_dir is not None:
            logger.warning(
                f"Project .env file not found: {Path().cwd() / '.FABulous' / '.env'} "
                f"this entry is ignored"
            )

    # 4. explicit project dir .env
    if project_dir is not None and (project_dir / ".FABulous" / ".env").exists():
        env_files.append(project_dir / ".FABulous" / ".env")
    elif project_dir is not None:
        logger.warning(
            f"Project .env file not found: {project_dir / '.FABulous' / '.env'} "
            f"this entry is ignored"
        )

    # 5. User-provided project .env file (highest .env priority)
    if project_dot_env and project_dot_env.exists():
        env_files.append(project_dot_env)
        logger.info(f"Loading project .env file from {project_dot_env}")
    elif project_dot_env is not None:
        logger.warning(
            f"Project .env file not found: {project_dot_env} this entry is ignored"
        )

    if project_dir:
        _context_instance = FABulousSettings(
            proj_dir=project_dir, _env_file=tuple(env_files)
        )
    else:
        _context_instance = FABulousSettings(_env_file=tuple(env_files))

    logger.debug("FABulous context initialized")
    return _context_instance


def get_context() -> FABulousSettings:
    """Get the global FABulous context.

    Returns
    -------
        FABulousSettings:
            The current FABulousSettings instance

    Raises
    ------
        RuntimeError: If context has not been initialized with init_context()
    """
    global _context_instance

    if _context_instance is None:
        raise RuntimeError(
            "FABulous context not initialized. Call init_context() first."
        )

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
    Raises
    ------
        RuntimeError
            If the user config directory is not set.
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

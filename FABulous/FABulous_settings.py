import os
from importlib.metadata import version
from pathlib import Path
from shutil import which

from loguru import logger
from packaging.version import Version
from pydantic import field_validator
from pydantic_core.core_schema import FieldValidationInfo  # type: ignore
from pydantic_settings import BaseSettings, SettingsConfigDict


class FABulousSettings(BaseSettings):
    """Application settings.

    Tool paths are resolved lazily during validation so that environment variable setup
    (including PATH updates for oss-cad-suite) can occur beforehand.
    """

    model_config = SettingsConfigDict(env_prefix="FAB_", case_sensitive=False, extra="allow")

    root: Path = Path()
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

    # CLI-specific options (previously in FABulousCliSettings)
    verbose: int = 0
    debug: bool = False
    log_file: Path | None = None
    force: bool = False

    # Script execution options
    fabulous_script: Path | None = None
    tcl_script: Path | None = None
    commands: str | None = None

    # Project creation options
    create_project: bool = False
    install_oss_cad_suite: bool = False

    # Version and help options
    update_project_version: bool = False

    # Output directory for metadata
    metadata_dir: str = ".FABulous"

    @field_validator("proj_version", "proj_version_created", mode="before")
    @classmethod
    def parse_version_str(cls, value: str | Version) -> Version:
        """Parse version from string or Version object."""
        if isinstance(value, str):
            return Version(value)
        return value

    @field_validator("model_pack", mode="before")
    @classmethod
    def parse_model_pack(cls, value: str | Path | None, info: FieldValidationInfo) -> Path | None:  # type: ignore[override]
        """Validate and normalise model_pack path based on project language.

        Uses already-validated proj_lang from info.data when available. Accepts None /
        empty string to mean unset.
        """
        proj_lang = info.data.get("proj_lang")
        if value in (None, ""):
            p = Path(info.data["proj_dir"])
            if proj_lang == HDLType.VHDL:
                mp = p / "Fabric" / "my_lib.vhdl"
                if mp.exists():
                    logger.warning(f"Model pack path is not set. Guessing model pack as: {mp}")
                    return mp
                mp = p / "Fabric" / "model_pack.vhdl"
                if mp.exists():
                    logger.warning(f"Model pack path is not set. Guessing model pack as: {mp}")
                    return mp
                logger.warning("Cannot find a suitable model pack. This might lead to error if not set.")

            if proj_lang in {HDLType.VERILOG, HDLType.SYSTEM_VERILOG}:
                mp = p / "Fabric" / "models_pack.v"
                if mp.exists():
                    logger.warning(f"Model pack path is not set. Guessing model pack as: {mp}")
                    return mp
                logger.warning("Cannot find a suitable model pack. This might lead to error if not set.")

        path = Path(str(value))
        # Retrieve previously validated proj_lang (falls back to default enum value)
        try:
            # If provided as string earlier but not validated yet
            if isinstance(proj_lang, str):
                proj_lang = HDLType[proj_lang.upper()]
        except KeyError:
            raise ValueError("Invalid project language while validating model_pack") from None

        if proj_lang in {HDLType.VERILOG, HDLType.SYSTEM_VERILOG}:
            if path.suffix not in {".v", ".sv"}:
                raise ValueError("Model pack for Verilog/System Verilog must be a .v or .sv file")
        elif proj_lang == HDLType.VHDL and path.suffix not in {".vhdl", ".vhd"}:
            raise ValueError("Model pack for VHDL must be a .vhdl or .vhd file")
        return path

    @field_validator("root", mode="after")
    @classmethod
    def is_dir(cls, value: Path | None) -> Path | None:
        """Check if inputs is a directory."""
        if value is None:
            return None
        if not value.is_dir():
            raise ValueError(f"{value} is not a valid directory")
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
    def resolve_tool_paths(cls, value: Path | None, info: FieldValidationInfo) -> Path | None:  # type: ignore[override]
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

        logger.warning(f"{tool} not found in PATH during settings initialisation. Some features may be unavailable.")
        return None

    # CLI-specific validators
    @field_validator("fabulous_script", "tcl_script", mode="before")
    @classmethod
    def validate_script_paths(cls, value: str | Path | None) -> Path | None:
        """Convert script paths to Path objects but don't validate existence yet.

        File existence will be validated at execution time to maintain backward
        compatibility with legacy argument handling.
        """
        if value is None:
            return None
        if isinstance(value, str):
            value = Path(value)
        return value.absolute()

    @field_validator("log_file", mode="before")
    @classmethod
    def validate_log_file(cls, value: str | Path | None) -> Path | None:
        """Validate log file path, creating parent directories if needed."""
        if value is None:
            return None
        if isinstance(value, str):
            value = Path(value)
        # Ensure parent directory exists
        value.parent.mkdir(parents=True, exist_ok=True)
        return value.absolute()


# Module-level singleton pattern for settings management
_context_instance: FABulousSettings | None = None


def init_context(
    fab_root: Path,
    project_dir: Path | None = None,
    global_dot_env: Path | None = None,
    project_dot_env: Path | None = None,
) -> FABulousSettings:
    """Initialize the global FABulous context with settings.

    This should be called once at application startup to configure the global settings.
    Subsequent calls will override the existing context.

    Args:
        model: Pydantic model with settings (preferred approach)
        project_dir: Project directory path (legacy approach)
        global_dot_env: Global .env file path (legacy approach)
        project_dot_env: Project .env file path (legacy approach)
        **kwargs: Additional settings parameters (legacy approach)

    Returns:
        The initialized FABulousSettings instance
    """
    global _context_instance
    # Resolve .env files in priority order
    env_files: list[Path] = []

    fab_dir = Path(fab_root)
    # Check FABulous directory first
    if fab_dir.joinpath(".env").exists():
        env_files.append(fab_dir.joinpath(".env"))
    # Check parent directory as fallback
    elif fab_dir.parent.joinpath(".env").exists():
        env_files.append(fab_dir.parent.joinpath(".env"))

    # 2. User-provided global .env file
    if global_dot_env:
        if global_dot_env.exists():
            env_files.append(global_dot_env)
        else:
            logger.warning(f"Global .env file not found: {global_dot_env} this is ignored")

    # 3. Default project .env files
    if project_dir:
        fab_proj_dir = os.getenv("FAB_PROJ_DIR", str(project_dir))
        if fab_proj_dir:
            fab_project_dir = Path(fab_proj_dir) / ".FABulous"

            # project_dir/.env (lower priority)
            if fab_project_dir.parent.joinpath(".env").exists():
                env_files.append(fab_project_dir.parent.joinpath(".env"))

            # .FABulous/.env (higher priority)
            if fab_project_dir.joinpath(".env").exists():
                env_files.append(fab_project_dir.joinpath(".env"))

    # 4. User-provided project .env file (highest .env priority)
    if project_dot_env and project_dot_env.exists():
        env_files.append(project_dot_env)

    _context_instance = FABulousSettings(_env_file=tuple(env_files))
    logger.debug("FABulous context initialized")
    return _context_instance


def get_context() -> FABulousSettings:
    """Get the global FABulous context.

    Returns:
        The current FABulousSettings instance

    Raises:
        RuntimeError: If context has not been initialized with init_context()
    """
    global _context_instance

    if _context_instance is None:
        raise RuntimeError("FABulous context not initialized. Call init_context() first.")

    return _context_instance


def reset_context() -> None:
    """Reset the global context (primarily for testing)."""
    global _context_instance
    _context_instance = None
    logger.debug("FABulous context reset")

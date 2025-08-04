from importlib.metadata import version
from pathlib import Path
from shutil import which

from packaging.version import Version
from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


def get_tools_path(tool: str) -> Path:
    """Get the path to a tool."""
    tool_path = which(tool)
    if tool_path is None:
        raise FileNotFoundError(f"{tool} not found in PATH.")
    return Path(tool_path).resolve()


class FABulousSettings(BaseSettings):
    """Application settings."""

    model_config = SettingsConfigDict(env_prefix="FAB_", case_sensitive=False)

    root: Path = Path(__file__).parent.parent.resolve()
    yosys_path: Path = get_tools_path("yosys")
    nextpnr_path: Path = get_tools_path("nextpnr-generic")
    iverilog_path: Path = get_tools_path("iverilog")
    vvp_path: Path = get_tools_path("vvp")
    fabulator_root: Path | None = None
    proj_dir: Path = Path.cwd()
    # FAB_OSS_CAD_SUITE
    fab_proj_version_created: Version = Version("0.0.1")
    fab_proj_version: Version = Version(version("FABulous-FPGA"))

    fab_proj_lang: str = "verilog"
    fab_switch_matrix_debug_signal: bool = False

    @field_validator("FAB_ROOT", mode="after")
    @classmethod
    def is_dir(cls, value: Path) -> bool:
        """Check if inputs is a directory."""
        return value.is_dir()

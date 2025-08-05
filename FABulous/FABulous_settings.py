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
    proj_dir: Path = Path.cwd()
    fabulator_root: Path | None = None
    oss_cad_suite: Path | None = None
    proj_version_created: Version = Version("0.0.1")
    proj_version: Version = Version(version("FABulous-FPGA"))

    proj_lang: str = "verilog"
    switch_matrix_debug_signal: bool = False

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

    @field_validator("root", mode="after")
    @classmethod
    def is_dir(cls, value: Path) -> bool:
        """Check if inputs is a directory."""
        return value.is_dir()

    @field_validator("proj_lang", mode="after")
    @classmethod
    def validate_proj_lang(cls, value: str) -> str:
        """Validate the project language."""
        if value not in ["verilog", "vhdl"]:
            raise ValueError("Project language must be either 'verilog' or 'vhdl'.")
        return value

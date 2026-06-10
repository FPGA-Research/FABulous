"""Core data models for the Architecture synthesizer.

This module centralizes enums, dataclasses, and JSON helper utilities used by parser,
mapper, transform, and report layers.
"""

from pathlib import Path

from pydantic import BaseModel, ConfigDict


class FabulousArchitectureConfig(BaseModel):
    """Configuration parameters for the FABulous architecture mapping process."""

    model_config = ConfigDict(strict=False, validate_assignment=True, extra="forbid")

    hdl_files: list[Path]
    top_module: str
    allow_resource_sharing: bool
    map_alu_macc_cells: bool
    map_ram_cells: bool
    optimize_fsm: bool
    map_io_pads: bool
    map_carry_chains: bool
    tile_output_dir: Path | None = None
    user_design_out_dir: Path | None = None

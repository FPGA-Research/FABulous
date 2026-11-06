"""Configuration of the timing characterisation and its per-macro source files.

`TimingModelConfig` is the validated JSON boundary. `resolve_sources` is the one
place where the default project paths and the per-tile overrides become the
files of one macro.
"""

from dataclasses import dataclass
from decimal import Decimal
from enum import StrEnum
from pathlib import Path

from loguru import logger
from pydantic import BaseModel, ConfigDict, Field

from fabulous.fabric_cad.timing_db import Ns
from fabulous.fabric_cad.timing_model.sdf_timing_graph import DelayType

# Substrings of directory names skipped by the default RTL search; `yosys/`
# holds synthesis blackboxes named after fabric BELs.
_RTL_EXCLUDED_DIR_PARTS = ("macro", "user_design", "Test")
_RTL_EXCLUDED_DIRS = frozenset({"yosys"})


class TimingModelMode(StrEnum):
    """Netlist the pip delays are read from.

    Attributes
    ----------
    STRUCTURAL
        The synthesised netlist. Needs no physical implementation; the delays
        are an approximation.
    PHYSICAL
        The post-layout netlist, with its parasitics when `consider_wire_delay`
        is set. Needs a finished GDS flow of each tile.
    """

    STRUCTURAL = "structural"
    PHYSICAL = "physical"


class TimingModelTileSourceFiles(BaseModel):
    """Source files of one tile or supertile that replace the project defaults.

    Attributes
    ----------
    model_config
        Pydantic configuration for the model, allowing for strict validation
        and assignment.
    rtl_files : list[Path] | Path | None
        RTL files to synthesise. A file name with `*` is a glob below its
        parent directory.
    netlist_file : Path | None
        Post-layout netlist.
    rc_file : Path | None
        Parasitics (SPEF) of the post-layout netlist.
    """

    model_config = ConfigDict(strict=False, validate_assignment=True, extra="forbid")

    rtl_files: list[Path] | Path | None = None
    netlist_file: Path | None = None
    rc_file: Path | None = None


class TimingModelConfig(BaseModel):
    """Settings of the timing characterisation.

    Attributes
    ----------
    model_config
        Pydantic configuration for the model, allowing for strict
        validation and assignment.
    project_dir : Path
        The project directory; the default source files are found below it.
    liberty_files : list[Path] | Path
        Liberty files of the standard-cell library, for one corner.
    min_buf_cell_and_ports : str
        The minimum buffer cell and ports "cell_name input_port output_port".
    pdk_name : str | None
        The name of the PDK, for information only.
    techmap_files : list[Path] | Path | None
        Techmap files applied during synthesis.
    tiehi_cell_and_port : str | None
        The cell and port used for tie-high connections "cell_name port_name".
    tielo_cell_and_port : str | None
        The cell and port used for tie-low connections "cell_name port_name".
    custom_per_tile_source_files : dict[str, TimingModelTileSourceFiles] | None
        Source files that replace the project defaults, by tile or supertile
        name.
    mode : TimingModelMode
        Netlist the pip delays are read from.
    consider_wire_delay : bool
        Whether physical mode reads the parasitics of the post-layout netlist.
    delay_type_str : DelayType
        How the delay triples of an SDF entry reduce to one pip delay.
    delay_scaling_factor : Decimal
        Factor applied to every characterised delay. The scaled delay is
        exact, not rounded.
    """

    model_config = ConfigDict(strict=False, validate_assignment=True, extra="forbid")

    project_dir: Path
    liberty_files: list[Path] | Path
    min_buf_cell_and_ports: str
    pdk_name: str | None = None
    techmap_files: list[Path] | Path | None = None
    tiehi_cell_and_port: str | None = None
    tielo_cell_and_port: str | None = None
    custom_per_tile_source_files: dict[str, TimingModelTileSourceFiles] | None = None
    mode: TimingModelMode = Field(default=TimingModelMode.PHYSICAL)
    consider_wire_delay: bool = Field(default=True)
    delay_type_str: DelayType = Field(default=DelayType.MAX_ALL)
    delay_scaling_factor: Decimal = Field(default=Decimal(1))


@dataclass(frozen=True, slots=True)
class StructuralSources:
    """Source files of a macro characterised from its synthesised netlist.

    Attributes
    ----------
    rtl_files : tuple[Path, ...]
        RTL files to synthesise.
    """

    rtl_files: tuple[Path, ...]


@dataclass(frozen=True, slots=True)
class PhysicalSources:
    """Source files of a macro characterised from its post-layout netlist.

    Attributes
    ----------
    rtl_files : tuple[Path, ...]
        RTL files to synthesise; BEL timing always reads the synthesised netlist.
    netlist_file : Path
        Post-layout netlist.
    spef_files : tuple[Path, ...]
        Parasitics of the post-layout netlist; empty to ignore wire delay.
    """

    rtl_files: tuple[Path, ...]
    netlist_file: Path
    spef_files: tuple[Path, ...]


type MacroSources = StructuralSources | PhysicalSources


def _project_rtl_files(project_dir: Path) -> list[Path]:
    """Return every Verilog file below `project_dir` that a tile may need.

    Parameters
    ----------
    project_dir : Path
        The project directory.

    Returns
    -------
    list[Path]
        Verilog files, in directory walk order.
    """
    files: list[Path] = []
    for directory, subdirectories, names in project_dir.walk():
        subdirectories[:] = [
            name
            for name in subdirectories
            if name not in _RTL_EXCLUDED_DIRS
            and not any(part in name for part in _RTL_EXCLUDED_DIR_PARTS)
        ]
        files.extend(directory / name for name in names if name.endswith(".v"))
    return files


def resolve_sources(config: TimingModelConfig, *, top: str) -> MacroSources:
    """Return the source files of macro `top`, overrides applied.

    The defaults are every Verilog file of the project and the GDS flow
    outputs below `Tile/{top}/macro/final_views`. An entry for `top` in
    `custom_per_tile_source_files` replaces each default it sets.

    Parameters
    ----------
    config : TimingModelConfig
        Characterisation settings.
    top : str
        Name of the tile or supertile module.

    Returns
    -------
    MacroSources
        The files of the macro; physical sources only in physical mode.

    Raises
    ------
    FileNotFoundError
        If a resolved file does not exist.
    """
    overrides = (config.custom_per_tile_source_files or {}).get(
        top, TimingModelTileSourceFiles()
    )
    rtl_files = _project_rtl_files(config.project_dir)
    if overrides.rtl_files:
        targets = (
            overrides.rtl_files
            if isinstance(overrides.rtl_files, list)
            else [overrides.rtl_files]
        )
        rtl_files = []
        for target in targets:
            if "*" in target.name:
                rtl_files.extend(target.parent.rglob(target.name))
            else:
                rtl_files.append(target)
        logger.info(
            f"Using RTL Verilog files for tile {top}:"
            f"{'\n  '.join(map(str, ['', *rtl_files]))}"
        )
    sources: MacroSources
    match config.mode:
        case TimingModelMode.STRUCTURAL:
            sources = StructuralSources(rtl_files=tuple(rtl_files))
        case TimingModelMode.PHYSICAL:
            final_views = config.project_dir / "Tile" / top / "macro" / "final_views"
            netlist_file = overrides.netlist_file or final_views / "nl" / f"{top}.nl.v"
            spef_files: tuple[Path, ...] = ()
            if config.consider_wire_delay:
                spef_files = (
                    overrides.rc_file
                    or final_views / "spef" / "nom" / f"{top}.nom.spef",
                )
            sources = PhysicalSources(
                rtl_files=tuple(rtl_files),
                netlist_file=netlist_file,
                spef_files=spef_files,
            )
    files = [*sources.rtl_files]
    if isinstance(sources, PhysicalSources):
        files += [sources.netlist_file, *sources.spef_files]
    for path in files:
        if not path.is_file():
            raise FileNotFoundError(f"Timing source file of {top!r} not found: {path}")
    return sources


def scale_delay(delay: Decimal, *, factor: Decimal) -> Ns:
    """Return `delay` scaled by `factor`, exactly.

    Parameters
    ----------
    delay : Decimal
        Unscaled delay in nanoseconds.
    factor : Decimal
        The configured `delay_scaling_factor`.

    Returns
    -------
    Ns
        The scaled delay.
    """
    scaled = delay * factor
    # The nextpnr timing file format: no trailing zeros, one decimal place at
    # least.
    scaled = scaled.normalize()
    if scaled == scaled.to_integral_value():
        scaled = scaled.quantize(Decimal("0.1"))
    return Ns(scaled)

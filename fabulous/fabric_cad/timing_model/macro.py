"""Synthesis and static timing analysis of one tile macro.

`run_macro_tools` is the only step of the characterisation that runs tools.
Its result is the immutable input of the pure pip and BEL extraction.
"""

from dataclasses import dataclass
from pathlib import Path

from loguru import logger

from fabulous.fabric_cad.timing_model.config import (
    MacroSources,
    PhysicalSources,
    StructuralSources,
    TimingModelConfig,
)
from fabulous.fabric_cad.timing_model.netlist import HierPath, NetlistIndex
from fabulous.fabric_cad.timing_model.sdf_timing_graph import SdfTimingGraph
from fabulous.fabric_definition.fabric import Fabric
from fabulous.fabric_definition.tile import Tile
from fabulous.tools.opensta import OpenStaTool
from fabulous.tools.yosys import YosysTool


@dataclass(frozen=True, slots=True)
class TileMacro:
    """A tile type and the module that is synthesised to time it.

    Attributes
    ----------
    tile : Tile
        The tile type.
    top : str
        The tile module, or the supertile module that holds the tile.
    scope : HierPath
        Path of the tile instance inside `top`; empty when `top` is the tile.
    """

    tile: Tile
    top: str
    scope: HierPath


def tile_macro(fabric: Fabric, tile_name: str) -> TileMacro:
    """Return the macro of tile type `tile_name`.

    A tile inside a supertile is timed in the supertile module.

    Parameters
    ----------
    fabric : Fabric
        The fabric.
    tile_name : str
        Name of the tile type.

    Returns
    -------
    TileMacro
        The macro of the tile type.

    Raises
    ------
    ValueError
        If the supertile places the tile more than once, so the tile has no
        single instance to characterise.
    """
    tile = fabric.tileDic[tile_name]
    super_tile = fabric.get_super_tile_containing(tile_name)
    if super_tile is None:
        return TileMacro(tile=tile, top=tile_name, scope=())
    placements = [
        (x, y)
        for y, row in enumerate(super_tile.tileMap)
        for x, member in enumerate(row)
        if member is not None and member.name == tile_name
    ]
    if len(placements) != 1:
        raise ValueError(
            f"SuperTile {super_tile.name!r} places tile "
            f"{tile_name!r} {len(placements)} times."
        )
    x, y = placements[0]
    return TileMacro(
        tile=tile, top=super_tile.name, scope=(super_tile.tile_instance_name(x, y),)
    )


@dataclass(frozen=True, slots=True)
class TimedNetlist:
    """A netlist and the SDF timing graph of the same netlist.

    Attributes
    ----------
    netlist : NetlistIndex
        Hierarchy of the netlist.
    graph : SdfTimingGraph
        Timing graph of the netlist.
    """

    netlist: NetlistIndex
    graph: SdfTimingGraph


@dataclass(frozen=True, slots=True)
class StructuralMacro:
    """Timing of a macro from its synthesised netlist only.

    Attributes
    ----------
    synth : TimedNetlist
        The hierarchical synthesised netlist and its timing.
    """

    synth: TimedNetlist


@dataclass(frozen=True, slots=True)
class PhysicalMacro:
    """Timing of a macro from its synthesised and its post-layout netlists.

    Attributes
    ----------
    synth : TimedNetlist
        The hierarchical synthesised netlist and its timing.
    layout : SdfTimingGraph
        Timing graph of the post-layout netlist.
    """

    synth: TimedNetlist
    layout: SdfTimingGraph


type MacroTiming = StructuralMacro | PhysicalMacro


def run_macro_tools(
    config: TimingModelConfig, *, top: str, sources: MacroSources, work_dir: Path
) -> MacroTiming:
    """Synthesise macro `top` and time it with OpenSTA.

    Parameters
    ----------
    config : TimingModelConfig
        Characterisation settings: cell library and delay selection.
    top : str
        Name of the module to synthesise.
    sources : MacroSources
        Source files of the macro.
    work_dir : Path
        Existing, empty directory for the netlist and SDF files.

    Returns
    -------
    MacroTiming
        The timing of the macro, physical if `sources` are.
    """
    logger.info(f"Running synthesis and STA for macro {top}")
    liberty = config.liberty_files
    liberty_files = [liberty] if isinstance(liberty, Path) else liberty
    techmap = config.techmap_files
    if techmap is None:
        techmap_files: list[Path] = []
    elif isinstance(techmap, Path):
        techmap_files = [techmap]
    else:
        techmap_files = techmap

    synth_netlist_file = work_dir / "synth.v"
    YosysTool.synthesize_gate_level(
        verilog_files=list(sources.rtl_files),
        liberty_files=liberty_files,
        top_name=top,
        netlist_file=synth_netlist_file,
        techmap_files=techmap_files,
        tiehi_cell_and_port=config.tiehi_cell_and_port,
        tielo_cell_and_port=config.tielo_cell_and_port,
        min_buf_cell_and_ports=config.min_buf_cell_and_ports,
    )
    synth_sdf_file = work_dir / "synth.sdf"
    OpenStaTool.write_sdf(
        netlist_file=synth_netlist_file,
        liberty_files=liberty_files,
        top_name=top,
        spef_files=[],
        sdf_file=synth_sdf_file,
    )
    synth = TimedNetlist(
        netlist=NetlistIndex.read(synth_netlist_file, top=top),
        graph=SdfTimingGraph(synth_sdf_file, config.delay_type_str),
    )
    match sources:
        case StructuralSources():
            return StructuralMacro(synth=synth)
        case PhysicalSources(netlist_file=netlist_file, spef_files=spef_files):
            layout_sdf_file = work_dir / "physical.sdf"
            OpenStaTool.write_sdf(
                netlist_file=netlist_file,
                liberty_files=liberty_files,
                top_name=top,
                spef_files=list(spef_files),
                sdf_file=layout_sdf_file,
            )
            return PhysicalMacro(
                synth=synth,
                layout=SdfTimingGraph(layout_sdf_file, config.delay_type_str),
            )

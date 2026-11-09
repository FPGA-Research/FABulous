"""Synthesis and static timing analysis of one tile or supertile macro.

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
from fabulous.fabric_cad.timing_model.netlist import NetlistIndex
from fabulous.fabric_cad.timing_model.sdf_timing_graph import SdfTimingGraph
from fabulous.fabric_definition.fabric import Fabric
from fabulous.fabric_definition.supertile import SuperTile
from fabulous.fabric_definition.tile import Tile
from fabulous.tools.opensta import OpenStaTool
from fabulous.tools.yosys import YosysTool


@dataclass(frozen=True, slots=True)
class TileMacro:
    """A tile type synthesised as its own module.

    Attributes
    ----------
    tile : Tile
        The tile type.
    """

    tile: Tile

    @property
    def top(self) -> str:
        """The module that is synthesised: the tile module."""
        return self.tile.name


@dataclass(frozen=True, slots=True)
class MemberTile:
    """A tile type inside a supertile.

    Attributes
    ----------
    tile : Tile
        The tile type.
    instance : str
        Instance name of the tile in the supertile module.
    """

    tile: Tile
    instance: str


@dataclass(frozen=True, slots=True)
class SuperTileMacro:
    """A supertile synthesised as one module with all its member tiles.

    Attributes
    ----------
    super_tile : SuperTile
        The supertile type.
    members : tuple[MemberTile, ...]
        Each member tile type and its instance, in `tileMap` row-major order.
    """

    super_tile: SuperTile
    members: tuple[MemberTile, ...]

    @property
    def top(self) -> str:
        """The module that is synthesised: the supertile module."""
        return self.super_tile.name


type Macro = TileMacro | SuperTileMacro


def fabric_macros(fabric: Fabric) -> list[Macro]:
    """Return one macro per module that is synthesised to time `fabric`.

    Each supertile is one macro that holds its member tiles; every other tile
    type is its own macro.

    Parameters
    ----------
    fabric : Fabric
        The fabric.

    Returns
    -------
    list[Macro]
        The supertile macros in `superTileDic` order, then the tile macros in
        `tileDic` order.

    Raises
    ------
    ValueError
        If a tile type appears twice in one supertile or in two supertiles,
        so it has no single instance to characterise.
    """
    macros: list[Macro] = []
    owners: dict[str, str] = {}
    for super_tile in fabric.superTileDic.values():
        members: list[MemberTile] = []
        for y, row in enumerate(super_tile.tileMap):
            for x, tile in enumerate(row):
                if tile is None:
                    continue
                if owners.get(tile.name) == super_tile.name:
                    raise ValueError(
                        f"Supertile {super_tile.name!r} places tile {tile.name!r} "
                        "more than once."
                    )
                if tile.name in owners:
                    raise ValueError(
                        f"Tile {tile.name!r} is in supertile {owners[tile.name]!r} "
                        f"and in supertile {super_tile.name!r}."
                    )
                owners[tile.name] = super_tile.name
                members.append(
                    MemberTile(tile=tile, instance=super_tile.tile_instance_name(x, y))
                )
        macros.append(SuperTileMacro(super_tile=super_tile, members=tuple(members)))
    macros.extend(
        TileMacro(tile=tile)
        for name, tile in fabric.tileDic.items()
        if name not in owners
    )
    return macros


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
    layout_netlist : NetlistIndex
        The flat post-layout netlist, which finds the cells of each member of a
        supertile macro.
    """

    synth: TimedNetlist
    layout: SdfTimingGraph
    layout_netlist: NetlistIndex


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
                layout_netlist=NetlistIndex.read(netlist_file, top=top),
            )

"""Characterise the timing of a fabric onto its BELs and into a `TimingDb`."""

import tempfile
from decimal import Decimal
from pathlib import Path

from loguru import logger

from fabulous.fabric_cad.gen_npnr_model import CLOCK_DELAY, tile_copies, tile_pips
from fabulous.fabric_cad.timing_db import (
    Pip,
    PipTiming,
    SwitchPip,
    TimingDb,
    switch_pips,
)
from fabulous.fabric_cad.timing_model.bels import characterize_bel
from fabulous.fabric_cad.timing_model.config import TimingModelConfig, resolve_sources
from fabulous.fabric_cad.timing_model.macro import (
    Macro,
    MacroTiming,
    SuperTileMacro,
    TileMacro,
    fabric_macros,
    run_macro_tools,
)
from fabulous.fabric_cad.timing_model.netlist import HierPath
from fabulous.fabric_cad.timing_model.pips import characterize_pips
from fabulous.fabric_definition.bel import Bel
from fabulous.fabric_definition.fabric import Fabric
from fabulous.fabric_definition.timing import BelArcs, Ns


def _tile_scopes(macros: list[Macro]) -> dict[str, tuple[str, HierPath]]:
    """Return the macro top and the instance path of each tile type.

    Parameters
    ----------
    macros : list[Macro]
        The macros of the fabric.

    Returns
    -------
    dict[str, tuple[str, HierPath]]
        Top module of the macro that times each tile type, and the path of the
        tile in it; the path is empty when the tile is the top.
    """
    scopes: dict[str, tuple[str, HierPath]] = {}
    for macro in macros:
        match macro:
            case TileMacro(tile=tile):
                scopes[tile.name] = (macro.top, ())
            case SuperTileMacro(members=members):
                for member in members:
                    scopes[member.tile.name] = (macro.top, (member.instance,))
    return scopes


def _characterize_pips(
    fabric: Fabric,
    *,
    macros: list[Macro],
    timings: dict[str, MacroTiming],
    scale: Decimal,
) -> PipTiming:
    """Return the delay of every pip of every placed tile and supertile type.

    A member tile of a supertile is timed in its instance inside the supertile
    macro; a supertile switch matrix at the top of the supertile macro.

    Parameters
    ----------
    fabric : Fabric
        The fabric.
    macros : list[Macro]
        The macros of the fabric.
    timings : dict[str, MacroTiming]
        Timing of each macro, by top module.
    scale : Decimal
        The configured `delay_scaling_factor`.

    Returns
    -------
    PipTiming
        Characterised pip delays.
    """
    # Placements of one tile type differ in their SJUMP wires.
    placed_pips: dict[str, list[Pip]] = {}
    for _, tile in fabric:
        if tile is not None:
            placed_pips.setdefault(tile.name, []).extend(tile_pips(tile))
    scopes = _tile_scopes(macros)
    tiles: dict[str, dict[Pip, Ns]] = {}
    for name, pips in placed_pips.items():
        top, scope = scopes[name]
        tiles[name] = characterize_pips(
            timings[top],
            scope=scope,
            switch_matrix=fabric.tileDic[name].switch_matrix_instance_name,
            pips=pips,
            scale=scale,
        )
    super_tiles: dict[str, dict[SwitchPip, Ns]] = {}
    for _, _, super_tile in fabric.iter_super_tile_placements():
        if super_tile.switch_matrix is None or super_tile.name in super_tiles:
            continue
        switch = list(switch_pips(super_tile.switch_matrix.connections))
        delays = characterize_pips(
            timings[super_tile.name],
            scope=(),
            switch_matrix=super_tile.switch_matrix_instance_name,
            pips=switch,
            scale=scale,
        )
        super_tiles[super_tile.name] = {pip: delays[pip] for pip in switch}
    return PipTiming(tiles=tiles, super_tiles=super_tiles)


def _characterize_bels(
    fabric: Fabric,
    *,
    macros: list[Macro],
    timings: dict[str, MacroTiming],
    scale: Decimal,
) -> list[tuple[Bel, BelArcs]]:
    """Return the arcs of every BEL of every placed tile and supertile type.

    A BEL is found by the instance name the tile or supertile generator gives
    it, in the macro that times its tile or supertile. Each BEL of a tile type
    is characterised once, and its arcs are paired with that BEL in every copy
    of the tile type.

    Parameters
    ----------
    fabric : Fabric
        The fabric.
    macros : list[Macro]
        The macros of the fabric.
    timings : dict[str, MacroTiming]
        Timing of each macro, by top module.
    scale : Decimal
        The configured `delay_scaling_factor`.

    Returns
    -------
    list[tuple[Bel, BelArcs]]
        Each BEL object of the fabric with its characterised arcs.
    """
    scopes = _tile_scopes(macros)
    tiles: dict[str, dict[str, BelArcs]] = {}
    for _, tile in fabric:
        if tile is None:
            continue
        top, scope = scopes[tile.name]
        arcs = tiles.setdefault(tile.name, {})
        for bel in tile.bels:
            if bel.instance_name not in arcs:
                arcs[bel.instance_name] = characterize_bel(
                    timings[top].synth,
                    bel,
                    instance=(*scope, bel.instance_name),
                    scale=scale,
                )
    super_tiles: dict[str, dict[str, BelArcs]] = {}
    for _, _, super_tile in fabric.iter_super_tile_placements():
        arcs = super_tiles.setdefault(super_tile.name, {})
        for bel in super_tile.bels:
            if bel.instance_name not in arcs:
                arcs[bel.instance_name] = characterize_bel(
                    timings[super_tile.name].synth,
                    bel,
                    instance=(super_tile.bel_instance_name(bel),),
                    scale=scale,
                )
    placed_super_tiles = {
        super_tile.name: super_tile
        for _, _, super_tile in fabric.iter_super_tile_placements()
    }
    return [
        (bel, tiles[tile.name][bel.instance_name])
        for tile in tile_copies(fabric)
        for bel in tile.bels
    ] + [
        (bel, super_tiles[super_tile.name][bel.instance_name])
        for super_tile in placed_super_tiles.values()
        for bel in super_tile.bels
    ]


def characterize(fabric: Fabric, config: TimingModelConfig) -> TimingDb:
    """Characterise the pip delays and BEL arcs of `fabric` with Yosys and OpenSTA.

    Each macro is synthesised and timed once: a supertile with all its member
    tiles, and every other tile type on its own. The BEL arcs are set as
    `Bel.arcs` once every macro and BEL is characterised, so a failure leaves
    the fabric unchanged. Clock arrival is not characterised; it stays
    `CLOCK_DELAY`. The tool outputs go to a temporary directory that is removed
    on return.

    Parameters
    ----------
    fabric : Fabric
        The fabric; its BEL arcs are set.
    config : TimingModelConfig
        Characterisation settings.

    Returns
    -------
    TimingDb
        Characterised pip delays of every placed tile and supertile type.
    """
    logger.info(f"Characterising tile timing, with mode: {config.mode}")
    macros = fabric_macros(fabric)
    with tempfile.TemporaryDirectory(prefix="fabulous_timing_") as work_root:
        timings: dict[str, MacroTiming] = {}
        for macro in macros:
            work_dir = Path(work_root) / macro.top
            work_dir.mkdir()
            timings[macro.top] = run_macro_tools(
                config,
                top=macro.top,
                sources=resolve_sources(config, top=macro.top),
                work_dir=work_dir,
            )
    scale = config.delay_scaling_factor
    pips = _characterize_pips(fabric, macros=macros, timings=timings, scale=scale)
    bel_arcs = _characterize_bels(fabric, macros=macros, timings=timings, scale=scale)
    for bel, arcs in bel_arcs:
        bel.arcs = arcs
    return TimingDb(pips=pips, clock_arrival=CLOCK_DELAY)

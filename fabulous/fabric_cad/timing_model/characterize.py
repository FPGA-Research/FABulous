"""Characterise the timing of a fabric into a `TimingDb`."""

import tempfile
from decimal import Decimal
from pathlib import Path

from loguru import logger

from fabulous.fabric_cad.gen_npnr_model import CLOCK_DELAY, tile_pips
from fabulous.fabric_cad.timing_db import (
    BelArcs,
    BelTiming,
    Ns,
    Pip,
    PipTiming,
    TimingDb,
    switch_pips,
)
from fabulous.fabric_cad.timing_model.bels import characterize_bel
from fabulous.fabric_cad.timing_model.config import TimingModelConfig, resolve_sources
from fabulous.fabric_cad.timing_model.macro import (
    MacroTiming,
    TileMacro,
    run_macro_tools,
    tile_macro,
)
from fabulous.fabric_cad.timing_model.pips import characterize_tile_pips
from fabulous.fabric_definition.fabric import Fabric


def _characterize_pips(
    fabric: Fabric,
    *,
    macros: dict[str, TileMacro],
    timings: dict[str, MacroTiming],
    scale: Decimal,
) -> PipTiming:
    """Return the delay of every pip of every placed tile type.

    Parameters
    ----------
    fabric : Fabric
        The fabric.
    macros : dict[str, TileMacro]
        Macro of each tile type.
    timings : dict[str, MacroTiming]
        Timing of each tile type's macro.
    scale : Decimal
        The configured `delay_scaling_factor`.

    Returns
    -------
    PipTiming
        Characterised pip delays.

    Raises
    ------
    ValueError
        If a placed supertile has switch-matrix pips, which are not characterised.
    """
    # Placements of one tile type differ in their SJUMP wires.
    placed_pips: dict[str, list[Pip]] = {}
    for _, tile in fabric:
        if tile is not None:
            placed_pips.setdefault(tile.name, []).extend(tile_pips(tile))
    tiles: dict[str, dict[Pip, Ns]] = {
        name: characterize_tile_pips(
            timings[name], macro=macros[name], pips=pips, scale=scale
        )
        for name, pips in placed_pips.items()
    }
    for _, _, super_tile in fabric.iter_super_tile_placements():
        if super_tile.switch_matrix is not None and any(
            switch_pips(super_tile.switch_matrix.connections)
        ):
            raise ValueError(
                f"Pip timing of the supertile {super_tile.name!r} switch matrix "
                "is not characterised."
            )
    return PipTiming(tiles=tiles, super_tiles={})


def _characterize_bels(
    fabric: Fabric,
    *,
    macros: dict[str, TileMacro],
    timings: dict[str, MacroTiming],
    scale: Decimal,
) -> BelTiming:
    """Return the arcs of every BEL of every placed tile and supertile type.

    A supertile BEL is characterised in the macro of the supertile's master
    tile, which is the whole supertile. A BEL is found by the instance name the
    tile or supertile generator gives it.

    Parameters
    ----------
    fabric : Fabric
        The fabric.
    macros : dict[str, TileMacro]
        Macro of each tile type.
    timings : dict[str, MacroTiming]
        Timing of each tile type's macro.
    scale : Decimal
        The configured `delay_scaling_factor`.

    Returns
    -------
    BelTiming
        Characterised BEL arcs.
    """
    tiles: dict[str, dict[str, BelArcs]] = {}
    for _, tile in fabric:
        if tile is None:
            continue
        arcs = tiles.setdefault(tile.name, {})
        for bel in tile.bels:
            if bel.instance_name not in arcs:
                arcs[bel.instance_name] = characterize_bel(
                    timings[tile.name].synth,
                    bel,
                    instance=(*macros[tile.name].scope, bel.instance_name),
                    scale=scale,
                )
    super_tiles: dict[str, dict[str, BelArcs]] = {}
    for base_fx, base_fy, super_tile in fabric.iter_super_tile_placements():
        tx_local, ty_local = super_tile.get_master_tile_coords()
        master = fabric.tile[base_fy + ty_local][base_fx + tx_local]
        arcs = super_tiles.setdefault(super_tile.name, {})
        for bel in super_tile.bels:
            if bel.instance_name not in arcs:
                arcs[bel.instance_name] = characterize_bel(
                    timings[master.name].synth,
                    bel,
                    instance=(super_tile.bel_instance_name(bel),),
                    scale=scale,
                )
    return BelTiming(tiles=tiles, super_tiles=super_tiles)


def characterize(fabric: Fabric, config: TimingModelConfig) -> TimingDb:
    """Characterise the pip delays and BEL arcs of `fabric` with Yosys and OpenSTA.

    Each tile type's macro is synthesised and timed once; a tile inside a
    supertile is timed in the supertile. Clock arrival is not characterised; it
    stays `CLOCK_DELAY`. The tool outputs go to a temporary directory that is
    removed on return.

    Parameters
    ----------
    fabric : Fabric
        The fabric.
    config : TimingModelConfig
        Characterisation settings.

    Returns
    -------
    TimingDb
        Characterised timing of every placed tile and supertile type.
    """
    logger.info(f"Characterising tile timing, with mode: {config.mode}")
    macros = {name: tile_macro(fabric, name) for name in fabric.tileDic}
    with tempfile.TemporaryDirectory(prefix="fabulous_timing_") as work_root:
        timings: dict[str, MacroTiming] = {}
        for name, macro in macros.items():
            work_dir = Path(work_root) / name
            work_dir.mkdir()
            timings[name] = run_macro_tools(
                config,
                top=macro.top,
                sources=resolve_sources(config, top=macro.top),
                work_dir=work_dir,
            )
    scale = config.delay_scaling_factor
    return TimingDb(
        pips=_characterize_pips(fabric, macros=macros, timings=timings, scale=scale),
        bels=_characterize_bels(fabric, macros=macros, timings=timings, scale=scale),
        clock_arrival=CLOCK_DELAY,
    )

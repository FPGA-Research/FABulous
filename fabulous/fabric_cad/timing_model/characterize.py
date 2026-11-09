"""Characterise the timing of a fabric onto its model."""

import tempfile
from dataclasses import replace
from decimal import Decimal
from pathlib import Path

from loguru import logger

from fabulous.fabric_cad.gen_npnr_model import (
    CLOCK_DELAY,
    switch_pips,
    tile_copies,
    tile_pips,
    wire_pips,
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
from fabulous.fabric_definition.fabric import Fabric
from fabulous.fabric_definition.timing import BelArcs, Ns, Pip, SwitchPip


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


def _characterize_tile_pips(
    fabric: Fabric,
    *,
    macros: list[Macro],
    timings: dict[str, MacroTiming],
    scale: Decimal,
) -> dict[str, dict[Pip, Ns]]:
    """Return the delay of every switch and wire pip of every tile type.

    Every tile type of the fabric is timed, placed or not, as the placeholder
    timing covers it. A member tile of a supertile is timed in its instance
    inside the supertile macro.

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
    dict[str, dict[Pip, Ns]]
        Pip delays by tile type name; the wire pips are those of every
        placement of the type.
    """
    # Placements of one tile type differ in their SJUMP wires.
    type_pips: dict[str, list[Pip]] = {
        name: list(tile_pips(tile)) for name, tile in fabric.tileDic.items()
    }
    for _, tile in fabric:
        if tile is not None:
            type_pips[tile.name].extend(tile_pips(tile))
    scopes = _tile_scopes(macros)
    delays: dict[str, dict[Pip, Ns]] = {}
    for name, pips in type_pips.items():
        top, scope = scopes[name]
        delays[name] = characterize_pips(
            timings[top],
            scope=scope,
            switch_matrix=fabric.tileDic[name].switch_matrix_instance_name,
            pips=pips,
            scale=scale,
        )
    return delays


def _characterize_super_tile_pips(
    fabric: Fabric,
    *,
    timings: dict[str, MacroTiming],
    scale: Decimal,
) -> dict[str, dict[SwitchPip, Ns]]:
    """Return the delay of every switch pip of every supertile type.

    A supertile switch matrix is timed at the top of the supertile macro.

    Parameters
    ----------
    fabric : Fabric
        The fabric.
    timings : dict[str, MacroTiming]
        Timing of each macro, by top module.
    scale : Decimal
        The configured `delay_scaling_factor`.

    Returns
    -------
    dict[str, dict[SwitchPip, Ns]]
        Pip delays by name of each supertile type that has a switch matrix.
    """
    delays: dict[str, dict[SwitchPip, Ns]] = {}
    for super_tile in fabric.superTileDic.values():
        if super_tile.switch_matrix is None:
            continue
        switch = list(switch_pips(super_tile.switch_matrix.connections))
        pip_delays = characterize_pips(
            timings[super_tile.name],
            scope=(),
            switch_matrix=super_tile.switch_matrix_instance_name,
            pips=switch,
            scale=scale,
        )
        delays[super_tile.name] = {pip: pip_delays[pip] for pip in switch}
    return delays


def _characterize_tile_bels(
    fabric: Fabric,
    *,
    macros: list[Macro],
    timings: dict[str, MacroTiming],
    scale: Decimal,
) -> dict[str, dict[str, BelArcs]]:
    """Return the arcs of every BEL of every tile type, placed or not.

    A BEL is found by the instance name the tile generator gives it, in the
    macro that times its tile.

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
    dict[str, dict[str, BelArcs]]
        BEL arcs by tile type name, then by `Bel.instance_name`.
    """
    scopes = _tile_scopes(macros)
    arcs: dict[str, dict[str, BelArcs]] = {}
    for name, tile in fabric.tileDic.items():
        top, scope = scopes[name]
        arcs[name] = {
            bel.instance_name: characterize_bel(
                timings[top].synth,
                bel,
                instance=(*scope, bel.instance_name),
                scale=scale,
            )
            for bel in tile.bels
        }
    return arcs


def _characterize_super_tile_bels(
    fabric: Fabric,
    *,
    timings: dict[str, MacroTiming],
    scale: Decimal,
) -> dict[str, dict[str, BelArcs]]:
    """Return the arcs of every BEL of every supertile type, placed or not.

    A BEL is found by the instance name the supertile generator gives it, in
    the supertile macro.

    Parameters
    ----------
    fabric : Fabric
        The fabric.
    timings : dict[str, MacroTiming]
        Timing of each macro, by top module.
    scale : Decimal
        The configured `delay_scaling_factor`.

    Returns
    -------
    dict[str, dict[str, BelArcs]]
        BEL arcs by supertile type name, then by `Bel.instance_name`.
    """
    return {
        name: {
            bel.instance_name: characterize_bel(
                timings[name].synth,
                bel,
                instance=(super_tile.bel_instance_name(bel),),
                scale=scale,
            )
            for bel in super_tile.bels
        }
        for name, super_tile in fabric.superTileDic.items()
    }


def characterize(fabric: Fabric, config: TimingModelConfig) -> None:
    """Characterise the timing of `fabric` with Yosys and OpenSTA onto the fabric.

    Each macro is synthesised and timed once: a supertile with all its member
    tiles, and every other tile type on its own. Every tile and supertile type
    is characterised once, and its BEL arcs, switch-matrix pip delays and wire
    delays are set on every copy of it only after everything is characterised,
    so a failure leaves the fabric unchanged. Clock arrival is not
    characterised; it is set to `CLOCK_DELAY`. The tool outputs go to a
    temporary directory that is removed on return.

    Parameters
    ----------
    fabric : Fabric
        The fabric; its timing is set.
    config : TimingModelConfig
        Characterisation settings.
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
    tile_delays = _characterize_tile_pips(
        fabric, macros=macros, timings=timings, scale=scale
    )
    super_tile_delays = _characterize_super_tile_pips(
        fabric, timings=timings, scale=scale
    )
    tile_arcs = _characterize_tile_bels(
        fabric, macros=macros, timings=timings, scale=scale
    )
    super_tile_arcs = _characterize_super_tile_bels(
        fabric, timings=timings, scale=scale
    )

    switch_delays = {
        name: {
            pip: tile_delays[name][pip]
            for pip in switch_pips(tile.switch_matrix.connections)
        }
        for name, tile in fabric.tileDic.items()
    }
    for tile in tile_copies(fabric):
        tile.switch_matrix = replace(
            tile.switch_matrix, pip_delays=switch_delays[tile.name]
        )
        tile.wireList = [
            replace(wire, delay=tile_delays[tile.name][pip])
            for wire, pip in wire_pips(tile)
        ]
        for bel in tile.bels:
            bel.arcs = tile_arcs[tile.name][bel.instance_name]
    for name, super_tile in fabric.superTileDic.items():
        if super_tile.switch_matrix is not None:
            super_tile.switch_matrix = replace(
                super_tile.switch_matrix, pip_delays=super_tile_delays[name]
            )
        for bel in super_tile.bels:
            bel.arcs = super_tile_arcs[name][bel.instance_name]
    fabric.clock_arrival = CLOCK_DELAY

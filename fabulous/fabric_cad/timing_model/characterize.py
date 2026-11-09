"""Characterise the timing of a fabric into a `TimingDb`."""

from loguru import logger

from fabulous.fabric_cad.gen_npnr_model import CLOCK_DELAY
from fabulous.fabric_cad.timing_db import (
    BelArcs,
    BelTiming,
    Ns,
    Pip,
    PipTiming,
    TimingDb,
    WirePip,
    ns,
    switch_pips,
)
from fabulous.fabric_cad.timing_model.FABulous_timing_model import (
    FABulousTileTimingModel,
)
from fabulous.fabric_cad.timing_model.models import TimingModelConfig
from fabulous.fabric_definition.fabric import Fabric


def _characterize_pips(
    fabric: Fabric, models: dict[str, FABulousTileTimingModel]
) -> PipTiming:
    """Return the delay of every pip of every placed tile type.

    Each tile type's pips are queried in grid order, switch pips before wire
    pips, because a physical wire delay reuses switch-matrix results the tile
    model cached while timing the switch pips.

    Parameters
    ----------
    fabric : Fabric
        The fabric.
    models : dict[str, FABulousTileTimingModel]
        Timing model of each tile type.

    Returns
    -------
    PipTiming
        Characterised pip delays.

    Raises
    ------
    ValueError
        If a placed supertile has switch-matrix pips, which are not characterised.
    """
    tiles: dict[str, dict[Pip, Ns]] = {}
    for _, tile in fabric:
        if tile is None:
            continue
        model = models[tile.name]
        delays = tiles.setdefault(tile.name, {})
        wire_pips = (WirePip(src=w.source, dst=w.destination) for w in tile.wireList)
        for pip in (*switch_pips(tile.switch_matrix.connections), *wire_pips):
            if pip not in delays:
                delays[pip] = ns(model.pip_delay(pip.src, pip.dst))
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
    fabric: Fabric, models: dict[str, FABulousTileTimingModel]
) -> BelTiming:
    """Return the arcs of every BEL of every placed tile and supertile type.

    A supertile BEL is characterised by the timing model of the supertile's
    master tile, which synthesises the whole supertile. A BEL is found by the
    instance name the tile or supertile generator gives it.

    Parameters
    ----------
    fabric : Fabric
        The fabric.
    models : dict[str, FABulousTileTimingModel]
        Timing model of each tile type.

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
                model = models[tile.name]
                arcs[bel.instance_name] = model.bel_timing(
                    bel, instance=(*model.tile_scope, bel.instance_name)
                )
    super_tiles: dict[str, dict[str, BelArcs]] = {}
    for base_fx, base_fy, super_tile in fabric.iter_super_tile_placements():
        tx_local, ty_local = super_tile.get_master_tile_coords()
        master = fabric.tile[base_fy + ty_local][base_fx + tx_local]
        arcs = super_tiles.setdefault(super_tile.name, {})
        for bel in super_tile.bels:
            if bel.instance_name not in arcs:
                arcs[bel.instance_name] = models[master.name].bel_timing(
                    bel, instance=(super_tile.bel_instance_name(bel),)
                )
    return BelTiming(tiles=tiles, super_tiles=super_tiles)


def characterize(fabric: Fabric, config: TimingModelConfig) -> TimingDb:
    """Characterise the pip delays and BEL arcs of `fabric` with Yosys and OpenSTA.

    Clock arrival is not characterised; it stays `CLOCK_DELAY`.

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
    logger.info(f"Initializing timing models for tiles, with mode: {config.mode}")
    models = {
        tile_name: FABulousTileTimingModel(
            config=config.model_copy(deep=True), fabric=fabric, tile_name=tile_name
        )
        for tile_name in fabric.tileDic
    }
    return TimingDb(
        pips=_characterize_pips(fabric, models),
        bels=_characterize_bels(fabric, models),
        clock_arrival=CLOCK_DELAY,
    )

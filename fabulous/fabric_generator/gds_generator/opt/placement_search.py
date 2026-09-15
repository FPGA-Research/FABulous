"""Run a tile's placement-driven search and read its winner back.

The search is a LibreLane flow, so launching it means resolving the PDK, the
HDL and the tile's configs, which is more than a REPL command should carry and
more than one command needs. `search_tile_from_placement` builds and starts the
flow; `won_config_mapping` and `won_interface_order` read the two inputs the
winning iteration exported out of its final state, each returning None when the
optimisation that produces it was off or never reached a proposal.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, cast

import yaml

from fabulous.custom_exception import GDSFlowError
from fabulous.fabric_definition.define import HDLType
from fabulous.fabric_generator.gds_generator.flows.placement_opt_flow import (
    FABulousTileVerilogPlacementOptFlow,
    FABulousTileVHDLPlacementOptFlow,
)
from fabulous.fabric_generator.gds_generator.formats import (
    CONFIG_MEM_FORMAT,
    TILE_INTERFACE_ORDER_FORMAT,
)
from fabulous.fabric_generator.gds_generator.opt.tile_interface import (
    InterfaceOrder,
    apply_interface_order,
    tile_pin_yaml,
    write_interface_order,
    write_ordered_pin_yaml,
)
from fabulous.fabric_generator.gds_generator.opt.variables import (
    CONFIG_BIT_MODE_VARIABLE,
    CONFIG_MAPPING_VARIABLE,
    PLACEMENT_ITERATIONS_VARIABLE,
    TILE_INTERFACE_ORDER_VARIABLE,
    TILE_INTERFACE_VARIABLE,
)
from fabulous.fabulous_settings import get_context, is_pdk_config_set

if TYPE_CHECKING:
    from librelane.state.state import State

    from fabulous.fabric_definition.fabric import Fabric
    from fabulous.fabric_definition.tile import Tile


def search_tile_from_placement(
    tile: Tile,
    *,
    project_dir: Path,
    fabric: Fabric,
    config_mapping: bool,
    tile_interface: bool,
    fixed_order: InterfaceOrder | None = None,
    iterations: int | None = None,
    override: Path | None = None,
) -> State:
    """Search a tile for the inputs it prefers and return the flow's final state.

    The run implements a proposal, reads the placement back and proposes again,
    keeping the iteration whose inputs cost the least. It places but does not
    route, and holds the die the tile's config gives, so its macro is a
    by-product: what it produces are inputs for a later hardening run.

    Parameters
    ----------
    tile : Tile
        The leaf tile to search.
    project_dir : Path
        The FABulous project the tile belongs to.
    fabric : Fabric
        The fabric the tile belongs to, which gives the configuration bit mode.
    config_mapping : bool
        Search the configuration mapping.
    tile_interface : bool
        Search the tile interface order.
    fixed_order : InterfaceOrder | None
        Ranks the search has to keep, normally what the tiles this one abuts
        already fix. Defaults to None, every border free.
    iterations : int | None
        Placements to spend on the search. Defaults to the flow's own budget.
    override : Path | None
        A YAML of further config for the flow.

    Returns
    -------
    State
        The final state of the optimisation flow.

    Raises
    ------
    GDSFlowError
        If neither optimisation was asked for, the PDK is unset, or the tile is
        composite, since a composite's configuration memory borrows the master
        cell's crosspoints and its borders are not reordered.
    """
    if not (config_mapping or tile_interface):
        raise GDSFlowError(
            "Pass config_mapping, tile_interface or both; there is nothing to "
            "search for otherwise."
        )
    if not is_pdk_config_set():
        raise GDSFlowError(
            "PDK configuration is not set. Set the PDK configuration to "
            "optimise a tile."
        )
    if tile.is_composite:
        raise GDSFlowError(
            f"{tile.name} is not a leaf tile of the fabric definition; a "
            "composite tile's configuration memory borrows the master cell's "
            "crosspoints and its borders are not reordered."
        )

    tile_dir = project_dir / "Tile" / tile.name
    design_dir = tile_dir / "macro" / "placement_opt"
    design_dir.mkdir(parents=True, exist_ok=True)

    # The search hardens from a copy, since the tile's own pin YAML is where an
    # order already searched for it lives and regenerating it would lose that.
    source = tile_pin_yaml(project_dir / "Tile", tile.name)
    if not source.is_file():
        write_ordered_pin_yaml(tile, source, None, fabric=fabric)
    payload = yaml.safe_load(source.read_text())
    pin_order_file = design_dir / source.name

    custom_overrides: dict = {}
    if fixed_order is not None:
        payload = apply_interface_order(payload, fixed_order)
        fixed_path = design_dir / "fixed_interface_order.yaml"
        write_interface_order(fixed_order, fixed_path)
        custom_overrides[TILE_INTERFACE_ORDER_VARIABLE.name] = str(fixed_path)
    pin_order_file.write_text(yaml.safe_dump(payload))

    if override:
        custom_overrides.update(yaml.safe_load(override.read_text()) or {})
    if iterations is not None:
        custom_overrides[PLACEMENT_ITERATIONS_VARIABLE.name] = iterations

    flow_cls = (
        FABulousTileVHDLPlacementOptFlow
        if get_context().proj_lang == HDLType.VHDL
        else FABulousTileVerilogPlacementOptFlow
    )
    flow = flow_cls(
        tile,
        pin_order_file,
        pdk=cast("str", get_context().pdk),
        pdk_root=cast("Path", get_context().pdk_root),
        base_config_path=project_dir / "Tile" / "include" / "gds_config.yaml",
        override_config_path=tile_dir / "gds_config.yaml",
        design_dir=design_dir,
        **{
            CONFIG_MAPPING_VARIABLE.name: config_mapping,
            TILE_INTERFACE_VARIABLE.name: tile_interface,
            CONFIG_BIT_MODE_VARIABLE.name: fabric.configBitMode,
        },
        **custom_overrides,
    )
    return flow.start()


def won_config_mapping(state: State) -> Path | None:
    """Return the `ConfigMem.csv` the winning iteration implemented.

    Parameters
    ----------
    state : State
        The final state of an optimisation flow.

    Returns
    -------
    Path | None
        The mapping, or None when no iteration exported one.
    """
    view = state.get(CONFIG_MEM_FORMAT)
    return None if view is None else Path(str(view))


def won_interface_order(state: State) -> Path | None:
    """Return the interface order the winning iteration implemented.

    Parameters
    ----------
    state : State
        The final state of an optimisation flow.

    Returns
    -------
    Path | None
        The order, or None when no iteration exported one.
    """
    view = state.get(TILE_INTERFACE_ORDER_FORMAT)
    return None if view is None else Path(str(view))

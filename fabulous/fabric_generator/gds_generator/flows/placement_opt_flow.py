"""The tile flow that searches a tile's mapping rather than hardening it.

The flow synthesises the tile, iterates the placement-driven optimisation over
it and exports what the winning iteration implemented. Everything else it writes
is a by-product: each iteration stops before routing and the die is whatever the
tile's own config gives, so a tile is hardened by running the macro flow again
on the exported mapping.
"""

from pathlib import Path
from typing import cast

import yaml
from librelane.flows.flow import Flow, FlowException
from librelane.state.state import State

from fabulous.custom_exception import GDSFlowError
from fabulous.fabric_definition.define import HDLType
from fabulous.fabric_definition.fabric import Fabric
from fabulous.fabric_definition.tile import Tile
from fabulous.fabric_generator.gds_generator.flows.flow_define import (
    prep_steps,
    vhdl_prep_steps,
)
from fabulous.fabric_generator.gds_generator.flows.tile_macro_flow import (
    FABulousTileVerilogMacroFlow,
    FABulousTileVHDLMacroFlow,
)
from fabulous.fabric_generator.gds_generator.formats import CONFIG_MEM_FORMAT
from fabulous.fabric_generator.gds_generator.gen_io_pin_config_yaml import (
    generate_IO_pin_order_config,
)
from fabulous.fabric_generator.gds_generator.opt.placement_opt import (
    PlacementDrivenTileOptimisation,
)
from fabulous.fabric_generator.gds_generator.steps.tile_area_opt import OptMode
from fabulous.fabric_generator.gds_generator.variables import (
    CONFIG_BIT_MODE_VARIABLE,
    CONFIG_MAPPING_VARIABLE,
    CONFIG_MEM_CSV_VARIABLE,
    PLACEMENT_ITERATIONS_VARIABLE,
)
from fabulous.fabulous_settings import get_context, is_pdk_config_set


class PlacementOptInputs:
    """Gives a tile macro flow the input the proposal step reads.

    The proposal step runs without the tile model, so the mapping it starts
    from is passed as config. A tile with no configuration bits, such as a
    termination tile, has no latches to place and so no mapping to read.

    Parameters
    ----------
    tile_type : Tile
        The tile to optimise.
    io_pin_config : Path
        The pin YAML the tile is placed from.
    pdk : str
        The PDK name.
    pdk_root : Path
        Where the PDK lives.
    design_dir : Path | None
        The run directory, which the search always gets given so its
        by-products land away from the tile's macro.
    **custom_config_overrides : dict
        Further config for the flow.

    Raises
    ------
    FlowException
        If asked for a super tile, whose configuration memory borrows the
        master tile's crosspoints and whose borders are not reordered, or if no
        run directory was given.
    """

    def __init__(
        self,
        tile_type: Tile,
        io_pin_config: Path,
        pdk: str,
        pdk_root: Path,
        design_dir: Path | None = None,
        **custom_config_overrides: dict,
    ) -> None:
        if not isinstance(tile_type, Tile):
            raise FlowException(
                f"{tile_type.name} is a supertile; its configuration memory "
                "borrows the master tile's crosspoints, so only a leaf tile "
                "takes this optimisation."
            )
        if design_dir is None:
            raise FlowException(
                f"{type(self).__name__} needs a design directory of its own; its "
                "run is a search whose output is thrown away."
            )
        super().__init__(
            tile_type,
            io_pin_config,
            OptMode.NO_OPT,
            pdk=pdk,
            pdk_root=pdk_root,
            design_dir=design_dir,
            **{
                CONFIG_MEM_CSV_VARIABLE.name: (
                    None
                    if tile_type.globalConfigBits == 0
                    else str(tile_type.config_mem.source)
                ),
            },
            **custom_config_overrides,
        )


@Flow.factory.register()
class FABulousTileVerilogPlacementOptFlow(
    PlacementOptInputs, FABulousTileVerilogMacroFlow
):
    """Placement-driven tile optimisation from Verilog."""

    Steps = prep_steps + [PlacementDrivenTileOptimisation]


@Flow.factory.register()
class FABulousTileVHDLPlacementOptFlow(PlacementOptInputs, FABulousTileVHDLMacroFlow):
    """Placement-driven tile optimisation from VHDL."""

    Steps = vhdl_prep_steps + [PlacementDrivenTileOptimisation]


def search_tile_from_placement(
    tile: Tile,
    *,
    project_dir: Path,
    fabric: Fabric,
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
        If the PDK is unset.
    """
    if not is_pdk_config_set():
        raise GDSFlowError(
            "PDK configuration is not set. Set the PDK configuration to "
            "optimise a tile."
        )
    tile_dir = project_dir / "Tile" / tile.name
    design_dir = tile_dir / "macro" / "placement_opt"
    design_dir.mkdir(parents=True, exist_ok=True)

    # The search hardens from a copy, so it never writes over the pin YAML the
    # tile is hardened from.
    source = tile_dir / f"{tile.name}_io_pin_order.yaml"
    if not source.is_file():
        generate_IO_pin_order_config(tile, source, fabric=fabric)
    pin_order_file = design_dir / source.name
    pin_order_file.write_text(yaml.safe_dump(yaml.safe_load(source.read_text())))

    custom_overrides: dict = {}
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
            CONFIG_MAPPING_VARIABLE.name: True,
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

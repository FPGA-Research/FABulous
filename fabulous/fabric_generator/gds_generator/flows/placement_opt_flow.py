"""Tile flows that produce a tile's inputs rather than its macro.

The flow synthesises the tile, then iterates the placement-driven
optimisations over it and exports what the winning iteration implemented: a
`ConfigMem.csv` and a tile interface order. Everything else it writes is a
by-product of the search and is thrown away, so a tile is hardened by running
the macro flow again on the exported inputs. The die is whatever the tile's own
config gives, since the search stops each iteration before it routes and the
macro flow is what sizes a tile.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from librelane.flows.flow import Flow, FlowException

from fabulous.fabric_generator.gds_generator.flows.flow_define import (
    prep_steps,
    vhdl_prep_steps,
)
from fabulous.fabric_generator.gds_generator.flows.tile_macro_flow import (
    FABulousTileVerilogMacroFlow,
    FABulousTileVHDLMacroFlow,
)
from fabulous.fabric_generator.gds_generator.opt.placement_opt import (
    PlacementDrivenTileOptimisation,
)
from fabulous.fabric_generator.gds_generator.opt.tile_area_opt import OptMode
from fabulous.fabric_generator.gds_generator.opt.tile_interface import write_bus_pairs
from fabulous.fabric_generator.gds_generator.opt.variables import (
    CONFIG_MEM_CSV_VARIABLE,
    TILE_INTERFACE_PAIRS_VARIABLE,
)
from fabulous.fabric_generator.parser.parse_csv import config_mem_csv_of

if TYPE_CHECKING:
    from fabulous.fabric_definition.tile import Tile


class PlacementOptInputs:
    """Gives a tile macro flow the two inputs the proposal steps read.

    The proposal steps run without the tile model, so the pairs they need are
    written next to the run as `<tile>_pin_pairs.yaml`. A tile with no
    configuration bits, such as a termination tile, has no latches to place and
    no mapping to read.

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
        if tile_type.is_composite:
            raise FlowException(
                f"{tile_type.name} is a composite tile; its configuration memory "
                "borrows the master cell's crosspoints and its borders are not "
                "reordered, so only leaf tiles take these optimisations."
            )
        if design_dir is None:
            raise FlowException(
                f"{type(self).__name__} needs a design directory of its own; its "
                "run is a search whose output is thrown away."
            )
        pairs = Path(design_dir) / f"{tile_type.name}_pin_pairs.yaml"
        pairs.parent.mkdir(parents=True, exist_ok=True)
        write_bus_pairs(pairs, tile_type.pairs)
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
                    if tile_type.total_config_bits == 0
                    else str(config_mem_csv_of(tile_type))
                ),
                TILE_INTERFACE_PAIRS_VARIABLE.name: str(pairs),
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

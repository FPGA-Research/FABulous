"""Tile flows that produce a tile's inputs rather than its macro.

The flow synthesises the tile, then iterates the placement-driven
optimisations over it and exports what the winning iteration implemented: a
`ConfigMem.csv` and a tile interface order. Everything else it writes is a
by-product of the search and is thrown away, so a tile is hardened by running
the macro flow again on the exported inputs.
"""

from pathlib import Path

from librelane.flows.flow import Flow, FlowException

from fabulous.fabric_definition.supertile import SuperTile
from fabulous.fabric_definition.tile import Tile
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
from fabulous.fabric_generator.gds_generator.opt.tile_interface import write_bus_pairs
from fabulous.fabric_generator.gds_generator.opt.variables import (
    CONFIG_MEM_CSV_VARIABLE,
    TILE_INTERFACE_PAIRS_VARIABLE,
)


def config_mem_csv_for(tile_type: Tile) -> str | None:
    """Return the `ConfigMem.csv` the configuration mapping reads, or None.

    A tile without configuration bits, such as a termination tile, has no
    latches to place.

    Parameters
    ----------
    tile_type : Tile
        The tile being optimised.

    Returns
    -------
    str | None
        The path of its configuration memory, or None when it has no
        configuration bits.
    """
    if tile_type.globalConfigBits == 0:
        return None
    return str(tile_type.config_mem_path)


def write_pin_pairs_for(tile_type: Tile, directory: Path) -> str:
    """Write the tile's bus pairs where the interface ordering step reads them.

    The step runs without the tile model, so the pairs it needs are written
    next to the run as `<tile>_pin_pairs.yaml`.

    Parameters
    ----------
    tile_type : Tile
        The tile being optimised.
    directory : Path
        The run directory the file goes in.

    Returns
    -------
    str
        The path of the file written.
    """
    path = directory / f"{tile_type.name}_pin_pairs.yaml"
    write_bus_pairs(path, tile_type.interface.pairs)
    return str(path)


class PlacementOptInputs:
    """The tile inputs the proposal steps read, mixed into a tile macro flow."""

    def extra_tile_config(
        self, tile_type: Tile | SuperTile, design_dir: Path
    ) -> dict[str, object]:
        """Point the optimisations at the tile's current mapping and its bus pairs.

        Parameters
        ----------
        tile_type : Tile | SuperTile
            The tile being optimised.
        design_dir : Path
            The run directory.

        Returns
        -------
        dict[str, object]
            The two inputs the proposal steps read.

        Raises
        ------
        FlowException
            If asked for a super tile, whose configuration memory borrows the
            master tile's crosspoints and whose borders are not reordered.
        """
        if isinstance(tile_type, SuperTile):
            raise FlowException(
                f"{tile_type.name} is a super tile; its configuration memory "
                "borrows the master tile's crosspoints and its borders are not "
                "reordered, so only regular tiles take these optimisations."
            )
        return {
            CONFIG_MEM_CSV_VARIABLE.name: config_mem_csv_for(tile_type),
            TILE_INTERFACE_PAIRS_VARIABLE.name: write_pin_pairs_for(
                tile_type, design_dir
            ),
        }


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

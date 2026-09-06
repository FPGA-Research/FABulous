"""Propose a tile interface order from the placed logic."""

from pathlib import Path

from librelane.common.types import Path as LibrelanePath
from librelane.logging.logger import info
from librelane.state.state import State
from librelane.steps.step import MetricsUpdate, Step, ViewsUpdate

from fabulous.custom_exception import GDSFlowError
from fabulous.fabric_generator.gds_generator.formats import (
    PLACEMENT_FORMAT,
    TILE_INTERFACE_ORDER_FORMAT,
)
from fabulous.fabric_generator.gds_generator.opt.placement import Placement
from fabulous.fabric_generator.gds_generator.opt.tile_interface import (
    current_offset,
    expand_bus_pairs,
    order_pairs,
    pins_by_side,
    rank_offset,
    read_bus_pairs,
    read_interface_order,
    write_interface_order,
)
from fabulous.fabric_generator.gds_generator.opt.variables import (
    TILE_INTERFACE_FIXED_ORDER_VARIABLE,
    TILE_INTERFACE_PAIRS_VARIABLE,
    TILE_INTERFACE_VARIABLE,
)


@Step.factory.register()
class ProposeTileInterfaceOrder(Step):
    """Write an interface order that puts every border pair next to the logic it feeds.

    The proposal is a pin YAML view in the step directory, the form
    `FABulousTileIOPlacement` applies through `FABULOUS_TILE_INTERFACE_ORDER`
    on the next iteration. Pairs of `FABULOUS_TILE_INTERFACE_FIXED_ORDER` keep
    their rank, so a border shared with an already hardened tile stays as it
    was.
    """

    id = "FABulous.ProposeTileInterfaceOrder"
    name = "Propose Tile Interface Order"

    inputs = [PLACEMENT_FORMAT]
    outputs = [TILE_INTERFACE_ORDER_FORMAT]

    config_vars = [
        TILE_INTERFACE_VARIABLE,
        TILE_INTERFACE_PAIRS_VARIABLE,
        TILE_INTERFACE_FIXED_ORDER_VARIABLE,
    ]

    def run(self, state_in: State, **_kwargs: str) -> tuple[ViewsUpdate, MetricsUpdate]:
        """Order the pairs and publish the proposal with its offset metrics.

        Parameters
        ----------
        state_in : State
            The state carrying the placement view.
        **_kwargs : str
            Unused.

        Returns
        -------
        tuple[ViewsUpdate, MetricsUpdate]
            The interface order view and the offsets before and after.

        Raises
        ------
        GDSFlowError
            If the ordering is on for a tile without bus pairs, which means a
            super tile, whose borders are not reordered.
        """
        if not self.config[TILE_INTERFACE_VARIABLE.name]:
            info(f"'{TILE_INTERFACE_VARIABLE.name}' is off: skipping '{self.id}'...")
            return {}, {}
        if (pairs_path := self.config[TILE_INTERFACE_PAIRS_VARIABLE.name]) is None:
            raise GDSFlowError(
                f"{TILE_INTERFACE_VARIABLE.name} needs "
                f"{TILE_INTERFACE_PAIRS_VARIABLE.name}; a super tile's borders are "
                "not reordered."
            )

        placement = Placement.from_json(Path(state_in[PLACEMENT_FORMAT]))
        pairs = expand_bus_pairs(read_bus_pairs(Path(pairs_path)), placement.pins)
        paired = {pair.first for pair in pairs} | {pair.second for pair in pairs}
        if unpaired := sorted(set(placement.pins) - paired):
            info(f"Pins left in their default segments: {unpaired}")

        fixed_path = self.config[TILE_INTERFACE_FIXED_ORDER_VARIABLE.name]
        fixed = None if fixed_path is None else read_interface_order(Path(fixed_path))
        ordered = order_pairs(placement, pairs, fixed)
        design = self.config["DESIGN_NAME"]
        out = Path(self.step_dir) / f"{design}.{TILE_INTERFACE_ORDER_FORMAT.extension}"
        write_interface_order(pins_by_side(ordered), out)

        before = current_offset(placement, pairs)
        after = rank_offset(placement, ordered)
        info(
            f"Border pair offset {before:.1f} um -> {after:.1f} um over "
            f"{len(pairs)} pairs; proposal written to {out}"
        )
        metrics: MetricsUpdate = {
            "fabulous__tile_interface__offset_before": before,
            "fabulous__tile_interface__offset_after": after,
            "fabulous__tile_interface__pairs": len(pairs),
        }
        return {TILE_INTERFACE_ORDER_FORMAT: LibrelanePath(str(out))}, metrics

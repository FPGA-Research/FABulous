"""Tile area optimisation that also rewrites the tile from its own placement.

The body of `TileAreaOptimisation` gains the four steps of "How to shrink my
FPGAs": the placement is read back out of OpenDB after clock tree synthesis,
each optimisation proposes new inputs from it, and the next iteration
implements them by rewiring the floorplanned netlist. `PlacementOptLoop` is
what remembers the proposals across iterations, since `WhileStep` rebuilds the
state every time.

The step is not part of the tile macro flow. It produces a configuration
memory mapping and an interface order, which are inputs a later hardening run
implements as written.
"""

from decimal import Decimal
from pathlib import Path

from librelane.logging.logger import info
from librelane.state.state import State
from librelane.steps import openroad as OpenROAD
from librelane.steps.step import MetricsUpdate, Step, ViewsUpdate

from fabulous.custom_exception import GDSFlowError
from fabulous.fabric_generator.gds_generator.formats import (
    CONFIG_MEM_FORMAT,
    TILE_INTERFACE_ORDER_FORMAT,
)
from fabulous.fabric_generator.gds_generator.opt.loop import PlacementOptLoop
from fabulous.fabric_generator.gds_generator.opt.tile_area_opt import (
    OptMode,
    TileAreaOptimisation,
)
from fabulous.fabric_generator.gds_generator.opt.variables import (
    CONFIG_BIT_MODE_VARIABLE,
    PLACEMENT_ITERATIONS_VARIABLE,
    ROUTE_EVERY_ITERATION_VARIABLE,
)
from fabulous.fabric_generator.gds_generator.steps.apply_config_mapping import (
    ApplyConfigMapping,
)
from fabulous.fabric_generator.gds_generator.steps.dump_placement import DumpPlacement
from fabulous.fabric_generator.gds_generator.steps.propose_config_mapping import (
    ProposeConfigMapping,
)
from fabulous.fabric_generator.gds_generator.steps.propose_tile_interface_order import (
    ProposeTileInterfaceOrder,
)


def _body_with_proposals() -> list[type[Step]]:
    """Return the area optimisation body with the placement-driven steps in it.

    The rewire follows the floorplan, since editing the ODB there is what lets
    an iteration implement a proposal without a second synthesis run. The
    proposals are read after clock tree synthesis and before routing, so a
    routing failure still yields the next iteration's inputs.

    Returns
    -------
    list[type[Step]]
        The body of the loop.
    """
    steps = list(TileAreaOptimisation.Steps)
    steps.insert(steps.index(OpenROAD.Floorplan) + 1, ApplyConfigMapping)
    after_cts = steps.index(OpenROAD.CTS) + 1
    steps[after_cts:after_cts] = [
        DumpPlacement,
        ProposeConfigMapping,
        ProposeTileInterfaceOrder,
    ]
    return steps


@Step.factory.register()
class PlacementDrivenTileOptimisation(TileAreaOptimisation):
    """Area optimisation whose iterations implement each other's proposals.

    Under a fixed die the budget is the iteration count. Otherwise the die
    grows to its first clean iteration under the usual cap and then shrinks
    after each clean iteration and holds after a failed one, so fresh proposals
    get another attempt at the same size.
    """

    id = "FABulous.PlacementDrivenTileOptimisation"
    name = "Placement Driven Tile Optimisation"

    Steps = _body_with_proposals()

    # The proposals of an iteration are inputs of the next one; only what the
    # winning iteration implemented leaves the step.
    outputs = [
        *TileAreaOptimisation.outputs,
        CONFIG_MEM_FORMAT,
        TILE_INTERFACE_ORDER_FORMAT,
    ]

    config_vars = TileAreaOptimisation.config_vars + [
        CONFIG_BIT_MODE_VARIABLE,
        PLACEMENT_ITERATIONS_VARIABLE,
        ROUTE_EVERY_ITERATION_VARIABLE,
    ]

    # A placement optimisation fault must stop the flow, not read as a die
    # that is too small.
    propagate_exceptions = (GDSFlowError,)

    # Built from the config on first use, so hooks work before `run` as well.
    loop: PlacementOptLoop | None = None

    def _loop(self) -> PlacementOptLoop:
        """Return the proposal bookkeeping of this run, built on first use."""
        if self.loop is None:
            self.loop = PlacementOptLoop(
                self.config,
                growth_cap=TileAreaOptimisation.max_iterations,
                no_opt=self.config["FABULOUS_OPT_MODE"] == OptMode.NO_OPT,
            )
        return self.loop

    def _no_opt_iterations(self) -> int:
        """Return the whole budget, since a fixed die still iterates on proposals."""
        return self._loop().max_iterations

    def _keep_working_state(self, state: State) -> None:
        """Keep the best clean iteration, since the latest proposal is not the best."""
        if self._loop().consider(state):
            super()._keep_working_state(state)

    def _compute_new_dimensions(
        self,
        width: Decimal,
        height: Decimal,
        width_step: Decimal,
        height_step: Decimal,
        instance_area: Decimal,
        core_area: Decimal,
    ) -> tuple[Decimal, Decimal]:
        """Grow to the first clean iteration, then shrink after each clean one.

        Parameters
        ----------
        width : Decimal
            The current die width.
        height : Decimal
            The current die height.
        width_step : Decimal
            One iteration's width step.
        height_step : Decimal
            One iteration's height step.
        instance_area : Decimal
            The area the cells need.
        core_area : Decimal
            The area the core offers.

        Returns
        -------
        tuple[Decimal, Decimal]
            The next iteration's die dimensions.
        """
        if not self._loop().clean_seen:
            return super()._compute_new_dimensions(
                width, height, width_step, height_step, instance_area, core_area
            )
        return self._compute_shrunk_dimensions(width, height, width_step, height_step)

    def _compute_shrunk_dimensions(
        self,
        width: Decimal,
        height: Decimal,
        width_step: Decimal,
        height_step: Decimal,
    ) -> tuple[Decimal, Decimal]:
        """Mirror the BALANCE / LARGE growth rule after a clean iteration.

        After a failed iteration that follows a clean one the die holds, so the
        fresh proposals get another attempt at the same size. A shrink that
        would go below the pin-minimum die ends the loop instead.

        Parameters
        ----------
        width : Decimal
            The current die width.
        height : Decimal
            The current die height.
        width_step : Decimal
            One iteration's width step.
        height_step : Decimal
            One iteration's height step.

        Returns
        -------
        tuple[Decimal, Decimal]
            The next iteration's die dimensions.

        Raises
        ------
        ValueError
            If the mode is neither BALANCE nor LARGE, which the directional
            modes never reach because they binary search instead.
        """
        loop = self._loop()
        if not loop.last_clean:
            return width, height
        logical_w = Decimal(self.config.get("FABULOUS_TILE_LOGICAL_WIDTH", 1))
        logical_h = Decimal(self.config.get("FABULOUS_TILE_LOGICAL_HEIGHT", 1))
        new_width, new_height = width, height
        match self.config["FABULOUS_OPT_MODE"]:
            case OptMode.BALANCE:
                if logical_w * logical_h > Decimal(1):
                    cell_step = max(width_step / logical_w, height_step / logical_h)
                    new_width -= cell_step * logical_w
                    new_height -= cell_step * logical_h
                elif width >= height:
                    new_width -= width_step
                else:
                    new_height -= height_step
            case OptMode.LARGE:
                new_width -= width_step
                new_height -= height_step
            case mode:
                raise ValueError(f"Unknown FABULOUS_OPT_MODE: {mode}")
        pin_w = Decimal(self.config.get("FABULOUS_PIN_MIN_WIDTH", 0))
        pin_h = Decimal(self.config.get("FABULOUS_PIN_MIN_HEIGHT", 0))
        if new_width < pin_w or new_height < pin_h or new_width <= 0 or new_height <= 0:
            info("The next shrink would fall below the pin-minimum die; stopping")
            loop.shrink_exhausted = True
            return width, height
        return new_width, new_height

    def condition(self, state: State) -> bool:
        """Keep iterating while the budget and the proposals both allow it."""
        if self._is_directional():
            return super().condition(state)
        return self._loop().should_continue()

    def pre_iteration_callback(self, pre_iteration: State) -> State:
        """Point the iteration at the proposals of the previous one."""
        self.config = self._loop().begin_iteration(self.config)
        return super().pre_iteration_callback(pre_iteration)

    def post_iteration_callback(
        self, post_iteration: State, full_iter_completed: bool
    ) -> State:
        """Keep the proposals the finished iteration produced."""
        self._loop().end_iteration(post_iteration, full_iter_completed)
        return super().post_iteration_callback(post_iteration, full_iter_completed)

    def post_loop_callback(self, state: State) -> State:
        """Export the winning iteration's inputs as views of the step."""
        result = super().post_loop_callback(state)
        loop = self._loop()
        if loop.winner is None:
            return result
        views = loop.export_winner(Path(self.step_dir), self.config["DESIGN_NAME"])
        return State(result, overrides=views, metrics=result.metrics)

    def mid_iteration_break(self, state: State, step: Step) -> bool:
        """Stop the body after the proposals on an iteration that does not route."""
        if isinstance(step, ProposeTileInterfaceOrder) and not self._loop().last_routed:
            info("Proposals read, skipping routing on this iteration")
            return True
        return super().mid_iteration_break(state, step)

    def run(
        self,
        state_in: State,
        **_kwargs: dict,
    ) -> tuple[ViewsUpdate, MetricsUpdate]:
        """Run the tile optimisation step with the loop bounding the body."""
        self.loop = None
        # The loop bounds the body itself; the sum keeps `WhileStep`'s own cap
        # from cutting in before the growth cap plus the budget.
        self.max_iterations = self._loop().max_iterations
        return super().run(state_in, **_kwargs)

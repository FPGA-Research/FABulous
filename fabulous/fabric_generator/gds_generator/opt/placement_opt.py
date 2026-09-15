"""Tile optimisation that rewrites a tile from its own placement.

The body of `TileAreaOptimisation` gains the four steps of "How to shrink my
FPGAs": the placement is read back out of OpenDB after clock tree synthesis,
each optimisation proposes new inputs from it, and the next iteration
implements them by rewiring the floorplanned netlist. `WhileStep` rebuilds the
state every iteration, so what carries across them lives on the step: which
inputs the running iteration implements, which proposals it produced, and which
iteration has scored best so far.

`DumpPlacement` sits after clock tree synthesis and before global routing, so
no proposal has ever read a routed design and routing an iteration cannot
change one. Each iteration therefore stops at its proposals, and routes only
when `FABULOUS_OPT_ROUTE_EVERY_ITERATION` asks for routed numbers to look at.
The die is fixed for the same reason: the step searches the mapping at the size
it is given, and the hardening run that implements the mapping searches the die.

An iteration is scored by what it implemented rather than by what it proposed,
because the cost of a proposal is only known once a placement has been made
from it. The loop ends when a proposal repeats its own input or the budget runs
out, and exports the inputs of the best-scoring iteration, because proposals
keep changing and the latest is not the best.

The step is not part of the tile macro flow. It produces a configuration memory
mapping and an interface order, which are inputs a later hardening run
implements as written.
"""

from __future__ import annotations

import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

from librelane.common.types import Path as LibrelanePath
from librelane.logging.logger import info
from librelane.state.state import State
from librelane.steps import openroad as OpenROAD
from librelane.steps.step import MetricsUpdate, Step, ViewsUpdate

from fabulous.custom_exception import GDSFlowError
from fabulous.fabric_definition.define import ConfigBitMode
from fabulous.fabric_generator.gds_generator.formats import (
    CONFIG_MEM_FORMAT,
    RECONNECT_FORMAT,
    TILE_INTERFACE_ORDER_FORMAT,
)
from fabulous.fabric_generator.gds_generator.opt.tile_area_opt import (
    OptMode,
    TileAreaOptimisation,
)
from fabulous.fabric_generator.gds_generator.opt.variables import (
    CONFIG_BIT_MODE_VARIABLE,
    CONFIG_MAPPING_RECONNECT_VARIABLE,
    CONFIG_MAPPING_TARGET_VARIABLE,
    CONFIG_MAPPING_VARIABLE,
    CONFIG_MEM_CSV_VARIABLE,
    PLACEMENT_ITERATIONS_VARIABLE,
    ROUTE_EVERY_ITERATION_VARIABLE,
    TILE_INTERFACE_FIXED_ORDER_VARIABLE,
    TILE_INTERFACE_ORDER_VARIABLE,
    TILE_INTERFACE_PAIRS_VARIABLE,
    TILE_INTERFACE_VARIABLE,
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

if TYPE_CHECKING:
    from librelane.state.design_format import DesignFormat

UNCHANGED_METRICS = {
    CONFIG_MAPPING_VARIABLE.name: "fabulous__config_mapping__unchanged",
    TILE_INTERFACE_VARIABLE.name: "fabulous__tile_interface__unchanged",
}
"""The metric each optimisation reports when its proposal repeats its input."""

REALISED_METRICS = {
    CONFIG_MAPPING_VARIABLE.name: "fabulous__config_mapping__stub_before",
    TILE_INTERFACE_VARIABLE.name: "fabulous__tile_interface__offset_before",
}
"""The micrometres each optimisation still costs on the placement it produced."""


@dataclass(frozen=True)
class IterationInputs:
    """What one iteration implements: its mapping, how to rewire to it, its order."""

    config_mem_csv: Path | None
    reconnect: Path | None
    interface_order: Path | None


def _body_with_proposals() -> list[type[Step]]:
    """Return the area optimisation body with the placement-driven steps in it.

    The rewire follows the floorplan, since editing the ODB there is what lets
    an iteration implement a proposal without a second synthesis run. The
    proposals are read after clock tree synthesis and before routing, which is
    what lets an iteration stop before it routes.

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


def _text(path: Path | None) -> str | None:
    """Return a path as the string a LibreLane path variable takes."""
    return None if path is None else str(path)


def _view(state: State, fmt: DesignFormat) -> Path | None:
    """Return a view of `state` as a path, or None when absent."""
    value = state.get(fmt.id)
    return None if value is None else Path(str(value))


@Step.factory.register()
class PlacementDrivenTileOptimisation(TileAreaOptimisation):
    """Tile optimisation whose iterations implement each other's proposals."""

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

    # Carried across iterations, which rebuild the state.
    budget: int = 0

    fixed_order: Path | None = None

    next_inputs: IterationInputs = IterationInputs(None, None, None)

    applied: IterationInputs | None = None

    winner: IterationInputs | None = None

    best_score: float | None = None

    iteration: int = 0

    converged: bool = False

    @property
    def config_mapping(self) -> bool:
        """Whether the configuration mapping is on."""
        return bool(self.config[CONFIG_MAPPING_VARIABLE.name])

    @property
    def tile_interface(self) -> bool:
        """Whether the tile interface ordering is on."""
        return bool(self.config[TILE_INTERFACE_VARIABLE.name])

    @property
    def routes(self) -> bool:
        """Whether the iterations route, which only produces numbers to read."""
        return bool(self.config[ROUTE_EVERY_ITERATION_VARIABLE.name])

    def _start_run(self) -> None:
        """Check the inputs of the optimisations and take their budget.

        Raises
        ------
        GDSFlowError
            If neither optimisation is on, since the loop then has nothing to
            propose; if the die is searched, since an iteration that stops at
            its proposals gives the die rule no verdict to grow or shrink on;
            if configuration mapping is on under a config-bit mode other than
            FRAME_BASED, since only frames form the crosspoint grid; if it is
            on without a `ConfigMem.csv`; or if the tile interface ordering is
            on without the tile's bus pairs, since either of the last two means
            a super tile or a tile without configuration bits was asked for an
            optimisation it has no inputs for.
        """
        if not (self.config_mapping or self.tile_interface):
            raise GDSFlowError(
                f"Neither {CONFIG_MAPPING_VARIABLE.name} nor "
                f"{TILE_INTERFACE_VARIABLE.name} is on, so there is nothing to "
                "propose; harden the tile with the macro flow instead."
            )
        if OptMode(self.config["FABULOUS_OPT_MODE"]) is not OptMode.NO_OPT:
            raise GDSFlowError(
                "FABULOUS_OPT_MODE must be no_opt here; the search reads its "
                "proposals before routing, which leaves the die rule no clean "
                "or failed verdict to size on. Harden the tile with the macro "
                "flow to search the die for the mapping this run exports."
            )
        mode = ConfigBitMode(self.config[CONFIG_BIT_MODE_VARIABLE.name])
        if self.config_mapping and mode is not ConfigBitMode.FRAME_BASED:
            raise GDSFlowError(
                f"{CONFIG_MAPPING_VARIABLE.name} needs {CONFIG_BIT_MODE_VARIABLE.name} "
                f"FRAME_BASED, not {mode.name}; only frames form the crosspoint "
                "grid the mapping assigns bits on."
            )
        csv = self.config[CONFIG_MEM_CSV_VARIABLE.name]
        if self.config_mapping and csv is None:
            raise GDSFlowError(
                f"{CONFIG_MAPPING_VARIABLE.name} needs {CONFIG_MEM_CSV_VARIABLE.name}; "
                "a super tile or a tile without configuration bits has no "
                "configuration memory to map."
            )
        if (
            self.tile_interface
            and self.config[TILE_INTERFACE_PAIRS_VARIABLE.name] is None
        ):
            raise GDSFlowError(
                f"{TILE_INTERFACE_VARIABLE.name} needs "
                f"{TILE_INTERFACE_PAIRS_VARIABLE.name}; a super tile's borders are "
                "not reordered."
            )
        order = self.config[TILE_INTERFACE_ORDER_VARIABLE.name]
        self.fixed_order = None if order is None else Path(str(order))
        self.budget = int(self.config[PLACEMENT_ITERATIONS_VARIABLE.name])
        self.next_inputs = IterationInputs(
            None if not self.config_mapping else Path(str(csv)),
            None,
            self.fixed_order,
        )
        self.applied = None
        self.winner = None
        self.best_score = None
        self.iteration = 0
        self.converged = False

    def _no_opt_iterations(self) -> int:
        """Return the budget, since the fixed die still iterates on proposals."""
        return self.budget

    def _score(self, state: State) -> float:
        """Return what the finished iteration still costs, in micrometres.

        Each optimisation reports the cost of the input it implemented, read
        off the placement that input produced, so the sum ranks the iterations
        by what they achieved rather than by what they went on to propose.

        Parameters
        ----------
        state : State
            The state the iteration ended with.

        Returns
        -------
        float
            The cost of every optimisation that is on.

        Raises
        ------
        GDSFlowError
            If the iteration reported no such metric, which means it never
            reached its proposals and the search has nothing to carry forward.
        """
        total = 0.0
        for switch, metric in REALISED_METRICS.items():
            if not self.config[switch]:
                continue
            value = state.metrics.get(metric)
            if value is None:
                raise GDSFlowError(
                    f"The iteration reported no {metric} metric, so it never "
                    "reached its proposals. The die is fixed during the search; "
                    "give the tile a size its cells place at."
                )
            total += float(value)
        return total

    def _keep_working_state(self, state: State) -> None:
        """Keep the best-scoring iteration, since the latest proposal is not the best.

        Parameters
        ----------
        state : State
            The iteration's final state.
        """
        score = self._score(state)
        if self.best_score is not None and score >= self.best_score:
            return
        self.best_score = score
        self.winner = self.applied
        super()._keep_working_state(state)

    def condition(self, state: State) -> bool:  # noqa: ARG002
        """Keep iterating while the budget and the proposals both allow it.

        Parameters
        ----------
        state : State
            The state the previous iteration ended with.

        Returns
        -------
        bool
            Whether another iteration runs.
        """
        return not self.converged and self.iteration < self.budget

    def pre_iteration_callback(self, pre_iteration: State) -> State:
        """Point the iteration at the proposals of the previous one.

        Parameters
        ----------
        pre_iteration : State
            The state the iteration starts from.

        Returns
        -------
        State
            That state; the inputs travel through the config.
        """
        self.applied = self.next_inputs
        self.config = self.config.copy(
            **{
                CONFIG_MAPPING_TARGET_VARIABLE.name: _text(self.applied.config_mem_csv),
                CONFIG_MAPPING_RECONNECT_VARIABLE.name: _text(self.applied.reconnect),
                TILE_INTERFACE_ORDER_VARIABLE.name: _text(self.applied.interface_order),
                TILE_INTERFACE_FIXED_ORDER_VARIABLE.name: _text(self.fixed_order),
            }
        )
        self.iteration += 1
        return super().pre_iteration_callback(pre_iteration)

    def post_iteration_callback(
        self, post_iteration: State, full_iter_completed: bool
    ) -> State:
        """Score the finished iteration and keep the proposals it produced.

        Parameters
        ----------
        post_iteration : State
            The state the iteration ended with, complete or broken off.
        full_iter_completed : bool
            Whether the iteration ran to the end without violations.

        Returns
        -------
        State
            The state the base class returns.
        """
        assert self.applied is not None
        self._keep_working_state(post_iteration)
        proposals = IterationInputs(
            _view(post_iteration, CONFIG_MEM_FORMAT) or self.applied.config_mem_csv,
            _view(post_iteration, RECONNECT_FORMAT) or self.applied.reconnect,
            _view(post_iteration, TILE_INTERFACE_ORDER_FORMAT)
            or self.applied.interface_order,
        )
        if proposals != self.applied:
            self.converged = self._proposals_repeat_inputs(post_iteration)
            if self.converged:
                info("Proposals match the inputs of this iteration: converged")
            self.next_inputs = proposals
        return super().post_iteration_callback(post_iteration, full_iter_completed)

    def _proposals_repeat_inputs(self, state: State) -> bool:
        """Return whether every optimisation that is on proposed its own input.

        Each proposal step compares its output with its input, so the answer
        needs no re-reading of the files.

        Parameters
        ----------
        state : State
            The state the iteration ended with.

        Returns
        -------
        bool
            Whether the iteration proposed what it was given.
        """
        reported = [
            state.metrics.get(metric)
            for switch, metric in UNCHANGED_METRICS.items()
            if self.config[switch]
        ]
        return bool(reported) and all(value == 1 for value in reported)

    def post_loop_callback(self, state: State) -> State:
        """Export the winning iteration's inputs as views of the step.

        Parameters
        ----------
        state : State
            The state the last iteration ended with.

        Returns
        -------
        State
            The winner's state, carrying its mapping and its interface order.
        """
        result = super().post_loop_callback(state)
        if self.winner is None:
            return result
        views: dict[DesignFormat, LibrelanePath] = {}
        design = self.config["DESIGN_NAME"]
        for source, fmt in (
            (self.winner.config_mem_csv, CONFIG_MEM_FORMAT),
            (self.winner.interface_order, TILE_INTERFACE_ORDER_FORMAT),
        ):
            if source is None:
                continue
            out = Path(self.step_dir) / f"{design}.{fmt.extension}"
            shutil.copyfile(source, out)
            views[fmt] = LibrelanePath(str(out))
        return State(result, overrides=views, metrics=result.metrics)

    def mid_iteration_break(self, state: State, step: Step) -> bool:
        """Stop the body after the proposals, which is what routing follows.

        Parameters
        ----------
        state : State
            The state the body has reached.
        step : Step
            The step that just ran.

        Returns
        -------
        bool
            Whether the iteration ends here.
        """
        if isinstance(step, ProposeTileInterfaceOrder) and not self.routes:
            info("Proposals read, skipping routing on this iteration")
            return True
        return super().mid_iteration_break(state, step)

    def run(
        self,
        state_in: State,
        **_kwargs: dict,
    ) -> tuple[ViewsUpdate, MetricsUpdate]:
        """Run the tile optimisation step with the proposals bounding the body."""
        self._start_run()
        return super().run(state_in, **_kwargs)

"""Search a tile's configuration mapping from the placement it produces.

Each iteration implements the last proposal, places, reads the placement back
out of OpenDB and proposes again. `DumpPlacement` sits before global routing, so
no proposal can depend on a routed design and an iteration stops at its
proposals unless `FABULOUS_OPT_ROUTE_EVERY_ITERATION` asks for routed numbers to
look at. `WhileStep` rebuilds the state every iteration, so what carries across
them lives on the step. An iteration is scored by what it implemented and not by
what it proposed, since the cost of a proposal is only known once a placement
has been made from it, and the loop exports the best-scoring iteration rather
than the last.
"""

import shutil
from dataclasses import dataclass
from pathlib import Path

from librelane.common.types import Path as LibrelanePath
from librelane.logging.logger import info
from librelane.state.design_format import DesignFormat
from librelane.state.state import State
from librelane.steps import checker as Checker
from librelane.steps import odb as Odb
from librelane.steps import openroad as OpenROAD
from librelane.steps.step import MetricsUpdate, Step, ViewsUpdate

from fabulous.custom_exception import GDSFlowError
from fabulous.fabric_definition.define import ConfigBitMode
from fabulous.fabric_generator.gds_generator.formats import (
    CONFIG_MEM_FORMAT,
    PLACEMENT_FORMAT,
    RECONNECT_FORMAT,
)
from fabulous.fabric_generator.gds_generator.helper import get_routing_obstructions
from fabulous.fabric_generator.gds_generator.steps.add_buffer import AddBuffers
from fabulous.fabric_generator.gds_generator.steps.apply_config_mapping import (
    ApplyConfigMapping,
)
from fabulous.fabric_generator.gds_generator.steps.diodes_on_ports import (
    FABulousDiodesOnPorts,
)
from fabulous.fabric_generator.gds_generator.steps.dump_placement import DumpPlacement
from fabulous.fabric_generator.gds_generator.steps.propose_config_mapping import (
    ProposeConfigMapping,
)
from fabulous.fabric_generator.gds_generator.steps.tile_IO_placement import (
    FABulousTileIOPlacement,
)
from fabulous.fabric_generator.gds_generator.steps.timed_detailed_routing import (
    FABulousDetailedRoutingTimed,
)
from fabulous.fabric_generator.gds_generator.steps.while_step import WhileStep
from fabulous.fabric_generator.gds_generator.variables import (
    CONFIG_BIT_MODE_VARIABLE,
    CONFIG_MAPPING_RECONNECT_VARIABLE,
    CONFIG_MAPPING_TARGET_VARIABLE,
    CONFIG_MAPPING_VARIABLE,
    CONFIG_MEM_CSV_VARIABLE,
    IGNORE_ANTENNA_VIOLATIONS_VARIABLE,
    PLACEMENT_ITERATIONS_VARIABLE,
    ROUTE_EVERY_ITERATION_VARIABLE,
)

UNCHANGED_METRICS = {
    CONFIG_MAPPING_VARIABLE.name: "fabulous__config_mapping__unchanged",
}
"""The metric the optimisation reports when its proposal repeats its input."""

REALISED_METRICS = {
    CONFIG_MAPPING_VARIABLE.name: "fabulous__config_mapping__stub_before",
}
"""The micrometres the optimisation still costs on the placement it produced."""


@dataclass(frozen=True)
class IterationInputs:
    """What one iteration implements: its mapping and how to rewire to it."""

    config_mem_csv: Path | None
    reconnect: Path | None


def _text(path: Path | None) -> str | None:
    """Return a path as the string a LibreLane path variable takes."""
    return None if path is None else str(path)


def _view(state: State, fmt: DesignFormat) -> Path | None:
    """Return a view of `state` as a path, or None when absent."""
    value = state.get(fmt.id)
    return None if value is None else Path(str(value))


@Step.factory.register()
class PlacementDrivenTileOptimisation(WhileStep):
    """Tile search whose iterations implement each other's proposals."""

    id = "FABulous.PlacementDrivenTileOptimisation"
    name = "Placement Driven Tile Optimisation"

    Steps = [
        OpenROAD.Floorplan,
        # The rewire follows the floorplan, since editing the ODB there is what
        # lets an iteration implement a proposal without a second synthesis run.
        ApplyConfigMapping,
        OpenROAD.DumpRCValues,
        Odb.CheckMacroAntennaProperties,
        Odb.SetPowerConnections,
        Odb.ManualMacroPlacement,
        OpenROAD.CutRows,
        OpenROAD.TapEndcapInsertion,
        Odb.AddPDNObstructions,
        OpenROAD.GeneratePDN,
        Odb.RemovePDNObstructions,
        Odb.AddRoutingObstructions,
        FABulousTileIOPlacement,
        Odb.ApplyDEFTemplate,
        FABulousDiodesOnPorts,
        OpenROAD.GlobalPlacement,
        AddBuffers,
        Odb.WriteVerilogHeader,
        Checker.PowerGridViolations,
        Odb.ManualGlobalPlacement,
        OpenROAD.DetailedPlacement,
        OpenROAD.CTS,
        # The proposals are read here, so an iteration can stop before it routes.
        DumpPlacement,
        ProposeConfigMapping,
        # Reached only when FABULOUS_OPT_ROUTE_EVERY_ITERATION asks for routed
        # numbers; nothing below feeds a proposal.
        OpenROAD.GlobalRouting,
        OpenROAD.CheckAntennas,
        OpenROAD.RepairAntennas,
        FABulousDetailedRoutingTimed,
        Odb.RemoveRoutingObstructions,
        OpenROAD.CheckAntennas,
        Checker.TrDRC,
        Odb.ReportDisconnectedPins,
        Checker.DisconnectedPins,
        Odb.ReportWireLength,
        Checker.WireLength,
    ]

    inputs = [DesignFormat.NETLIST]

    # The proposals of an iteration are inputs of the next one; only what the
    # winning iteration implemented leaves the step.
    outputs = [DesignFormat.ODB, DesignFormat.DEF, CONFIG_MEM_FORMAT, PLACEMENT_FORMAT]

    config_vars = [
        CONFIG_BIT_MODE_VARIABLE,
        CONFIG_MAPPING_VARIABLE,
        CONFIG_MEM_CSV_VARIABLE,
        IGNORE_ANTENNA_VIOLATIONS_VARIABLE,
        PLACEMENT_ITERATIONS_VARIABLE,
        ROUTE_EVERY_ITERATION_VARIABLE,
    ]

    # Carried across iterations, which rebuild the state.
    last_working_state: State | None = None

    # A placement optimisation fault must stop the flow, not read as a die
    # that is too small.
    propagate_exceptions = (GDSFlowError,)

    # Carried across iterations, which rebuild the state.
    budget: int = 0

    next_inputs: IterationInputs = IterationInputs(None, None)

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
    def routes(self) -> bool:
        """Whether the iterations route, which only produces numbers to read."""
        return bool(self.config[ROUTE_EVERY_ITERATION_VARIABLE.name])

    def _start_run(self) -> None:
        """Check the inputs of the optimisations and take their budget.

        Raises
        ------
        GDSFlowError
            If the configuration mapping is off, since the loop then has
            nothing to propose; if the die is searched, since an iteration that
            stops at its proposals gives the die rule no verdict to grow or
            shrink on; if the mapping runs under a config-bit mode other than
            FRAME_BASED, since only frames form the crosspoint grid; or if it
            runs without a `ConfigMem.csv` or without the tile's bus pairs,
            either of which means a super tile or a tile without configuration
            bits was asked for an optimisation it has no inputs for.
        """
        if not self.config_mapping:
            raise GDSFlowError(
                f"{CONFIG_MAPPING_VARIABLE.name} is off, so there is nothing to "
                "propose; harden the tile with the macro flow instead."
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
        self.budget = int(self.config[PLACEMENT_ITERATIONS_VARIABLE.name])
        self.max_iterations = self.budget
        if self.config[IGNORE_ANTENNA_VIOLATIONS_VARIABLE.name]:
            info("Ignoring antenna violations during the placement search.")
            self.config = self.config.copy(ERROR_ON_TR_DRC=False)
        self.last_working_state = None
        self.next_inputs = IterationInputs(Path(str(csv)), None)
        self.applied = None
        self.winner = None
        self.best_score = None
        self.iteration = 0
        self.converged = False

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
        self.last_working_state = state.copy()

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
            }
        )
        self.iteration += 1
        # Obstructions accumulate across iterations unless cleared first, and
        # the routed arm wants the detailed router's full effort.
        self.config = self.config.copy(DRT_OPT_ITERS=64, ROUTING_OBSTRUCTIONS=None)
        self.config = self.config.copy(
            ROUTING_OBSTRUCTIONS=get_routing_obstructions(self.config)
        )
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

    def post_loop_callback(self, state: State) -> State:  # noqa: ARG002
        """Export the winning iteration's inputs as views of the step.

        Parameters
        ----------
        state : State
            The state the last iteration ended with.

        Returns
        -------
        State
            The winner's state, carrying its mapping.

        Raises
        ------
        GDSFlowError
            If no iteration reached its proposals, which means every one of them
            broke off before the placement the search reads.
        """
        if self.last_working_state is None:
            raise GDSFlowError(
                "No iteration reached its proposals, so the search has nothing "
                "to export. The die is fixed here; give the tile a size its "
                "cells place at."
            )
        result = self.last_working_state
        if self.winner is None or self.winner.config_mem_csv is None:
            return result
        design = self.config["DESIGN_NAME"]
        out = Path(self.step_dir) / f"{design}.{CONFIG_MEM_FORMAT.extension}"
        shutil.copyfile(self.winner.config_mem_csv, out)
        views: dict[DesignFormat, LibrelanePath] = {
            CONFIG_MEM_FORMAT: LibrelanePath(str(out))
        }
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
        if isinstance(step, ProposeConfigMapping) and not self.routes:
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

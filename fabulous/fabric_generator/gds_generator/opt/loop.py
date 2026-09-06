"""Carry proposals between iterations of the tile area optimisation.

`WhileStep` rebuilds the state every iteration, so everything the loop of "How
to shrink my FPGAs" must remember lives on one `PlacementOptLoop` that
`TileAreaOptimisation` keeps for the whole run and calls from its hooks: which
inputs the running iteration implements, which proposals it produced, whether
they converged, which clean iteration is the winner so far and how many
iterations the budget still allows.

Under no_opt the budget is the iteration count and only the last iteration
routes unless every iteration is asked to. Under balance and large the die
grows to its first clean iteration under the step's usual cap, then the budget
counts iterations after that first clean one, each shrinking after a clean run
and holding after a failed one. The winner is the clean iteration with the
smallest die, then the smallest routed wirelength, because proposals keep
changing and the latest is not the best.
"""

import shutil
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path

from librelane.common.types import Path as LibrelanePath
from librelane.config.config import Config
from librelane.logging.logger import info
from librelane.state.design_format import DesignFormat
from librelane.state.state import State

from fabulous.custom_exception import GDSFlowError
from fabulous.fabric_definition.configmem import ConfigMem
from fabulous.fabric_definition.define import ConfigBitMode
from fabulous.fabric_generator.gds_generator.formats import (
    CONFIG_MEM_FORMAT,
    RECONNECT_FORMAT,
    TILE_INTERFACE_ORDER_FORMAT,
)
from fabulous.fabric_generator.gds_generator.opt.tile_interface import (
    read_interface_order,
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


@dataclass(frozen=True)
class IterationInputs:
    """What one iteration implements: its mapping, how to rewire to it, its order."""

    config_mem_csv: Path | None
    reconnect: Path | None
    interface_order: Path | None


def _same_inputs(applied: IterationInputs, proposed: IterationInputs) -> bool:
    """Return whether a proposal repeats the inputs it was made from, by content."""
    if (applied.config_mem_csv is None) != (proposed.config_mem_csv is None):
        return False
    if (applied.interface_order is None) != (proposed.interface_order is None):
        return False
    same_mapping = (
        applied.config_mem_csv is None
        or proposed.config_mem_csv is None
        or ConfigMem.from_csv(applied.config_mem_csv).bit_at
        == ConfigMem.from_csv(proposed.config_mem_csv).bit_at
    )
    same_order = (
        applied.interface_order is None
        or proposed.interface_order is None
        or read_interface_order(applied.interface_order)
        == read_interface_order(proposed.interface_order)
    )
    return same_mapping and same_order


def _metric(state: State, name: str) -> str:
    """Return a metric of a finished iteration.

    Parameters
    ----------
    state : State
        The state the iteration ended with.
    name : str
        The metric name.

    Returns
    -------
    str
        The metric value as reported.

    Raises
    ------
    GDSFlowError
        If the iteration reported no such metric, since the winner cannot be
        scored without it.
    """
    value = state.metrics.get(name)
    if value is None:
        raise GDSFlowError(f"The iteration reported no {name} metric")
    return str(value)


class PlacementOptLoop:
    """Iteration bookkeeping for the placement-driven optimisations.

    Parameters
    ----------
    config : Config
        The area optimisation step's config at the start of its run.
    growth_cap : int
        How many iterations the die may grow before the first clean one, the
        step's usual iteration cap.
    no_opt : bool
        Whether the die is fixed, in which case the budget is the iteration
        count and routing is skipped until the last iteration.

    Raises
    ------
    GDSFlowError
        If neither optimisation is on, since the loop then has nothing to
        propose; if configuration mapping is on under a config-bit mode other
        than FRAME_BASED, since only frames form the crosspoint grid; if it is
        on without a `ConfigMem.csv`; or if the tile interface ordering is on
        without the tile's bus pairs, since either of the last two means a
        super tile or a tile without configuration bits was asked for an
        optimisation it has no inputs for.
    """

    def __init__(self, config: Config, *, growth_cap: int, no_opt: bool) -> None:
        self.config_mapping = bool(config[CONFIG_MAPPING_VARIABLE.name])
        self.tile_interface = bool(config[TILE_INTERFACE_VARIABLE.name])
        if not (self.config_mapping or self.tile_interface):
            raise GDSFlowError(
                f"Neither {CONFIG_MAPPING_VARIABLE.name} nor "
                f"{TILE_INTERFACE_VARIABLE.name} is on, so there is nothing to "
                "propose; harden the tile with the macro flow instead."
            )
        self.growth_cap = growth_cap
        self.no_opt = no_opt
        self.budget: int = 0
        self.route_every = False
        self.fixed_order: Path | None = None
        self.next_inputs = IterationInputs(None, None, None)
        self.applied: IterationInputs | None = None
        self.winner: IterationInputs | None = None
        self.best_score: tuple[Decimal, Decimal] | None = None
        self.iteration = 0
        self.since_clean = 0
        self.clean_seen = False
        self.last_clean = False
        self.last_routed = False
        self.converged = False
        self.shrink_exhausted = False
        mode = ConfigBitMode(config[CONFIG_BIT_MODE_VARIABLE.name])
        if self.config_mapping and mode is not ConfigBitMode.FRAME_BASED:
            raise GDSFlowError(
                f"{CONFIG_MAPPING_VARIABLE.name} needs {CONFIG_BIT_MODE_VARIABLE.name} "
                f"FRAME_BASED, not {mode.name}; only frames form the crosspoint "
                "grid the mapping assigns bits on."
            )
        csv = config[CONFIG_MEM_CSV_VARIABLE.name]
        if self.config_mapping and csv is None:
            raise GDSFlowError(
                f"{CONFIG_MAPPING_VARIABLE.name} needs {CONFIG_MEM_CSV_VARIABLE.name}; "
                "a super tile or a tile without configuration bits has no "
                "configuration memory to map."
            )
        if self.tile_interface and config[TILE_INTERFACE_PAIRS_VARIABLE.name] is None:
            raise GDSFlowError(
                f"{TILE_INTERFACE_VARIABLE.name} needs "
                f"{TILE_INTERFACE_PAIRS_VARIABLE.name}; a super tile's borders are "
                "not reordered."
            )
        order = config[TILE_INTERFACE_ORDER_VARIABLE.name]
        self.fixed_order = None if order is None else Path(str(order))
        self.budget = int(config[PLACEMENT_ITERATIONS_VARIABLE.name])
        self.route_every = bool(config[ROUTE_EVERY_ITERATION_VARIABLE.name])
        self.next_inputs = IterationInputs(
            None if not self.config_mapping else Path(str(csv)),
            None,
            self.fixed_order,
        )

    @property
    def max_iterations(self) -> int:
        """Bound on the body: growth cap plus budget, so neither cuts the other."""
        return self.growth_cap + self.budget

    def _routes_next(self) -> bool:
        """Return whether the iteration about to start goes through routing."""
        if not self.no_opt or self.route_every:
            return True
        return self.converged or self.iteration >= self.budget

    def begin_iteration(self, config: Config) -> Config:
        """Point an iteration's config at the proposals of the previous one.

        Parameters
        ----------
        config : Config
            The step config before the iteration.

        Returns
        -------
        Config
            The config with the mapping target, reconnection list, applied
            interface order and fixed interface order of this iteration.
        """
        self.applied = self.next_inputs
        config = config.copy(
            **{
                CONFIG_MAPPING_TARGET_VARIABLE.name: _text(self.applied.config_mem_csv),
                CONFIG_MAPPING_RECONNECT_VARIABLE.name: _text(self.applied.reconnect),
                TILE_INTERFACE_ORDER_VARIABLE.name: _text(self.applied.interface_order),
                TILE_INTERFACE_FIXED_ORDER_VARIABLE.name: _text(self.fixed_order),
            }
        )
        self.iteration += 1
        if self.clean_seen:
            self.since_clean += 1
        self.last_routed = self._routes_next()
        return config

    def end_iteration(self, state: State, clean: bool) -> None:
        """Keep the proposals of a finished iteration and note convergence.

        Parameters
        ----------
        state : State
            The state the iteration ended with, complete or broken off.
        clean : bool
            Whether the iteration ran to the end without violations.
        """
        assert self.applied is not None
        self.last_clean = clean
        self.clean_seen = self.clean_seen or clean
        proposals = IterationInputs(
            _view(state, CONFIG_MEM_FORMAT) or self.applied.config_mem_csv,
            _view(state, RECONNECT_FORMAT) or self.applied.reconnect,
            _view(state, TILE_INTERFACE_ORDER_FORMAT) or self.applied.interface_order,
        )
        if proposals == self.applied:
            # Neither proposal step ran, so there is nothing to converge on.
            return
        self.converged = _same_inputs(self.applied, proposals)
        if self.converged:
            info("Proposals match the inputs of this iteration: converged")
        self.next_inputs = proposals

    def consider(self, state: State) -> bool:
        """Score a clean iteration and say whether it is the winner so far.

        Parameters
        ----------
        state : State
            The clean iteration's final state.

        Returns
        -------
        bool
            True when this iteration beats every earlier clean one.
        """
        x0, y0, x1, y1 = (
            Decimal(v) for v in _metric(state, "design__die__bbox").split()
        )
        score = (
            (x1 - x0) * (y1 - y0),
            Decimal(_metric(state, "route__wirelength")),
        )
        if self.best_score is not None and score >= self.best_score:
            return False
        self.best_score = score
        self.winner = self.applied
        return True

    def should_continue(self) -> bool:
        """Loop condition for the non-directional modes."""
        if self.shrink_exhausted:
            return False
        if self.no_opt:
            if self.iteration >= self.budget:
                return False
            return not (self.last_routed and (self.converged or not self.route_every))
        if not self.clean_seen:
            return self.iteration < self.growth_cap
        return self.since_clean < self.budget

    def export_winner(
        self, step_dir: Path, design: str
    ) -> dict[DesignFormat, LibrelanePath]:
        """Copy the winner's inputs into the step directory as views.

        Parameters
        ----------
        step_dir : Path
            The area optimisation step directory.
        design : str
            The design name the views are named after.

        Returns
        -------
        dict[DesignFormat, LibrelanePath]
            The configuration memory and interface order views, each present
            only when the winner implemented one.
        """
        assert self.winner is not None
        views: dict[DesignFormat, LibrelanePath] = {}
        for source, fmt in (
            (self.winner.config_mem_csv, CONFIG_MEM_FORMAT),
            (self.winner.interface_order, TILE_INTERFACE_ORDER_FORMAT),
        ):
            if source is None:
                continue
            out = step_dir / f"{design}.{fmt.extension}"
            shutil.copyfile(source, out)
            views[fmt] = LibrelanePath(str(out))
        return views


def _text(path: Path | None) -> str | None:
    """Return a path as the string a LibreLane path variable takes."""
    return None if path is None else str(path)


def _view(state: State, fmt: DesignFormat) -> Path | None:
    """Return a view of `state` as a path, or None when absent."""
    value = state.get(fmt.id)
    return None if value is None else Path(str(value))

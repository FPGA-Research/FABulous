"""PnR pass wrapper for routing-demand evaluation."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from fabulous.fabric_cad.fabxplore.modules.routing_demand_evaluator import (
    RoutingDemandEvaluator,
    RoutingDemandEvaluatorOptions,
    RoutingDemandEvaluatorResult,
)
from fabulous.fabric_cad.fabxplore.modules.routing_demand_evaluator.core.models import (
    DemandProfileName,
    OptimizerName,
    RouterName,
)
from fabulous.fabric_cad.fabxplore.pnr.pnr_pass import PnRPass

if TYPE_CHECKING:
    from pathlib import Path

    from fabulous.fabric_cad.fabxplore.pyosys.pyosys_bridge import PyosysBridge
    from fabulous.fabulous_api import FABulous_API


@dataclass
class RoutingDemandEvaluatorPass(PnRPass):
    """Evaluate synthetic routing demands for one FABulous tile.

    Attributes
    ----------
    tile_name : str
        FABulous tile to evaluate.
    tile_dir : Path | None
        Optional tile directory override.
    tile_csv : Path | None
        Optional tile CSV override.
    switch_matrix : Path | None
        Optional switch-matrix list or CSV override.
    demand_profile : DemandProfileName | str
        Demand profile name.
    demand_iterations : int
        Target demand count.
    random_demand_ratio : float
        Fraction of demands reserved for random soft demands.
    seed : int
        Random seed.
    opt : bool
        Whether optimization is enabled.
    optimizer : OptimizerName | str
        Optimizer name.
    opt_target_pip_reduction : float
        Target PIP reduction for optimizers.
    opt_max_soft_failure_rate : float
        Maximum optimizer-added soft-demand failure rate.
    opt_max_hard_failure_rate : float
        Maximum optimizer-added hard-demand failure rate.
    opt_use_baseline_failure_rates : bool
        Whether optimizer failure-rate limits are added to the baseline rates.
    opt_write_back : bool
        Whether optimizer changes overwrite the active tile files in place.
    report_max_soft_failure_rate : float
        Maximum soft-demand failure rate before the report status becomes a warning.
    router : RouterName | str
        Router name.
    router_max_iterations : int
        Maximum router negotiation iterations.
    router_present_cost_multiplier : float
        Present congestion cost multiplier.
    router_history_cost_increment : float
        Historical congestion increment.
    router_base_resource_capacity : int
        Default resource capacity before congestion is reported.
    fanout_targets : list[int] | None
        Fanout sizes used by fanout-style demand classes.
    max_net_sinks : int
        Maximum sinks in one generated net demand.
    config_bit_capacity_override : int | None
        Optional total config-bit capacity. ``None`` uses the loaded FABulous fabric.
    config_bit_margin : int
        Reserved config-bit margin.
    track_progress : bool
        Whether progress should be logged.
    """

    tile_name: str
    tile_dir: Path | None = None
    tile_csv: Path | None = None
    switch_matrix: Path | None = None
    demand_profile: DemandProfileName | str = DemandProfileName.DEFAULT
    demand_iterations: int = 1000
    random_demand_ratio: float = 0.25
    seed: int = 1
    opt: bool = False
    optimizer: OptimizerName | str = OptimizerName.NONE
    opt_target_pip_reduction: float = 0.20
    opt_max_soft_failure_rate: float = 0.05
    opt_max_hard_failure_rate: float = 0.0
    opt_use_baseline_failure_rates: bool = True
    opt_write_back: bool = False
    report_max_soft_failure_rate: float = 0.05
    router: RouterName | str = RouterName.PATHFINDER
    router_max_iterations: int = 30
    router_present_cost_multiplier: float = 1.3
    router_history_cost_increment: float = 1.0
    router_base_resource_capacity: int = 1
    fanout_targets: list[int] | None = None
    max_net_sinks: int = 8
    config_bit_capacity_override: int | None = None
    config_bit_margin: int = 0
    track_progress: bool = True

    _result: RoutingDemandEvaluatorResult | None = None

    def run_on(self, design: PyosysBridge, fab: FABulous_API) -> None:
        """Run routing-demand evaluation.

        Parameters
        ----------
        design : PyosysBridge
            Packed design associated with the architecture flow.
        fab : FABulous_API
            Loaded FABulous API instance.
        """
        options = RoutingDemandEvaluatorOptions(
            tile_name=self.tile_name,
            tile_dir=self.tile_dir,
            tile_csv=self.tile_csv,
            switch_matrix=self.switch_matrix,
            demand_profile=self.demand_profile,
            demand_iterations=self.demand_iterations,
            random_demand_ratio=self.random_demand_ratio,
            seed=self.seed,
            opt=self.opt,
            optimizer=self.optimizer,
            opt_target_pip_reduction=self.opt_target_pip_reduction,
            opt_max_soft_failure_rate=self.opt_max_soft_failure_rate,
            opt_max_hard_failure_rate=self.opt_max_hard_failure_rate,
            opt_use_baseline_failure_rates=self.opt_use_baseline_failure_rates,
            opt_write_back=self.opt_write_back,
            report_max_soft_failure_rate=self.report_max_soft_failure_rate,
            router=self.router,
            router_max_iterations=self.router_max_iterations,
            router_present_cost_multiplier=self.router_present_cost_multiplier,
            router_history_cost_increment=self.router_history_cost_increment,
            router_base_resource_capacity=self.router_base_resource_capacity,
            fanout_targets=self.fanout_targets or [2, 4, 8],
            max_net_sinks=self.max_net_sinks,
            config_bit_capacity_override=self.config_bit_capacity_override,
            config_bit_margin=self.config_bit_margin,
            track_progress=self.track_progress,
        )
        self._result = RoutingDemandEvaluator(options).run(design, fab)

    @property
    def report_summary(self) -> str:
        """Return the latest report summary.

        Returns
        -------
        str
            Report text, or a placeholder if the pass has not run.
        """
        return self._result.report_summary if self._result else "No result available."

    @property
    def result_data(self) -> RoutingDemandEvaluatorResult | None:
        """Return the latest structured result.

        Returns
        -------
        RoutingDemandEvaluatorResult | None
            Latest result if available.
        """
        return self._result

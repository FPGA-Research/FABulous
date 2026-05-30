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
    from fabulous.fabric_cad.fabxplore.pnr.pnr_bridge import PnRBridge


@dataclass
class RoutingDemandEvaluatorPass(PnRPass):
    """Evaluate synthetic routing demands for one FABulous tile.

    Attributes
    ----------
    tile_name : str
        FABulous tile to evaluate.
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
    apply_to_tile_model : bool
        Whether optimizer changes update the in-memory FabGraph tile model.
    opt_max_iterations : int
        Maximum optimizer pruning iterations.
    opt_clean_mux : bool
        Whether greedy optimization should prefer mux bucket cleanup.
    opt_power_of_two_muxes : bool
        Whether mux cleanup should require power-of-two mux fanins where possible.
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
    config_bit_margin : int
        Reserved config-bit margin.
    track_progress : bool
        Whether progress should be logged.
    progress_chunk_size : int
        Number of optimizer iterations between progress updates.
    """

    tile_name: str
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
    apply_to_tile_model: bool = False
    opt_max_iterations: int = 50
    opt_clean_mux: bool = False
    opt_power_of_two_muxes: bool = False
    report_max_soft_failure_rate: float = 0.05
    router: RouterName | str = RouterName.PATHFINDER
    router_max_iterations: int = 30
    router_present_cost_multiplier: float = 1.3
    router_history_cost_increment: float = 1.0
    router_base_resource_capacity: int = 1
    fanout_targets: list[int] | None = None
    max_net_sinks: int = 8
    config_bit_margin: int = 0
    track_progress: bool = True
    progress_chunk_size: int = 10

    _result: RoutingDemandEvaluatorResult | None = None

    def run_on(self, fpga_model: PnRBridge) -> None:
        """Run routing-demand evaluation.

        Parameters
        ----------
        fpga_model : PnRBridge
            Combined packed design, FABulous project API, and routing graph.
        """
        options = RoutingDemandEvaluatorOptions(
            tile_name=self.tile_name,
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
            apply_to_tile_model=self.apply_to_tile_model,
            opt_max_iterations=self.opt_max_iterations,
            opt_clean_mux=self.opt_clean_mux,
            opt_power_of_two_muxes=self.opt_power_of_two_muxes,
            report_max_soft_failure_rate=self.report_max_soft_failure_rate,
            router=self.router,
            router_max_iterations=self.router_max_iterations,
            router_present_cost_multiplier=self.router_present_cost_multiplier,
            router_history_cost_increment=self.router_history_cost_increment,
            router_base_resource_capacity=self.router_base_resource_capacity,
            fanout_targets=self.fanout_targets or [2, 4, 8],
            max_net_sinks=self.max_net_sinks,
            config_bit_margin=self.config_bit_margin,
            track_progress=self.track_progress,
            progress_chunk_size=self.progress_chunk_size,
        )
        self._result = RoutingDemandEvaluator(options).run(fpga_model)

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

"""Base optimizer interface for routing-demand evaluation."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    from fabulous.fabric_cad.fabxplore.modules.routing_demand_evaluator.core.models import (  # noqa: E501
        DemandProfileResult,
        MatrixData,
        RoutingDemandEvaluatorOptions,
        RoutingDemandEvaluatorResult,
    )
    from fabulous.fabric_cad.fabxplore.modules.routing_demand_evaluator.core.process_tracker import (  # noqa: E501
        RoutingDemandProcessTracker,
    )
    from fabulous.fabric_cad.fabxplore.modules.routing_demand_evaluator.core.routing_graph import (  # noqa: E501
        RoutingGraph,
    )
    from fabulous.fabric_cad.fabxplore.modules.routing_demand_evaluator.routers.base import (  # noqa: E501
        RoutingDemandRouter,
    )
    from fabulous.fabric_cad.fabxplore.pnr.pnr_bridge import PnRBridge


class EvaluationOracle(Protocol):
    """Callable protocol for optimizer demand-oracle evaluations."""

    def __call__(
        self,
        graph: RoutingGraph,
        warnings: list[str],
        *,
        track_router: bool = False,
    ) -> RoutingDemandEvaluatorResult:
        """Evaluate one routing graph candidate."""


@dataclass(frozen=True)
class OptimizerContext:
    """Context passed to routing-matrix optimizers.

    Attributes
    ----------
    options : RoutingDemandEvaluatorOptions
        Evaluator options.
    matrix : MatrixData
        Loaded matrix metadata.
    graph : RoutingGraph
        Current routing graph.
    demand_profile : DemandProfileResult
        Generated demand profile.
    router : RoutingDemandRouter
        Router used as the demand oracle.
    fpga_model : PnRBridge
        Active PnR bridge whose graph may be updated by optimizers.
    tracker : RoutingDemandProcessTracker
        Progress tracker for optimizer status.
    warnings : list[str]
        Existing warnings.
    evaluate : EvaluationOracle
        Evaluation oracle callable.
    """

    options: RoutingDemandEvaluatorOptions
    matrix: MatrixData
    graph: RoutingGraph
    demand_profile: DemandProfileResult
    router: RoutingDemandRouter
    fpga_model: PnRBridge
    tracker: RoutingDemandProcessTracker
    warnings: list[str]
    evaluate: EvaluationOracle


class RoutingDemandOptimizer(ABC):
    """Abstract optimizer interface."""

    @abstractmethod
    def optimize(self, context: OptimizerContext) -> RoutingDemandEvaluatorResult:
        """Optimize or evaluate a routing matrix.

        Parameters
        ----------
        context : OptimizerContext
            Optimizer context.

        Returns
        -------
        RoutingDemandEvaluatorResult
            Evaluation result after optimization.
        """

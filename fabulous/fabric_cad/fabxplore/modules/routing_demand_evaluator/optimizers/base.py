"""Base optimizer interface for routing-demand evaluation."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Callable

    from fabulous.fabric_cad.fabxplore.modules.routing_demand_evaluator.core.models import (  # noqa: E501
        DemandProfileResult,
        MatrixData,
        RoutingDemandEvaluatorOptions,
        RoutingDemandEvaluatorResult,
    )
    from fabulous.fabric_cad.fabxplore.modules.routing_demand_evaluator.core.routing_graph import (  # noqa: E501
        RoutingGraph,
    )
    from fabulous.fabric_cad.fabxplore.modules.routing_demand_evaluator.routers.base import (  # noqa: E501
        RoutingDemandRouter,
    )


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
    warnings : list[str]
        Existing warnings.
    evaluate : Callable[[RoutingGraph, list[str]], RoutingDemandEvaluatorResult]
        Evaluation oracle callable.
    """

    options: RoutingDemandEvaluatorOptions
    matrix: MatrixData
    graph: RoutingGraph
    demand_profile: DemandProfileResult
    router: RoutingDemandRouter
    warnings: list[str]
    evaluate: Callable[[RoutingGraph, list[str]], RoutingDemandEvaluatorResult]


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

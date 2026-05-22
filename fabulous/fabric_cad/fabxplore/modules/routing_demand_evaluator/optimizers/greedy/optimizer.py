"""Greedy optimizer placeholder."""

from __future__ import annotations

from typing import TYPE_CHECKING

from fabulous.fabric_cad.fabxplore.modules.routing_demand_evaluator.optimizers.base import (  # noqa: E501
    OptimizerContext,
    RoutingDemandOptimizer,
)

if TYPE_CHECKING:
    from fabulous.fabric_cad.fabxplore.modules.routing_demand_evaluator.core.models import (  # noqa: E501
        RoutingDemandEvaluatorResult,
    )


class GreedyOptimizer(RoutingDemandOptimizer):
    """Placeholder for future greedy demand-oracle pruning."""

    def optimize(self, context: OptimizerContext) -> RoutingDemandEvaluatorResult:
        """Raise until greedy optimization is implemented.

        Parameters
        ----------
        context : OptimizerContext
            Optimizer context.

        Raises
        ------
        NotImplementedError
            Always raised for the placeholder implementation.

        Returns
        -------
        RoutingDemandEvaluatorResult
            Optimized routing-demand evaluation result.
        """
        _ = context
        raise NotImplementedError(
            "greedy routing-demand optimization is not implemented"
        )

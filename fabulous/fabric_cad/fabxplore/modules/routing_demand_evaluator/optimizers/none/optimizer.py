"""No-op optimizer for evaluate-only runs."""

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


class NoOptimizer(RoutingDemandOptimizer):
    """Evaluate the matrix without mutation."""

    def optimize(self, context: OptimizerContext) -> RoutingDemandEvaluatorResult:
        """Run the evaluator without optimization.

        Parameters
        ----------
        context : OptimizerContext
            Optimizer context.

        Returns
        -------
        RoutingDemandEvaluatorResult
            Evaluation result.
        """
        return context.evaluate(context.graph, [])

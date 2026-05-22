"""Monte Carlo optimizer placeholder."""

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


class MonteCarloOptimizer(RoutingDemandOptimizer):
    """Placeholder for future Monte Carlo PIP-importance pruning."""

    def optimize(self, context: OptimizerContext) -> RoutingDemandEvaluatorResult:
        """Raise until Monte Carlo optimization is implemented.

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
             The result of the optimization.
        """
        _ = context
        raise NotImplementedError(
            "Monte Carlo routing-demand optimization is not implemented"
        )

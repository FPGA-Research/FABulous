"""Optimizer registry for routing-demand evaluation."""

from __future__ import annotations

from typing import TYPE_CHECKING

from fabulous.fabric_cad.fabxplore.modules.routing_demand_evaluator.core.models import (
    OptimizerName,
    RoutingDemandEvaluatorOptions,
)
from fabulous.fabric_cad.fabxplore.modules.routing_demand_evaluator.optimizers.dense.optimizer import (  # noqa: E501
    DenseOptimizer,
)
from fabulous.fabric_cad.fabxplore.modules.routing_demand_evaluator.optimizers.greedy.optimizer import (  # noqa: E501
    GreedyOptimizer,
)
from fabulous.fabric_cad.fabxplore.modules.routing_demand_evaluator.optimizers.monte_carlo.optimizer import (  # noqa: E501
    MonteCarloOptimizer,
)
from fabulous.fabric_cad.fabxplore.modules.routing_demand_evaluator.optimizers.none.optimizer import (  # noqa: E501
    NoOptimizer,
)

if TYPE_CHECKING:
    from fabulous.fabric_cad.fabxplore.modules.routing_demand_evaluator.optimizers.base import (  # noqa: E501
        RoutingDemandOptimizer,
    )


def create_optimizer(
    options: RoutingDemandEvaluatorOptions,
) -> RoutingDemandOptimizer:
    """Create an optimizer from evaluator options.

    Parameters
    ----------
    options : RoutingDemandEvaluatorOptions
        Evaluator options.

    Returns
    -------
    RoutingDemandOptimizer
        Optimizer implementation.

    Raises
    ------
    ValueError
        If the optimizer is unknown.
    """
    match options.optimizer:
        case OptimizerName.NONE:
            return NoOptimizer()
        case OptimizerName.GREEDY:
            return GreedyOptimizer()
        case OptimizerName.DENSE:
            return DenseOptimizer()
        case OptimizerName.MONTE_CARLO:
            return MonteCarloOptimizer()
        case _:
            raise ValueError(f"Unknown optimizer: {options.optimizer}")

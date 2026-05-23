"""Scoring functions for the Monte Carlo optimizer."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from fabulous.fabric_cad.fabxplore.modules.routing_demand_evaluator.core.models import (  # noqa: E501
        RoutingDemandEvaluatorResult,
    )
    from fabulous.fabric_cad.fabxplore.modules.routing_demand_evaluator.optimizers.monte_carlo.matrix import (  # noqa: E501
        CandidateBatch,
        ImportanceByPip,
    )


def demand_loss(
    candidate: RoutingDemandEvaluatorResult,
    baseline: RoutingDemandEvaluatorResult,
) -> float:
    """Return a scalar regression loss for one ablation result.

    The loss is intentionally conservative: hard-demand regressions dominate
    soft-demand regressions, and soft-demand regressions dominate path-length
    changes. A PIP with a higher loss when removed is considered more important.

    Parameters
    ----------
    candidate : RoutingDemandEvaluatorResult
        Candidate ablation result.
    baseline : RoutingDemandEvaluatorResult
        Baseline result.

    Returns
    -------
    float
        Non-negative regression loss.
    """
    hard_delta = max(
        candidate.stats.hard_failure_rate - baseline.stats.hard_failure_rate,
        0.0,
    )
    soft_delta = max(
        candidate.stats.soft_failure_rate - baseline.stats.soft_failure_rate,
        0.0,
    )
    sink_scale = max(baseline.stats.failed_sinks, baseline.stats.total_demands, 1)
    failed_sink_delta = (
        max(
            candidate.stats.failed_sinks - baseline.stats.failed_sinks,
            0,
        )
        / sink_scale
    )
    path_delta = max(
        candidate.stats.average_path_length - baseline.stats.average_path_length,
        0.0,
    ) / max(baseline.stats.average_path_length, 1.0)
    return (
        (1000.0 * hard_delta)
        + (100.0 * soft_delta)
        + (10.0 * failed_sink_delta)
        + path_delta
    )


def batch_importance(
    batch: CandidateBatch,
    importance_by_pip: ImportanceByPip,
) -> float:
    """Return total estimated risk for removing one candidate batch.

    Parameters
    ----------
    batch : CandidateBatch
        Candidate batch.
    importance_by_pip : ImportanceByPip
        Importance values keyed by PIP.

    Returns
    -------
    float
        Total positive importance.
    """
    return sum(max(importance_by_pip.get(pip, 0.0), 0.0) for pip in batch.pips)


def batch_value(batch: CandidateBatch, importance_by_pip: ImportanceByPip) -> float:
    """Return a pruning value score for one candidate batch.

    Parameters
    ----------
    batch : CandidateBatch
        Candidate batch.
    importance_by_pip : ImportanceByPip
        Importance values keyed by PIP.

    Returns
    -------
    float
        Higher scores are better pruning candidates.
    """
    saved = len(batch.pips) + batch.config_bits_saved + batch.mux_cost_saved
    risk = batch_importance(batch, importance_by_pip)
    power_bonus = 1.25 if batch.normalizes_power_of_two else 1.0
    return power_bonus * saved / (1.0 + risk)

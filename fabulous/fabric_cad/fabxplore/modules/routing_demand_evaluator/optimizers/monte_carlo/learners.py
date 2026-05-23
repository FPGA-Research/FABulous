"""Importance learners for the Monte Carlo optimizer."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    from collections.abc import Sequence

    from fabulous.fabric_cad.fabxplore.modules.routing_demand_evaluator.optimizers.monte_carlo.matrix import (  # noqa: E501
        ImportanceByPip,
        Pip,
    )


class ImportanceLearner(Protocol):
    """Contract for internal Monte Carlo importance learners."""

    def observe(self, pips: Sequence[Pip], loss: float) -> None:
        """Add one temporary ablation observation.

        Parameters
        ----------
        pips : Sequence[Pip]
            PIPs removed in the temporary ablation batch.
        loss : float
            Demand-regression loss measured after removing the batch.
        """

    def penalize(self, pips: Sequence[Pip], loss: float) -> None:
        """Increase importance for a rejected pruning observation.

        Parameters
        ----------
        pips : Sequence[Pip]
            PIPs in a pruning batch rejected by the demand oracle.
        loss : float
            Loss measured for the rejected pruning candidate.
        """

    def scores(self) -> ImportanceByPip:
        """Return current importance scores keyed by PIP.

        Returns
        -------
        ImportanceByPip
            Current non-negative importance estimate for each known PIP.
        """


@dataclass(frozen=True)
class AblationSample:
    """One temporary ablation observation.

    Attributes
    ----------
    pips : frozenset[Pip]
        PIPs removed for the temporary ablation.
    loss : float
        Demand regression loss observed for the ablation.
    """

    pips: frozenset[Pip]
    loss: float


@dataclass
class AverageDifferenceLearner:
    """Average-loss difference importance learner.

    This preserves the original estimator: a PIP is important when batches that
    remove it have higher average loss than batches that keep it.

    Attributes
    ----------
    all_pips : list[Pip]
        Complete set of PIPs that should receive an importance score.
    samples : list[AblationSample]
        Temporary ablation observations accumulated during learning.
    penalties : ImportanceByPip
        Extra importance added for rejected pruning candidates.
    """

    all_pips: list[Pip]
    samples: list[AblationSample] = field(default_factory=list)
    penalties: ImportanceByPip = field(default_factory=dict)

    def observe(self, pips: Sequence[Pip], loss: float) -> None:
        """Add one temporary ablation observation.

        Parameters
        ----------
        pips : Sequence[Pip]
            PIPs removed in the temporary ablation batch.
        loss : float
            Demand-regression loss measured after removing the batch.
        """
        self.samples.append(AblationSample(pips=frozenset(pips), loss=loss))

    def penalize(self, pips: Sequence[Pip], loss: float) -> None:
        """Increase importance for PIPs from a rejected pruning batch.

        Parameters
        ----------
        pips : Sequence[Pip]
            PIPs in a pruning batch rejected by the demand oracle.
        loss : float
            Loss measured for the rejected pruning candidate.
        """
        penalty = max(loss, 1.0) / max(len(pips), 1)
        for pip in pips:
            self.penalties[pip] = self.penalties.get(pip, 0.0) + penalty

    def scores(self) -> ImportanceByPip:
        """Return current average-difference importance scores.

        Returns
        -------
        ImportanceByPip
            Importance scores keyed by PIP, including rejection penalties.
        """
        importance = _estimate_average_difference(self.samples, self.all_pips)
        for pip, penalty in self.penalties.items():
            importance[pip] = importance.get(pip, 0.0) + penalty
        return importance


@dataclass
class GradientImportanceLearner:
    """Online gradient-style importance learner.

    The model predicts one batch loss as the sum of selected PIP weights. Each
    observation nudges only the PIPs in that batch toward the observed loss,
    distributing the update across the batch to improve high-loss attribution.

    Attributes
    ----------
    all_pips : list[Pip]
        Complete set of PIPs that should receive an importance score.
    learning_rate : float
        Fraction of prediction error applied on each observation.
    penalty_rate : float
        Scale applied to rejected-batch penalties.
    weights : ImportanceByPip
        Mutable importance weights keyed by PIP.
    """

    all_pips: list[Pip]
    learning_rate: float = 0.25
    penalty_rate: float = 1.0
    weights: ImportanceByPip = field(default_factory=dict)

    def __post_init__(self) -> None:
        """Initialize all known PIPs with zero importance."""
        for pip in self.all_pips:
            self.weights.setdefault(pip, 0.0)

    def observe(self, pips: Sequence[Pip], loss: float) -> None:
        """Apply one online batch-loss update.

        Parameters
        ----------
        pips : Sequence[Pip]
            PIPs removed in the temporary ablation batch.
        loss : float
            Demand-regression loss measured after removing the batch.
        """
        if not pips:
            return
        prediction = sum(self.weights.get(pip, 0.0) for pip in pips)
        error = loss - prediction
        update = self.learning_rate * error / len(pips)
        for pip in pips:
            self.weights[pip] = max(self.weights.get(pip, 0.0) + update, 0.0)

    def penalize(self, pips: Sequence[Pip], loss: float) -> None:
        """Increase importance for PIPs from a rejected pruning batch.

        Parameters
        ----------
        pips : Sequence[Pip]
            PIPs in a pruning batch rejected by the demand oracle.
        loss : float
            Loss measured for the rejected pruning candidate.
        """
        if not pips:
            return
        update = self.penalty_rate * max(loss, 1.0) / len(pips)
        for pip in pips:
            self.weights[pip] = self.weights.get(pip, 0.0) + update

    def scores(self) -> ImportanceByPip:
        """Return current gradient importance scores.

        Returns
        -------
        ImportanceByPip
            Snapshot of current non-negative importance weights keyed by PIP.
        """
        return dict(self.weights)


def _estimate_average_difference(
    samples: list[AblationSample],
    all_pips: list[Pip],
) -> ImportanceByPip:
    """Estimate importance using removed-vs-kept average loss.

    Parameters
    ----------
    samples : list[AblationSample]
        Temporary ablation observations.
    all_pips : list[Pip]
        Complete set of PIPs that should receive an importance score.

    Returns
    -------
    ImportanceByPip
        Non-negative importance estimate for each known PIP.
    """
    if not samples:
        return {pip: 0.0 for pip in all_pips}

    removed_sum: dict[Pip, float] = {pip: 0.0 for pip in all_pips}
    removed_count: dict[Pip, int] = {pip: 0 for pip in all_pips}
    kept_sum: dict[Pip, float] = {pip: 0.0 for pip in all_pips}
    kept_count: dict[Pip, int] = {pip: 0 for pip in all_pips}
    all_pip_set = set(all_pips)

    for sample in samples:
        removed = sample.pips & all_pip_set
        for pip in removed:
            removed_sum[pip] += sample.loss
            removed_count[pip] += 1
        for pip in all_pip_set - removed:
            kept_sum[pip] += sample.loss
            kept_count[pip] += 1

    importance: ImportanceByPip = {}
    for pip in all_pips:
        if removed_count[pip] == 0:
            importance[pip] = 0.0
            continue
        removed_avg = removed_sum[pip] / removed_count[pip]
        kept_avg = kept_sum[pip] / kept_count[pip] if kept_count[pip] else 0.0
        importance[pip] = max(removed_avg - kept_avg, 0.0)
    return importance

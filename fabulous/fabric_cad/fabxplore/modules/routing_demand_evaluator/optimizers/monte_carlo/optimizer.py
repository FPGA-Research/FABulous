"""Monte Carlo routing-demand optimizer."""

from __future__ import annotations

from dataclasses import dataclass
from math import ceil
from random import Random
from typing import TYPE_CHECKING

from fabulous.fabric_cad.fabxplore.modules.routing_demand_evaluator.core.models import (  # noqa: E501
    OptimizerStats,
    RoutingDemandEvaluatorResult,
)
from fabulous.fabric_cad.fabxplore.modules.routing_demand_evaluator.core.report import (
    render_routing_demand_report,
)
from fabulous.fabric_cad.fabxplore.modules.routing_demand_evaluator.optimizers.base import (  # noqa: E501
    OptimizerContext,
    RoutingDemandOptimizer,
)
from fabulous.fabric_cad.fabxplore.modules.routing_demand_evaluator.optimizers.monte_carlo.candidates import (  # noqa: E501
    SlidingWindowSampler,
    pruning_candidates,
    removable_pips,
    sample_ablation_batch,
)
from fabulous.fabric_cad.fabxplore.modules.routing_demand_evaluator.optimizers.monte_carlo.functions import (  # noqa: E501
    demand_loss,
)
from fabulous.fabric_cad.fabxplore.modules.routing_demand_evaluator.optimizers.monte_carlo.learners import (  # noqa: E501
    GradientImportanceLearner,
    ImportanceLearner,
)
from fabulous.fabric_cad.fabxplore.modules.routing_demand_evaluator.optimizers.monte_carlo.matrix import (  # noqa: E501
    CandidateBatch,
    Connections,
    ImportanceByPip,
    MonteCarloCounters,
    MonteCarloHyperParameters,
    MonteCarloLimits,
    Pip,
    apply_to_tile_model,
    build_graph,
    build_importance_matrix,
    copy_connections,
    estimate_config_bits,
    mux_cleanup_stats,
    non_power_of_two_mux_count,
    remove_pips,
    routing_pip_count,
    target_reached,
)

if TYPE_CHECKING:
    from pathlib import Path


@dataclass(frozen=True)
class PruningRoundResult:
    """Result from one Monte Carlo pruning round.

    Attributes
    ----------
    accepted : tuple[Connections, RoutingDemandEvaluatorResult] | None
        Accepted candidate state, or ``None`` when nothing was accepted.
    had_candidates : bool
        Whether the round found any valid candidate batch to evaluate.
    blocked_by_target_budget : bool
        Whether valid candidates existed but all exceeded the remaining strict
        power-of-two pruning budget.
    """

    accepted: tuple[Connections, RoutingDemandEvaluatorResult] | None
    had_candidates: bool
    blocked_by_target_budget: bool = False


class MonteCarloOptimizer(RoutingDemandOptimizer):
    """Monte Carlo PIP-importance pruning optimizer."""

    def optimize(self, context: OptimizerContext) -> RoutingDemandEvaluatorResult:
        """Prune switch-matrix PIPs using sampled demand regressions.

        Parameters
        ----------
        context : OptimizerContext
            Optimizer context.

        Returns
        -------
        RoutingDemandEvaluatorResult
            Evaluation result after Monte Carlo pruning.
        """
        context.tracker.evaluation_start("baseline demand oracle")
        baseline = context.evaluate(context.graph, [], track_router=True)
        limits = _failure_limits(context, baseline)
        if not _within_limits(baseline, limits):
            return _with_optimizer_stats(
                result=baseline,
                baseline=baseline,
                final_connections=context.matrix.connections,
                limits=limits,
                counters=MonteCarloCounters(),
                stop_reason="baseline_exceeds_optimizer_limits",
                applied_to_tile_model=False,
                importance_by_pip={},
                importance_file=None,
            )

        rng = Random(context.options.seed)
        connections = copy_connections(context.matrix.connections)
        current = baseline
        counters = MonteCarloCounters()
        hyperparameters = MonteCarloHyperParameters()
        target_remove = ceil(
            baseline.stats.original_routing_pips
            * context.options.opt_target_pip_reduction
        )
        all_pips = _all_pips(context.matrix.connections)
        coverage_pips = removable_pips(context.matrix.connections, set())
        stop_reason = "target_reached" if target_remove == 0 else "max_iterations"
        clean_mux = (
            context.options.opt_clean_mux or context.options.opt_power_of_two_muxes
        )
        context.tracker.optimizer_start(
            str(context.options.optimizer),
            target_remove,
            context.options.opt_max_iterations,
        )

        learner, importance_by_pip = _learn_importance(
            context=context,
            baseline=baseline,
            baseline_connections=context.matrix.connections,
            rng=rng,
            all_pips=all_pips,
            coverage_pips=coverage_pips,
            counters=counters,
            clean_mux=clean_mux,
            hyperparameters=hyperparameters,
        )

        rejected: set[Pip] = set()
        best_loss = demand_loss(current, baseline)
        while counters.pruning_iterations < context.options.opt_max_iterations:
            if target_reached(
                removed_pips=counters.accepted_pips,
                target_remove=target_remove,
            ):
                stop_reason = "target_reached"
                break

            round_result = _try_pruning_round(
                context=context,
                connections=connections,
                current=current,
                limits=limits,
                rejected=rejected,
                rng=rng,
                importance_by_pip=importance_by_pip,
                learner=learner,
                counters=counters,
                clean_mux=clean_mux,
                hyperparameters=hyperparameters,
            )
            if not round_result.had_candidates:
                if round_result.blocked_by_target_budget:
                    stop_reason = "power_of_two_budget_exhausted"
                else:
                    stop_reason = (
                        "power_of_two_blocked"
                        if context.options.opt_power_of_two_muxes
                        and non_power_of_two_mux_count(connections)
                        else "no_removable_pips"
                    )
                break
            if round_result.accepted is None:
                continue

            connections, current = round_result.accepted
            current_loss = demand_loss(current, baseline)
            if current_loss <= best_loss:
                best_loss = current_loss
                counters.best_iteration = counters.pruning_iterations

        remaining_non_power_rows = non_power_of_two_mux_count(connections)
        if context.options.opt_power_of_two_muxes and remaining_non_power_rows:
            current = current.model_copy(
                update={
                    "warnings": [
                        *current.warnings,
                        (
                            "Power-of-two mux cleanup incomplete; "
                            f"{remaining_non_power_rows} non-power-of-two "
                            "mux row(s) remain."
                        ),
                        "Tile-model apply skipped because strict power-of-two mux "
                        "cleanup did not finish.",
                    ]
                }
            )

        importance_file: Path | None = None
        should_apply = (
            context.options.apply_to_tile_model
            and counters.accepted_pips > 0
            and (
                not context.options.opt_power_of_two_muxes
                or remaining_non_power_rows == 0
            )
        )
        if should_apply:
            apply_to_tile_model(context, connections)

        result = _with_optimizer_stats(
            result=current,
            baseline=baseline,
            final_connections=connections,
            limits=limits,
            counters=counters,
            stop_reason=stop_reason,
            applied_to_tile_model=should_apply,
            importance_by_pip=importance_by_pip,
            importance_file=importance_file,
        )
        context.tracker.optimizer_finish(
            removed_pips=counters.accepted_pips,
            final_pips=result.stats.final_pips,
            stop_reason=stop_reason,
        )
        return result


def _learn_importance(
    context: OptimizerContext,
    baseline: RoutingDemandEvaluatorResult,
    baseline_connections: Connections,
    rng: Random,
    all_pips: list[Pip],
    coverage_pips: list[Pip],
    counters: MonteCarloCounters,
    clean_mux: bool,
    hyperparameters: MonteCarloHyperParameters,
) -> tuple[ImportanceLearner, ImportanceByPip]:
    """Learn PIP importance from temporary Monte Carlo ablations.

    Parameters
    ----------
    context : OptimizerContext
        Optimizer context.
    baseline : RoutingDemandEvaluatorResult
        Baseline result.
    baseline_connections : Connections
        Baseline matrix connections used for every temporary ablation.
    rng : Random
        Random source.
    all_pips : list[Pip]
        PIPs to score.
    coverage_pips : list[Pip]
        Removable PIPs expected to receive learning coverage.
    counters : MonteCarloCounters
        Mutable counters.
    clean_mux : bool
        Whether mux-aware sampling is enabled.
    hyperparameters : MonteCarloHyperParameters
        Internal Monte Carlo tuning constants.

    Returns
    -------
    tuple[ImportanceLearner, ImportanceByPip]
        Importance learner and learned PIP importance values.
    """
    learner: ImportanceLearner = GradientImportanceLearner(
        all_pips=all_pips,
        learning_rate=hyperparameters.gradient_learning_rate,
        penalty_rate=hyperparameters.rejected_penalty_rate,
    )
    previous_importance = learner.scores()
    importance_by_pip: ImportanceByPip = dict(previous_importance)
    sample_counts: dict[Pip, int] = {pip: 0 for pip in coverage_pips}
    total_sample_loss = 0.0
    window_sampler = SlidingWindowSampler(
        pips=coverage_pips,
        rng=rng,
        batch_size=hyperparameters.learning_batch_size,
    )
    rejected: set[Pip] = set()
    last_change_iteration = 0
    while counters.learning_iterations < context.options.opt_max_iterations:
        batch = sample_ablation_batch(
            connections=baseline_connections,
            rng=rng,
            rejected=rejected,
            clean_mux=clean_mux,
            power_of_two_muxes=context.options.opt_power_of_two_muxes,
            window_sampler=window_sampler,
            force_window=any(count == 0 for count in sample_counts.values()),
        )
        if batch is None:
            break
        loss = _evaluate_ablation_loss(
            context=context,
            baseline=baseline,
            baseline_connections=baseline_connections,
            pips=batch.pips,
        )
        total_sample_loss = _record_learning_observation(
            counters=counters,
            learner=learner,
            sample_counts=sample_counts,
            pips=batch.pips,
            loss=loss,
            total_sample_loss=total_sample_loss,
        )
        previous_importance, last_change_iteration = _update_learning_log(
            context=context,
            counters=counters,
            learner=learner,
            previous_importance=previous_importance,
            last_change_iteration=last_change_iteration,
            scored_pips=len(all_pips),
            window_sampler=window_sampler,
        )

        if _should_refine_high_loss_batch(
            batch=batch,
            loss=loss,
            counters=counters,
            hyperparameters=hyperparameters,
        ):
            for refined_pips in _high_loss_refinement_batches(batch.pips):
                if counters.learning_iterations >= context.options.opt_max_iterations:
                    break
                refined_loss = _evaluate_ablation_loss(
                    context=context,
                    baseline=baseline,
                    baseline_connections=baseline_connections,
                    pips=refined_pips,
                )
                total_sample_loss = _record_learning_observation(
                    counters=counters,
                    learner=learner,
                    sample_counts=sample_counts,
                    pips=refined_pips,
                    loss=refined_loss,
                    total_sample_loss=total_sample_loss,
                )
                previous_importance, last_change_iteration = _update_learning_log(
                    context=context,
                    counters=counters,
                    learner=learner,
                    previous_importance=previous_importance,
                    last_change_iteration=last_change_iteration,
                    scored_pips=len(all_pips),
                    window_sampler=window_sampler,
                )

    importance_by_pip = learner.scores()
    if counters.learning_iterations != last_change_iteration:
        counters.weight_change_rate = _weight_change_rate(
            previous=previous_importance,
            current=importance_by_pip,
        )
    _update_sample_coverage(counters, sample_counts, [])
    return learner, importance_by_pip


def _evaluate_ablation_loss(
    context: OptimizerContext,
    baseline: RoutingDemandEvaluatorResult,
    baseline_connections: Connections,
    pips: list[Pip],
) -> float:
    """Evaluate one temporary ablation and return its demand loss.

    Parameters
    ----------
    context : OptimizerContext
        Optimizer context.
    baseline : RoutingDemandEvaluatorResult
        Baseline result.
    baseline_connections : Connections
        Baseline matrix connections.
    pips : list[Pip]
        Temporarily removed PIPs.

    Returns
    -------
    float
        Regression loss.
    """
    candidate_connections = remove_pips(baseline_connections, pips)
    candidate_graph = build_graph(context.matrix, candidate_connections)
    candidate = context.evaluate(candidate_graph, [])
    return demand_loss(candidate, baseline)


def _record_learning_observation(
    counters: MonteCarloCounters,
    learner: ImportanceLearner,
    sample_counts: dict[Pip, int],
    pips: list[Pip],
    loss: float,
    total_sample_loss: float,
) -> float:
    """Record one learning observation in counters and learner state.

    Parameters
    ----------
    counters : MonteCarloCounters
        Mutable counters.
    learner : ImportanceLearner
        Importance learner.
    sample_counts : dict[Pip, int]
        Mutable per-PIP sample counts.
    pips : list[Pip]
        Observed PIPs.
    loss : float
        Observed loss.
    total_sample_loss : float
        Running total sample loss before this observation.

    Returns
    -------
    float
        Updated total sample loss.
    """
    learner.observe(pips, loss)
    total_sample_loss += loss
    counters.iterations += 1
    counters.learning_iterations += 1
    counters.sampled_batches += 1
    counters.importance_rounds += 1
    counters.average_sample_loss = total_sample_loss / counters.sampled_batches
    counters.max_sample_loss = max(counters.max_sample_loss, loss)
    _update_sample_coverage(counters, sample_counts, pips)
    return total_sample_loss


def _should_refine_high_loss_batch(
    batch: CandidateBatch,
    loss: float,
    counters: MonteCarloCounters,
    hyperparameters: MonteCarloHyperParameters,
) -> bool:
    """Return whether a high-loss batch should be split for attribution.

    Parameters
    ----------
    batch : CandidateBatch
        Learning batch.
    loss : float
        Observed loss.
    counters : MonteCarloCounters
        Current counters.
    hyperparameters : MonteCarloHyperParameters
        Internal Monte Carlo tuning constants.

    Returns
    -------
    bool
        Whether to run split attribution samples.
    """
    if len(batch.pips) <= 1:
        return False
    threshold = max(
        hyperparameters.high_loss_refinement_min_loss,
        counters.average_sample_loss * hyperparameters.high_loss_refinement_ratio,
    )
    return loss >= threshold


def _high_loss_refinement_batches(pips: list[Pip]) -> list[list[Pip]]:
    """Split a high-loss batch into smaller attribution batches.

    Parameters
    ----------
    pips : list[Pip]
        High-loss batch PIPs.

    Returns
    -------
    list[list[Pip]]
        Smaller batches.
    """
    midpoint = max(1, len(pips) // 2)
    return [pips[:midpoint], pips[midpoint:]]


def _update_learning_log(
    context: OptimizerContext,
    counters: MonteCarloCounters,
    learner: ImportanceLearner,
    previous_importance: ImportanceByPip,
    last_change_iteration: int,
    scored_pips: int,
    window_sampler: SlidingWindowSampler,
) -> tuple[ImportanceByPip, int]:
    """Update learning weight-change logs when a progress chunk is reached.

    Parameters
    ----------
    context : OptimizerContext
        Optimizer context.
    counters : MonteCarloCounters
        Current counters.
    learner : ImportanceLearner
        Importance learner.
    previous_importance : ImportanceByPip
        Previous logged importance values.
    last_change_iteration : int
        Last learning iteration where weight change was logged.
    scored_pips : int
        Number of scored PIPs.
    window_sampler : SlidingWindowSampler
        Learning sampler with epoch progress.

    Returns
    -------
    tuple[ImportanceByPip, int]
        Updated previous importance values and last log iteration.
    """
    if not _should_log_learning(context, counters):
        return previous_importance, last_change_iteration
    importance_by_pip = learner.scores()
    counters.weight_change_rate = _weight_change_rate(
        previous=previous_importance,
        current=importance_by_pip,
    )
    _log_learning_progress(
        context=context,
        counters=counters,
        scored_pips=scored_pips,
        window_sampler=window_sampler,
    )
    return dict(importance_by_pip), counters.learning_iterations


def _try_pruning_round(
    context: OptimizerContext,
    connections: Connections,
    current: RoutingDemandEvaluatorResult,
    limits: MonteCarloLimits,
    rejected: set[Pip],
    rng: Random,
    importance_by_pip: ImportanceByPip,
    learner: ImportanceLearner,
    counters: MonteCarloCounters,
    clean_mux: bool,
    hyperparameters: MonteCarloHyperParameters,
) -> PruningRoundResult:
    """Try one ranked Monte Carlo pruning candidate.

    Parameters
    ----------
    context : OptimizerContext
        Optimizer context.
    connections : Connections
        Current accepted connections.
    current : RoutingDemandEvaluatorResult
        Current accepted evaluation result.
    limits : MonteCarloLimits
        Allowed failure-rate limits.
    rejected : set[Pip]
        Rejected PIPs.
    rng : Random
        Random source.
    importance_by_pip : ImportanceByPip
        Current importance estimates.
    learner : ImportanceLearner
        Importance learner.
    counters : MonteCarloCounters
        Mutable counters.
    clean_mux : bool
        Whether mux-aware candidates are enabled.
    hyperparameters : MonteCarloHyperParameters
        Internal Monte Carlo tuning constants.

    Returns
    -------
    PruningRoundResult
        Candidate availability and optional accepted state.
    """
    if counters.pruning_iterations >= context.options.opt_max_iterations:
        return PruningRoundResult(accepted=None, had_candidates=False)
    batches = pruning_candidates(
        connections=connections,
        rng=rng,
        rejected=rejected,
        importance_by_pip=importance_by_pip,
        clean_mux=clean_mux,
        power_of_two_muxes=context.options.opt_power_of_two_muxes,
        hyperparameters=hyperparameters,
    )
    if not batches:
        return PruningRoundResult(accepted=None, had_candidates=False)

    batch = _best_batch_under_remaining_target(
        batches=batches,
        current_removed=counters.accepted_pips,
        target_remove=ceil(
            current.stats.original_routing_pips
            * context.options.opt_target_pip_reduction
        ),
        allow_overshoot=not context.options.opt_power_of_two_muxes,
    )
    if batch is None:
        return PruningRoundResult(
            accepted=None,
            had_candidates=False,
            blocked_by_target_budget=True,
        )
    batch = _cautious_batch_near_limits(
        batch=batch,
        current=current,
        limits=limits,
        power_of_two_muxes=context.options.opt_power_of_two_muxes,
        hyperparameters=hyperparameters,
    )
    accepted = _try_pruning_batch(
        context=context,
        connections=connections,
        current=current,
        limits=limits,
        rejected=rejected,
        importance_by_pip=importance_by_pip,
        learner=learner,
        counters=counters,
        batch=batch,
        allow_split=not context.options.opt_power_of_two_muxes,
    )
    return PruningRoundResult(accepted=accepted, had_candidates=True)


def _try_pruning_batch(
    context: OptimizerContext,
    connections: Connections,
    current: RoutingDemandEvaluatorResult,
    limits: MonteCarloLimits,
    rejected: set[Pip],
    importance_by_pip: ImportanceByPip,
    learner: ImportanceLearner,
    counters: MonteCarloCounters,
    batch: CandidateBatch,
    allow_split: bool,
) -> tuple[Connections, RoutingDemandEvaluatorResult] | None:
    """Try one pruning batch and split it when the oracle rejects it.

    Parameters
    ----------
    context : OptimizerContext
        Optimizer context.
    connections : Connections
        Current accepted connections.
    current : RoutingDemandEvaluatorResult
        Current accepted result.
    limits : MonteCarloLimits
        Allowed failure-rate limits.
    rejected : set[Pip]
        Rejected PIPs.
    importance_by_pip : ImportanceByPip
        Mutable importance values.
    learner : ImportanceLearner
        Importance learner.
    counters : MonteCarloCounters
        Mutable counters.
    batch : CandidateBatch
        Candidate batch to try.
    allow_split : bool
        Whether rejected batches can be split.

    Returns
    -------
    tuple[Connections, RoutingDemandEvaluatorResult] | None
        Accepted candidate, or ``None``.
    """
    if counters.pruning_iterations >= context.options.opt_max_iterations:
        return None
    if not batch.pips:
        return None
    candidate_connections = remove_pips(connections, batch.pips)
    candidate_graph = build_graph(context.matrix, candidate_connections)
    candidate = context.evaluate(candidate_graph, [])
    counters.iterations += 1
    counters.pruning_iterations += 1
    counters.attempted_batches += 1
    counters.attempted_pips += len(batch.pips)
    if _within_limits(candidate, limits):
        counters.accepted_batches += 1
        counters.accepted_pips += len(batch.pips)
        _log_pruning_progress(
            context,
            counters,
            current_pips=routing_pip_count(candidate_connections),
        )
        return candidate_connections, candidate

    counters.rejected_batches += 1
    counters.rejected_pips += len(batch.pips)
    _penalize_rejected_batch(
        learner=learner,
        importance_by_pip=importance_by_pip,
        batch=batch,
        loss=demand_loss(candidate, current),
    )
    if allow_split and len(batch.pips) > 1:
        accepted = _try_split_pruning_batch(
            context=context,
            connections=connections,
            current=current,
            limits=limits,
            rejected=rejected,
            importance_by_pip=importance_by_pip,
            learner=learner,
            counters=counters,
            batch=batch,
        )
        if accepted is not None:
            return accepted

    rejected.update(batch.pips)
    _log_pruning_progress(
        context,
        counters,
        current_pips=routing_pip_count(connections),
    )
    return None


def _try_split_pruning_batch(
    context: OptimizerContext,
    connections: Connections,
    current: RoutingDemandEvaluatorResult,
    limits: MonteCarloLimits,
    rejected: set[Pip],
    importance_by_pip: ImportanceByPip,
    learner: ImportanceLearner,
    counters: MonteCarloCounters,
    batch: CandidateBatch,
) -> tuple[Connections, RoutingDemandEvaluatorResult] | None:
    """Try smaller low-importance pieces of a rejected pruning batch.

    Parameters
    ----------
    context : OptimizerContext
        Optimizer context.
    connections : Connections
        Current accepted connections.
    current : RoutingDemandEvaluatorResult
        Current accepted result.
    limits : MonteCarloLimits
        Allowed failure-rate limits.
    rejected : set[Pip]
        Rejected PIPs.
    importance_by_pip : ImportanceByPip
        Mutable importance values.
    learner : ImportanceLearner
        Importance learner.
    counters : MonteCarloCounters
        Mutable counters.
    batch : CandidateBatch
        Rejected batch to split.

    Returns
    -------
    tuple[Connections, RoutingDemandEvaluatorResult] | None
        Accepted smaller batch, or ``None``.
    """
    ordered = sorted(
        batch.pips,
        key=lambda pip: (importance_by_pip.get(pip, 0.0), pip[1], pip[0]),
    )
    midpoint = max(1, len(ordered) // 2)
    split_batches = [
        CandidateBatch(pips=ordered[:midpoint]),
        CandidateBatch(pips=ordered[midpoint:]),
    ]
    for split_batch in split_batches:
        if not split_batch.pips:
            continue
        accepted = _try_pruning_batch(
            context=context,
            connections=connections,
            current=current,
            limits=limits,
            rejected=rejected,
            importance_by_pip=importance_by_pip,
            learner=learner,
            counters=counters,
            batch=split_batch,
            allow_split=len(split_batch.pips) > 1,
        )
        if accepted is not None:
            return accepted
    return None


def _best_batch_under_remaining_target(
    batches: list[CandidateBatch],
    current_removed: int,
    target_remove: int,
    allow_overshoot: bool,
) -> CandidateBatch | None:
    """Return a batch sized near the remaining target when possible.

    Parameters
    ----------
    batches : list[CandidateBatch]
        Ranked candidate batches.
    current_removed : int
        Already accepted removed PIPs.
    target_remove : int
        Target removals.
    allow_overshoot : bool
        Whether an oversized batch may be returned when every batch exceeds the
        remaining target budget.

    Returns
    -------
    CandidateBatch | None
        Selected candidate batch, or ``None`` if all batches exceed the
        remaining target and overshoot is not allowed.
    """
    remaining = max(target_remove - current_removed, 1)
    for batch in batches:
        if len(batch.pips) <= remaining:
            return batch
    return batches[0] if allow_overshoot else None


def _cautious_batch_near_limits(
    batch: CandidateBatch,
    current: RoutingDemandEvaluatorResult,
    limits: MonteCarloLimits,
    power_of_two_muxes: bool,
    hyperparameters: MonteCarloHyperParameters,
) -> CandidateBatch:
    """Shrink a batch when the current result is close to failure limits.

    Parameters
    ----------
    batch : CandidateBatch
        Candidate batch.
    current : RoutingDemandEvaluatorResult
        Current accepted result.
    limits : MonteCarloLimits
        Allowed failure-rate limits.
    power_of_two_muxes : bool
        Whether mux fanins must stay power-of-two sized.
    hyperparameters : MonteCarloHyperParameters
        Internal Monte Carlo tuning constants.

    Returns
    -------
    CandidateBatch
        Original or shrunk batch.
    """
    if power_of_two_muxes or len(batch.pips) <= 1:
        return batch
    pressure = _limit_pressure(current, limits)
    if pressure < hyperparameters.near_limit_pressure:
        return batch
    cap = (
        1
        if pressure >= hyperparameters.critical_limit_pressure
        else min(4, len(batch.pips))
    )
    return CandidateBatch(pips=batch.pips[:cap])


def _limit_pressure(
    result: RoutingDemandEvaluatorResult,
    limits: MonteCarloLimits,
) -> float:
    """Return how close a result is to the optimizer failure limits.

    Parameters
    ----------
    result : RoutingDemandEvaluatorResult
        Current accepted result.
    limits : MonteCarloLimits
        Allowed failure-rate limits.

    Returns
    -------
    float
        Maximum used fraction of hard/soft limits.
    """
    hard_pressure = (
        result.stats.hard_failure_rate / limits.hard
        if limits.hard > 0.0
        else (1.0 if result.stats.hard_failure_rate > 0.0 else 0.0)
    )
    soft_pressure = (
        result.stats.soft_failure_rate / limits.soft
        if limits.soft > 0.0
        else (1.0 if result.stats.soft_failure_rate > 0.0 else 0.0)
    )
    return max(hard_pressure, soft_pressure)


def _failure_limits(
    context: OptimizerContext,
    baseline: RoutingDemandEvaluatorResult,
) -> MonteCarloLimits:
    """Return optimizer failure-rate limits.

    Parameters
    ----------
    context : OptimizerContext
        Optimizer context.
    baseline : RoutingDemandEvaluatorResult
        Baseline evaluation result.

    Returns
    -------
    MonteCarloLimits
        Allowed failure-rate limits.
    """
    hard = context.options.opt_max_hard_failure_rate
    soft = context.options.opt_max_soft_failure_rate
    if context.options.opt_use_baseline_failure_rates:
        hard += baseline.stats.hard_failure_rate
        soft += baseline.stats.soft_failure_rate
    return MonteCarloLimits(hard=min(hard, 1.0), soft=min(soft, 1.0))


def _within_limits(
    result: RoutingDemandEvaluatorResult,
    limits: MonteCarloLimits,
) -> bool:
    """Return whether one result satisfies optimizer limits.

    Parameters
    ----------
    result : RoutingDemandEvaluatorResult
        Candidate result.
    limits : MonteCarloLimits
        Allowed failure-rate limits.

    Returns
    -------
    bool
        Whether the candidate is acceptable.
    """
    return (
        result.stats.hard_failure_rate <= limits.hard
        and result.stats.soft_failure_rate <= limits.soft
    )


def _with_optimizer_stats(
    result: RoutingDemandEvaluatorResult,
    baseline: RoutingDemandEvaluatorResult,
    final_connections: Connections,
    limits: MonteCarloLimits,
    counters: MonteCarloCounters,
    stop_reason: str,
    applied_to_tile_model: bool,
    importance_by_pip: ImportanceByPip,
    importance_file: Path | None,
) -> RoutingDemandEvaluatorResult:
    """Attach optimizer statistics and rerender the report.

    Parameters
    ----------
    result : RoutingDemandEvaluatorResult
        Final optimizer result.
    baseline : RoutingDemandEvaluatorResult
        Baseline result.
    final_connections : Connections
        Final accepted connections.
    limits : MonteCarloLimits
        Allowed failure-rate limits.
    counters : MonteCarloCounters
        Mutable counters.
    stop_reason : str
        Stop reason.
    applied_to_tile_model : bool
        Whether the accepted matrix was applied to the in-memory tile model.
    importance_by_pip : ImportanceByPip
        PIP importance values.
    importance_file : Path | None
        Written importance file.

    Returns
    -------
    RoutingDemandEvaluatorResult
        Result with optimizer statistics and rendered report.
    """
    baseline_pips = baseline.stats.original_routing_pips
    final_pips = routing_pip_count(final_connections)
    removed_pips = max(baseline_pips - final_pips, 0)
    final_matrix_bits = estimate_config_bits(final_connections)
    baseline_non_matrix_bits = (
        baseline.stats.total_config_bits - baseline.stats.matrix_config_bits
    )
    mux_cleanup = mux_cleanup_stats(
        baseline_connections=baseline.matrix.connections,
        final_connections=final_connections,
        baseline_config_bits=baseline.stats.matrix_config_bits,
        final_config_bits=final_matrix_bits,
    )
    stats = OptimizerStats(
        enabled=True,
        optimizer=str(result.options.optimizer),
        applied_to_tile_model=applied_to_tile_model,
        baseline_pips=baseline_pips,
        final_pips=final_pips,
        removed_pips=removed_pips,
        baseline_matrix_config_bits=baseline.stats.matrix_config_bits,
        final_matrix_config_bits_estimate=final_matrix_bits,
        baseline_total_config_bits=baseline.stats.total_config_bits,
        final_total_config_bits_estimate=baseline_non_matrix_bits + final_matrix_bits,
        pip_reduction=(removed_pips / baseline_pips if baseline_pips else 0.0),
        target_pip_reduction=result.options.opt_target_pip_reduction,
        baseline_hard_failure_rate=baseline.stats.hard_failure_rate,
        baseline_soft_failure_rate=baseline.stats.soft_failure_rate,
        allowed_hard_failure_rate=limits.hard,
        allowed_soft_failure_rate=limits.soft,
        final_hard_failure_rate=result.stats.hard_failure_rate,
        final_soft_failure_rate=result.stats.soft_failure_rate,
        attempted_iterations=counters.iterations,
        attempted_batches=counters.attempted_batches,
        accepted_batches=counters.accepted_batches,
        rejected_batches=counters.rejected_batches,
        attempted_pips=counters.attempted_pips,
        accepted_pips=counters.accepted_pips,
        rejected_pips=counters.rejected_pips,
        stop_reason=stop_reason,
        mux_cleanup=mux_cleanup,
        sampled_batches=counters.sampled_batches,
        importance_rounds=counters.importance_rounds,
        learning_iterations=counters.learning_iterations,
        pruning_iterations=counters.pruning_iterations,
        average_sample_loss=counters.average_sample_loss,
        max_sample_loss=counters.max_sample_loss,
        weight_change_rate=counters.weight_change_rate,
        sampled_pips=counters.sampled_pips,
        unsampled_pips=counters.unsampled_pips,
        sampled_pip_rate=counters.sampled_pip_rate,
        min_samples_per_pip=counters.min_samples_per_pip,
        average_samples_per_pip=counters.average_samples_per_pip,
        max_samples_per_pip=counters.max_samples_per_pip,
        best_iteration=counters.best_iteration,
        pip_importance_matrix=build_importance_matrix(
            baseline.matrix.connections,
            importance_by_pip,
        ),
        pip_importance_file=importance_file,
    )
    updated = result.model_copy(update={"optimizer_stats": stats})
    return updated.model_copy(
        update={"report_summary": render_routing_demand_report(updated)}
    )


def _all_pips(connections: Connections) -> list[Pip]:
    """Return all routing PIPs from matrix connections.

    Parameters
    ----------
    connections : Connections
        Matrix connections.

    Returns
    -------
    list[Pip]
        PIPs.
    """
    return [(source, row) for row, sources in connections.items() for source in sources]


def _update_sample_coverage(
    counters: MonteCarloCounters,
    sample_counts: dict[Pip, int],
    pips: list[Pip],
) -> None:
    """Update learning coverage counters.

    Parameters
    ----------
    counters : MonteCarloCounters
        Mutable counters.
    sample_counts : dict[Pip, int]
        Mutable per-PIP sample counts.
    pips : list[Pip]
        PIPs seen in the latest sample.
    """
    for pip in pips:
        if pip in sample_counts:
            sample_counts[pip] += 1
    if not sample_counts:
        counters.sampled_pips = 0
        counters.unsampled_pips = 0
        counters.sampled_pip_rate = 0.0
        counters.min_samples_per_pip = 0
        counters.average_samples_per_pip = 0.0
        counters.max_samples_per_pip = 0
        return
    counts = list(sample_counts.values())
    counters.sampled_pips = sum(1 for count in counts if count > 0)
    counters.unsampled_pips = len(counts) - counters.sampled_pips
    counters.sampled_pip_rate = counters.sampled_pips / len(counts)
    counters.min_samples_per_pip = min(counts)
    counters.average_samples_per_pip = sum(counts) / len(counts)
    counters.max_samples_per_pip = max(counts)


def _penalize_rejected_batch(
    learner: ImportanceLearner,
    importance_by_pip: ImportanceByPip,
    batch: CandidateBatch,
    loss: float,
) -> None:
    """Increase importance for PIPs from a rejected pruning batch.

    Parameters
    ----------
    learner : ImportanceLearner
        Importance learner.
    importance_by_pip : ImportanceByPip
        Mutable importance values.
    batch : CandidateBatch
        Rejected pruning batch.
    loss : float
        Observed loss for the rejected batch.
    """
    learner.penalize(batch.pips, loss)
    importance_by_pip.clear()
    importance_by_pip.update(learner.scores())


def _weight_change_rate(
    previous: ImportanceByPip,
    current: ImportanceByPip,
) -> float:
    """Return relative average absolute importance-weight change.

    Parameters
    ----------
    previous : ImportanceByPip
        Previous importance values.
    current : ImportanceByPip
        Current importance values.

    Returns
    -------
    float
        Relative change rate.
    """
    if not current:
        return 0.0
    keys = set(previous) | set(current)
    absolute_change = sum(
        abs(current.get(pip, 0.0) - previous.get(pip, 0.0)) for pip in keys
    ) / len(keys)
    average_weight = sum(abs(current.get(pip, 0.0)) for pip in keys) / len(keys)
    return absolute_change / (1.0e-12 + average_weight)


def _should_log_learning(
    context: OptimizerContext,
    counters: MonteCarloCounters,
) -> bool:
    """Return whether the current learning iteration should be logged.

    Parameters
    ----------
    context : OptimizerContext
        Optimizer context.
    counters : MonteCarloCounters
        Mutable counters.

    Returns
    -------
    bool
        Whether to recompute and log current weight change.
    """
    iteration = counters.learning_iterations
    return (
        iteration % context.options.progress_chunk_size == 0
        or iteration == context.options.opt_max_iterations
    )


def _log_learning_progress(
    context: OptimizerContext,
    counters: MonteCarloCounters,
    scored_pips: int,
    window_sampler: SlidingWindowSampler,
) -> None:
    """Log Monte Carlo learning progress.

    Parameters
    ----------
    context : OptimizerContext
        Optimizer context.
    counters : MonteCarloCounters
        Current counters.
    scored_pips : int
        Number of scored PIPs.
    window_sampler : SlidingWindowSampler
        Learning sampler with epoch progress.
    """
    context.tracker.monte_carlo_learning_iteration(
        iteration=counters.learning_iterations,
        max_iterations=context.options.opt_max_iterations,
        average_loss=counters.average_sample_loss,
        max_loss=counters.max_sample_loss,
        weight_change_rate=counters.weight_change_rate,
        scored_pips=scored_pips,
        sampled_pips=counters.sampled_pips,
        unsampled_pips=counters.unsampled_pips,
        epoch=window_sampler.epoch,
        epoch_progress=window_sampler.epoch_progress,
        epoch_size=window_sampler.epoch_size,
    )


def _log_pruning_progress(
    context: OptimizerContext,
    counters: MonteCarloCounters,
    current_pips: int,
) -> None:
    """Log Monte Carlo pruning progress.

    Parameters
    ----------
    context : OptimizerContext
        Optimizer context.
    counters : MonteCarloCounters
        Current counters.
    current_pips : int
        Current accepted routing PIP count.
    """
    context.tracker.monte_carlo_pruning_iteration(
        iteration=counters.pruning_iterations,
        max_iterations=context.options.opt_max_iterations,
        current_pips=current_pips,
        accepted_pips=counters.accepted_pips,
        accepted_batches=counters.accepted_batches,
        rejected_batches=counters.rejected_batches,
    )

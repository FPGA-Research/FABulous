"""Candidate sampling for the Monte Carlo optimizer."""

from __future__ import annotations

from typing import TYPE_CHECKING

from fabulous.fabric_cad.fabxplore.modules.routing_demand_evaluator.optimizers.monte_carlo.functions import (  # noqa: E501
    batch_value,
)
from fabulous.fabric_cad.fabxplore.modules.routing_demand_evaluator.optimizers.monte_carlo.matrix import (  # noqa: E501
    CandidateBatch,
    Connections,
    ImportanceByPip,
    MonteCarloHyperParameters,
    Pip,
    is_allowed_mux_fanin,
    mux_config_bits,
    mux_cost,
    remove_emptying_pips,
    target_mux_fanin,
)

if TYPE_CHECKING:
    from random import Random


class SlidingWindowSampler:
    """Shuffled sliding-window sampler for learning coverage.

    Parameters
    ----------
    pips : list[Pip]
        Removable PIPs to sample.
    rng : Random
        Random source.
    batch_size : int
        Number of PIPs per batch.
    """

    def __init__(
        self,
        pips: list[Pip],
        rng: Random,
        batch_size: int,
    ) -> None:
        self._pips = list(pips)
        self._rng = rng
        self._batch_size = max(1, batch_size)
        self._index = 0
        self._epoch = 0
        self._reshuffle()

    @property
    def epoch(self) -> int:
        """Return the current 1-based shuffled pass number."""
        return self._epoch

    @property
    def epoch_progress(self) -> int:
        """Return how many PIPs have been consumed in this epoch."""
        return min(self._index, len(self._pips))

    @property
    def epoch_size(self) -> int:
        """Return the number of PIPs in one epoch."""
        return len(self._pips)

    def next_batch(self) -> CandidateBatch | None:
        """Return the next shuffled sliding-window batch.

        Returns
        -------
        CandidateBatch | None
            Candidate batch, or ``None`` if there are no PIPs.
        """
        if not self._pips:
            return None
        if self._index >= len(self._pips):
            self._reshuffle()
        batch = self._pips[self._index : self._index + self._batch_size]
        self._index += self._batch_size
        return CandidateBatch(pips=batch)

    def _reshuffle(self) -> None:
        """Shuffle the PIP order and start a new epoch."""
        self._rng.shuffle(self._pips)
        self._index = 0
        self._epoch += 1


def removable_pips(
    connections: Connections,
    rejected: set[Pip] | None = None,
) -> list[Pip]:
    """Return switch-matrix PIPs that can be removed without emptying a row.

    Parameters
    ----------
    connections : Connections
        Current matrix connections.
    rejected : set[Pip] | None
        PIPs that should not be retried.

    Returns
    -------
    list[Pip]
        Removable PIPs.
    """
    rejected = rejected or set()
    return [
        (source, row)
        for row, sources in connections.items()
        if len(sources) > 1
        for source in sources
        if (source, row) not in rejected
    ]


def sample_ablation_batch(
    connections: Connections,
    rng: Random,
    rejected: set[Pip],
    clean_mux: bool,
    power_of_two_muxes: bool,
    window_sampler: SlidingWindowSampler | None = None,
    force_window: bool = False,
) -> CandidateBatch | None:
    """Sample a temporary Monte Carlo ablation batch.

    Parameters
    ----------
    connections : Connections
        Current matrix connections.
    rng : Random
        Random source.
    rejected : set[Pip]
        Rejected PIPs to avoid.
    clean_mux : bool
        Whether mux-aware batches are preferred.
    power_of_two_muxes : bool
        Whether batches should preserve power-of-two mux sizes.
    window_sampler : SlidingWindowSampler | None
        Shuffled sliding-window sampler used for broad learning coverage.
    force_window : bool
        Whether the sliding-window sampler must be used when available.

    Returns
    -------
    CandidateBatch | None
        Sampled batch, or ``None`` if no candidate exists.
    """
    use_window = window_sampler is not None and (
        force_window or not clean_mux or rng.random() < 0.75
    )
    if use_window and window_sampler is not None:
        window_batch = window_sampler.next_batch()
        if window_batch is not None:
            return window_batch

    if clean_mux or power_of_two_muxes:
        mux_batches = mux_candidate_batches(
            connections=connections,
            rejected=rejected,
            power_of_two_muxes=power_of_two_muxes,
            importance_by_pip=None,
            rng=rng,
        )
        if mux_batches:
            return rng.choice(mux_batches)

    candidates = removable_pips(connections, rejected)
    if not candidates:
        return None
    rng.shuffle(candidates)
    batch_size = max(1, min(12, len(candidates) // 20 or 1))
    pips = remove_emptying_pips(connections, candidates[:batch_size])
    if not pips:
        return None
    return CandidateBatch(pips=pips)


def pruning_candidates(
    connections: Connections,
    rng: Random,
    rejected: set[Pip],
    importance_by_pip: ImportanceByPip,
    clean_mux: bool,
    power_of_two_muxes: bool,
    hyperparameters: MonteCarloHyperParameters,
    pool_size: int = 32,
) -> list[CandidateBatch]:
    """Return ranked pruning candidates for one Monte Carlo round.

    Parameters
    ----------
    connections : Connections
        Current matrix connections.
    rng : Random
        Random source.
    rejected : set[Pip]
        Rejected PIPs to avoid.
    importance_by_pip : ImportanceByPip
        Importance values keyed by PIP.
    clean_mux : bool
        Whether mux-aware candidates are preferred.
    power_of_two_muxes : bool
        Whether mux rows must remain power-of-two sized.
    hyperparameters : MonteCarloHyperParameters
        Internal Monte Carlo tuning constants.
    pool_size : int
        Number of sampled non-mux candidates to consider.

    Returns
    -------
    list[CandidateBatch]
        Candidate batches, highest priority first.
    """
    batches: list[CandidateBatch] = []
    if clean_mux or power_of_two_muxes:
        batches.extend(
            mux_candidate_batches(
                connections=connections,
                rejected=rejected,
                power_of_two_muxes=power_of_two_muxes,
                importance_by_pip=importance_by_pip,
                rng=rng,
            )
        )
    candidates = removable_pips(connections, rejected)
    if candidates and not power_of_two_muxes:
        pool_size = min(pool_size, hyperparameters.pruning_candidate_pool_size)
        for _ in range(min(pool_size, max(1, len(candidates)))):
            rng.shuffle(candidates)
            batch_size = min(hyperparameters.pruning_batch_size, len(candidates))
            pips = remove_emptying_pips(connections, candidates[:batch_size])
            if pips:
                batches.append(CandidateBatch(pips=pips))

    unique: dict[tuple[Pip, ...], CandidateBatch] = {}
    for batch in batches:
        key = tuple(sorted(batch.pips))
        unique.setdefault(key, batch)
    return sorted(
        unique.values(),
        key=lambda batch: _candidate_sort_key(batch, importance_by_pip),
    )


def mux_candidate_batches(
    connections: Connections,
    rejected: set[Pip],
    power_of_two_muxes: bool,
    importance_by_pip: ImportanceByPip | None,
    rng: Random,
) -> list[CandidateBatch]:
    """Return row-local mux cleanup batches.

    Parameters
    ----------
    connections : Connections
        Current matrix connections.
    rejected : set[Pip]
        Rejected PIPs to avoid.
    power_of_two_muxes : bool
        Whether non-power-of-two rows are mandatory cleanup candidates.
    importance_by_pip : ImportanceByPip | None
        Optional importance values used to choose removable row sources.
    rng : Random
        Random source used for unbiased ablation sampling.

    Returns
    -------
    list[CandidateBatch]
        Mux cleanup candidate batches.
    """
    batches: list[CandidateBatch] = []
    for row, sources in connections.items():
        fanin = len(sources)
        if fanin <= 1:
            continue
        target = target_mux_fanin(fanin)
        if power_of_two_muxes and not is_allowed_mux_fanin(fanin):
            target = target_mux_fanin(fanin)
        removable_count = fanin - target
        if removable_count <= 0:
            continue
        candidate_pips = [
            (source, row) for source in sources if (source, row) not in rejected
        ]
        candidate_pips = _select_row_pips(
            pips=candidate_pips,
            count=removable_count,
            importance_by_pip=importance_by_pip,
            rng=rng,
        )
        if len(candidate_pips) != removable_count:
            continue
        batches.append(
            CandidateBatch(
                pips=candidate_pips,
                mux_cost_saved=max(mux_cost(fanin) - mux_cost(target), 0),
                config_bits_saved=max(
                    mux_config_bits(fanin) - mux_config_bits(target),
                    0,
                ),
                normalizes_power_of_two=not is_allowed_mux_fanin(fanin),
            )
        )
    return batches


def _select_row_pips(
    pips: list[Pip],
    count: int,
    importance_by_pip: ImportanceByPip | None,
    rng: Random,
) -> list[Pip]:
    """Select row-local PIPs for a mux cleanup batch.

    Parameters
    ----------
    pips : list[Pip]
        Candidate row PIPs.
    count : int
        Number of PIPs to choose.
    importance_by_pip : ImportanceByPip | None
        Optional PIP importance values.
    rng : Random
        Random source.

    Returns
    -------
    list[Pip]
        Selected PIPs.
    """
    if importance_by_pip is None:
        shuffled = list(pips)
        rng.shuffle(shuffled)
        return shuffled[:count]
    return sorted(
        pips,
        key=lambda pip: (importance_by_pip.get(pip, 0.0), pip[0], pip[1]),
    )[:count]


def _candidate_sort_key(
    batch: CandidateBatch,
    importance_by_pip: ImportanceByPip,
) -> tuple[float, int, int, int]:
    """Return stable ranking key for a candidate batch.

    Parameters
    ----------
    batch : CandidateBatch
        Candidate batch.
    importance_by_pip : ImportanceByPip
        Importance values keyed by PIP.

    Returns
    -------
    tuple[float, int, int, int]
        Sort key.
    """
    value = batch_value(batch, importance_by_pip)
    saved = len(batch.pips) + batch.config_bits_saved + batch.mux_cost_saved
    return (-value, -batch.config_bits_saved, -saved, len(batch.pips))

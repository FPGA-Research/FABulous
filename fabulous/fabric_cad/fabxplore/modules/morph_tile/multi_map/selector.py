"""Select non-overlapping multi-map replacement groups.

The multi-map SAT stage can produce many legal replacement candidates, but two
selected candidates must never consume the same source LUT. This module solves
that final set-packing problem with three internal strategies:

* ``GreedyDisjointSelector`` is deterministic and very fast.
* ``LocalImprovementDisjointSelector`` starts from greedy and accepts local
  one-removal improvements.
* ``CpSatSetPackingSelector`` encodes the selection as an OR-Tools CP-SAT
  optimization problem.

All selectors use the same objective order: maximize replaced LUT count,
minimize replacement-instance count on ties, then prefer higher match scores.
"""

from __future__ import annotations

from time import monotonic
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Callable

    from fabulous.fabric_cad.fabxplore.modules.morph_tile.multi_map.models import (
        MultiMapMatch,
    )
    from fabulous.fabric_cad.fabxplore.modules.morph_tile.multi_map.options import (
        MultiMapOptions,
    )


class GreedyDisjointSelector:
    """Select disjoint matches with a greedy deterministic policy.

    The selector sorts SAT-positive matches by score and then keeps the first
    match that does not overlap any already-selected LUTs.

    Examples
    --------
    If ``A`` covers ``{lut0, lut1}`` and ``B`` covers ``{lut1, lut2}``, then the
    higher-ranked one wins and the other is skipped because both consume
    ``lut1``.
    """

    def select(
        self,
        matches: list[MultiMapMatch],
        options: MultiMapOptions,
    ) -> list[MultiMapMatch]:
        """Select a largest-looking disjoint match set.

        Parameters
        ----------
        matches : list[MultiMapMatch]
            Successful SAT matches.
        options : MultiMapOptions
            Selection options.

        Returns
        -------
        list[MultiMapMatch]
            Greedy disjoint match set.

        Examples
        --------
        A high-scoring early match can block several later matches. This is
        fast and deterministic, but not globally optimal.
        """
        selected: list[MultiMapMatch] = []
        used_luts: set[str] = set()
        ordered = sorted(
            matches,
            key=lambda match: (match.score, tuple(sorted(match.candidate.lut_ids))),
            reverse=True,
        )
        for match in ordered:
            if (
                options.max_selected_groups is not None
                and len(selected) >= options.max_selected_groups
            ):
                break
            lut_ids = set(match.candidate.lut_ids)
            if used_luts.isdisjoint(lut_ids):
                selected.append(match)
                used_luts.update(lut_ids)
        return selected


class LocalImprovementDisjointSelector:
    """Improve greedy disjoint selection with deterministic local swaps.

    Parameters
    ----------
    base_selector : GreedyDisjointSelector | None
        Initial selector used before local swaps are attempted.

    Examples
    --------
    If greedy selected ``A`` but removing ``A`` lets the selector pack ``B`` and
    ``C`` without overlap, the local-improvement pass can replace ``A`` with the
    better pair.
    """

    def __init__(self, base_selector: GreedyDisjointSelector | None = None) -> None:
        self.base_selector = base_selector or GreedyDisjointSelector()

    def select(
        self,
        matches: list[MultiMapMatch],
        options: MultiMapOptions,
        progress: Callable[[dict[str, object]], None] | None = None,
    ) -> list[MultiMapMatch]:
        """Select disjoint matches and improve the greedy result locally.

        Parameters
        ----------
        matches : list[MultiMapMatch]
            Successful SAT matches.
        options : MultiMapOptions
            Selection options.
        progress : Callable[[dict[str, object]], None] | None
            Optional callback receiving selector progress events.

        Returns
        -------
        list[MultiMapMatch]
            Locally improved disjoint match set.

        Examples
        --------
        This keeps the greedy result when no one-removal replacement improves
        coverage or score.
        """
        start_time = monotonic()
        selected = self.base_selector.select(matches, options)
        ordered = _ordered_matches(matches)
        _emit_selector_event(
            progress,
            "start",
            {
                "selector": "local_improvement",
                "input_matches": len(matches),
                "selected_groups": len(selected),
                "replaced_luts": _replaced_lut_count(selected),
            },
        )

        iterations = 0
        for iteration in range(1, len(matches) + 1):
            replacement = self._best_single_removal_swap(
                selected,
                ordered,
                options,
                iteration=iteration,
                progress=progress,
                start_time=start_time,
            )
            if replacement is None:
                break
            selected = replacement
            iterations = iteration
            _emit_selector_event(
                progress,
                "progress",
                {
                    "selector": "local_improvement",
                    "phase": "iteration",
                    "scan": iteration,
                    "accepted_improvements": iterations,
                    "selected_groups": len(selected),
                    "replaced_luts": _replaced_lut_count(selected),
                    "score": _selection_score(selected),
                    "wall_time_s": monotonic() - start_time,
                },
            )
        selected = _ordered_matches(selected)
        _emit_selector_event(
            progress,
            "finish",
            {
                "selector": "local_improvement",
                "status": "DONE",
                "input_matches": len(matches),
                "accepted_improvements": iterations,
                "selected_groups": len(selected),
                "replaced_luts": _replaced_lut_count(selected),
                "score": _selection_score(selected),
                "wall_time_s": monotonic() - start_time,
            },
        )
        return selected

    def _best_single_removal_swap(
        self,
        selected: list[MultiMapMatch],
        ordered: list[MultiMapMatch],
        options: MultiMapOptions,
        *,
        iteration: int,
        progress: Callable[[dict[str, object]], None] | None,
        start_time: float,
    ) -> list[MultiMapMatch] | None:
        """Return the best improving one-removal local swap if one exists.

        Parameters
        ----------
        selected : list[MultiMapMatch]
            Current disjoint selection.
        ordered : list[MultiMapMatch]
            All matches in deterministic greedy order.
        options : MultiMapOptions
            Selection options.
        iteration : int
            Current local-improvement iteration.
        progress : Callable[[dict[str, object]], None] | None
            Optional callback receiving selector progress events.
        start_time : float
            Monotonic start time for elapsed progress.

        Returns
        -------
        list[MultiMapMatch] | None
            Improved selection, or ``None`` if no single-removal swap helps.
        """
        best = selected
        selected_ids = {id(match) for match in selected}
        removals = _ordered_matches(selected)
        for remove_index, removed in enumerate(removals, start=1):
            selected_without = [match for match in selected if match is not removed]
            candidate = _pack_local_replacements(
                selected_without,
                ordered,
                selected_ids,
                removed,
                options,
            )
            if _selection_cmp(candidate, best) > 0:
                best = candidate
            _emit_selector_event(
                progress,
                "progress",
                {
                    "selector": "local_improvement",
                    "phase": "removal_scan",
                    "scan": iteration,
                    "current": remove_index,
                    "total": len(removals),
                    "scan_best_groups": len(best),
                    "scan_best_replaced_luts": _replaced_lut_count(best),
                    "wall_time_s": monotonic() - start_time,
                },
            )
        if best is selected:
            return None
        return _ordered_matches(best)


class CpSatSetPackingSelector:
    """Select disjoint matches with an OR-Tools CP-SAT set-packing model.

    Parameters
    ----------
    max_time_seconds : float
        Solver time limit in seconds.
    num_search_workers : int
        Number of CP-SAT search workers.
    fallback_selector : LocalImprovementDisjointSelector | None
        Selector used when OR-Tools is unavailable or no feasible CP-SAT
        solution is returned.

    Raises
    ------
    ValueError
        If max_time_seconds or num_search_workers is smaller than one.

    Examples
    --------
    For matches ``A={lut0,lut1}``, ``B={lut1,lut2}``, and ``C={lut3,lut4}``,
    the CP-SAT model creates Boolean variables ``x_A``, ``x_B``, and ``x_C``.
    Since ``A`` and ``B`` overlap on ``lut1``, it adds ``x_A + x_B <= 1`` and
    then maximizes replaced LUTs, minimizes replacement count on ties, and
    finally prefers higher-scoring matches.
    """

    def __init__(
        self,
        max_time_seconds: float = 300.0,
        num_search_workers: int = 8,
        fallback_selector: LocalImprovementDisjointSelector | None = None,
    ) -> None:
        if max_time_seconds <= 0:
            raise ValueError("max_time_seconds must be > 0")
        if num_search_workers < 1:
            raise ValueError("num_search_workers must be >= 1")
        self.max_time_seconds = max_time_seconds
        self.num_search_workers = num_search_workers
        self.fallback_selector = fallback_selector or LocalImprovementDisjointSelector()

    def select(
        self,
        matches: list[MultiMapMatch],
        options: MultiMapOptions,
    ) -> list[MultiMapMatch]:
        """Select a globally optimized disjoint match set with CP-SAT.

        Parameters
        ----------
        matches : list[MultiMapMatch]
            Successful SAT matches.
        options : MultiMapOptions
            Selection options.

        Returns
        -------
        list[MultiMapMatch]
            Best CP-SAT solution, or the fallback selection if CP-SAT does not
            return a better feasible result.

        Examples
        --------
        The returned selection is always disjoint. If CP-SAT proves optimality
        within the time limit, it is globally best for the provided matches.
        """
        selected, _metadata = self.select_with_metadata(matches, options)
        return selected

    def select_with_metadata(
        self,
        matches: list[MultiMapMatch],
        options: MultiMapOptions,
        progress: Callable[[dict[str, object]], None] | None = None,
    ) -> tuple[list[MultiMapMatch], dict[str, object]]:
        """Select disjoint matches and return CP-SAT execution metadata.

        Parameters
        ----------
        matches : list[MultiMapMatch]
            Successful SAT matches.
        options : MultiMapOptions
            Selection options.
        progress : Callable[[dict[str, object]], None] | None
            Optional callback receiving CP-SAT progress events.

        Returns
        -------
        tuple[list[MultiMapMatch], dict[str, object]]
            Selected matches plus selector metadata for reports.
        """
        if not matches:
            metadata = _selector_metadata(
                selector="cp_sat_set_packing",
                status="EMPTY",
                input_matches=0,
                selected=[],
                fallback_used=False,
                fallback_selector="local_improvement",
                max_time_seconds=self.max_time_seconds,
                num_search_workers=self.num_search_workers,
            )
            return [], metadata

        fallback = self.fallback_selector.select(matches, options, progress=progress)
        try:
            return self._select_with_cp_sat(
                matches,
                options,
                fallback,
                progress,
            )
        except ImportError:
            metadata = _selector_metadata(
                selector="cp_sat_set_packing",
                status="ORTOOLS_UNAVAILABLE",
                input_matches=len(matches),
                selected=fallback,
                fallback_used=True,
                fallback_selector="local_improvement",
                max_time_seconds=self.max_time_seconds,
                num_search_workers=self.num_search_workers,
            )
            _emit_selector_event(progress, "finish", metadata)
            return fallback, metadata

    def _select_with_cp_sat(
        self,
        matches: list[MultiMapMatch],
        options: MultiMapOptions,
        fallback: list[MultiMapMatch],
        progress: Callable[[dict[str, object]], None] | None,
    ) -> tuple[list[MultiMapMatch], dict[str, object]]:
        """Solve the set-packing model with OR-Tools CP-SAT.

        Parameters
        ----------
        matches : list[MultiMapMatch]
            Successful SAT matches.
        options : MultiMapOptions
            Selection options.
        fallback : list[MultiMapMatch]
            Already-computed fallback selection.
        progress : Callable[[dict[str, object]], None] | None
            Optional callback receiving CP-SAT progress events.

        Returns
        -------
        tuple[list[MultiMapMatch], dict[str, object]]
            Selected matches plus selector metadata.
        """
        from ortools.sat.python import cp_model

        ordered = self._ordered_matches(matches)
        model = cp_model.CpModel()
        variables = [
            model.NewBoolVar(f"match_{index}") for index, _match in enumerate(ordered)
        ]

        lut_to_variables: dict[str, list] = {}
        for variable, match in zip(variables, ordered, strict=True):
            for lut_id in match.candidate.lut_ids:
                lut_to_variables.setdefault(lut_id, []).append(variable)
        for lut_variables in lut_to_variables.values():
            if len(lut_variables) > 1:
                model.AddAtMostOne(lut_variables)

        if options.max_selected_groups is not None:
            model.Add(sum(variables) <= options.max_selected_groups)

        objective_weights = self._objective_weights(ordered)
        model.Maximize(
            sum(
                weight * variable
                for weight, variable in zip(objective_weights, variables, strict=True)
            )
        )

        fallback_ids = {id(match) for match in fallback}
        for variable, match in zip(variables, ordered, strict=True):
            model.AddHint(variable, int(id(match) in fallback_ids))

        solver = cp_model.CpSolver()
        solver.parameters.max_time_in_seconds = self.max_time_seconds
        solver.parameters.num_search_workers = self.num_search_workers
        _emit_selector_event(
            progress,
            "start",
            {
                "selector": "cp_sat_set_packing",
                "fallback_selector": "local_improvement",
                "input_matches": len(matches),
                "lut_constraints": len(lut_to_variables),
                "fallback_selected_groups": len(fallback),
                "fallback_replaced_luts": _replaced_lut_count(fallback),
                "max_time_seconds": self.max_time_seconds,
                "num_search_workers": self.num_search_workers,
            },
        )

        solve_start = monotonic()

        class _ProgressCallback(cp_model.CpSolverSolutionCallback):
            """Emit throttled CP-SAT feasible-solution updates.

            The callback is called by OR-Tools whenever the solver finds a new feasible
            incumbent. It reads the current Boolean variable values and forwards a
            compact progress event to the mapper process tracker.
            """

            def __init__(self) -> None:
                super().__init__()
                self._last_emit = -1.0

            def on_solution_callback(self) -> None:
                """Emit a progress event for the current feasible solution."""
                wall_time = self.WallTime()
                if self._last_emit >= 0.0 and wall_time - self._last_emit < 1.0:
                    return
                self._last_emit = wall_time
                selected_now = [
                    match
                    for variable, match in zip(variables, ordered, strict=True)
                    if self.BooleanValue(variable)
                ]
                _emit_selector_event(
                    progress,
                    "progress",
                    {
                        "selector": "cp_sat_set_packing",
                        "selected_groups": len(selected_now),
                        "replaced_luts": _replaced_lut_count(selected_now),
                        "score": _selection_score(selected_now),
                        "objective": self.ObjectiveValue(),
                        "best_bound": self.BestObjectiveBound(),
                        "wall_time_s": wall_time,
                    },
                )

        last_bound_emit = [-1.0]

        def _bound_callback(bound: float) -> None:
            """Emit a throttled CP-SAT objective-bound update.

            Parameters
            ----------
            bound : float
                Current solver objective bound.
            """
            elapsed = monotonic() - solve_start
            last_emit = last_bound_emit[0]
            if last_emit >= 0.0 and elapsed - last_emit < 2.0:
                return
            last_bound_emit[0] = elapsed
            _emit_selector_event(
                progress,
                "bound",
                {
                    "selector": "cp_sat_set_packing",
                    "best_bound": bound,
                    "wall_time_s": elapsed,
                },
            )

        if progress is not None:
            solver.best_bound_callback = _bound_callback

        status = solver.solve(
            model,
            solution_callback=_ProgressCallback() if progress is not None else None,
        )
        status_name = solver.StatusName(status)
        if status not in {cp_model.OPTIMAL, cp_model.FEASIBLE}:
            metadata = _selector_metadata(
                selector="cp_sat_set_packing",
                status=status_name,
                input_matches=len(matches),
                selected=fallback,
                fallback_used=True,
                fallback_selector="local_improvement",
                max_time_seconds=self.max_time_seconds,
                num_search_workers=self.num_search_workers,
                wall_time_s=solver.WallTime(),
                objective=None,
                best_bound=solver.BestObjectiveBound(),
                lut_constraints=len(lut_to_variables),
            )
            _emit_selector_event(progress, "finish", metadata)
            return fallback, metadata

        selected = [
            match
            for variable, match in zip(variables, ordered, strict=True)
            if solver.BooleanValue(variable)
        ]
        selected = self._ordered_matches(selected)
        fallback_used = self._selection_cmp(selected, fallback) < 0
        final_selection = fallback if fallback_used else selected
        metadata = _selector_metadata(
            selector="cp_sat_set_packing",
            status=status_name,
            input_matches=len(matches),
            selected=final_selection,
            fallback_used=fallback_used,
            fallback_selector="local_improvement",
            max_time_seconds=self.max_time_seconds,
            num_search_workers=self.num_search_workers,
            wall_time_s=solver.WallTime(),
            objective=solver.ObjectiveValue(),
            best_bound=solver.BestObjectiveBound(),
            lut_constraints=len(lut_to_variables),
            cp_sat_selected_groups=len(selected),
            cp_sat_replaced_luts=_replaced_lut_count(selected),
            fallback_selected_groups=len(fallback),
            fallback_replaced_luts=_replaced_lut_count(fallback),
        )
        _emit_selector_event(progress, "finish", metadata)
        return final_selection, metadata

    def _objective_weights(self, matches: list[MultiMapMatch]) -> list[int]:
        """Return lexicographic objective weights for CP-SAT.

        Parameters
        ----------
        matches : list[MultiMapMatch]
            Matches to assign objective weights.

        Returns
        -------
        list[int]
            Integer weights where LUT coverage dominates replacement count,
            and replacement count dominates the match-score tie-breaker.
        """
        score_bound = sum(abs(match.score) for match in matches)
        instance_weight = 2 * score_bound + 1
        coverage_weight = len(matches) * instance_weight + 2 * score_bound + 1
        return [
            len(match.candidate.lut_ids) * coverage_weight
            - instance_weight
            + match.score
            for match in matches
        ]

    def _ordered_matches(self, matches: list[MultiMapMatch]) -> list[MultiMapMatch]:
        """Return matches in deterministic order.

        Parameters
        ----------
        matches : list[MultiMapMatch]
            Matches to sort.

        Returns
        -------
        list[MultiMapMatch]
            Matches sorted by score and stable LUT-id signature.
        """
        return sorted(
            matches,
            key=lambda match: (match.score, tuple(sorted(match.candidate.lut_ids))),
            reverse=True,
        )

    def _selection_cmp(
        self,
        left: list[MultiMapMatch],
        right: list[MultiMapMatch],
    ) -> int:
        """Compare two selections by the class objective order.

        Parameters
        ----------
        left : list[MultiMapMatch]
            First selection.
        right : list[MultiMapMatch]
            Second selection.

        Returns
        -------
        int
            ``1`` if left is better, ``-1`` if right is better, otherwise ``0``.
        """
        left_key = self._selection_key(left)
        right_key = self._selection_key(right)
        return (left_key > right_key) - (left_key < right_key)

    def _selection_key(
        self,
        matches: list[MultiMapMatch],
    ) -> tuple[int, int, int, tuple[tuple[str, ...], ...]]:
        """Return deterministic quality key for a selected match set.

        Parameters
        ----------
        matches : list[MultiMapMatch]
            Selection to score.

        Returns
        -------
        tuple[int, int, int, tuple[tuple[str, ...], ...]]
            Key ordered by replaced LUT count, fewer replacement instances,
            score, and stable LUT-id signature.
        """
        lut_count = sum(len(match.candidate.lut_ids) for match in matches)
        score = sum(match.score for match in matches)
        signature = tuple(
            sorted(tuple(sorted(match.candidate.lut_ids)) for match in matches)
        )
        return (lut_count, -len(matches), score, signature)


def match_score(match: MultiMapMatch) -> int:
    """Return a greedy score for one successful match.

    Parameters
    ----------
    match : MultiMapMatch
        Successful multi-map match.

    Returns
    -------
    int
        Larger scores are selected first.

    Examples
    --------
    Groups with more reused boundary inputs receive a small bonus, while groups
    with many boundary inputs receive a small penalty.
    """
    lut_count = len(match.candidate.lut_ids)
    boundary_count = len(match.candidate.boundary_tokens)
    shared_count = _shared_boundary_use_count(match)
    return lut_count * 10_000 + shared_count * 100 - boundary_count * 10


def select_disjoint_matches(
    matches: list[MultiMapMatch],
    options: MultiMapOptions,
) -> list[MultiMapMatch]:
    """Select a largest-looking disjoint match set.

    Parameters
    ----------
    matches : list[MultiMapMatch]
        Successful SAT matches.
    options : MultiMapOptions
        Selection options.

    Returns
    -------
    list[MultiMapMatch]
        Disjoint match set selected by the internal selector.
    """
    selected, _metadata = select_disjoint_matches_with_report(matches, options)
    return selected


def select_disjoint_matches_with_report(
    matches: list[MultiMapMatch],
    options: MultiMapOptions,
    progress: Callable[[dict[str, object]], None] | None = None,
) -> tuple[list[MultiMapMatch], dict[str, object]]:
    """Select disjoint matches and return selector report metadata.

    Parameters
    ----------
    matches : list[MultiMapMatch]
        Successful SAT matches.
    options : MultiMapOptions
        Selection options.
    progress : Callable[[dict[str, object]], None] | None
        Optional callback receiving selector progress events.

    Returns
    -------
    tuple[list[MultiMapMatch], dict[str, object]]
        Disjoint match set plus metadata describing the selector used.

    Raises
    ------
    ValueError
        If the internal selector kind is not recognized.
    """
    selector_kind = 2
    match selector_kind:
        case 0:
            selector = GreedyDisjointSelector()
            selected = selector.select(matches, options)
            metadata = _selector_metadata(
                selector="greedy",
                status="DONE",
                input_matches=len(matches),
                selected=selected,
                fallback_used=False,
            )
            return selected, metadata
        case 1:
            selector = LocalImprovementDisjointSelector()
            selected = selector.select(matches, options, progress=progress)
            metadata = _selector_metadata(
                selector="local_improvement",
                status="DONE",
                input_matches=len(matches),
                selected=selected,
                fallback_used=False,
            )
            return selected, metadata
        case 2:
            selector = CpSatSetPackingSelector()
            return selector.select_with_metadata(matches, options, progress)
        case _:
            raise ValueError(f"unknown internal selector kind: {selector_kind}")


def prune_matches(
    matches: list[MultiMapMatch],
    options: MultiMapOptions,
) -> list[MultiMapMatch]:
    """Keep the best stored matches within the configured memory cap.

    Parameters
    ----------
    matches : list[MultiMapMatch]
        Successful SAT matches.
    options : MultiMapOptions
        Memory options.

    Returns
    -------
    list[MultiMapMatch]
        Pruned match list.
    """
    if len(matches) <= options.max_stored_matches:
        return matches
    return sorted(matches, key=lambda match: match.score, reverse=True)[
        : options.max_stored_matches
    ]


def _shared_boundary_use_count(match: MultiMapMatch) -> int:
    """Estimate input-sharing from boundary input reuse in solved tile mapping.

    Parameters
    ----------
    match : MultiMapMatch
        Successful match with decoded tile input mapping.

    Returns
    -------
    int
        Count of repeated logical sources in the solved input mapping.
    """
    counts: dict[str, int] = {}
    for source in match.result.input_mapping.values():
        counts[source] = counts.get(source, 0) + 1
    return sum(count - 1 for count in counts.values() if count > 1)


def _selector_metadata(
    *,
    selector: str,
    status: str,
    input_matches: int,
    selected: list[MultiMapMatch],
    fallback_used: bool,
    **extra: object,
) -> dict[str, object]:
    """Build user-facing selector metadata.

    Parameters
    ----------
    selector : str
        Selector implementation name.
    status : str
        Selector status label.
    input_matches : int
        Number of SAT-positive matches considered by the selector.
    selected : list[MultiMapMatch]
        Final selected match set.
    fallback_used : bool
        Whether the selector returned its fallback result.
    **extra : object
        Additional selector-specific metadata.

    Returns
    -------
    dict[str, object]
        Metadata suitable for progress logs and reports.
    """
    metadata: dict[str, object] = {
        "selector": selector,
        "status": status,
        "input_matches": input_matches,
        "selected_groups": len(selected),
        "replaced_luts": _replaced_lut_count(selected),
        "score": _selection_score(selected),
        "fallback_used": fallback_used,
    }
    metadata.update(extra)
    return metadata


def _emit_selector_event(
    progress: Callable[[dict[str, object]], None] | None,
    event: str,
    payload: dict[str, object],
) -> None:
    """Emit a selector progress event if a callback is available.

    Parameters
    ----------
    progress : Callable[[dict[str, object]], None] | None
        Optional callback.
    event : str
        Event name such as ``"start"``, ``"progress"``, or ``"finish"``.
    payload : dict[str, object]
        Event-specific values.
    """
    if progress is None:
        return
    progress({"event": event, **payload})


def _replaced_lut_count(matches: list[MultiMapMatch]) -> int:
    """Return the number of source LUTs covered by a selection.

    Parameters
    ----------
    matches : list[MultiMapMatch]
        Selected matches.

    Returns
    -------
    int
        Sum of selected group sizes.
    """
    return sum(len(match.candidate.lut_ids) for match in matches)


def _selection_score(matches: list[MultiMapMatch]) -> int:
    """Return the total heuristic score of a selection.

    Parameters
    ----------
    matches : list[MultiMapMatch]
        Selected matches.

    Returns
    -------
    int
        Sum of selected match scores.
    """
    return sum(match.score for match in matches)


def _pack_local_replacements(
    selected_without: list[MultiMapMatch],
    ordered: list[MultiMapMatch],
    selected_ids: set[int],
    removed: MultiMapMatch,
    options: MultiMapOptions,
) -> list[MultiMapMatch]:
    """Greedily pack matches made available by removing one selected match.

    Parameters
    ----------
    selected_without : list[MultiMapMatch]
        Current selection after one match has been removed.
    ordered : list[MultiMapMatch]
        All matches in deterministic greedy order.
    selected_ids : set[int]
        Object ids of matches that were part of the original selection.
    removed : MultiMapMatch
        Selected match being replaced.
    options : MultiMapOptions
        Selection options.

    Returns
    -------
    list[MultiMapMatch]
        Selection after greedily adding newly compatible replacements.
    """
    used_luts = _used_luts(selected_without)
    removed_luts = set(removed.candidate.lut_ids)
    replacement = list(selected_without)

    for match in ordered:
        if id(match) in selected_ids:
            continue
        lut_ids = set(match.candidate.lut_ids)
        if removed_luts.isdisjoint(lut_ids) or not used_luts.isdisjoint(lut_ids):
            continue
        if (
            options.max_selected_groups is not None
            and len(replacement) >= options.max_selected_groups
        ):
            break
        replacement.append(match)
        used_luts.update(lut_ids)
    return _ordered_matches(replacement)


def _ordered_matches(matches: list[MultiMapMatch]) -> list[MultiMapMatch]:
    """Return matches in deterministic greedy-selection order.

    Parameters
    ----------
    matches : list[MultiMapMatch]
        Matches to sort.

    Returns
    -------
    list[MultiMapMatch]
        Matches sorted by score and LUT-id signature.
    """
    return sorted(
        matches,
        key=lambda match: (match.score, tuple(sorted(match.candidate.lut_ids))),
        reverse=True,
    )


def _used_luts(matches: list[MultiMapMatch]) -> set[str]:
    """Return all source LUT ids used by a selection.

    Parameters
    ----------
    matches : list[MultiMapMatch]
        Selected matches.

    Returns
    -------
    set[str]
        Union of selected source LUT ids.
    """
    used: set[str] = set()
    for match in matches:
        used.update(match.candidate.lut_ids)
    return used


def _selection_cmp(left: list[MultiMapMatch], right: list[MultiMapMatch]) -> int:
    """Compare two disjoint selections by coverage and instance count.

    Parameters
    ----------
    left : list[MultiMapMatch]
        First selection.
    right : list[MultiMapMatch]
        Second selection.

    Returns
    -------
    int
        ``1`` if left is better, ``-1`` if right is better, otherwise ``0``.
    """
    left_key = _selection_key(left)
    right_key = _selection_key(right)
    return (left_key > right_key) - (left_key < right_key)


def _selection_key(
    matches: list[MultiMapMatch],
) -> tuple[int, int, int, tuple[tuple[str, ...], ...]]:
    """Return deterministic quality key for a selected match set.

    Parameters
    ----------
    matches : list[MultiMapMatch]
        Selection to score.

    Returns
    -------
    tuple[int, int, int, tuple[tuple[str, ...], ...]]
        Key ordered by replaced LUT count, fewer replacement instances, score,
        and stable LUT-id signature.
    """
    lut_count = sum(len(match.candidate.lut_ids) for match in matches)
    score = sum(match.score for match in matches)
    signature = tuple(
        sorted(tuple(sorted(match.candidate.lut_ids)) for match in matches)
    )
    return (lut_count, -len(matches), score, signature)

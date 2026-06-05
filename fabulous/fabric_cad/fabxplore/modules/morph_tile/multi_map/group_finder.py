"""Generate bounded multi-LUT group candidates.

Groups are sampled with a deterministic random generator and lightweight locality
heuristics. Only group keys are deduplicated; failed groups are not stored unless they
pass all structural filters.
"""

from __future__ import annotations

from dataclasses import dataclass
from itertools import combinations
from random import Random
from typing import TYPE_CHECKING

from fabulous.fabric_cad.fabxplore.modules.morph_tile.multi_map.models import (
    LutGraph,
    LutGroupCandidate,
    PortBitRef,
)

if TYPE_CHECKING:
    from collections.abc import Callable

    from fabulous.fabric_cad.fabxplore.modules.morph_tile.multi_map.options import (
        MultiMapOptions,
    )


@dataclass(frozen=True)
class _GroupIndex:
    """Cached graph lookups used during group sampling.

    Attributes
    ----------
    input_sets : dict[str, set[str]]
        Non-constant input tokens for each LUT id.
    input_index : dict[str, tuple[str, ...]]
        Reverse index from input token to LUT ids that consume that token.
    neighbors : dict[str, set[str]]
        Undirected LUT-to-LUT graph neighbors for each LUT id.
    """

    input_sets: dict[str, set[str]]
    input_index: dict[str, tuple[str, ...]]
    neighbors: dict[str, set[str]]


def iter_group_candidates(
    graph: LutGraph,
    options: MultiMapOptions,
    progress: Callable[[str, int, int, int], None] | None = None,
) -> list[LutGroupCandidate]:
    """Sample structurally valid LUT groups.

    Parameters
    ----------
    graph : LutGraph
        LUT graph extracted from the source design.
    options : MultiMapOptions
        Grouping options.
    progress : Callable[[str, int, int, int], None] | None
        Optional callback receiving phase, current item, total items, and kept
        candidate count.

    Returns
    -------
    list[LutGroupCandidate]
        Candidate groups in sampled order.

    Examples
    --------
    The deterministic phase gives every LUT global seed coverage, but each seed
    only explores bounded local candidates:

    ``lut_a -> local graph growth, shared-input partners, direct neighbors``

    After that, the random phase adds up to ``max_iterations`` more attempts.
    All proposed groups pass through the same boundary and duplicate filters.
    If ``options.luts_per_group`` contains multiple sizes, this function runs
    the same sampling flow for each size and merges duplicate LUT-id tuples.
    """
    group_sizes = options.group_sizes()
    if len(group_sizes) > 1:
        return _iter_group_candidates_for_sizes(graph, options, group_sizes, progress)
    luts_per_group = group_sizes[0]

    lut_ids = sorted(graph.nodes)
    if len(lut_ids) < luts_per_group:
        return []

    rng = Random(options.random_seed)
    index = _group_index(graph)
    seen: set[tuple[str, ...]] = set()
    candidates: list[LutGroupCandidate] = []

    for seed_index, seed in enumerate(lut_ids, start=1):
        for group_ids in _deterministic_seed_groups_for_seed(
            lut_ids,
            index,
            seed,
            luts_per_group,
            options.max_graph_frontier,
            options.max_graph_hops,
        ):
            candidate = _candidate_from_group(graph, index, group_ids, options)
            if candidate is None or candidate.lut_ids in seen:
                continue
            seen.add(candidate.lut_ids)
            candidates.append(candidate)
        if progress is not None:
            progress("deterministic", seed_index, len(lut_ids), len(candidates))

    attempts = 0
    while attempts < options.max_iterations:
        attempts += 1
        group_ids = _sample_group(
            lut_ids,
            index,
            luts_per_group,
            options.pure_random_match,
            rng,
        )
        if group_ids is None:
            break
        key = tuple(sorted(group_ids))
        candidate = _candidate_from_group(graph, index, key, options)
        if candidate is None or candidate.lut_ids in seen:
            if progress is not None:
                progress(
                    "random",
                    attempts,
                    options.max_iterations,
                    len(candidates),
                )
            continue
        seen.add(candidate.lut_ids)
        candidates.append(candidate)
        if progress is not None:
            progress("random", attempts, options.max_iterations, len(candidates))
    return candidates


def _iter_group_candidates_for_sizes(
    graph: LutGraph,
    options: MultiMapOptions,
    group_sizes: tuple[int, ...],
    progress: Callable[[str, int, int, int], None] | None,
) -> list[LutGroupCandidate]:
    """Sample candidates for several exact LUT-group sizes.

    Parameters
    ----------
    graph : LutGraph
        LUT graph extracted from the source design.
    options : MultiMapOptions
        Grouping options with multiple allowed group sizes.
    group_sizes : tuple[int, ...]
        Validated exact group sizes to sample.
    progress : Callable[[str, int, int, int], None] | None
        Optional progress callback.

    Returns
    -------
    list[LutGroupCandidate]
        Deduplicated candidate groups across all requested sizes.
    """
    seen: set[tuple[str, ...]] = set()
    candidates: list[LutGroupCandidate] = []
    for luts_per_group in group_sizes:
        size_options = options.with_luts_per_group(luts_per_group)
        previous_count = len(candidates)

        def size_progress(
            phase: str,
            current: int,
            total: int,
            kept: int,
            *,
            size: int = luts_per_group,
            offset: int = previous_count,
        ) -> None:
            if progress is not None:
                progress(f"{phase}[{size}]", current, total, offset + kept)

        for candidate in iter_group_candidates(
            graph,
            size_options,
            progress=size_progress,
        ):
            if candidate.lut_ids in seen:
                continue
            seen.add(candidate.lut_ids)
            candidates.append(candidate)
    return candidates


def _deterministic_seed_groups_for_seed(
    lut_ids: list[str],
    index: _GroupIndex,
    seed: str,
    luts_per_group: int,
    max_graph_frontier: int,
    max_graph_hops: int | None,
) -> list[tuple[str, ...]]:
    """Build deterministic groups anchored at one seed LUT.

    Parameters
    ----------
    lut_ids : list[str]
        All LUT ids in stable graph order.
    index : _GroupIndex
        Cached graph lookup data.
    seed : str
        LUT id used as the group anchor.
    luts_per_group : int
        Exact number of LUT ids required in each proposed group.
    max_graph_frontier : int
        Maximum graph-growth candidates considered at each expansion step.
    max_graph_hops : int | None
        Optional local cone depth. If unset, depth follows ``luts_per_group``.

    Returns
    -------
    list[tuple[str, ...]]
        Candidate LUT-id tuples proposed for this seed.

    Examples
    --------
    For ``seed="lut_0"`` and ``luts_per_group=3``, this may propose one group
    from graph growth, one from shared input nets, and one from direct
    LUT-to-LUT neighbors. Later filtering decides which of those groups are
    structurally usable.
    """
    groups: list[tuple[str, ...]] = []
    groups.extend(
        _graph_growth_seed_groups(
            index,
            seed,
            luts_per_group,
            max_graph_frontier,
            max_graph_hops,
        )
    )
    shared = _ranked_input_partners(
        lut_ids,
        index,
        seed,
        limit=luts_per_group - 1,
    )
    if len(shared) >= luts_per_group - 1:
        groups.append(tuple(sorted([seed, *shared[: luts_per_group - 1]])))
    neighbors = sorted(index.neighbors[seed])
    if len(neighbors) >= luts_per_group - 1:
        groups.append(tuple(sorted([seed, *neighbors[: luts_per_group - 1]])))
    return groups


def _graph_growth_seed_groups(
    index: _GroupIndex,
    seed: str,
    luts_per_group: int,
    max_graph_frontier: int,
    max_graph_hops: int | None,
) -> list[tuple[str, ...]]:
    """Grow local LUT-to-LUT graph groups from one seed.

    Parameters
    ----------
    index : _GroupIndex
        Cached graph lookup data.
    seed : str
        LUT id used as the group anchor.
    luts_per_group : int
        Exact number of LUTs required in a completed group.
    max_graph_frontier : int
        Maximum graph candidates kept at each expansion step.
    max_graph_hops : int | None
        Optional hop-depth override for cone-style expansion.

    Returns
    -------
    list[tuple[str, ...]]
        Completed graph-grown LUT groups.

    Examples
    --------
    With ``max_graph_hops=None`` and ``luts_per_group=3``, the search grows at
    most two graph steps. With ``max_graph_hops=4``, it first builds a bounded
    local cone and then emits fixed-size groups from that cone.
    """
    if luts_per_group == 1:
        return [(seed,)]
    if max_graph_hops is not None:
        return _graph_cone_seed_groups(
            index,
            seed,
            luts_per_group,
            max_graph_frontier,
            max_graph_hops,
        )

    return _group_sized_graph_growth(
        index,
        seed,
        luts_per_group,
        max_graph_frontier,
    )


def _group_sized_graph_growth(
    index: _GroupIndex,
    seed: str,
    luts_per_group: int,
    max_graph_frontier: int,
) -> list[tuple[str, ...]]:
    """Grow graph groups with depth derived from the target group size.

    Parameters
    ----------
    index : _GroupIndex
        Cached graph lookup data.
    seed : str
        LUT id used as the group anchor.
    luts_per_group : int
        Exact number of LUTs required in a completed group.
    max_graph_frontier : int
        Maximum graph candidates considered at each expansion step.

    Returns
    -------
    list[tuple[str, ...]]
        Completed LUT groups reachable by bounded graph growth.

    Examples
    --------
    For a chain ``lut0 -> lut1 -> lut2`` and ``luts_per_group=3``, starting at
    ``lut0`` can complete ``("lut0", "lut1", "lut2")`` without trying all
    unrelated LUT triples in the design.
    """
    beam_width = min(max_graph_frontier, max(1, luts_per_group))
    partials = [(seed,)]
    completed: list[tuple[str, ...]] = []

    for _hop in range(luts_per_group - 1):
        expanded: list[tuple[str, ...]] = []
        for group in partials:
            for candidate in _ranked_expansion_candidates(
                index,
                group,
                max_graph_frontier,
            ):
                next_group = tuple(sorted({*group, candidate}))
                if len(next_group) == len(group):
                    continue
                expanded.append(next_group)
        if not expanded:
            break

        expanded = _best_unique_groups(index, expanded, beam_width)
        completed.extend(group for group in expanded if len(group) == luts_per_group)
        partials = [group for group in expanded if len(group) < luts_per_group]
        if not partials:
            break
    return completed


def _graph_cone_seed_groups(
    index: _GroupIndex,
    seed: str,
    luts_per_group: int,
    max_graph_frontier: int,
    max_graph_hops: int,
) -> list[tuple[str, ...]]:
    """Build fixed-size groups from a bounded local LUT graph cone.

    Parameters
    ----------
    index : _GroupIndex
        Cached graph lookup data.
    seed : str
        LUT id used as the group anchor.
    luts_per_group : int
        Exact number of LUTs required in each emitted group.
    max_graph_frontier : int
        Maximum ranked neighbors retained per hop.
    max_graph_hops : int
        Number of LUT-to-LUT graph hops to explore from ``seed``.

    Returns
    -------
    list[tuple[str, ...]]
        Fixed-size groups containing ``seed`` and partners from the local cone.

    Examples
    --------
    If the two best partners are found within the cone and
    ``luts_per_group=3``, the emitted groups always contain the seed and two
    cone partners.
    """
    partners = _reachable_cone_partners(
        index,
        seed,
        max_graph_frontier,
        max_graph_hops,
    )
    if len(partners) < luts_per_group - 1:
        return []

    groups = [
        tuple(sorted((seed, *partner_group)))
        for partner_group in combinations(partners, luts_per_group - 1)
    ]
    return _best_unique_groups(index, groups, len(groups))


def _reachable_cone_partners(
    index: _GroupIndex,
    seed: str,
    max_graph_frontier: int,
    max_graph_hops: int,
) -> list[str]:
    """Return ranked LUTs reachable from one seed within a bounded graph cone.

    Parameters
    ----------
    index : _GroupIndex
        Cached graph lookup data.
    seed : str
        LUT id where the graph walk starts.
    max_graph_frontier : int
        Maximum ranked neighbors retained per hop.
    max_graph_hops : int
        Number of LUT-to-LUT graph hops to explore.

    Returns
    -------
    list[str]
        Reachable partner LUT ids ranked by connection and shared-input score.
    """
    seen = {seed}
    frontier = {seed}
    reachable: list[str] = []

    for _hop in range(max_graph_hops):
        candidates: set[str] = set()
        for lut_id in frontier:
            candidates.update(index.neighbors[lut_id])
        candidates.difference_update(seen)
        ranked = sorted(
            candidates,
            key=lambda candidate: (
                -_expansion_score(index, seen, candidate),
                candidate,
            ),
        )[:max_graph_frontier]
        if not ranked:
            break
        reachable.extend(ranked)
        seen.update(ranked)
        frontier = set(ranked)

    return sorted(
        set(reachable),
        key=lambda candidate: (-_expansion_score(index, {seed}, candidate), candidate),
    )


def _ranked_expansion_candidates(
    index: _GroupIndex,
    group: tuple[str, ...],
    max_graph_frontier: int,
) -> list[str]:
    """Return best local graph expansion candidates for one partial group.

    Parameters
    ----------
    index : _GroupIndex
        Cached graph lookup data.
    group : tuple[str, ...]
        Partial group currently being expanded.
    max_graph_frontier : int
        Maximum ranked candidates to return.

    Returns
    -------
    list[str]
        LUT ids adjacent to the partial group, ranked by expansion score.
    """
    group_set = set(group)
    candidates: set[str] = set()
    for lut_id in group:
        candidates.update(index.neighbors[lut_id])
    candidates.difference_update(group_set)
    ranked = sorted(
        candidates,
        key=lambda candidate: (
            -_expansion_score(index, group_set, candidate),
            candidate,
        ),
    )
    return ranked[:max_graph_frontier]


def _best_unique_groups(
    index: _GroupIndex,
    groups: list[tuple[str, ...]],
    limit: int,
) -> list[tuple[str, ...]]:
    """Keep the best unique partial groups within the growth limit.

    Parameters
    ----------
    index : _GroupIndex
        Cached graph lookup data.
    groups : list[tuple[str, ...]]
        Partial or complete groups to rank.
    limit : int
        Maximum number of groups to keep.

    Returns
    -------
    list[tuple[str, ...]]
        Highest-ranked unique groups.
    """
    unique = sorted(set(groups))
    ranked = sorted(
        unique,
        key=lambda group: (-_group_growth_score(index, group), group),
    )
    return ranked[:limit]


def _expansion_score(
    index: _GroupIndex,
    group: set[str],
    candidate: str,
) -> int:
    """Score adding a candidate LUT to one partial graph group.

    Parameters
    ----------
    index : _GroupIndex
        Cached graph lookup data.
    group : set[str]
        Existing partial group.
    candidate : str
        LUT id being considered for expansion.

    Returns
    -------
    int
        Larger score for candidates with more group edges and shared inputs.
    """
    connected_edges = sum(candidate in index.neighbors[lut_id] for lut_id in group)
    shared_inputs = sum(
        _shared_input_count(index, lut_id, candidate) for lut_id in group
    )
    return connected_edges * 100 + shared_inputs


def _group_growth_score(cache: _GroupIndex, group: tuple[str, ...]) -> int:
    """Score a partial group during bounded graph growth.

    Parameters
    ----------
    cache : _GroupIndex
        Cached graph lookup data.
    group : tuple[str, ...]
        LUT ids in the partial or complete group.

    Returns
    -------
    int
        Larger score for groups with more internal edges and shared inputs.
    """
    connected_edges = 0
    shared_inputs = 0
    for position, left in enumerate(group):
        for right in group[position + 1 :]:
            connected_edges += int(right in cache.neighbors[left])
            shared_inputs += _shared_input_count(cache, left, right)
    return connected_edges * 100 + shared_inputs


def _sample_group(
    lut_ids: list[str],
    index: _GroupIndex,
    luts_per_group: int,
    pure_random_match: float,
    rng: Random,
) -> tuple[str, ...] | None:
    """Sample one random group key.

    Parameters
    ----------
    lut_ids : list[str]
        All LUT ids in stable graph order.
    index : _GroupIndex
        Cached graph lookup data.
    luts_per_group : int
        Exact number of LUT ids to sample.
    pure_random_match : float
        Probability of sampling all LUTs uniformly from the whole graph.
    rng : Random
        Deterministic random generator.

    Returns
    -------
    tuple[str, ...] | None
        Sorted LUT-id group, or ``None`` if the graph is too small.

    Examples
    --------
    With ``pure_random_match=1.0``, every attempt is a total random sample from
    all LUT ids. With ``pure_random_match=0.0``, the sampler starts from one
    random seed and prefers graph neighbors or shared-input partners, falling
    back to unrelated LUTs only when needed.
    """
    if len(lut_ids) < luts_per_group:
        return None
    if pure_random_match > 0.0 and rng.random() < pure_random_match:
        return tuple(sorted(rng.sample(lut_ids, luts_per_group)))
    seed = rng.choice(lut_ids)
    pool = [lut_id for lut_id in index.neighbors[seed] if lut_id != seed]
    if rng.random() < 0.5:
        pool.extend(
            _ranked_input_partners(
                lut_ids,
                index,
                seed,
                limit=max(luts_per_group * 4, 8),
            )
        )
    if len(set(pool)) < luts_per_group - 1:
        pool.extend(lut_id for lut_id in lut_ids if lut_id != seed)
    unique_pool = sorted(set(pool))
    if len(unique_pool) < luts_per_group - 1:
        return None
    partners = rng.sample(unique_pool, luts_per_group - 1)
    return tuple(sorted([seed, *partners]))


def _group_index(graph: LutGraph) -> _GroupIndex:
    """Build cached graph lookups for group sampling.

    Parameters
    ----------
    graph : LutGraph
        Extracted LUT graph.

    Returns
    -------
    _GroupIndex
        Precomputed input sets, input reverse index, and graph neighbors.
    """
    input_sets = {
        lut_id: _nonconstant_input_tokens(node.input_tokens)
        for lut_id, node in graph.nodes.items()
    }
    index: dict[str, list[str]] = {}
    for lut_id, tokens in input_sets.items():
        for token in tokens:
            index.setdefault(token, []).append(lut_id)
    input_index = {token: tuple(sorted(lut_ids)) for token, lut_ids in index.items()}
    neighbors = {lut_id: _compute_neighbors(graph, lut_id) for lut_id in graph.nodes}
    return _GroupIndex(
        input_sets=input_sets,
        input_index=input_index,
        neighbors=neighbors,
    )


def _ranked_input_partners(
    lut_ids: list[str],
    index: _GroupIndex,
    seed: str,
    limit: int,
) -> list[str]:
    """Return shared-input partners followed by cheap zero-share fallback LUTs.

    Parameters
    ----------
    lut_ids : list[str]
        All LUT ids in stable graph order.
    index : _GroupIndex
        Cached graph lookup data.
    seed : str
        LUT id whose input tokens define the shared-input score.
    limit : int
        Maximum number of partners to return.

    Returns
    -------
    list[str]
        Partner LUT ids ranked by shared input count, then deterministic
        zero-share fallback LUTs if not enough sharing partners exist.

    Examples
    --------
    If ``lut_a`` and ``lut_b`` both consume nets ``x`` and ``y``, then
    ``lut_b`` receives a higher score as a partner for ``lut_a`` than an
    unrelated LUT with no shared inputs.
    """
    counts: dict[str, int] = {}
    for token in index.input_sets[seed]:
        for other in index.input_index.get(token, ()):
            if other == seed:
                continue
            counts[other] = counts.get(other, 0) + 1

    partners = sorted(counts, key=lambda other: (-counts[other], other))
    if len(partners) >= limit:
        return partners[:limit]

    seen = set(partners)
    seen.add(seed)
    for other in lut_ids:
        if other in seen:
            continue
        partners.append(other)
        if len(partners) >= limit:
            break
    return partners


def _nonconstant_input_tokens(tokens: tuple[str, ...]) -> set[str]:
    """Return unique non-constant input tokens.

    Parameters
    ----------
    tokens : tuple[str, ...]
        LUT input net tokens.

    Returns
    -------
    set[str]
        Input tokens except literal constants ``"0"`` and ``"1"``.
    """
    return {token for token in tokens if token not in {"0", "1"}}


def _candidate_from_group(
    graph: LutGraph,
    index: _GroupIndex,
    group_ids: tuple[str, ...],
    options: MultiMapOptions,
) -> LutGroupCandidate | None:
    """Build one candidate if it passes structural filters.

    Parameters
    ----------
    graph : LutGraph
        Extracted LUT graph.
    index : _GroupIndex
        Cached graph lookup data.
    group_ids : tuple[str, ...]
        Sorted LUT ids proposed as one group.
    options : MultiMapOptions
        Boundary and connectedness options.

    Returns
    -------
    LutGroupCandidate | None
        Candidate with boundary input and output refs, or ``None`` if the group
        fails cheap structural filters.

    Examples
    --------
    For a cascade ``lut_a -> lut_c`` where both LUTs are selected, the output
    net of ``lut_a`` is internal and is not counted as a boundary input. A net
    entering two selected LUTs is counted once because boundary tokens are
    deduplicated.
    """
    group_set = set(group_ids)
    if options.connected_only and not _is_connected_group(index, group_set):
        return None

    internal_outputs = {graph.nodes[lut_id].output_token for lut_id in group_ids}
    boundary_tokens: list[str] = []
    boundary_refs: dict[str, PortBitRef] = {}
    token_to_name: dict[str, str] = {}
    for lut_id in group_ids:
        node = graph.nodes[lut_id]
        for token, ref in zip(node.input_tokens, node.input_refs, strict=True):
            if token in {"0", "1"} or token in internal_outputs:
                continue
            if token in token_to_name:
                continue
            source_name = f"N{len(boundary_tokens)}"
            token_to_name[token] = source_name
            boundary_tokens.append(token)
            boundary_refs[source_name] = ref

    if not (
        options.min_boundary_inputs
        <= len(boundary_tokens)
        <= options.max_boundary_inputs
    ):
        return None

    output_refs = _boundary_output_refs(graph, group_ids, group_set)
    if not (
        options.min_boundary_outputs <= len(output_refs) <= options.max_boundary_outputs
    ):
        return None

    return LutGroupCandidate(
        lut_ids=group_ids,
        boundary_tokens=tuple(boundary_tokens),
        boundary_refs=boundary_refs,
        output_refs=output_refs,
    )


def _boundary_output_refs(
    graph: LutGraph,
    group_ids: tuple[str, ...],
    group_set: set[str],
) -> dict[str, PortBitRef]:
    """Return selected LUT outputs that leave the group.

    Parameters
    ----------
    graph : LutGraph
        Extracted LUT graph.
    group_ids : tuple[str, ...]
        Sorted LUT ids in the proposed group.
    group_set : set[str]
        Same ids as a set for membership checks.

    Returns
    -------
    dict[str, PortBitRef]
        Spec output name to original LUT output reference for boundary outputs.
    """
    output_refs: dict[str, PortBitRef] = {}
    for lut_id in group_ids:
        node = graph.nodes[lut_id]
        users = set(graph.users_by_token.get(node.output_token, ()))
        has_external_use = node.output_token in graph.external_user_tokens
        if not has_external_use and users and users <= group_set:
            continue
        output_refs[f"Y{len(output_refs)}"] = node.output_ref
    return output_refs


def _compute_neighbors(graph: LutGraph, lut_id: str) -> set[str]:
    """Compute LUT-to-LUT graph neighbors for one LUT.

    Parameters
    ----------
    graph : LutGraph
        Extracted LUT graph.
    lut_id : str
        LUT id whose graph neighbors should be computed.

    Returns
    -------
    set[str]
        LUT ids directly connected through a producer-consumer net.
    """
    node = graph.nodes[lut_id]
    out = set()
    for token in node.input_tokens:
        driver = graph.driver_by_token.get(token)
        if driver is not None and driver != lut_id:
            out.add(driver)
    for user in graph.users_by_token.get(node.output_token, ()):
        if user != lut_id:
            out.add(user)
    return out


def _shared_input_count(index: _GroupIndex, left: str, right: str) -> int:
    """Return the count of non-constant shared LUT input tokens.

    Parameters
    ----------
    index : _GroupIndex
        Cached graph lookup data.
    left : str
        First LUT id.
    right : str
        Second LUT id.

    Returns
    -------
    int
        Number of non-constant input tokens consumed by both LUTs.
    """
    return len(index.input_sets[left] & index.input_sets[right])


def _is_connected_group(index: _GroupIndex, group: set[str]) -> bool:
    """Return whether a group is connected by LUT-to-LUT edges.

    Parameters
    ----------
    index : _GroupIndex
        Cached graph lookup data.
    group : set[str]
        LUT ids in the proposed group.

    Returns
    -------
    bool
        ``True`` if all LUTs are reachable from each other using only selected
        LUT-to-LUT neighbor edges.
    """
    if not group:
        return False
    pending = [next(iter(group))]
    seen: set[str] = set()
    while pending:
        lut_id = pending.pop()
        if lut_id in seen:
            continue
        seen.add(lut_id)
        pending.extend(index.neighbors[lut_id] & group)
    return seen == group

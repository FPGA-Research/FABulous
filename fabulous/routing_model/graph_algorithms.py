"""Timing-graph query and path algorithms over sdf_toolkit's native graph.

These are the FABulous-specific graph queries the routing-model extraction needs
but that sdf_toolkit does not provide natively. They are plain functions that
operate on a `networkx` directed graph (the `MultiDiGraph` exposed by
`sdf_toolkit.TimingGraph.graph`) or on the native `TimingGraph` itself, so the
caller keeps owning the graph and there is no extra graph wrapper to maintain.

The corner-projection policy lives here too: `DelayType` enumerates how a
multi-corner SDF delay is collapsed to a scalar, and `project_delay` performs that
collapse. `single_delay` is the only delay-aware query: it uses sdf_toolkit's
native path enumeration (`TimingGraph.find_paths`), collapses each arc delay along
a path with `project_delay`, and returns the worst-case (critical) path delay. The
remaining queries are purely structural (reachability, hop distance, fan-out) and
ignore edge delays.
"""

from collections.abc import Callable, Iterable
from enum import StrEnum
from math import isclose
from statistics import fmean

import networkx as nx
from sdf_toolkit import TimingGraph
from sdf_toolkit.core.model import DelayPaths, Values


class DelayType(StrEnum):
    """How a multi-corner SDF delay is collapsed into a single scalar.

    Attributes
    ----------
    MIN_ALL
        Minimum delay across all corners.
    MAX_ALL
        Maximum delay across all corners.
    AVG_ALL
        Average delay across all corners.
    AVG_FAST
        Average delay across the fast corners.
    AVG_SLOW
        Average delay across the slow corners.
    MAX_FAST
        Maximum delay across the fast corners.
    MAX_SLOW
        Maximum delay across the slow corners.
    MIN_FAST
        Minimum delay across the fast corners.
    MIN_SLOW
        Minimum delay across the slow corners.
    """

    MIN_ALL = "min_all"
    MAX_ALL = "max_all"
    AVG_ALL = "avg_all"
    AVG_FAST = "avg_fast"
    AVG_SLOW = "avg_slow"
    MAX_FAST = "max_fast"
    MAX_SLOW = "max_slow"
    MIN_FAST = "min_fast"
    MIN_SLOW = "min_slow"


def _present_endpoints(values: Values | None) -> list[float]:
    """Return the min/max endpoints of a corner that the SDF actually specifies.

    Parameters
    ----------
    values : Values | None
        A corner's min/avg/max triple, or None if the corner is absent.

    Returns
    -------
    list[float]
        The specified min and max endpoints (each omitted when None); empty when
        the corner is absent or specifies neither endpoint.
    """
    if values is None:
        return []
    return [float(v) for v in (values.min, values.max) if v is not None]


def _delay_type_reducer(delay_type: DelayType) -> Callable[[Iterable[float]], float]:
    """Return the aggregation a delay type implies over alternative delays.

    Parameters
    ----------
    delay_type : DelayType
        The corner combination being extracted.

    Returns
    -------
    Callable[[Iterable[float]], float]
        ``min`` for MIN_* types, ``max`` for MAX_* types, ``fmean`` for AVG_*.

    Raises
    ------
    ValueError
        If `delay_type` is not a known `DelayType`.
    """
    match delay_type:
        case DelayType.MIN_ALL | DelayType.MIN_FAST | DelayType.MIN_SLOW:
            return min
        case DelayType.MAX_ALL | DelayType.MAX_FAST | DelayType.MAX_SLOW:
            return max
        case DelayType.AVG_ALL | DelayType.AVG_FAST | DelayType.AVG_SLOW:
            return fmean
        case _:
            raise ValueError(f"Unknown delay type: {delay_type!r}")


def project_delay(delay: DelayPaths, delay_type: DelayType) -> float:
    """Collapse a multi-corner `DelayPaths` into a single scalar delay.

    Prefers the nominal corner when present. Otherwise the fast/slow corner
    endpoints are combined according to `delay_type`, aggregating only over the
    values the SDF actually specifies: a missing `min`/`max`, or an absent corner,
    is skipped rather than treated as zero. A missing value in SDF means
    "unspecified", so coercing it to zero would corrupt min/avg aggregations.

    Parameters
    ----------
    delay : DelayPaths
        The parsed sdf_toolkit delay for one timing arc or composed path.
    delay_type : DelayType
        Which corner combination to extract.

    Returns
    -------
    float
        The scalar delay.

    Raises
    ------
    ValueError
        If `delay_type` is not a known `DelayType`, or if the delay specifies no
        value for the requested corner combination.
    """
    nominal = _present_endpoints(delay.nominal)
    if nominal:
        return max(nominal)

    fast = _present_endpoints(delay.fast)
    slow = _present_endpoints(delay.slow)

    match delay_type:
        case DelayType.MIN_ALL | DelayType.MAX_ALL | DelayType.AVG_ALL:
            values = fast + slow
        case DelayType.MIN_FAST | DelayType.MAX_FAST | DelayType.AVG_FAST:
            values = fast
        case DelayType.MIN_SLOW | DelayType.MAX_SLOW | DelayType.AVG_SLOW:
            values = slow
        case _:
            raise ValueError(f"Unknown delay type: {delay_type!r}")

    if not values:
        raise ValueError(f"SDF delay specifies no value for {delay_type!r}: {delay!r}")
    return _delay_type_reducer(delay_type)(values)


def single_delay(
    timing_graph: TimingGraph,
    source: str,
    target: str,
    delay_type: DelayType = DelayType.MAX_ALL,
) -> float:
    """Return the delay of the shortest path between two pins.

    The delay is the smallest total over the paths from `source` to `target`,
    where each arc contributes the scalar `project_delay` of its multi-corner
    delay. It is found with Dijkstra's algorithm, so it is efficient and copes
    natively with the switch-matrix cycles: analysed unconfigured, every mux
    input coexists, so mux outputs feed back into other mux inputs and form large
    strongly connected components, and a shortest-path search walks the direct
    route between the two pins without being trapped by that feedback.

    Each arc is projected to a scalar rather than composing the multi-corner
    `DelayPaths` first, because arcs in an SDF need not populate the same corners
    (an interconnect may carry only a nominal delay while an IOPATH carries
    fast/slow), and field-wise `DelayPaths` addition drops any corner that is
    missing on either arc. Parallel arcs between the same pair of nodes (e.g.
    conditional IOPATH variants of the same pin-to-pin arc) collapse with the
    aggregation the delay type implies — the worst variant for MAX_*, the best
    for MIN_*, the mean for AVG_* — so a worst-case analysis is not
    short-circuited by a fast conditional variant.

    The underlying Dijkstra search lets ``nx.NodeNotFound`` propagate when
    `source` or `target` is not in the graph, and ``nx.NetworkXNoPath`` when no
    path exists between them.

    Parameters
    ----------
    timing_graph : TimingGraph
        The native sdf_toolkit timing graph.
    source : str
        The source node.
    target : str
        The target node.
    delay_type : DelayType
        Corner combination used to collapse each arc delay into a scalar.

    Returns
    -------
    float
        The shortest-path delay between `source` and `target`.
    """
    collapse_arcs = _delay_type_reducer(delay_type)

    def edge_weight(
        _source: str, _sink: str, parallel_arcs: dict[object, dict]
    ) -> float:
        return collapse_arcs(
            project_delay(arc["delay"], delay_type) for arc in parallel_arcs.values()
        )

    return nx.dijkstra_path_length(
        timing_graph.graph, source, target, weight=edge_weight
    )


def earliest_common_nodes(
    graph: nx.DiGraph,
    sources: list[str],
    mode: str = "max",
    sentinel: str | None = None,
    prefer_sentinel_for_single_source: bool = False,
    follow_steps_to_sentinel: int = 0,
    stop: float | None = None,
) -> tuple[list[str], float | None, dict[str, dict[str, float]]]:
    """Find the structurally earliest node reachable from ALL given sources.

    The function first finds all nodes reachable from every source. It then
    restricts to the structurally earliest common region(s), using SCCs of the
    common-reachable subgraph. Among those candidates it minimizes:

        cost(v) = max_i dist(s_i, v)      if mode == "max"
        cost(v) = sum_i dist(s_i, v)      if mode == "sum"

    If several candidates still tie, it prefers the one that can still reach the
    largest downstream common region. If there is still a tie, it prefers the one
    that can reach more total downstream nodes. Final fallback is lexicographic
    node order.

    For a single source, the earliest common node is normally the source itself.
    If `prefer_sentinel_for_single_source` is True and the source can reach the
    sentinel, we follow a shortest path to the sentinel and return the node we
    walk `follow_steps_to_sentinel` edges along that path; when several shortest
    paths exist, the walk takes the lexicographically smallest successor at each
    step so the result does not depend on graph iteration order.

    Parameters
    ----------
    graph : nx.DiGraph
        The timing graph.
    sources : list[str]
        Source nodes.
    mode : str
        "max" to minimize worst distance, "sum" to minimize total distance.
    sentinel : str | None
        Optional node that can be returned if only one source is given.
    prefer_sentinel_for_single_source : bool
        If True and exactly one source is given, return the sentinel instead of
        the source when the source can reach the sentinel.
    follow_steps_to_sentinel : int
        Number of steps to follow along the path to the sentinel before returning
        the node.
    stop : float | None
        Optional cutoff for path length.

    Returns
    -------
    tuple[list[str], float | None, dict[str, dict[str, float]]]
        - best_nodes: a single-element list containing the chosen node, or [] if
          none exists
        - best_cost: minimal cost of the chosen node, or None if no common node
          exists
        - dists: source -> node -> distance

    Raises
    ------
    ValueError
        If `mode` is invalid or if a source node is not in the graph.
    """
    if mode not in {"max", "sum"}:
        raise ValueError("mode must be 'max' or 'sum'")

    sources = list(dict.fromkeys(sources))
    if not sources:
        return [], None, {}

    missing = [s for s in sources if s not in graph]
    if missing:
        raise ValueError(f"Source node(s) not in graph: {missing}")

    # Compute distances from each source to all reachable nodes.
    dists: dict[str, dict[str, float]] = {}
    for s in sources:
        dists[s] = nx.single_source_shortest_path_length(graph, s, cutoff=stop)

    # Fast path for single source: just return the source. Or follow the path to
    # the sentinel if requested and possible and return that followed node as the
    # earliest node instead.
    if len(sources) == 1:
        source = sources[0]
        if (
            prefer_sentinel_for_single_source
            and sentinel is not None
            and sentinel in graph
            and sentinel in dists[source]
        ):
            # Walk towards the sentinel along shortest-path nodes only,
            # taking the lexicographically smallest successor at each step so
            # the chosen node does not depend on graph iteration order.
            sentinel_distance = dists[source][sentinel]
            dist_to_sentinel = nx.single_source_shortest_path_length(
                graph.reverse(copy=False), sentinel, cutoff=sentinel_distance
            )
            steps = min(max(follow_steps_to_sentinel, 0), sentinel_distance)
            chosen = source
            for _ in range(steps):
                chosen = min(
                    succ
                    for succ in graph.successors(chosen)
                    if dist_to_sentinel.get(succ) == dist_to_sentinel[chosen] - 1
                )
            return [chosen], dists[source][chosen], dists
        return [source], 0.0, dists

    # Keep only nodes reachable from every source.
    common = set(dists[sources[0]].keys())
    for s in sources[1:]:
        common &= set(dists[s].keys())

    if not common:
        return [], None, dists

    # Build a new graph containing only the nodes reachable from all sources, so
    # from now on the code ignores nodes that are not common to all sources.
    common_subgraph = graph.subgraph(common).copy()

    # Find groups of mutually reachable nodes (SCCs). In a directed graph that
    # means: if A -> B, B -> C, and C -> A, then {A, B, C} is one SCC.
    sccs = list(nx.strongly_connected_components(common_subgraph))
    node_to_scc: dict[str, int] = {}
    for idx, comp in enumerate(sccs):
        for node in comp:
            node_to_scc[node] = idx

    # Count, for each SCC, how many edges come into it from a different SCC.
    scc_indegree = {i: 0 for i in range(len(sccs))}
    for u, v in common_subgraph.edges():
        su = node_to_scc[u]
        sv = node_to_scc[v]
        if su != sv:
            scc_indegree[sv] += 1

    # Earliest common regions are SCCs with no incoming edge from another common
    # SCC.
    earliest_scc_ids = {i for i, indeg in scc_indegree.items() if indeg == 0}
    candidates = [node for node in common if node_to_scc[node] in earliest_scc_ids]

    def cost(v: str) -> float:
        """Compute the cost of a node based on the selected mode."""
        if mode == "sum":
            return sum(dists[s][v] for s in sources)
        return max(dists[s][v] for s in sources)

    candidate_costs = {v: cost(v) for v in candidates}
    best_cost = min(candidate_costs.values())

    # First tie-break step: keep only nodes with minimal cost.
    cost_tied = [
        v
        for v, c in candidate_costs.items()
        if isclose(c, best_cost, rel_tol=1e-12, abs_tol=1e-12)
    ]

    if len(cost_tied) == 1:
        return [cost_tied[0]], best_cost, dists

    def common_reach_score(v: str) -> int:
        """Prefer nodes that still reach more of the common downstream region."""
        return 1 + len(nx.descendants(common_subgraph, v))

    common_scores = {v: common_reach_score(v) for v in cost_tied}
    max_common_score = max(common_scores.values())
    common_tied = [v for v in cost_tied if common_scores[v] == max_common_score]

    if len(common_tied) == 1:
        return [common_tied[0]], best_cost, dists

    def total_reach_score(v: str) -> int:
        """Second tie-break: prefer nodes that reach more of the full graph."""
        return 1 + len(nx.descendants(graph, v))

    total_scores = {v: total_reach_score(v) for v in common_tied}
    max_total_score = max(total_scores.values())
    total_tied = [v for v in common_tied if total_scores[v] == max_total_score]

    # Final deterministic fallback.
    chosen = sorted(total_tied)[0]
    return [chosen], best_cost, dists


def follow_first_fanout_from_pins(
    graph: nx.DiGraph, hier_pin_path: str, num_follow: int = 1
) -> str:
    """Follow the first fan-out path from a given hierarchical pin path.

    Can do multiple hops if `num_follow > 1`, following the first fan-out at each
    step. "First" means the lexicographically smallest successor, so the walk
    does not depend on graph iteration order.

    Parameters
    ----------
    graph : nx.DiGraph
        The timing graph.
    hier_pin_path : str
        Hierarchical pin path to start from.
    num_follow : int
        Number of fan-out hops to follow.

    Returns
    -------
    str
        The hierarchical pin path reached after following the fan-out.
    """
    current_pin = hier_pin_path
    for _ in range(num_follow):
        successor = min(graph.successors(current_pin), default=None)
        if successor is None:
            break
        current_pin = successor
    return current_pin


def nearest_targets(
    graph: nx.DiGraph, source: str, targets: Iterable[str], num: int = 1
) -> list[str]:
    """Find the nearest target node(s) from a source by hop distance.

    Runs a single breadth-first search from `source` and ranks the reachable
    targets by (distance, name), so ties between equally near targets resolve
    to the lexicographically smallest and the result does not depend on graph
    iteration order. Targets missing from the graph are ignored.

    To search towards inputs instead of outputs, pass a reversed graph as
    `graph`.

    Parameters
    ----------
    graph : nx.DiGraph
        The timing graph to traverse.
    source : str
        Source node.
    targets : Iterable[str]
        Candidate target nodes.
    num : int
        Number of nearest targets to return. If fewer are reachable, all
        reachable ones are returned.

    Returns
    -------
    list[str]
        The nearest target nodes, nearest first; empty when none is reachable.

    Raises
    ------
    ValueError
        If `targets` is empty or `num` is less than 1.
    """
    target_set = set(targets)
    if not target_set:
        raise ValueError("targets must be a non-empty iterable of nodes")
    if num < 1:
        raise ValueError("num must be at least 1")

    dist = nx.single_source_shortest_path_length(graph, source)
    ranked = sorted((d, node) for node, d in dist.items() if node in target_set)
    return [node for _, node in ranked[:num]]

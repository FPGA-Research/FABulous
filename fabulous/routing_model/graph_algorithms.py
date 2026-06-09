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
        case DelayType.MIN_ALL:
            values, reducer = fast + slow, min
        case DelayType.MAX_ALL:
            values, reducer = fast + slow, max
        case DelayType.AVG_ALL:
            values, reducer = fast + slow, fmean
        case DelayType.AVG_FAST:
            values, reducer = fast, fmean
        case DelayType.AVG_SLOW:
            values, reducer = slow, fmean
        case DelayType.MAX_FAST:
            values, reducer = fast, max
        case DelayType.MAX_SLOW:
            values, reducer = slow, max
        case DelayType.MIN_FAST:
            values, reducer = fast, min
        case DelayType.MIN_SLOW:
            values, reducer = slow, min
        case _:
            raise ValueError(f"Unknown delay type: {delay_type!r}")

    if not values:
        raise ValueError(f"SDF delay specifies no value for {delay_type!r}: {delay!r}")
    return reducer(values)


def single_delay(
    timing_graph: TimingGraph,
    source: str,
    target: str,
    delay_type: DelayType = DelayType.MAX_ALL,
) -> float:
    """Return the worst-case path delay between two pins.

    Uses sdf_toolkit's native path enumeration (`TimingGraph.find_paths`) to find
    every simple path from `source` to `target`. Each arc's multi-corner delay is
    collapsed to a scalar with `project_delay` and summed along the path; the
    largest path total (the critical path) is returned.

    Each arc is projected to a scalar before summing rather than composing the
    multi-corner `DelayPaths` first, because arcs in an SDF need not populate the
    same corners (an interconnect may carry only a nominal delay while an IOPATH
    carries fast/slow), and field-wise `DelayPaths` addition drops any corner that
    is missing on either arc.

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
        The worst-case delay between `source` and `target`.

    Raises
    ------
    nx.NetworkXNoPath
        If no path exists between `source` and `target`.
    """
    paths = timing_graph.find_paths(source, target)
    if not paths:
        raise nx.NetworkXNoPath(f"No path from {source!r} to {target!r}")
    return max(
        sum(project_delay(edge.delay, delay_type) for edge in path) for path in paths
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
    sentinel, we follow the shortest path to the sentinel and return the node we
    walk `follow_steps_to_sentinel` edges along that path.

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
            path = nx.shortest_path(graph, source=source, target=sentinel)
            step_idx = min(max(follow_steps_to_sentinel, 0), len(path) - 1)
            chosen = path[step_idx]
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
    step.

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
        successor = next(graph.successors(current_pin), None)
        if successor is None:
            break
        current_pin = successor
    return current_pin


def path_to_nearest_target_sentinel(
    graph: nx.DiGraph,
    source: str,
    targets: list[str],
    weight: str | None = None,
    sentinel_prefix: str = "_sentinel_",
) -> tuple[list[str] | None, str | None]:
    """Shortest path to the nearest target using the sentinel-node trick.

    Find the shortest path from `source` to the nearest node in `targets` in a
    directed NetworkX graph by attaching a temporary sentinel node that every
    target points to with a zero-cost edge.
    https://networkx.org/documentation/stable/reference/algorithms/shortest_paths.html

    To search towards inputs instead of outputs, pass a reversed graph as
    `graph`.

    Parameters
    ----------
    graph : nx.DiGraph
        The timing graph to traverse.
    source : str
        Source node.
    targets : list[str]
        Candidate target nodes.
    weight : str | None
        Edge attribute name to use as weight. If None, the graph is treated as
        unweighted (hop count).
    sentinel_prefix : str
        Base name for the temporary sentinel node.

    Returns
    -------
    tuple[list[str] | None, str | None]
        - path: list of nodes from `source` to the closest target (no sentinel),
          or None if no target is reachable.
        - closest_target: the closest target node, or None if none is reachable.

    Raises
    ------
    ValueError
        If `targets` is empty.
    """
    target_set = set(targets)
    if not target_set:
        raise ValueError("targets must be a non-empty iterable of nodes")

    # Pick a sentinel name that does not collide with existing nodes.
    sentinel = f"{sentinel_prefix}_i89f9j9g58f7g6e5d4c3b2a1"

    graph.add_node(sentinel)

    # Add zero-cost edges from each target to the sentinel.
    if weight is None:
        for t in target_set:
            graph.add_edge(t, sentinel)
    else:
        for t in target_set:
            graph.add_edge(t, sentinel, **{weight: 0})
    try:
        path = nx.shortest_path(graph, source=source, target=sentinel, weight=weight)
    except nx.NetworkXNoPath:
        return None, None
    finally:
        # Remove the sentinel whether or not a path was found.
        if sentinel in graph:
            graph.remove_node(sentinel)

    # The real closest target is the node before the sentinel.
    closest_target = path[-2]
    path_without_sentinel = path[:-1]

    return path_without_sentinel, closest_target

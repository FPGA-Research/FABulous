"""SDF to Timing Graph Conversion Module.

This module provides functionality to convert SDF files into timing graphs represented
as NetworkX directed graphs. It is the main class used to create timing graphs from SDF
files. It is derived from SDFTimingGraphBase which provides basic functionality.

New algorithms can be added here. Note that this is a low level module focused on graph
algorithms based on the SDF, and should not contain high-level algorithms based on
verilog netlists.
"""

from math import isclose

import networkx as nx

from fabulous.fabric_cad.timing_model.hdlnx.sdfnx.sdf_to_graph_base import (
    SDFTimingGraphBase,
)


class SDFTimingGraph(SDFTimingGraphBase):
    """Class to represent a timing graph generated from an SDF file.

    It extends SDFTimingGraphBase to allow for additional algorithms specific to timing
    analysis on the SDF timing graph. Inherits all attributes and methods from
    SDFTimingGraphBase.
    """

    ### Public Methods ###

    def has_path(self, source: str, target: str) -> bool:
        """Check if there is a path from source to target in the timing graph.

        Parameters
        ----------
        source : str
            The source node.
        target : str

            The target node.

        Returns
        -------
        bool
            True if a path exists, False otherwise.

        Examples
        --------
            exists = sdf_graph.has_path("nodeA/pin", "nodeB/pin")
        """
        return nx.has_path(self.graph, source=source, target=target)

    def delay_path(self, source: str, target: str) -> tuple[float, list[str], str]:
        """Find path with delay between source and target nodes in the timing graph.

        Parameters
        ----------
        source : str

            The source node.
        target : str

            The target node.

        Returns
        -------
        tuple[float, list[str], str]
            A tuple containing the total delay, the path as a list of nodes,
            and a detailed info string about the path.

        Examples
        --------
            length, path, info = sdf_graph.delay_path("nodeA/pin", "nodeB/pin")
        """
        length: float = nx.dijkstra_path_length(
            self.graph, source=source, target=target, weight="weight"
        )
        path: list[str] = nx.dijkstra_path(
            self.graph, source=source, target=target, weight="weight"
        )
        info: str = ""

        for i in range(len(path) - 1):
            u = path[i]
            v = path[i + 1]
            edge_data = self.graph.edges[u, v]
            info += (
                f"{u} -> {v} with delay {edge_data['weight']} "
                f"({edge_data['component'].cell_name},"
                f"{edge_data['component'].c_type})\n"
            )
        return length, path, info

    def earliest_common_nodes(
        self,
        sources: list[str],
        mode: str = "max",
        sentinel: str | None = None,
        prefer_sentinel_for_single_source: bool = False,
        follow_steps_to_sentinel: int = 0,
        stop: float | None = None,
    ) -> tuple[list[str], float | None, dict[str, dict[str, float]]]:
        """Find the structurally earliest node reachable from ALL given sources.

        The function first finds all nodes reachable from every source.
        It then restricts to the structurally earliest common region(s), using SCCs
        of the common-reachable subgraph. Among those candidates it minimizes:

            cost(v) = max_i dist(s_i, v)      if mode == "max"
            cost(v) = sum_i dist(s_i, v)      if mode == "sum"

        If several candidates still tie, it prefers the one that can
        still reach the largest downstream common region. If there is still a tie,
        it prefers the one that can reach more total downstream nodes. Final fallback
        is lexicographic node order.

        For a single source, the earliest common node is normally the source itself.
        If `prefer_sentinel_for_single_source` is True and the source can reach the
        sentinel, we follow the shortest path to the sentinel and return the node
        we walk follow_steps_to_sentinel edges along that path.

        Parameters
        ----------
        sources : list[str]
            Source nodes.
        mode : str
            "max" to minimize worst distance, "sum" to minimize total distance.
        sentinel : str | None
            Optional node that can be returned if only one source is given.
        prefer_sentinel_for_single_source : bool
            If True and exactly one source is given, return the sentinel instead of the
            source when the source can reach the sentinel.
        follow_steps_to_sentinel : int
            Number of steps to follow along the path to the sentinel before
            returning the node.
        stop : float | None
            Optional cutoff for path length.

        Returns
        -------
        tuple[list[str], float | None, dict[str, dict[str, float]]]
            - best_nodes: a single-element list containing the chosen node,
              or [] if none exists
            - best_cost: minimal cost of the chosen node,
              or None if no common node exists
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

        missing = [s for s in sources if s not in self.graph]
        if missing:
            raise ValueError(f"Source node(s) not in graph: {missing}")

        # Compute distances from each source to all reachable nodes.
        dists: dict[str, dict[str, float]] = {}
        for s in sources:
            # Compute shortest-path distances from each source.
            dists[s] = nx.single_source_shortest_path_length(self.graph, s, cutoff=stop)

        # Fast path for single source: just return the source.
        # Or follow the path to the sentinel if requested and possible
        # and return that follwed node as the earliest node instead.
        if len(sources) == 1:
            source = sources[0]
            if (
                prefer_sentinel_for_single_source
                and sentinel is not None
                and sentinel in self.graph
                and sentinel in dists[source]
            ):
                path = nx.shortest_path(self.graph, source=source, target=sentinel)
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

        # Builds a new graph containing only the nodes that are reachable
        # from all sources. So from now on, the code ignores nodes that are
        # not common to all sources.
        common_subgraph = self.graph.subgraph(common).copy()

        # Finds groups of nodes where every node can reach every other node
        # in the same group. In a directed graph, that means they form a mutually
        # reachable region. Example: if A -> B, B -> C, and C -> A, then {A, B, C}
        # is one SCC
        sccs = list(nx.strongly_connected_components(common_subgraph))
        node_to_scc: dict[str, int] = {}
        for idx, comp in enumerate(sccs):
            for node in comp:
                node_to_scc[node] = idx

        # Creates a counter for each SCC
        # This will count how many edges come into that SCC from a different SCC
        scc_indegree = {i: 0 for i in range(len(sccs))}
        for u, v in common_subgraph.edges():
            su = node_to_scc[u]
            sv = node_to_scc[v]
            if su != sv:
                scc_indegree[sv] += 1

        # Earliest common regions are SCCs with no incoming edge
        # from another common SCC.
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
            return 1 + len(nx.descendants(self.graph, v))

        total_scores = {v: total_reach_score(v) for v in common_tied}
        max_total_score = max(total_scores.values())
        total_tied = [v for v in common_tied if total_scores[v] == max_total_score]

        # Final deterministic fallback.
        chosen = sorted(total_tied)[0]
        return [chosen], best_cost, dists

    def follow_first_fanout_from_pins(
        self, hier_pin_path: str, num_follow: int = 1
    ) -> str:
        """Follow the first fanout path from a given hierarchical pin path.

        Can do multiple hops if num_follow > 1, following the first
        fanout at each step.

        Parameters
        ----------
        hier_pin_path : str
            Hierarchical pin path to start from.
        num_follow : int
            Number of fanout hops to follow.

        Returns
        -------
        str
            The hierarchical pin path reached after following the fanout.
        """
        current_pin: str = hier_pin_path
        for _ in range(num_follow):
            successors = next(self.graph.successors(current_pin), None)
            if successors is None:
                break
            current_pin = successors
        return current_pin

    def path_to_nearest_target_sentinel(
        self,
        source: str,
        targets: list[str],
        weight: str | None = None,
        sentinel_prefix: str = "_sentinel_",
        reverse: bool = False,
    ) -> tuple[list[str], str]:
        """Shortest path to nearest target using sentinel-node trick.

        Find the shortest path from `source` to the nearest node in `targets`
        in a (directed) NetworkX graph using the sentinel-node trick.
        https://networkx.org/documentation/stable/reference/algorithms/shortest_paths.html

        Parameters
        ----------
        source : str
            Source node.
        targets : list[str]
            List of target nodes.
        weight : str | None, optional
            Edge attribute name to use as weight. If None, the graph is treated
            as unweighted (hop count).
        sentinel_prefix : str, optional
            Base name for the temporary sentinel node (ensured to be unique).
        reverse : bool
            If True, find the shortest path from the nearest target to the source
            instead (i.e., reverse the graph direction).

        Returns
        -------
        path : list[str]
            List of nodes from `source` to the closest target (no sentinel),
            or None if no target is reachable.
        closest_target : str
            The closest target node, or None if no target is reachable.

        Raises
        ------
        ValueError
            If `targets` is empty.
        """
        G = self.reverse_graph if reverse else self.graph
        targets: set[str] = set(targets)
        if not targets:
            raise ValueError("targets must be a non-empty iterable of nodes")

        # Pick a sentinel name that doesn't collide with existing nodes
        sentinel: str = f"{sentinel_prefix}_i89f9j9g58f7g6e5d4c3b2a1"

        G.add_node(sentinel)

        # Add zero-cost edges from each target to the sentinel
        if weight is None:
            for t in targets:
                G.add_edge(t, sentinel)
        else:
            for t in targets:
                G.add_edge(t, sentinel, weight=0)
        try:
            # Shortest path (directed) source -> sentinel
            path: list[str] = nx.shortest_path(
                G, source=source, target=sentinel, weight=weight
            )
        except nx.NetworkXNoPath:
            # Clean up and signal no reachable target
            G.remove_node(sentinel)
            return None, None
        finally:
            # If shortest_path raised, sentinel is still removed here.
            if sentinel in G:
                G.remove_node(sentinel)

        # Remove sentinel from the path
        # The real closest target is the node before the sentinel
        closest_target: str = path[-2]
        path_without_sentinel: list[str] = path[:-1]

        return path_without_sentinel, closest_target

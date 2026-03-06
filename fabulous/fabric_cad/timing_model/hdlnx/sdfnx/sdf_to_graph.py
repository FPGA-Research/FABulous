"""
SDF to Timing Graph Conversion Module
This module provides functionality to convert SDF files into timing graphs
represented as NetworkX directed graphs.
It is the main class used to create timing graphs from SDF files.
It is derived from SDFTimingGraphBase which provides basic functionality.

New algorithms can be added here. Note that this is a low level module focused on graph 
algorithms based on the SDF, and should not contain high-level algorithms based on
verilog netlists.
"""


import networkx as nx
from fabulous.fabric_cad.timing_model.hdlnx.sdfnx.sdf_to_graph_base import SDFTimingGraphBase
from fabulous.fabric_cad.timing_model.models import *


class SDFTimingGraph(SDFTimingGraphBase):
    """
    Class to represent a timing graph generated from an SDF file.
    It extends SDFTimingGraphBase to allow for additional algorithms
    specific to timing analysis on the SDF timing graph.
    Inherits all attributes and methods from SDFTimingGraphBase.
    """

    ### Public Methods ###
    
    def has_path(self, source: str, target: str) -> bool:
        """
        Check if there is a path from source to target in the timing graph.

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
        """
        Find the path with the delay between source and target nodes in the timing graph.

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
                f"{u} -> {v} with delay {edge_data['weight']} ({edge_data['component'].cell_name},"
                f"{edge_data['component'].c_type})\n"
            )
        return length, path, info

    def earliest_common_nodes(
        self,
        sources: list[str],
        mode: str = "max",
        consider_delay: bool = True,
        stop: float | int | None = None,
    ) -> tuple[list[str], float | None, dict[str, dict[str, float]]]:
        """
        Find the earliest node(s) that are reachable from ALL given sources in a directed graph.
        Similar to betweenness_centrality_subset, but finds nodes that minimize the maximum (or sum) distance
        from all sources.

        For each node v reachable from every s in `sources`, we define a cost:

            cost(v) = max_i dist(s_i, v)      if mode == "max" (minimize worst distance)
            cost(v) = sum_i dist(s_i, v)      if mode == "sum" (minimize total distance)

        Parameters
        ----------
        sources : list[str]
            Iterable of source nodes.
        mode : str
            "max" to minimize worst distance, "sum" to minimize total distance.
        consider_delay : bool
            Whether to consider edge weights (delay) in distance calculation.
            Otherwise, use hop count.
        stop : float | int
            Optional cutoff for maximum path length to consider. If consider_delay is True,
            this is in units of delay; otherwise, in hops.

        Returns
        -------
        tuple[list[str], float, dict[str, dict[str, float]]]
            - best_nodes (list[str]): list of nodes with minimal cost (may be multiple)
            - best_cost (float): the minimal cost value (hop-count, or delay sum), or None if no common node
            - dists (dict[str, dict[str, float]]): dict: source -> dict(node -> distance)
        """
        sources = list(sources)
        if not sources:
            return [], None, {}

        # BFS from each source (unweighted shortest path length)
        dists: dict[str, dict[str, float]] = {}
        for s in sources:
            dists[s] = nx.single_source_dijkstra_path_length(
                self.graph, s, cutoff=stop, weight="weight" if consider_delay else None
            )

        # Nodes reachable from ALL sources
        common = None
        for s in sources:
            reachable = set(dists[s].keys())
            common = reachable if common is None else (common & reachable)

        if not common:
            return [], None, dists  # no common reachable node

        # Cost function
        if mode == "sum":

            def cost(v):
                """Cost is the sum of distances from all sources to v."""
                return sum(dists[s][v] for s in sources)
        else:

            def cost(v):
                """Cost is the maximum distance from any source to v."""
                return max(dists[s][v] for s in sources)

        # Find minimal cost and all nodes achieving it
        best_cost = min(cost(v) for v in common)
        best_nodes = [v for v in common if cost(v) == best_cost]

        return best_nodes, best_cost, dists

    def follow_first_fanout_from_pins(
        self, hier_pin_path: str, num_follow: int = 1
    ) -> str:
        """
        Follow the first fanout path from a given hierarchical pin path
        for a specified number of hops.

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
        """
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

        Returns
        -------
        path : list[str] | None
            List of nodes from `source` to the closest target (no sentinel),
            or None if no target is reachable.
        closest_target : str | None
            The closest target node, or None if no target is reachable.

        Raises
        ------
        ValueError
            If `targets` is empty.
        """
        if reverse:
            G = self.reverse_graph
        else:
            G = self.graph

        targets: set[str] = set(targets)
        if not targets:
            raise ValueError("targets must be a non-empty iterable of nodes")

        # Pick a sentinel name that doesn't collide with existing nodes
        sentinel: str = f"{sentinel_prefix}_i89f9j9g58f7g6e5d4c3b2a1"

        G.add_node(sentinel)

        # Add zero-cost edges from each target to the sentinel
        if weight is None:
            for t in targets:
                # if G.has_node(t):
                G.add_edge(t, sentinel)
        else:
            for t in targets:
                # if G.has_node(t):
                G.add_edge(t, sentinel, weight=0)
        try:
            # Shortest path (directed) source -> sentinel
            path: list[str] = nx.shortest_path(
                G, source=source, target=sentinel, weight=weight
            )
            # dist: float = nx.shortest_path_length(G, source=source, target=sentinel, weight=weight)
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

        # Adjust distance for unweighted graphs (we added one extra edge)
        # if weight is None:
        # dist = dist - 1

        return path_without_sentinel, closest_target  # , dist

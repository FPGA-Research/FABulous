#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# SDF to Timing Graph Conversion Module
# This module provides functionality to convert SDF files into timing graphs
# represented as NetworkX directed graphs.
# It is the main class used to create timing graphs from SDF files.
# It is derived from SDFTimingGraphBase which provides basic functionality.
# New algorithms can be added here.

from pathlib import Path
import math

import networkx as nx

from .sdf_to_graph_base import SDFTimingGraphBase

class SDFTimingGraph(SDFTimingGraphBase):
    """
    Class to represent a timing graph generated from an SDF file.
    It extends SDFTimingGraphBase to allow for additional algorithms
    specific to timing analysis.
    Inherits all attributes and methods from SDFTimingGraphBase.
    """
    
    ### Public Methods ###
    
    def earliest_common_nodes(self, sources: list[str], mode: str = "max",
                              consider_delay: bool = True, 
                              stop: float | int = None) -> tuple[list[str], float, dict[str, dict[str, float]]]:
        """
        Find the earliest node(s) that are reachable from ALL given sources in a directed graph.
        Similar to betweenness_centrality_subset, but finds nodes that minimize the maximum (or sum) distance
        from all sources.

        For each node v reachable from every s in `sources`, we define a cost:

            cost(v) = max_i dist(s_i, v)      if mode == "max" (minimize worst distance)
            cost(v) = sum_i dist(s_i, v)      if mode == "sum" (minimize total distance)
            
        Arguments:
            sources (list[str]): Iterable of source nodes.
            mode (str): "max" to minimize worst distance, "sum" to minimize total distance.
            consider_delay (bool): Whether to consider edge weights (delay) in distance calculation.
                                   Otherwise, use hop count.
            stop (float | int): Optional cutoff for maximum path length to consider. If consider_delay is True,
                                this is in units of delay; otherwise, in hops.

        Returns:
            tuple (list[str], float, dict[str, dict[str, float]]):
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
            dists[s] = nx.single_source_dijkstra_path_length(self.graph, s, cutoff=stop, 
                                                             weight="weight" if consider_delay else None)

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
                return sum(dists[s][v] for s in sources)
        else:
            def cost(v):
                return max(dists[s][v] for s in sources)

        # Find minimal cost and all nodes achieving it
        best_cost = min(cost(v) for v in common)
        best_nodes = [v for v in common if cost(v) == best_cost]

        return best_nodes, best_cost, dists
    
    def follow_first_fanout_from_pins(self, hier_pin_path: str, num_follow: int = 1) -> str:
        """
        Follow the first fanout path from a given hierarchical pin path
        for a specified number of hops.
        
        Args:
            hier_pin_path (str): Hierarchical pin path to start from.
            num_follow (int): Number of fanout hops to follow.
        Returns:
            str: The hierarchical pin path reached after following the fanout.
        """
        
        current_pin: str = hier_pin_path
        for _ in range(num_follow):
            successors = next(self.graph.successors(current_pin), None)
            if successors is None:
                break
            current_pin = successors
        return current_pin
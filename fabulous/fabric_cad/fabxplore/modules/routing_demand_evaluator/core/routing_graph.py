"""Routing graph for demand evaluation."""

from __future__ import annotations

from dataclasses import dataclass, field
from heapq import heappop, heappush
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Iterable


@dataclass(frozen=True)
class RoutingGraph:
    """Directed routing-resource graph.

    Attributes
    ----------
    node_to_id : dict[str, int]
        Mapping from node names to compact integer identifiers.
    id_to_node : list[str]
        Node names indexed by integer identifier.
    adjacency : dict[int, list[int]]
        Directed adjacency list.
    """

    node_to_id: dict[str, int]
    id_to_node: list[str]
    adjacency: dict[int, list[int]]

    @classmethod
    def from_edges(cls, edges: Iterable[tuple[str, str]]) -> RoutingGraph:
        """Build a graph from named directed edges.

        Parameters
        ----------
        edges : Iterable[tuple[str, str]]
            Directed ``source, sink`` edge pairs.

        Returns
        -------
        RoutingGraph
            Compact integer graph.
        """
        node_to_id: dict[str, int] = {}
        id_to_node: list[str] = []
        adjacency_sets: dict[int, set[int]] = {}

        def node_id(name: str) -> int:
            if name not in node_to_id:
                node_to_id[name] = len(id_to_node)
                id_to_node.append(name)
            return node_to_id[name]

        for source, sink in edges:
            source_id = node_id(source)
            sink_id = node_id(sink)
            adjacency_sets.setdefault(source_id, set()).add(sink_id)
            adjacency_sets.setdefault(sink_id, set())

        adjacency = {
            node: sorted(sinks) for node, sinks in sorted(adjacency_sets.items())
        }
        return cls(node_to_id=node_to_id, id_to_node=id_to_node, adjacency=adjacency)

    def has_node(self, name: str) -> bool:
        """Return whether a node exists.

        Parameters
        ----------
        name : str
            Node name.

        Returns
        -------
        bool
            Whether the node is present.
        """
        return name in self.node_to_id

    def sources(self) -> list[str]:
        """Return graph nodes with outgoing edges.

        Returns
        -------
        list[str]
            Source-capable node names.
        """
        return [
            self.id_to_node[node] for node, sinks in self.adjacency.items() if sinks
        ]

    def sinks(self) -> list[str]:
        """Return graph nodes with incoming edges.

        Returns
        -------
        list[str]
            Sink-capable node names.
        """
        incoming = {sink for sinks in self.adjacency.values() for sink in sinks}
        return [self.id_to_node[node] for node in sorted(incoming)]

    def edges(self) -> list[tuple[str, str]]:
        """Return named graph edges.

        Returns
        -------
        list[tuple[str, str]]
            Directed edge pairs.
        """
        return [
            (self.id_to_node[source], self.id_to_node[sink])
            for source, sinks in self.adjacency.items()
            for sink in sinks
        ]

    def shortest_path(
        self,
        source: str,
        sink: str,
        node_costs: dict[int, float] | None = None,
    ) -> tuple[list[str], float] | None:
        """Find a shortest path using Dijkstra search.

        Parameters
        ----------
        source : str
            Source node.
        sink : str
            Sink node.
        node_costs : dict[int, float] | None
            Optional extra node costs keyed by node id.

        Returns
        -------
        tuple[list[str], float] | None
            Path and cost, or ``None`` if unreachable.
        """
        if source not in self.node_to_id or sink not in self.node_to_id:
            return None

        source_id = self.node_to_id[source]
        sink_id = self.node_to_id[sink]
        costs = node_costs or {}
        queue: list[tuple[float, int]] = [(0.0, source_id)]
        distances = {source_id: 0.0}
        parents: dict[int, int] = {}

        while queue:
            cost, node = heappop(queue)
            if node == sink_id:
                return self._path_from_parents(parents, source_id, sink_id), cost
            if cost != distances[node]:
                continue
            for next_node in self.adjacency.get(node, []):
                next_cost = cost + 1.0 + costs.get(next_node, 0.0)
                if next_cost < distances.get(next_node, float("inf")):
                    distances[next_node] = next_cost
                    parents[next_node] = node
                    heappush(queue, (next_cost, next_node))
        return None

    def shortest_path_to_any(
        self,
        sources: list[str],
        sink: str,
        node_costs: dict[int, float] | None = None,
    ) -> tuple[list[str], float] | None:
        """Find a shortest path from any source to one sink.

        Parameters
        ----------
        sources : list[str]
            Candidate source nodes.
        sink : str
            Sink node.
        node_costs : dict[int, float] | None
            Optional extra node costs keyed by node id.

        Returns
        -------
        tuple[list[str], float] | None
            Path and cost, or ``None`` if unreachable.
        """
        best: tuple[list[str], float] | None = None
        for source in sources:
            path = self.shortest_path(source, sink, node_costs)
            if path is None:
                continue
            if best is None or path[1] < best[1]:
                best = path
        return best

    def _path_from_parents(
        self,
        parents: dict[int, int],
        source_id: int,
        sink_id: int,
    ) -> list[str]:
        """Reconstruct a path from a Dijkstra parent map.

        Parameters
        ----------
        parents : dict[int, int]
            Parent map.
        source_id : int
            Source node id.
        sink_id : int
            Sink node id.

        Returns
        -------
        list[str]
            Node-name path.
        """
        path = [sink_id]
        while path[-1] != source_id:
            path.append(parents[path[-1]])
        path.reverse()
        return [self.id_to_node[node] for node in path]


@dataclass
class RoutingGraphBuilder:
    """Incrementally build a routing graph.

    Attributes
    ----------
    edges : list[tuple[str, str]]
        Directed edge pairs.
    """

    edges: list[tuple[str, str]] = field(default_factory=list)

    def add_connection_rows(self, connections: dict[str, list[str]]) -> None:
        """Add switch-matrix row PIPs.

        Parameters
        ----------
        connections : dict[str, list[str]]
            Mapping from destination row to selectable source names.
        """
        for sink, sources in connections.items():
            for source in sources:
                self.edges.append((source, sink))

    def add_jump_edges(self, jump_edges: list[tuple[str, str]]) -> None:
        """Add local JUMP resource edges.

        Parameters
        ----------
        jump_edges : list[tuple[str, str]]
            Directed JUMP edges.
        """
        self.edges.extend(jump_edges)

    def build(self) -> RoutingGraph:
        """Build the compact routing graph.

        Returns
        -------
        RoutingGraph
            Built graph.
        """
        return RoutingGraph.from_edges(self.edges)

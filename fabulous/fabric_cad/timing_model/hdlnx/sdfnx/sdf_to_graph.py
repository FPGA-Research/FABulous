"""SDF to Timing Graph Conversion Module.

This module provides functionality to convert SDF files into timing graphs represented
as NetworkX directed graphs. It is the main class used to create timing graphs from SDF
files. It is derived from SDFTimingGraphBase which provides basic functionality.

New algorithms can be added here. Note that this is a low level module focused on graph
algorithms based on the SDF, and should not contain high-level algorithms based on
verilog netlists.
"""

from dataclasses import replace
from functools import cached_property
from itertools import islice, pairwise
from math import isclose

import networkx as nx
from typing_extensions import deprecated

from fabulous.fabric_cad.timing_model.hdlnx.sdfnx.sdf_to_graph_base import (
    SDFTimingGraphBase,
)
from fabulous.fabric_cad.timing_model.models import (
    Component,
    SDFCellType,
    SDFPathTiming,
    SDFPathType,
    SDFTimingTriplet,
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

    @deprecated("Use query_timing_paths() instead.")
    def single_delay(self, source: str, target: str) -> float:
        """Find path with delay between source and target nodes in the timing graph.

        Note: The delay value depends on delay_type_str when creating the graph.
        For example, if delay_type_str="max_all", then the delay represents the
        maximum delay along the path. If delay_type_str="min_all", then the
        delay represents the minimum delay along the path. Fastest way to obtain
        only a single delay value along the path.

        Parameters
        ----------
        source : str
            The source node.

        target : str
            The target node.

        Returns
        -------
        float
            The total delay between the source and target nodes.

        Examples
        --------
            length = sdf_graph.single_delay("nodeA/pin", "nodeB/pin")
        """
        length: float = nx.dijkstra_path_length(
            self.graph, source=source, target=target, weight="weight"
        )
        return length

    def query_timing_paths(
        self,
        source: str,
        target: str,
        max_paths: int = 10,
        clock_pin: str | None = None,
    ) -> list[SDFPathTiming]:
        """Return complete timing information for the shortest structural paths.

        Paths are ordered by edge count rather than delay, keeping path discovery
        independent of the scalar delay selected when the graph was constructed. The
        search is bounded and lazy, and results beyond `max_paths` are truncated.

        When `clock_pin` is supplied, sequential paths are split at their first
        synthetic data-to-clock timing-check edge. Setup and hold constraints are
        adjusted for the data path before that edge and the clock path from
        `clock_pin` to the matching register clock. Clock-to-target propagation uses
        that clock path and the selected sequential path's exact output suffix. Raw
        standard-cell timing checks remain available separately.

        The current SDF parser stores one transition triple as `nominal`, two as
        `fast` and `slow`, and three as `fast`, `nominal`, and `slow`. This method
        normalizes those shapes according to SDF transition ordering: a single value
        applies to rise and fall, while the first and second values of longer lists
        describe rise and fall respectively. Within each triple, the parser's `avg`
        value is the SDF typical value.

        Parameters
        ----------
        source : str
            Source graph node.
        target : str
            Target graph node.
        max_paths : int
            Maximum number of shortest simple paths to return.
        clock_pin : str | None
            Optional graph pin representing the BEL-level clock source. Without it,
            raw timing checks and propagation delays are still returned, but effective
            setup/hold and clock-to-target delays are unavailable.

        Returns
        -------
        list[SDFPathTiming]
            Timing results ordered from the fewest to the most graph edges.

        Raises
        ------
        ValueError
            If `max_paths` is less than one or a propagation component contains an
            unsupported delay-path shape.

        Notes
        -----
        NetworkX propagates `NodeNotFound` when either endpoint is absent and
        `NetworkXNoPath` when the endpoints are disconnected.
        """
        if max_paths < 1:
            raise ValueError("max_paths must be at least 1.")

        path_timings: list[SDFPathTiming] = self._query_structural_timing_paths(
            source,
            target,
            max_paths,
        )
        if clock_pin is None:
            return path_timings

        clock_paths: dict[str, SDFPathTiming | None] = {}
        clocked_path_timings: list[SDFPathTiming] = []
        for path_timing in path_timings:
            register_clock_pin: str | None = path_timing.register_clock_pin
            effective_setup: tuple[SDFTimingTriplet, ...] = ()
            effective_hold: tuple[SDFTimingTriplet, ...] = ()
            clock_to_output_rise: SDFTimingTriplet | None = None
            clock_to_output_fall: SDFTimingTriplet | None = None
            if register_clock_pin is not None:
                if register_clock_pin not in clock_paths:
                    clock_paths[register_clock_pin] = (
                        self._first_structural_timing_path(
                            clock_pin,
                            register_clock_pin,
                        )
                    )
                register_clock_path: SDFPathTiming | None = clock_paths[
                    register_clock_pin
                ]
                if register_clock_path is not None:
                    effective_setup, effective_hold = self._effective_timing_checks(
                        path_timing,
                        register_clock_path,
                    )
                    timing_check_index: int = next(
                        index
                        for index, component in enumerate(path_timing.components)
                        if component.is_timing_check
                    )
                    clock_to_output_components: tuple[Component, ...] = (
                        *register_clock_path.components,
                        *path_timing.components[timing_check_index + 1 :],
                    )
                    rise_values, fall_values, _ = self._transition_delays(
                        clock_to_output_components
                    )
                    clock_to_output_rise = self._sum_timing_triplets(rise_values)
                    clock_to_output_fall = self._sum_timing_triplets(fall_values)

            clocked_path_timings.append(
                replace(
                    path_timing,
                    effective_setup=effective_setup,
                    effective_hold=effective_hold,
                    clock_to_output_rise=clock_to_output_rise,
                    clock_to_output_fall=clock_to_output_fall,
                )
            )

        return clocked_path_timings

    def _query_structural_timing_paths(
        self,
        source: str,
        target: str,
        max_paths: int,
    ) -> list[SDFPathTiming]:
        """Find and decode structural paths without clock-dependent calculations.

        Parameters
        ----------
        source : str
            Source graph node.
        target : str
            Target graph node.
        max_paths : int
            Maximum number of shortest simple paths to decode.

        Returns
        -------
        list[SDFPathTiming]
            Decoded paths ordered by increasing edge count.
        """
        path_generator = nx.shortest_simple_paths(
            self.graph,
            source=source,
            target=target,
            weight=None,
        )
        node_paths: list[list[str]] = list(islice(path_generator, max_paths))
        return [
            self._decode_timing_path(node_path, self._sequential_instances)
            for node_path in node_paths
        ]

    @cached_property
    def _sequential_instances(self) -> frozenset[str]:
        """Return SDF instances containing sequential timing checks.

        Returns
        -------
        frozenset[str]
            Instance names containing setup or hold timing checks.
        """
        return frozenset(
            instance_name
            for instance_name, instance_components in self.instances.items()
            if any(
                component.c_type in {SDFCellType.SETUP, SDFCellType.HOLD}
                for component in instance_components
            )
        )

    def _first_structural_timing_path(
        self,
        source: str,
        target: str,
    ) -> SDFPathTiming | None:
        """Return the first structural timing path between two graph nodes.

        Parameters
        ----------
        source : str
            Source graph node.
        target : str
            Target graph node.

        Returns
        -------
        SDFPathTiming | None
            First path ordered by edge count, or `None` when no path exists.

        Notes
        -----
        NetworkX `NodeNotFound` errors remain visible to identify invalid caller input.
        """
        try:
            paths: list[SDFPathTiming] = self._query_structural_timing_paths(
                source,
                target,
                max_paths=1,
            )
        except nx.NetworkXNoPath:
            return None
        return paths[0] if paths else None

    def _decode_timing_path(
        self,
        node_path: list[str],
        sequential_instances: frozenset[str],
    ) -> SDFPathTiming:
        """Decode one graph-node path into its complete structural timing data.

        Parameters
        ----------
        node_path : list[str]
            Ordered graph nodes forming the path.
        sequential_instances : frozenset[str]
            SDF instances containing setup or hold timing checks.

        Returns
        -------
        SDFPathTiming
            Structural propagation, timing-check, and path classification data.
        """
        components: list[Component] = [
            self.graph.edges[path_source, path_target]["component"]
            for path_source, path_target in pairwise(node_path)
        ]
        rise_values, fall_values, high_impedance_values = self._transition_delays(
            components
        )
        high_impedance: SDFTimingTriplet | None = None
        if all(value is not None for value in high_impedance_values):
            high_impedance = self._sum_timing_triplets(
                [value for value in high_impedance_values if value is not None]
            )

        timing_checks: list[Component] = self._path_timing_checks(components)
        setup: tuple[SDFTimingTriplet, ...] = tuple(
            self._timing_triplet(component.delay_paths["nominal"])
            for component in timing_checks
            if component.c_type == SDFCellType.SETUP
        )
        hold: tuple[SDFTimingTriplet, ...] = tuple(
            self._timing_triplet(component.delay_paths["nominal"])
            for component in timing_checks
            if component.c_type == SDFCellType.HOLD
        )
        timing_check_index: int | None = next(
            (
                index
                for index, component in enumerate(components)
                if component.is_timing_check
            ),
            None,
        )
        register_clock_pin: str | None = (
            node_path[timing_check_index + 1]
            if timing_check_index is not None
            else None
        )
        is_sequential: bool = any(
            component.is_timing_check
            or (
                component.c_type == SDFCellType.IOPATH
                and component.from_cell_instance == component.to_cell_instance
                and component.from_cell_instance in sequential_instances
            )
            for component in components
        )
        conditions: tuple[str, ...] = tuple(
            dict.fromkeys(
                component.cond_equation
                for component in [*components, *timing_checks]
                if component.is_cond and component.cond_equation is not None
            )
        )
        return SDFPathTiming(
            nodes=tuple(node_path),
            components=tuple(components),
            path_type=(
                SDFPathType.SEQUENTIAL if is_sequential else SDFPathType.COMBINATIONAL
            ),
            rise=self._sum_timing_triplets(rise_values),
            fall=self._sum_timing_triplets(fall_values),
            high_impedance=high_impedance,
            setup=setup,
            hold=hold,
            timing_checks=tuple(timing_checks),
            conditions=conditions,
            register_clock_pin=register_clock_pin,
        )

    def _transition_delays(
        self,
        components: list[Component] | tuple[Component, ...],
    ) -> tuple[
        list[SDFTimingTriplet],
        list[SDFTimingTriplet],
        list[SDFTimingTriplet | None],
    ]:
        """Decode transition delays for an ordered collection of SDF components.

        Parameters
        ----------
        components : list[Component] | tuple[Component, ...]
            Ordered path components.

        Returns
        -------
        rise_values : list[SDFTimingTriplet]
            Per-component rising-transition delays.
        fall_values : list[SDFTimingTriplet]
            Per-component falling-transition delays.
        high_impedance_values : list[SDFTimingTriplet | None]
            Per-component high-impedance delays when available.

        Raises
        ------
        ValueError
            If a component contains an unsupported delay-path shape.
        """
        rise_values: list[SDFTimingTriplet] = []
        fall_values: list[SDFTimingTriplet] = []
        high_impedance_values: list[SDFTimingTriplet | None] = []
        zero_delay = SDFTimingTriplet(minimum=0.0, typical=0.0, maximum=0.0)
        for component in components:
            if component.delay_paths is None:
                rise_values.append(zero_delay)
                fall_values.append(zero_delay)
                high_impedance_values.append(zero_delay)
                continue

            delay_path_keys: set[str] = set(component.delay_paths)
            if delay_path_keys == {"nominal"}:
                rise_delay = self._timing_triplet(component.delay_paths["nominal"])
                fall_delay = rise_delay
                high_impedance_delay: SDFTimingTriplet | None = rise_delay
            elif delay_path_keys == {"fast", "slow"}:
                rise_delay = self._timing_triplet(component.delay_paths["fast"])
                fall_delay = self._timing_triplet(component.delay_paths["slow"])
                high_impedance_delay = None
            elif delay_path_keys == {"fast", "nominal", "slow"}:
                rise_delay = self._timing_triplet(component.delay_paths["fast"])
                fall_delay = self._timing_triplet(component.delay_paths["nominal"])
                high_impedance_delay = self._timing_triplet(
                    component.delay_paths["slow"]
                )
            else:
                raise ValueError(
                    f"Unsupported SDF delay-path shape {delay_path_keys!r} for "
                    f"component {component.connection_string!r}."
                )
            rise_values.append(rise_delay)
            fall_values.append(fall_delay)
            high_impedance_values.append(high_impedance_delay)
        return rise_values, fall_values, high_impedance_values

    def _path_timing_checks(self, components: list[Component]) -> list[Component]:
        """Find setup and hold checks associated with a structural path.

        Parameters
        ----------
        components : list[Component]
            Ordered path components.

        Returns
        -------
        list[Component]
            Unique SDF setup and hold components in encounter order.
        """
        timing_checks: list[Component] = []
        for component in components:
            if not component.is_timing_check:
                continue
            for timing_check in self.instances.get(component.from_cell_instance, []):
                if (
                    timing_check.c_type in {SDFCellType.SETUP, SDFCellType.HOLD}
                    and timing_check.from_cell_pin == component.to_cell_pin
                    and timing_check.to_cell_pin == component.from_cell_pin
                    and timing_check not in timing_checks
                ):
                    timing_checks.append(timing_check)
        return timing_checks

    def _effective_timing_checks(
        self,
        data_path: SDFPathTiming,
        clock_path: SDFPathTiming,
    ) -> tuple[tuple[SDFTimingTriplet, ...], tuple[SDFTimingTriplet, ...]]:
        """Adjust cell setup and hold checks for data and clock path delays.

        Parameters
        ----------
        data_path : SDFPathTiming
            Sequential path containing the data propagation and cell timing checks.
        clock_path : SDFPathTiming
            Path from the requested clock source to the register clock pin.

        Returns
        -------
        tuple[tuple[SDFTimingTriplet, ...], tuple[SDFTimingTriplet, ...]]
            Effective setup and hold timing triples.
        """
        timing_check_index: int = next(
            index
            for index, component in enumerate(data_path.components)
            if component.is_timing_check
        )
        data_rise_values, data_fall_values, _ = self._transition_delays(
            data_path.components[:timing_check_index]
        )
        data_rise: SDFTimingTriplet = self._sum_timing_triplets(data_rise_values)
        data_fall: SDFTimingTriplet = self._sum_timing_triplets(data_fall_values)
        (
            data_minimum,
            data_typical_minimum,
            data_typical_maximum,
            data_maximum,
        ) = self._transition_extremes(data_rise, data_fall)
        (
            clock_minimum,
            clock_typical_minimum,
            clock_typical_maximum,
            clock_maximum,
        ) = self._transition_extremes(clock_path.rise, clock_path.fall)

        effective_setup: tuple[SDFTimingTriplet, ...] = tuple(
            SDFTimingTriplet(
                minimum=self._sum_and_subtract(
                    data_minimum,
                    cell_setup.minimum,
                    clock_maximum,
                ),
                typical=self._sum_and_subtract(
                    data_typical_maximum,
                    cell_setup.typical,
                    clock_typical_minimum,
                ),
                maximum=self._sum_and_subtract(
                    data_maximum,
                    cell_setup.maximum,
                    clock_minimum,
                ),
            )
            for cell_setup in data_path.setup
        )
        effective_hold: tuple[SDFTimingTriplet, ...] = tuple(
            SDFTimingTriplet(
                minimum=self._sum_and_subtract(
                    cell_hold.minimum,
                    clock_minimum,
                    data_maximum,
                ),
                typical=self._sum_and_subtract(
                    cell_hold.typical,
                    clock_typical_maximum,
                    data_typical_minimum,
                ),
                maximum=self._sum_and_subtract(
                    cell_hold.maximum,
                    clock_maximum,
                    data_minimum,
                ),
            )
            for cell_hold in data_path.hold
        )
        return effective_setup, effective_hold

    def _timing_triplet(
        self,
        delay_values: dict[str, float | None],
    ) -> SDFTimingTriplet:
        """Convert one parser delay triple into the public timing model.

        Parameters
        ----------
        delay_values : dict[str, float | None]
            Parser dictionary containing `min`, `avg`, and `max` values.

        Returns
        -------
        SDFTimingTriplet
            Normalized minimum, typical, and maximum delay values.
        """
        return SDFTimingTriplet(
            minimum=delay_values.get("min"),
            typical=delay_values.get("avg"),
            maximum=delay_values.get("max"),
        )

    def _sum_timing_triplets(
        self,
        values: list[SDFTimingTriplet],
    ) -> SDFTimingTriplet:
        """Sum timing triples while preserving unavailable SDF values.

        Parameters
        ----------
        values : list[SDFTimingTriplet]
            Timing triples for the ordered components of one path.

        Returns
        -------
        SDFTimingTriplet
            Component-wise path sum. A field remains `None` if any traversed
            component does not provide that field.
        """
        minimum_values: list[float | None] = [value.minimum for value in values]
        typical_values: list[float | None] = [value.typical for value in values]
        maximum_values: list[float | None] = [value.maximum for value in values]
        return SDFTimingTriplet(
            minimum=(
                sum(value for value in minimum_values if value is not None)
                if all(value is not None for value in minimum_values)
                else None
            ),
            typical=(
                sum(value for value in typical_values if value is not None)
                if all(value is not None for value in typical_values)
                else None
            ),
            maximum=(
                sum(value for value in maximum_values if value is not None)
                if all(value is not None for value in maximum_values)
                else None
            ),
        )

    def _transition_extremes(
        self,
        rise: SDFTimingTriplet,
        fall: SDFTimingTriplet,
    ) -> tuple[float | None, float | None, float | None, float | None]:
        """Return conservative extrema across rise and fall transitions.

        Parameters
        ----------
        rise : SDFTimingTriplet
            Rising-transition timing values.
        fall : SDFTimingTriplet
            Falling-transition timing values.

        Returns
        -------
        tuple[float | None, float | None, float | None, float | None]
            Minimum, typical minimum, typical maximum, and maximum values. An
            extremum is `None` when either transition does not provide that corner.
        """
        minimum: float | None = (
            min(rise.minimum, fall.minimum)
            if rise.minimum is not None and fall.minimum is not None
            else None
        )
        typical_minimum: float | None = (
            min(rise.typical, fall.typical)
            if rise.typical is not None and fall.typical is not None
            else None
        )
        typical_maximum: float | None = (
            max(rise.typical, fall.typical)
            if rise.typical is not None and fall.typical is not None
            else None
        )
        maximum: float | None = (
            max(rise.maximum, fall.maximum)
            if rise.maximum is not None and fall.maximum is not None
            else None
        )
        return minimum, typical_minimum, typical_maximum, maximum

    def _sum_and_subtract(
        self,
        first_addend: float | None,
        second_addend: float | None,
        subtrahend: float | None,
    ) -> float | None:
        """Add two timing values and subtract a third when all are available.

        Parameters
        ----------
        first_addend : float | None
            First value to add.
        second_addend : float | None
            Second value to add.
        subtrahend : float | None
            Value to subtract.

        Returns
        -------
        float | None
            Calculated value, or `None` when any operand is unavailable.
        """
        if first_addend is None or second_addend is None or subtrahend is None:
            return None
        return first_addend + second_addend - subtrahend

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

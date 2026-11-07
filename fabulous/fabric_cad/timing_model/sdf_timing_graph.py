"""Timing graph built from an SDF file.

This module is the only user of `sdf_toolkit`. It parses the SDF, turns its IOPATH and
INTERCONNECT entries into a `networkx` graph of pins, and answers the path queries the
FABulous timing model needs. `sdf_toolkit` parses SDF numbers as `float`; each one is
converted to `Decimal` here, once, so all timing arithmetic is exact.
"""

from copy import copy
from dataclasses import dataclass, replace
from decimal import Decimal
from enum import StrEnum
from functools import cached_property
from itertools import islice, pairwise
from math import isclose
from pathlib import Path
from typing import Self

import networkx as nx
from loguru import logger
from sdf_toolkit import parse_sdf_file
from sdf_toolkit.core.model import BaseEntry, DelayPaths, EntryType, Values

from fabulous.fabric_cad.timing_db import ns


class SDFCellType(StrEnum):
    """Enumeration of cell types for the SDF timing model.

    Includes INTERCONNECT and IOPATH for the timing graph, as well
    as other types like REMOVAL, RECOVERY, SETUP, HOLD, WIDTH.

    Attributes
    ----------
    IOPATH
        Represents an IOPATH component, which defines timing paths between
        pins within the same cell.
    INTERCONNECT
        Represents an INTERCONNECT component, which defines timing paths
        between pins across
        different cells (i.e., inter-cell connections).
    REMOVAL
        Represents a REMOVAL component, which defines timing checks for
        signal removal.
    RECOVERY
        Represents a RECOVERY component, which defines timing checks for
        signal recovery.
    SETUP
        Represents a SETUP component, which defines timing checks for
        setup time.
    HOLD
        Represents a HOLD component, which defines timing checks for
        hold time.
    WIDTH
        Represents a WIDTH component, which defines timing checks for
        pulse width.
    """

    IOPATH = "IOPATH"
    INTERCONNECT = "INTERCONNECT"
    REMOVAL = "REMOVAL"
    RECOVERY = "RECOVERY"
    SETUP = "SETUP"
    HOLD = "HOLD"
    WIDTH = "WIDTH"


@dataclass(frozen=True, slots=True)
class SDFTimingTriplet:
    """Represent the minimum, typical, and maximum values of an SDF delay.

    Attributes
    ----------
    minimum : Decimal | None
        Minimum delay, or `None` when the SDF does not provide it.
    typical : Decimal | None
        Typical delay, called `avg` by the current SDF parser, or `None` when
        the SDF does not provide it.
    maximum : Decimal | None
        Maximum delay, or `None` when the SDF does not provide it.
    """

    minimum: Decimal | None
    typical: Decimal | None
    maximum: Decimal | None


@dataclass(frozen=True, slots=True)
class SDFDelayPaths:
    """Hold the delay triples of one SDF entry as the SDF lists them.

    One triple is stored as `nominal`, two as `fast` and `slow`, and three as
    `fast`, `nominal` and `slow`. Timing checks store their limit as `nominal`.

    Attributes
    ----------
    nominal : SDFTimingTriplet | None
        The only triple, or the second of three.
    fast : SDFTimingTriplet | None
        The first of two or three triples.
    slow : SDFTimingTriplet | None
        The last of two or three triples.
    """

    nominal: SDFTimingTriplet | None
    fast: SDFTimingTriplet | None
    slow: SDFTimingTriplet | None


@dataclass(frozen=True)
class Component:
    """Represents a component in the SDF timing model.

    Its either an INTERCONNECT or an IOPATH for the timing graph.
    But it can also be: REMOVAL, RECOVERY, SETUP, HOLD, WIDTH.

    Attributes
    ----------
    c_type : SDFCellType
        Type of the component, either "INTERCONNECT" or "IOPATH"
        for the timing graph.
        Other types include: "REMOVAL", "RECOVERY", "SETUP", "HOLD", "WIDTH".
    connection_string : str
        Unique identifier for the component.
    cell_name : str
        Name of the cell e.g., 'AND2X1'.
    from_cell_instance : str
        Instance name of the source cell.
    to_cell_instance : str
        Instance name of the destination cell.
    from_cell_pin : str
        Pin name on the source cell.
    to_cell_pin : str
        Pin name on the destination cell.
    delay : Decimal
        Delay associated with this component: INTERCONNECT delay: cell to cell delay,
        IOPATH delay: pin to pin delay within a cell.
        Is a single delay over fast, slow (min, max)
        by using a cost function to combine them.
    delay_paths : SDFDelayPaths | None
        Delay triples as written in the SDF, or `None` for the synthetic
        data-to-clock edge of a timing check.
    is_one_cell_instance : bool
        True if from_cell_instance and to_cell_instance are the same.
    is_timing_check : bool
        True if the component represents a timing check.
    is_timing_env : bool
        True if the component represents a timing environment.
    is_absolute : bool
        True if the delay is absolute.
    is_incremental : bool
        True if the delay is incremental.
    is_cond : bool
        True if the delay is conditional.
    cond_equation : str | None
        Condition equation if is_cond is True.
    from_pin_edge : str | None
        Edge type for the from pin, e.g., "posedge" or "negedge".
    to_pin_edge : str | None
        Edge type for the to pin, e.g., "posedge" or "negedge".
    """

    c_type: SDFCellType
    connection_string: str
    cell_name: str
    from_cell_instance: str
    to_cell_instance: str
    from_cell_pin: str
    to_cell_pin: str
    delay: Decimal
    delay_paths: SDFDelayPaths | None
    is_one_cell_instance: bool
    is_timing_check: bool
    is_timing_env: bool
    is_absolute: bool
    is_incremental: bool
    is_cond: bool
    cond_equation: str | None
    from_pin_edge: str | None
    to_pin_edge: str | None


class DelayType(StrEnum):
    """Enumeration of delay types for the SDF timing model.

    Includes various combinations of min, max, avg, fast, and slow delays.

    Attributes
    ----------
    MIN_ALL
        Represents the minimum delay across all conditions.
    MAX_ALL
        Represents the maximum delay across all conditions.
    AVG_ALL
        Represents the average delay across all conditions.
    AVG_FAST
        Represents the average delay under fast conditions.
    AVG_SLOW
        Represents the average delay under slow conditions.
    MAX_FAST
        Represents the maximum delay under fast conditions.
    MAX_SLOW
        Represents the maximum delay under slow conditions.
    MIN_FAST
        Represents the minimum delay under fast conditions.
    MIN_SLOW
        Represents the minimum delay under slow conditions.
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


class SDFPathType(StrEnum):
    """Classify an SDF timing path by its sequential behavior.

    Attributes
    ----------
    COMBINATIONAL
        The path contains only combinational timing components.
    SEQUENTIAL
        The path crosses a sequential cell or synthetic timing-check edge.
    """

    COMBINATIONAL = "combinational"
    SEQUENTIAL = "sequential"


@dataclass(frozen=True, slots=True)
class SDFPathTiming:
    """Collect the complete timing information for one structural graph path.

    Attributes
    ----------
    nodes : tuple[str, ...]
        Ordered graph nodes forming the path.
    components : tuple[Component, ...]
        Ordered SDF components forming the path edges.
    path_type : SDFPathType
        Whether the path is combinational or sequential.
    rise : SDFTimingTriplet
        Aggregated rising-transition propagation delay.
    fall : SDFTimingTriplet
        Aggregated falling-transition propagation delay.
    high_impedance : SDFTimingTriplet | None
        Aggregated high-impedance transition delay when it can be derived for every
        component on the path.
    setup : tuple[SDFTimingTriplet, ...]
        Setup checks associated with sequential edges on the path.
    hold : tuple[SDFTimingTriplet, ...]
        Hold checks associated with sequential edges on the path.
    timing_checks : tuple[Component, ...]
        Original SDF timing-check components associated with the path.
    conditions : tuple[str, ...]
        Ordered, unique SDF conditions affecting the path or its timing checks.
    register_clock_pin : str | None
        Graph pin at the register clock reached by the first timing-check edge.
    effective_setup : tuple[SDFTimingTriplet, ...]
        Setup constraints adjusted for the data and clock paths. Empty when no
        `clock_pin` was supplied to the path query or its clock path is unavailable.
    effective_hold : tuple[SDFTimingTriplet, ...]
        Hold constraints adjusted for the data and clock paths. Empty when no
        `clock_pin` was supplied to the path query or its clock path is unavailable.
    clock_to_output_rise : SDFTimingTriplet | None
        Rising clock-to-target propagation delay from the supplied clock pin.
    clock_to_output_fall : SDFTimingTriplet | None
        Falling clock-to-target propagation delay from the supplied clock pin.
    """

    nodes: tuple[str, ...]
    components: tuple[Component, ...]
    path_type: SDFPathType
    rise: SDFTimingTriplet
    fall: SDFTimingTriplet
    high_impedance: SDFTimingTriplet | None = None
    setup: tuple[SDFTimingTriplet, ...] = ()
    hold: tuple[SDFTimingTriplet, ...] = ()
    timing_checks: tuple[Component, ...] = ()
    conditions: tuple[str, ...] = ()
    register_clock_pin: str | None = None
    effective_setup: tuple[SDFTimingTriplet, ...] = ()
    effective_hold: tuple[SDFTimingTriplet, ...] = ()
    clock_to_output_rise: SDFTimingTriplet | None = None
    clock_to_output_fall: SDFTimingTriplet | None = None


def _triplet(values: Values | None) -> SDFTimingTriplet | None:
    """Convert an `sdf_toolkit` value triple into the timing model's triple."""
    if values is None:
        return None
    return SDFTimingTriplet(
        minimum=None if values.min is None else ns(values.min),
        typical=None if values.avg is None else ns(values.avg),
        maximum=None if values.max is None else ns(values.max),
    )


def _delay_paths(delay_paths: DelayPaths) -> SDFDelayPaths:
    """Keep the nominal, fast and slow triples of one SDF entry."""
    return SDFDelayPaths(
        nominal=_triplet(delay_paths.nominal),
        fast=_triplet(delay_paths.fast),
        slow=_triplet(delay_paths.slow),
    )


def _scalar_delay(delay_paths: SDFDelayPaths, kind: DelayType) -> Decimal:
    """Reduce the delay triples of one entry to the graph edge weight.

    A nominal triple gives the larger of its minimum and maximum. Otherwise the fast
    and slow triples are combined as `kind` selects. Missing values count as zero.

    Parameters
    ----------
    delay_paths : SDFDelayPaths
        Delay triples of the entry.
    kind : DelayType
        Combination of the fast and slow triples.

    Returns
    -------
    Decimal
        The edge weight.

    Raises
    ------
    ValueError
        If `kind` is not a known delay type.
    """
    empty = SDFTimingTriplet(minimum=None, typical=None, maximum=None)
    if delay_paths.nominal is not None:
        return max(
            delay_paths.nominal.minimum or Decimal(0),
            delay_paths.nominal.maximum or Decimal(0),
        )

    fast = delay_paths.fast or empty
    slow = delay_paths.slow or empty
    fast_min = fast.minimum or Decimal(0)
    fast_max = fast.maximum or Decimal(0)
    slow_min = slow.minimum or Decimal(0)
    slow_max = slow.maximum or Decimal(0)

    match kind:
        case DelayType.MIN_ALL:
            return min(fast_min, fast_max, slow_min, slow_max)
        case DelayType.MAX_ALL:
            return max(fast_min, fast_max, slow_min, slow_max)
        case DelayType.AVG_ALL:
            return (fast_min + fast_max + slow_min + slow_max) / 4
        case DelayType.AVG_FAST:
            return (fast_min + fast_max) / 2
        case DelayType.AVG_SLOW:
            return (slow_min + slow_max) / 2
        case DelayType.MAX_FAST:
            return max(fast_min, fast_max)
        case DelayType.MAX_SLOW:
            return max(slow_min, slow_max)
        case DelayType.MIN_FAST:
            return min(fast_min, fast_max)
        case DelayType.MIN_SLOW:
            return min(slow_min, slow_max)
        case _:
            raise ValueError(f"Unknown delay type: {kind!r}")


def _check_limit(check: Component) -> SDFTimingTriplet:
    """Return the limit of a setup or hold check, which the SDF gives as one triple.

    Parameters
    ----------
    check : Component
        A SETUP or HOLD entry.

    Returns
    -------
    SDFTimingTriplet
        The check limit.

    Raises
    ------
    ValueError
        If the check has no single limit triple.
    """
    if check.delay_paths is None or check.delay_paths.nominal is None:
        raise ValueError(
            f"Timing check {check.connection_string!r} of {check.from_cell_instance!r} "
            "has no single limit value."
        )
    return check.delay_paths.nominal


class SdfTimingGraph:
    """Timing graph of an SDF file, with path queries for timing extraction.

    Each IOPATH and INTERCONNECT entry becomes an edge between hierarchical pin names.
    A SETUP or HOLD check also becomes a zero-delay edge from the data pin to the
    clock pin, so a path can cross a register from its data input through its
    clock-to-output arc. All entries of each instance, timing checks included, are
    kept in `instances`.

    Parameters
    ----------
    sdf_file : Path
        Path to the SDF file.
    delay_type : DelayType
        How the delay triples of an entry reduce to its edge weight.

    Attributes
    ----------
    graph : nx.DiGraph
        Pin graph. Each edge holds its `weight` and its `component`.
    reverse_graph : nx.DiGraph
        `graph` with every edge reversed.
    hier_sep : str
        Hierarchy divider of the SDF.
    instances : dict[str, list[Component]]
        All non-INTERCONNECT entries of each instance.
    input_ports : list[str]
        Top-level pins with no incoming edge.
    output_ports : list[str]
        Top-level pins with no outgoing edge.
    """

    graph: nx.DiGraph
    reverse_graph: nx.DiGraph
    hier_sep: str
    instances: dict[str, list[Component]]
    input_ports: list[str]
    output_ports: list[str]

    def __init__(
        self, sdf_file: Path, delay_type: DelayType = DelayType.MAX_ALL
    ) -> None:
        sdf = parse_sdf_file(sdf_file)
        self.hier_sep = sdf.header.divider or "/"
        self.instances = {}
        # Cell edges go in before interconnect edges; the node and edge order this
        # gives decides which of several equally short paths a query returns first.
        cell_edges: list[Component] = []
        interconnects: list[Component] = []
        for cell_name, cell_instances in sdf.cells.items():
            for instance_name, entries in cell_instances.items():
                self.instances[instance_name] = []
                for entry_name, entry in entries.items():
                    component = self._component(
                        entry=entry,
                        entry_name=entry_name,
                        cell_name=cell_name,
                        instance_name=instance_name,
                        delay_type=delay_type,
                    )
                    if entry.type == EntryType.INTERCONNECT:
                        interconnects.append(component)
                        continue
                    self.instances[instance_name].append(component)
                    if entry.type == EntryType.IOPATH:
                        cell_edges.append(component)
                    elif entry.type in (EntryType.SETUP, EntryType.HOLD):
                        # A check runs from the clock to the data pin. The edge
                        # runs from data to clock and carries no delay, so the
                        # path continues through the clock-to-output IOPATH.
                        cell_edges.append(
                            replace(
                                component,
                                c_type=SDFCellType.IOPATH,
                                connection_string=entry_name.split("_", 1)[-1],
                                from_cell_pin=component.to_cell_pin,
                                to_cell_pin=component.from_cell_pin,
                                delay=Decimal(0),
                                delay_paths=None,
                                from_pin_edge=None,
                                to_pin_edge=None,
                            )
                        )

        self.graph = nx.DiGraph()
        for component in [*cell_edges, *interconnects]:
            self.graph.add_edge(
                self._node(component.from_cell_instance, component.from_cell_pin),
                self._node(component.to_cell_instance, component.to_cell_pin),
                weight=component.delay,
                component=component,
            )
        self.reverse_graph = self.graph.reverse(copy=True)
        self.input_ports = list(
            {
                node
                for node in self.graph.nodes
                if self.graph.in_degree(node) == 0 and self.hier_sep not in node
            }
        )
        self.output_ports = list(
            {
                node
                for node in self.graph.nodes
                if self.graph.out_degree(node) == 0 and self.hier_sep not in node
            }
        )

    def _component(
        self,
        *,
        entry: BaseEntry,
        entry_name: str,
        cell_name: str,
        instance_name: str,
        delay_type: DelayType,
    ) -> Component:
        """Convert one parsed SDF entry into a timing model component.

        Parameters
        ----------
        entry : BaseEntry
            Parsed SDF entry.
        entry_name : str
            Unique name of the entry within its instance.
        cell_name : str
            Cell type of the instance.
        instance_name : str
            Instance holding the entry, empty for the top cell.
        delay_type : DelayType
            How the delay triples reduce to the edge weight.

        Returns
        -------
        Component
            The entry with typed delays. INTERCONNECT pins are split into instance
            and pin at the last hierarchy divider.

        Raises
        ------
        ValueError
            If the entry has no pins or no delays, or its type is not one the timing
            model handles.
        """
        if entry.from_pin is None or entry.to_pin is None:
            raise ValueError(
                f"SDF entry {entry_name!r} of instance {instance_name!r} has no pins."
            )
        if entry.delay_paths is None:
            raise ValueError(
                f"SDF entry {entry_name!r} of instance {instance_name!r} has no delays."
            )
        if entry.type == EntryType.INTERCONNECT:
            from_instance, _, from_pin = entry.from_pin.rpartition(self.hier_sep)
            to_instance, _, to_pin = entry.to_pin.rpartition(self.hier_sep)
        else:
            from_instance, from_pin = instance_name, entry.from_pin
            to_instance, to_pin = instance_name, entry.to_pin
        delay_paths = _delay_paths(entry.delay_paths)
        return Component(
            c_type=SDFCellType(entry.type.value.upper()),
            cell_name=cell_name,
            connection_string=entry_name,
            from_cell_instance=from_instance,
            to_cell_instance=to_instance,
            from_cell_pin=from_pin,
            to_cell_pin=to_pin,
            delay=_scalar_delay(delay_paths, delay_type),
            delay_paths=delay_paths,
            is_one_cell_instance=from_instance == to_instance,
            is_timing_check=entry.is_timing_check,
            is_timing_env=entry.is_timing_env,
            is_absolute=entry.is_absolute,
            is_incremental=entry.is_incremental,
            is_cond=entry.is_cond,
            cond_equation=entry.cond_equation,
            from_pin_edge=None
            if entry.from_pin_edge is None
            else entry.from_pin_edge.value,
            to_pin_edge=None if entry.to_pin_edge is None else entry.to_pin_edge.value,
        )

    def _node(self, instance: str, pin: str) -> str:
        """Return the graph node of a pin, which is the pin alone at the top level."""
        return f"{instance}{self.hier_sep}{pin}".removeprefix(self.hier_sep)

    def within(self, prefix: str) -> Self:
        """Return a copy whose graphs keep only the pins under `prefix`.

        `instances` and the ports are shared with this graph, which is left
        unchanged.

        Parameters
        ----------
        prefix : str
            Hierarchical name prefix, such as `Inst_LA_LUT4c_frame_config_dffesr/`.

        Returns
        -------
        Self
            The restricted graph.
        """
        view = copy(self)
        # Filter rather than call `subgraph()`: its node set would make the order
        # of query results follow the string hash seed.
        view.graph = nx.subgraph_view(
            self.graph, filter_node=lambda pin: pin.startswith(prefix)
        ).copy()
        view.reverse_graph = view.graph.reverse(copy=True)
        for cached_view in ("clock_graph", "combinational_graph"):
            view.__dict__.pop(cached_view, None)
        return view

    def with_ports(
        self,
        *,
        inputs: dict[str, dict[str, Component | None]],
        outputs: dict[str, dict[str, Component | None]],
    ) -> Self:
        """Return a copy with the given port nodes as its only ports.

        Each port edge stands for the wire it is given, retargeted to the port
        node, so its weight and delays are that wire's. A port edge given no
        wire has zero delay.

        Parameters
        ----------
        inputs : dict[str, dict[str, Component | None]]
            Each input port, to the pins it drives and the wire into each.
        outputs : dict[str, dict[str, Component | None]]
            Each output port, to the pins that drive it and the wire out of each.

        Returns
        -------
        Self
            The graph with the port nodes.

        Raises
        ------
        ValueError
            If a port is already a node or is named twice, or a port edge
            touches a pin that is not in the graph.
        """
        view = copy(self)
        view.graph = self.graph.copy()
        for port in [*inputs, *outputs]:
            if port in view.graph or (port in inputs and port in outputs):
                raise ValueError(f"Port {port!r} is already a node of the graph.")
        for direction in (inputs, outputs):
            for port, pins in direction.items():
                for pin, wire in pins.items():
                    if pin not in self.graph:
                        raise ValueError(
                            f"Pin {pin!r} of port {port!r} is not in the graph."
                        )
                    instance, _, pin_name = pin.rpartition(self.hier_sep)
                    ends = ((instance, pin_name), ("", port))
                    source, sink = ends[::-1] if direction is inputs else ends
                    component = self._port_wire(wire, source=source, sink=sink)
                    view.graph.add_edge(
                        self._node(*source),
                        self._node(*sink),
                        weight=component.delay,
                        component=component,
                    )
        view.reverse_graph = view.graph.reverse(copy=True)
        view.input_ports = list(inputs)
        view.output_ports = list(outputs)
        for cached_view in ("clock_graph", "combinational_graph"):
            view.__dict__.pop(cached_view, None)
        return view

    @staticmethod
    def _port_wire(
        wire: Component | None,
        *,
        source: tuple[str, str],
        sink: tuple[str, str],
    ) -> Component:
        """Return the INTERCONNECT of a port edge from `source` to `sink`.

        Parameters
        ----------
        wire : Component | None
            The wire the edge stands for, or `None` for a zero-delay edge.
        source : tuple[str, str]
            Instance and pin the edge starts at.
        sink : tuple[str, str]
            Instance and pin the edge ends at.

        Returns
        -------
        Component
            The wire with the given ends.
        """
        (from_instance, from_pin), (to_instance, to_pin) = source, sink
        if wire is None:
            wire = Component(
                c_type=SDFCellType.INTERCONNECT,
                connection_string="",
                cell_name="",
                from_cell_instance=from_instance,
                to_cell_instance=to_instance,
                from_cell_pin=from_pin,
                to_cell_pin=to_pin,
                delay=Decimal(0),
                delay_paths=None,
                is_one_cell_instance=False,
                is_timing_check=False,
                is_timing_env=False,
                is_absolute=True,
                is_incremental=False,
                is_cond=False,
                cond_equation=None,
                from_pin_edge=None,
                to_pin_edge=None,
            )
        return replace(
            wire,
            connection_string=f"{from_pin} {to_pin}",
            from_cell_instance=from_instance,
            from_cell_pin=from_pin,
            to_cell_instance=to_instance,
            to_cell_pin=to_pin,
            is_one_cell_instance=from_instance == to_instance,
        )

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
        """
        return nx.has_path(self.graph, source=source, target=target)

    def single_delay(self, source: str, target: str) -> Decimal:
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
        Decimal
            The total delay between the source and target nodes.

        Examples
        --------
            length = sdf_graph.single_delay("nodeA/pin", "nodeB/pin")
        """
        logger.warning(
            "single_delay() is deprecated. Use query_timing_paths() instead."
        )
        length: Decimal | int = nx.dijkstra_path_length(
            self.graph, source=source, target=target, weight="weight"
        )
        # networkx returns the int 0 for an empty path. Adding to Decimal(0) gives a
        # Decimal and raises TypeError on a float weight.
        return Decimal(0) + length

    def query_timing_paths(
        self,
        source: str,
        target: str,
        max_paths: int = 10,
        clock_pin: str | None = None,
        *,
        include_timing_checks: bool = True,
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
        standard-cell timing checks remain available separately. A direct
        clock-to-output path also reports clock-to-output propagation, without
        requiring a synthetic data-to-clock edge or producing setup/hold checks.

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
        include_timing_checks : bool
            Whether discovery may cross synthetic data-to-clock edges. Disable
            for clock-to-output queries so unrelated data paths cannot consume
            the bounded search results.

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

        path_timings: list[SDFPathTiming] = (
            self._query_structural_timing_paths(source, target, max_paths)
            if include_timing_checks
            else self.query_clock_paths(source, target, max_paths)
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
                    clock_paths[register_clock_pin] = self._first_clock_path(
                        clock_pin,
                        register_clock_pin,
                    )
                register_clock_path: SDFPathTiming | None = clock_paths[
                    register_clock_pin
                ]
                if register_clock_path is not None:
                    if any(
                        component.is_timing_check
                        for component in path_timing.components
                    ):
                        effective_setup, effective_hold = self._effective_timing_checks(
                            path_timing,
                            register_clock_path,
                        )
                    clock_index = path_timing.nodes.index(register_clock_pin)
                    clock_to_output_components: tuple[Component, ...] = (
                        *register_clock_path.components,
                        *path_timing.components[clock_index:],
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

    @cached_property
    def clock_graph(self) -> nx.DiGraph:
        """Return clock propagation, including integrated clock-gating cells.

        Returns
        -------
        nx.DiGraph
            A graph view without synthetic data-to-clock timing-check edges.
        """

        def include_edge(source: str, target: str) -> bool:
            """Keep physical propagation through buffers and clock gates."""
            return not self.graph.edges[source, target]["component"].is_timing_check

        return nx.subgraph_view(self.graph, filter_edge=include_edge)

    def query_clock_paths(
        self, source: str, target: str, max_paths: int = 10
    ) -> list[SDFPathTiming]:
        """Trace a clock without following synthetic data-to-clock edges.

        Parameters
        ----------
        source : str
            Clock source pin.
        target : str
            Clock destination pin.
        max_paths : int
            Maximum number of paths, ordered by edge count.

        Returns
        -------
        list[SDFPathTiming]
            Clock propagation paths, retaining clock-gate delays.

        Raises
        ------
        ValueError
            If `max_paths` is less than one.
        """
        if max_paths < 1:
            raise ValueError("max_paths must be at least 1.")
        paths = nx.shortest_simple_paths(self.clock_graph, source, target)
        return [
            self._decode_timing_path(path, self._sequential_instances)
            for path in islice(paths, max_paths)
        ]

    @cached_property
    def combinational_graph(self) -> nx.DiGraph:
        """Return the propagation graph with register boundaries removed.

        Returns
        -------
        nx.DiGraph
            A view excluding synthetic timing checks and sequential cell arcs.
        """

        def include_edge(source: str, target: str) -> bool:
            """Stop traversal at a register instead of crossing a clock boundary."""
            component = self.graph.edges[source, target]["component"]
            return not component.is_timing_check and not (
                component.c_type == SDFCellType.IOPATH
                and component.from_cell_instance in self._sequential_instances
            )

        return nx.subgraph_view(self.graph, filter_edge=include_edge)

    def query_combinational_paths(
        self, source: str, target: str, max_paths: int = 10
    ) -> list[SDFPathTiming]:
        """Query propagation paths without crossing a sequential cell.

        Parameters
        ----------
        source : str
            Source graph pin.
        target : str
            Target graph pin.
        max_paths : int
            Maximum number of paths, ordered by edge count.

        Returns
        -------
        list[SDFPathTiming]
            Combinational paths, including the zero-length path for identical pins.

        Raises
        ------
        ValueError
            If `max_paths` is less than one.
        """
        if max_paths < 1:
            raise ValueError("max_paths must be at least 1.")
        paths = nx.shortest_simple_paths(self.combinational_graph, source, target)
        return [
            self._decode_timing_path(path, self._sequential_instances)
            for path in islice(paths, max_paths)
        ]

    def query_register_input_timing(
        self,
        source: str,
        data_pin: str,
        register_clock_pin: str,
        clock_pin: str,
        max_paths: int = 10,
    ) -> list[SDFPathTiming]:
        """Characterize setup and hold independently of any register output.

        Parameters
        ----------
        source : str
            BEL data input resolved to a graph pin.
        data_pin : str
            Register pin with a setup or hold check.
        register_clock_pin : str
            Clock endpoint of that check.
        clock_pin : str
            BEL clock source, before any internal clock buffers.
        max_paths : int
            Maximum number of combinational data paths to characterize.

        Returns
        -------
        list[SDFPathTiming]
            Register input paths with effective setup and hold values.
        """
        clock_path = self.query_clock_paths(clock_pin, register_clock_pin, 1)[0]
        timings = []
        for data_path in self.query_combinational_paths(source, data_pin, max_paths):
            path = self._decode_timing_path(
                [*data_path.nodes, register_clock_pin], self._sequential_instances
            )
            setup, hold = self._effective_timing_checks(path, clock_path)
            timings.append(replace(path, effective_setup=setup, effective_hold=hold))
        return timings

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

    def _first_clock_path(
        self,
        source: str,
        target: str,
    ) -> SDFPathTiming | None:
        """Return the first clock path without crossing a synthetic timing check.

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
            paths: list[SDFPathTiming] = self.query_clock_paths(
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
            _check_limit(component)
            for component in timing_checks
            if component.c_type == SDFCellType.SETUP
        )
        hold: tuple[SDFTimingTriplet, ...] = tuple(
            _check_limit(component)
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
        if register_clock_pin is None:
            # A clock-to-Q query has no synthetic data-to-clock edge.
            register_clock_pin = next(
                (
                    node_path[index]
                    for index, component in enumerate(components)
                    if component.c_type == SDFCellType.IOPATH
                    and any(
                        check.c_type in {SDFCellType.SETUP, SDFCellType.HOLD}
                        and check.from_cell_pin == component.from_cell_pin
                        for check in self.instances.get(
                            component.from_cell_instance, []
                        )
                    )
                ),
                None,
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
        zero_delay = SDFTimingTriplet(
            minimum=Decimal(0), typical=Decimal(0), maximum=Decimal(0)
        )
        for component in components:
            if component.delay_paths is None:
                rise_values.append(zero_delay)
                fall_values.append(zero_delay)
                high_impedance_values.append(zero_delay)
                continue

            match component.delay_paths:
                case SDFDelayPaths(
                    nominal=SDFTimingTriplet() as nominal, fast=None, slow=None
                ):
                    rise_delay = nominal
                    fall_delay = nominal
                    high_impedance_delay: SDFTimingTriplet | None = nominal
                case SDFDelayPaths(
                    nominal=None,
                    fast=SDFTimingTriplet() as fast,
                    slow=SDFTimingTriplet() as slow,
                ):
                    rise_delay = fast
                    fall_delay = slow
                    high_impedance_delay = None
                case SDFDelayPaths(
                    nominal=SDFTimingTriplet() as nominal,
                    fast=SDFTimingTriplet() as fast,
                    slow=SDFTimingTriplet() as slow,
                ):
                    rise_delay = fast
                    fall_delay = nominal
                    high_impedance_delay = slow
                case _:
                    raise ValueError(
                        f"Unsupported SDF delay-path shape {component.delay_paths!r} "
                        f"for component {component.connection_string!r}."
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
        minimum_values: list[Decimal | None] = [value.minimum for value in values]
        typical_values: list[Decimal | None] = [value.typical for value in values]
        maximum_values: list[Decimal | None] = [value.maximum for value in values]
        return SDFTimingTriplet(
            minimum=(
                sum(
                    (value for value in minimum_values if value is not None),
                    start=Decimal(0),
                )
                if all(value is not None for value in minimum_values)
                else None
            ),
            typical=(
                sum(
                    (value for value in typical_values if value is not None),
                    start=Decimal(0),
                )
                if all(value is not None for value in typical_values)
                else None
            ),
            maximum=(
                sum(
                    (value for value in maximum_values if value is not None),
                    start=Decimal(0),
                )
                if all(value is not None for value in maximum_values)
                else None
            ),
        )

    def _transition_extremes(
        self,
        rise: SDFTimingTriplet,
        fall: SDFTimingTriplet,
    ) -> tuple[Decimal | None, Decimal | None, Decimal | None, Decimal | None]:
        """Return conservative extrema across rise and fall transitions.

        Parameters
        ----------
        rise : SDFTimingTriplet
            Rising-transition timing values.
        fall : SDFTimingTriplet
            Falling-transition timing values.

        Returns
        -------
        tuple[Decimal | None, Decimal | None, Decimal | None, Decimal | None]
            Minimum, typical minimum, typical maximum, and maximum values. An
            extremum is `None` when either transition does not provide that corner.
        """
        minimum: Decimal | None = (
            min(rise.minimum, fall.minimum)
            if rise.minimum is not None and fall.minimum is not None
            else None
        )
        typical_minimum: Decimal | None = (
            min(rise.typical, fall.typical)
            if rise.typical is not None and fall.typical is not None
            else None
        )
        typical_maximum: Decimal | None = (
            max(rise.typical, fall.typical)
            if rise.typical is not None and fall.typical is not None
            else None
        )
        maximum: Decimal | None = (
            max(rise.maximum, fall.maximum)
            if rise.maximum is not None and fall.maximum is not None
            else None
        )
        return minimum, typical_minimum, typical_maximum, maximum

    def _sum_and_subtract(
        self,
        first_addend: Decimal | None,
        second_addend: Decimal | None,
        subtrahend: Decimal | None,
    ) -> Decimal | None:
        """Add two timing values and subtract a third when all are available.

        Parameters
        ----------
        first_addend : Decimal | None
            First value to add.
        second_addend : Decimal | None
            Second value to add.
        subtrahend : Decimal | None
            Value to subtract.

        Returns
        -------
        Decimal | None
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
        chosen = min(total_tied)
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

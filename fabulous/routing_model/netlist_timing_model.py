"""Convert a Verilog gate-level netlist into a timing graph.

Synthesizes RTL into a gate-level netlist with `YosysTool` (or normalizes an
existing one), generates an SDF file from it with `OpenStaTool`, and parses that
into sdf_toolkit's native timing graph. Structural queries on the netlist
hierarchy (finding instances, resolving pins, listing ports) are delegated to the
parsed :class:`~fabulous.fabric_definition.yosys_obj.YosysJson`; this module only
owns the timing-graph side of the model.
"""

from pathlib import Path

import networkx as nx
from sdf_toolkit import TimingGraph, parse

from fabulous.fabric_definition.cell_spec import StdCellLibrary
from fabulous.fabric_definition.yosys_obj import InstanceRef, YosysJson
from fabulous.fabulous_settings import get_context
from fabulous.routing_model.graph_algorithms import (
    DelayType,
    path_to_nearest_target_sentinel,
)
from fabulous.tools.opensta import OpenStaTool
from fabulous.tools.yosys import YosysTool


class NetlistTimingModel:
    """Build a timing graph from Verilog RTL or a gate-level netlist.

    Synthesizes the RTL into a gate-level netlist with `YosysTool` (or normalizes
    an existing gate-level netlist when `is_gate_level` is True), generates an SDF
    file from that netlist with `OpenStaTool`, and parses it into sdf_toolkit's
    native timing graph (`self.timing_graph`, with the backing
    `networkx.MultiDiGraph` exposed as ``self.graph``). The structural netlist is
    parsed into a `YosysJson` (`self.netlist`) for hierarchy queries; the
    top-level `input_ports` / `output_ports` are read from it. The temporary
    netlist and SDF files are cleaned up afterwards.

    The standard-cell inputs (liberty and techmap files, the buffer/tie cells)
    come from the `library`; the debug flag is sourced from the active
    :func:`get_context`.

    Parameters
    ----------
    verilog_files : list[Path] | Path
        The RTL Verilog file(s) to synthesize, or the gate-level netlist when
        `is_gate_level` is True.
    top_name : str
        The name of the top-level module.
    library : StdCellLibrary
        The PDK's standard-cell library: liberty/techmap files and cells.
    is_gate_level : bool, optional
        Whether `verilog_files` is already a gate-level netlist (default False).
    spef_files : list[Path] | Path | None, optional
        SPEF RC extraction file(s) for wire-delay analysis, or None.
    delay_type_str : DelayType, optional
        Type of delay to consider (e.g., DelayType.MAX_ALL).
        Default is DelayType.MAX_ALL.
    """

    def __init__(
        self,
        verilog_files: list[Path] | Path,
        top_name: str,
        library: StdCellLibrary,
        is_gate_level: bool = False,
        spef_files: list[Path] | Path | None = None,
        delay_type_str: DelayType = DelayType.MAX_ALL,
    ) -> None:
        self.top_name: str = top_name
        self.delay_type_str: DelayType = delay_type_str

        ctx = get_context()
        self.debug: bool = ctx.debug

        netlist_file = YosysTool.synthesize(
            verilog_files=verilog_files,
            top_name=top_name,
            library=library,
            is_gate_level=is_gate_level,
            flat=False,
            debug=self.debug,
        )

        sdf_file = OpenStaTool.analyze(
            verilog_netlist=netlist_file,
            liberty_files=library.liberty_files,
            top_name=top_name,
            spef_files=spef_files,
            debug=self.debug,
        )

        sdf_object = parse(sdf_file.read_text())
        self.timing_graph = TimingGraph(sdf_object)
        self.hier_sep = sdf_object.header.divider or "/"
        self.graph: nx.MultiDiGraph = self.timing_graph.graph
        self.reverse_graph: nx.MultiDiGraph = self.graph.reverse(copy=True)

        self.netlist = YosysJson(
            netlist_file, top_name=top_name, hier_sep=self.hier_sep
        )

        OpenStaTool.clean_up(sdf_file)
        YosysTool.clean_up(netlist_file, is_gate_level=is_gate_level)

    def nearest_port_from_pin(
        self, hier_pin_path: str, reverse: bool = False, num_ports: int = 1
    ) -> list[str]:
        """Nearest port from pin.

        Find the nearest top-level port(s) connected to the same net as the given
        hierarchical pin. With `reverse` the search goes towards input ports,
        otherwise towards output ports.

        Parameters
        ----------
        hier_pin_path : str
            Hierarchical pin path.
        reverse : bool
            If True, search towards input ports; if False, towards output ports.
        num_ports : int
            Number of nearest ports to return. If fewer ports are found, return
            all found.

        Returns
        -------
        list[str]
            Hierarchical paths of the nearest top-level ports.

        Raises
        ------
        ValueError
            If num_ports is less than 1.
        """
        if num_ports < 1:
            raise ValueError("num_ports must be at least 1")
        if num_ports == 1:
            graph = self.reverse_graph if reverse else self.graph
            targets = self.netlist.input_ports if reverse else self.netlist.output_ports
            _, closest_target = path_to_nearest_target_sentinel(
                graph, hier_pin_path, targets
            )
            return [closest_target] if closest_target is not None else []
        if reverse:
            dist = nx.single_source_shortest_path_length(
                self.reverse_graph, hier_pin_path
            )
            leaf_dists = [
                (v, d) for v, d in dist.items() if v in self.netlist.input_ports
            ]
        else:
            dist = nx.single_source_shortest_path_length(self.graph, hier_pin_path)
            leaf_dists = [
                (v, d) for v, d in dist.items() if v in self.netlist.output_ports
            ]

        if len(leaf_dists) == 0:
            return []

        # already sorted by distance from NetworkX
        return [leaf_dists[i][0] for i in range(min(num_ports, len(leaf_dists)))]

    def nearest_ports_from_instance_pin_nets(
        self, instance: InstanceRef, reverse: bool = False, num_ports: int = 1
    ) -> tuple[dict[str, list[str]], list[str]]:
        """Nearest ports from instance pin nets.

        For each net on the instance's pins, find the nearest top-level port(s).
        With `reverse` the search goes towards input ports, otherwise output ports.

        Parameters
        ----------
        instance : InstanceRef
            The instance whose pin nets are traced.
        reverse : bool
            If True, search towards input ports; if False, towards output ports.
        num_ports : int
            Number of nearest ports to return per pin.

        Returns
        -------
        tuple[dict[str, list[str]], list[str]]
            Mapping from instance net names to nearest top-level port paths, and a
            de-duplicated flat list of those ports (nearest first).
        """
        net_to_pin: dict[str, list[str]] = (
            self.netlist.net_to_pin_paths_for_instance_resolved(instance)
        )
        pin_to_nearest_ports: dict[str, list[str]] = {}
        pin_to_nearest_ports_list: list[str] = []
        for net, pin_paths in net_to_pin.items():
            if pin_paths is None or len(pin_paths) == 0:
                continue
            nearest_ports = self.nearest_port_from_pin(
                pin_paths[0], reverse=reverse, num_ports=num_ports
            )
            pin_to_nearest_ports_list.extend(nearest_ports)
            pin_to_nearest_ports[net] = nearest_ports

        return pin_to_nearest_ports, list(dict.fromkeys(pin_to_nearest_ports_list))

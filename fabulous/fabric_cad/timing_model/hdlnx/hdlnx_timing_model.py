"""Convertes verilog RTL into a verilog gate-level netlist.

Will use an external synthesis tool.

In this context a sysnthesis tool can be anything that can convert RTL verilog into
gate-level verilog, that means also tools that can do backend design steps like
technology mapping and place&route.

It then runs an external STA tool on the gate-level netlist and parses the SDF file it
writes into a timing graph.
"""

import networkx as nx
from loguru import logger

from fabulous.fabric_cad.timing_model.hdlnx.sdfnx.sdf_to_graph import SDFTimingGraph
from fabulous.fabric_cad.timing_model.models import (
    DelayType,
)
from fabulous.fabric_cad.timing_model.tools.specification import StaTool, SynthTool


class HdlnxTimingModel(SDFTimingGraph):
    """Class to generate a timing graph from Verilog RTL.

    It does this by first synthesizing the RTL into a gate-level netlist using an
    external synthesis tool, then writing an SDF file for that netlist with an
    external STA tool, and parsing the SDF file into the timing graph.

    The gate-level netlist stays at `synth_tool.synth_netlist_file` until the caller
    runs `synth_tool.synth_clean_up()`.

    Parameters
    ----------
    sta_tool : StaTool
        The static timing analysis tool to use for generating the timing graph.
    synth_tool : SynthTool
        The synthesis tool to use for converting RTL to gate-level netlist.
    delay_type_str : DelayType, optional
        The type of delay to use for the timing graph (default is DelayType.MAX_ALL).
    debug : bool, optional
        If True, print debug warnings about overwriting STA tool
        configurations (default is False).
    """

    def __init__(
        self,
        sta_tool: StaTool,
        synth_tool: SynthTool,
        delay_type_str: DelayType = DelayType.MAX_ALL,
        debug: bool = False,
    ) -> None:
        synth_tool.synth_synthesize()

        if sta_tool.sta_netlist_file is not None and debug:
            logger.warning(
                "STA tool already has a netlist file. This will be "
                "overwritten by HdlnxTimingModel."
            )

        if sta_tool.sta_design_name is not None and debug:
            logger.warning(
                "STA tool already has a design name. This will be "
                "overwritten by HdlnxTimingModel."
            )

        if sta_tool.sta_liberty_files is not None and debug:
            logger.warning(
                "STA tool already has liberty files. This will be "
                "overwritten by HdlnxTimingModel."
            )

        sta_tool.sta_netlist_file = synth_tool.synth_netlist_file
        sta_tool.sta_design_name = synth_tool.synth_design_name
        sta_tool.sta_liberty_files = synth_tool.synth_liberty_files

        sta_tool.sta_analyze()
        super().__init__(sta_tool.sta_sdf_file, delay_type_str)
        sta_tool.sta_clean_up()

    def nearest_port_from_pin(
        self, hier_pin_path: str, reverse: bool = False, num_ports: int = 1
    ) -> list[str]:
        """Nearest port from pin.

        Given a hierarchical pin path like "inst1/inst2/A0", find the nearest top-
        level port connected to the same net as that pin. Depending on `reverse`, the
        search is done towards input ports (reverse=True) or output ports
        (reverse=False).

        Parameters
        ----------
        hier_pin_path : str
            Hierarchical pin path.
        reverse : bool
            If True, search towards input ports; if False, towards output ports.
        num_ports : int
            Number of nearest ports to return. if less ports are found,
            return all found, which can be less than `num_ports`.

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
            path_without_sentinel, closest_target = (
                self.path_to_nearest_target_sentinel(
                    hier_pin_path,
                    self.input_ports if reverse else self.output_ports,
                    reverse=reverse,
                )
            )
            return [closest_target] if closest_target is not None else []
        if reverse:
            dist = nx.single_source_shortest_path_length(
                self.reverse_graph, hier_pin_path
            )
            leaf_dists = [(v, d) for v, d in dist.items() if v in self.input_ports]
        else:
            dist = nx.single_source_shortest_path_length(self.graph, hier_pin_path)
            leaf_dists = [(v, d) for v, d in dist.items() if v in self.output_ports]

        if len(leaf_dists) == 0:
            return []

        # already sorted by distance from NetworkX
        return [leaf_dists[i][0] for i in range(min(num_ports, len(leaf_dists)))]

    def nearest_ports_from_pins(
        self,
        net_pins: dict[str, list[str]],
        reverse: bool = False,
        num_ports: int = 1,
    ) -> tuple[dict[str, list[str]], list[str]]:
        """Nearest top-level ports from the leaf pins of each net.

        Depending on `reverse`, the search is done towards input ports
        (reverse=True) or output ports (reverse=False). Only the first leaf pin of
        each net is searched from.

        Parameters
        ----------
        net_pins : dict[str, list[str]]
            Net name to its leaf pins, as `NetlistIndex.net_leaf_pins` returns.
        reverse : bool
            If True, search towards input ports; if False, towards output ports.
        num_ports : int
            Number of nearest ports to return per net. if less ports are found,
            return all found, which can be less than `num_ports`.

        Returns
        -------
        tuple[dict[str, list[str]], list[str]]
            Mapping from net names to lists of nearest top-level port paths, and
            all of those ports without duplicates. Each list is sorted starting
            from the nearest ports.
        """
        pin_to_nearest_ports: dict[str, list[str]] = {}
        pin_to_nearest_ports_list: list[str] = []
        for net, pin_paths in net_pins.items():
            if len(pin_paths) == 0:
                continue
            nearest_ports = self.nearest_port_from_pin(
                pin_paths[0], reverse=reverse, num_ports=num_ports
            )
            pin_to_nearest_ports_list.extend(nearest_ports)
            pin_to_nearest_ports[net] = nearest_ports

        return pin_to_nearest_ports, list(dict.fromkeys(pin_to_nearest_ports_list))

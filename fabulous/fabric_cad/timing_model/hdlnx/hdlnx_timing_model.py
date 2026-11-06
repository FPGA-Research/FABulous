"""Timing graph of a synthesised or post-layout tile netlist.

The caller writes the netlist's SDF file with `OpenStaTool.write_sdf` and builds
the graph from it; this module adds the nearest-port searches the pip
characterisation needs.
"""

import networkx as nx

from fabulous.fabric_cad.timing_model.sdf_timing_graph import SdfTimingGraph


class HdlnxTimingModel(SdfTimingGraph):
    """Timing graph of a tile netlist with nearest-port searches."""

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

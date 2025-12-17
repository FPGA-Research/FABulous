#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# SDF Timing Graph Class Module
# This module provides a class to represent timing graphs generated from SDF files.
# It also includes methods to analyze the timing graph using NetworkX.
# SDF to dict is done using f4pga_sdf_timing.sdf_timing.sdfparse see also:
#   https://github.com/chipsalliance/f4pga-sdf-timing/tree/master

from pathlib import Path

import networkx as nx

from .timing_graph import gen_timing_digraph
from .models import Component

class SDFTimingGraphBase:
    """
    Class to represent a timing graph generated from an SDF file.
    It also contains algorithms to analyze the timing graph.
    Attributes:
        sdf_file (Path): Path to the SDF file.
        delay_type_str (str): The type of delay to extract. Options include:
            "min_all", "max_all", "avg_all", "avg_fast", "avg_slow",
            "max_fast", "max_slow", "min_fast", "min_slow".
        hier_sep (str): Hierarchy separator used in the design If None, it will be inferred from the SDF header.
        graph (nx.DiGraph): Directed graph representing the timing information.
        header_info (dict): Dictionary containing header information from the SDF file.
    """
    
    def __init__(self, sdf_file: Path, delay_type_str: str = "max_all"):
        self.sdf_file: Path = sdf_file
        self.sdf_file_content: str = sdf_file.read_text()
        self.delay_type_str: str = delay_type_str
        
        (self.graph, self.header_info, 
         self.sdf_data_dict, self.cells, self.instances, 
         self.io_paths, self.interconnects) = gen_timing_digraph(sdf_file, delay_type_str)
        
        self.hier_sep = self.header_info["divider"] if "divider" in self.header_info else "/"
        self.input_ports = list({n for n in self.graph.nodes if self.graph.in_degree(n) == 0 and self.hier_sep not in n})
        self.output_ports = list({n for n in self.graph.nodes if self.graph.out_degree(n) == 0 and self.hier_sep not in n})
        self.reverse_graph = self.graph.reverse(copy=True)
        
    ### Public Methods ###
    
    def get_input_and_output_ports(self) -> list[str]:
        """
        Get the list of input and output ports in the timing graph.
        Returns:
            list[str]: List of input and output port names.
        """
        return self.input_ports + self.output_ports
    
    def get_output_ports(self) -> list[str]:
        """
        Get the list of output ports in the timing graph.
        Returns:
            list[str]: List of output port names.
        """
        return self.output_ports
    
    def get_input_ports(self) -> list[str]:
        """
        Get the list of input ports in the timing graph.
        Returns:
            list[str]: List of input port names.
        """
        return self.input_ports
    
    def get_hier_sep(self) -> str:
        """
        Get the hierarchical separator used in instance names.
        Returns:
            str: The hierarchical separator.
        """
        return self.hier_sep
    
    def get_interconnects(self) -> list[Component]:
        """
        Get the list of interconnect components present in the SDF file.
        Returns:
            list[Component]: List of interconnect components.
        """
        return self.interconnects
    
    def get_io_paths(self) -> list[Component]:
        """
        Get the list of IOPATH components present in the SDF file.
        Returns:
            list[Component]: List of IOPATH components.
        """
        return self.io_paths
    
    def get_cell_instances(self) -> dict[str, list[Component]]:
        """
        Get the dictionary of instance names and their associated 
        components present in the SDF file.
        Returns:
            dict[str, list[Component]]: Dictionary mapping instance 
                                        names to lists of components.
        """
        return self.instances
    
    def get_cell_instance(self, instance_name: str) -> list[Component]:
        """
        Get the list of components associated with a given instance name.
        Args:
            instance_name (str): The name of the cell instance.
        Returns:
            list[Component]: List of components associated with the instance.
        """
        return self.instances[instance_name]
    
    def get_cells(self) -> list[str]:
        """
        Get the list of cell names present in the SDF file.
        Returns:
            list[str]: List of cell names.
        """
        return self.cells
    
    def get_raw_sdf_data(self) -> str:
        """
        Get the raw SDF file content as a string.
        Returns:
            str: The content of the SDF file.
        """
        return self.sdf_file_content
    
    def get_sdf_data_dict(self) -> dict:
        """
        Get the SDF data as a dictionary.
        Returns:
            dict: The SDF data in dictionary format.
        """
        return self.sdf_data_dict
    
    def get_nxgraph(self) -> nx.DiGraph:
        """
        Get the NetworkX directed graph representing the timing information.
        Note that the graph edges have a 'weight' attribute representing delay
        and that each node is a string in the format "cell_instance_name/pin_name".
        Returns:
            nx.DiGraph: The directed graph with delay annotations.
        """
        return self.graph
    
    def get_reverse_nxgraph(self) -> nx.DiGraph:
        """
        Get the reversed NetworkX directed graph representing the timing information.
        Note that the graph edges have a 'weight' attribute representing delay
        and that each node is a string in the format "cell_instance_name/pin_name".
        Returns:
            nx.DiGraph: The reversed directed graph with delay annotations.
        """
        return self.reverse_graph
    
    def set_nxgraph(self, graph: nx.DiGraph):
        """
        Set the NetworkX directed graph representing the timing information.
        This can be useful to replace the graph after modifications with other networkx algorithms.
        Args:
            graph (nx.DiGraph): The directed graph to set.
        Examples:
            ```python
            sdf_graph = SDFTimingGraph(sdf_file, "max_all")
            G = sdf_graph.get_nxgraph()
            # Modify G using networkx algorithms
            sdf_graph.set_nxgraph(G)
        """
        self.graph = graph
    
    def print_graph(self):
        """
        Print the edges of the timing graph along with their delay weights and component information.
        """
        for u, v, data in self.graph.edges(data=True):
            print(f"{u} --> {v} delay {data['weight']} ({data['component'].cell_name}, {data['component'].c_type})")
    
    def get_SDF_header_info(self) -> tuple[dict, str]:
        """
        Get the SDF header information as a dictionary and formatted string.
        Returns:
            tuple (dict, str): A tuple containing the header information dictionary and a formatted string.
        """
        info_str: str = ""
        for key, value in self.header_info.items():
            info_str += f"{key}: {value}\n"
        return self.header_info, info_str
    
    def has_path(self, source: str, target: str) -> bool:
        """
        Check if there is a path from source to target in the timing graph.
        Args:
            source (str): The source node.
            target (str): The target node.
        Returns:
            bool: True if a path exists, False otherwise.
        Examples:
            ```python
            exists = sdf_graph.has_path("nodeA/pin", "nodeB/pin")
        """
        return nx.has_path(self.graph, source=source, target=target)
    
    def delay_path(self, source: str, target: str) -> tuple[float, list[str], str]:
        """
        Find the path with the delay between source and target nodes in the timing graph.
        Args:
            source (str): The source node.
            target (str): The target node.
        Returns:
            tuple (float, list[str], str): A tuple containing the total delay, the path as a list of nodes,
                                           and a detailed info string about the path.
        Examples:
            ```python
            length, path, info = sdf_graph.delay_path("nodeA/pin", "nodeB/pin")
        """
        
        length: float = nx.dijkstra_path_length(self.graph, source=source, target=target, weight="weight")
        path: list[str] = nx.dijkstra_path(self.graph, source=source, target=target, weight="weight")
        info:str = ""
        
        for i in range(len(path)-1):
            u = path[i]
            v = path[i+1]
            edge_data = self.graph.edges[u, v]
            info += (f"{u} -> {v} with delay {edge_data['weight']} ({edge_data['component'].cell_name}," 
                     f"{edge_data['component'].c_type})\n")
        return length, path, info
    
    def get_cell_instance_inputs_to_outputs(self, instance_name: str) -> tuple[list[str], list[str]]:
        """
        Get the input and output pins of a given cell instance.
        Args:
            instance_name (str): The name of the cell instance.
        Returns:
            tuple (list[str], list[str]): A tuple containing two lists: input pins and output pins.
        """
        input_pins: list[str] = []
        output_pins: list[str] = []
        
        if instance_name not in self.instances:
            print(f"Instance {instance_name} not found in SDF instances.")
            return input_pins, output_pins
        
        for i in self.instances[instance_name]:
            if i.c_type == "IOPATH":
                input_pins.append(i.from_cell_pin)
                output_pins.append(i.to_cell_pin)
        return input_pins, output_pins
    
    def get_cell_instance_component_by_type(self, instance_name: str, 
                                            c_type: str, input_pin: str, output_pin: str) -> Component:
        """
        Get a specific component of a cell instance by type and pin names.
        Args:
            instance_name (str): The name of the cell instance.
            c_type (str): The type of component: "IOPATH", "REMOVAL", 
                                                 "RECOVERY", "SETUP", "HOLD", "WIDTH".
            input_pin (str): The input pin name.
            output_pin (str): The output pin name.
        Returns:
            Component: The matching component, or None if not found.
        """
        
        if instance_name not in self.instances:
            raise KeyError(f"Instance {instance_name} not found in SDF instances.")
        
        for i in self.instances[instance_name]:
            if i.c_type == c_type and i.from_cell_pin == input_pin and i.to_cell_pin == output_pin:
                return i
        return None
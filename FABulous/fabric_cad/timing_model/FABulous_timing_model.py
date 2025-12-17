#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# Tming model for FABulous designs

from pathlib import Path
import os
import re

from loguru import logger

from .hdlnx.hdlnx_timing_model import HdlnxTimingModel

from FABulous.fabric_definition.Fabric import Fabric
from FABulous.fabric_definition.SuperTile import SuperTile
from FABulous.fabric_definition.Tile import Tile

class FABulousTileTimingModel:
    def __init__(self, config: dict, fabric: Fabric):
        self.config = config
        self.fabric = fabric
        
        self._add_config_keys(new_keys={
            "project_dir": "required",            # Path
            "tile_name": "required",              # str, e.g., "LUT4AB"
            "liberty_files": "required",          # list[Path] | Path
            "techmap_files": "required",          # list[Path] 
            "min_buf_cell_and_ports": "required", # str, e.g., "sg13g2_buf_1 A X"
            "mode": "physical",                   # str, "physical" | "structural"
            "sta_executable": "sta",              # str
            "sta_program": "opensta",             # str
            "synth_program": "yosys",             # str
            "synth_executable": "yosys",          # str
            "consider_wire_delay": True,          # bool
            "delay_type_str": "max_all",          # str
            "debug": False,                       # bool
            
        }, msg="FABulous Tile Timing Model")
        
        self.is_in_which_super_tile: str | None = None
        self.unique_tile_name: str = self.config["tile_name"]
        
        for unique_tiles in self.fabric.get_all_unique_tiles():
            if isinstance(unique_tiles, SuperTile):
                for composed_tile in unique_tiles.tiles:
                    if composed_tile.name == self.config["tile_name"]:
                        self.is_in_which_super_tile = unique_tiles.name
                        self.unique_tile_name = unique_tiles.name
                        break
        
        exclude_dir_patterns: list[str] = ["macro", "user_design", "Test"]
        self.verilog_files: list[Path] = self.find_matching_files(self.config["project_dir"], r".*\.v$", exclude_dir_patterns)
        
        ### Init:
        
        logger.info(f"Initializing FABulous Timing Model for Tile: {self.config['tile_name']}")
        logger.info(f"  SuperTile: {self.is_in_which_super_tile}")
        self.config["hier_sep"] = None
        
        logger.info("Initializing Synthesis-level timing model...")
        self.config["flat"] = False
        self.config["is_gate_level"] = False
        self.config["spef_files"] = None
        self.config["verilog_files"] = self.verilog_files
        self.config["top_name"] = self.unique_tile_name
        
        self.hdlnx_tm_synth = HdlnxTimingModel(self.config)
        
        logger.info("Initializing Physical-level timing model...")
        self.config["is_gate_level"] = True
        self.config["verilog_files"] = (Path(f"{self.config['project_dir']}/Tile/{self.unique_tile_name}"
                                             f"/macro/final_views/nl/{self.unique_tile_name}.nl.v"))
        if self.config["consider_wire_delay"]:
            self.config["spef_files"] = (Path(f"{self.config['project_dir']}/Tile/{self.unique_tile_name}"
                                              f"/macro/final_views/spef/nom/{self.unique_tile_name}.nom.spef"))
        
        self.hdlnx_tm_phys = HdlnxTimingModel(self.config)
        
        # Extract switch matrix information
        # Check super_tile_type in config to filter the correct switch matrix
        
        logger.info("Extracting switch matrix information...")
        self.switch_matrix_hier_path = self.hdlnx_tm_synth.find_instance_paths_by_regex(r".*_switch_matrix$")
        self.switch_matrix_module_name = self.hdlnx_tm_synth.find_verilog_modules_regex(r"^[^/]*_switch_matrix$")
        
        
        if self.is_in_which_super_tile is None:
            if len(self.switch_matrix_hier_path) == 0 or len(self.switch_matrix_module_name) == 0:
                raise ValueError("No switch matrix instance or module found for regular Tile.")
            if len(self.switch_matrix_hier_path) > 1 or len(self.switch_matrix_module_name) > 1:
                raise ValueError("Multiple switch matrix instances or modules found for a non-SuperTile.")
            self.switch_matrix_hier_path = self.switch_matrix_hier_path[0]
            self.switch_matrix_module_name = self.switch_matrix_module_name[0]
            logger.info(f"Using switch matrix instance: {self.switch_matrix_hier_path}, "
                        f"module: {self.switch_matrix_module_name}")
        else:
            self.switch_matrix_hier_path = [
                p for p in self.switch_matrix_hier_path 
                if self.config["tile_name"] in p
            ]
            self.switch_matrix_module_name = [
                m for m in self.switch_matrix_module_name 
                if self.config["tile_name"] in m
            ]
            if len(self.switch_matrix_hier_path) == 0 or len(self.switch_matrix_module_name) == 0:
                raise ValueError(f"No switch matrix instance or module found for SuperTile "
                                 f"{self.unique_tile_name}")
            if len(self.switch_matrix_hier_path) > 1 or len(self.switch_matrix_module_name) > 1:
                raise ValueError(f"Multiple switch matrix instances or modules found Tile "
                                 f"{self.config['tile_name']} in SuperTile {self.unique_tile_name}.")
            self.switch_matrix_hier_path = self.switch_matrix_hier_path[0]
            self.switch_matrix_module_name = self.switch_matrix_module_name[0]   
            logger.info(f"Tile {self.config['tile_name']} is part of super tile {self.unique_tile_name}.")
        
        
        logger.info("Loading internal PIPs...")
        self.internal_pips_grouped_by_inst = self.hdlnx_tm_synth.get_module_instance_nets(self.switch_matrix_module_name)
        self.internal_pips = self.hdlnx_tm_synth.get_instance_pins(self.switch_matrix_hier_path)
        logger.info("FABulous Timing Model initialized.")
        
        ### Definitions:
        
        self.mode = self.config["mode"]
    
    
    def _add_config_keys(self, new_keys: dict, msg: str = ""):
        """
        Adds new configuration keys to the configuration dictionary if they are not already present.
        Use "required" as the value to indicate that a key is mandatory, otherwise a default value is assigned.
        Args:
            new_keys (dict): Dictionary of new configuration keys and their default values.
            msg (str): Optional message to include in the KeyError if a required key is missing.
        Raises:
            KeyError: If any required key is missing from the configuration dictionary.
        """
        for key, val in new_keys.items():
            if key not in self.config:
                if val == "required":
                    raise KeyError(f"Missing required configuration key [{msg}]: '{key}'")
                else:
                    self.config[key] = val
    
    def find_matching_files(
        self,
        root_dir: Path,
        file_pattern: str,
        exclude_dir_patterns: list[str] | None = None,
        exclude_file_patterns: list[str] | None = None,
    ) -> list[Path]:
        """
        Recursively traverse root_dir and return a list of Path objects
        for all files whose *name* matches file_pattern (regex).

        - exclude_dir_patterns: list of regex patterns; directory names
        matching any of these will be skipped completely.
        - exclude_file_patterns: list of regex patterns; file names
        matching any of these will be skipped.
        
        Args:
            root_dir (Path): Root directory to start the search.
            file_pattern (str): Regex pattern to match file names.
            exclude_dir_patterns (list[str] | None): List of regex patterns to exclude directories.
            exclude_file_patterns (list[str] | None): List of regex patterns to exclude files.
        Returns:
            list[Path]: List of Path objects for matched files. 
        Raises:
            ValueError: If root_dir is not a Path object.
        """
        
        if not isinstance(root_dir, Path):
            raise ValueError("root_dir must be a Path object.")
        
        root_path = root_dir

        file_re = re.compile(file_pattern)
        exclude_dir_res = [re.compile(p) for p in (exclude_dir_patterns or [])]
        exclude_file_res = [re.compile(p) for p in (exclude_file_patterns or [])]

        matched_files: list[Path] = []

        for dirpath, dirnames, filenames in os.walk(root_path):
            # Filter out excluded directories in-place so os.walk doesn't descend into them
            dirnames[:] = [
                d for d in dirnames
                if not any(r.search(d) for r in exclude_dir_res)
            ]

            for fname in filenames:
                # Skip excluded file names
                if any(r.search(fname) for r in exclude_file_res):
                    continue

                # Match main pattern on file name
                if file_re.search(fname):
                    matched_files.append(Path(dirpath) / fname)

        return matched_files

        
    def is_tile_internal_pip(self, pip_src: str, pip_dst: str) -> bool:
        """
        Check if both PIPs are internal PIPs of the switch matrix.
        That means the path must be through a switch matrix multiplexer.
        Its not a wire delay.
        
        Args:
            pip_src (str): Source PIP port name (e.g., "LB_O")
            pip_dst (str): Destination PIP port name (e.g., "JN2BEG3")
        Returns:
            bool: True if both PIPs are internal PIPs of the switch matrix, False otherwise.
        """
        instance_to_nets = self.internal_pips_grouped_by_inst
        target = set([pip_src, pip_dst])
        for inst, net_list in instance_to_nets.items():
            if target.issubset(set(net_list)):
                return True  
        return False
           
    def internal_pip_delay_structural(self, pip_src: str, pip_dst: str) -> float:
        """
        Calculate delay between two PIPs in the switch matrix.
        It is the fast variant that does not need physical design
        information, but the results may be less accurate.
        
        Args:
            pip_src (str): Source PIP port name (e.g., "LB_O")
            pip_dst (str): Destination PIP port name (e.g., "JN2BEG3")
        Returns:
            float: Delay in nanoseconds between the two PIPs.
        """
        
        if pip_src not in self.internal_pips or pip_dst not in self.internal_pips:
            raise ValueError(f"One or both PIPs {pip_src}, {pip_dst} are not internal PIPs of the switch matrix.")
        
        synth_model = self.hdlnx_tm_synth
        
        logger.info(f"Finding synthesis-level switch matrix mux for PIPs {pip_src} -> {pip_dst}")
        swm_mux = synth_model.find_instances_paths_with_all_nets(
            self.switch_matrix_module_name, 
            [pip_src, pip_dst], 
            filter_regex=self.switch_matrix_hier_path
        )
        
        if len(swm_mux) == 0:
            raise ValueError(f"No switch matrix mux instance found for PIPs {pip_src} -> {pip_dst}"
                             f"Pip name might be incorrect. Or they appear in different swm multiplexers.")
        
        if len(swm_mux) > 1:
            logger.warning(f"Multiple switch matrix mux instances found for PIPs {pip_src} -> {pip_dst}. "
                           f"Using the first one: {swm_mux[0]}")
            
        logger.info(f"  Found switch matrix mux instance: {swm_mux[0]}")
        swm_mux_resolved = synth_model.net_to_pin_paths_for_instance_resolved(swm_mux[0])
        logger.info(f"Switch matrix mux resolved pins for src and dst:")
        logger.info(f"  {pip_src}: {swm_mux_resolved[pip_src]}")
        logger.info(f"  {pip_dst}: {swm_mux_resolved[pip_dst]}")
        
        if len(swm_mux_resolved[pip_src]) == 0:
            raise ValueError(f"No resolved pins found for PIP source {pip_src} in switch matrix mux instance {swm_mux[0]}.")
        if len(swm_mux_resolved[pip_dst]) == 0:
            raise ValueError(f"No resolved pins found for PIP destination {pip_dst} in switch matrix mux instance {swm_mux[0]}.")
        if len(swm_mux_resolved[pip_src]) > 1:
            logger.warning(f"Multiple resolved pins found for PIP source {pip_src} in switch matrix mux instance {swm_mux[0]}. "
                           f"Using the first one: {swm_mux_resolved[pip_src][0]}")
        if len(swm_mux_resolved[pip_dst]) > 1:
            logger.warning(f"Multiple resolved pins found for PIP destination {pip_dst} in switch matrix mux instance {swm_mux[0]}. "
                           f"Using the first one: {swm_mux_resolved[pip_dst][0]}")
        
        logger.info(f"Calculating structural delay from {pip_src} to {pip_dst}")
        delay, path, info = synth_model.delay_path(swm_mux_resolved[pip_src][0], swm_mux_resolved[pip_dst][0])
        
        logger.info(f"Delay from {pip_src} to {pip_dst}: {delay} ns via path:")
        print(info)
        
        return delay
            
    
    def internal_pip_delay_physical(self, pip_src: str, pip_dst: str) -> float:
        """
        Calculate delay between two PIPs using physical design information.
        This method uses the physical-level timing model to provide more accurate delay estimates
        by considering the actual physical implementation.
        
        Args:
            pip_src (str): Source PIP port name (e.g., "LB_O")
            pip_dst (str): Destination PIP port name (e.g., "JN2BEG3")
        Returns:
            float: Delay in nanoseconds between the two PIPs.
        """
        
        if pip_src not in self.internal_pips or pip_dst not in self.internal_pips:
            raise ValueError(f"One or both PIPs {pip_src}, {pip_dst} are not internal PIPs of the switch matrix.")
        
        
        synth_model = self.hdlnx_tm_synth
        phys_model = self.hdlnx_tm_phys
        
        ###########################################################################
        # Synthesis-level resolution (extract the realted module ports that are 
        # connected to the SMW mux to which the PIP belongs)
        ###########################################################################
        
        # extract the swm mux for pips: pip_src, pip_dst
        logger.info(f"Finding synthesis-level switch matrix mux for PIPs {pip_src} -> {pip_dst}")
        swm_mux_for_pips = synth_model.find_instances_paths_with_all_nets(
            self.switch_matrix_module_name, 
            [pip_src, pip_dst],
            filter_regex=self.switch_matrix_hier_path
        )
        
        if len(swm_mux_for_pips) == 0:
            raise ValueError(f"No switch matrix mux instance found for PIPs {pip_src} -> {pip_dst}"
                             f"Pip name might be incorrect. Or they appear in different swm multiplexers.")
            
        if len(swm_mux_for_pips) > 1:
            logger.warning(f"Multiple switch matrix mux instances found for PIPs {pip_src} -> {pip_dst}. "
                           f"Using the first one: {swm_mux_for_pips[0]}")
        
        logger.info(f"  Found switch matrix mux instance: {swm_mux_for_pips[0]}")
        logger.info("Finding synthesis-level top-level ports connected to the switch matrix mux nets...")
        
        # find the nearest top level ports connected to all the nets of the swm mux input pins
        # We reverse the timing graph to find the input ports (towards inputs).
        # We do this ebcause the pysical design only presevers top-level port names,
        # and they are the same as in the synthesis-level netlist.
        # !! num_ports parameter sweep.
        # Good default value is 4. Fastest is 1 (converging a bit worse then).
        swm_nearest_ports = synth_model.nearest_ports_from_instance_pin_nets(
                swm_mux_for_pips[0], 
                reverse=True, 
                num_ports=1
        )
        
        for swm_wire, ports in swm_nearest_ports[0].items():
            print(f"  SWM wire {swm_wire} nearest top-level ports: {ports}")
        
        swm_nearest_ports_for_each_swm_wire = swm_nearest_ports[0]
        swm_nearest_ports_all = swm_nearest_ports[1]
        
        #############################################################################################
        # Physical-level resolution map the synthesis-level top-level ports that are related to the 
        # swm mux to physical-level swm mux pins to find the sm mux output pin (Then we can calc the 
        # delay between pip_src and pip_dst). To find the swm mux output we will use a method that
        # we call earliest node convergence. That means for MUX the topology we know that all inputs
        # converge to the output pin (mostly), so we can find the earliest common node from all the input
        # ports found above. Similar to graph betweenness centrality subset, but here we want to find the node
        # that minimizes the maximum distance from all the input ports.
        #############################################################################################
        
        # Find the converging node (the output pin of the swm mux)
        logger.info("Starting physical extraction of the switch matrix mux for pips")
        if len(swm_nearest_ports_all) > 1:
            best_nodes, best_cost, dists = phys_model.earliest_common_nodes(swm_nearest_ports_all, 
                                                                            mode="max", consider_delay=False)
            logger.info(f"Converging nodes: {best_nodes} with hops: {best_cost}")
            # !!check and follow output, sels common node to input ports then to output
            best_nodes.sort()
            swm_phys_output = best_nodes[0]
        else:
            # !!Probably just a buffer. But still we must check...
            swm_phys_output = phys_model.follow_first_fanout_from_pins(swm_nearest_ports_all[0], num_follow=2)
            logger.info(f"Only one input port found, follow its successor: {swm_phys_output}")
        
        ######################################################################
        # Finally calculate the delay between the two PIPs at physical level
        ######################################################################
        
        # Calculate delay between pip_src and the converged output pin
        # We use the 0st nearest port found for pip_src beacuse the list is sorted
        # starting from the nearest port.
        logger.info(f"Calculating physical delay from {pip_src} to {pip_dst}")
        
        if f"{pip_src}" not in (swm_nearest_ports_for_each_swm_wire or 
                                len(swm_nearest_ports_for_each_swm_wire[f"{pip_src}"]) == 0):
            raise ValueError(f"No nearest ports (end points) found for PIP source {pip_src} in physical model.")
        
        delay, path, info = phys_model.delay_path(swm_nearest_ports_for_each_swm_wire[f"{pip_src}"][0], swm_phys_output)
        
        logger.info(f"Physical Delay from {pip_src} to {pip_dst}: {delay} ns via path:")
        print(info)
        
        return delay 
    
    def external_pip_delay_structural(self, pip_src: str, pip_dst: str) -> float:
        return 0.001
    
    def external_pip_delay_physical(self, pip_src: str, pip_dst: str) -> float:
        return 0.001
    
    def internal_pip_delay(self, pip_src: str, pip_dst: str) -> float:
        if self.mode == "physical":
            return self.internal_pip_delay_physical(pip_src, pip_dst)
        else:
            return self.internal_pip_delay_structural(pip_src, pip_dst)
    
    def external_pip_delay(self, pip_src: str, pip_dst: str) -> float:
        if self.mode == "physical":
            return self.external_pip_delay_physical(pip_src, pip_dst)
        else:
            return self.external_pip_delay_structural(pip_src, pip_dst)
    
    def pip_delay(self, pip_src: str, pip_dst: str) -> float:
        if self.is_tile_internal_pip(pip_src, pip_dst):
            return self.internal_pip_delay(pip_src, pip_dst)
        else:
            return self.external_pip_delay(pip_src, pip_dst)
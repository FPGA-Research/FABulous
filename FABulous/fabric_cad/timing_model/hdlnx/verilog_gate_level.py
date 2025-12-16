#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# This module converts a Verilog gate-level netlist into a timing graph.
# It uses the SDFTimingGraph class to parse the SDF file and generate
# a NetworkX directed graph representing the timing relationships.
# It will call an external STA tool to generate the SDF file from the Verilog netlist.

from pathlib import Path
import tempfile, os
import subprocess
import re

import networkx as nx
from concurrent.futures import ThreadPoolExecutor

from .sdfnx.sdf_to_graph import SDFTimingGraph

class VerilogGateLevelTimingGraph(SDFTimingGraph):
    """
    Class to represent a timing graph generated from a Verilog gate-level netlist.
    It extends SDFTimingGraph to include functionality for generating the SDF file
    using an external static timing analysis (STA) tool.
    Attributes:
        verilog_netlist (Path): Path to the Verilog gate-level netlist file.
        liberty_files (list[Path] | Path): List of paths to Liberty files or a single Liberty file path.
        top_name (str): Name of the top-level module in the Verilog netlist.
        sta_executable (str): Path to the STA tool executable.
        sta_program (str): Name of the STA tool program (e.g., "opensta").
        spef_files (list[Path] | Path | None): List of paths to SPEF files or a single SPEF file path, or None.
        delay_type_str (str): Type of delay to consider (e.g., "max_all").
        hier_sep (str | None): Hierarchy separator used in the netlist, or None.
        debug (bool): Flag to enable debug mode.
    """
    
    def __init__(self, verilog_netlist: Path, liberty_files: list[Path] | Path, top_name: str, sta_executable: str, 
                 sta_program: str, spef_files: list[Path] |Path = None, delay_type_str: str = "max_all", 
                 hier_sep: str = None, debug: bool = False):
        self.verilog_netlist: Path = verilog_netlist
        self.liberty_files: list[Path] | Path = liberty_files
        self.top_name: str = top_name
        self.sta_executable: str = sta_executable
        self.sta_program: str = sta_program
        self.spef_files: list[Path] | Path = spef_files
        self.delay_type_str: str = delay_type_str
        self.debug: bool = debug
        
        self._check_errors()
        
        self.verilog_netlist_content: str = self.verilog_netlist.read_text()
        
        # Register new STA tool here.
        # The value must be a function that points to the respective sta function
        # which always returns the (temp) path to the generated sdf netlist file.
        self.registered_sta_tools: dict[str, Path] = {
            "opensta": self._generate_sdf_opensta()
        }
        
        self._apply_settings()
    
    ### Protected methods ###   
        
    def _apply_settings(self):
        """
        Applies the settings and generates the SDF file using the specified STA tool.
        Initializes the parent SDFTimingGraph class with the generated SDF file.
        """
        
        if self.sta_program in self.registered_sta_tools:
            sdf_path: Path = self.registered_sta_tools[self.sta_program]
        else:
            raise NotImplementedError(f"STA tool '{self.sta_program}' is not supported.")
        
        # Initialize the parent SDFTimingGraph class
        super().__init__(sdf_path, self.delay_type_str)
        
        # Delete the temporary SDF file
        os.remove(sdf_path)
        
    def _check_errors(self):
        """
        Checks for errors in the provided configuration parameters.
        Raises:
            TypeError: If any parameter is of incorrect type.
            FileNotFoundError: If any specified file does not exist.
            ValueError: If any specified file is empty.
        """
        
        if not isinstance(self.verilog_netlist, Path):
            raise TypeError("verilog_netlist must be a pathlib.Path object.")
        if not self.verilog_netlist.exists():
            raise FileNotFoundError(f"Verilog netlist file not found: {self.verilog_netlist}")
        if self.verilog_netlist.stat().st_size == 0:
            raise ValueError(f"Verilog netlist file is empty: {self.verilog_netlist}")
        
        if not isinstance(self.liberty_files, (list, Path)):
            raise TypeError("liberty_files must be a list of pathlib.Path objects or a single pathlib.Path object.")
        if isinstance(self.liberty_files, list):
            for lib in self.liberty_files:
                if not isinstance(lib, Path):
                    raise TypeError("Each item in liberty_files list must be a pathlib.Path object.")
                if not lib.exists():
                    raise FileNotFoundError(f"Liberty file not found: {lib}")
                if lib.stat().st_size == 0:
                    raise ValueError(f"Liberty file is empty: {lib}")
        else:
            if not self.liberty_files.exists():
                raise FileNotFoundError(f"Liberty file not found: {self.liberty_files}")
            if self.liberty_files.stat().st_size == 0:
                raise ValueError(f"Liberty file is empty: {self.liberty_files}")
            
        if not isinstance(self.top_name, str):
            raise TypeError("top_name must be a string.")
        if not isinstance(self.sta_executable, str):
            raise TypeError("sta_executable must be a string.")
        if not isinstance(self.sta_program, str):
            raise TypeError("sta_program must be a string.")
        
        if self.spef_files is not None and not isinstance(self.spef_files, (list, Path)):
            raise TypeError("spef_files must be a list of pathlib.Path objects or a single pathlib.Path object or None.")
        if isinstance(self.spef_files, list):
            for spef in self.spef_files:
                if not isinstance(spef, Path):
                    raise TypeError("Each item in spef_files list must be a pathlib.Path object.")
                if not spef.exists():
                    raise FileNotFoundError(f"SPEF file not found: {spef}")
                if spef.stat().st_size == 0:
                    raise ValueError(f"SPEF file is empty: {spef}")
        elif isinstance(self.spef_files, Path):
            if not self.spef_files.exists():
                raise FileNotFoundError(f"SPEF file not found: {self.spef_files}")
            if self.spef_files.stat().st_size == 0:
                raise ValueError(f"SPEF file is empty: {self.spef_files}")
        
        if not isinstance(self.delay_type_str, str):
            raise TypeError("delay_type_str must be a string.")
        if not isinstance(self.debug, bool):
            raise TypeError("debug must be a boolean.")
    
    def _call_external(self, executable: str, args: list[str] = [], 
                       stdin_data: str = "", debug: bool = False) -> subprocess.CompletedProcess:
        """
        Calls an external executable with given arguments and stdin data.
        Captures the output and checks for errors.
        Args:
            executable (str): The path to the executable to run.
            args (list[str]): List of arguments to pass to the executable.
            stdin_data (str): Data to send to the executable's stdin.
        Returns:
            subprocess.CompletedProcess: The result of the subprocess call.
        Raises:
            RuntimeError: If the external command fails.
        """
        
        if debug:
            print("Debug mode enabled for external command.")
            print(f"Calling external command: {executable} {' '.join(args)}")
            print(f"With stdin data:\n{stdin_data}")
            result = subprocess.run(
                [executable, *args],
                input=stdin_data,   
                text=True,                   
            )
        else:
            result = subprocess.run(
                [executable, *args],
                input=stdin_data,   
                text=True,            
                capture_output=True, 
                check=False,          
            )
        
        if result.returncode != 0:
            raise RuntimeError(f"Command '{' '.join([executable, *args])}' failed with error: {result.stderr}")
        return result
    
    ### Protected methods (STA connection Interface) ###
        
    def _generate_sdf_opensta(self) -> Path:
        """
        Generates an temporary SDF file from the Verilog gate-level netlist using OpenSTA.
        The SDF file is created in a temporary location and deleted after use.
        Returns:
            Path: The path to the generated SDF file.
        """
        
        sta_tcl_script: str = ""
        if isinstance(self.liberty_files, Path):
            sta_tcl_script += f"read_liberty {self.liberty_files}\n"
        else:
            for lib in self.liberty_files:
                sta_tcl_script += f"read_liberty {lib}\n"
        sta_tcl_script += f"read_verilog {self.verilog_netlist}\n"
        sta_tcl_script += f"link_design {self.top_name}\n"
        if self.spef_files is not None:
            if isinstance(self.spef_files, Path):
                sta_tcl_script += f"read_spef {self.spef_files}\n"
            elif isinstance(self.spef_files, list):
                for spef in self.spef_files:
                    sta_tcl_script += f"read_spef {spef}\n"
        sta_tcl_script += "write_sdf {}\n".format("{sdf_path}")
        sta_tcl_script += "exit\n"
        
        fd, path = tempfile.mkstemp(prefix="sta_", suffix=".sdf")
        os.close(fd) 
        
        if self.debug:
            print(f"Generating SDF file at temporary path: {path}")
        
        self._call_external(
            self.sta_executable,
            stdin_data=sta_tcl_script.format(sdf_path=path),
            debug=self.debug
        )  
        
        with open(path, "r") as f:
            content: str = f.read()
            if len(content) == 0:
               os.remove(path)
               raise RuntimeError("Failed to generate SDF file using OpenSTA. No content in SDF file.")
        
        if path is None:
            raise RuntimeError("Failed to generate SDF file using OpenSTA. No SDF file created.")        
       
        return Path(path)
    
    ### Public methods ###
    
    def get_raw_verilog_netlist_data(self) -> str:
        """
        Returns the raw Verilog netlist content as a string.
        Returns:
            str: The content of the Verilog netlist file.
        """
        return self.verilog_netlist_content

    
    def resolve_hier_pin(self, hier_pin_path: str) -> list[str]:
        """
        Parse a structural Verilog netlist and resolve a hierarchical pin path
        like "inst1/inst2/A0" down to all leaf std-cell pins connected to it.
        
        Returns a list of hierarchical pin paths (strings).
        
        Limitations:
        - Expects gate-level, structural Verilog: module/endmodule + simple instances
          of the form: CellType inst_name ( .PIN(net), ... );
        - Ignores assign statements, generate blocks, functions, etc.
        - Assumes module port names are used as net names inside the module.
        Args:
            hier_pin_path (str): Hierarchical pin path in the format "inst1/inst2/pin".
        Returns:
            list[str]: List of resolved leaf pin paths.
        """
        
        sep = self.get_hier_sep()
        hier_pin_path: str = f"{self.top_name}{sep}{hier_pin_path}"
        verilog_src: str = self.verilog_netlist_content
        
        # ------------------------------------------------------------------
        # Strip comments: /* ... */ and // ...
        # ------------------------------------------------------------------
        src_no_block = re.sub(r'/\*.*?\*/', '', verilog_src, flags=re.S)
        src_clean = re.sub(r'//.*?$', '', src_no_block, flags=re.M)

        # ------------------------------------------------------------------
        # Parse modules and their instances
        # modules[name] = { "instances": [ { "type": ..., "name": ..., "conns": {pin: net} }, ... ] }
        # ------------------------------------------------------------------
        modules = {}

        module_pattern = re.compile(
            r'\bmodule\b\s+([A-Za-z_][\w$]*)\b(.*?)\bendmodule\b',
            flags=re.S
        )

        # Very simple instance pattern: CellType inst_name ( .PIN(net), ... );
        # This will also match the module header "module name (...);" but we filter it out.
        inst_pattern = re.compile(
            r'([A-Za-z_][\w$]*)\s+([A-Za-z_][\w$]*)\s*\((.*?)\);\s*',
            flags=re.S
        )

        reserved_types = {
            "module", "input", "output", "inout", "wire", "reg", "tri", "tri0", "tri1",
            "supply0", "supply1", "parameter", "localparam", "assign", "always",
            "initial", "generate", "endgenerate", "if", "for", "case", "function", "task"
        }

        pin_net_pattern = re.compile(r'\.\s*([\w$]+)\s*\(\s*([^)]+?)\s*\)')

        for m in module_pattern.finditer(src_clean):
            mod_name = m.group(1)
            mod_body = m.group(2)
            instances = []

            for im in inst_pattern.finditer(mod_body):
                cell_type, inst_name, conn_str = im.groups()

                # Skip "instances" that are actually keywords, e.g. the module header
                if cell_type in reserved_types:
                    continue

                conns = {}
                for pin, net in pin_net_pattern.findall(conn_str):
                    net = net.strip()
                    conns[pin] = net

                instances.append({
                    "type": cell_type,
                    "name": inst_name,
                    "conns": conns,
                })

            modules[mod_name] = {"instances": instances}

        # ------------------------------------------------------------------
        # Parse hierarchical pin path: Top/inst1/inst2/.../pin
        # ------------------------------------------------------------------
        parts = hier_pin_path.split(sep)
        if len(parts) < 3:
            raise ValueError(
                f"Hierarchical pin path must be 'Top{sep}inst{sep}...{sep}pin', got: {hier_pin_path!r}"
            )

        top_module = parts[0]
        inst_chain = parts[1:-1]
        target_pin = parts[-1]

        if top_module not in modules:
            raise KeyError(f"Top module {top_module!r} not found in netlist")

        # ------------------------------------------------------------------
        # Walk down the instance chain to find:
        # - the parent module of the last instance
        # - the last instance itself
        # - the child module type of that instance
        # ------------------------------------------------------------------
        curr_module = top_module
        prev_module = None
        last_inst = None
        hier_prefix = top_module

        for inst_name in inst_chain:
            prev_module = curr_module
            inst_list = modules.get(curr_module, {}).get("instances", [])
            last_inst = None
            for inst in inst_list:
                if inst["name"] == inst_name:
                    last_inst = inst
                    break
            if last_inst is None:
                raise KeyError(
                    f"Instance {inst_name!r} not found in module {curr_module!r}"
                )
            curr_module = last_inst["type"]
            hier_prefix += f"{sep}" + inst_name

        if last_inst is None or prev_module is None:
            raise ValueError(
                f"Path {hier_pin_path!r} does not contain a valid instance chain"
            )

        # last_inst is the instance whose pin we are addressing
        if target_pin not in last_inst["conns"]:
            raise KeyError(
                f"Pin {target_pin!r} not found on instance {last_inst['name']!r} "
                f"in module {prev_module!r}"
            )

        # Parent net (in prev_module) connected to this pin - not strictly needed for
        # the downward traversal, but useful to check things.
        parent_net = last_inst["conns"][target_pin]

        child_module = curr_module  # type of the last instance
        child_net = target_pin      # assume port name == internal net name inside child

        # If the instance itself is already a leaf std-cell (no module definition),
        # then the endpoint is just that pin.
        if child_module not in modules:
            prefix = top_module + f"{sep}"
            # strip top module name from hierarchical prefix
            pp = hier_prefix[len(prefix):] if hier_prefix.startswith(prefix) else hier_prefix
            return [f"{pp}{sep}{target_pin}"]

        # ------------------------------------------------------------------
        # Recursively traverse down the hierarchy from (child_module, child_net)
        # ------------------------------------------------------------------
        visited = set()

        def traverse(mod_name, net_name, prefix):
            """
            In module `mod_name`, find all instance pins that are connected to `net_name`.
            For std-cell instances (type not in modules), record leaf paths.
            For submodules (type in modules), recurse into that submodule, using the
            pin name as the net name inside the child.
            """
            key = (mod_name, net_name, prefix)
            if key in visited:
                return []
            visited.add(key)

            results = []
            inst_list = modules.get(mod_name, {}).get("instances", [])

            for inst in inst_list:
                inst_type = inst["type"]
                inst_name = inst["name"]
                for pin, net in inst["conns"].items():
                    if net != net_name:
                        continue

                    new_prefix = f"{prefix}{sep}{inst_name}"

                    # Leaf std-cell: no module definition for its type
                    if inst_type not in modules:
                        results.append(f"{new_prefix}{sep}{pin}")
                    else:
                        # Submodule: descend, assuming port name == internal net name
                        results.extend(traverse(inst_type, pin, new_prefix))
            
            return results

        leaf_pins = traverse(child_module, child_net, hier_prefix)
        
        # strip top module name
        prefix = top_module + f"{sep}"
        leaf_pins = [
            p[len(prefix):] if p.startswith(prefix) else p
            for p in leaf_pins
        ]
        
        return leaf_pins
    
    def find_verilog_modules_regex(self, name_pattern: str) -> list[str]:
        """
        Parse a Verilog netlist and return all module names that match the given regex pattern.
        Args:
            verilog_src (str): The Verilog netlist content as a string.
            name_pattern (str): Regular expression pattern to match module names.
        Returns:
            list[str]: List of module names matching the regex pattern.
        """
        
        verilog_src:str = self.verilog_netlist_content
        
        # Strip block and line comments
        src = re.sub(r'/\*.*?\*/', '', verilog_src, flags=re.DOTALL)       # /* ... */
        src = re.sub(r'//.*?$', '', src, flags=re.MULTILINE)               # // ...

        #    Regex for module declaration:
        #    module <name> [#(...)] (
        module_decl_re = re.compile(
            r'^\s*module\s+([A-Za-z_]\w*)\s*'      # module name (group 1)
            r'(?:#\s*\([^()]*\))?'                 # optional parameter list #(...)
            r'\s*\(',                              # opening parenthesis of port list
            flags=re.MULTILINE
        )

        name_re = re.compile(name_pattern)
        found: list[str] = []
        for m in module_decl_re.finditer(src):
            name = m.group(1)
            if name_re.search(name):
                found.append(name)
        return found
    
    def find_instance_paths_by_regex(self, inst_regex: str, filter_regex: str | None = None) -> list[str]:
        """
        Parse a structural Verilog netlist, walk the hierarchy from `top_module`,
        and return all hierarchical instance paths (without the top module name) whose
        path matches `inst_regex`.
        Args:
            inst_regex (str): Regular expression to match hierarchical instance paths.
            filter_regex (str | None): Optional regular expression to filter the matched instance paths.
        Returns:
            list[str]: List of hierarchical instance paths matching the regex.
        """
       
        top_module = self.top_name
        sep = self.get_hier_sep()
        verilog_src: str = self.verilog_netlist_content

        # -------------------------------------------------------------
        # Remove comments: /* ... */ and // ...
        # -------------------------------------------------------------
        src_no_block = re.sub(r'/\*.*?\*/', '', verilog_src, flags=re.S)
        src_clean = re.sub(r'//.*?$', '', src_no_block, flags=re.M)

        # -------------------------------------------------------------
        # Parse modules and their instances (type + name only)
        # -------------------------------------------------------------
        # modules[name] = { "instances": [ { "type": ..., "name": ... }, ... ] }
        modules = {}

        module_pattern = re.compile(
            r'\bmodule\b\s+([A-Za-z_][\w$]*)\b(.*?)\bendmodule\b',
            flags=re.S,
        )

        # Simple instance pattern: CellType inst_name ( ... );
        inst_pattern = re.compile(
            r'([A-Za-z_][\w$]*)\s+([A-Za-z_][\w$]*)\s*\(',
            flags=re.S,
        )

        reserved_types = {
            "module", "input", "output", "inout", "wire", "reg", "tri", "tri0", "tri1",
            "supply0", "supply1", "parameter", "localparam", "assign", "always",
            "initial", "generate", "endgenerate", "if", "for", "case", "function", "task"
        }

        for m in module_pattern.finditer(src_clean):
            mod_name = m.group(1)
            mod_body = m.group(2)
            instances = []

            for im in inst_pattern.finditer(mod_body):
                cell_type, inst_name = im.groups()

                # Skip things that look like keywords / non-instances
                if cell_type in reserved_types:
                    continue

                instances.append({
                    "type": cell_type,
                    "name": inst_name,
                })

            modules[mod_name] = {"instances": instances}

        # -------------------------------------------------------------
        # Check that top_module exists
        # -------------------------------------------------------------
        if top_module not in modules:
            raise KeyError(f"Top module {top_module!r} not found in netlist")

        # -------------------------------------------------------------
        # DFS from top_module, build hierarchical instance paths
        # (without including the top module name itself)
        # -------------------------------------------------------------
        pattern = re.compile(inst_regex)
        results = []

        def dfs(mod_name: str, path_parts):
            """
            mod_name: current module type
            path_parts: list of instance names from *below* top, e.g. ["inst_sw_matrix", "inst_cus_mux81_buf_NN4BEG0"]
            """
            inst_list = modules.get(mod_name, {}).get("instances", [])
            for inst in inst_list:
                inst_name = inst["name"]
                new_parts = path_parts + [inst_name]
                hier_path = sep.join(new_parts)  # WITHOUT the top module name

                # Regex is matched on this hierarchical path
                if pattern.search(hier_path):
                    results.append(hier_path)

                # If this instance's type is another module, recurse into it
                inst_type = inst["type"]
                if inst_type in modules:
                    dfs(inst_type, new_parts)

        dfs(top_module, [])
        
        if filter_regex is not None:
            filter_pattern = re.compile(filter_regex)
            results = [p for p in results if filter_pattern.search(p)]
        
        return results
    
    
    def find_instances_with_all_nets(self, module_name: str, nets: list[str]) -> list[str]:
        """
        Scan a Verilog netlist and return instance names inside `module_name`
        that have *all* nets in `nets` connected to any of their pins.

        - Only looks at direct instances inside the given module (no hierarchy).
        - Assumes gate-level style instantiations like:

            cell_type inst_name (
                .A0(net1),
                .A1(net2),
                ...
            );

        Args:
            module_name:  Name of the module to search in.
            nets:         List of net names that must all appear on the instance.

        Returns:
            List of instance names (strings).
        """
        
        text = self.verilog_netlist_content

        # Extract the reference module body: module <name> ... endmodule
        mod_pattern = re.compile(
            rf"module\s+{re.escape(module_name)}\b(.*?endmodule)",
            re.DOTALL
        )
        m = mod_pattern.search(text)
        if not m:
            raise ValueError(f"Module {module_name!r} not found in netlist content")

        module_body = m.group(1)

        # Remove simple // comments to avoid bogus matches
        module_body = re.sub(r"//.*?$", "", module_body, flags=re.MULTILINE)

        # Find instantiations:  cell_type inst_name ( ... );
        inst_pattern = re.compile(
            r"""
            (?P<cell>\w+)        # cell type
            \s+
            (?P<inst>\w+)        # instance name
            \s*
            \(
                (?P<pins>[^;]*?) # pin connections until the semicolon
            \)
            \s*;
            """,
            re.DOTALL | re.VERBOSE,
        )

        # Pin connection pattern: .PIN_NAME(NET_NAME)
        pin_conn_pattern = re.compile(
            r"\.\s*\w+\s*\(\s*([^\s\)]+)\s*\)"
        )

        target_nets = set(nets)
        matching_instances: list[str] = []

        for im in inst_pattern.finditer(module_body):
            inst_name = im.group("inst")
            pins_block = im.group("pins")

            # Collect all nets connected on this instance
            nets_on_inst = set(
                pin_conn_pattern.findall(pins_block)
            )

            if target_nets.issubset(nets_on_inst):
                matching_instances.append(inst_name)

        return matching_instances
    
    def find_instances_paths_with_all_nets(self, module_name: str, nets: list[str], 
                                           filter_regex: str | None = None) -> list[str]:
        """
        Combines `find_instances_with_all_nets` and `find_instance_paths_by_regex` to return
        hierarchical instance paths (without top module name) for instances inside `module_name`
        that have *all* nets in `nets` connected to any of their pins.
        Args:
            module_name:  Name of the module to search in.
            nets:         List of net names that must all appear on the instance.
            filter_regex: Optional regular expression to filter the matched instance paths.
        Returns:
            List of hierarchical instance paths (strings).
        
        """
        inst_hier_paths = []
        insts = self.find_instances_with_all_nets(module_name, nets)
        for inst in insts:
            paths = self.find_instance_paths_by_regex(rf"{re.escape(inst)}$", filter_regex=filter_regex)
            inst_hier_paths.extend(paths)
        return inst_hier_paths
        
    def net_to_pin_paths_for_instance(self, hier_inst_path: str) -> dict[str, str]:
        """
        Given a hierarchical instance path like:
            "Inst_LUT4AB_switch_matrix/inst_cus_mux161_buf_JE2BEG3"

        and a gate-level Verilog netlist, return a mapping:
            net_name -> "\\<hier_inst_path\\>/\\<pin_name\\>"

        Only the leaf instance is resolved (no further hierarchy).

        Example output:
            {
            "N1END2": "Inst_LUT4AB_switch_matrix/inst_cus_mux161_buf_JE2BEG3/A0",
            "N2END4": "Inst_LUT4AB_switch_matrix/inst_cus_mux161_buf_JE2BEG3/A1",
            ...
            }
            
        Args:
            hier_inst_path (str): Hierarchical instance path.
        Returns:
            dict(str, str): Mapping from net names to pins keep hierarchy (no further hierarchy).
        Raises:
            ValueError: If the top module or instance is not found in the netlist.
        """

        text = self.verilog_netlist_content
        top_module = self.top_name
        sep = self.get_hier_sep()

        # Collect all modules: name -> body text
        module_pattern = re.compile(
            r"module\s+(\w+)\b(.*?endmodule)",
            re.DOTALL,
        )

        modules = {}
        for m in module_pattern.finditer(text):
            name = m.group(1)
            body = m.group(2)
            modules[name] = body

        if top_module not in modules:
            raise ValueError(f"Top module {top_module!r} not found in netlist")

        # Pattern for instances inside a module
        # Handles: cell_type [#(...)] inst_name ( ... );
        inst_pattern = re.compile(
            r"""
            (?P<cell>\w+)                 # cell/module type
            \s+
            (?P<inst>\w+)                 # instance name
            \s*
            \(
                (?P<pins>[^;]*?)          # pin connections until ';'
            \)
            \s*;
            """,
            re.DOTALL | re.VERBOSE,
        )

        # Pattern for pin connections: .PIN(NET)
        pin_conn_pattern = re.compile(
            r"\.\s*(?P<pin>\w+)\s*\(\s*(?P<net>[^\s\)]+)\s*\)"
        )

        # Walk the hierarchy down to the leaf instance 
        segments = hier_inst_path.split(sep)
        current_module = top_module

        for depth, inst_name in enumerate(segments):
            body = modules.get(current_module)
            if body is None:
                raise ValueError(f"Module {current_module!r} not found while resolving {hier_inst_path!r}")

            found = False
            cell_type = None
            pins_block = None

            for m in inst_pattern.finditer(body):
                if m.group("inst") == inst_name:
                    cell_type = m.group("cell")
                    pins_block = m.group("pins")
                    found = True
                    break

            if not found:
                raise ValueError(
                    f"Instance {inst_name!r} not found inside module {current_module!r}"
                )

            # If not yet at the leaf, descend into the instance's module type
            if depth < len(segments) - 1:
                current_module = cell_type
            else:
                # Leaf instance: parse its pin connections
                net_to_path: dict[str, str] = {}
                for pm in pin_conn_pattern.finditer(pins_block):
                    pin = pm.group("pin")
                    net = pm.group("net")
                    # Note: if the same net appears on multiple pins, last one wins
                    net_to_path[net] = f"{hier_inst_path}{sep}{pin}"
                return net_to_path

        raise RuntimeError("Unexpected end of hierarchy resolution")
    
    def net_to_pin_paths_for_instance_resolved(self, hier_inst_path: str) -> dict[str, list[str]]:
        """
        Given a hierarchical instance path like:
            "Inst_LUT4AB_switch_matrix/inst_cus_mux161_buf_JE2BEG3"
        and a gate-level Verilog netlist, return a mapping:
            net_name -> [ "\\<full_hier_pin_path1\\>", "\\<full_hier_pin_path2\\>", ... ]
        where each full hierarchical pin path is resolved down to leaf std-cell pins.
        Args:
            hier_inst_path (str): Hierarchical instance path.
        Returns:
            dict(str, list[str]): Mapping from net names to lists of resolved leaf pin paths.
        """
        resolved_paths: dict[str, list[str]] = {}
        net_to_pin = self.net_to_pin_paths_for_instance(hier_inst_path)
        for net, pin_path in net_to_pin.items():
            leaf_pins = self.resolve_hier_pin(pin_path)
            resolved_paths[net] = leaf_pins
        return resolved_paths
    
    def nearest_port_from_pin(self, hier_pin_path: str, reverse: bool = False, num_ports: int = 1) -> list[str]:
        """
        Given a hierarchical pin path like "inst1/inst2/A0", find the nearest
        top-level port connected to the same net as that pin.
        Depending on `reverse`, the search is done towards input ports (reverse=True)
        or output ports (reverse=False).
        
        Args:
            hier_pin_path (str): Hierarchical pin path.
            reverse (bool): If True, search towards input ports; if False, towards output ports.
            num_ports (int): Number of nearest ports to return. if less ports are found, return all found,
            which can be less than `num_ports`.
        
        Returns:
            list(str): Hierarchical paths of the nearest top-level ports.
        """
        
        # Experimental: Use existing path_to_nearest_target_sentinel method
        #path_without_sentinel, closest_target, dist = self.path_to_nearest_target_sentinel(
        #    hier_pin_path,
        #    self.get_input_ports() if reverse else self.get_output_ports(),
        #    reverse=reverse
        #)
        #
        #return [closest_target] if closest_target is not None else []
        
        # Use NetworkX shortest path to find nearest port
        # Depending on `reverse`, search towards inputs or outputs
        # If reverse=True, search towards inputs (for setup analysis)
        # If reverse=False, search towards outputs (for hold analysis)
        if reverse:
            dist = nx.single_source_shortest_path_length(self.graph.reverse(copy=True), hier_pin_path)
            leaf_dists = [(v, d) for v, d in dist.items() if v in self.get_input_ports()]
        else:  
            dist = nx.single_source_shortest_path_length(self.graph, hier_pin_path)
            leaf_dists = [(v, d) for v, d in dist.items() if v in self.get_output_ports()]
            
        if len(leaf_dists) == 0:
            return []
        
        # already sorted by distance from NetworkX
        # leaf_dists.sort(key=lambda x: x[1])
        return [leaf_dists[i][0] for i in range(min(num_ports, len(leaf_dists)))]
        
    def nearest_ports_from_instance_pin_nets(self, inst_path: str, 
                                             reverse: bool = False, 
                                             num_ports: int = 1) -> tuple[dict[str, list[str]], list[str]]:
        """
        Given a hierarchical instance path like "inst1/inst2", find the nearest
        top-level ports connected to the same nets as the instance's pins.
        Depending on `reverse`, the search is done towards input ports (reverse=True)
        or output ports (reverse=False).
        
        Args:
            inst_path (str): Hierarchical instance path.
            reverse (bool): If True, search towards input ports; if False, towards output ports.
            num_ports (int): Number of nearest ports to return per pin. if less ports are found, return all found,
            which can be less than `num_ports`.
        Returns:
            tuple[dict(str, list[str]), list[str]]: Mapping from instance net names to lists of nearest top-level port paths.
                                                    The list is sorted starting from the nearest ports.
        """
        
        net_to_pin: dict[str, list[str]] = self.net_to_pin_paths_for_instance_resolved(inst_path)
        pin_to_nearest_ports: dict[str, list[str]] = {}
        pin_to_nearest_ports_list: list[str] = []
        for net, pin_paths in net_to_pin.items():
            if pin_paths is None or len(pin_paths) == 0:
                continue 
            # Maybe not only use the first pin path for nearest port search
            nearest_ports = self.nearest_port_from_pin(pin_paths[0], reverse=reverse, num_ports=num_ports)
            pin_to_nearest_ports_list.extend(nearest_ports)
            pin_to_nearest_ports[net] = nearest_ports
        
        # Remove duplicates while preserving order
        return pin_to_nearest_ports, list(dict.fromkeys(pin_to_nearest_ports_list))
    
    def get_instance_pins(self, hier_inst_path: str) -> list[str]:
        """
        Given a hierarchical instance path like:
            "Inst_LUT4AB_switch_matrix/inst_cus_mux161_buf_JE2BEG3" 
        and a gate-level Verilog netlist, return a list of pin names
        connected to that instance, in the order they appear in the instantiation.
        Args:
            hier_inst_path (str): Hierarchical instance path.
        Returns:
            list[str]: List of pin names connected to the instance.
        Raises:
            ValueError: If the top module or instance is not found in the netlist.
        """
        
        verilog_src : str = self.verilog_netlist_content
        top_module : str = self.top_name
        sep : str = self.get_hier_sep()

        # Strip comments to avoid bogus matches ---
        # Remove block comments /* ... */
        text = re.sub(r"/\*.*?\*/", "", verilog_src, flags=re.DOTALL)
        # Remove line comments // ...
        text = re.sub(r"//.*?$", "", text, flags=re.MULTILINE)

        # --- 1) Collect all modules: name -> body text ---
        module_pattern = re.compile(
            r"module\s+(\w+)\b(.*?endmodule)",
            re.DOTALL,
        )

        modules = {}
        for m in module_pattern.finditer(text):
            name = m.group(1)
            body = m.group(2)
            modules[name] = body

        if top_module not in modules:
            raise ValueError(f"Top module {top_module!r} not found")

        # Pattern for instances inside a module ---
        # Handles: cell_type [#(...)] inst_name ( ... );
        inst_pattern = re.compile(
            r"""
            (?P<cell>\w+)                 # cell/module type
            \s+
            (?P<inst>\w+)                 # instance name
            \s*
            \(
                (?P<pins>[^;]*?)          # pin connections until ';'
            \)
            \s*;
            """,
            re.DOTALL | re.VERBOSE,
        )

        # Pattern for pin connections: .PIN(NET) ---
        pin_conn_pattern = re.compile(
            r"\.\s*(?P<pin>\w+)\s*\(\s*(?P<net>[^\s\)]+)\s*\)"
        )

        # Walk the hierarchy down to the leaf instance ---
        segments = hier_inst_path.split(sep)
        current_module = top_module

        for depth, inst_name in enumerate(segments):
            body = modules.get(current_module)
            if body is None:
                raise ValueError(
                    f"Module {current_module!r} not found while resolving {hier_inst_path!r}"
                )

            found = False
            cell_type = None
            pins_block = None

            # find the instance in the current module
            for m in inst_pattern.finditer(body):
                if m.group("inst") == inst_name:
                    cell_type = m.group("cell")
                    pins_block = m.group("pins")
                    found = True
                    break

            if not found:
                raise ValueError(
                    f"Instance {inst_name!r} not found inside module {current_module!r}"
                )

            # If not yet at the leaf, descend into the instance's module type
            if depth < len(segments) - 1:
                current_module = cell_type
            else:
                # Leaf instance: parse its pin connections
                pins_in_order: list[str] = []
                for pm in pin_conn_pattern.finditer(pins_block):
                    pin_name = pm.group("pin")
                    pins_in_order.append(pin_name)
                return pins_in_order

        # Should never get here
        raise RuntimeError("Hierarchy resolution fell through unexpectedly")

    def get_module_instance_nets(self, module_name: str) -> dict[str, list[str]]:
        """
        Parse a Verilog netlist given as text and extract, for a given module,
        all instance names and the nets connected to each instance.

        Args:
            module_name: Name of the module to inspect.

        Returns:
            Dict mapping:
                instance_name -> [net1, net2, net3, ...]
            where each list contains all nets connected to that instance
            (order is the order of the pin connections in the instantiation).
        """

        verilog_src: str = self.verilog_netlist_content
        
        # Strip comments so patterns don't get confused ---
        # Remove block comments /* ... */
        text = re.sub(r"/\*.*?\*/", "", verilog_src, flags=re.DOTALL)
        # Remove line comments // ...
        text = re.sub(r"//.*?$", "", text, flags=re.MULTILINE)

        # Extract the body of the target module: module <name> ... endmodule
        module_pattern = re.compile(
            r"module\s+(\w+)\b(.*?endmodule)",
            re.DOTALL,
        )

        target_body = None
        for m in module_pattern.finditer(text):
            name = m.group(1)
            body = m.group(2)
            if name == module_name:
                target_body = body
                break

        if target_body is None:
            raise ValueError(f"Module {module_name!r} not found in provided Verilog source")

        # Instance pattern inside a module
        # Matches:
        #   cell_type inst_name ( ... );
        inst_pattern = re.compile(
            r"""
            (?P<cell>\w+)                 # cell/module type
            \s+
            (?P<inst>\w+)                 # instance name
            \s*
            \(
                (?P<pins>[^;]*?)          # pin connections up to ';'
            \)
            \s*;
            """,
            re.DOTALL | re.VERBOSE,
        )

        # Pin connection pattern: .PIN(NET) 
        # NET can be e.g. N1END3, JE2BEG0, ConfigBits[328], etc.
        pin_conn_pattern = re.compile(
            r"\.\s*(?P<pin>\w+)\s*\(\s*(?P<net>[^\s\)]+)\s*\)"
        )

        instance_to_nets: dict[str, list[str]] = {}

        # Find all instantiations and their nets 
        for m in inst_pattern.finditer(target_body):
            inst_name = m.group("inst")
            pins_block = m.group("pins")

            nets: list[str] = []
            for pm in pin_conn_pattern.finditer(pins_block):
                net = pm.group("net")
                nets.append(net)

            instance_to_nets[inst_name] = nets

        return instance_to_nets
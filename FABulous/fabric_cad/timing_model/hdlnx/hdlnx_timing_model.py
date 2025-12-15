#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# This module convertes verilog RTL into a verilog gate-level netlist using an external synthesis tool.
# In this context a sysnthesis tool can be anything that can convert RTL verilog into gate-level verilog,
# that means also tools that can do backend design steps like technology mapping and place&route.
# It then uses the VerilogGateLevelTimingGraph class to generate a timing graph from the gate-level netlist.

from pathlib import Path
import tempfile, os

from .verilog_gate_level import VerilogGateLevelTimingGraph

class HdlnxTimingModel(VerilogGateLevelTimingGraph):
    """
    Class to generate a timing graph from Verilog RTL by first synthesizing it into a gate-level netlist
    using an external synthesis tool, and then using the VerilogGateLevelTimingGraph class to generate the timing graph.
    
    Supported synthesis tools:
    - Yosys, keyword: "yosys"
    
    Supported static timing analysis (STA) tools:
    - OpenSTA, keyword: "opensta"
    
    Attributes:
        config (dict): Configuration dictionary containing the following keys:
    ```python
    {
        verilog_files: list[Path] | Path,     # List of Verilog RTL files or a single Verilog RTL file
        liberty_files: list[Path] | Path,     # List of Liberty files or a single Liberty file
        top_name: str,                        # Top module name
        sta_executable: str,                  # Path to the STA tool executable
        sta_program: str,                     # STA tool program name
        synth_program: str,                   # Synthesis tool program name
        synth_executable: str,                # Path to the synthesis tool executable
        spef_files: list[Path] | Path | None, # SPEF files for SDF (only for gate-level netlists)
        delay_type_str: str,                  # Delay type string for STA (default: "max_all")
        hier_sep: str | None,                 # Hierarchy separator (default: None)
        is_gate_level: bool,                  # Gate-level netlist flag (default: False)
        debug: bool                           # Debug mode flag (default: False)
        
        # Additional keys for Yosys synthesis tool:
        
        techmap_files: list[Path] | None,          # List of techmap files or None
        tiehi_cell_and_port: str | None,           # Tie-high cell and port string or None
        tielo_cell_and_port: str | None,           # Tie-low cell and port string or None
        min_buf_cell_and_ports: str | None,        # Minimum buffer cell and ports string or None
        flat: bool                                 # Flatten hierarchy flag (default: False)
    }
    ```
    """
    
    def __init__(self, config: dict):
        self.config: dict = config
        self.json_netlist: str | None = None
        self._check_config()
        
        # Register supported synthesis tools.
        # The value must be a function that points to the respective synthesis function
        # which always returns the (temp) path to the generated gate-level netlist file.
        self.registered_synth_tools: dict[str, Path] = {
            "yosys": self._generate_gate_level_netlist_yosys()
        }
        
        self._apply_config()
    
    ### Protected Methods ###
    
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
        
    def _check_config(self):
        """
        Checks if the configuration dictionary contains all required global keys.
        Raises:
            KeyError: If any required key is missing from the configuration dictionary.
            TypeError: If any key has an incorrect type.
            FileNotFoundError: If any specified file does not exist.
            ValueError: If any specified file is empty.
        """
        
        # Register required configuration keys and their default values
        self._add_config_keys(new_keys= {
            "verilog_files": "required",     # list[Path] | Path
            "liberty_files": "required",     # catched in parent class, list[Path] | Path
            "top_name": "required",          # catched in parent class, str
            "sta_executable": "required",    # catched in parent class, str
            "sta_program": "required",       # catched in parent class, str
            "synth_program": "required",     # str
            "synth_executable": "required",  # str
            "spef_files": None,              # catched in parent class, list[Path] | Path | None
            "delay_type_str": "max_all",     # catched in parent class, str
            "hier_sep": None,                # catched in parent class, str
            "is_gate_level": False,          # bool
            "debug": False                   # catched in parent class, bool
        }, msg="global")
            
        if not isinstance(self.config["verilog_files"], (list, Path)):
            raise TypeError("verilog_files must be a list of pathlib.Path objects or a single pathlib.Path object.")
        if isinstance(self.config["verilog_files"], list):
            for vf in self.config["verilog_files"]:
                if not isinstance(vf, Path):
                    raise TypeError("Each item in verilog_files list must be a pathlib.Path object.")
                if not vf.exists():
                    raise FileNotFoundError(f"Verilog file not found: {vf}")
                if vf.stat().st_size == 0:
                    raise ValueError(f"Verilog file is empty: {vf}")
        else:
            if not isinstance(self.config["verilog_files"], Path):
                raise TypeError("verilog_files must be a list of pathlib.Path objects or a single pathlib.Path object.")
            if not self.config["verilog_files"].exists():
                raise FileNotFoundError(f"Verilog file not found: {self.config['verilog_files']}")
            if self.config["verilog_files"].stat().st_size == 0:
                raise ValueError(f"Verilog file is empty: {self.config['verilog_files']}")
        
        if not isinstance(self.config["is_gate_level"], bool):
            raise TypeError("is_gate_level must be a boolean value.")

        if self.config["is_gate_level"] == True and not isinstance(self.config["verilog_files"], Path):
            raise TypeError("When is_gate_level is True, verilog_files must be a single pathlib.Path object."
                            " Multiple Verilog files are not supported for gate-level netlists.")
            
        if not isinstance(self.config["synth_executable"], str):
            raise TypeError("synth_executable must be a string.")
        if not isinstance(self.config["synth_program"], str):
            raise TypeError("synth_program must be a string.")
        
        if self.config["is_gate_level"] == False and self.config["spef_files"] is not None:
            raise ValueError("SDF back-annotation via SPEF files is only supported for gate-level netlists."
                             " Please set is_gate_level to True when using a SPEF file.")      
            
    def _apply_config(self):
        """
        Applies the configuration by synthesizing the Verilog RTL into a gate-level netlist
        using the specified synthesis tool, and then initializing the parent VerilogGateLevelTimingGraph
        class with the generated gate-level netlist.
        Raises:
            NotImplementedError: If the specified synthesis tool is not supported.
        """
        
        if self.config["is_gate_level"]:
            # Directly use the provided gate-level netlist
            super().__init__(verilog_netlist=self.config["verilog_files"], liberty_files=self.config["liberty_files"], 
                             top_name=self.config["top_name"], sta_executable=self.config["sta_executable"], 
                             sta_program=self.config["sta_program"], spef_files=self.config["spef_files"], 
                             delay_type_str=self.config["delay_type_str"], hier_sep=self.config["hier_sep"], 
                             debug=self.config["debug"])
        else:
            if self.config["synth_program"] in self.registered_synth_tools:
                tmp_gate_level_netlist_path: Path = self.registered_synth_tools[self.config["synth_program"]]
            else:
                raise NotImplementedError(f"Synthesis tool '{self.config['synth_program']}' is not supported.")
            
            # Initialize the parent VerilogGateLevelTimingGraph class with the generated gate-level netlist
            super().__init__(verilog_netlist=tmp_gate_level_netlist_path, liberty_files=self.config["liberty_files"], 
                             top_name=self.config["top_name"], sta_executable=self.config["sta_executable"], 
                             sta_program=self.config["sta_program"], spef_files=self.config["spef_files"],
                             delay_type_str=self.config["delay_type_str"], hier_sep=self.config["hier_sep"], 
                             debug=self.config["debug"])
            
            #### Clean up temporary gate-level netlist file ####
            os.remove(tmp_gate_level_netlist_path)
    
    ### Protected methods (Synthesis connection Interface) ###
               
    def _generate_gate_level_netlist_yosys (self) -> Path:
        """
        Generates a temporary gate-level netlist from the Verilog RTL files using Yosys.
        The gate-level netlist is created in a temporary location and deleted after use.
        Returns:
            Path: Path to the generated temporary gate-level netlist file.
        """
        
        # Register required configuration keys and their default values
        self._add_config_keys(new_keys= {
            "techmap_files": None,          # list[Path] | None
            "tiehi_cell_and_port": None,    # str | None
            "tielo_cell_and_port": None,    # str | None
            "min_buf_cell_and_ports": None, # str | None
            "flat": False                   # bool
        }, msg="yosys")
        
               
        if self.config["techmap_files"] is not None:
            if not isinstance(self.config["techmap_files"], list):
                raise TypeError("techmap_files must be a list of pathlib.Path objects or None.")
            for tm in self.config["techmap_files"]:
                if not isinstance(tm, Path):
                    raise TypeError("Each item in techmap_files list must be a pathlib.Path object.")
                if not tm.exists():
                    raise FileNotFoundError(f"Techmap file not found: {tm}")
                if tm.stat().st_size == 0:
                    raise ValueError(f"Techmap file is empty: {tm}")
        
        if not isinstance(self.config["tiehi_cell_and_port"], (str, type(None))):
            raise TypeError("tiehi_cell_and_port must be a string or None.")
        if not isinstance(self.config["tielo_cell_and_port"], (str, type(None))):
            raise TypeError("tielo_cell_and_port must be a string or None.")
        if not isinstance(self.config["min_buf_cell_and_ports"], (str, type(None))):
            raise TypeError("min_buf_cell_and_ports must be a string or None.")
        if not isinstance(self.config["flat"], bool):
            raise TypeError("flat must be a boolean value.")
        
        if (self.config["tiehi_cell_and_port"] is None) ^ (self.config["tielo_cell_and_port"] is None):
            raise ValueError("Both tiehi_cell_and_port and tielo_cell_and_port must be specified together.")
        
        # Generate Yosys synthesis TCL script   
        synth_tcl_script: str = ""
        synth_tcl_script += f"yosys -import\n"
        if isinstance(self.config["liberty_files"], Path):
            synth_tcl_script += f"read_liberty -lib {self.config['liberty_files']}\n"
        else:
            for lib in self.config["liberty_files"]:
                synth_tcl_script += f"read_liberty -lib {lib}\n"
        if isinstance(self.config["verilog_files"], Path):
            synth_tcl_script += f"read_verilog -overwrite -sv {self.config['verilog_files']}\n"
        else:
            for vf in self.config["verilog_files"]:
                synth_tcl_script += f"read_verilog -overwrite -sv {vf}\n"
        if self.config["flat"]:
            synth_tcl_script += f"synth -flatten -top {self.config['top_name']}\n"
        else:
            synth_tcl_script += f"synth -top {self.config['top_name']}\n"
        synth_tcl_script += f"renames -top {self.config['top_name']}\n"
        synth_tcl_script += f"renames -wire\n"
        
        if self.config["techmap_files"] is not None:
            for tm in self.config["techmap_files"]:
                synth_tcl_script += f"techmap -map {tm}\n"
            synth_tcl_script += f"simplemap\n"
        
        synth_tcl_script += f"clockgate -liberty  {self.config['liberty_files'][0] if isinstance(
                            self.config['liberty_files'], list) else self.config['liberty_files']}\n"
        synth_tcl_script += f"dfflibmap -liberty  {self.config['liberty_files'][0] if isinstance(
                            self.config['liberty_files'], list) else self.config['liberty_files']}\n"
        synth_tcl_script += f"setundef -zero\n"
        synth_tcl_script += f"splitnets\n"
        
        if self.config["tiehi_cell_and_port"] is not None and self.config["tielo_cell_and_port"] is not None:
            synth_tcl_script += (f"hilomap -hicell {self.config['tiehi_cell_and_port']} "
                                          f"-locell {self.config['tielo_cell_and_port']}\n")
        if self.config["min_buf_cell_and_ports"] is not None:
            synth_tcl_script += f"insbuf -buf {self.config['min_buf_cell_and_ports']}\n"
        
        synth_tcl_script += f"tribuf\n"
        synth_tcl_script += f"abc -liberty {self.config['liberty_files'][0] if isinstance(
                            self.config['liberty_files'], list) else self.config['liberty_files']}\n"
        synth_tcl_script += f"opt -purge -full\n"
        synth_tcl_script += "write_verilog -noattr -noexpr {}\n".format("{synth_output_file}")
        synth_tcl_script += "write_json {}\n".format("{synth_output_json_file}")
        
        fd, path = tempfile.mkstemp(prefix="synth_verilog_", suffix=".v")
        os.close(fd) 
        
        fd, json_path = tempfile.mkstemp(prefix="synth_json_", suffix=".json")
        os.close(fd)
        
        if self.config["debug"]:
            print(f"Generating Synthesized Verilog file at temporary path: {path}")
            print(f"Generating Synthesized JSON file at temporary path: {json_path}")
        
        self._call_external(
            self.config["synth_executable"],
            stdin_data=synth_tcl_script.format(synth_output_file=path, synth_output_json_file=json_path),
            debug=self.config["debug"],
            args=["-C"]
        )
        
        with open(path, "r") as f:
            content: str = f.read()
            if len(content) == 0:
               os.remove(path)
               raise RuntimeError("Failed to generate gate-level netlist using Yosys. No content in netlist file.")
        if path is None:
            raise RuntimeError("Failed to generate gate-level netlist using Yosys. No netlist file created.")
        
        with open(json_path, "r") as f:
            self.json_netlist: str = f.read()
            if self.json_netlist is None or len(self.json_netlist) == 0:
                raise RuntimeError("Failed to generate JSON netlist using Yosys. No content in JSON netlist file.")   
        if json_path is None:
            raise RuntimeError("Failed to generate JSON netlist using Yosys. No JSON netlist file created.")
        os.remove(json_path)
        
        return Path(path)
    
    ### Public Methods ###
    
    def get_netlist_as_json(self) -> str:
        """
        Returns the Verilog netlist as a JSON string.
        Returns:
            str: JSON representation of the Verilog netlist.
        """
        if self.json_netlist is None:
            raise RuntimeError("Netlist JSON representation is not available. This depends on the tool flow used.")
        return self.json_netlist
    
    
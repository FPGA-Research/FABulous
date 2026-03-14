"""
Yosys Tool Interface, which uses Yosys to synthesize a Verilog design to a gate-level netlist 
and then uses an STA tool (e.g., OpenSTA) to analyze the netlist and generate an SDF file. 
The SDF file is then parsed to create a timing graph representation of the design. 
This module provides a high-level interface for performing synthesis and timing analysis 
using Yosys.
"""


from fabulous.fabric_cad.timing_model.tools.specification import SynthTool
from pathlib import Path
import tempfile, os
import subprocess
from loguru import logger


class YosysTool(SynthTool):
    """
    YosysTool is a synthesis tool interface that uses Yosys to synthesize Verilog 
    RTL into a gate-level netlist. It supports various synthesis options such as 
    techmapping, tie-high/low cell mapping, and buffer insertion. The generated gate-level 
    netlist can then be used for static timing analysis (STA) with tools like OpenSTA.
    """
    
    def __init__(
        self,
        synth_executable: Path | str,
        top_name: str | None = None,
        is_gate_level: bool = False,
        techmap_files: list[Path] | None = None,
        tiehi_cell_and_port: str | None = None,
        tielo_cell_and_port: str | None = None,
        min_buf_cell_and_ports: str | None = None,
        verilog_files: list[Path] | Path | None = None,
        liberty_files: list[Path] | Path | None = None,
        debug: bool = False,
        flat: bool = False    
    ):
        """
        Initializes the YosysTool with the given configuration parameters.
        
        Parameters
        ----------
        synth_executable : Path | str
            The path to the Yosys executable.
        top_name : str | None
            The name of the top-level module in the Verilog design.
        is_gate_level : bool
            Flag indicating whether the input Verilog files are already gate-level 
            netlists (True) or need to be synthesized (False).
        techmap_files : list[Path] | None
            List of techmap files for Yosys or None if not using techmapping.
        tiehi_cell_and_port : str | None
            String specifying the tie-high cell and port for Yosys hilomap, or None if not using hilomap.
        tielo_cell_and_port : str | None
            String specifying the tie-low cell and port for Yosys hilomap, or None if not using hilomap.
        min_buf_cell_and_ports : str | None
            String specifying the minimum buffer cell and ports for Yosys insbuf, or None if not using insbuf.
        verilog_files : list[Path] | Path | None
            List of Verilog RTL files or a single Verilog RTL file to be synthesized.
        liberty_files : list[Path] | Path | None
            List of Liberty files or a single Liberty file for the target technology.
        debug : bool
            Flag indicating whether to enable debug mode for verbose output during synthesis.
        flat : bool
            Flag indicating whether to flatten the hierarchy during synthesis (default: False).
        """
        self.verilog_files: list[Path] | Path | None = verilog_files
        self.lib_files: list[Path] | Path | None = liberty_files
        self.top_name: str | None = top_name
        self.synth_executable: Path | str = synth_executable
        self.techmap_files: list[Path] | None = techmap_files
        self.tiehi_cell_and_port: str | None = tiehi_cell_and_port
        self.tielo_cell_and_port: str | None = tielo_cell_and_port
        self.min_buf_cell_and_ports: str | None = min_buf_cell_and_ports
        self.is_gate_level: bool = is_gate_level
        self.debug: bool = debug
        self.flat: bool = flat
        
        self.netlist_path: Path | None = None
         
    def synth_synthesize(self):
        """
        Generates a temporary gate-level netlist from the Verilog RTL files using Yosys.
        The gate-level netlist is created in a temporary location and deleted after use.

        Raises
        ------
        RuntimeError
            If synthesis fails or if the generated netlist file is empty or not created.
        """
        self._check_errors()
        
        if self.is_gate_level:
            self.netlist_path = self.verilog_files
            return None
        
        # Generate Yosys synthesis TCL script
        synth_tcl_script: str = ""
        synth_tcl_script += f"yosys -import\n"
        if isinstance(self.lib_files, Path):
            synth_tcl_script += f"read_liberty -lib {self.lib_files}\n"
        else:
            for lib in self.lib_files:
                synth_tcl_script += f"read_liberty -lib {lib}\n"
        if isinstance(self.verilog_files, Path):
            synth_tcl_script += (
                f"read_verilog -overwrite -sv {self.verilog_files}\n"
            )
        else:
            for vf in self.verilog_files:
                synth_tcl_script += f"read_verilog -overwrite -sv {vf}\n"
        if self.flat:
            synth_tcl_script += f"synth -flatten -top {self.top_name}\n"
        else:
            synth_tcl_script += f"synth -top {self.top_name}\n"
        synth_tcl_script += f"renames -top {self.top_name}\n"
        synth_tcl_script += f"renames -wire\n"

        if self.techmap_files is not None:
            for tm in self.techmap_files:
                synth_tcl_script += f"techmap -map {tm}\n"
            synth_tcl_script += f"simplemap\n"

        synth_tcl_script += f"clockgate -liberty  {
            self.lib_files[0]
            if isinstance(self.lib_files, list)
            else self.lib_files
        }\n"
        synth_tcl_script += f"dfflibmap -liberty  {
            self.lib_files[0]
            if isinstance(self.lib_files, list)
            else self.lib_files
        }\n"
        synth_tcl_script += f"setundef -zero\n"
        synth_tcl_script += f"splitnets\n"

        if (
            self.tiehi_cell_and_port is not None
            and self.tielo_cell_and_port is not None
        ):
            synth_tcl_script += (
                f"hilomap -hicell {self.tiehi_cell_and_port} "
                f"-locell {self.tielo_cell_and_port}\n"
            )
        if self.min_buf_cell_and_ports is not None:
            synth_tcl_script += f"insbuf -buf {self.min_buf_cell_and_ports}\n"

        synth_tcl_script += f"tribuf\n"
        synth_tcl_script += f"abc -liberty {
            self.lib_files[0]
            if isinstance(self.lib_files, list)
            else self.lib_files
        }\n"
        synth_tcl_script += f"opt -purge -full\n"
        synth_tcl_script += "write_verilog -noattr -noexpr {}\n".format(
            "{synth_output_file}"
        )

        fd, path = tempfile.mkstemp(prefix="synth_verilog_", suffix=".v")
        os.close(fd)
        path = Path(path)
        
        if not path.exists():
            raise RuntimeError(
                "Failed to generate gate-level netlist using Yosys. No netlist file created."
            )
 
        logger.debug(f"Generating Synthesized Verilog file at temporary path: {path}")

        self._call_external(
            self.synth_executable,
            stdin_data=synth_tcl_script.format(
                synth_output_file=path
            ),
            debug=self.debug,
            args=["-C"],
        )

        content: str = path.read_text()
        if not content:
            path.unlink()
            raise RuntimeError(
                "Failed to generate gate-level netlist using Yosys. No content in netlist file."
            )
        
        result_file: Path = path

        # Remove single-bit vector notation for compatibility
        # with OpenSTA SDF back-annotation
        netl: str = result_file.read_text()
        netl = netl.replace("[0:0]", " ")
        result_file.write_text(netl)

        self.netlist_path = result_file
         
    @property
    def synth_netlist_file(self) -> Path:
        """
        Returns the path to the generated gate-level netlist file.
        
        Raises
        ------
        RuntimeError
            If the netlist file has not been generated yet (i.e., synthesize() has not been called).
        """
        if self.netlist_path is None:
            raise RuntimeError("Netlist file has not been generated yet. Call synthesize() first.")
        return self.netlist_path

    @property
    def synth_design_name(self) -> str:
        """
        Returns the name of the design being synthesized.

        Returns
        -------
        str
            The name of the design being synthesized.
        """
        return self.top_name

    @synth_design_name.setter
    def synth_design_name(self, name: str):
        """
        Sets the name of the design being synthesized.

        Parameters
        ----------
        name : str
            The name of the design being synthesized.
        """
        self.top_name = name
    
    @property
    def synth_rtl_files(self) -> list[Path] | Path:
        """
        Returns the list of RTL Verilog files used for synthesis.
        
        Returns
        -------
        list[Path] | Path
            The list of RTL Verilog files used for synthesis.
        """
        return self.verilog_files

    @synth_rtl_files.setter
    def synth_rtl_files(self, files: list[Path] | Path):
        """
        Sets the list of RTL Verilog files used for synthesis.

        Parameters
        ----------
        files : list[Path] | Path
            The list of RTL Verilog files to use for synthesis.
        """
        self.verilog_files = files
        
    @property
    def synth_liberty_files(self) -> list[Path] | Path:
        """
        Returns the list of Liberty files used for synthesis.
        
        Returns
        -------
        list[Path] | Path
            The list of Liberty files used for synthesis.
        """
        return self.lib_files
    
    @synth_liberty_files.setter
    def synth_liberty_files(self, files: list[Path] | Path):
        """
        Sets the list of Liberty files used for synthesis.

        Parameters
        ----------
        files : list[Path] | Path
            The list of Liberty files to use for synthesis.
        """
        self.lib_files = files
        
    @property
    def synth_passthrough(self) -> bool:
        """
        Returns whether the synthesis tool is in passthrough mode (i.e., it does not perform 
        actual synthesis but simply passes through the input rtl files).
        
        Returns
        -------
        bool
            True if the synthesis tool is in passthrough mode, False otherwise.
        """
        return self.is_gate_level
    
    @synth_passthrough.setter
    def synth_passthrough(self, value: bool):
        """
        Sets whether the synthesis tool is in passthrough mode.

        Parameters
        ----------
        value : bool
            True to enable passthrough mode, False to disable.
        """
        self.is_gate_level = value
           
    def synth_clean_up(self):
        """
        Cleans up the temporary gate-level netlist file generated by Yosys, if it exists.
        """
        if self.netlist_path is not None and self.netlist_path.exists():  
            logger.debug(f"Cleaning up temporary netlist file at: {self.netlist_path}")
            # Dont delete the netlist file if it was provided 
            # as input (i.e., gate-level netlist case)
            if not self.is_gate_level:
                self.netlist_path.unlink()
            self.netlist_path = None
    
    def _call_external(
        self,
        executable: str,
        args: list[str] = [],
        stdin_data: str = "",
        debug: bool = False,
    ) -> subprocess.CompletedProcess:
        """
        Calls an external executable with given arguments and stdin data.
        Captures the output and checks for errors.

        Parameters
        ----------
        executable : str
            The path to the executable to run.
        args : list[str]
            List of arguments to pass to the executable.
        stdin_data : str
            Data to send to the executable's stdin.

        Returns
        -------
        subprocess.CompletedProcess
            The result of the subprocess call.

        Raises
        ------
        RuntimeError
            If the external command fails.
        """
        if debug:
            logger.debug("Debug mode enabled for external command.")
            logger.debug(f"Calling external command: {executable} {' '.join(args)}")
            logger.debug(f"With stdin data:\n{stdin_data}")
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
            raise RuntimeError(
                f"Command '{' '.join([executable, *args])}' failed with error: {result.stderr}"
            )
        return result
    
    def _check_errors(self):
        """
        Checks for errors in the configuration parameters provided to the YosysTool.
        
        Raises
        ------
        TypeError
            If any parameter has an incorrect type.
        FileNotFoundError
            If any specified file does not exist.
        ValueError
            If any specified file is empty or if there are invalid combinations of configuration values.
        """
        if not isinstance(self.verilog_files, (list, Path)):
            raise TypeError(
                "verilog_files must be a list of pathlib.Path objects or a single pathlib.Path object."
            )
        if self.is_gate_level:
            if isinstance(self.verilog_files, list):
                raise TypeError(
                    "When is_gate_level is True, verilog_files must be a single pathlib.Path object."
                    " Multiple Verilog files are not supported for gate-level netlists."
                )
        if isinstance(self.verilog_files, list):
            for vf in self.verilog_files:
                if not isinstance(vf, Path):
                    raise TypeError(
                        "Each item in verilog_files list must be a pathlib.Path object."
                    )
                if not vf.exists():
                    raise FileNotFoundError(f"Verilog file not found: {vf}")
                if vf.stat().st_size == 0:
                    raise ValueError(f"Verilog file is empty: {vf}")
        else:
            if not isinstance(self.verilog_files, Path):
                raise TypeError(
                    "verilog_files must be a list of pathlib.Path objects or a single pathlib.Path object."
                )
            if not self.verilog_files.exists():
                raise FileNotFoundError(
                    f"Verilog file not found: {self.verilog_files}"
                )
            if self.verilog_files.stat().st_size == 0:
                raise ValueError(
                    f"Verilog file is empty: {self.verilog_files}"
                )

        if not isinstance(self.is_gate_level, bool):
            raise TypeError("is_gate_level must be a boolean value.")

        if self.is_gate_level == True and not isinstance(
            self.verilog_files, Path
        ):
            raise TypeError(
                "When is_gate_level is True, verilog_files must be a single pathlib.Path object."
                " Multiple Verilog files are not supported for gate-level netlists."
            )

        if not isinstance(self.synth_executable, (Path, str)):
            raise TypeError("synth_executable must be a string or a pathlib.Path object.")
        
        if self.techmap_files is not None:
            if not isinstance(self.techmap_files, list):
                raise TypeError(
                    "techmap_files must be a list of pathlib.Path objects or None."
                )
            for tm in self.techmap_files:
                if not isinstance(tm, Path):
                    raise TypeError(
                        "Each item in techmap_files list must be a pathlib.Path object."
                    )
                if not tm.exists():
                    raise FileNotFoundError(f"Techmap file not found: {tm}")
                if tm.stat().st_size == 0:
                    raise ValueError(f"Techmap file is empty: {tm}")

        if not isinstance(self.tiehi_cell_and_port, (str, type(None))):
            raise TypeError("tiehi_cell_and_port must be a string or None.")
        if not isinstance(self.tielo_cell_and_port, (str, type(None))):
            raise TypeError("tielo_cell_and_port must be a string or None.")
        if not isinstance(self.min_buf_cell_and_ports, (str, type(None))):
            raise TypeError("min_buf_cell_and_ports must be a string or None.")
        if not isinstance(self.flat, bool):
            raise TypeError("flat must be a boolean value.")

        if (self.tiehi_cell_and_port is None) ^ (
            self.tielo_cell_and_port is None
        ):
            raise ValueError(
                "Both tiehi_cell_and_port and tielo_cell_and_port must be specified together."
            )
           
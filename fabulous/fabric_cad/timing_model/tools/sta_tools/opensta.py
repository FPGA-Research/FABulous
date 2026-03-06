"""
OpenSTA Tool Interface, providing an interface to run OpenSTA for static 
timing analysis on a given Verilog netlist.
"""


from fabulous.fabric_cad.timing_model.tools.specification import StaTool
from pathlib import Path
import tempfile, os
import subprocess
from loguru import logger


class OpenStaTool(StaTool):
    """
    OpenSTA is an open-source static timing analysis tool. This class provides an interface 
    to run OpenSTA on a given netlist, and to retrieve the generated SDF file after analysis.
    """
    
    def __init__(
        self,
        sta_executable: Path | str,
        liberty_files: list[Path] | Path | None = None,
        top_name: str | None = None,
        verilog_netlist: Path | None = None,
        spef_files: list[Path] | Path | None = None,
        debug: bool = False,
    ):
        """
        Initializes the OpenSTATool with the given parameters.
        
        Parameters
        ----------
        sta_executable : Path | str
            The path to the OpenSTA executable.
        liberty_files : list[Path] | Path | None
            The Liberty timing model file(s) to use for analysis. Can be a single Path or a list of Paths.
        top_name : str | None
            The name of the top-level design to analyze.
        verilog_netlist : Path | None
            The path to the Verilog gate-level netlist to analyze. If None, it must be set before calling analyze().
        spef_files : list[Path] | Path | None
            The SPEF RC extraction file(s) to use for analysis. Can be a single Path or a list of Paths.
        debug : bool
            Flag to enable debug mode, which will print additional information during analysis. Default is False.
        """
        self.verilog_netlist: Path | None = verilog_netlist
        self.lib_files: list[Path] | Path | None = liberty_files
        self.top_name: str | None = top_name
        self.sta_executable: Path | str = sta_executable
        self.spef_files: list[Path] | Path | None = spef_files
        self.debug: bool = debug
        
        self.sdf_path: Path | None = None
        
    def sta_analyze(self): 
        """
        Generates an temporary SDF file from the Verilog gate-level netlist using OpenSTA.
        The SDF file is created in a temporary location and deleted after use.

        Returns
        -------
        Path
            The path to the generated SDF file.
            
        Raises
        ------
        RuntimeError
            If the SDF file cannot be generated or is empty after running OpenSTA.
        """
        self._check_errors()
        
        sta_tcl_script: str = ""
        if isinstance(self.lib_files, Path):
            sta_tcl_script += f"read_liberty {self.lib_files}\n"
        else:
            for lib in self.lib_files:
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
        path = Path(path)
        
        if not path.exists():
            raise RuntimeError(
                "Failed to generate SDF file using OpenSTA. No SDF file created."
            )

        logger.debug(f"Generating SDF file at temporary path: {path}")

        self._call_external(
            self.sta_executable,
            stdin_data=sta_tcl_script.format(sdf_path=path),
            debug=self.debug,
        )

        content: str = path.read_text()
        if not content:
            path.unlink()
            raise RuntimeError(
                "Failed to generate SDF file using OpenSTA. No content in SDF file."
            )
            
        self.sdf_path = path

    @property
    def sta_sdf_file(self) -> Path:
        """
        Returns the path to the generated SDF file after analysis.

        Returns
        -------
        Path
            The path to the generated SDF file.

        Raises
        ------
        RuntimeError
            If the SDF file has not been generated yet.
        """
        if self.sdf_path is None:
            raise RuntimeError("SDF file has not been generated yet. Call analyze() first.")
        return self.sdf_path
    
    @property
    def sta_netlist_file(self) -> Path:
        """
        Returns the path to the netlist file used for STA analysis.

        Returns
        -------
        Path
            The path to the netlist file used for STA analysis.
        """
        return self.verilog_netlist
    
    @sta_netlist_file.setter
    def sta_netlist_file(self, netl: Path):
        """
        Sets the path to the netlist file used for STA analysis.

        Parameters
        ----------
        netl : Path
            The path to the netlist file.
        """
        self.verilog_netlist = netl
    
    @property
    def sta_design_name(self) -> str:
        """
        Returns the name of the design being analyzed.

        Returns
        -------
        str
            The name of the design being analyzed.
        """
        return self.top_name

    @sta_design_name.setter
    def sta_design_name(self, name: str):
        """
        Sets the name of the design being analyzed.
        
        Parameters
        ----------
        name : str
            The name of the design being analyzed.
        """
        self.top_name = name
        
    @property
    def sta_liberty_files(self) -> list[Path] | Path | None:
        """
        Returns the list of Liberty files used for STA analysis.

        Returns
        -------
        list[Path] | Path | None
            The list of Liberty files used for STA analysis.
        """
        return self.lib_files

    @sta_liberty_files.setter
    def sta_liberty_files(self, files: list[Path] | Path | None):
        """
        Sets the list of Liberty files used for STA analysis.

        Parameters
        ----------
        files : list[Path] | Path | None
            The list of Liberty files used for STA analysis.
        """
        self.lib_files = files
        
    @property
    def sta_rc_files(self) -> list[Path] | Path | None:
        """
        Returns the list of RC files used for STA analysis.

        Returns
        -------
        list[Path] | Path | None
            The list of RC files used for STA analysis.
        """
        return self.spef_files

    @sta_rc_files.setter
    def sta_rc_files(self, files: list[Path] | Path | None):
        """
        Sets the list of RC files used for STA analysis.

        Parameters
        ----------
        files : list[Path] | Path | None
            The list of RC files used for STA analysis.
        """
        self.spef_files = files

    def sta_clean_up(self):
        """
        Cleans up any temporary files generated during STA analysis, including the SDF file.
        """
        if self.sdf_path is not None and self.sdf_path.exists():
            logger.debug(f"Cleaning up temporary SDF file at: {self.sdf_path}")
            self.sdf_path.unlink()
            self.sdf_path = None
    
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
        Checks for errors in the provided configuration parameters.

        Raises
        ------
        TypeError
            If any parameter is of incorrect type.
        FileNotFoundError
            If any specified file does not exist.
        ValueError
            If any specified file is empty.
        """
        if not isinstance(self.verilog_netlist, Path):
            raise TypeError("verilog_netlist must be a pathlib.Path object.")
        if not self.verilog_netlist.exists():
            raise FileNotFoundError(
                f"Verilog netlist file not found: {self.verilog_netlist}"
            )
        if self.verilog_netlist.stat().st_size == 0:
            raise ValueError(f"Verilog netlist file is empty: {self.verilog_netlist}")

        if not isinstance(self.lib_files, (list, Path)):
            raise TypeError(
                "liberty_files must be a list of pathlib.Path objects or a single pathlib.Path object."
            )
        if isinstance(self.lib_files, list):
            for lib in self.lib_files:
                if not isinstance(lib, Path):
                    raise TypeError(
                        "Each item in liberty_files list must be a pathlib.Path object."
                    )
                if not lib.exists():
                    raise FileNotFoundError(f"Liberty file not found: {lib}")
                if lib.stat().st_size == 0:
                    raise ValueError(f"Liberty file is empty: {lib}")
        else:
            if not self.lib_files.exists():
                raise FileNotFoundError(f"Liberty file not found: {self.lib_files}")
            if self.lib_files.stat().st_size == 0:
                raise ValueError(f"Liberty file is empty: {self.lib_files}")

        if not isinstance(self.top_name, str):
            raise TypeError("top_name must be a string.")
        if not isinstance(self.sta_executable, (Path, str)):
            raise TypeError("sta_executable must be a string or a pathlib.Path object.")

        if self.spef_files is not None and not isinstance(
            self.spef_files, (list, Path)
        ):
            raise TypeError(
                "spef_files must be a list of pathlib.Path objects or a single pathlib.Path object or None."
            )
        if isinstance(self.spef_files, list):
            for spef in self.spef_files:
                if not isinstance(spef, Path):
                    raise TypeError(
                        "Each item in spef_files list must be a pathlib.Path object."
                    )
                if not spef.exists():
                    raise FileNotFoundError(f"SPEF file not found: {spef}")
                if spef.stat().st_size == 0:
                    raise ValueError(f"SPEF file is empty: {spef}")
        elif isinstance(self.spef_files, Path):
            if not self.spef_files.exists():
                raise FileNotFoundError(f"SPEF file not found: {self.spef_files}")
            if self.spef_files.stat().st_size == 0:
                raise ValueError(f"SPEF file is empty: {self.spef_files}")

        if not isinstance(self.debug, bool):
            raise TypeError("debug must be a boolean.")
        
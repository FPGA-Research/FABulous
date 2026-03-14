"""
This module defines the abstract base classes for synthesis and static 
timing analysis (STA) tools. These classes specify the required methods 
that any concrete implementation of a synthesis or STA tool must provide, 
such as synthesizing a Verilog file, returning the path to the generated 
netlist or SDF file, and cleaning up temporary files after analysis.
"""


from abc import ABC, abstractmethod
from pathlib import Path


class SynthTool(ABC):
    """
    Abstract base class for synthesis tool backends.

    Concrete implementations synthesize one or more RTL Verilog files into a
    gate-level netlist using a set of Liberty timing libraries. Implementations
    may optionally support a passthrough mode where the input RTL is forwarded
    without running synthesis.
    """
    
    @abstractmethod
    def synth_synthesize(self):
        """
        Synthesizes the given Verilog file.
        """
        pass
    
    @property
    @abstractmethod
    def synth_netlist_file(self) -> Path:
        """
        Returns the path to the synthesized netlist file.
        
        Returns
        -------
        Path
            The path to the synthesized netlist file.
        """
        pass
    
    @abstractmethod
    def synth_clean_up(self):
        """
        Cleans up any temporary files generated during synthesis.
        """
        pass
    
    @property
    @abstractmethod
    def synth_design_name(self) -> str:
        """
        Gets the name of the design being synthesized.
        
        Returns
        -------
        str            
            The name of the design being synthesized.
        """
        pass
    
    @synth_design_name.setter
    @abstractmethod
    def synth_design_name(self, name: str):
        """
        Sets the name of the design being synthesized.
        
        Parameters
        ----------
        name : str
            The name of the design being synthesized.
        """
        pass
    
    @property
    @abstractmethod
    def synth_liberty_files(self) -> list[Path] | Path:
        """
        Returns the list of Liberty files used for synthesis.
        
        Returns
        -------
        list[Path] | Path
            The list of Liberty files used for synthesis.
        """
        pass
    
    @synth_liberty_files.setter
    @abstractmethod
    def synth_liberty_files(self, files: list[Path] | Path):
        """
        Sets the list of Liberty files used for synthesis.
        
        Parameters
        ----------
        files : list[Path] | Path
            The list of Liberty files to be used for synthesis.
        """
        pass
    
    @property
    @abstractmethod
    def synth_rtl_files(self) -> list[Path] | Path:
        """
        Returns the list of RTL files used for synthesis.
        
        Returns
        -------
        list[Path] | Path
            The list of RTL files used for synthesis.
        """
        pass
    
    @synth_rtl_files.setter
    @abstractmethod
    def synth_rtl_files(self, files: list[Path] | Path):
        """
        Sets the list of RTL files used for synthesis.
        
        Parameters
        ----------
        files : list[Path] | Path
            The list of RTL files to be used for synthesis.
        """
        pass
    
    @property
    @abstractmethod
    def synth_passthrough(self) -> bool:
        """
        Returns whether the synthesis tool is in passthrough mode (i.e., it does not perform 
        actual synthesis but simply passes through the input rtl files).
        
        Returns
        -------
        bool
            True if the synthesis tool is in passthrough mode, False otherwise.
        """
        pass
    
    @synth_passthrough.setter
    @abstractmethod
    def synth_passthrough(self, value: bool):
        """
        Sets whether the synthesis tool is in passthrough mode.
        
        Parameters
        ----------
        value : bool
            True to enable passthrough mode, False to disable it.
        """
        pass

class StaTool(ABC):
    """
    Abstract base class for static timing analysis (STA) tool backends.

    Concrete implementations run a timing analysis on a synthesized netlist and
    produce an SDF file for back-annotated simulation or further timing checks.
    """
    
    @abstractmethod
    def sta_analyze(self):
        """
        Analyzes the given netlist file.
        """
        pass

    @property
    @abstractmethod
    def sta_sdf_file(self) -> Path:
        """
        Returns the path to the generated SDF file.
        
        Returns
        -------
        Path
            The path to the generated SDF file.
        """
        pass
    
    @abstractmethod
    def sta_clean_up(self):
        """
        Cleans up any temporary files generated during STA analysis.
        """
        pass
    
    @property
    @abstractmethod
    def sta_netlist_file(self) -> Path:
        """
        Returns the path to the netlist file used for STA analysis.
        
        Returns
        -------
        Path
            The path to the netlist file used for STA analysis.
        """
        pass
    
    @sta_netlist_file.setter
    @abstractmethod
    def sta_netlist_file(self, netl: Path):
        """
        Sets the path to the netlist file used for STA analysis.
        
        Parameters
        ----------
        netl : Path
            The path to the netlist file used for STA analysis.
        """
        pass
    
    @property
    @abstractmethod
    def sta_design_name(self) -> str:
        """
        Returns the name of the design being analyzed.
        
        Returns
        -------
        str
            The name of the design being analyzed.
        """
        pass
    
    @sta_design_name.setter
    @abstractmethod
    def sta_design_name(self, name: str):
        """
        Sets the name of the design being analyzed.
        
        Parameters
        ----------
        name : str
            The name of the design being analyzed.
        """
        pass
    
    @property
    @abstractmethod
    def sta_liberty_files(self) -> list[Path] | Path:
        """
        Returns the list of Liberty files used for STA analysis.
        
        Returns
        -------
        list[Path] | Path
            The list of Liberty files used for STA analysis.
        """
        pass
    
    @sta_liberty_files.setter
    @abstractmethod
    def sta_liberty_files(self, files: list[Path] | Path):
        """
        Sets the list of Liberty files used for STA analysis.
        
        Parameters
        ----------
        files : list[Path] | Path
            The list of Liberty files to be used for STA analysis.
        """
        pass
    
    @property
    @abstractmethod
    def sta_rc_files(self) -> list[Path] | Path | None:
        """
        Returns the list of RC files used for STA analysis.
        
        Returns
        -------
        list[Path] | Path | None
            The list of RC files used for STA analysis, or None if no RC files are specified.
        """
        pass
    
    @sta_rc_files.setter
    @abstractmethod
    def sta_rc_files(self, files: list[Path] | Path | None):
        """
        Sets the list of RC files used for STA analysis.
        
        Parameters
        ----------
        files : list[Path] | Path | None
            The list of RC files to be used for STA analysis, or None to clear the RC files.
        """
        pass
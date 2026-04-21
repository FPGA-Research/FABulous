"""Define the abstract base classes for synthesis STA tool backends.

These classes specify the required methods that any concrete implementation of a
synthesis or STA tool must provide, such as synthesizing a Verilog file, returning the
path to the generated netlist or SDF file, and cleaning up temporary files after
analysis.
"""

from abc import ABC, abstractmethod
from pathlib import Path


class SynthTool(ABC):
    """Abstract base class for synthesis tool backends.

    Concrete implementations synthesize one or more RTL Verilog files into a gate-level
    netlist using a set of Liberty timing libraries. Implementations may optionally
    support a passthrough mode where the input RTL is forwarded without running
    synthesis.
    """

    @abstractmethod
    def synth_synthesize(self) -> None:
        """Synthesize the given Verilog file."""

    @property
    @abstractmethod
    def synth_netlist_file(self) -> Path:
        """Return the path to the synthesized netlist file.

        Returns
        -------
        Path
            The path to the synthesized netlist file.
        """

    @abstractmethod
    def synth_clean_up(self) -> None:
        """Clean up any temporary files generated during synthesis."""

    @property
    @abstractmethod
    def synth_design_name(self) -> str:
        """Get the name of the design being synthesized.

        Returns
        -------
        str
            The name of the design being synthesized.
        """

    @synth_design_name.setter
    @abstractmethod
    def synth_design_name(self, name: str) -> None:
        """Set the name of the design being synthesized.

        Parameters
        ----------
        name : str
            The name of the design being synthesized.
        """

    @property
    @abstractmethod
    def synth_liberty_files(self) -> list[Path] | Path:
        """Return the list of Liberty files used for synthesis.

        Returns
        -------
        list[Path] | Path
            The list of Liberty files used for synthesis.
        """

    @synth_liberty_files.setter
    @abstractmethod
    def synth_liberty_files(self, files: list[Path] | Path) -> None:
        """Set the list of Liberty files used for synthesis.

        Parameters
        ----------
        files : list[Path] | Path
            The list of Liberty files to be used for synthesis.
        """

    @property
    @abstractmethod
    def synth_rtl_files(self) -> list[Path] | Path:
        """Return the list of RTL files used for synthesis.

        Returns
        -------
        list[Path] | Path
            The list of RTL files used for synthesis.
        """

    @synth_rtl_files.setter
    @abstractmethod
    def synth_rtl_files(self, files: list[Path] | Path) -> None:
        """Set the list of RTL files used for synthesis.

        Parameters
        ----------
        files : list[Path] | Path
            The list of RTL files to be used for synthesis.
        """

    @property
    @abstractmethod
    def synth_passthrough(self) -> bool:
        """Return whether the synthesis tool is in passthrough mode.

        (i.e., it does not perform actual synthesis but simply passes
        through the input rtl files).

        Returns
        -------
        bool
            True if the synthesis tool is in passthrough mode,
            False otherwise.
        """

    @synth_passthrough.setter
    @abstractmethod
    def synth_passthrough(self, value: bool) -> None:
        """Set whether the synthesis tool is in passthrough mode.

        Parameters
        ----------
        value : bool
            True to enable passthrough mode, False to disable it.
        """


class StaTool(ABC):
    """Abstract base class for static timing analysis (STA) tool backends.

    Concrete implementations run a timing analysis on a synthesized netlist and produce
    an SDF file for back-annotated simulation or further timing checks.
    """

    @abstractmethod
    def sta_analyze(self) -> None:
        """Analyze the given netlist file."""

    @property
    @abstractmethod
    def sta_sdf_file(self) -> Path:
        """Return the path to the generated SDF file.

        Returns
        -------
        Path
            The path to the generated SDF file.
        """

    @abstractmethod
    def sta_clean_up(self) -> None:
        """Clean up any temporary files generated during STA analysis."""

    @property
    @abstractmethod
    def sta_netlist_file(self) -> Path:
        """Return the path to the netlist file used for STA analysis.

        Returns
        -------
        Path
            The path to the netlist file used for STA analysis.
        """

    @sta_netlist_file.setter
    @abstractmethod
    def sta_netlist_file(self, netl: Path) -> None:
        """Set the path to the netlist file used for STA analysis.

        Parameters
        ----------
        netl : Path
            The path to the netlist file used for STA analysis.
        """

    @property
    @abstractmethod
    def sta_design_name(self) -> str:
        """Return the name of the design being analyzed.

        Returns
        -------
        str
            The name of the design being analyzed.
        """

    @sta_design_name.setter
    @abstractmethod
    def sta_design_name(self, name: str) -> None:
        """Set the name of the design being analyzed.

        Parameters
        ----------
        name : str
            The name of the design being analyzed.
        """

    @property
    @abstractmethod
    def sta_liberty_files(self) -> list[Path] | Path:
        """Return the list of Liberty files used for STA analysis.

        Returns
        -------
        list[Path] | Path
            The list of Liberty files used for STA analysis.
        """

    @sta_liberty_files.setter
    @abstractmethod
    def sta_liberty_files(self, files: list[Path] | Path) -> None:
        """Set the list of Liberty files used for STA analysis.

        Parameters
        ----------
        files : list[Path] | Path
            The list of Liberty files to be used for STA analysis.
        """

    @property
    @abstractmethod
    def sta_rc_files(self) -> list[Path] | Path | None:
        """Return the list of RC files used for STA analysis.

        Returns
        -------
        list[Path] | Path | None
            The list of RC files used for STA analysis, or None
            if no RC files are specified.
        """

    @sta_rc_files.setter
    @abstractmethod
    def sta_rc_files(self, files: list[Path] | Path | None) -> None:
        """Set the list of RC files used for STA analysis.

        Parameters
        ----------
        files : list[Path] | Path | None
            The list of RC files to be used for STA analysis, or
            None to clear the RC files.
        """

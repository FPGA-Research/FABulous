"""Provide thin pyosys helpers for JSON/Verilog design conversion.

This module isolates direct pyosys pass execution behind a small wrapper and utility
functions. It keeps temporary file plumbing in one place so other modules can treat
pyosys conversion as simple function calls.
"""

import json
from pathlib import Path

import pyosys.libyosys as ys


class PyosysBridge:
    """Wrap a pyosys design object and common IO pass commands.

    The bridge keeps a single active design and provides helpers for reading/writing
    JSON and Verilog without duplicating command strings.

    Parameters
    ----------
    debug : bool, optional
        If True, pyosys pass commands are run without tee to preserve
        output for debugging.
    """

    def __init__(self, debug: bool = False) -> None:
        self._ys = ys
        self.design: object = self._ys.Design()
        self.temp_dir: Path = Path.home() / ".fabulous" / "tmp"
        self.debug = debug

        self.temp_dir.mkdir(parents=True, exist_ok=True)

    def read_json_path(self, path: Path) -> None:
        """Load a design from a JSON file path into the active design.

        Parameters
        ----------
        path : Path
            Path to Yosys JSON netlist file.
        """
        self._run(f"read_json {path}")

    def read_verilog_path(self, path: Path) -> None:
        """Load a design from a Verilog file path into the active design.

        Parameters
        ----------
        path : Path
            Path to Verilog netlist/source file.
        """
        self._run(f"read_verilog {path}")

    def write_json_path(self, path: Path) -> None:
        """Write the active design to a JSON file path.

        Parent directories are created automatically before emission.

        Parameters
        ----------
        path : Path
            Destination JSON file path.
        """
        path.parent.mkdir(parents=True, exist_ok=True)
        self._run(f"write_json {path}")

    def write_verilog_path(self, path: Path) -> None:
        """Write the active design to a Verilog file path.

        The emitted Verilog omits attributes and expression expansion to
        match the project output conventions.

        Parameters
        ----------
        path : Path
            Destination Verilog file path.
        """
        path.parent.mkdir(parents=True, exist_ok=True)
        self._run(f"write_verilog -noattr -noexpr {path}")

    @property
    def get_netlist_dict(self) -> dict:
        """Get the active design as a JSON dictionary.

        The function writes the design to a temporary JSON file and parses
        it back into a dictionary for return.

        Returns
        -------
        dict
            Parsed Yosys JSON dictionary for the active design.
        """
        path: Path = self.temp_dir / "lut_combinator_tmp_design.json"
        self.write_json_path(path)
        try:
            src: dict = json.loads(path.read_text(encoding="utf-8"))
        finally:
            if path.exists():
                path.unlink()
        return src

    @property
    def get_verilog_string(self) -> str:
        """Get the active design emitted as a Verilog string.

        Returns
        -------
        str
            Emitted Verilog netlist text.
        """
        path: Path = self.temp_dir / "lut_combinator_tmp_design.v"
        self.write_verilog_path(path)
        try:
            return path.read_text(encoding="utf-8")
        finally:
            if path.exists():
                path.unlink()

    def load_netlist_dict(self, model_json: dict) -> None:
        """Load a JSON design dictionary into the active design.

        The function writes the dictionary to a temporary JSON file and reads
        it through pyosys to populate the active design.

        Note the design will be cleared before loading the new design,
        so any existing design will be lost.

        Parameters
        ----------
        model_json : dict
            Yosys JSON design dictionary.
        """
        path: Path = self.temp_dir / "lut_combinator_tmp_design.json"
        path.write_text(json.dumps(model_json), encoding="utf-8")
        try:
            self.design = None
            self.design = self._ys.Design()
            self.read_json_path(path)
        finally:
            if path.exists():
                path.unlink()

    def load_design(self, design: object) -> None:
        """Attach an existing pyosys design as the active design.

        Note the design will be cleared before loading the new design,
        so any existing design will be lost.

        Parameters
        ----------
        design : object
            Existing pyosys design instance.
        """
        self.design = None
        self.design = design

    def run_pass(self, cmd: str) -> None:
        """Execute an arbitrary pyosys pass command on active design.

        Parameters
        ----------
        cmd : str
            pyosys pass command string.
        """
        self._run(cmd)

    def _run(self, cmd: str) -> None:
        """Run one pyosys pass command against the current design.

        Parameters
        ----------
        cmd : str
            pyosys pass command string.
        """
        if self.debug:
            self._ys.run_pass(cmd, self.design)
        else:
            self._ys.run_pass(f"tee -q {cmd}", self.design)

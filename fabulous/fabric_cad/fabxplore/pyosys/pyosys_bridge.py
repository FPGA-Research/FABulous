"""Provide thin pyosys helpers for design import/export and pass execution.

This module isolates direct pyosys pass execution behind a wrapper and utility
functions. It keeps temporary-file handling in one place so other modules can treat
pyosys design import/export as simple function calls.
"""

import json
import shlex
import tempfile
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

import pyosys.libyosys as ys

from fabulous.fabric_definition.yosys_obj import YosysJson


class PyosysBridge:
    """Wrap a pyosys design object and common IO/pass commands.

    The bridge keeps a single active design and provides helpers for reading,
    writing, and serializing designs without duplicating pyosys command strings.

    Parameters
    ----------
    debug : bool
        If True, pyosys pass commands are run without quiet tee wrapping so
        command output remains visible for debugging.
    """

    def __init__(self, debug: bool = False) -> None:
        self._ys = ys
        self.design: ys.Design = self._ys.Design()
        self.debug = debug

    def top_name(self) -> str:
        """Return the name of the top module in the active design.

        Returns
        -------
        str
            Name of the top module in the active design.
        """
        return str(self.design.top_module().name).replace("\\", "")

    def read_verilog_paths(
        self,
        paths: list[Path],
        replace_design: bool = False,
    ) -> None:
        """Read one or more Verilog files into the active design.

        Parameters
        ----------
        paths : list[Path]
            Verilog source or netlist paths to read.
        replace_design : bool
            If True, replace the current design before reading the files.
            If False, add the files to the current design.

        Raises
        ------
        ValueError
            If `paths` is empty.
        """
        if not paths:
            raise ValueError("paths must not be empty")

        if replace_design:
            self.reset_design()

        for path in paths:
            self._run(f"read_verilog {self._quote_path(path)}")

    def read_verilog_string(
        self,
        verilog_text: str,
        replace_design: bool = False,
        blackbox: bool = False,
    ) -> None:
        """Read Verilog source text into the active design.

        Parameters
        ----------
        verilog_text : str
            Verilog source text to read.
        replace_design : bool
            If True, replace the current design before reading the text.
            If False, add the text to the current design.
        blackbox : bool
            If True, read the text with the -lib option to treat
            all modules as blackboxes.
            If False, read the text normally to include module
            definitions in the design.

        Raises
        ------
        ValueError
            If `verilog_text` is empty.
        """
        if not verilog_text:
            raise ValueError("verilog_text must not be empty")

        if replace_design:
            self.reset_design()

        with self._temporary_path(".v") as path:
            path.write_text(verilog_text, encoding="utf-8")
            if blackbox:
                self._run(f"read_verilog -lib -overwrite {self._quote_path(path)}")
            else:
                self._run(f"read_verilog -overwrite {self._quote_path(path)}")

    def read_json_paths(
        self,
        paths: list[Path],
        replace_design: bool = False,
    ) -> None:
        """Read one or more Yosys JSON files into the active design.

        Parameters
        ----------
        paths : list[Path]
            Yosys JSON netlist paths to read.
        replace_design : bool
            If True, replace the current design before reading the files.
            If False, add the files to the current design.

        Raises
        ------
        ValueError
            If `paths` is empty.
        """
        if not paths:
            raise ValueError("paths must not be empty")

        if replace_design:
            self.reset_design()

        for path in paths:
            self._run(f"read_json {self._quote_path(path)}")

    def write_json_path(self, path: Path) -> None:
        """Write the active design to a Yosys JSON file.

        Parent directories are created automatically before emission.

        Parameters
        ----------
        path : Path
            Destination JSON file path.
        """
        path.parent.mkdir(parents=True, exist_ok=True)
        self._run(f"write_json {self._quote_path(path)}")

    def write_verilog_path(self, path: Path, include_attributes: bool = False) -> None:
        """Write the active design to a Verilog file.

        The emitted Verilog omits expression expansion. Attributes are omitted
        by default to match the project output conventions, but can be emitted
        when downstream tooling or diagnostics need cell metadata.

        Parameters
        ----------
        path : Path
            Destination Verilog file path.
        include_attributes : bool
            If ``True``, preserve Yosys attributes in the emitted Verilog.
        """
        path.parent.mkdir(parents=True, exist_ok=True)
        attr_flag = "" if include_attributes else "-noattr "
        self._run(f"write_verilog {attr_flag}-noexpr {self._quote_path(path)}")

    def write_blif_path(self, path: Path) -> None:
        """Write the active design to a BLIF file.

        Parameters
        ----------
        path : Path
            Destination BLIF file path.
        """
        path.parent.mkdir(parents=True, exist_ok=True)
        self._run(f"write_blif {self._quote_path(path)}")

    def to_netlist_dict(self) -> dict:
        """Return the active design as a parsed Yosys JSON dictionary.

        Returns
        -------
        dict
            Parsed Yosys JSON dictionary for the active design.
        """
        with self._temporary_path(".json") as path:
            self.write_json_path(path)
            return json.loads(path.read_text(encoding="utf-8"))

    def to_verilog_string(self, include_attributes: bool = False) -> str:
        """Return the active design emitted as Verilog text.

        Parameters
        ----------
        include_attributes : bool
            If ``True``, preserve Yosys attributes in the emitted Verilog.

        Returns
        -------
        str
            Emitted Verilog netlist text.
        """
        with self._temporary_path(".v") as path:
            self.write_verilog_path(path, include_attributes=include_attributes)
            return path.read_text(encoding="utf-8")

    def to_py_object(self) -> YosysJson:
        """Return the active design as a YosysJson object.

        This is a pure python class strcutured definition of the
        Yosys JSON format, which is more convenient to work with in python code.

        Returns
        -------
        YosysJson
            YosysJson object parsed from the active design's JSON representation.
        """
        netlist_dict = self.to_netlist_dict()
        return YosysJson(yosys_dict=netlist_dict)

    def load_netlist_dict(self, model_json: dict) -> None:
        """Replace the active design with one loaded from a JSON dictionary.

        Parameters
        ----------
        model_json : dict
            Yosys JSON design dictionary.
        """
        with self._temporary_path(".json") as path:
            path.write_text(json.dumps(model_json), encoding="utf-8")
            self.read_json_paths([path], replace_design=True)

    def load_design(self, design: ys.Design) -> None:
        """Replace the active design with an existing pyosys design.

        Parameters
        ----------
        design : ys.Design
            Existing pyosys design instance.
        """
        self.design = design

    def reset_design(self) -> None:
        """Replace the active design with a fresh empty pyosys design."""
        self.design = self._ys.Design()

    def run_pass(self, cmd: str) -> None:
        """Execute an arbitrary pyosys pass command on the active design.

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

    @staticmethod
    def _quote_path(path: Path) -> str:
        """Return a shell-escaped path string for use in pyosys commands."""
        return shlex.quote(str(path))

    @staticmethod
    @contextmanager
    def _temporary_path(suffix: str) -> Iterator[Path]:
        """Yield a temporary file path in the system temp directory.

        The file is created in the system temporary directory, yielded as a
        `Path`, and removed automatically afterwards.

        Parameters
        ----------
        suffix : str
            File suffix, including the leading dot.

        Yields
        ------
        Path
            Temporary file path created for the context.
        """
        with tempfile.NamedTemporaryFile(
            mode="w",
            suffix=suffix,
            delete=False,
            encoding="utf-8",
        ) as tmp:
            path = Path(tmp.name)

        try:
            yield path
        finally:
            path.unlink(missing_ok=True)

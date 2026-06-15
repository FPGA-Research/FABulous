"""Gate-level RTL mapping flow.

This module wraps the Pyosys bridge with a PDK-aware synthesis and standard-cell mapping
sequence. It reads RTL files, applies Liberty modifications from the input
configuration, runs the mapping passes, and records area statistics for the mapped
design.
"""

import re
import subprocess
import tempfile
from pathlib import Path

from fabulous.fabric_cad.fabxplore.modules.netlist_tool.core.liberty import (
    LibertyHandler,
)
from fabulous.fabric_cad.fabxplore.modules.netlist_tool.core.models import (
    PdkInputConfig,
)
from fabulous.fabric_cad.fabxplore.modules.netlist_tool.core.sta_utils import (
    StaSlacks,
    extract_sta_slacks,
)
from fabulous.fabric_cad.fabxplore.pyosys.pyosys_bridge import PyosysBridge


class NetlistTool:
    """Map RTL sources to a PDK-specific gate-level netlist.

    Parameters
    ----------
    config : PdkInputConfig
        PDK input configuration describing the RTL sources, top module, Liberty
        edits, technology maps, and optional post-mapping transformations.
    debug : bool, optional
        If ``True``, initialize the Pyosys bridge in debug mode.
    """

    def __init__(self, config: PdkInputConfig, debug: bool = False) -> None:
        self.config = config
        self.debug = debug
        self.netlist_design = PyosysBridge(debug=debug)

        self.liberty_handler = LibertyHandler(config)
        self.liberty_corner_text = self.liberty_handler.modify_liberty(
            self.config.liberty_corner_file.read_text()
        )

        self._area: float | None = None
        self._hold_slack: float | None = None
        self._setup_slack: float | None = None
        self._stats: str | None = None
        self._netlist: str | None = None
        self._sta_report: str | None = None

    @property
    def slacks(self) -> StaSlacks:
        """Return the worst hold and setup slack values extracted from the STA report.

        Returns
        -------
        StaSlacks
            Dictionary containing the worst hold and setup slack values.

            ``"hold"``
                Worst slack from ``Path Type: min`` paths. Returns ``None`` if no
                min path is found.

            ``"setup"``
                Worst slack from ``Path Type: max`` paths. Returns ``None`` if no
                max path is found.

        Raises
        ------
        ValueError
            If the STA report has not been generated yet.
        """
        if self._sta_report is None:
            raise ValueError("STA report has not been generated. Call run_sta() first.")

        return extract_sta_slacks(self._sta_report)

    @property
    def sta_report(self) -> str:
        """Return the STA report from the last mapping run.

        Returns
        -------
        str
            The STA report as a text string.

        Raises
        ------
        ValueError
            If :meth:`run_sta` has not been called yet.
        """
        if self._sta_report is None:
            raise ValueError("STA report has not been generated. Call run_sta() first.")
        return self._sta_report

    @property
    def netlist(self) -> str:
        """Return the final mapped netlist in Yosys's internal format.

        Returns
        -------
        str
            The mapped netlist as a text string.

        Raises
        ------
        ValueError
            If :meth:`map_rtl` has not been called yet.
        """
        if self._netlist is None:
            raise ValueError("Netlist has not been generated. Call map_rtl() first.")
        return self._netlist

    @property
    def stats(self) -> str:
        """Return the Yosys statistics output from the last mapping run.

        Returns
        -------
        str
            Text emitted by the final Yosys ``stat`` command.

        Raises
        ------
        ValueError
            If :meth:`map_rtl` has not been called yet.
        """
        if self._stats is None:
            raise ValueError("Stats have not been computed yet. Call map_rtl() first.")
        return self._stats

    @property
    def area(self) -> float:
        """Return the mapped chip area from the last mapping run.

        Returns
        -------
        float
            Chip area parsed from the final Yosys statistics output.

        Raises
        ------
        ValueError
            If :meth:`map_rtl` has not been called yet.
        """
        if self._area is None:
            raise ValueError("Area has not been computed yet. Call map_rtl() first.")
        return self._area

    def _read_rtl_files(self) -> None:
        """Read configured RTL sources into the Pyosys design.

        Returns
        -------
        None
            This method mutates the internal Pyosys design.
        """
        self.netlist_design.read_verilog_paths(self.config.rtl_files)

    def _synth(self) -> None:
        """Run synthesis, mapping, and optional post-mapping transforms.

        The method applies the configured top-module hierarchy, optimization
        passes, standard-cell mapping against the modified Liberty text,
        PDK-specific technology maps, optional buffer insertion, optional
        sub-circuit extraction, and optional cell type remapping.

        Returns
        -------
        None
            This method mutates the internal Pyosys design.
        """
        self.netlist_design.run_pass(f"hierarchy -check -top {self.config.top_name}")
        self.netlist_design.run_pass("proc")
        self.netlist_design.run_pass("check")
        self.netlist_design.run_pass("flatten")
        self.netlist_design.run_pass("opt_expr")
        self.netlist_design.run_pass("opt_clean")
        self.netlist_design.run_pass("check")
        self.netlist_design.run_pass("opt -nodffe -nosdff")
        self.netlist_design.run_pass("opt_clean")
        self.netlist_design.run_pass("opt")
        self.netlist_design.run_pass("wreduce")
        self.netlist_design.run_pass("peepopt")
        self.netlist_design.run_pass("opt_clean")
        self.netlist_design.run_pass("share -aggressive")
        self.netlist_design.run_pass("opt_clean")

        self.netlist_design.run_pass("aigmap")
        self.netlist_design.run_pass("techmap -map +/techmap.v")
        self.netlist_design.run_pass("opt")
        self.netlist_design.run_pass(
            f'abc -g {self.config.gates} -script "+strash;&get,-n;&fraig,-x;&put;scorr;'
            "balance,-l;resub,-K,6,-l;rewrite,-l;resub,-K,6,-N,2,-l;refactor,-l;"
            "resub,-K,8,-l;balance,-l;resub,-K,8,-N,2,-l;rewrite,-l;resub,-K,10,-l;"
            "rewrite,-z,-l;resub,-K,10,-N,2,-l;balance,-l;resub,-K,12,-l;"
            "refactor,-z,-l;resub,-K,12,-N,2,-l;rewrite,-z,-l;balance,-l;dc2;"
            "balance,-l;resub,-K,6,-l;rewrite,-l;resub,-K,6,-N,2,-l;refactor,-l;"
            "resub,-K,8,-l;balance,-l;resub,-K,8,-N,2,-l;rewrite,-l;resub,-K,10,-l;"
            "rewrite,-z,-l;resub,-K,10,-N,2,-l;balance,-l;resub,-K,12,-l;"
            "refactor,-z,-l;resub,-K,12,-N,2,-l;rewrite,-z,-l;balance,-l;strash;"
            '&get,-n;&dch,-f;&nf,-R,1000;&put"'
        )
        self.netlist_design.run_pass("opt")

        with tempfile.TemporaryDirectory() as tmpdir_obj:
            tmp_lib: Path = Path(tmpdir_obj) / "liberty_tmp.lib"
            tmp_lib.write_text(self.liberty_corner_text)
            self.netlist_design.run_pass(f"dfflibmap -liberty {tmp_lib}")
            self.netlist_design.run_pass(f"abc -liberty {tmp_lib}")
            self.netlist_design.run_pass(f"clockgate -liberty {tmp_lib}")

        self.netlist_design.run_pass(f"rename -top {self.config.top_name}")
        self.netlist_design.run_pass("rename -wire")
        for techmap_file in self.config.techmap_files:
            self.netlist_design.run_pass(f"techmap -map {techmap_file}")
        self.netlist_design.run_pass("setundef -zero")
        self.netlist_design.run_pass("splitnets")
        self.netlist_design.run_pass(
            f"hilomap -hicell {self.config.tiehi_cell_and_port} "
            f"-locell {self.config.tielo_cell_and_port}"
        )
        self.netlist_design.run_pass("rename -hide")
        self.netlist_design.run_pass("opt_clean -purge")

        if self.config.buffer_wire_insertion:
            self.netlist_design.run_pass(
                f"insbuf -buf {self.config.min_buf_cell_and_ports}"
            )

        self.netlist_design.run_pass("opt -full -purge")

        with tempfile.TemporaryDirectory() as tmpdir_obj:
            tmp_lib: Path = Path(tmpdir_obj) / "liberty_tmp.lib"
            for circ in self.config.sub_circuit_map_rules or []:
                tmp_lib.write_text(circ)
                self.netlist_design.run_pass(f"extract -map {tmp_lib}")

        if self.config.change_cell_types:
            for cell_type, cells in self.config.change_cell_types.items():
                for cell in cells:
                    self.netlist_design.run_pass(f"chtype -map {cell} {cell_type}")

        with tempfile.TemporaryDirectory() as tmpdir_obj:
            tmp_lib: Path = Path(tmpdir_obj) / "liberty_tmp.lib"
            tmp_lib.write_text(self.liberty_corner_text)
            self.netlist_design.run_pass(f"stat -liberty {tmp_lib}")

        self._netlist = self.netlist_design.to_verilog_string()

    def _tmp_stats(self) -> None:
        """Run the final statistics pass and cache its results.

        The method writes the modified Liberty text to a temporary file, captures
        Yosys ``stat`` output, and parses the chip area from that output when
        available.

        Returns
        -------
        None
            This method updates the cached ``stats`` and ``area`` values.
        """
        with tempfile.TemporaryDirectory() as tmpdir_obj:
            tempdir = Path(tmpdir_obj)
            tmp_stats_file = tempdir / "stat.txt"
            tmp_lib: Path = tempdir / "liberty_tmp.lib"
            tmp_lib.write_text(self.liberty_corner_text)
            self.netlist_design.run_pass(
                f"tee -o {tmp_stats_file} stat -liberty {tmp_lib}"
            )

            self._stats = tmp_stats_file.read_text()

            pattern = r"Chip area for module\s+'\\[^']+':\s*([0-9]+(?:\.[0-9]+)?)"
            match = re.search(pattern, self._stats)

            if match:
                self._area = float(match.group(1))

    def run_sta(
        self,
        clk_ports: list[str],
        period_ns: float,
        sta_exec: str = "sta",
        custom_sta_script: str | None = None,
    ) -> None:
        """Run static timing analysis on the mapped design.

        Parameters
        ----------
        clk_ports : list[str]
            List of clock port names to create in the STA tool.
        period_ns : float
            Clock period in nanoseconds to use for timing analysis.
        sta_exec : str
            Path to the STA executable to run.
        custom_sta_script : str | None
            Optional custom STA script to run instead of the default generated one.
            If provided, this script will be passed directly to the STA tool's stdin.
        """
        with tempfile.TemporaryDirectory() as tmpdir_obj:
            tempdir = Path(tmpdir_obj)
            tmp_netlist: Path = tempdir / "netlist_tmp.v"
            tmp_lib: Path = tempdir / "liberty_tmp.lib"
            tmp_report: Path = tempdir / "report_tmp.txt"

            tmp_netlist.write_text(self.netlist)
            tmp_lib.write_text(self.liberty_corner_text)

            sta_script = (
                custom_sta_script
                or f"""
                read_liberty {tmp_lib}
                read_verilog {tmp_netlist}
                link_design {self.config.top_name}
                create_clock -name clk -period {period_ns} {" ".join(clk_ports)}
                report_checks -path_delay min_max > {tmp_report}
            """
            )

            self._call_external(sta_exec, stdin_data=sta_script, debug=self.debug)
            self._sta_report = tmp_report.read_text()

    def map_rtl(self) -> None:
        """Run the full RTL-to-gate-level mapping flow.

        The method reads configured RTL sources, executes synthesis and
        technology mapping passes, then stores the final statistics text and
        parsed chip area on the instance.

        Returns
        -------
        None
            This method mutates the internal Pyosys design and cached
            statistics.
        """
        self._read_rtl_files()
        self._synth()
        self._tmp_stats()

    def _call_external(
        self,
        executable: str,
        args: list[str] | None = None,
        stdin_data: str = "",
        debug: bool = False,
    ) -> subprocess.CompletedProcess:
        """Call an external executable with given arguments and stdin data.

        Captures the output and checks for errors.

        Parameters
        ----------
        executable : str
            The path to the executable to run.
        args : list[str] | None
            List of arguments to pass to the executable.
        stdin_data : str
            Data to send to the executable's stdin.
        debug : bool
            Flag to enable debug mode, which will print additional information.

        Returns
        -------
        subprocess.CompletedProcess
            The result of the subprocess call.

        Raises
        ------
        RuntimeError
            If the external command fails.
        """
        if args is None:
            args = []

        if debug:
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
                f"Command '{' '.join([executable, *args])}' "
                f"failed with error: {result.stderr}"
            )
        return result

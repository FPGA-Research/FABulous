"""Gate-level RTL mapping flow.

This module wraps the Pyosys bridge with a PDK-aware synthesis and standard-cell mapping
sequence. It reads RTL files, applies Liberty modifications from the input
configuration, runs the mapping passes, and records area statistics for the mapped
design.
"""

import re
import tempfile
from pathlib import Path

from fabulous.fabric_cad.fabxplore.modules.netlist_tool.core.liberty import (
    LibertyHandler,
)
from fabulous.fabric_cad.fabxplore.modules.netlist_tool.core.models import (
    PdkInputConfig,
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
        self._stats: str | None = None

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
            'abc -g cmos -script "+strash;&get,-n;&fraig,-x;&put;scorr;'
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

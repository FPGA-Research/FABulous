"""Convertes verilog RTL into a verilog gate-level netlist.

Yosys synthesizes the RTL, then VerilogGateLevelTimingGraph turns the resulting
netlist into a timing graph. The netlist is a temporary this class owns, so it is
deleted once the graph is built; a caller that already has a netlist skips this
class and constructs VerilogGateLevelTimingGraph directly.
"""

from pathlib import Path

from fabulous.fabric_cad.timing_model.hdlnx.verilog_gate_level import (
    VerilogGateLevelTimingGraph,
)
from fabulous.fabric_cad.timing_model.models import (
    DelayType,
)
from fabulous.tools.yosys import YosysTool


class HdlnxTimingModel(VerilogGateLevelTimingGraph):
    """Class to generate a timing graph from Verilog RTL.

    It does this by first synthesizing the RTL into a gate-level netlist with
    Yosys, and then using the VerilogGateLevelTimingGraph class to generate the
    timing graph.

    Parameters
    ----------
    top_name : str
        The top-level module to synthesize and analyze.
    verilog_files : list[Path] | Path
        The RTL source file(s) to synthesize.
    liberty_files : list[Path] | Path
        The Liberty file(s) for the target technology.
    techmap_files : list[Path] | None
        Techmap files applied after `synth`, or None to skip techmapping.
    tiehi_cell_and_port : str | None
        The "cell port" pair for `hilomap -hicell`, or None to skip hilomap.
    tielo_cell_and_port : str | None
        The "cell port" pair for `hilomap -locell`, or None to skip hilomap.
    min_buf_cell_and_ports : str | None
        The "cell in out" triple for `insbuf`, or None to skip buffer insertion.
    flat : bool
        Whether to flatten the hierarchy during synthesis. Defaults to False.
    spef_files : list[Path] | Path | None
        Parasitics to back-annotate for wire delay, or None to ignore wire delay.
    delay_type_str : DelayType
        The type of delay to use for the timing graph. Defaults to
        DelayType.MAX_ALL.
    debug : bool
        Flag to enable debug mode. Defaults to False.
    """

    def __init__(
        self,
        top_name: str,
        verilog_files: list[Path] | Path,
        liberty_files: list[Path] | Path,
        techmap_files: list[Path] | None = None,
        tiehi_cell_and_port: str | None = None,
        tielo_cell_and_port: str | None = None,
        min_buf_cell_and_ports: str | None = None,
        flat: bool = False,
        spef_files: list[Path] | Path | None = None,
        delay_type_str: DelayType = DelayType.MAX_ALL,
        debug: bool = False,
    ) -> None:
        netlist_file: Path = YosysTool.synthesize_to_netlist(
            verilog_files=verilog_files,
            liberty_files=liberty_files,
            top_name=top_name,
            techmap_files=techmap_files,
            tiehi_cell_and_port=tiehi_cell_and_port,
            tielo_cell_and_port=tielo_cell_and_port,
            min_buf_cell_and_ports=min_buf_cell_and_ports,
            flat=flat,
        )
        try:
            super().__init__(
                top_name=top_name,
                netlist_file=netlist_file,
                liberty_files=liberty_files,
                spef_files=spef_files,
                delay_type_str=delay_type_str,
                debug=debug,
            )
        finally:
            YosysTool.clean_up(netlist_file)

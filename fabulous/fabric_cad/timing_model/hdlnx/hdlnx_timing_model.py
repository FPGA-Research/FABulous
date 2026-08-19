"""Convertes verilog RTL into a verilog gate-level netlist.

Will use an external synthesis tool.

In this context a sysnthesis tool can be anything that can convert RTL verilog into
gate-level verilog, that means also tools that can do backend design steps like
technology mapping and place&route.

It then uses the VerilogGateLevelTimingGraph class to generate a timing graph from the
gate-level netlist.
"""

from fabulous.fabric_cad.timing_model.hdlnx.verilog_gate_level import (
    VerilogGateLevelTimingGraph,
)
from fabulous.fabric_cad.timing_model.models import (
    DelayType,
)
from fabulous.fabric_cad.timing_model.tools.specification import StaTool, SynthTool


class HdlnxTimingModel(VerilogGateLevelTimingGraph):
    """Class to generate a timing graph from Verilog RTL.

    It does this by first synthesizing the RTL into a
    gate-level netlist using an external synthesis tool, and then using the
    VerilogGateLevelTimingGraph class to generate the timing graph.

    Initializes the HdlnxTimingModel with the given synthesis and STA tools,
    and generates the timing graph.

    Parameters
    ----------
    sta_tool : StaTool
        The static timing analysis tool to use for generating the timing graph.
    synth_tool : SynthTool
        The synthesis tool to use for converting RTL to gate-level netlist.
    delay_type_str : DelayType, optional
        The type of delay to use for the timing graph (default is DelayType.MAX_ALL).
    debug : bool, optional
        If True, enable debug output for the underlying tools
        (default is False).
    """

    def __init__(
        self,
        sta_tool: StaTool,
        synth_tool: SynthTool,
        delay_type_str: DelayType = DelayType.MAX_ALL,
        debug: bool = False,
    ) -> None:
        self.synth_tool: SynthTool = synth_tool
        self.synth_tool.synth_synthesize()

        _sta_tool: StaTool = sta_tool

        _sta_tool.sta_netlist_file = self.synth_tool.synth_netlist_file
        _sta_tool.sta_design_name = self.synth_tool.synth_design_name
        _sta_tool.sta_liberty_files = self.synth_tool.synth_liberty_files

        super().__init__(
            top_name=self.synth_tool.synth_design_name,
            sta_tool=_sta_tool,
            delay_type_str=delay_type_str,
            debug=debug,
        )

        synth_tool.synth_clean_up()

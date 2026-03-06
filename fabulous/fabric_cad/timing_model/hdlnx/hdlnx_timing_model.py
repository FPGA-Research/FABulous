"""
This module convertes verilog RTL into a verilog gate-level netlist using an external synthesis tool.
In this context a sysnthesis tool can be anything that can convert RTL verilog into gate-level verilog,
that means also tools that can do backend design steps like technology mapping and place&route.
It then uses the VerilogGateLevelTimingGraph class to generate a timing graph from the gate-level netlist.
"""


from fabulous.fabric_cad.timing_model.hdlnx.verilog_gate_level import VerilogGateLevelTimingGraph
from fabulous.fabric_cad.timing_model.models import *
from fabulous.fabric_cad.timing_model.tools.specification import StaTool, SynthTool
from loguru import logger


class HdlnxTimingModel(VerilogGateLevelTimingGraph):
    """
    Class to generate a timing graph from Verilog RTL by first synthesizing 
    it into a gate-level netlist using an external synthesis tool, and then using 
    the VerilogGateLevelTimingGraph class to generate the timing graph.
    """

    def __init__(
        self,
        sta_tool: StaTool, 
        synth_tool: SynthTool, 
        delay_type_str: DelayType = DelayType.MAX_ALL, 
        debug: bool = False
    ):
        """
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
            If True, print debug warnings about overwriting STA tool configurations (default is False).
        """
        self.synth_tool: SynthTool = synth_tool
        self.synth_tool.synthesize()
        
        _sta_tool: StaTool = sta_tool
        
        if _sta_tool.netlist_file is not None and debug:
            logger.warning(
                f"STA tool already has a netlist file. This will be overwritten by HdlnxTimingModel."
            )
       
        if _sta_tool.design_name is not None and debug:
            logger.warning(
                f"STA tool already has a design name. This will be overwritten by HdlnxTimingModel."
            )
          
        if _sta_tool.liberty_files is not None and debug:
            logger.warning(
                f"STA tool already has liberty files. This will be overwritten by HdlnxTimingModel."
            )
        
        _sta_tool.netlist_file = self.synth_tool.netlist_file
        _sta_tool.design_name = self.synth_tool.design_name
        _sta_tool.liberty_files = self.synth_tool.liberty_files
        
        super().__init__(
            top_name=self.synth_tool.design_name,
            sta_tool=_sta_tool,
            delay_type_str=delay_type_str,
            debug=debug,
        )
        
        self.verilog_netlist_content: str = synth_tool.netlist_file.read_text()
        synth_tool.clean_up()
"""FABulous HDL exporters module.

This module contains code generators and exporter functions for generating
HDL (Hardware Description Language) files from fabric definitions.

Components:
- code_generator: Base CodeGenerator class
- verilog_generator: Verilog HDL generation
- vhdl_generator: VHDL generation
- fabric: Fabric-level HDL generation (generateFabric)
- tile: Tile-level generation (generateTile, generateSuperTile)
- switchmatrix: Switch matrix generation (genTileSwitchMatrix)
- configmem: Configuration memory generation (generateConfigMem)
- top_wrapper: Top-level wrapper generation (generateTopWrapper)
- automation: Automation utilities for fabric generation
- helpers: Helper functions for HDL generation
"""

# Code generators
from fabulous.backend.hdl.code_generator import CodeGenerator
from fabulous.backend.hdl.configmem import generateConfigMem

# Generation functions
from fabulous.backend.hdl.fabric import generateFabric
from fabulous.backend.hdl.switchmatrix import genTileSwitchMatrix
from fabulous.backend.hdl.tile import generateSuperTile, generateTile
from fabulous.backend.hdl.top_wrapper import generateTopWrapper
from fabulous.backend.hdl.verilog_generator import VerilogCodeGenerator
from fabulous.backend.hdl.vhdl_generator import VHDLCodeGenerator

__all__ = [
    "CodeGenerator",
    "VerilogCodeGenerator",
    "VHDLCodeGenerator",
    "generateFabric",
    "generateTile",
    "generateSuperTile",
    "genTileSwitchMatrix",
    "generateConfigMem",
    "generateTopWrapper",
]

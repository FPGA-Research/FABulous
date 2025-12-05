"""FABulous FPGA framework package.

This package provides a complete FPGA fabric generation framework with a
processing pipeline architecture for maximum flexibility and extensibility.

Processing Pipeline
-------------------
The framework follows a pipeline architecture similar to web frameworks:

1. **Reader**: Parse input formats (CSV, YAML, etc.) → Fabric object
2. **Context**: Hold fabric state and writer configuration
3. **Transform**: Mutate/process fabric (middleware-like operations)
4. **Exporters**: Generate output files (HDL, bitstreams, models)

Quick Start
-----------
::

    from fabulous import Context, Transform, VerilogCodeGenerator, generateFabric

    # Setup pipeline
    context = Context(VerilogCodeGenerator())
    context.load_fabric("fabric.csv")
    transform = Transform(context)

    # Apply transforms
    transform.generate_fabric_io_bels()

    # Export outputs
    context.set_output("output/fabric.v")
    generateFabric(context.writer, context.fabric)
"""

# Core data structures
# Core processing pipeline
from fabulous.core import Context, CSVReader, Reader, Transform

# Exporter functions (pure generation functions)
from fabulous.fabric_cad.gen_bitstream_spec import generateBitstreamSpec
from fabulous.fabric_cad.gen_npnr_model import genNextpnrModel
from fabulous.fabric_definition.bel import Bel
from fabulous.fabric_definition.fabric import Fabric
from fabulous.fabric_definition.supertile import SuperTile
from fabulous.fabric_definition.tile import Tile

# Code generators
from fabulous.fabric_generator.code_generator import CodeGenerator
from fabulous.fabric_generator.code_generator.code_generator_Verilog import (
    VerilogCodeGenerator,
)
from fabulous.fabric_generator.code_generator.code_generator_VHDL import (
    VHDLCodeGenerator,
)
from fabulous.fabric_generator.gen_fabric.gen_configmem import generateConfigMem
from fabulous.fabric_generator.gen_fabric.gen_fabric import generateFabric
from fabulous.fabric_generator.gen_fabric.gen_switchmatrix import genTileSwitchMatrix
from fabulous.fabric_generator.gen_fabric.gen_tile import (
    generateSuperTile,
    generateTile,
)
from fabulous.fabric_generator.gen_fabric.gen_top_wrapper import generateTopWrapper

# Geometry
from fabulous.geometry_generator.geometry_gen import GeometryGenerator

__all__ = [
    # Data structures
    "Fabric",
    "Tile",
    "Bel",
    "SuperTile",
    # Code generators
    "CodeGenerator",
    "VerilogCodeGenerator",
    "VHDLCodeGenerator",
    # Exporters (pure generation functions)
    "generateFabric",
    "generateTile",
    "generateSuperTile",
    "genTileSwitchMatrix",
    "generateTopWrapper",
    "generateConfigMem",
    "generateBitstreamSpec",
    "genNextpnrModel",
    # Geometry
    "GeometryGenerator",
    # Processing pipeline
    "Context",
    "Transform",
    "Reader",
    "CSVReader",
]

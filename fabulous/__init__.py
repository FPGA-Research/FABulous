"""FABulous FPGA framework package.

This package provides a complete FPGA fabric generation framework with a
processing pipeline architecture for maximum flexibility and extensibility.

Processing Pipeline
-------------------
The framework follows a pipeline architecture similar to web frameworks:

1. **Reader/Parsers**: Parse input formats (CSV, YAML, etc.) → Fabric object
2. **Core/Context**: Hold fabric state and coordinate pipeline
3. **Core/Transform**: Mutate/process fabric (middleware-like operations)
4. **Exporters**: Generate output files (HDL, bitstreams, geometry, GDS)

Quick Start
-----------
::

    from fabulous import FabricContext, Transform, VerilogCodeGenerator, generateFabric

    # Setup pipeline
    context = FabricContext(VerilogCodeGenerator())
    context.load_fabric("fabric.csv")
    transform = Transform(context)

    # Apply transforms
    transform.generate_fabric_io_bels()

    # Export outputs
    context.set_output("output/fabric.v")
    generateFabric(context.writer, context.fabric)
"""

# Core processing pipeline
from fabulous.core import CSVReader, FabricContext, Reader, Transform

# Bitstream/CAD exporters
from fabulous.backend.pnr import (
    generateBitstreamSpec,
    genNextpnrModel,
)

# Geometry exporter
from fabulous.backend.geometry import GeometryGenerator

# HDL exporters (code generators)
from fabulous.backend.hdl import (
    CodeGenerator,
    VerilogCodeGenerator,
    VHDLCodeGenerator,
    generateConfigMem,
    generateFabric,
    generateSuperTile,
    generateTile,
    generateTopWrapper,
    genTileSwitchMatrix,
)

# Data model
from fabulous.model import Bel, Fabric, SuperTile, Tile

__all__ = [
    # Core pipeline
    "FabricContext",
    "Transform",
    "Reader",
    "CSVReader",
    # Data model
    "Fabric",
    "Tile",
    "Bel",
    "SuperTile",
    # HDL exporters
    "CodeGenerator",
    "VerilogCodeGenerator",
    "VHDLCodeGenerator",
    "generateFabric",
    "generateTile",
    "generateSuperTile",
    "genTileSwitchMatrix",
    "generateTopWrapper",
    "generateConfigMem",
    # Bitstream/CAD
    "generateBitstreamSpec",
    "genNextpnrModel",
    # Geometry
    "GeometryGenerator",
]

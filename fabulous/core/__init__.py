"""Core fabric processing pipeline.

This module provides the processing pipeline architecture for fabric generation:
- Reader: Parses input formats (CSV, YAML, etc.) → Fabric
- Context: Holds fabric state (like request context in web frameworks)
- Transform: Processes/mutates fabric (like middleware)

Exporters (generateFabric, generateTile, etc.) read from Context
to produce output files.

Example Pipeline
----------------
::

    from fabulous.core import Context, Transform, CSVReader
    from fabulous import VerilogCodeGenerator, generateFabric

    # 1. Read: Parse input (auto-detects format from extension)
    context = Context(VerilogCodeGenerator())
    context.load_fabric("fabric.csv")  # Auto-uses CSVReader

    # Or explicit reader:
    # reader = CSVReader()
    # context.load_fabric("fabric.csv", reader)

    # 2. Transform: Mutate fabric state
    transform = Transform(context)
    transform.generate_fabric_io_bels()

    # 3. Export: Generate outputs
    context.set_output("output/fabric.v")
    generateFabric(context.writer, context.fabric)

Future Format Migration
-----------------------
When switching from CSV to YAML::

    # 1. Implement YAMLReader.read() method
    # 2. Convert fabric.csv → fabric.yaml
    # 3. Change: context.load_fabric("fabric.csv")
    #       to: context.load_fabric("fabric.yaml")
    # 4. Rest of pipeline unchanged!
"""

from fabulous.core.context import Context
from fabulous.core.reader import CSVReader, Reader, create_reader
from fabulous.core.transform import Transform

__all__ = [
    "Context",
    "Transform",
    "Reader",
    "CSVReader",
    "create_reader",
]

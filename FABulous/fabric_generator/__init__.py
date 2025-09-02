"""FABulous fabric generator module.

This module provides functionality for generating FPGA fabric implementations from
fabric definitions. It includes code generators for different HDLs and
tools for generating various fabric components.

The fabric generator consists of:
- code_generator: Abstract and concrete code generators for VHDL and Verilog
- gen_fabric: Core fabric generation functions and utilities
- parser: Parsers for CSV files, HDL files, and configuration memory specifications

Key functionality includes:
- Generating HDL code for tiles, switch matrices, and complete fabrics
- Parsing fabric definitions from CSV files
- Generating configuration memory structures
- Creating top-level fabric wrappers and automation scripts
"""

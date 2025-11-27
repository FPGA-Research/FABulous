"""FABulous fabric definition module.

This module contains classes and enumerations for defining FPGA fabric structure
and components. It provides the core data structures for representing tiles,
BELs (Basic Elements of Logic), ports, wires, and fabric configuration.

The fabric definition includes:
- Bel: Basic elements of logic like LUTs, flip-flops, and any other custom components
- ConfigMem: Configuration memory structures
- Fabric: Top-level fabric representation with tiles and routing
- Gen_IO: Generated I/O port definitions
- Port: Routing port definitions between tiles
- SuperTile: Multi-tile components for larger or more complex structures
- Tile: Individual FPGA tiles containing BELs and switch matrices
- Wire: Inter-tile wire connections
- define: Common enumerations and constants
"""

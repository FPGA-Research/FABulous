"""FABulous fabric model module.

This module contains the core data structures for defining FPGA fabric structure
and components. It provides classes for representing tiles, BELs (Basic Elements
of Logic), ports, wires, and fabric configuration.

The model includes:
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

from fabulous.model.bel import Bel
from fabulous.model.configmem import ConfigMem
from fabulous.model.fabric import Fabric
from fabulous.model.port import Port
from fabulous.model.supertile import SuperTile
from fabulous.model.tile import Tile
from fabulous.model.wire import Wire

__all__ = [
    "Bel",
    "ConfigMem",
    "Fabric",
    "Port",
    "SuperTile",
    "Tile",
    "Wire",
]

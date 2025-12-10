"""FABulous geometry exporters module.

This module provides functionality for generating geometric representations of
FPGA fabrics for the FABulator GUI. It converts fabric definitions
into geometric objects with positioning and routing information.

Components:
- generator: Main GeometryGenerator class (formerly geometry_gen)
- bel_geometry: Geometric representation of Basic Elements of Logic (BELs)
- fabric_geometry: Complete fabric geometric layout
- geometry_obj: Base geometric object definitions
- port_geometry: Port positioning and routing geometry
- sm_geometry: Switch matrix geometric representations
- tile_geometry: Individual tile geometric layouts
- wire_geometry: Wire routing and connection geometry

This module is primarily used for:
- Generating CSV files for FABulator visualization
- Creating placement information for CAD tools
- Providing geometric constraints for routing algorithms
- Supporting fabric visualization and debugging
"""

from fabulous.backend.geometry.generator import GeometryGenerator

__all__ = ["GeometryGenerator"]

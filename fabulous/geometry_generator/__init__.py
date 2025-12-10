"""Deprecated: This module has been moved to fabulous.exporters.geometry.

This module is deprecated and will be removed in a future version.
Please update your imports to use fabulous.exporters.geometry instead.
"""

import warnings

from fabulous.backend.geometry import GeometryGenerator

warnings.warn(
    "fabulous.geometry_generator is deprecated and will be removed in version 3.0. "
    "Please use fabulous.exporters.geometry instead.",
    DeprecationWarning,
    stacklevel=2,
)

# Re-export from new location for backward compatibility

__all__ = ["GeometryGenerator"]

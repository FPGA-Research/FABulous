"""Deprecated: This module has been moved to fabulous.model.

This module is deprecated and will be removed in a future version.
Please update your imports to use fabulous.model instead.

Old import:
    from fabulous.model import Fabric, Tile, Bel

New import:
    from fabulous.model import Fabric, Tile, Bel
"""

import warnings

warnings.warn(
    "fabulous.fabric_definition is deprecated and will be removed in version 3.0. "
    "Please use fabulous.model instead.",
    DeprecationWarning,
    stacklevel=2,
)

# Re-export from new location for backward compatibility
from fabulous.model import *  # noqa: F401, F403

__all__ = [
    "Bel",
    "ConfigMem",
    "Fabric",
    "Port",
    "SuperTile",
    "Tile",
    "Wire",
]

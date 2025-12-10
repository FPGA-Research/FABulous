"""Deprecated: This module has been moved to fabulous.exporters.hdl.

This module is deprecated and will be removed in a future version.
Please update your imports to use fabulous.exporters.hdl instead.

Old import:
    from fabulous.backend.hdl.fabric import generateFabric

New import:
    from fabulous.backend.hdl import generateFabric

The gen_fabric module has been reorganized into fabulous.exporters.hdl,
which contains all HDL generation functionality.
"""

import warnings

warnings.warn(
    "fabulous.fabric_generator.gen_fabric is deprecated and will be removed in version 3.0. "
    "Please use fabulous.exporters.hdl instead.",
    DeprecationWarning,
    stacklevel=2,
)

# Re-export from new location for backward compatibility
from fabulous.backend.hdl import *  # noqa: F401, F403

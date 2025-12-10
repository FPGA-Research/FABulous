"""Deprecated: This module has been moved to fabulous.templates.

This module is deprecated and will be removed in a future version.
Please update your imports to use fabulous.templates instead.

Old import:
    from fabulous.fabric_files import ...

New import:
    from fabulous.templates import ...
"""

import warnings

warnings.warn(
    "fabulous.fabric_files is deprecated and will be removed in version 3.0. "
    "Please use fabulous.templates instead.",
    DeprecationWarning,
    stacklevel=2,
)

# Note: This directory will be removed in a future version.
# All template files have been moved to fabulous.templates

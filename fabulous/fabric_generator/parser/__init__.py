"""Deprecated: This module has been moved to fabulous.parsers.

This module is deprecated and will be removed in a future version.
Please update your imports to use fabulous.parsers instead.

Old import:
    from fabulous.parsers.csv_parser import parse_csv

New import:
    from fabulous.parsers.csv_parser import parse_csv
"""

import warnings

warnings.warn(
    "fabulous.fabric_generator.parser is deprecated and will be removed in version 3.0. "
    "Please use fabulous.parsers instead.",
    DeprecationWarning,
    stacklevel=2,
)

# Re-export from new location for backward compatibility
from fabulous.parsers import *  # noqa: F401, F403

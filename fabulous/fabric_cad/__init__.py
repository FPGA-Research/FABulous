"""Deprecated: This module has been moved to fabulous.exporters.bitstream.

This module is deprecated and will be removed in a future version.
Please update your imports to use fabulous.exporters.bitstream instead.

Old import:
    from fabulous.backend.bitstream.bitstream_spec import generateBitstreamSpec

New import:
    from fabulous.backend.bitstream import generateBitstreamSpec

This package provided CAD tools for FPGA fabric development including bitstream
generation and design flow automation. All functionality has been moved to
fabulous.exporters.bitstream.
"""

import warnings

from fabulous.backend.pnr import *

warnings.warn(
    "fabulous.fabric_cad is deprecated and will be removed in version 3.0. "
    "Please use fabulous.exporters.bitstream instead.",
    DeprecationWarning,
    stacklevel=2,
)

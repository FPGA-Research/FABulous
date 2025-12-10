"""FABulous bitstream and CAD exporters module.

This module contains exporters for bitstream specifications and CAD tool
integration, including nextpnr models and design wrappers.

Components:
- bitstream_spec: Generate bitstream specification (generateBitstreamSpec)
- npnr_model: Generate nextpnr model files (genNextpnrModel)
- design_wrapper: Generate design top wrapper for CAD tools
"""

from fabulous.backend.pnr.bitstream_spec import generateBitstreamSpec
from fabulous.backend.pnr.npnr_model import genNextpnrModel

__all__ = [
    "generateBitstreamSpec",
    "genNextpnrModel",
]

"""Synthesis command implementation for the FABulous CLI.

deprecated: Use ``compile_design --synth-only`` instead.

This module provides a backwards-compatible ``synthesis`` command that
redirects to :func:`~fabulous.fabulous_cli.cmd_compile_design._compile_design`
with ``synth_only=True``.
"""

import argparse
from typing import TYPE_CHECKING

from cmd2 import with_argparser, with_category
from loguru import logger

from fabulous.fabulous_cli.cmd_compile_design import (
    CMD_USER_DESIGN_FLOW,
    _compile_design,
    compile_design_parser,
)

if TYPE_CHECKING:
    from fabulous.fabulous_cli.fabulous_cli import FABulous_CLI


@with_category(CMD_USER_DESIGN_FLOW)
@with_argparser(compile_design_parser)
def do_synthesis(self: "FABulous_CLI", args: argparse.Namespace) -> None:
    """Run Yosys synthesis for the specified Verilog files.

    deprecated: Use ``compile_design --synth-only`` instead.
    """
    logger.warning(
        "The 'synthesis' command is deprecated. Use 'compile_design' instead."
    )
    args.synth_only = True
    args.pnr_only = False
    args.bitgen_only = False
    _compile_design(self, args)

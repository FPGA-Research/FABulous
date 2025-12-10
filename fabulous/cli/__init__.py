"""FABulous command-line interface module.

This module provides the command-line interface for FABulous FPGA framework.

Components:
- main: Main CLI entry point (FABulous_CLI)
- synthesis: Synthesis commands
- gui: GUI-related commands
- helper: CLI utility functions
- plugin: Typer CLI plugin integration
"""

from fabulous.cli.main import FABulous_CLI

__all__ = ["FABulous_CLI"]

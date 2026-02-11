"""Custom exception classes for the FABulous framework.

This module defines all custom exceptions used throughout the FABulous framework for
better error handling and debugging. Each exception class is designed for specific error
scenarios that can occur during fabric generation, parsing, and configuration.
"""


class CommandError(Exception):
    """Exception raised for errors in the command execution."""


class EnvironmentNotSet(Exception):
    """Exception raised when the environment is not set."""


class InvalidFileType(Exception):
    """Exception raised for unsupported file types."""


class FabricParsingError(Exception):
    """Exception raised for errors in fabric parsing."""


class SpecMissMatch(Exception):
    """Exception raised when a required FASM file is missing."""


class InvalidPortType(Exception):
    """Exception raised for invalid port types."""


class InvalidFabricDefinition(Exception):
    """Exception raised for invalid fabric definitions."""


class InvalidFabricParameter(Exception):
    """Exception raised for invalid fabric parameters."""


class InvalidSwitchMatrixDefinition(Exception):
    """Exception raised for invalid matrix definitions."""


class InvalidListFileDefinition(Exception):
    """Exception raised for invalid list file formats."""


class InvalidTileDefinition(Exception):
    """Exception raised for invalid tile definitions."""


class InvalidSupertileDefinition(Exception):
    """Exception raised for invalid supertile definitions."""


class InvalidBelDefinition(Exception):
    """Exception raised for invalid BEL definitions."""


class PipelineCommandError(Exception):
    """Exception raised for errors in command line arguments."""


class InvalidState(Exception):
    """Exception raised for invalid state during fabric generation."""

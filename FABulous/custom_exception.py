class CommandError(Exception):
    """Exception raised for errors in the command execution."""


class EnvironmentNotSet(Exception):
    """Exception raised when the environment is not set."""


class FileTypeError(Exception):
    """Exception raised for unsupported file types."""


class FabricParsingError(Exception):
    """Exception raised for errors in fabric parsing."""

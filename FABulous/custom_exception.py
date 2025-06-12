class CommandError(Exception):
    """Exception raised for errors in the command execution."""

    pass


class EnvironmentNotSet(Exception):
    """Exception raised when the environment is not set."""

    pass


class FileTypeError(Exception):
    """Exception raised for unsupported file types."""

    pass


class FabricParsingError(Exception):
    """Exception raised for errors in fabric parsing."""

    pass

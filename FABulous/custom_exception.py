class CommandError(Exception):
    """Exception raised for errors in the command execution."""

    pass


class EnvironmentNotSet(Exception):
    """Exception raised when the environment is not set."""

    pass


class FileTypeError(Exception):
    """Exception raised for unsupported file types."""

    pass

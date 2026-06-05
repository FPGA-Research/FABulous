"""Built-in plugin registering the CSV fabric parser."""

from fabulous.fabric_generator.parser.parse_csv import parseFabricCSV
from fabulous.plugins import hookimpl
from fabulous.plugins.types import ParserProvider


@hookimpl
def fabulous_register_parsers() -> list[ParserProvider]:
    """Register the built-in CSV fabric parser.

    Returns
    -------
    list[ParserProvider]
        A provider for the ``.csv`` fabric parser.
    """
    return [ParserProvider(".csv", parseFabricCSV, "csv")]

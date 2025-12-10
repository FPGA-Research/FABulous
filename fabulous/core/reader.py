"""Fabric input readers - parses various formats into Fabric objects.

This module provides the input layer of the processing pipeline, supporting
multiple fabric definition formats (CSV, YAML, etc.).
"""

from abc import ABC, abstractmethod
from pathlib import Path

from fabulous.model.fabric import Fabric


class Reader(ABC):
    """Abstract base for fabric input parsers.

    Follows strategy pattern - allows switching between input formats
    without changing the rest of the pipeline.
    """

    @abstractmethod
    def read(self, path: Path) -> Fabric:
        """Parse input file and return Fabric object.

        Parameters
        ----------
        path : Path
            Path to fabric definition file

        Returns
        -------
        Fabric
            Parsed fabric object
        """
        ...


class CSVReader(Reader):
    """CSV fabric definition reader (current format)."""

    def read(self, path: Path) -> Fabric:
        """Parse CSV fabric definition.

        Parameters
        ----------
        path : Path
            Path to CSV fabric definition file

        Returns
        -------
        Fabric
            Parsed fabric object
        """
        from fabulous.parsers.csv_parser import parseFabricCSV

        return parseFabricCSV(path)


def create_reader(_path: Path) -> Reader:
    """Create appropriate reader based on file extension.

    Parameters
    ----------
    path : Path
        Path to fabric definition file

    Returns
    -------
    Reader
        Appropriate reader instance

    """
    return CSVReader()

"""Simple FPGA geometry location base object class."""

from enum import Enum


class Location:
    """A simple data structure for storing a location.

    Attributes
    ----------
    x : int
        X coordinate
    y : int
        Y coordinate
    """

    x: int
    y: int

    def __init__(self, x: int, y: int) -> None:
        """Initialize a `Location` instance.

        Parameters
        ----------
        x : int
            X coordinate
        y : int
            Y coordinate
        """
        self.x = x
        self.y = y

    def __repr__(self) -> str:
        """Return the string representation of the location.

        Returns
        -------
        str
            String in format 'x/y'
        """
        return f"{self.x}/{self.y}"


class Border(Enum):
    """Enumeration for tile border types in the fabric geometry.

    Used to specify which type of border a tile has within the fabric layout.
    """

    NORTHSOUTH = "NORTHSOUTH"
    EASTWEST = "EASTWEST"
    CORNER = "CORNER"
    NONE = "NONE"

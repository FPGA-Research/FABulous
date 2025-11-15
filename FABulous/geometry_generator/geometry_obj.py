"""Simple FPGA geometry location base object class."""

from dataclasses import dataclass
from enum import Enum

from FABulous.fabric_definition.define import IO


@dataclass
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


def oppositeIO(io: IO) -> IO:
    """Return opposite IO port."""
    if io == IO.INPUT:
        return IO.OUTPUT
    if io == IO.OUTPUT:
        return IO.INPUT
    if io == IO.INOUT:
        return IO.INOUT
    return IO.NULL

from enum import Enum
from fabric_generator.fabric import IO


class Location:
    """
    A simple datastruct for storing a Location.

    Attributes:
        x (int): X coordinate
        y (int): Y coordinate

    """

    x: int
    y: int

    def __init__(self, x: int, y: int):
        self.x = x
        self.y = y

    def __repr__(self) -> str:
        return f"{self.x}/{self.y}"


class Border(Enum):
    NORTHSOUTH = "NORTHSOUTH"
    EASTWEST = "EASTWEST"
    CORNER = "CORNER"
    NONE = "NONE"



def oppositeIO(io: IO):
    if io == IO.INPUT:
        return IO.OUTPUT
    if io == IO.OUTPUT:
        return IO.INPUT
    if io == IO.INOUT:
        return IO.INOUT
    return IO.NULL

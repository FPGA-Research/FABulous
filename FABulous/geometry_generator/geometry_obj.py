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

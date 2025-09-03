import re
from dataclasses import dataclass

from FABulous.fabric_definition.define import Direction


@dataclass(frozen=True, eq=True)
class Wire:
    """This class is for wire connections that span across multiple tiles. If working
    for connections between two adjacent tiles, the Port class should have all the
    required information. The main use of this class is to assist model generation,
    where information at individual wire level is needed.

    Attributes
    ----------
    direction : Direction
        The direction of the wire
    source : str
        The source name of the wire
    xOffset : int
        The X-offset of the wire
    yOffset : int
        The Y-offset of the wire
    destination : str
        The destination name of the wire
    sourceTile : str
        The source tile name of the wire
    destinationTile : str
        The destination tile name of the wire
    """

    direction: Direction
    source: str
    xOffset: int
    yOffset: int
    destination: str
    sourceTile: str
    destinationTile: str

    def __repr__(self) -> str:
        return f"{self.source}-X{self.xOffset}Y{self.yOffset}>{self.destination}"

    def __eq__(self, __o: object) -> bool:
        if __o is None or not isinstance(__o, Wire):
            return False
        return self.source == __o.source and self.destination == __o.destination

    def __post_init__(self) -> None:
        def validSourceDestination(name: str) -> bool:
            if self.xOffset == 0 and self.yOffset == 0:
                return True
            if not name:
                return True
            return re.match(r"^X\d+Y\d+$", name) is not None

        if not validSourceDestination(self.sourceTile):
            raise ValueError(
                f"Invalid source tile name: {self.sourceTile} for wire {self}, "
                "your source is located out side of the fabric, please check the "
                "source and destination port offset."
            )
        if not validSourceDestination(self.destinationTile):
            raise ValueError(
                f"Invalid destination tile name: {self.destinationTile} for wire "
                f"{self}, "
                "your destination is located out side of the fabric, please check "
                "the source and destination port offset."
            )

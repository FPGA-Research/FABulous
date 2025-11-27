"""Wire class for managing connections between tiles."""

import re
from dataclasses import dataclass

from FABulous.fabric_definition.define import Direction


@dataclass(frozen=True, eq=True)
class Wire:
    """Store wire connections that span across multiple tiles.

    If working on connections between two adjacent tiles,
    the Port class should have all the required information.
    The main use of this class is to assist model generation,
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
        """Return string representation of the wire.

        Returns
        -------
        str
            A compact string showing source, offsets, and destination.
        """
        return f"{self.source}-X{self.xOffset}Y{self.yOffset}>{self.destination}"

    def __eq__(self, __o: object, /) -> bool:
        """Check if two `Wire` objects are equal.

        Two wires are considered equal if they have the same
        source and destination names.

        Parameters
        ----------
        __o : object
            The object to compare with.

        Returns
        -------
        bool
            True if the wires are equal, False otherwise.
        """
        if __o is None or not isinstance(__o, Wire):
            return False
        return self.source == __o.source and self.destination == __o.destination

    def __post_init__(self) -> None:
        """Validate wire configuration after initialization.

        Check that source and destination tile names follow the expected format
        (X{num}Y{num}) or are empty for boundary conditions. This validation
        ensures that wires don't reference tiles outside the fabric boundaries.

        Raises
        ------
        ValueError
            If source or destination tile names are invalid for non-zero offsets.
        """

        def validSourceDestination(name: str) -> bool:
            """Check if the source or destination tile name is valid."""
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

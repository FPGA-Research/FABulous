"""Port geometry definitions."""

from dataclasses import dataclass
from enum import Enum

from FABulous.fabric_definition.define import IO, Direction, Side


class PortType(Enum):
    """Enumeration for different types of ports in the fabric geometry.

    Defines the various categories of ports that can exist within the fabric:
    - SWITCH_MATRIX: Ports connected to switch matrices
    - JUMP: Jump ports for long-distance connections
    - BEL: Ports connected to Basic Elements of Logic
    """

    SWITCH_MATRIX = "PORT"
    JUMP = "JUMP_PORT"
    BEL = "BEL_PORT"


@dataclass
class PortGeometry:
    """A data structure representing the geometry of a Port.

    Sets all attributes to default values: None for names and directions,
    zero for numeric values, and appropriate defaults for enumerated types.

    Attributes
    ----------
    name : str | None, optional
        Name of the port
    sourceName : str | None, optional
        Name of the port source
    destName : str | None, optional
        Name of the port destination
    type : PortType | None, optional
        Type of the port
    ioDirection : IO
        IO direction of the port.
    sideOfTile : Side
        Side of the tile the port's wire is on.
    offset : int
        Offset to the connected port.
    wireDirection : Direction | None, optional
        Direction of the ports wire
    groupId : int
        ID of the port group.
    groupWires : int
        Number of wires in the port group.
    relX : int
        X coordinate of the port, relative to its parent (bel, switch matrix).
    relY : int
        Y coordinate of the port, relative to its parent (bel, switch matrix).
    nextId : int
        ID of the next port in the group.
    """

    name: str | None = None
    sourceName: str | None = None
    destName: str | None = None
    type: PortType | None = None
    ioDirection: IO = IO.NULL
    sideOfTile: Side = Side.ANY
    offset: int = 0
    wireDirection: Direction | None = None
    groupId: int = 0
    groupWires: int = 0
    relX: int = 0
    relY: int = 0
    nextId: int = 1

    def generateGeometry(
        self,
        name: str,
        sourceName: str,
        destName: str,
        portType: PortType,
        ioDirection: IO,
        relX: int,
        relY: int,
    ) -> None:
        """Generate the geometry for a port.

        Sets the basic geometric and connection properties of the port,
        including its name, source/destination connections, type, I/O direction,
        and relative position within its parent component.

        Parameters
        ----------
        name : str
            Name of the port
        sourceName : str
            Name of the port source
        destName : str
            Name of the port destination
        portType : PortType
            Type of the port (SWITCH_MATRIX, JUMP, or BEL)
        ioDirection : IO
            I/O direction of the port (INPUT, OUTPUT, or INOUT)
        relX : int
            X coordinate relative to the parent component
        relY : int
            Y coordinate relative to the parent component
        """
        self.name = name
        self.sourceName = sourceName
        self.destName = destName
        self.type = portType
        self.ioDirection = ioDirection
        self.relX = relX
        self.relY = relY

    def saveToCSV(self, writer: object) -> None:
        """Save port geometry data to CSV format.

        Writes the port geometry information including type, name,
        source/destination connections, I/O direction, and relative
        position to a CSV file using the provided writer.

        Parameters
        ----------
        writer : object
            The CSV `writer` object to use for output
        """
        writer.writerows(
            [
                [self.type.value],
                ["Name"] + [self.name],
                ["Source"] + [self.sourceName],
                ["Dest"] + [self.destName],
                ["IO"] + [self.ioDirection.value],
                ["RelX"] + [str(self.relX)],
                ["RelY"] + [str(self.relY)],
                [],
            ]
        )

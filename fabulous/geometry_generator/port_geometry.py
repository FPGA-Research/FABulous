"""Port geometry definitions."""

from dataclasses import dataclass
from enum import Enum

from fabulous.fabric_definition.define import IO, Direction, Side


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
    source_name : str | None, optional
        Name of the port source
    destName : str | None, optional
        Name of the port destination
    type : PortType | None, optional
        Type of the port
    io_direction : IO
        IO direction of the port.
    side_of_tile : Side
        Side of the tile the port's wire is on.
    offset : int
        Offset to the connected port.
    wire_direction : Direction | None, optional
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
    source_name: str | None = None
    destName: str | None = None
    type: PortType | None = None
    io_direction: IO = IO.NULL
    side_of_tile: Side = Side.ANY
    offset: int = 0
    wire_direction: Direction | None = None
    groupId: int = 0
    groupWires: int = 0
    relX: int = 0
    relY: int = 0
    nextId: int = 1

    def generateGeometry(
        self,
        name: str,
        source_name: str,
        destName: str,
        portType: PortType,
        io_direction: IO,
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
        source_name : str
            Name of the port source
        destName : str
            Name of the port destination
        portType : PortType
            Type of the port (SWITCH_MATRIX, JUMP, or BEL)
        io_direction : IO
            I/O direction of the port (INPUT, OUTPUT, or INOUT)
        relX : int
            X coordinate relative to the parent component
        relY : int
            Y coordinate relative to the parent component
        """
        self.name = name
        self.source_name = source_name
        self.destName = destName
        self.type = portType
        self.io_direction = io_direction
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
                ["Source"] + [self.source_name],
                ["Dest"] + [self.destName],
                ["IO"] + [self.io_direction.value],
                ["RelX"] + [str(self.relX)],
                ["RelY"] + [str(self.relY)],
                [],
            ]
        )

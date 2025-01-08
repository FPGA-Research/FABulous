from csv import writer as csvWriter
from enum import Enum

from FABulous.fabric_definition.define import IO, Side


class PortType(Enum):
    SWITCH_MATRIX = "PORT"
    JUMP = "JUMP_PORT"
    BEL = "BEL_PORT"


class PortGeometry:
    """A data structure representing the geometry of a Port

    Attributes
    ----------
    name : str
        Name of the port
    sourceName : str
        Name of the port source
    destName : str
        Name of the port destination
    type : PortType
        Type of the port
    ioDirection : IO
        IO direction of the port
    sideOfTile : Side
        Side of the tile the ports wire is on
    offset : int
        Offset to the connected port
    wireDirection : Direction
        Direction of the ports wire
    groupId : int
        Id of the port group
    groupWires : int
        Amount of wires of the port group
    relX : int
        X coordinate of the port, relative to its parent (bel, switch matrix)
    relY : int
        Y coordinate of the port, relative to its parent (bel, switch matrix)
    """

    name: str
    sourceName: str
    destName: str
    type: PortType
    ioDirection: IO
    sideOfTile: Side
    offset: int
    groupId: int
    groupWires: int
    relX: int
    relY: int

    nextId = 1

    def __init__(self):
        self.name = None
        self.sourceName = None
        self.destName = None
        self.type = None
        self.ioDirection = IO.NULL
        self.sideOfTile = Side.ANY
        self.offset = 0
        self.wireDirection = None
        self.groupId = 0
        self.groupWires = 0
        self.relX = 0
        self.relY = 0

    def generateGeometry(
        self,
        name: str,
        sourceName: str,
        destName: str,
        type: PortType,
        ioDirection: IO,
        relX: int,
        relY: int,
    ) -> None:
        self.name = name
        self.sourceName = sourceName
        self.destName = destName
        self.type = type
        self.ioDirection = ioDirection
        self.relX = relX
        self.relY = relY

    def saveToCSV(self, writer: csvWriter) -> None:
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

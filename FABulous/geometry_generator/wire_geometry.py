from csv import writer as csvWriter

from FABulous.custom_exception import InvalidPortType
from FABulous.fabric_definition.Fabric import Direction
from FABulous.geometry_generator.geometry_obj import Location


class WireGeometry:
    """A data structure representing the geometry of a wire within a tile.

    Attributes
    ----------
    name : str
        Name of the wire
    path : List[Location]
        Path of the wire
    """

    name: str
    path: list[Location]

    def __init__(self, name: str) -> None:
        self.name = name
        self.path = []

    def addPathLoc(self, pathLoc: Location) -> None:
        self.path.append(pathLoc)

    def saveToCSV(self, writer: csvWriter) -> None:
        writer.writerows([["WIRE"], ["Name"] + [self.name]])
        for pathPoint in self.path:
            writer.writerows(
                [["RelX"] + [str(pathPoint.x)], ["RelY"] + [str(pathPoint.y)]]
            )
        writer.writerow([])


class StairWires:
    """A data structure representing a stair-like collection of wires.

    Attributes
    ----------
    name : str
        Name of the structure
    refX : int
        Reference point x coord of the stair structure
    refY : int
        Reference point y coord of the stair structure
    offset : int
        Offset of the wires
    direction : Direction
        Direction of the wires
    groupWires : int
        Amount of wires of a single "strand"
    tileWidth : int
        Width of the tile containing the wires
    tileHeight : int
        Height of the tile containing the wires
    wireGeoms : List[WireGeometry]
        List of the wires geometries

    Structure
    ---------
    The (refX, refY) point refers to the following location(s) of the stair-like structure:

    .. asciiart::

        |        @   @   @                  @@  @@  @@
        |        @   @   @                  @@  @@  @@
        |        @   @   @                  @@  @@  @@
        |        @   @   @                  @@  @@  @@
        |        @   @   @                  @@  @@  @@
        |        @   @   @@@@@@@@     @@@@@@@@  @@  @@
        |        @   @         @@     @         @@  @@
        |        @   @@@@@@@.  @@     @   @@@@@@@@  @@
        |        @         @.  @@     @   @@        @@
        |    --> @@@@@@.@  @.  @@     @   @. .@@@@@@@@  <-- (refX, refY)
        |              .@  @.  @@     @   @. .@
        |              .@  @.  @@     @   @. .@
        |              .@  @.  @@     @   @. .@
        |              .@  @.  @@     @   @. .@
        |              .@  @@  @@     @   @. .@


    Depending on the orientation of the structure. Rotate right by 90° to get
    the image for the corresponding left-right stair-ike wire structure.
    The right stair-like structure represents a north stair, the left one
    represents a south stair (These being the directions of the wires).
    """

    name: str
    refX: int
    refY: int
    offset: int
    direction: Direction
    groupWires: int
    tileWidth: int
    tileHeight: int
    wireGeoms: list[WireGeometry]

    def __init__(self, name: str) -> None:
        self.name = name
        self.refX = 0
        self.refY = 0
        self.offset = 0
        self.direction = None
        self.groupWires = 0
        self.tileWidth = 0
        self.tileHeight = 0
        self.wireGeoms = []

    def generateGeometry(
        self,
        refX: int,
        refY: int,
        offset: int,
        direction: Direction,
        groupWires: int,
        tileWidth: int,
        tileHeight: int,
    ) -> None:
        self.refX = refX
        self.refY = refY
        self.offset = offset
        self.direction = direction
        self.groupWires = groupWires
        self.tileWidth = tileWidth
        self.tileHeight = tileHeight

        if self.direction == Direction.NORTH:
            self.generateNorthStairWires()
        elif self.direction == Direction.SOUTH:
            self.generateSouthStairWires()
        elif self.direction == Direction.EAST:
            self.generateEastStairWires()
        elif self.direction == Direction.WEST:
            self.generateWestStairWires()
        else:
            raise InvalidPortType(
                f"Invalid direction {self.direction} for stair wires!"
            )

    def generateNorthStairWires(self) -> None:
        totalWires = self.groupWires * (abs(self.offset) - 1)
        refX = self.refX
        refY = self.refY

        for i in range(totalWires):
            wireGeom = WireGeometry(f"{self.name} #{i}")
            start = Location(refX, 0)
            nextToStart = Location(refX, refY)
            nextToEnd = Location(refX - self.groupWires, refY)
            end = Location(refX - self.groupWires, self.tileHeight)

            wireGeom.addPathLoc(start)
            wireGeom.addPathLoc(nextToStart)
            wireGeom.addPathLoc(nextToEnd)
            wireGeom.addPathLoc(end)
            self.wireGeoms.append(wireGeom)

            refX -= 1
            refY -= 1

    def generateSouthStairWires(self) -> None:
        totalWires = self.groupWires * (abs(self.offset) - 1)
        refX = self.refX
        refY = self.refY

        for i in range(totalWires):
            wireGeom = WireGeometry(f"{self.name} #{i}")
            start = Location(refX, 0)
            nextToStart = Location(refX, refY)
            nextToEnd = Location(refX + self.groupWires, refY)
            end = Location(refX + self.groupWires, self.tileHeight)

            wireGeom.addPathLoc(start)
            wireGeom.addPathLoc(nextToStart)
            wireGeom.addPathLoc(nextToEnd)
            wireGeom.addPathLoc(end)
            self.wireGeoms.append(wireGeom)

            refX += 1
            refY -= 1

    def generateEastStairWires(self) -> None:
        totalWires = self.groupWires * (abs(self.offset) - 1)
        refX = self.refX
        refY = self.refY

        for i in range(totalWires):
            wireGeom = WireGeometry(f"{self.name} #{i}")
            start = Location(self.tileWidth, refY)
            nextToStart = Location(refX, refY)
            nextToEnd = Location(refX, refY + self.groupWires)
            end = Location(0, refY + self.groupWires)

            wireGeom.addPathLoc(start)
            wireGeom.addPathLoc(nextToStart)
            wireGeom.addPathLoc(nextToEnd)
            wireGeom.addPathLoc(end)
            self.wireGeoms.append(wireGeom)

            refX += 1
            refY += 1

    def generateWestStairWires(self) -> None:
        totalWires = self.groupWires * (abs(self.offset) - 1)
        refX = self.refX
        refY = self.refY

        for i in range(totalWires):
            wireGeom = WireGeometry(f"{self.name} #{i}")
            start = Location(self.tileWidth, refY)
            nextToStart = Location(refX, refY)
            nextToEnd = Location(refX, refY - self.groupWires)
            end = Location(0, refY - self.groupWires)

            wireGeom.addPathLoc(start)
            wireGeom.addPathLoc(nextToStart)
            wireGeom.addPathLoc(nextToEnd)
            wireGeom.addPathLoc(end)
            self.wireGeoms.append(wireGeom)

            refX += 1
            refY -= 1

    def saveToCSV(self, writer: csvWriter) -> None:
        for wireGeom in self.wireGeoms:
            wireGeom.saveToCSV(writer)


class WireConstraints:
    """
        A simple datastruct for storing
        information on where wires arrive
        at the border of a tile.

        Attributes:
            northPositions: List[int]
            southPositions: List[int]
            eastPositions: List[int]
            westPositions: List[int]

    """
    northPositions: list[int]
    southPositions: list[int]
    eastPositions: list[int]
    westPositions: list[int]

    def __init__(self):
        self.northPositions = []
        self.southPositions = []
        self.eastPositions = []
        self.westPositions = []

    def addConstraintsOf(self, stairWires: StairWires) -> None:
        totalWires = stairWires.groupWires * (abs(stairWires.offset) - 1)

        if stairWires.direction == Direction.NORTH:
            refX = stairWires.refX

            for i in range(totalWires):
                self.northPositions.append(refX)
                self.southPositions.append(refX - stairWires.groupWires)
                refX -= 1

        if stairWires.direction == Direction.SOUTH:
            refX = stairWires.refX

            for i in range(totalWires):
                self.northPositions.append(refX)
                self.southPositions.append(refX + stairWires.groupWires)
                refX += 1

        if stairWires.direction == Direction.EAST:
            refY = stairWires.refY

            for i in range(totalWires):
                self.eastPositions.append(refY)
                self.westPositions.append(refY + stairWires.groupWires)
                refY += 1

        if stairWires.direction == Direction.WEST:
            refY = stairWires.refY

            for i in range(totalWires):
                self.eastPositions.append(refY)
                self.westPositions.append(refY - stairWires.groupWires)
                refY -= 1

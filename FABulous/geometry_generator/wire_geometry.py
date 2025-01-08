from csv import writer as csvWriter
from typing import List
from loguru import logger

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
    path: List[Location]

    def __init__(self, name: str):
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
    ::

               @   @   @                  @@  @@  @@
               @   @   @                  @@  @@  @@
               @   @   @                  @@  @@  @@
               @   @   @                  @@  @@  @@
               @   @   @                  @@  @@  @@
               @   @   @@@@@@@@     @@@@@@@@  @@  @@
               @   @         @@     @         @@  @@
               @   @@@@@@@%  @@     @   @@@@@@@@  @@
               @         @%  @@     @   @@        @@
          -->  @@@@@@%@  @%  @@     @   @# #@@@@@@@@  <-- (refX, refY)
                     %@  @%  @@     @   @# #@
                     %@  @%  @@     @   @# #@
                     %@  @%  @@     @   @# #@
                     %@  @%  @@     @   @# #@
                     %@  @@  @@     @   @# #@

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
    wireGeoms: List[WireGeometry]

    def __init__(self, name: str):
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
            logger.critical("Invalid direction!")
            raise Exception

    def generateNorthStairWires(self) -> None:
        totalWires = self.groupWires * (abs(self.offset) - 1)

        for i in range(totalWires):
            wireGeom = WireGeometry(f"{self.name} #{i}")
            start = Location(self.refX, 0)
            nextToStart = Location(self.refX, self.refY)
            nextToEnd = Location(self.refX - self.groupWires, self.refY)
            end = Location(self.refX - self.groupWires, self.tileHeight)

            wireGeom.addPathLoc(start)
            wireGeom.addPathLoc(nextToStart)
            wireGeom.addPathLoc(nextToEnd)
            wireGeom.addPathLoc(end)
            self.wireGeoms.append(wireGeom)

            self.refX -= 1
            self.refY -= 1

    def generateSouthStairWires(self) -> None:
        totalWires = self.groupWires * (abs(self.offset) - 1)

        for i in range(totalWires):
            wireGeom = WireGeometry(f"{self.name} #{i}")
            start = Location(self.refX, 0)
            nextToStart = Location(self.refX, self.refY)
            nextToEnd = Location(self.refX + self.groupWires, self.refY)
            end = Location(self.refX + self.groupWires, self.tileHeight)

            wireGeom.addPathLoc(start)
            wireGeom.addPathLoc(nextToStart)
            wireGeom.addPathLoc(nextToEnd)
            wireGeom.addPathLoc(end)
            self.wireGeoms.append(wireGeom)

            self.refX += 1
            self.refY -= 1

    def generateEastStairWires(self) -> None:
        totalWires = self.groupWires * (abs(self.offset) - 1)

        for i in range(totalWires):
            wireGeom = WireGeometry(f"{self.name} #{i}")
            start = Location(self.tileWidth, self.refY)
            nextToStart = Location(self.refX, self.refY)
            nextToEnd = Location(self.refX, self.refY + self.groupWires)
            end = Location(0, self.refY + self.groupWires)

            wireGeom.addPathLoc(start)
            wireGeom.addPathLoc(nextToStart)
            wireGeom.addPathLoc(nextToEnd)
            wireGeom.addPathLoc(end)
            self.wireGeoms.append(wireGeom)

            self.refX += 1
            self.refY += 1

    def generateWestStairWires(self) -> None:
        totalWires = self.groupWires * (abs(self.offset) - 1)

        for i in range(totalWires):
            wireGeom = WireGeometry(f"{self.name} #{i}")
            start = Location(self.tileWidth, self.refY)
            nextToStart = Location(self.refX, self.refY)
            nextToEnd = Location(self.refX, self.refY - self.groupWires)
            end = Location(0, self.refY - self.groupWires)

            wireGeom.addPathLoc(start)
            wireGeom.addPathLoc(nextToStart)
            wireGeom.addPathLoc(nextToEnd)
            wireGeom.addPathLoc(end)
            self.wireGeoms.append(wireGeom)

            self.refX += 1
            self.refY -= 1

    def saveToCSV(self, writer: csvWriter) -> None:
        for wireGeom in self.wireGeoms:
            wireGeom.saveToCSV(writer)

"""Wire geometry classes for FABulous FPGA routing structures.

This module provides classes for representing wire geometries within FPGA tiles,
including simple wires and complex stair-like wire structures for multi-tile routing. It
supports CSV serialization for integration with geometry files.
"""

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
        """Initialize a WireGeometry instance.

        Parameters
        ----------
        name : str
            The name of the wire
        """
        self.name = name
        self.path = []

    def addPathLoc(self, pathLoc: Location) -> None:
        """Add a location point to the wire path.

        Parameters
        ----------
        pathLoc : Location
            The location point to add to the wire path
        """
        self.path.append(pathLoc)

    def saveToCSV(self, writer: object) -> None:
        """Save wire geometry data to CSV format.

        Writes the wire name and all path points with their coordinates
        to a CSV file using the provided writer.

        Parameters
        ----------
        writer
            The CSV writer object to use for output
        """
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
    The (refX,refY) point refers to the following location(s)
    of the stair-like structure:

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
        """Initialize a StairWires instance.

        Parameters
        ----------
        name : str
            The name of the stair wire structure
        """
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
        """Generate the stair wire geometry based on parameters and direction.

        Creates the complete stair-like wire structure by calling the appropriate
        directional generation method based on the specified direction.

        Parameters
        ----------
        refX : int
            Reference X coordinate for the stair structure
        refY : int
            Reference Y coordinate for the stair structure
        offset : int
            Wire offset distance
        direction : Direction
            Direction of the wire routing (NORTH, SOUTH, EAST, or WEST)
        groupWires : int
            Number of wires in each group or strand
        tileWidth : int
            Width of the containing tile
        tileHeight : int
            Height of the containing tile

        Raises
        ------
        InvalidPortType
            If an invalid direction is provided
        """
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
        """Generate stair-like wires for north direction routing.

        Creates a series of L-shaped wire segments that form a stair-like pattern for
        routing connections northward across multiple tiles. Each wire starts at the
        bottom edge, goes to a stair step, then continues to the top edge.
        """
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
        """Generate stair-like wires for south direction routing.

        Creates a series of L-shaped wire segments that form a stair-like pattern for
        routing connections southward across multiple tiles. Each wire starts at the
        bottom edge, goes to a stair step, then continues to the top edge.
        """
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
        """Generate stair-like wires for east direction routing.

        Creates a series of L-shaped wire segments that form a stair-like pattern for
        routing connections eastward across multiple tiles. Each wire starts at the
        right edge, goes to a stair step, then continues to the left edge.
        """
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
        """Generate stair-like wires for west direction routing.

        Creates a series of L-shaped wire segments that form a stair-like pattern for
        routing connections westward across multiple tiles. Each wire starts at the
        right edge, goes to a stair step, then continues to the left edge.
        """
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

    def saveToCSV(self, writer: object) -> None:
        """Save all stair wire geometries to CSV format.

        Writes all individual wire geometries in the stair structure
        to a CSV file using the provided writer.

        Parameters
        ----------
        writer
            The CSV writer object to use for output
        """
        for wireGeom in self.wireGeoms:
            wireGeom.saveToCSV(writer)

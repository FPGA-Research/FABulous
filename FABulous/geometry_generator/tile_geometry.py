"""Tile geometry generation and management for FABulous FPGA tiles.

This module provides the `TileGeometry` class for representing and generating the
geometric layout of FPGA tiles, including switch matrices, BELs, and interconnect wires.
It handles both direct connections to neighboring tiles and complex stair-like routing
for longer-distance connections.
"""

from csv import writer as csvWriter
from dataclasses import dataclass, field

from FABulous.custom_exception import InvalidPortType
from FABulous.fabric_definition.define import Direction, Side
from FABulous.fabric_definition.Tile import Tile
from FABulous.geometry_generator.bel_geometry import BelGeometry
from FABulous.geometry_generator.geometry_obj import Border, Location
from FABulous.geometry_generator.port_geometry import PortGeometry
from FABulous.geometry_generator.sm_geometry import SmGeometry
from FABulous.geometry_generator.wire_geometry import (
    StairWires,
    WireConstraints,
    WireGeometry,
)


@dataclass
class TileGeometry:
    """A data structure representing the geometry of a tile.

    Initializes all attributes to default values: empty name, zero dimensions,
    no border, and empty lists for geometric components.

    Attributes
    ----------
    name : str
        Name of the tile
    width : int
        Width of the tile
    height : int
        Height of the tile
    border : Border
        Border of the fabric the tile is on
    wireConstraints : WireConstraints
        Wire constraints of the tile
    neighbourConstraints : WireConstraints | None
        Wire constraints of neighbouring tiles
    smGeometry : SmGeometry
        Geometry of the tiles switch matrix
    belGeomList : list[BelGeometry]
        List of the geometries of the tiles bels
    wireGeomList : list[WireGeometry]
        List of the geometries of the tiles wires
    stairWiresList : list[StairWires]
        List of the stair-like wires of the tile
    currPortGroupId : int
        Current port group ID being processed
    queuedAdjustmentBottom : int
        Queued adjustment for bottom positioning
    queuedAdjustmentLeft : int
        Queued adjustment for left positioning
    reserveStairSpaceBottom : bool
        Whether to reserve space at bottom for stair wires
    reserveStairSpaceLeft : bool
        Whether to reserve space at left for stair wires
    eastMiddleY : int
        Middle Y coordinate for east side
    northMiddleX : int
        Middle X coordinate for north side
    southMiddleX : int
        Middle X coordinate for south side
    westMiddleY : int
        Middle Y coordinate for west side
    """

    name: str = ""
    width: int = 0
    height: int = 0
    border: Border = Border.NONE
    wireConstraints: WireConstraints = WireConstraints()
    neighbourConstraints: WireConstraints | None = None
    smGeometry: SmGeometry = field(default_factory=SmGeometry)
    belGeomList: list[BelGeometry] = field(default_factory=list)
    wireGeomList: list[WireGeometry] = field(default_factory=list)
    stairWiresList: list[StairWires] = field(default_factory=list)
    currPortGroupId: int = 0
    queuedAdjustmentBottom: int = 0
    queuedAdjustmentLeft: int = 0
    reserveStairSpaceBottom: bool = False
    reserveStairSpaceLeft: bool = False
    eastMiddleY: int = 0
    northMiddleX: int = 0
    southMiddleX: int = 0
    westMiddleY: int = 0

    def generateGeometry(self, tile: Tile, padding: int) -> None:
        """Generate the geometry for a tile.

        Creates geometric representations for all BELs and the switch matrix,
        then calculates the overall tile dimensions based on the generated components
        and padding requirements.

        Parameters
        ----------
        tile : Tile
            The `Tile` object to generate geometry for
        padding : int
            The padding space to add around components
        """
        self.name = tile.name

        for bel in tile.bels:
            belGeom = BelGeometry()
            belGeom.generateGeometry(bel, padding)
            self.belGeomList.append(belGeom)

        self.smGeometry.generateGeometry(tile, self.border, self.belGeomList, padding)

        maxBelWidth = max([belGeom.width for belGeom in self.belGeomList] + [0])
        self.width = (
            self.smGeometry.relX + self.smGeometry.width + 2 * padding + maxBelWidth
        )

        self.height = (
            self.smGeometry.relY
            + self.smGeometry.height
            + max(
                self.smGeometry.eastWiresReservedHeight,
                self.smGeometry.westWiresReservedHeight,
            )
            + 2 * padding
        )

    def adjustDimensions(
        self,
        maxWidthInColumn: int,
        maxHeightInRow: int,
        maxSmWidthInColumn: int,
        maxSmRelXInColumn: int,
    ) -> None:
        """Adjust tile dimensions to match maximum values in fabric grid.

        Normalizes the tile dimensions and switch matrix positioning to align
        with the maximum dimensions found in the same fabric column/row,
        ensuring uniform tile sizing across the fabric.

        Parameters
        ----------
        maxWidthInColumn : int
            Maximum width among tiles in the same column
        maxHeightInRow : int
            Maximum height among tiles in the same row
        maxSmWidthInColumn : int
            Maximum switch matrix width in the same column
        maxSmRelXInColumn : int
            Maximum switch matrix relative X position in the same column
        """
        self.width = maxWidthInColumn
        self.height = maxHeightInRow
        self.smGeometry.width = maxSmWidthInColumn  # TODO: needed?
        self.smGeometry.relX = maxSmRelXInColumn

        # TODO: dim.smWidth = dim.smWidth*2 if dim.smWidth*2 < maxSmWidths[j]
        # else dim.smWidth

    def adjustSmPos(self, lowestSmYInRow: int, padding: int) -> None:
        """Ajusts the position of the switch matrix.

        This is done by using the lowest Y coordinate of any switch matrix in the same
        row for reference.

        After this step is completed for all switch matrices, their southern edge will
        be on the same Y coordinate, allowing for easier inter-tile routing.
        """
        currentSmY = self.smGeometry.relY + self.smGeometry.height
        additionalOffset = lowestSmYInRow - currentSmY
        self.smGeometry.relY += additionalOffset

        self.setBelPositions(padding)

        # Bel positions are set by now, so the bel ports
        # of the switch matrix can be generated now.
        self.smGeometry.generateBelPorts(self.belGeomList)

    def setBelPositions(self, padding: int) -> None:
        """Set BEL positions."""
        belPadding = padding // 2
        belX = self.smGeometry.relX + self.smGeometry.width + padding
        belY = self.smGeometry.relY + belPadding
        for belGeom in self.belGeomList:
            belGeom.adjustPos(belX, belY)
            belY += belGeom.height
            belY += belPadding

    def generateWires(self, padding: int) -> None:
        """Generate all wire geometries for the tile.

        Creates wire geometries for BEL connections, direct connections to
        neighboring tiles, and indirect connections requiring stair-like routing.
        Ensures proper alignment of wire positions across different tile types.

        Parameters
        ----------
        padding : int
            The padding space to add around wire routing
        """
        self.generateBelWires()
        self.generateDirectWires(padding)

        # This adjustment is done to ensure that wires
        # in tiles with less/more direct north than
        # south wires (and the same with east/west)
        # align, such as in some super-tiles.
        self.northMiddleX = min(self.northMiddleX, self.southMiddleX)
        self.southMiddleX = min(self.northMiddleX, self.southMiddleX)
        self.eastMiddleY = max(self.eastMiddleY, self.westMiddleY)
        self.westMiddleY = max(self.eastMiddleY, self.westMiddleY)

        self.generateIndirectWires(padding)

    def generateBelWires(self) -> None:
        """Generate the wires between the switch matrix and its bels."""
        for belGeom in self.belGeomList:
            belToSmDistanceX = belGeom.relX - (
                self.smGeometry.relX + self.smGeometry.width
            )

            for portGeom in belGeom.internalPortGeoms:
                wireName = f"{portGeom.sourceName} ⟶ {portGeom.destName}"
                wireGeom = WireGeometry(wireName)
                start = Location(
                    portGeom.relX + belGeom.relX, portGeom.relY + belGeom.relY
                )
                end = Location(
                    portGeom.relX + belGeom.relX - belToSmDistanceX,
                    portGeom.relY + belGeom.relY,
                )
                wireGeom.addPathLoc(start)
                wireGeom.addPathLoc(end)
                self.wireGeomList.append(wireGeom)

    def generateDirectWires(self, padding: int) -> None:
        """Generate wires to neighbouring tiles, which are straightforward to generate.

        Parameters
        ----------
        padding : int
            The padding value to use for wire generation

        Raises
        ------
        InvalidPortType
            If a port with offset 1 has no tile side defined
        """
        self.northMiddleX = self.smGeometry.relX - padding
        self.southMiddleX = self.smGeometry.relX - padding
        self.eastMiddleY = self.smGeometry.relY + self.smGeometry.height + padding
        self.westMiddleY = self.smGeometry.relY + self.smGeometry.height + padding

        if self.border == Border.NORTHSOUTH:
            wireNorthPositions = sorted(
                self.neighbourConstraints.southPositions, reverse=True
            )
            wireSouthPositions = sorted(
                self.neighbourConstraints.northPositions, reverse=True
            )
            northIter = iter(wireNorthPositions)
            southIter = iter(wireSouthPositions)
            self.northMiddleX = next(northIter, None)
            self.southMiddleX = next(southIter, None)

        if self.border == Border.EASTWEST:
            wireEastPositions = sorted(self.neighbourConstraints.westPositions)
            wireWestPositions = sorted(self.neighbourConstraints.eastPositions)
            eastIter = iter(wireEastPositions)
            westIter = iter(wireWestPositions)
            self.eastMiddleY = next(eastIter, None)
            self.westMiddleY = next(westIter, None)

        for portGeom in self.smGeometry.portGeoms:
            if abs(portGeom.offset) != 1:
                continue
            wireName = f"{portGeom.sourceName} ⟶ {portGeom.destName}"
            wireGeom = WireGeometry(wireName)

            if portGeom.sideOfTile == Side.NORTH:
                startX = self.smGeometry.relX
                startY = self.smGeometry.relY + portGeom.relY
                wireGeom.addPathLoc(Location(startX, startY))

                middleY = self.smGeometry.relY + portGeom.relY
                wireGeom.addPathLoc(Location(self.northMiddleX, middleY))

                endX = self.northMiddleX
                endY = 0
                wireGeom.addPathLoc(Location(endX, endY))
                self.wireConstraints.northPositions.append(self.northMiddleX)

                if self.border == Border.NORTHSOUTH:
                    self.northMiddleX = next(northIter, 0)
                else:
                    self.northMiddleX -= 1

            elif portGeom.sideOfTile == Side.SOUTH:
                startX = self.smGeometry.relX
                startY = self.smGeometry.relY + portGeom.relY
                wireGeom.addPathLoc(Location(startX, startY))

                middleY = self.smGeometry.relY + portGeom.relY
                wireGeom.addPathLoc(Location(self.southMiddleX, middleY))

                endX = self.southMiddleX
                endY = self.height
                wireGeom.addPathLoc(Location(endX, endY))
                self.wireConstraints.southPositions.append(self.southMiddleX)

                if self.border == Border.NORTHSOUTH:
                    self.southMiddleX = next(southIter, 0)
                else:
                    self.southMiddleX -= 1

            elif portGeom.sideOfTile == Side.EAST:
                startX = self.smGeometry.relX + portGeom.relX
                startY = self.smGeometry.relY + self.smGeometry.height
                wireGeom.addPathLoc(Location(startX, startY))

                middleX = self.smGeometry.relX + portGeom.relX
                wireGeom.addPathLoc(Location(middleX, self.eastMiddleY))

                endX = self.width
                endY = self.eastMiddleY
                wireGeom.addPathLoc(Location(endX, endY))
                self.wireConstraints.eastPositions.append(self.eastMiddleY)

                if self.border == Border.EASTWEST:
                    self.eastMiddleY = next(eastIter, 0)
                else:
                    self.eastMiddleY += 1

            elif portGeom.sideOfTile == Side.WEST:
                startX = self.smGeometry.relX + portGeom.relX
                startY = self.smGeometry.relY + self.smGeometry.height
                wireGeom.addPathLoc(Location(startX, startY))

                middleX = self.smGeometry.relX + portGeom.relX
                wireGeom.addPathLoc(Location(middleX, self.westMiddleY))

                endX = 0
                endY = self.westMiddleY
                wireGeom.addPathLoc(Location(endX, endY))
                self.wireConstraints.westPositions.append(self.westMiddleY)

                if self.border == Border.EASTWEST:
                    self.westMiddleY = next(westIter, 0)
                else:
                    self.westMiddleY += 1

            else:
                raise InvalidPortType(
                    f"Port with offset 1 and no tile side! {portGeom}"
                )

            self.wireGeomList.append(wireGeom)

    def generateIndirectWires(self, padding: int) -> None:
        """Generate wires to non-neighbouring tiles.

        These wires require staircase-like routing patterns to reach tiles
        that are not direct neighbors (offset >= 2). The routing varies
        by tile side and wire direction.

        Parameters
        ----------
        padding : int
            The padding space to add around wire routing

        Raises
        ------
        InvalidPortType
            If a port has abs(offset) > 1 but no tile side assigned.
        """
        for portGeom in self.smGeometry.portGeoms:
            if abs(portGeom.offset) < 2:
                continue

            if portGeom.sideOfTile == Side.NORTH:
                self.indirectNorthSideWire(portGeom, padding)
            elif portGeom.sideOfTile == Side.SOUTH:
                self.indirectSouthSideWire(portGeom)
            elif portGeom.sideOfTile == Side.EAST:
                self.indirectEastSideWire(portGeom, padding)
            elif portGeom.sideOfTile == Side.WEST:
                self.indirectWestSideWire(portGeom)
            else:
                raise InvalidPortType(
                    f"Port with abs(offset) > 1 and no tile side! {portGeom}"
                )

    def indirectNorthSideWire(self, portGeom: PortGeometry, padding: int) -> None:
        """Generate indirect wires with stair-like routing.

        Creates staircase-shaped wire routing for connections that span multiple tiles
        northward. Manages stair wire generation and space reservation based on
        wire direction and grouping.

        Parameters
        ----------
        portGeom : PortGeometry
            The port geometry defining the wire characteristics
        padding : int
            The padding space around the wire routing
        """
        generateNorthSouthStairWire = (
            self.border != Border.NORTHSOUTH and self.border != Border.CORNER
        )

        # with a new group of ports, there will be the
        # need for a new stair-like wire for that group
        if generateNorthSouthStairWire and self.currPortGroupId != portGeom.groupId:
            self.currPortGroupId = portGeom.groupId

            if self.reserveStairSpaceLeft:
                self.reserveStairSpaceLeft = False
                lastStair = self.stairWiresList[-1]
                lastStairWidth = lastStair.groupWires * (abs(lastStair.offset) - 1)
                self.northMiddleX -= lastStairWidth

            xOffset = 0
            if portGeom.wireDirection == Direction.SOUTH:
                self.reserveStairSpaceLeft = True
                xOffset = portGeom.groupWires * abs(portGeom.offset) - 1

            stairWiresName = f"({portGeom.sourceName} ⟶ {portGeom.destName})"
            stairWires = StairWires(stairWiresName)
            stairWires.generateGeometry(
                self.northMiddleX - xOffset,
                self.smGeometry.southPortsTopY + self.smGeometry.relY - padding,
                portGeom.offset,
                portGeom.wireDirection,
                portGeom.groupWires,
                self.width,
                self.height,
            )
            self.stairWiresList.append(stairWires)
            self.wireConstraints.addConstraintsOf(stairWires)

            if portGeom.wireDirection == Direction.NORTH:
                stairReservedWidth = portGeom.groupWires * (abs(portGeom.offset) - 1)
                self.northMiddleX -= stairReservedWidth

        wireName = f"{portGeom.sourceName} ⟶ {portGeom.destName}"
        wireGeom = WireGeometry(wireName)
        start = Location(self.northMiddleX, 0)
        middle = Location(self.northMiddleX, self.smGeometry.relY + portGeom.relY)
        end = Location(self.smGeometry.relX, self.smGeometry.relY + portGeom.relY)
        wireGeom.addPathLoc(start)
        wireGeom.addPathLoc(middle)
        wireGeom.addPathLoc(end)
        self.wireGeomList.append(wireGeom)
        self.wireConstraints.northPositions.append(self.northMiddleX)
        self.northMiddleX -= 1

    def indirectSouthSideWire(self, portGeom: PortGeometry) -> None:
        """Generate indirect wires on the south side without creating stair-like wires.

        Creates L-shaped wire routing for southward connections. Unlike north side
        wires, this method only generates the connection wires and reserves space
        for stair wires created by the north side method.

        Parameters
        ----------
        portGeom : PortGeometry
            The port geometry defining the wire characteristics
        """
        generateNorthSouthStairWire = (
            self.border != Border.NORTHSOUTH and self.border != Border.CORNER
        )

        # with a new group of ports, there will be the
        # need for space for the generated stair-like wire
        if generateNorthSouthStairWire and self.currPortGroupId != portGeom.groupId:
            self.currPortGroupId = portGeom.groupId

            self.southMiddleX -= self.queuedAdjustmentLeft
            stairReservedWidth = portGeom.groupWires * (abs(portGeom.offset) - 1)

            # depending on the direction, do the adjustment
            # now, or queue it - taking the different "bending"
            # of the stair-like wire into account.
            if portGeom.wireDirection == Direction.NORTH:
                self.queuedAdjustmentLeft = stairReservedWidth

            if portGeom.wireDirection == Direction.SOUTH:
                self.southMiddleX -= stairReservedWidth
                self.queuedAdjustmentLeft = 0

        wireName = f"{portGeom.sourceName} ⟶ {portGeom.destName}"
        wireGeom = WireGeometry(wireName)
        start = Location(self.southMiddleX, self.height)
        middle = Location(self.southMiddleX, self.smGeometry.relY + portGeom.relY)
        end = Location(self.smGeometry.relX, self.smGeometry.relY + portGeom.relY)
        wireGeom.addPathLoc(start)
        wireGeom.addPathLoc(middle)
        wireGeom.addPathLoc(end)
        self.wireGeomList.append(wireGeom)
        self.wireConstraints.southPositions.append(self.southMiddleX)
        self.southMiddleX -= 1

    def indirectEastSideWire(self, portGeom: PortGeometry, padding: int) -> None:
        """Generate indirect wires on the east side of the tile with stair-like routing.

        Creates staircase-shaped wire routing for connections that span multiple tiles
        eastward. Manages stair wire generation and space reservation based on
        wire direction and grouping.

        Parameters
        ----------
        portGeom : PortGeometry
            The port geometry defining the wire characteristics
        padding : int
            The padding space around the wire routing
        """
        generateEastWestStairWire = (
            self.border != Border.EASTWEST and self.border != Border.CORNER
        )

        # with a new group of ports, there will be the
        # need for a new stair-like wire for that group
        if generateEastWestStairWire and self.currPortGroupId != portGeom.groupId:
            self.currPortGroupId = portGeom.groupId

            if self.reserveStairSpaceBottom:
                self.reserveStairSpaceBottom = False
                lastStair = self.stairWiresList[-1]
                lastStairWidth = lastStair.groupWires * (abs(lastStair.offset) - 1)
                self.eastMiddleY += lastStairWidth

            yOffset = 0
            if portGeom.wireDirection == Direction.WEST:
                self.reserveStairSpaceBottom = True
                yOffset = portGeom.groupWires * abs(portGeom.offset) - 1

            stairWiresName = f"({portGeom.sourceName} ⟶ {portGeom.destName})"
            stairWires = StairWires(stairWiresName)
            stairWires.generateGeometry(
                self.smGeometry.westPortsRightX + self.smGeometry.relX + padding,
                self.eastMiddleY + yOffset,
                portGeom.offset,
                portGeom.wireDirection,
                portGeom.groupWires,
                self.width,
                self.height,
            )
            self.stairWiresList.append(stairWires)
            self.wireConstraints.addConstraintsOf(stairWires)

            if portGeom.wireDirection == Direction.EAST:
                stairReservedWidth = portGeom.groupWires * (abs(portGeom.offset) - 1)
                self.eastMiddleY += stairReservedWidth

        wireName = f"{portGeom.sourceName} ⟶ {portGeom.destName}"
        wireGeom = WireGeometry(wireName)
        start = Location(
            self.smGeometry.relX + portGeom.relX, self.smGeometry.relY + portGeom.relY
        )
        middle = Location(self.smGeometry.relX + portGeom.relX, self.eastMiddleY)
        end = Location(self.width, self.eastMiddleY)
        wireGeom.addPathLoc(start)
        wireGeom.addPathLoc(middle)
        wireGeom.addPathLoc(end)
        self.wireGeomList.append(wireGeom)
        self.wireConstraints.eastPositions.append(self.eastMiddleY)
        self.eastMiddleY += 1

    def indirectWestSideWire(self, portGeom: PortGeometry) -> None:
        """Generate indirect wires on the west side without creating stair-like wires.

        Creates L-shaped wire routing for westward connections. Unlike east side
        wires, this method only generates the connection wires and reserves space
        for stair wires created by the east side method.

        Parameters
        ----------
        portGeom : PortGeometry
            The port geometry defining the wire characteristics
        """
        generateEastWestStairWire = (
            self.border != Border.EASTWEST and self.border != Border.CORNER
        )

        # with a new group of ports, there will be the
        # need for space for the generated stair-like wire
        if generateEastWestStairWire and self.currPortGroupId != portGeom.groupId:
            self.currPortGroupId = portGeom.groupId

            self.westMiddleY += self.queuedAdjustmentBottom
            stairReservedHeight = portGeom.groupWires * (abs(portGeom.offset) - 1)

            # depending on the direction, do the adjustment
            # now, or queue it - taking the different "bending"
            # of the stair-like wire into account.
            if portGeom.wireDirection == Direction.EAST:
                self.queuedAdjustmentBottom = stairReservedHeight

            if portGeom.wireDirection == Direction.WEST:
                self.westMiddleY += stairReservedHeight
                self.queuedAdjustmentBottom = 0

        wireName = f"{portGeom.sourceName} ⟶ {portGeom.destName}"
        wireGeom = WireGeometry(wireName)
        start = Location(0, self.westMiddleY)
        middle = Location(self.smGeometry.relX + portGeom.relX, self.westMiddleY)
        end = Location(
            self.smGeometry.relX + portGeom.relX, self.smGeometry.relY + portGeom.relY
        )
        wireGeom.addPathLoc(start)
        wireGeom.addPathLoc(middle)
        wireGeom.addPathLoc(end)
        self.wireGeomList.append(wireGeom)
        self.wireConstraints.westPositions.append(self.westMiddleY)
        self.westMiddleY += 1

    def totalWireLines(self) -> int:
        """Return the total amount of lines (segments) of wires of the tiles routing."""
        totalWireLines = 0

        for wireGeom in self.wireGeomList:
            lines = len(wireGeom.path) - 1
            totalWireLines += lines

        for stairWires in self.stairWiresList:
            for wireGeom in stairWires.wireGeoms:
                lines = len(wireGeom.path) - 1
                totalWireLines += lines

        return totalWireLines

    def saveToCSV(self, writer: csvWriter) -> None:
        """Save tile geometry data to CSV format.

        Writes the tile geometry information including dimensions and all
        geometric components (switch matrix, BELs, wires, stair wires) to
        a CSV file using the provided writer.

        Parameters
        ----------
        writer : csvWriter
            The CSV writer object to use for output
        """
        writer.writerows(
            [
                ["TILE"],
                ["Name"] + [self.name],
                ["Width"] + [str(self.width)],
                ["Height"] + [str(self.height)],
                [],
            ]
        )
        self.smGeometry.saveToCSV(writer)

        for belGeometry in self.belGeomList:
            belGeometry.saveToCSV(writer)

        for wireGeometry in self.wireGeomList:
            wireGeometry.saveToCSV(writer)

        for stairWires in self.stairWiresList:
            stairWires.saveToCSV(writer)

    def __repr__(self) -> str:
        """Return string representation of the tile geometry.

        Returns
        -------
        str
            String containing the width and height of the tile
        """
        return f"{self.width, self.height}"

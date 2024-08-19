from csv import writer as csvWriter
from loguru import logger
from typing import List

from FABulous.fabric_definition.Tile import Tile
from FABulous.fabric_definition.define import Direction, Side
from FABulous.geometry_generator.bel_geometry import BelGeometry
from FABulous.geometry_generator.geometry_obj import Border, Location
from FABulous.geometry_generator.port_geometry import PortGeometry
from FABulous.geometry_generator.sm_geometry import SmGeometry
from FABulous.geometry_generator.wire_geometry import StairWires, WireGeometry


class TileGeometry:
    """A data structure representing the geometry of a tile.

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
    smGeometry : SmGeometry
        Geometry of the tiles switch matrix
    belGeomList : List[BelGeometry]
        List of the geometries of the tiles bels
    wireGeomList : List[WireGeometry]
        List of the geometries of the tiles wires
    stairWiresList : List[StairWires]
        List of the stair-like wires of the tile
    """

    name: str
    width: int
    height: int
    border: Border
    smGeometry: SmGeometry
    belGeomList: List[BelGeometry]
    wireGeomList: List[WireGeometry]
    stairWiresList: List[StairWires]

    def __init__(self):
        self.name = None
        self.width = 0
        self.height = 0
        self.border = Border.NONE
        self.smGeometry = SmGeometry()
        self.belGeomList = []
        self.wireGeomList = []
        self.stairWiresList = []

    def generateGeometry(self, tile: Tile, padding: int) -> None:
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

        self.width = maxWidthInColumn
        self.height = maxHeightInRow
        self.smGeometry.width = maxSmWidthInColumn  # TODO: needed?
        self.smGeometry.relX = maxSmRelXInColumn

        # TODO:
        # dim.smWidth = dim.smWidth*2 if dim.smWidth*2 < maxSmWidths[j] else dim.smWidth

    def adjustSmPos(self, lowestSmYInRow: int, padding: int) -> None:
        """
        ajusts the position of the switch matrix, using
        the lowest Y coordinate of any switch matrix in
        the same row for reference. After this step is
        completed for all switch matrices, their southern
        edge will be on the same Y coordinate, allowing
        for easier inter-tile routing.

        """
        currentSmY = self.smGeometry.relY + self.smGeometry.height
        additionalOffset = lowestSmYInRow - currentSmY
        self.smGeometry.relY += additionalOffset

        self.setBelPositions(padding)

        # Bel positions are set by now, so the bel ports
        # of the switch matrix can be generated now.
        self.smGeometry.generateBelPorts(self.belGeomList)

    def setBelPositions(self, padding: int) -> None:
        """
        The position of the switch matrix is final when
        this is called, thus bel positions can be set.

        """
        belPadding = padding // 2
        belX = self.smGeometry.relX + self.smGeometry.width + padding
        belY = self.smGeometry.relY + belPadding
        for belGeom in self.belGeomList:
            belGeom.adjustPos(belX, belY)
            belY += belGeom.height
            belY += belPadding

    def generateWires(self, padding: int) -> None:
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
        """
        Generates the wires between the switch matrix
        and its bels.

        """
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

    northMiddleX = None
    southMiddleX = None
    eastMiddleY = None
    westMiddleY = None

    def generateDirectWires(self, padding: int) -> None:
        """
        Generates wires to neigbouring tiles, which are
        straightforward to generate.

        """
        self.northMiddleX = self.smGeometry.relX - padding
        self.southMiddleX = self.smGeometry.relX - padding
        self.eastMiddleY = self.smGeometry.relY + self.smGeometry.height + padding
        self.westMiddleY = self.smGeometry.relY + self.smGeometry.height + padding

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
                self.westMiddleY += 1

            else:
                logger.critical("Port with offset 1 and no tile side!")
                raise Exception

            self.wireGeomList.append(wireGeom)

    currPortGroupId = 0
    reserveStairSpaceLeft = False
    reserveStairSpaceBottom = False
    queuedAdjustmentLeft = 0
    queuedAdjustmentBottom = 0

    def generateIndirectWires(self, padding: int):
        """
        Generates wires to non-neighbouring tiles.
        These are not straightforward to generate,
        as they require a staircase-like shape.

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
                logger.critical("Port with abs(offset) > 1 and no tile side!")
                raise Exception

    def indirectNorthSideWire(self, portGeom: PortGeometry, padding: int) -> None:
        """
        generates indirect wires on the north side of the tile,
        along with the stair-like wires needed.

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
        self.northMiddleX -= 1

    def indirectSouthSideWire(self, portGeom: PortGeometry) -> None:
        """
        In contrast to indirectNorthSideWire(), this method
        generates only indirect wires on the south side of
        the tile, but no stair-like wires.

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
        self.southMiddleX -= 1

    def indirectEastSideWire(self, portGeom: PortGeometry, padding: int) -> None:
        """
        generates indirect wires on the east side of the tile,
        along with the stair-like wires needed.

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
        self.eastMiddleY += 1

    def indirectWestSideWire(self, portGeom: PortGeometry) -> None:
        """
        In contrast to indirectEastSideWire(), this method
        generates only indirect wires on the south side of
        the tile, but no stair-like wires.

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
        self.westMiddleY += 1

    def saveToCSV(self, writer: csvWriter) -> None:
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
        return f"{self.width, self.height}"

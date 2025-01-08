import pathlib
from loguru import logger
from csv import writer as csvWriter
from typing import List

from FABulous.fabric_definition.define import IO, Direction, Side
from FABulous.fabric_definition.Port import Port
from FABulous.fabric_definition.Tile import Tile
from FABulous.geometry_generator.bel_geometry import BelGeometry
from FABulous.geometry_generator.geometry_obj import Border
from FABulous.geometry_generator.port_geometry import PortGeometry, PortType


class SmGeometry:
    """A data structure representing the geometry of a Switch Matrix.

    Attributes
    ----------
    name : str
        Name of the switch matrix
    src : str
        File path of the switch matrix HDL source file
    csv : str
        File path of the switch matrix CSV file
    width : int
        Width of the switch matrix
    height : int
        Height of the switch matrix
    relX : int
        X coordinate of the switch matrix, relative within the tile
    relY : int
        Y coordinate of the switch matrix, relative within the tile
    northPorts : List[Port]
        List of the ports of the switch matrix in north direction
    southPorts : List[Port]
        List of the ports of the switch matrix in south direction
    eastPorts : List[Port]
        List of the ports of the switch matrix in east direction
    westPorts : List[Port]
        List of the ports of the switch matrix in west direction
    jumpPorts : List[Port]
        List of the jump ports of the switch matrix
    portGeoms : List[PortGeometry]
        List of geometries of the ports of the switch matrix
    northWiresReservedWidth : int
        Reserved width for wires going north
    southWiresReservedWidth : int
        Reserved width for wires going south
    eastWiresReservedHeight : int
        Reserved height for wires going east
    westWiresReservedHeight : int
        Reserved height for wires going west
    southPortsTopY : int
        Top most y coord of any south port, reference for stair-wires
    westPortsRightX : int
        Right most x coord of any west port, reference for stair-wires
    """

    name: str
    src: pathlib.Path
    csv: pathlib.Path
    width: int
    height: int
    relX: int
    relY: int
    northPorts: List[Port]
    southPorts: List[Port]
    eastPorts: List[Port]
    westPorts: List[Port]
    jumpPorts: List[Port]
    portGeoms: List[PortGeometry]
    northWiresReservedWidth: int
    southWiresReservedWidth: int
    eastWiresReservedHeight: int
    westWiresReservedHeight: int
    southPortsTopY: int
    westPortsRightX: int

    def __init__(self):
        self.name = None
        self.src = None
        self.csv = None
        self.width = 0
        self.height = 0
        self.relX = 0
        self.relY = 0
        self.northPorts = []
        self.southPorts = []
        self.eastPorts = []
        self.westPorts = []
        self.jumpPorts = []
        self.portGeoms = []
        self.northWiresReservedWidth = 0
        self.southWiresReservedWidth = 0
        self.eastWiresReservedHeight = 0
        self.westWiresReservedHeight = 0
        self.southPortsTopY = 0
        self.westPortsRightX = 0

    def preprocessPorts(self, tileBorder: Border) -> None:
        """
        Ensures that ports are ordered correctly,
        merges connected jump ports and augments
        ports for term tiles.

        """
        # This step augments ports in border tiles.
        # This is needed, as these are not contained
        # in the (north...west)SidePorts in FABulous.
        # TODO: check if numbering is generated correctly
        #  for augmented ports
        if tileBorder == Border.NORTHSOUTH or tileBorder == Border.CORNER:
            augmentedSouthPorts = []
            for southPort in self.southPorts:
                if abs(southPort.yOffset) > 1:
                    augmentedPort = Port(
                        southPort.wireDirection,
                        southPort.sourceName,
                        0,
                        1,
                        southPort.destinationName,
                        southPort.wireCount * abs(southPort.yOffset),
                        southPort.name,
                        southPort.inOut,
                        southPort.sideOfTile,
                    )
                    augmentedSouthPorts.append(augmentedPort)
                else:
                    augmentedSouthPorts.append(southPort)
            self.southPorts = augmentedSouthPorts

            augmentedNorthPorts = []
            for northPort in self.northPorts:
                if abs(northPort.yOffset) > 1:
                    augmentedPort = Port(
                        northPort.wireDirection,
                        northPort.sourceName,
                        0,
                        1,
                        northPort.destinationName,
                        northPort.wireCount * abs(northPort.yOffset),
                        northPort.name,
                        northPort.inOut,
                        northPort.sideOfTile,
                    )
                    augmentedNorthPorts.append(augmentedPort)
                else:
                    augmentedNorthPorts.append(northPort)
            self.northPorts = augmentedNorthPorts

        if tileBorder == Border.EASTWEST or tileBorder == Border.CORNER:
            augmentedEastPorts = []
            for eastPort in self.eastPorts:
                if abs(eastPort.xOffset) > 1:
                    augmentedPort = Port(
                        eastPort.wireDirection,
                        eastPort.sourceName,
                        1,
                        0,
                        eastPort.destinationName,
                        eastPort.wireCount * abs(eastPort.xOffset),
                        eastPort.name,
                        eastPort.inOut,
                        eastPort.sideOfTile,
                    )
                    augmentedEastPorts.append(augmentedPort)
                else:
                    augmentedEastPorts.append(eastPort)
            self.eastPorts = augmentedEastPorts

            augmentedWestPorts = []
            for westPort in self.westPorts:
                if abs(westPort.xOffset) > 1:
                    augmentedPort = Port(
                        westPort.wireDirection,
                        westPort.sourceName,
                        1,
                        0,
                        westPort.destinationName,
                        westPort.wireCount * abs(westPort.xOffset),
                        westPort.name,
                        westPort.inOut,
                        westPort.sideOfTile,
                    )
                    augmentedWestPorts.append(augmentedPort)
                else:
                    augmentedWestPorts.append(westPort)
            self.westPorts = augmentedWestPorts

        # This step ensures correct ordering, this is important
        # for the wire generation step.
        self.northPorts = sorted(self.northPorts, key=lambda port: abs(port.yOffset))
        self.southPorts = sorted(self.southPorts, key=lambda port: abs(port.yOffset))
        self.eastPorts = sorted(self.eastPorts, key=lambda port: abs(port.xOffset))
        self.westPorts = sorted(self.westPorts, key=lambda port: abs(port.xOffset))

        # This step merges connected jump ports into
        # a single port.
        mergedJumpPorts = []
        portNameMap = {}
        for jumpPort in self.jumpPorts:
            portNameMap[jumpPort.name] = jumpPort

        while len(portNameMap) != 0:
            firstPortName = next(iter(portNameMap))
            firstPort = portNameMap[firstPortName]

            if firstPortName != firstPort.sourceName:
                partnerName = firstPort.sourceName
            else:
                partnerName = firstPort.destinationName

            if partnerName in portNameMap:
                mergedPort = Port(
                    Direction.JUMP,
                    firstPort.sourceName,
                    0,
                    0,
                    firstPort.destinationName,
                    firstPort.wireCount,
                    firstPortName,
                    IO.INOUT,
                    firstPort.sideOfTile,
                )
                mergedJumpPorts.append(mergedPort)
                del portNameMap[firstPortName]
                del portNameMap[partnerName]
            else:
                logger.info(f"No partner found for {firstPortName}")
                logger.info(f"Partner would have been {partnerName}")
                logger.info(f"Adding jump port {firstPortName} without partner")

                mergedJumpPorts.append(firstPort)
                del portNameMap[firstPortName]

        self.jumpPorts = mergedJumpPorts

    def generateGeometry(
        self, tile: Tile, tileBorder: Border, belGeoms: List[BelGeometry], padding: int
    ) -> None:
        self.name = f"{tile.name}_switch_matrix"
        self.src = tile.tileDir.parent.joinpath(f"{self.name}.v")
        self.csv = tile.tileDir.parent.joinpath(f"{self.name}.csv")

        self.jumpPorts = [
            port for port in tile.portsInfo if port.wireDirection == Direction.JUMP
        ]
        self.northPorts = tile.getNorthSidePorts()
        self.southPorts = tile.getSouthSidePorts()
        self.eastPorts = tile.getEastSidePorts()
        self.westPorts = tile.getWestSidePorts()
        self.preprocessPorts(tileBorder)

        # Counting the total number of wires for each direction
        northWires = sum([port.wireCount for port in self.northPorts])
        southWires = sum([port.wireCount for port in self.southPorts])
        eastWires = sum([port.wireCount for port in self.eastPorts])
        westWires = sum([port.wireCount for port in self.westPorts])
        jumpWires = sum([port.wireCount for port in self.jumpPorts])

        self.northWiresReservedWidth = sum(
            [abs(port.yOffset) * port.wireCount for port in self.northPorts]
        )
        self.southWiresReservedWidth = sum(
            [abs(port.yOffset) * port.wireCount for port in self.southPorts]
        )
        self.eastWiresReservedHeight = sum(
            [abs(port.xOffset) * port.wireCount for port in self.eastPorts]
        )
        self.westWiresReservedHeight = sum(
            [abs(port.xOffset) * port.wireCount for port in self.westPorts]
        )

        self.relX = (
            max(self.northWiresReservedWidth, self.southWiresReservedWidth)
            + 2 * padding
        )
        self.relY = padding

        # These gaps are for the stair-like wires,
        # hence they're not needed for border tiles,
        # where no stair-like wires are generated.
        if tileBorder == Border.NORTHSOUTH or tileBorder == Border.CORNER:
            portsGapWest = 0
        else:
            portsGapWest = sum(
                [
                    port.wireCount
                    for port in (self.northPorts + self.southPorts)
                    if abs(port.yOffset) > 1
                ]
            )
            portsGapWest += padding

        if tileBorder == Border.EASTWEST or tileBorder == Border.CORNER:
            portsGapSouth = 0
        else:
            portsGapSouth = sum(
                [
                    port.wireCount
                    for port in (self.eastPorts + self.westPorts)
                    if abs(port.xOffset) > 1
                ]
            )
            portsGapSouth += padding

        belsHeightTotal = sum([belGeom.height for belGeom in belGeoms])
        belPadding = padding // 2
        belsPaddingTotal = (len(belGeoms) + 1) * belPadding
        belsReservedSpace = belsHeightTotal + belsPaddingTotal

        self.width = max(eastWires + westWires + portsGapSouth, jumpWires) + 2 * padding
        self.height = max(
            southWires + northWires + portsGapWest + 2 * padding, belsReservedSpace
        )
        self.generatePortsGeometry(padding)

        self.southPortsTopY = min(
            [geom.relY for geom in self.portGeoms if geom.sideOfTile == Side.SOUTH]
            + [self.height]
        )
        self.westPortsRightX = max(
            [geom.relX for geom in self.portGeoms if geom.sideOfTile == Side.WEST] + [0]
        )

    def generatePortsGeometry(self, padding: int) -> None:
        jumpPortX = padding
        jumpPortY = 0
        for port in self.jumpPorts:
            for i in range(port.wireCount):
                portGeom = PortGeometry()
                portGeom.generateGeometry(
                    f"{port.name}{i}",
                    f"{port.sourceName}{i}",
                    f"{port.destinationName}{i}",
                    PortType.JUMP,
                    port.inOut,
                    jumpPortX,
                    jumpPortY,
                )
                self.portGeoms.append(portGeom)
                jumpPortX += 1

        northPortX = 0
        northPortY = padding
        for port in self.northPorts:
            for i in range(port.wireCount):
                portGeom = PortGeometry()
                portGeom.generateGeometry(
                    f"{port.name}{i}",
                    f"{port.sourceName}{i}",
                    f"{port.destinationName}{i}",
                    PortType.SWITCH_MATRIX,
                    port.inOut,
                    northPortX,
                    northPortY,
                )
                portGeom.sideOfTile = port.sideOfTile
                portGeom.offset = port.yOffset
                portGeom.wireDirection = port.wireDirection
                portGeom.groupId = PortGeometry.nextId
                portGeom.groupWires = port.wireCount

                self.portGeoms.append(portGeom)
                northPortY += 1
            PortGeometry.nextId += 1

        southPortX = 0
        southPortY = self.height - padding
        for port in self.southPorts:
            for i in range(port.wireCount):
                portGeom = PortGeometry()
                portGeom.generateGeometry(
                    f"{port.name}{i}",
                    f"{port.sourceName}{i}",
                    f"{port.destinationName}{i}",
                    PortType.SWITCH_MATRIX,
                    port.inOut,
                    southPortX,
                    southPortY,
                )
                portGeom.sideOfTile = port.sideOfTile
                portGeom.offset = port.yOffset
                portGeom.wireDirection = port.wireDirection
                portGeom.groupId = PortGeometry.nextId
                portGeom.groupWires = port.wireCount

                self.portGeoms.append(portGeom)
                southPortY -= 1
            PortGeometry.nextId += 1

        eastPortX = self.width - padding
        eastPortY = self.height
        for port in self.eastPorts:
            for i in range(port.wireCount):
                portGeom = PortGeometry()
                portGeom.generateGeometry(
                    f"{port.name}{i}",
                    f"{port.sourceName}{i}",
                    f"{port.destinationName}{i}",
                    PortType.SWITCH_MATRIX,
                    port.inOut,
                    eastPortX,
                    eastPortY,
                )
                portGeom.sideOfTile = port.sideOfTile
                portGeom.offset = port.xOffset
                portGeom.wireDirection = port.wireDirection
                portGeom.groupId = PortGeometry.nextId
                portGeom.groupWires = port.wireCount

                self.portGeoms.append(portGeom)
                eastPortX -= 1
            PortGeometry.nextId += 1

        westPortX = padding
        westPortY = self.height
        for port in self.westPorts:
            for i in range(port.wireCount):
                portGeom = PortGeometry()
                portGeom.generateGeometry(
                    f"{port.name}{i}",
                    f"{port.sourceName}{i}",
                    f"{port.destinationName}{i}",
                    PortType.SWITCH_MATRIX,
                    port.inOut,
                    westPortX,
                    westPortY,
                )
                portGeom.sideOfTile = port.sideOfTile
                portGeom.offset = port.xOffset
                portGeom.wireDirection = port.wireDirection
                portGeom.groupId = PortGeometry.nextId
                portGeom.groupWires = port.wireCount

                self.portGeoms.append(portGeom)
                westPortX += 1
            PortGeometry.nextId += 1

    def generateBelPorts(self, belGeomList: List[BelGeometry]) -> None:
        for belGeom in belGeomList:
            for belPortGeom in belGeom.internalPortGeoms:
                portX = self.width
                portY = belGeom.relY - self.relY + belPortGeom.relY

                portGeom = PortGeometry()
                portGeom.generateGeometry(
                    belPortGeom.name,
                    belPortGeom.sourceName,
                    belPortGeom.destName,
                    PortType.SWITCH_MATRIX,
                    belPortGeom.ioDirection,
                    portX,
                    portY,
                )
                self.portGeoms.append(portGeom)

    def saveToCSV(self, writer: csvWriter) -> None:
        writer.writerows(
            [
                ["SWITCH_MATRIX"],
                ["Name"] + [self.name],
                ["Src"] + [self.src],
                ["Csv"] + [self.csv],
                ["RelX"] + [str(self.relX)],
                ["RelY"] + [str(self.relY)],
                ["Width"] + [str(self.width)],
                ["Height"] + [str(self.height)],
                [],
            ]
        )

        for portGeom in self.portGeoms:
            portGeom.saveToCSV(writer)

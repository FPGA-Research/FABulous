"""Switch matrix geometry definitions."""

from pathlib import Path

from loguru import logger

from FABulous.fabric_definition.define import IO, Direction, Side
from FABulous.fabric_definition.Port import Port
from FABulous.fabric_definition.Tile import Tile
from FABulous.geometry_generator.bel_geometry import BelGeometry
from FABulous.geometry_generator.geometry_obj import Border
from FABulous.geometry_generator.port_geometry import PortGeometry, PortType


class SmGeometry:
    """A data structure representing the geometry of a Switch Matrix.

    Sets all attributes to default values: None for names and paths,
    zero for dimensions and coordinates, and empty lists for ports
    and port geometries.

    Attributes
    ----------
    name : str
        Name of the switch matrix
    src : Path
        File path of the switch matrix HDL source file
    csv : Path
        File path of the switch matrix CSV file
    width : int
        Width of the switch matrix
    height : int
        Height of the switch matrix
    relX : int
        X coordinate of the switch matrix, relative within the tile
    relY : int
        Y coordinate of the switch matrix, relative within the tile
    northPorts : list[Port]
        List of the ports of the switch matrix in north direction
    southPorts : list[Port]
        List of the ports of the switch matrix in south direction
    eastPorts : list[Port]
        List of the ports of the switch matrix in east direction
    westPorts : list[Port]
        List of the ports of the switch matrix in west direction
    jumpPorts : list[Port]
        List of the jump ports of the switch matrix
    portGeoms : list[PortGeometry]
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
    src: Path
    csv: Path
    width: int
    height: int
    relX: int
    relY: int
    northPorts: list[Port]
    southPorts: list[Port]
    eastPorts: list[Port]
    westPorts: list[Port]
    jumpPorts: list[Port]
    portGeoms: list[PortGeometry]
    northWiresReservedWidth: int
    southWiresReservedWidth: int
    eastWiresReservedHeight: int
    westWiresReservedHeight: int
    southPortsTopY: int
    westPortsRightX: int

    def __init__(self) -> None:
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
        """Order the ports for downstream drawing.

        Ensure that ports are ordered correctly, merge connected jump ports and augment
        ports for term tiles.
        This step augments ports in border tiles.
        This is needed, as these are not contained in the (north...west)SidePorts
        in FABulous.
        """
        # This step ensures correct ordering, this is important
        # for the wire generation step.
        self.northPorts = sorted(self.northPorts, key=lambda port: abs(port.yOffset))
        self.southPorts = sorted(self.southPorts, key=lambda port: abs(port.yOffset))
        self.eastPorts = sorted(self.eastPorts, key=lambda port: abs(port.xOffset))
        self.westPorts = sorted(self.westPorts, key=lambda port: abs(port.xOffset))

        # This step augments ports in border tiles.
        # This is needed, as these are not contained
        # in the (north...west)SidePorts in FABulous.
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
        self, tile: Tile, tileBorder: Border, belGeoms: list[BelGeometry], padding: int
    ) -> None:
        """Generate the geometry for a switch matrix.

        Creates the geometric representation of a switch matrix including its
        dimensions, port arrangements, and spatial relationships. Calculates
        the required space for routing wires and positions the switch matrix
        within the tile.
        the required space for routing wires and positions for the switch matrix

        Parameters
        ----------
        tile : Tile
            The tile object containing the switch matrix definition
        tileBorder : Border
            The border type of the tile within the fabric
        belGeoms : list[BelGeometry]
            List of BEL geometries within the same tile
        padding : int
            The padding space to add around the switch matrix
        """
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
        """Generate the geometry for all ports of the switch matrix.

        Creates `PortGeometry` objects for all jump, north, south, east, and west
        ports of the switch matrix. Positions each port according to its type
        and assigns appropriate coordinates and grouping information.

        Parameters
        ----------
        padding : int
            The padding space to add around ports
        """
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

    def generateBelPorts(self, belGeomList: list[BelGeometry]) -> None:
        """Generate port geometries for BEL connections to the switch matrix.

        Creates `PortGeometry` objects for connecting BEL internal ports to the
        switch matrix. These ports facilitate routing between BELs and the
        switch matrix interconnect network.

        Parameters
        ----------
        belGeomList : list[BelGeometry]
            List of BEL geometries to connect to the switch matrix
        """
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

    def saveToCSV(self, writer: object) -> None:
        """Save switch matrix geometry data to CSV format.

        Writes the switch matrix geometry information including name, source
        and CSV file paths, position, dimensions, and all port geometries
        to a CSV file using the provided writer.

        Parameters
        ----------
        writer : object
            The CSV `writer` object to use for output
        """
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

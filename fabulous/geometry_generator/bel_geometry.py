"""Class for generating and managing the geometry of BELs."""

from pathlib import Path
from typing import TYPE_CHECKING

from fabulous.fabric_definition.bel import Bel
from fabulous.fabric_definition.define import IO
from fabulous.geometry_generator.port_geometry import PortGeometry, PortType

if TYPE_CHECKING:
    from _csv import Writer


class BelGeometry:
    """A data structure representing the geometry of a bel.

    Dimensions, coordinates and port lists start empty; `generateGeometry`
    fills in the name, source and layout.

    Attributes
    ----------
    name : str
        Name of the bel
    src : Path
        File path of the bel HDL source file
    width : int
        Width of the bel
    height : int
        Height of the bel
    relX : int
        X coordinate of the bel, relative within the tile
    relY : int
        Y coordinate of the bel, relative within the tile
    internalInputs : list[str]
        Internal input port names of the bel
    internalOutputs : list[str]
        Internal output port names of the bel
    externalInputs : list[str]
        External input port names of the bel
    externalOutputs : list[str]
        External output port names of the bel
    internalPortGeoms : list[PortGeometry]
        List of geometries of the internal ports of the bel
    externalPortGeoms : list[PortGeometry]
        List of geometries of the external ports of the bel
    """

    name: str
    src: Path
    width: int
    height: int
    relX: int
    relY: int
    internalInputs: list[str]
    internalOutputs: list[str]
    externalInputs: list[str]
    externalOutputs: list[str]
    internalPortGeoms: list[PortGeometry]
    externalPortGeoms: list[PortGeometry]

    def __init__(self) -> None:
        self.width = 0
        self.height = 0
        self.relX = 0
        self.relY = 0
        self.internalInputs = []
        self.internalOutputs = []
        self.externalInputs = []
        self.externalOutputs = []
        self.internalPortGeoms = []
        self.externalPortGeoms = []

    def generateGeometry(self, bel: Bel, padding: int) -> None:
        """Generate the geometry for a BEL (Basic Element).

        Creates the geometric representation of a BEL including its dimensions
        and port layout. The height is determined by the maximum number of
        ports on either side plus padding, while width is currently fixed.

        Parameters
        ----------
        bel : Bel
            The BEL object to generate the geometry for
        padding : int
            The padding space to add around the BEL
        """
        self.name = bel.name
        self.src = bel.src
        self.internalInputs = bel.inputs
        self.internalOutputs = bel.outputs
        self.externalInputs = bel.externalInput
        self.externalOutputs = bel.externalOutput

        internalPortsAmount = len(self.internalInputs) + len(self.internalOutputs)
        externalPortsAmount = len(self.externalInputs) + len(self.externalOutputs)
        maxAmountVerticalPorts = max(internalPortsAmount, externalPortsAmount)

        self.height = maxAmountVerticalPorts + padding
        self.width = 32  # TODO: Deduce width in a meaningful way?

        self.generatePortsGeometry(bel, padding)

    def generatePortsGeometry(self, bel: Bel, padding: int) -> None:
        """Generate the geometry for all ports of the BEL.

        Creates PortGeometry objects for all internal and external input/output
        ports of the BEL. Internal ports are positioned on the left side (X=0),
        while external ports are positioned on the right side (X=width).

        Parameters
        ----------
        bel : Bel
            The BEL object containing port information
        padding : int
            The padding space to add around ports
        """
        internalPortX = 0
        internalPortY = padding // 2
        for port in self.internalInputs:
            portName = port
            portGeom = PortGeometry(
                name=portName,
                source_name=portName,
                destName=portName,
                type=PortType.BEL,
                io_direction=IO.INPUT,
                relX=internalPortX,
                relY=internalPortY,
            )
            self.internalPortGeoms.append(portGeom)
            internalPortY += 1

        for port in self.internalOutputs:
            portName = port
            portGeom = PortGeometry(
                name=portName,
                source_name=portName,
                destName=portName,
                type=PortType.BEL,
                io_direction=IO.OUTPUT,
                relX=internalPortX,
                relY=internalPortY,
            )
            self.internalPortGeoms.append(portGeom)
            internalPortY += 1

        externalPortX = self.width
        externalPortY = padding // 2
        for port in self.externalInputs:
            portName = port.removeprefix(bel.prefix)
            portGeom = PortGeometry(
                name=portName,
                source_name=portName,
                destName=portName,
                type=PortType.BEL,
                io_direction=IO.INPUT,
                relX=externalPortX,
                relY=externalPortY,
            )
            self.externalPortGeoms.append(portGeom)
            externalPortY += 1

        for port in self.externalOutputs:
            portName = port.removeprefix(bel.prefix)
            portGeom = PortGeometry(
                name=portName,
                source_name=portName,
                destName=portName,
                type=PortType.BEL,
                io_direction=IO.OUTPUT,
                relX=externalPortX,
                relY=externalPortY,
            )
            self.externalPortGeoms.append(portGeom)
            externalPortY += 1

    def adjustPos(self, relX: int, relY: int) -> None:
        """Adjust the position of the BEL within its containing tile.

        Updates the relative X and Y coordinates of the BEL to position
        it correctly within the tile layout.

        Parameters
        ----------
        relX : int
            New relative X coordinate within the tile
        relY : int
            New relative Y coordinate within the tile
        """
        self.relX = relX
        self.relY = relY

    def saveToCSV(self, writer: "Writer") -> None:
        """Save BEL geometry data to CSV format.

        Writes the BEL geometry information including name, source file,
        position, dimensions, and all port geometries to a CSV file
        using the provided writer.

        Parameters
        ----------
        writer : Writer
            The CSV writer object to use for output
        """
        writer.writerows(
            [
                ["BEL"],
                ["Name"] + [self.name],
                ["Src"] + [self.src],
                ["RelX"] + [str(self.relX)],
                ["RelY"] + [str(self.relY)],
                ["Width"] + [str(self.width)],
                ["Height"] + [str(self.height)],
                [],
            ]
        )

        for portGeom in self.internalPortGeoms:
            portGeom.saveToCSV(writer)

        for portGeom in self.externalPortGeoms:
            portGeom.saveToCSV(writer)

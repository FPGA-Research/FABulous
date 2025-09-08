from csv import writer as csvWriter

from FABulous.fabric_definition.Bel import Bel
from FABulous.fabric_definition.define import IO
from FABulous.geometry_generator.port_geometry import PortGeometry, PortType


class BelGeometry:
    """A data structure representing the geometry of a bel.

    Attributes
    ----------
    name : str
        Name of the bel
    src : str
        File path of the bel HDL source file
    width : int
        Width of the bel
    height : int
        Height of the bel
    relX : int
        X coordinate of the bel, relative within the tile
    relY : int
        Y coordinate of the bel, relative within the tile
    internalInputs : List[str]
        Internal input port names of the bel
    internalOutputs : List[str]
        Internal output port names of the bel
    externalInputs : List[str]
        External input port names of the bel
    externalOutputs : List[str]
        External output port names of the bel
    internalPortGeoms : List[PortGeometry]
        List of geometries of the internal ports of the bel
    externalPortGeoms : List[PortGeometry]
        List of geometries of the external ports of the bel
    """

    name: str
    src: str
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
        """Initialize a BelGeometry instance.

        Sets all attributes to default values: None for names/sources,
        zero for dimensions and coordinates, and empty lists for
        port names and geometries.
        """
        self.name = None
        self.src = None
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
            The BEL object to generate geometry for
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
        ports of the BEL. Internal ports are positioned on the left side (x=0),
        while external ports are positioned on the right side (x=width).

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
            portGeom = PortGeometry()
            portGeom.generateGeometry(
                portName,
                portName,
                portName,
                PortType.BEL,
                IO.INPUT,
                internalPortX,
                internalPortY,
            )
            self.internalPortGeoms.append(portGeom)
            internalPortY += 1

        for port in self.internalOutputs:
            portName = port
            portGeom = PortGeometry()
            portGeom.generateGeometry(
                portName,
                portName,
                portName,
                PortType.BEL,
                IO.OUTPUT,
                internalPortX,
                internalPortY,
            )
            self.internalPortGeoms.append(portGeom)
            internalPortY += 1

        externalPortX = self.width
        externalPortY = padding // 2
        for port in self.externalInputs:
            portName = port.removeprefix(bel.prefix)
            portGeom = PortGeometry()
            portGeom.generateGeometry(
                portName,
                portName,
                portName,
                PortType.BEL,
                IO.INPUT,
                externalPortX,
                externalPortY,
            )
            self.externalPortGeoms.append(portGeom)
            externalPortY += 1

        for port in self.externalOutputs:
            portName = port.removeprefix(bel.prefix)
            portGeom = PortGeometry()
            portGeom.generateGeometry(
                portName,
                portName,
                portName,
                PortType.BEL,
                IO.OUTPUT,
                externalPortX,
                externalPortY,
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

    def saveToCSV(self, writer: csvWriter) -> None:
        """Save BEL geometry data to CSV format.

        Writes the BEL geometry information including name, source file,
        position, dimensions, and all port geometries to a CSV file
        using the provided writer.

        Parameters
        ----------
        writer : csvWriter
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

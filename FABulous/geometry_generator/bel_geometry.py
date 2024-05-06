from csv import writer as csvWriter
from typing import List

from FABulous.fabric_generator.fabric import IO, Bel
from FABulous.geometry_generator.port_geometry import PortGeometry, PortType


class BelGeometry:
    """
    A datastruct representing the geometry of a Bel.

    Attributes:
        name                (str)               :   Name of the bel
        src                 (str)               :   File path of the bel HDL source file
        width               (int)               :   Width of the bel
        height              (int)               :   Height of the bel
        relX                (int)               :   X coordinate of the bel, relative within the tile
        relY                (int)               :   Y coordinate of the bel, relative within the tile
        internalInputs      (List[str])         :   Internal input port names of the bel
        internalOutputs     (List[str])         :   Internal output port names of the bel
        externalInputs      (List[str])         :   External input port names of the bel
        externalOutputs     (List[str])         :   External output port names of the bel
        internalPortGeoms   (List[PortGeometry]):   List of geometries of the internal ports of the bel
        externalPortGeoms   (List[PortGeometry]):   List of geometries of the external ports of the bel

    """

    name: str
    src: str
    width: int
    height: int
    relX: int
    relY: int
    internalInputs: List[str]
    internalOutputs: List[str]
    externalInputs: List[str]
    externalOutputs: List[str]
    internalPortGeoms: List[PortGeometry]
    externalPortGeoms: List[PortGeometry]

    def __init__(self):
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
        self.relX = relX
        self.relY = relY

    def saveToCSV(self, writer: csvWriter) -> None:
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

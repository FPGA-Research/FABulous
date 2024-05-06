import fabric_generator.model_generation_vpr as model_gen_vpr
import fabric_generator.model_generation_npnr as model_gen_npnr
from fabric_generator.code_generation_VHDL import VHDLWriter
import fabric_generator.code_generator as codeGen
import fabric_generator.file_parser as fileParser
from fabric_generator.fabric import Fabric, Tile
from fabric_generator.fabric_gen import FabricGenerator
from geometry_generator.geometry_gen import GeometryGenerator

import logging

logger = logging.getLogger(__name__)
logging.basicConfig(
    format="[%(levelname)s]-%(asctime)s - %(message)s", level=logging.INFO
)


class FABulous:
    fabricGenerator: FabricGenerator
    geometryGenerator: GeometryGenerator
    fabric: Fabric
    fileExtension: str = ".v"

    def __init__(self, writer: codeGen.codeGenerator, fabricCSV: str = ""):
        self.writer = writer
        if fabricCSV != "":
            self.fabric = fileParser.parseFabricCSV(fabricCSV)
            self.fabricGenerator = FabricGenerator(self.fabric, self.writer)
            self.geometryGenerator = GeometryGenerator(self.fabric)

        if isinstance(self.writer, VHDLWriter):
            self.fileExtension = ".vhdl"
        # self.fabricGenerator = FabricGenerator(fabric, writer)

    def setWriterOutputFile(self, outputDir):
        logger.info(f"Output file: {outputDir}")
        self.writer.outFileName = outputDir

    def loadFabric(self, dir: str):
        if dir.endswith(".csv"):
            self.fabric = fileParser.parseFabricCSV(dir)
            self.fabricGenerator = FabricGenerator(self.fabric, self.writer)
            self.geometryGenerator = GeometryGenerator(self.fabric)
        else:
            logger.warning("Only .csv files are supported for fabric loading")

    def bootstrapSwitchMatrix(self, tileName: str, outputDir: str):
        tile = self.fabric.getTileByName(tileName)
        self.fabricGenerator.bootstrapSwitchMatrix(tile, outputDir)

    def addList2Matrix(self, list: str, matrix: str):
        self.fabricGenerator.list2CSV(list, matrix)

    def genConfigMem(self, tileName: str, configMem: str):
        tile = self.fabric.getTileByName(tileName)
        self.fabricGenerator.generateConfigMem(tile, configMem)

    def genSwitchMatrix(self, tileName: str):
        tile = self.fabric.getTileByName(tileName)
        self.fabricGenerator.genTileSwitchMatrix(tile)

    def genTile(self, tileName: str):
        tile = self.fabric.getTileByName(tileName)
        self.fabricGenerator.generateTile(tile)

    def genSuperTile(self, tileName: str):
        tile = self.fabric.getSuperTileByName(tileName)
        self.fabricGenerator.generateSuperTile(tile)

    def genFabric(self):
        self.fabricGenerator.generateFabric()

    def genGeometry(self, geomPadding: int = 8):
        self.geometryGenerator.generateGeometry(geomPadding)
        self.geometryGenerator.saveToCSV(self.writer.outFileName)

    def genTopWrapper(self):
        self.fabricGenerator.generateTopWrapper()

    def genBitStreamSpec(self):
        specObject = self.fabricGenerator.generateBitsStreamSpec()
        return specObject

    def genModelNpnr(self):
        return model_gen_npnr.genNextpnrModel(self.fabric)

    def genModelVPR(self, customXML: str = ""):
        return model_gen_vpr.genVPRModel(self.fabric, customXML)

    def genModelVPRRoutingResource(self):
        return model_gen_vpr.genVPRRoutingResourceGraph(self.fabric)

    def genModelVPRConstrains(self):
        return model_gen_vpr.genVPRConstrainsXML(self.fabric)

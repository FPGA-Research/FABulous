from loguru import logger


# Importing Modules from FABulous Framework.
import FABulous.fabric_generator.code_generator as codeGen
import FABulous.fabric_generator.file_parser as fileParser
import FABulous.fabric_cad.model_generation_npnr as model_gen_npnr
import FABulous.fabric_cad.model_generation_vpr as model_gen_vpr
from FABulous.fabric_generator.code_generation_VHDL import VHDLWriter
from FABulous.fabric_definition.Fabric import Fabric, Tile
from FABulous.fabric_generator.fabric_gen import FabricGenerator
from FABulous.geometry_generator.geometry_gen import GeometryGenerator


class FABulous:
    """Class for managing fabric and geometry generation.

    This class parses fabric data from 'fabric.csv', generates fabric layouts,
    geometries, models for both place and route tools (npnr/VPR), as well as
    other fabric-related functions.

    Attributes
    ----------
    fabricGenerator : FabricGenerator
        Object responsible for generating fabric-related outputs.
    geometryGenerator : GeometryGenerator
        Object responsible for generating geometry-related outputs.
    fabric : Fabric
        Represents the parsed fabric data.
    fileExtension : str
        Default file extension for generated output files ('.v' or '.vhdl').
    """

    fabricGenerator: FabricGenerator
    geometryGenerator: GeometryGenerator
    fabric: Fabric
    fileExtension: str = ".v"

    def __init__(self, writer: codeGen.codeGenerator, fabricCSV: str = ""):
        """Initialises FABulous object.

        If 'fabricCSV' is provided, parses fabric data and initialises
        'fabricGenerator' and 'geometryGenerator' with parsed data.

        If using VHDL, changes the extension from '.v' to'.vhdl'.

        Parameters
        ----------
        writer : codeGen.codeGenerator
            Object responsible for generating code from code_generator.py
        fabricCSV : str, optional
            Path to the CSV file containing fabric data, by default ""
        """
        self.writer = writer
        if fabricCSV != "":
            self.fabric = fileParser.parseFabricCSV(fabricCSV)
            self.fabricGenerator = FabricGenerator(self.fabric, self.writer)
            self.geometryGenerator = GeometryGenerator(self.fabric)

        if isinstance(self.writer, VHDLWriter):
            self.fileExtension = ".vhdl"
        # self.fabricGenerator = FabricGenerator(fabric, writer)

    def setWriterOutputFile(self, outputDir):
        """Sets the output file directory for the write object.

        Parameters
        ----------
        outputDir : str
            Directory path where output files will be saved.
        """
        logger.info(f"Output file: {outputDir}")
        self.writer.outFileName = outputDir

    def loadFabric(self, dir: str):
        """Loads fabric data from 'fabric.csv'.

        Parameters
        ----------
        dir : str
            Path to CSV file containing fabric data.

        Raises
        ----------
        ValueError
            If 'dir' does not end with '.csv'
        """
        if dir.endswith(".csv"):
            self.fabric = fileParser.parseFabricCSV(dir)
            self.fabricGenerator = FabricGenerator(self.fabric, self.writer)
            self.geometryGenerator = GeometryGenerator(self.fabric)
        else:
            logger.error("Only .csv files are supported for fabric loading")
            raise ValueError

    def bootstrapSwitchMatrix(self, tileName: str, outputDir: str):
        """Bootstraps the switch matrix for the specified tile via 'bootstrapSwitchMatrix'
        defined in 'fabric_gen.py'.

        Parameters
        ----------
        tileName : str
            Name of the tile for which the switch matrix will be bootstrapped.
        outputDir : str
            Directory path where the switch matrix will be generated.
        """
        tile = self.fabric.getTileByName(tileName)
        self.fabricGenerator.bootstrapSwitchMatrix(tile, outputDir)

    def addList2Matrix(self, list: str, matrix: str):
        """Converts list into CSV matrix via 'list2CSV' defined in
        'fabric_gen.py' and saves it.

        Parameters
        ----------
        list : str
            List data to be converted.
        matrix : str
            File path where the matrix data will be saved.
        """
        self.fabricGenerator.list2CSV(list, matrix)

    def genConfigMem(self, tileName: str, configMem: str):
        """Generate configuration memory for specified tile.

        Parameters
        ----------
        tileName : str
            Name of the tile for which configuration memory will be generated.
        configMem : str
            File path where the configuration memory will be saved.
        """
        tile = self.fabric.getTileByName(tileName)
        self.fabricGenerator.generateConfigMem(tile, configMem)

    def genSwitchMatrix(self, tileName: str):
        """Generates switch matrix for specified tile via 'genTileSwitchMatrix'
        defined in 'fabric_gen.py'.

        Parameters
        ----------
        tileName : str
            Name of the tile for which the switch matrix will be generated.
        """
        tile = self.fabric.getTileByName(tileName)
        self.fabricGenerator.genTileSwitchMatrix(tile)

    def genTile(self, tileName: str):
        """Generates a tile based on its name via 'generateTile'
        defined in 'fabric_gen.py'.

        Parameters
        ----------
        tileName : str
            Name of the tile generated.
        """
        tile = self.fabric.getTileByName(tileName)
        self.fabricGenerator.generateTile(tile)

    def genSuperTile(self, tileName: str):
        """Generates a super tile based on its name via 'generateSuperTile'
        defined in 'fabric_gen.py'.

        Parameters
        ----------
        tileName : str
            Name of the super tile generated.
        """
        tile = self.fabric.getSuperTileByName(tileName)
        self.fabricGenerator.generateSuperTile(tile)

    def genFabric(self):
        """Generates the entire fabric layout via 'generatreFabric' defined
        in 'fabric_gen.py'.
        """
        self.fabricGenerator.generateFabric()

    def genGeometry(self, geomPadding: int = 8):
        """Generates geometry based on the fabric data and saves it to CSV.

        Parameters
        ----------
        geomPadding : int, optional
            Padding value for geometry generation, by default 8.
        """
        self.geometryGenerator.generateGeometry(geomPadding)
        self.geometryGenerator.saveToCSV(self.writer.outFileName)

    def genTopWrapper(self):
        """Generates the top wrapper for the fabric via 'generateTopWrapper'
        defined in 'fabric_gen.py'.
        """
        self.fabricGenerator.generateTopWrapper()

    def genBitStreamSpec(self):
        """Generates the bitsream specification object.

        Returns
        -------
        Object
            Bitstream specification object generated by 'fabricGenerator'.
        """
        specObject = self.fabricGenerator.generateBitsStreamSpec()
        return specObject

    def genModelNpnr(self):
        """Generates model for Nextpnr based on fabric data.

        Returns
        -------
        Object
            Model generated by 'model_gen_npnr.genNextpnrModel'.
        """
        return model_gen_npnr.genNextpnrModel(self.fabric)

    def genModelVPR(self, customXML: str = ""):
        """Generates model for VPR based on fabric data.

        Parameters
        ----------
        customXML : str, optional
            Custom XML configuration for VPR model generation, by default ""

        Returns
        -------
        Object
            Model generated by 'model_gen_vpr.genVPRModel'.
        """
        return model_gen_vpr.genVPRModel(self.fabric, customXML)

    def genModelVPRRoutingResource(self):
        """Generates routing resource graph for VPR based on fabric data.

        Returns
        -------
        Object
            Routing resource graph generated by `model_gen_vpr.genVPRRoutingResourceGraph`.
        """
        return model_gen_vpr.genVPRRoutingResourceGraph(self.fabric)

    def genModelVPRConstrains(self):
        """Generates XML constraints for VPR based on fabric data.

        Returns
        -------
        Object
            XML Constraints generated by `model_gen_vpr.genVPRConstrainsXML`.
        """
        return model_gen_vpr.genVPRConstrainsXML(self.fabric)

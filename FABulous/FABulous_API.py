from pathlib import Path

from loguru import logger

import FABulous.fabric_cad.model_generation_npnr as model_gen_npnr
import FABulous.fabric_generator.code_generator as codeGen
import FABulous.fabric_generator.file_parser as fileParser

# Importing Modules from FABulous Framework.
from FABulous.fabric_definition.Bel import Bel
from FABulous.fabric_definition.Fabric import Fabric
from FABulous.fabric_definition.SuperTile import SuperTile
from FABulous.fabric_definition.Tile import Tile
from FABulous.fabric_generator.code_generation_VHDL import VHDLWriter
from FABulous.fabric_generator.fabric_automation import genIOBel
from FABulous.fabric_generator.fabric_gen import (
    FabricGenerator,
    generateUserDesignTopWrapper,
)
from FABulous.geometry_generator.geometry_gen import GeometryGenerator


class FABulous_API:
    """Class for managing fabric and geometry generation.

    This class parses fabric data from 'fabric.csv', generates fabric layouts,
    geometries, models for nextpnr, as well as
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

    def setWriterOutputFile(self, outputDir):
        """Sets the output file directory for the write object.

        Parameters
        ----------
        outputDir : str
            Directory path where output files will be saved.
        """
        logger.info(f"Output file: {outputDir}")
        self.writer.outFileName = outputDir

    def loadFabric(self, dir: Path):
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
        if dir.suffix == ".csv":
            self.fabric = fileParser.parseFabricCSV(dir)
            self.fabricGenerator = FabricGenerator(self.fabric, self.writer)
            self.geometryGenerator = GeometryGenerator(self.fabric)
        else:
            logger.error("Only .csv files are supported for fabric loading")
            raise ValueError

    def bootstrapSwitchMatrix(self, tileName: str, outputDir: str):
        """Bootstraps the switch matrix for the specified tile via
        'bootstrapSwitchMatrix' defined in 'fabric_gen.py'.

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
        """Converts list into CSV matrix via 'list2CSV' defined in 'fabric_gen.py' and
        saves it.

        Parameters
        ----------
        list : str
            List data to be converted.
        matrix : str
            File path where the matrix data will be saved.
        """
        self.fabricGenerator.list2CSV(list, matrix)

    def genConfigMem(self, tileName: str, configMem: Path):
        """Generate configuration memory for specified tile.

        Parameters
        ----------
        tileName : str
            Name of the tile for which configuration memory will be generated.
        configMem : str
            File path where the configuration memory will be saved.
        """
        if tile := self.fabric.getTileByName(tileName):
            self.fabricGenerator.generateConfigMem(tile, configMem)
        else:
            raise ValueError(f"Tile {tileName} not found")

    def genSwitchMatrix(self, tileName: str):
        """Generates switch matrix for specified tile via 'genTileSwitchMatrix' defined
        in 'fabric_gen.py'.

        Parameters
        ----------
        tileName : str
            Name of the tile for which the switch matrix will be generated.
        """
        tile = self.fabric.getTileByName(tileName)
        self.fabricGenerator.genTileSwitchMatrix(tile)

    def genTile(self, tileName: str):
        """Generates a tile based on its name via 'generateTile' defined in
        'fabric_gen.py'.

        Parameters
        ----------
        tileName : str
            Name of the tile generated.
        """
        if tile := self.fabric.getTileByName(tileName):
            self.fabricGenerator.generateTile(tile)
        else:
            raise ValueError(f"Tile {tileName} not found")

    def genSuperTile(self, tileName: str):
        """Generates a super tile based on its name via 'generateSuperTile' defined in
        'fabric_gen.py'.

        Parameters
        ----------
        tileName : str
            Name of the super tile generated.
        """
        tile = self.fabric.getSuperTileByName(tileName)
        self.fabricGenerator.generateSuperTile(tile)

    def genFabric(self):
        """Generates the entire fabric layout via 'generatreFabric' defined in
        'fabric_gen.py'."""
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
        """Generates the top wrapper for the fabric via 'generateTopWrapper' defined in
        'fabric_gen.py'."""
        self.fabricGenerator.generateTopWrapper()

    def genBitStreamSpec(self):
        """Generates the bitsream specification object.

        Returns
        -------
        Object
            Bitstream specification object generated by 'fabricGenerator'.
        """
        return self.fabricGenerator.generateBitsStreamSpec()

    def genRoutingModel(self):
        """Generates model for Nextpnr based on fabric data.

        Returns
        -------
        Object
            Model generated by 'model_gen_npnr.genNextpnrModel'.
        """
        return model_gen_npnr.genNextpnrModel(self.fabric)

    def getBels(self) -> list[Bel]:
        """Returns all unique Bels within a fabric.

        Returns
        -------
        Bel
            Bel object based on bel name.
        """
        return self.fabric.getAllUniqueBels()

    def getTile(self, tileName: str) -> Tile | None:
        """Returns Tile object based on tile name.

        Parameters
        ----------
            tileName : str
                Name of the Tile.

        Returns
        -------
        Tile
            Tile object based on tile name.
        """

        return self.fabric.getTileByName(tileName)

    def getTiles(self):
        """Returns all Tiles within a fabric.

        Returns
        -------
        Tile
            Tile object based on tile name.
        """
        return self.fabric.tileDic.values()

    def getSuperTile(self, tileName: str) -> SuperTile | None:
        """Returns SuperTile object based on tile name.

        Parameters
        ----------
            tileName : str
                Name of the SuperTile.

        Returns
        -------
        SuperTile
            SuperTile object based on tile name.
        """

        return self.fabric.getSuperTileByName(tileName)

    def getSuperTiles(self):
        """Returns all SuperTiles within a fabric.

        Returns
        -------
        SuperTile
            SuperTile object based on tile name.
        """
        return self.fabric.superTileDic.values()

    def generateUserDesignTopWrapper(self, userDesign: Path, topWrapper: Path):
        """Generates the top wrapper for the user design.

        Parameters
        ----------
        userDesign : Path
            Path to the user design file.
        topWrapper : Path
            Path to the output top wrapper file.
        """
        generateUserDesignTopWrapper(self.fabric, userDesign, topWrapper)

    def genIOBelForTile(self, tile_name: str) -> list[Bel]:
        """
        Generates the IO BELs for the generative IOs of a tile.
        Config Access Generative IOs will be a separate Bel.
        Updates the tileDic with the generated IO BELs.

        Parameters
        ----------
        tile_name : str
            Name of the tile to generate IO Bels.

        Returns
        -------
        bels : List[Bel]
            The bel object representing the generative IOs.

        Raises
        ------
        ValueError
            If tile not found in fabric.
            In case of an invalid IO type for generative IOs.
            If the number of config access ports does not match the number of config bits.
        """
        tile = self.fabric.getTileByName(tile_name)
        bels: list[Bel] = []
        if not tile:
            logger.error(f"Tile {tile_name} not found in fabric.")
            raise ValueError

        suffix = "vhdl" if isinstance(self.writer, VHDLWriter) else "v"

        gios = [gio for gio in tile.gen_ios if not gio.configAccess]
        gio_config_access = [gio for gio in tile.gen_ios if gio.configAccess]

        if gios:
            bel_path = tile.tileDir.parent / f"{tile.name}_GenIO.{suffix}"
            bel = genIOBel(gios, bel_path, True)
            if bel:
                bels.append(bel)
        if gio_config_access:
            bel_path = tile.tileDir.parent / f"{tile.name}_ConfigAccess_GenIO.{suffix}"
            bel = genIOBel(gio_config_access, bel_path, True)
            if bel:
                bels.append(bel)

        # update fabric tileDic with generated IO BELs
        if self.fabric.tileDic.get(tile_name):
            self.fabric.tileDic[tile_name].bels += bels
        elif not self.fabric.unusedTileDic[tile_name].bels:
            logger.warning(
                f"Tile {tile_name} is not used in fabric, but defined in fabric.csv."
            )
            self.fabric.unusedTileDic[tile_name].bels += bels
        else:
            logger.error(
                f"Tile {tile_name} is not defined in fabric, please add to fabric.csv."
            )
            raise ValueError

        # update bels on all tiles in fabric.tile
        for row in self.fabric.tile:
            for tile in row:
                if tile and tile.name == tile_name:
                    tile.bels += bels

        return bels

    def genFabricIOBels(self):
        """Generates the IO BELs for the generative IOs of the fabric."""

        for tile in self.fabric.tileDic.values():
            if tile.gen_ios:
                logger.info(f"Generating IO BELs for tile {tile.name}")
                self.genIOBelForTile(tile.name)

"""FABulous API module for fabric and geometry generation.

This module provides the main API class for managing FPGA fabric generation, including
parsing fabric definitions, generating HDL code, creating geometries, and handling
various fabric-related operations.
"""

from collections.abc import Iterable
from pathlib import Path

from loguru import logger

import FABulous.fabric_cad.gen_npnr_model as model_gen_npnr
import FABulous.fabric_generator.parser.parse_csv as fileParser
from FABulous.fabric_cad.gen_bitstream_spec import generateBitstreamSpec
from FABulous.fabric_cad.gen_design_top_wrapper import generateUserDesignTopWrapper

# Importing Modules from FABulous Framework.
from FABulous.fabric_definition.Bel import Bel
from FABulous.fabric_definition.Fabric import Fabric
from FABulous.fabric_definition.SuperTile import SuperTile
from FABulous.fabric_definition.Tile import Tile
from FABulous.fabric_generator.code_generator import CodeGenerator
from FABulous.fabric_generator.code_generator.code_generator_VHDL import (
    VHDLCodeGenerator,
)
from FABulous.fabric_generator.gen_fabric.fabric_automation import genIOBel
from FABulous.fabric_generator.gen_fabric.gen_configmem import generateConfigMem
from FABulous.fabric_generator.gen_fabric.gen_fabric import generateFabric
from FABulous.fabric_generator.gen_fabric.gen_helper import (
    bootstrapSwitchMatrix,
    list2CSV,
)
from FABulous.fabric_generator.gen_fabric.gen_switchmatrix import genTileSwitchMatrix
from FABulous.fabric_generator.gen_fabric.gen_tile import (
    generateSuperTile,
    generateTile,
)
from FABulous.fabric_generator.gen_fabric.gen_top_wrapper import generateTopWrapper
from FABulous.FABulous_settings import get_context
from FABulous.geometry_generator.geometry_gen import GeometryGenerator


class FABulous_API:
    """Class for managing fabric and geometry generation.

    This class parses fabric data from 'fabric.csv', generates fabric layouts,
    geometries, models for nextpnr, as well as
    other fabric-related functions.

    Attributes
    ----------
    geometryGenerator : GeometryGenerator
        Object responsible for generating geometry-related outputs.
    fabric : Fabric
        Represents the parsed fabric data.
    fileExtension : str
        Default file extension for generated output files ('.v' or '.vhdl').
    """

    geometryGenerator: GeometryGenerator
    fabric: Fabric
    fileExtension: str = ".v"

    def __init__(self, writer: CodeGenerator, fabricCSV: str = "") -> None:
        """Initialises FABulous object.

        If 'fabricCSV' is provided, parses fabric data and initialises
        'fabricGenerator' and 'geometryGenerator' with parsed data.

        If using VHDL, changes the extension from '.v' to'.vhdl'.

        Parameters
        ----------
        writer : CodeGenerator
            Object responsible for generating code from code_generator.py
        fabricCSV : str, optional
            Path to the CSV file containing fabric data, by default ""
        """
        self.writer = writer
        if fabricCSV != "":
            self.fabric = fileParser.parseFabricCSV(fabricCSV)
            self.geometryGenerator = GeometryGenerator(self.fabric)
        if isinstance(self.writer, VHDLCodeGenerator):
            self.fileExtension = ".vhdl"

    def setWriterOutputFile(self, outputDir: Path) -> None:
        """Sets the output file directory for the write object.

        Parameters
        ----------
        outputDir : Path
            Directory path where output files will be saved.
        """
        logger.info(f"Output file: {outputDir}")
        self.writer.outFileName = outputDir

    def loadFabric(self, fabric_dir: Path) -> None:
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
        if fabric_dir.suffix == ".csv":
            self.fabric = fileParser.parseFabricCSV(fabric_dir)
            self.geometryGenerator = GeometryGenerator(self.fabric)
        else:
            logger.error("Only .csv files are supported for fabric loading")
            raise ValueError

    def bootstrapSwitchMatrix(self, tileName: str, outputDir: Path) -> None:
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
        if not tile:
            raise ValueError(f"Tile {tileName} not found in fabric.")
        bootstrapSwitchMatrix(tile, outputDir)

    def addList2Matrix(self, listFile: Path, matrix: Path) -> None:
        """Converts list into CSV matrix via 'list2CSV' defined in 'fabric_gen.py' and
        saves it.

        Parameters
        ----------
        list : str
            List data to be converted.
        matrix : str
            File path where the matrix data will be saved.
        """
        list2CSV(listFile, matrix)

    def genConfigMem(self, tileName: str, configMem: Path) -> None:
        """Generate configuration memory for specified tile.

        Parameters
        ----------
        tileName : str
            Name of the tile for which configuration memory will be generated.
        configMem : str
            File path where the configuration memory will be saved.
        """
        if tile := self.fabric.getTileByName(tileName):
            generateConfigMem(self.writer, self.fabric, tile, configMem)
        else:
            raise ValueError(f"Tile {tileName} not found")

    def genSwitchMatrix(self, tileName: str) -> None:
        """Generates switch matrix for specified tile via 'genTileSwitchMatrix' defined
        in 'fabric_gen.py'.

        Parameters
        ----------
        tileName : str
            Name of the tile for which the switch matrix will be generated.
        """
        if tile := self.fabric.getTileByName(tileName):
            switch_matrix_debug_signal = get_context().switch_matrix_debug_signal
            logger.info(
                f"Generate switch matrix debug signals: {switch_matrix_debug_signal}"
            )
            genTileSwitchMatrix(
                self.writer, self.fabric, tile, switch_matrix_debug_signal
            )
        else:
            raise ValueError(f"Tile {tileName} not found")

    def genTile(self, tileName: str) -> None:
        """Generates a tile based on its name via 'generateTile' defined in
        'fabric_gen.py'.

        Parameters
        ----------
        tileName : str
            Name of the tile generated.
        """
        if tile := self.fabric.getTileByName(tileName):
            generateTile(self.writer, self.fabric, tile)
        else:
            raise ValueError(f"Tile {tileName} not found")

    def genSuperTile(self, tileName: str) -> None:
        """Generates a super tile based on its name via 'generateSuperTile' defined in
        'fabric_gen.py'.

        Parameters
        ----------
        tileName : str
            Name of the super tile generated.
        """
        if tile := self.fabric.getSuperTileByName(tileName):
            generateSuperTile(self.writer, self.fabric, tile)
        else:
            raise ValueError(f"SuperTile {tileName} not found")

    def genFabric(self) -> None:
        """Generates the entire fabric layout via 'generatreFabric' defined in
        'fabric_gen.py'."""
        generateFabric(self.writer, self.fabric)

    def genGeometry(self, geomPadding: int = 8) -> None:
        """Generates geometry based on the fabric data and saves it to CSV.

        Parameters
        ----------
        geomPadding : int, optional
            Padding value for geometry generation, by default 8.
        """
        self.geometryGenerator.generateGeometry(geomPadding)
        self.geometryGenerator.saveToCSV(self.writer.outFileName)

    def genTopWrapper(self) -> None:
        """Generates the top wrapper for the fabric via 'generateTopWrapper' defined in
        'fabric_gen.py'."""
        generateTopWrapper(self.writer, self.fabric)

    def genBitStreamSpec(self) -> dict:
        """Generates the bitsream specification object.

        Returns
        -------
        Object
            Bitstream specification object generated by 'fabricGenerator'.
        """
        return generateBitstreamSpec(self.fabric)

    def genRoutingModel(self) -> tuple[str, str, str, str]:
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

    def getTiles(self) -> Iterable[Tile]:
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

    def getSuperTiles(self) -> Iterable[SuperTile]:
        """Returns all SuperTiles within a fabric.

        Returns
        -------
        SuperTile
            SuperTile object based on tile name.
        """
        return self.fabric.superTileDic.values()

    def generateUserDesignTopWrapper(self, userDesign: Path, topWrapper: Path) -> None:
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
        """Generates the IO BELs for the generative IOs of a tile. Config Access
        Generative IOs will be a separate Bel. Updates the tileDic with the generated IO
        BELs.

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
            If the number of config access ports does not match the number of
            config bits.
        """
        tile = self.fabric.getTileByName(tile_name)
        bels: list[Bel] = []
        if not tile:
            logger.error(f"Tile {tile_name} not found in fabric.")
            raise ValueError

        suffix = "vhdl" if isinstance(self.writer, VHDLCodeGenerator) else "v"

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

    def genFabricIOBels(self) -> None:
        """Generates the IO BELs for the generative IOs of the fabric."""

        for tile in self.fabric.tileDic.values():
            if tile.gen_ios:
                logger.info(f"Generating IO BELs for tile {tile.name}")
                self.genIOBelForTile(tile.name)

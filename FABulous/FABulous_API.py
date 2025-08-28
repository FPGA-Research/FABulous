import csv
import os
import pickle
import subprocess as sp
import sys
from collections.abc import Iterable
from pathlib import Path

from loguru import logger

import FABulous.fabric_cad.gen_npnr_model as model_gen_npnr
import FABulous.fabric_generator.parser.parse_csv as fileParser
from FABulous.custom_exception import CommandError, InvalidFileType
from FABulous.fabric_cad.bit_gen import genBitstream
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
from FABulous.FABulous_CLI.helper import (
    check_if_application_exists,
    copy_verilog_files,
    make_hex,
    remove_dir,
)
from FABulous.FABulous_settings import FABulousSettings
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
    projectDir : Path
        Project directory path.
    """

    geometryGenerator: GeometryGenerator
    fabric: Fabric
    fileExtension: str = ".v"
    projectDir: Path

    def __init__(
        self, writer: CodeGenerator, fabricCSV: str = "", projectDir: Path | None = None
    ) -> None:
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
        projectDir : Path, optional
            Project directory path, by default None
        """
        self.writer = writer
        self.projectDir = projectDir or Path.cwd()
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
            switch_matrix_debug_signal = FABulousSettings().switch_matrix_debug_signal
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
            If the number of config access ports does not match the number of config bits.
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

    def setProjectDir(self, projectDir: Path) -> None:
        """Set the project directory.

        Parameters
        ----------
        projectDir : Path
            Path to the project directory.
        """
        self.projectDir = projectDir.absolute()

    def runFABulousFabricFlow(self) -> bool:
        """Execute the complete FABulous fabric generation flow.

        Runs fabric generation, bitstream spec generation, top wrapper generation,
        nextpnr model generation, and geometry generation.

        Returns
        -------
        bool
            True if all steps completed successfully, False otherwise.
        """
        try:
            logger.info("Running FABulous fabric flow")

            # Generate IO fabric
            self.genFabricIOBels()

            # Generate fabric
            logger.info("Generating fabric")
            tileByPath = [
                f.stem for f in (self.projectDir / "Tile/").iterdir() if f.is_dir()
            ]
            tileByFabric = list(self.fabric.tileDic.keys())
            superTileByFabric = list(self.fabric.superTileDic.keys())
            allTiles = list(set(tileByPath) & set(tileByFabric + superTileByFabric))

            # Generate all tiles
            self.genAllTiles(allTiles)

            # Generate fabric
            self.setWriterOutputFile(
                self.projectDir / f"Fabric/{self.fabric.name}.{self.fileExtension}"
            )
            self.genFabric()

            # Generate bitstream spec
            logger.info("Generating bitstream specification")
            self.saveBitStreamSpec()

            # Generate top wrapper
            logger.info("Generating top wrapper")
            self.setWriterOutputFile(
                self.projectDir / f"Fabric/{self.fabric.name}_top.{self.fileExtension}"
            )
            self.genTopWrapper()

            # Generate nextpnr model
            logger.info("Generating nextpnr model")
            self.saveRoutingModel()

            # Generate geometry
            logger.info("Generating geometry")
            geomFile = self.projectDir / f"{self.fabric.name}_geometry.csv"
            self.setWriterOutputFile(geomFile)
            self.genGeometry()

            logger.info("FABulous fabric flow complete")

        except Exception as e:  # noqa: BLE001
            logger.error(f"FABulous fabric flow failed: {e}")
            return False
        else:
            return True

    def genAllTiles(self, tiles: list[str]) -> None:
        """Generate all specified tiles with switch matrix and configuration memory.

        Parameters
        ----------
        tiles : list[str]
            List of tile names to generate.
        """
        for t in tiles:
            logger.info(f"Generating tile {t}")
            subTileDir = self.projectDir / f"Tile/{t}"

            # Check if it's a super tile
            subTiles = (
                [f.stem for f in subTileDir.iterdir() if f.is_dir()]
                if subTileDir.exists()
                else []
            )

            if subTiles:
                logger.info(
                    f"{t} is a super tile, generating {t} with sub tiles {' '.join(subTiles)}"
                )
                for st in subTiles:
                    # Generate sub-tile components
                    self.setWriterOutputFile(
                        subTileDir / f"{st}/{st}_switch_matrix.{self.fileExtension}"
                    )
                    self.genSwitchMatrix(st)

                    self.setWriterOutputFile(
                        subTileDir / f"{st}/{st}_ConfigMem.{self.fileExtension}"
                    )
                    self.genConfigMem(st, subTileDir / f"{st}/{st}_ConfigMem.csv")

                    self.setWriterOutputFile(
                        subTileDir / f"{st}/{st}.{self.fileExtension}"
                    )
                    self.genTile(st)

                # Generate super tile
                self.setWriterOutputFile(subTileDir / f"{t}.{self.fileExtension}")
                self.genSuperTile(t)
            else:
                # Generate regular tile
                self.setWriterOutputFile(
                    subTileDir / f"{t}_switch_matrix.{self.fileExtension}"
                )
                self.genSwitchMatrix(t)

                self.setWriterOutputFile(
                    subTileDir / f"{t}_ConfigMem.{self.fileExtension}"
                )
                self.genConfigMem(t, subTileDir / f"{t}_ConfigMem.csv")

                self.setWriterOutputFile(subTileDir / f"{t}.{self.fileExtension}")
                self.genTile(t)

    def saveBitStreamSpec(self) -> None:
        """Generate and save bitstream specification to files."""
        specObject = self.genBitStreamSpec()
        metaDataDir = self.projectDir / ".FABulous"
        metaDataDir.mkdir(exist_ok=True)

        # Save binary file
        binFile = metaDataDir / "bitStreamSpec.bin"
        logger.info(f"output file: {binFile}")
        with binFile.open("wb") as outFile:
            pickle.dump(specObject, outFile)

        # Save CSV file
        csvFile = metaDataDir / "bitStreamSpec.csv"
        logger.info(f"output file: {csvFile}")
        with csvFile.open("w") as f:
            w = csv.writer(f)
            for key1 in specObject["TileSpecs"]:
                w.writerow([key1])
                for key2, val in specObject["TileSpecs"][key1].items():
                    w.writerow([key2, val])

    def saveRoutingModel(self) -> None:
        """Generate and save nextpnr routing model files."""
        npnrModel = self.genRoutingModel()
        metaDataDir = self.projectDir / ".FABulous"
        metaDataDir.mkdir(exist_ok=True)

        # Save model files
        (metaDataDir / "pips.txt").write_text(npnrModel[0])
        logger.info(f"output file: {metaDataDir / 'pips.txt'}")

        (metaDataDir / "bel.txt").write_text(npnrModel[1])
        logger.info(f"output file: {metaDataDir / 'bel.txt'}")

        (metaDataDir / "bel.v2.txt").write_text(npnrModel[2])
        logger.info(f"output file: {metaDataDir / 'bel.v2.txt'}")

        (metaDataDir / "template.pcf").write_text(npnrModel[3])
        logger.info(f"output file: {metaDataDir / 'template.pcf'}")

    def runPlaceAndRoute(self, jsonFile: Path) -> None:
        """Run place and route with Nextpnr for a given JSON file.

        Parameters
        ----------
        jsonFile : Path
            Path to the JSON file generated by Yosys.

        Raises
        ------
        InvalidFileType
            If the file is not a JSON file.
        FileNotFoundError
            If required files are not found.
        CommandError
            If place and route fails.
        """
        if jsonFile.suffix != ".json":
            raise InvalidFileType(
                "No json file provided. Usage: place_and_route <json_file>"
            )

        parent = jsonFile.parent
        json_file = jsonFile.name
        top_module_name = jsonFile.stem
        fasm_file = f"{top_module_name}.fasm"
        log_file = f"{top_module_name}_npnr_log.txt"

        # Check for required files
        metaDataDir = self.projectDir / ".FABulous"
        if (
            not (metaDataDir / "pips.txt").exists()
            or not (metaDataDir / "bel.txt").exists()
        ):
            raise FileNotFoundError(
                "Pips and Bel files are not found, please run model_gen_npnr first"
            )

        if not jsonFile.exists():
            raise FileNotFoundError(
                f'Cannot find file "{json_file}" in path "{parent}/".'
            )

        logger.info(f"Running Placement and Routing with Nextpnr for design {jsonFile}")

        # Run nextpnr
        npnr = FABulousSettings().nextpnr_path
        runCmd = [
            f"FAB_ROOT={self.projectDir}",
            str(npnr),
            "--uarch",
            "fabulous",
            "--json",
            str(jsonFile),
            "-o",
            f"fasm={parent / fasm_file}",
            "--verbose",
            "--log",
            str(parent / log_file),
        ]

        result = sp.run(
            " ".join(runCmd),
            stdout=sys.stdout,
            stderr=sp.STDOUT,
            check=True,
            shell=True,
        )
        if result.returncode != 0:
            raise CommandError("Nextpnr failed with non-zero exit code")

        logger.info("Placement and Routing completed")

    def generateBitstream(self, fasmFile: Path) -> None:
        """Generate bitstream from FASM file.

        Parameters
        ----------
        fasmFile : Path
            Path to the FASM file.

        Raises
        ------
        InvalidFileType
            If the file is not a FASM file.
        FileNotFoundError
            If required files are not found.
        CommandError
            If bitstream generation fails.
        """
        if fasmFile.suffix != ".fasm":
            raise InvalidFileType(
                "No fasm file provided. Usage: gen_bitStream_binary <fasm_file>"
            )

        parent = fasmFile.parent
        top_module_name = fasmFile.stem
        bitstream_file = f"{top_module_name}.bin"

        # Check for required files
        bitStreamSpecFile = self.projectDir / ".FABulous/bitStreamSpec.bin"
        if not bitStreamSpecFile.exists():
            raise FileNotFoundError(
                "Cannot find bitStreamSpec.bin file, which is generated by running gen_bitStream_spec"
            )

        if not fasmFile.exists():
            raise FileNotFoundError(
                f"Cannot find {fasmFile} file which is generated by running place_and_route."
            )

        logger.info(f"Generating Bitstream for design {fasmFile}")
        logger.info(f"Outputting to {parent / bitstream_file}")

        try:
            genBitstream(
                str(fasmFile), str(bitStreamSpecFile), str(parent / bitstream_file)
            )
        except Exception as e:
            raise CommandError(
                f"Bitstream generation failed for {fasmFile}. Please check the logs for more details."
            ) from e

        logger.info("Bitstream generated")

    def runSimulation(self, bitstreamFile: Path, waveform_format: str = "fst") -> None:
        """Run simulation for FPGA design using Icarus Verilog.

        Parameters
        ----------
        bitstreamFile : Path
            Path to the bitstream file.
        waveform_format : str, optional
            Waveform output format ("fst" or "vcd"), by default "fst".

        Raises
        ------
        InvalidFileType
            If the file is not a bitstream file.
        FileNotFoundError
            If the bitstream file is not found.
        CommandError
            If simulation fails.
        """
        if bitstreamFile.suffix != ".bin":
            raise InvalidFileType(
                "No bitstream file specified. Usage: run_simulation <format> <bitstream_file>"
            )

        if not bitstreamFile.exists():
            raise FileNotFoundError(
                f"Cannot find {bitstreamFile} file which is generated by running gen_bitStream_binary."
            )

        topModule = bitstreamFile.stem
        defined_option = f"CREATE_{waveform_format.upper()}"

        designFile = f"{topModule}.v"
        topModuleTB = f"{topModule}_tb"
        testBench = f"{topModuleTB}.v"
        vvpFile = f"{topModuleTB}.vvp"

        logger.info(f"Running simulation for {designFile}")

        testPath = self.projectDir / "Test"
        buildDir = testPath / "build"
        fabricFilesDir = buildDir / "fabric_files"

        buildDir.mkdir(exist_ok=True)
        fabricFilesDir.mkdir(exist_ok=True)

        # Copy verilog files
        copy_verilog_files(self.projectDir / "Tile", fabricFilesDir)
        copy_verilog_files(self.projectDir / "Fabric", fabricFilesDir)
        file_list = [str(i) for i in fabricFilesDir.glob("*.v")]

        # Run iverilog
        iverilog = check_if_application_exists(
            os.getenv("FAB_IVERILOG_PATH", "iverilog")
        )
        runCmd = [
            str(iverilog),
            "-D",
            defined_option,
            "-s",
            topModuleTB,
            "-o",
            str(buildDir / vvpFile),
            *file_list,
            str(bitstreamFile.parent / designFile),
            str(testPath / testBench),
        ]

        result = sp.run(runCmd, check=True)
        if result.returncode != 0:
            raise CommandError(
                f"Simulation failed for {designFile}. Please check the logs for more details."
            )

        # Create hex file for simulation
        bitstreamHexPath = (buildDir.parent / bitstreamFile.stem).with_suffix(".hex")
        make_hex(bitstreamFile, bitstreamHexPath)

        # Run vvp
        vvp = FABulousSettings().vvp_path
        vvpArgs = [
            f"+output_waveform={testPath / topModule}.{waveform_format}",
            f"+bitstream_hex={bitstreamHexPath}",
        ]
        if waveform_format == "fst":
            vvpArgs.append("-fst")

        runCmd = [str(vvp), str(buildDir / vvpFile)] + vvpArgs
        result = sp.run(runCmd, check=True)

        remove_dir(buildDir)
        if result.returncode != 0:
            raise CommandError(
                f"Simulation failed for {designFile}. Please check the logs for more details."
            )

        logger.info("Simulation finished")

    def runFABulousBitstreamFlow(self, verilogFile: Path) -> bool:
        """Run the complete FABulous bitstream generation flow.

        Runs synthesis, place and route, and bitstream generation.

        Parameters
        ----------
        verilogFile : Path
            Path to the Verilog file.

        Returns
        -------
        bool
            True if all steps completed successfully, False otherwise.

        Raises
        ------
        InvalidFileType
            If the file is not a Verilog file.
        """
        if verilogFile.suffix != ".v":
            raise InvalidFileType(
                "No verilog file provided. Usage: run_FABulous_bitstream <top_module_file>"
            )

        try:
            logger.info(f"Running FABulous bitstream flow for {verilogFile}")

            file_path_no_suffix = verilogFile.parent / verilogFile.stem
            json_file_path = file_path_no_suffix.with_suffix(".json")
            fasm_file_path = file_path_no_suffix.with_suffix(".fasm")

            # Note: Synthesis would need to be implemented separately as it involves external tools
            # This is a placeholder for the synthesis step
            logger.info("Synthesis step would be called here")

            # Run place and route
            self.runPlaceAndRoute(json_file_path)

            # Generate bitstream
            self.generateBitstream(fasm_file_path)

            logger.info("FABulous bitstream generation complete")

        except Exception as e:  # noqa: BLE001
            logger.error(f"FABulous bitstream flow failed: {e}")
            return False
        else:
            return True

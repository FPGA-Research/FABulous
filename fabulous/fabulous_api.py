"""FABulous API module for fabric and geometry generation.

This module provides the main API class for managing FPGA fabric generation, including
parsing fabric definitions, generating HDL code, creating geometries, and handling
various fabric-related operations.
"""

import shutil
from collections.abc import Iterable
from pathlib import Path

from loguru import logger

import fabulous.fabric_generator.parser.parse_csv as fileParser
from fabulous.fabric_cad.gen_bitstream_spec import generateBitstreamSpec
from fabulous.fabric_cad.gen_design_top_wrapper import generateUserDesignTopWrapper

# Importing Modules from FABulous Framework.
from fabulous.fabric_definition.bel import Bel
from fabulous.fabric_definition.define import ConfigBitMode, Side
from fabulous.fabric_definition.fabric import Fabric
from fabulous.fabric_definition.supertile import SuperTile
from fabulous.fabric_definition.tile import Tile
from fabulous.fabric_generator.code_generator import CodeGenerator
from fabulous.fabric_generator.code_generator.code_generator_VHDL import (
    VHDLCodeGenerator,
)
from fabulous.fabric_generator.gds_generator.flows.fabric_macro_flow import (
    FABulousFabricMacroFlow,
)
from fabulous.fabric_generator.gds_generator.flows.fabric_optimisation_flow import (
    FABulousFabricOptimisationFlow,
)
from fabulous.fabric_generator.gds_generator.flows.tile_macro_flow import (
    FABulousTileVerilogMacroFlow,
)
from fabulous.fabric_generator.gds_generator.gen_io_pin_config_yaml import (
    generate_IO_pin_order_config,
)
from fabulous.fabric_generator.gds_generator.steps.tile_area_opt import OptMode
from fabulous.fabric_generator.gen_fabric.fabric_automation import genIOBel
from fabulous.fabric_generator.gen_fabric.gen_configmem import generateConfigMem
from fabulous.fabric_generator.gen_fabric.gen_fabric import generateFabric
from fabulous.fabric_generator.gen_fabric.gen_helper import (
    bootstrapSwitchMatrix,
    list2CSV,
)
from fabulous.fabric_generator.gen_fabric.gen_switchmatrix import genTileSwitchMatrix
from fabulous.fabric_generator.gen_fabric.gen_tile import (
    generateSuperTile,
    generateTile,
)
from fabulous.fabric_generator.gen_fabric.gen_top_wrapper import generateTopWrapper
from fabulous.fabulous_settings import get_context
from fabulous.geometry_generator.geometry_gen import GeometryGenerator
from fabulous.routing_model.generator import RoutingModelGenerator
from fabulous.routing_model.graph_algorithms import DelayType
from fabulous.routing_model.tile_timing_model import TimingModelMode


class FABulous_API:
    """Class for managing fabric and geometry generation.

    This class parses fabric data from 'fabric.csv', generates fabric layouts,
    geometries, models for nextpnr, as well as
    other fabric-related functions.

    If 'fabricCSV' is provided, parses fabric data and initialises
    'fabricGenerator' and 'geometryGenerator' with parsed data.

    If using VHDL, changes the extension from '.v' to'.vhdl'.

    Parameters
    ----------
    writer : CodeGenerator
        Object responsible for generating code from code_generator.py
    fabricCSV : str, optional
        Path to the CSV file containing fabric data, by default ""

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
        self.writer = writer
        if fabricCSV != "":
            self.fabric = fileParser.parseFabricCSV(fabricCSV)
            self.geometryGenerator = GeometryGenerator(self.fabric)
        if isinstance(self.writer, VHDLCodeGenerator):
            self.fileExtension = ".vhdl"

    def setWriterOutputFile(self, outputDir: Path) -> None:
        """Set the output file directory for the write object.

        Parameters
        ----------
        outputDir : Path
            Directory path where output files will be saved.
        """
        logger.info(f"Output file: {outputDir}")
        self.writer.outFileName = outputDir

    def loadFabric(self, fabric_dir: Path) -> None:
        """Load fabric data from 'fabric.csv'.

        Parameters
        ----------
        fabric_dir : Path
            Path to CSV file containing fabric data.

        Raises
        ------
        ValueError
            If 'fabric_dir' does not end with '.csv'
        """
        if fabric_dir.suffix == ".csv":
            self.fabric = fileParser.parseFabricCSV(fabric_dir)
            self.geometryGenerator = GeometryGenerator(self.fabric)
        else:
            logger.error("Only .csv files are supported for fabric loading")
            raise ValueError

    def bootstrapSwitchMatrix(self, tileName: str, outputDir: Path) -> None:
        """Bootstrap the switch matrix for the specified tile.

        Using 'bootstrapSwitchMatrix' defined in 'fabric_gen.py'.

        Parameters
        ----------
        tileName : str
            Name of the tile for which the switch matrix will be bootstrapped.
        outputDir : Path
            Directory path where the switch matrix will be generated.

        Raises
        ------
        ValueError
            If tile is not found in fabric.
        """
        tile = self.fabric.getTileByName(tileName)
        if not tile:
            raise ValueError(f"Tile {tileName} not found in fabric.")
        bootstrapSwitchMatrix(tile, outputDir)

    def addList2Matrix(self, listFile: Path, matrix: Path) -> None:
        """Convert list into CSV matrix and save it.

        Using 'list2CSV' defined in 'fabric_gen.py'.

        Parameters
        ----------
        listFile : Path
            List data to be converted.
        matrix : Path
            File path where the matrix data will be saved.
        """
        list2CSV(listFile, matrix)

    def genConfigMem(self, tileName: str, configMem: Path) -> None:
        """Generate configuration memory for specified tile.

        Parameters
        ----------
        tileName : str
            Name of the tile for which configuration memory will be generated.
        configMem : Path
            File path where the configuration memory will be saved.

        Raises
        ------
        ValueError
            If tile is not found in fabric.
        """
        if tile := self.fabric.getTileByName(tileName):
            generateConfigMem(
                self.writer,
                tile,
                configMem,
                frame_bits_per_row=self.fabric.frameBitsPerRow,
                max_frame_per_col=self.fabric.maxFramesPerCol,
            )
        else:
            raise ValueError(f"Tile {tileName} not found")

    def genSwitchMatrix(
        self, tileName: str, csv_output_dir: Path | None = None
    ) -> None:
        """Generate switch matrix for specified tile.

        Using 'genTileSwitchMatrix' defined in 'fabric_gen.py'.

        Parameters
        ----------
        tileName : str
            Name of the tile for which the switch matrix will be generated.
        csv_output_dir : Path | None
            Optional directory to write the generated CSV file when converting
            from `.list` format. If None, the CSV is written to the same directory
            as the source `.list` file. This parameter is ignored when the input
            is already a `.csv` file.

        Raises
        ------
        ValueError
            If tile is not found in fabric.
        """
        if tile := self.fabric.getTileByName(tileName):
            switch_matrix_debug_signal = get_context().switch_matrix_debug_signal
            logger.info(
                f"Generate switch matrix debug signals: {switch_matrix_debug_signal}"
            )
            genTileSwitchMatrix(
                self.writer,
                tile,
                switch_matrix_debug_signal,
                csv_output_dir=csv_output_dir,
                config_bit_mode=self.fabric.configBitMode,
                multiplexer_style=self.fabric.multiplexerStyle,
                default_pip_delay=self.fabric.generateDelayInSwitchMatrix,
                preserve_list_order=self.fabric.preserveListOrder,
            )
        else:
            raise ValueError(f"Tile {tileName} not found")

    def genTile(
        self,
        tileName: str,
        frame_bit_per_row: int | None = None,
        max_frame_per_col: int | None = None,
        disable_user_clk: bool | None = None,
        config_bit_mode: ConfigBitMode | None = None,
    ) -> None:
        """Generate a tile based on its name.

        Using 'generateTile' defined in 'fabric_gen.py'.

        Parameters
        ----------
        tileName : str
            Name of the tile generated.
        frame_bit_per_row : int | None
            Override for the fabric's ``frameBitsPerRow``. If ``None``, the value
            from ``self.fabric`` is used.
        max_frame_per_col : int | None
            Override for the fabric's ``maxFramesPerCol``. If ``None``, the value
            from ``self.fabric`` is used.
        disable_user_clk : bool | None
            Override for the fabric's ``disableUserCLK``. If ``None``, the value
            from ``self.fabric`` is used.
        config_bit_mode : ConfigBitMode | None
            Override for the fabric's ``configBitMode``. If ``None``, the value
            from ``self.fabric`` is used.

        Raises
        ------
        ValueError
            If tile is not found in fabric.
        """
        if tile := self.fabric.getTileByName(tileName):
            generateTile(
                self.writer,
                tile,
                frame_bit_per_row or self.fabric.frameBitsPerRow,
                max_frame_per_col or self.fabric.maxFramesPerCol,
                disable_user_clk or self.fabric.disableUserCLK,
                config_bit_mode or self.fabric.configBitMode,
            )
        else:
            raise ValueError(f"Tile {tileName} not found")

    def genSuperTile(
        self,
        tileName: str,
        frame_bit_per_row: int | None = None,
        max_frame_per_col: int | None = None,
        disable_user_clk: bool | None = None,
        config_bit_mode: ConfigBitMode | None = None,
    ) -> None:
        """Generate a super tile based on its name.

        Using 'generateSuperTile' defined in 'fabric_gen.py'.

        Parameters
        ----------
        tileName : str
            Name of the super tile generated.
        frame_bit_per_row : int | None
            Override for the fabric's ``frameBitsPerRow``. If ``None``, the value
            from ``self.fabric`` is used.
        max_frame_per_col : int | None
            Override for the fabric's ``maxFramesPerCol``. If ``None``, the value
            from ``self.fabric`` is used.
        disable_user_clk : bool | None
            Override for the fabric's ``disableUserCLK``. If ``None``, the value
            from ``self.fabric`` is used.
        config_bit_mode : ConfigBitMode | None
            Override for the fabric's ``configBitMode``. If ``None``, the value
            from ``self.fabric`` is used.

        Raises
        ------
        ValueError
            If super tile is not found in fabric.
        """
        if tile := self.fabric.getSuperTileByName(tileName):
            generateSuperTile(
                self.writer,
                tile,
                frame_bit_per_row or self.fabric.frameBitsPerRow,
                max_frame_per_col or self.fabric.maxFramesPerCol,
                disable_user_clk or self.fabric.disableUserCLK,
                config_bit_mode or self.fabric.configBitMode,
            )
        else:
            raise ValueError(f"SuperTile {tileName} not found")

    def genFabric(self) -> None:
        """Generate the entire fabric layout.

        Via 'generateFabric' defined in 'fabric_gen.py'.
        """
        generateFabric(self.writer, self.fabric)

    def genGeometry(self, geomPadding: int = 8) -> None:
        """Generate geometry based on the fabric data and save it to CSV.

        Parameters
        ----------
        geomPadding : int, optional
            Padding value for geometry generation, by default 8.
        """
        self.geometryGenerator.generateGeometry(geomPadding)
        self.geometryGenerator.saveToCSV(self.writer.outFileName)

    def genTopWrapper(self) -> None:
        """Generate the top wrapper for the fabric.

        Using 'generateTopWrapper' defined in 'fabric_gen.py'.
        """
        generateTopWrapper(self.writer, self.fabric)

    def genBitStreamSpec(self) -> dict:
        """Generate the bitstream specification object.

        Returns
        -------
        dict
            Bitstream specification object generated by 'fabricGenerator'.
        """
        return generateBitstreamSpec(self.fabric)

    def generate_routing_model(
        self,
        mode: TimingModelMode = TimingModelMode.PLACEHOLDER,
        consider_wire_delay: bool = True,
        delay_type: DelayType = DelayType.MAX_ALL,
        delay_scaling_factor: float = 1.0,
        verilog_files: list[Path] | None = None,
    ) -> tuple[str, str, str, str]:
        """Generate the nextpnr routing model for the fabric.

        Parameters
        ----------
        mode : TimingModelMode
            Timing mode. In ``TimingModelMode.PLACEHOLDER`` (the default) the model
            uses placeholder pip delays; otherwise per-pip routing delays are
            extracted from the timing models built in the given mode.
        consider_wire_delay : bool
            Whether to include wire delay in the physical analysis, by default True.
        delay_type : DelayType
            How multi-corner delays are collapsed to a scalar, by default
            DelayType.MAX_ALL.
        delay_scaling_factor : float
            Scaling factor applied to computed delays, by default 1.0.
        verilog_files : list[Path] | None
            Fabric Verilog source files used to build the timing models. Required
            when ``mode`` is given, ignored otherwise, by default None.

        Returns
        -------
        tuple[str, str, str, str]
            The pip, old-style BEL, new-style BEL, and constraint descriptions.
        """
        return RoutingModelGenerator(
            self.fabric,
            mode=mode,
            consider_wire_delay=consider_wire_delay,
            delay_type=delay_type,
            delay_scaling_factor=delay_scaling_factor,
            verilog_files=verilog_files,
        ).generate()

    def getBels(self) -> list[Bel]:
        """Return all unique Bels within a fabric.

        Returns
        -------
        list[Bel]
            List of all unique Bel objects in the fabric.
        """
        return self.fabric.getAllUniqueBels()

    def getTile(
        self, tileName: str, raises_on_miss: bool = False
    ) -> Tile | SuperTile | None:
        """Return 'Tile' or 'SuperTile' object based on 'tileName'.

        Parameters
        ----------
        tileName : str
            Name of the Tile.
        raises_on_miss : bool, optional
            Whether to raise an error if the tile is not found, by default 'False'.

        Returns
        -------
        Tile | SuperTile | None
            'Tile' or 'SuperTile' object based on tile name, or 'None' if not found.

        Raises
        ------
        KeyError
            If the tile specified by 'tileName' is not found and 'raises_on_miss'
            is 'True'.
        """
        try:
            return self.fabric.getTileByName(tileName)
        except KeyError as e:
            if raises_on_miss:
                raise KeyError from e
            return None

    def getTiles(self) -> Iterable[Tile]:
        """Return all Tiles within a fabric.

        Returns
        -------
        Iterable[Tile]
            Collection of all Tile objects in the fabric.
        """
        return self.fabric.tileDic.values()

    def getSuperTile(
        self, tileName: str, raises_on_miss: bool = False
    ) -> SuperTile | None:
        """Return 'SuperTile' object based on 'tileName'.

        Parameters
        ----------
        tileName : str
            Name of the SuperTile.
        raises_on_miss : bool, optional
            Whether to raise an error if the supertile is not found, by default 'False'.

        Returns
        -------
        SuperTile | None
            SuperTile object based on tile name, or None if not found.

        Raises
        ------
        KeyError
            If the supertile specified by 'tileName' is not found and 'raises_on_miss'
            is 'True'.
        """
        try:
            return self.fabric.getSuperTileByName(tileName)
        except KeyError as e:
            if raises_on_miss:
                raise KeyError from e
            return None

    def getSuperTiles(self) -> Iterable[SuperTile]:
        """Return all SuperTiles within a fabric.

        Returns
        -------
        Iterable[SuperTile]
            Collection of all SuperTile objects in the fabric.
        """
        return self.fabric.superTileDic.values()

    def generateUserDesignTopWrapper(self, userDesign: Path, topWrapper: Path) -> None:
        """Generate the top wrapper for the user design.

        Parameters
        ----------
        userDesign : Path
            Path to the user design file.
        topWrapper : Path
            Path to the output top wrapper file.
        """
        generateUserDesignTopWrapper(self.fabric, userDesign, topWrapper)

    def genIOBelForTile(self, tile_name: str) -> list[Bel]:
        """Generate the IO BELs for the generative IOs of a tile.

        Config Access Generative IOs will be a separate Bel.
        Updates the tileDic with the generated IO BELs.

        Parameters
        ----------
        tile_name : str
            Name of the tile to generate IO Bels.

        Returns
        -------
        list[Bel]
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
        """Generate the IO BELs for the generative IOs of the fabric."""
        for tile in self.fabric.tileDic.values():
            if tile.gen_ios:
                logger.info(f"Generating IO BELs for tile {tile.name}")
                self.genIOBelForTile(tile.name)

    def gen_io_pin_order_config(
        self,
        tile: Tile | SuperTile,
        outfile: Path,
        prefix: str = "",
        *,
        external_port_side: Side = Side.SOUTH,
    ) -> None:
        """Generate IO pin order configuration YAML for a tile or super tile.

        Parameters
        ----------
        tile : Tile | SuperTile
            The fabric element for which to generate the configuration.
        outfile : Path
            Output YAML path.
        prefix : str
            Prefix to add to port names.
        external_port_side : Side
            Side used for BEL external ports when no fabric placement context
            is available.
        """
        generate_IO_pin_order_config(
            tile,
            outfile,
            fabric=self.fabric,
            prefix=prefix,
            external_port_side=external_port_side,
        )

    def genTileMacro(
        self,
        tile_dir: Path,
        io_pin_config: Path,
        out_folder: Path,
        pdk: str,
        pdk_root: Path,
        *,
        final_view: Path | None = None,
        optimisation: OptMode | None = OptMode.BALANCE,
        base_config_path: Path | None = None,
        config_override_path: Path | None = None,
        custom_config_overrides: dict | None = None,
    ) -> None:
        """Run the macro flow to generate the macro Verilog files."""
        logger.info(f"PDK root: {pdk_root}")
        logger.info(f"PDK: {pdk}")
        logger.info(f"Output folder: {out_folder.resolve()}")
        flow = FABulousTileVerilogMacroFlow(
            self.fabric.getTileByName(tile_dir.name),
            io_pin_config,
            OptMode(optimisation),
            pdk=pdk,
            pdk_root=pdk_root,
            base_config_path=base_config_path,
            override_config_path=config_override_path,
            **custom_config_overrides or {},
        )
        result = flow.start()
        if final_view:
            logger.info(f"Saving final view to {final_view}")
            result.save_snapshot(final_view)
        else:
            logger.info(
                f"Saving final views for FABulous to {out_folder / 'final_views'}"
            )
            result.save_snapshot(out_folder / "final_views")
        logger.info("Macro flow completed.")

    def fabric_stitching(
        self,
        tile_macro_paths: dict[str, Path],
        fabric_path: Path,
        out_folder: Path,
        pdk: str,
        pdk_root: Path,
        *,
        base_config_path: Path | None = None,
        config_override_path: Path | None = None,
        **custom_config_overrides: dict,
    ) -> None:
        """Run the stitching flow to assemble tile macros into a fabric-level GDS.

        Parameters
        ----------
        tile_macro_paths : dict[str, Path]
            Dictionary mapping tile names to their macro output directories.
        fabric_path : Path
            Path to the fabric-level Verilog file.
        out_folder : Path
            Output directory for the stitched fabric.
        pdk : str
            PDK name to use.
        pdk_root : Path
            Path to PDK root directory.
        base_config_path : Path | None
            Path to base configuration YAML file.
        config_override_path : Path | None, optional
            Additional configuration overrides.
        **custom_config_overrides : dict
            software configuration overrides.
        """
        logger.info(f"PDK root: {pdk_root}")
        logger.info(f"PDK: {pdk}")
        logger.info(f"Output folder: {out_folder.resolve()}")

        flow = FABulousFabricMacroFlow(
            fabric=self.fabric,
            fabric_verilog_paths=[fabric_path],
            tile_macro_dirs=tile_macro_paths,
            base_config_path=base_config_path,
            config_override_path=config_override_path,
            design_dir=out_folder,
            pdk_root=pdk_root,
            pdk=pdk,
            **custom_config_overrides,
        )
        result = flow.start()
        logger.info(f"Saving final views for FABulous to {out_folder / 'final_views'}")
        result.save_snapshot(out_folder / "final_views")
        logger.info("Stitching flow completed.")

    def full_fabric_automation(
        self,
        project_dir: Path,
        out_folder: Path,
        pdk: str,
        pdk_root: Path,
        *,
        base_config_path: Path | None = None,
        config_override_path: Path | None = None,
        tile_opt_config: Path | None = None,
        nlp_only: bool = False,
        nlp_area_margin: float = 0.05,
        **config_overrides: dict,
    ) -> None:
        """Run the stitching flow to assemble tile macros into a fabric-level GDS."""
        logger.info(f"PDK root: {pdk_root}")
        logger.info(f"PDK: {pdk}")
        logger.info(f"Output folder: {out_folder.resolve()}")
        config_args = {
            "FABULOUS_PROJ_DIR": str(project_dir.resolve()),
            "FABULOUS_FABRIC": self.fabric,
            "DESIGN_NAME": self.fabric.name,
            "FABULOUS_NLP_ONLY": nlp_only,
            "FABULOUS_NLP_AREA_MARGIN": nlp_area_margin,
        }
        if tile_opt_config is not None:
            config_args["TILE_OPT_INFO"] = str(tile_opt_config)
        configs = [
            i
            for i in [
                config_args,
                base_config_path,
                config_override_path,
                config_overrides,
            ]
            if i is not None
        ]
        flow = FABulousFabricOptimisationFlow(
            configs,
            name=self.fabric.name,
            design_dir=str(out_folder.resolve()),
            pdk=pdk,
            pdk_root=str(pdk_root.resolve()),
        )
        result = flow.start()
        final_views = out_folder / "final_views"
        logger.info(f"Saving final views for FABulous to {final_views}")
        result.save_snapshot(final_views)
        tile_opt_summary = flow.config.get("TILE_OPT_INFO")
        if tile_opt_summary is not None:
            summary_src = Path(tile_opt_summary)
            summary_dst = final_views / summary_src.name
            logger.info(f"Copying tile optimisation summary to {summary_dst}")
            shutil.copyfile(summary_src, summary_dst)
        logger.info("Stitching flow completed.")

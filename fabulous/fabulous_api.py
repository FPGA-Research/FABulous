"""FABulous API module for fabric and geometry generation.

DEPRECATED: This module provides backward compatibility for existing code.
New code should use the processing pipeline architecture:
- Context for state management
- Transform for fabric mutations
- Direct imports for exporters

See fabulous.core for the new architecture.
"""

import warnings
from collections.abc import Iterable
from pathlib import Path

from loguru import logger

import fabulous.fabric_cad.gen_npnr_model as model_gen_npnr
from fabulous.core import Context, Transform
from fabulous.fabric_cad.gen_bitstream_spec import generateBitstreamSpec
from fabulous.fabric_cad.gen_design_top_wrapper import generateUserDesignTopWrapper

# Importing Modules from FABulous Framework.
from fabulous.fabric_definition.bel import Bel
from fabulous.fabric_definition.fabric import Fabric
from fabulous.fabric_definition.supertile import SuperTile
from fabulous.fabric_definition.tile import Tile
from fabulous.fabric_generator.code_generator import CodeGenerator
from fabulous.fabric_generator.code_generator.code_generator_VHDL import (
    VHDLCodeGenerator,
)
from fabulous.fabric_generator.gds_generator.steps.tile_optimisation import OptMode
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


class FABulous_API:
    """DEPRECATED: Use Context and Transform instead.

    This class is maintained for backward compatibility.
    New code should use the processing pipeline architecture:
    - Context for state management
    - Transform for fabric mutations
    - Direct imports from fabulous package for exporters

    Example migration::

        # Old way
        api = FABulous_API(writer, "fabric.csv")
        api.genFabric()

        # New way
        from fabulous import Context, generateFabric
        context = Context(writer, "fabric.csv")
        generateFabric(context.writer, context.fabric)

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
        warnings.warn(
            "FABulous_API is deprecated. Use Context and Transform from fabulous.core instead. "
            "See https://github.com/FABulous/FABulous for migration guide.",
            DeprecationWarning,
            stacklevel=2,
        )

        # Create new architecture components
        self._context = Context(writer, fabricCSV if fabricCSV else None)
        self._transform = Transform(self._context)

        # Maintain backward compatibility for direct attribute access
        self.writer = self._context.writer
        self.fileExtension = ".vhdl" if isinstance(writer, VHDLCodeGenerator) else ".v"

    @property
    def fabric(self) -> Fabric:
        """Get fabric from context."""
        return self._context.fabric

    @property
    def geometryGenerator(self) -> GeometryGenerator:
        """Get geometry generator from context."""
        return self._context.geometryGenerator

    def setWriterOutputFile(self, outputDir: Path) -> None:
        """Set the output file directory for the write object.

        Parameters
        ----------
        outputDir : Path
            Directory path where output files will be saved.
        """
        logger.info(f"Output file: {outputDir}")
        self._context.set_output(outputDir)

    def loadFabric(self, fabric_dir: Path) -> None:
        """Load fabric data from fabric definition file.

        Parameters
        ----------
        fabric_dir : Path
            Path to fabric definition file (CSV or YAML)

        Raises
        ------
        ValueError
            If file format is not supported
        """
        self._context.load_fabric(fabric_dir)

    def bootstrapSwitchMatrix(self, tileName: str, outputDir: Path) -> None:
        """Bootstrap the switch matrix for the specified tile.

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
        tile = self._context.get_tile(tileName, required=True)
        bootstrapSwitchMatrix(tile, outputDir)

    def addList2Matrix(self, listFile: Path, matrix: Path) -> None:
        """Convert list into CSV matrix and save it.

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
        tile = self._context.get_tile(tileName, required=True)
        generateConfigMem(
            self._context.writer, self._context.fabric, tile, configMem
        )

    def genSwitchMatrix(self, tileName: str) -> None:
        """Generate switch matrix for specified tile.

        Parameters
        ----------
        tileName : str
            Name of the tile for which the switch matrix will be generated.

        Raises
        ------
        ValueError
            If tile is not found in fabric.
        """
        tile = self._context.get_tile(tileName, required=True)
        switch_matrix_debug_signal = get_context().switch_matrix_debug_signal
        logger.info(
            f"Generate switch matrix debug signals: {switch_matrix_debug_signal}"
        )
        genTileSwitchMatrix(
            self._context.writer,
            self._context.fabric,
            tile,
            switch_matrix_debug_signal,
        )

    def genTile(self, tileName: str) -> None:
        """Generate a tile based on its name.

        Parameters
        ----------
        tileName : str
            Name of the tile generated.

        Raises
        ------
        ValueError
            If tile is not found in fabric.
        """
        tile = self._context.get_tile(tileName, required=True)
        generateTile(self._context.writer, self._context.fabric, tile)

    def genSuperTile(self, tileName: str) -> None:
        """Generate a super tile based on its name.

        Parameters
        ----------
        tileName : str
            Name of the super tile generated.

        Raises
        ------
        ValueError
            If super tile is not found in fabric.
        """
        tile = self._context.get_super_tile(tileName, required=True)
        generateSuperTile(self._context.writer, self._context.fabric, tile)

    def genFabric(self) -> None:
        """Generate the entire fabric layout."""
        generateFabric(self._context.writer, self._context.fabric)

    def genGeometry(self, geomPadding: int = 8) -> None:
        """Generate geometry based on the fabric data and save it to CSV.

        Parameters
        ----------
        geomPadding : int, optional
            Padding value for geometry generation, by default 8.
        """
        self._context.geometryGenerator.generateGeometry(geomPadding)
        self._context.geometryGenerator.saveToCSV(self._context.writer.outFileName)

    def genTopWrapper(self) -> None:
        """Generate the top wrapper for the fabric."""
        generateTopWrapper(self._context.writer, self._context.fabric)

    def genBitStreamSpec(self) -> dict:
        """Generate the bitstream specification object.

        Returns
        -------
        dict
            Bitstream specification object
        """
        return generateBitstreamSpec(self._context.fabric)

    def genRoutingModel(self) -> tuple[str, str, str, str]:
        """Generate model for Nextpnr based on fabric data.

        Returns
        -------
        tuple[str, str, str, str]
            Model generated for Nextpnr
        """
        return model_gen_npnr.genNextpnrModel(self._context.fabric)

    def getBels(self) -> list[Bel]:
        """Return all unique Bels within a fabric.

        Returns
        -------
        list[Bel]
            List of all unique Bel objects in the fabric.
        """
        return self._context.fabric.getAllUniqueBels()

    def getTile(
        self, tileName: str, raises_on_miss: bool = False
    ) -> Tile | SuperTile | None:
        """Return Tile object based on tile name.

        Parameters
        ----------
        tileName : str
            Name of the Tile.
        raises_on_miss : bool, optional
            Whether to raise an error if the tile is not found, by default False.

        Returns
        -------
        Tile | SuperTile | None
            Tile object based on tile name, or None if not found.

        Raises
        ------
        KeyError
            If tile is not found and 'raises_on_miss' is True.
        """
        return self._context.get_tile(tileName, required=raises_on_miss)

    def getTiles(self) -> Iterable[Tile]:
        """Return all Tiles within a fabric.

        Returns
        -------
        Iterable[Tile]
            Collection of all Tile objects in the fabric.
        """
        return self._context.get_tiles()

    def getSuperTile(
        self, tileName: str, raises_on_miss: bool = False
    ) -> SuperTile | None:
        """Return SuperTile object based on tile name.

        Parameters
        ----------
        tileName : str
            Name of the SuperTile.
        raises_on_miss : bool, optional
            Whether to raise an error if the supertile is not found, by default False.

        Returns
        -------
        SuperTile | None
            SuperTile object based on tile name, or None if not found.

        Raises
        ------
        KeyError
            If tile is not found and 'raises_on_miss' is True.
        """
        return self._context.get_super_tile(tileName, required=raises_on_miss)

    def getSuperTiles(self) -> Iterable[SuperTile]:
        """Return all SuperTiles within a fabric.

        Returns
        -------
        Iterable[SuperTile]
            Collection of all SuperTile objects in the fabric.
        """
        return self._context.get_super_tiles()

    def generateUserDesignTopWrapper(self, userDesign: Path, topWrapper: Path) -> None:
        """Generate the top wrapper for the user design.

        Parameters
        ----------
        userDesign : Path
            Path to the user design file.
        topWrapper : Path
            Path to the output top wrapper file.
        """
        generateUserDesignTopWrapper(self._context.fabric, userDesign, topWrapper)

    def genIOBelForTile(self, tile_name: str) -> list[Bel]:
        """Transform: Generate IO BELs for a tile and update fabric state.

        Config Access Generative IOs will be a separate Bel.
        Updates the tileDic with the generated IO BELs.

        Parameters
        ----------
        tile_name : str
            Name of the tile to generate IO Bels for

        Returns
        -------
        list[Bel]
            The BEL objects representing the generative IOs

        Raises
        ------
        ValueError
            If tile not found, invalid IO type, or config mismatch
        """
        return self._transform.generate_io_bels_for_tile(tile_name)

    def genFabricIOBels(self) -> None:
        """Transform: Generate IO BELs for all tiles with generative IOs."""
        self._transform.generate_fabric_io_bels()

    def gen_io_pin_order_config(self, tile: Tile | SuperTile, outfile: Path) -> None:
        """Generate IO pin order configuration YAML for a tile or super tile.

        Parameters
        ----------
        tile : Tile | SuperTile
            The fabric element for which to generate the configuration
        outfile : Path
            Output YAML path
        """
        self._transform.generate_io_pin_order_config(tile, outfile)

    def genTileMacro(
        self,
        tile_dir: Path,
        io_pin_config: Path,
        out_folder: Path,
        *,
        final_view: Path | None = None,
        optimisation: OptMode = OptMode.BALANCE,
        base_config_path: Path | None = None,
        config_override_path: Path | None = None,
        custom_config_overrides: dict | None = None,
        pdk_root: Path | None = None,
        pdk: str | None = None,
    ) -> None:
        """Transform: Run tile macro generation flow."""
        self._transform.run_tile_macro_flow(
            tile_dir,
            io_pin_config,
            out_folder,
            final_view=final_view,
            optimisation=optimisation,
            base_config_path=base_config_path,
            config_override_path=config_override_path,
            custom_config_overrides=custom_config_overrides,
            pdk_root=pdk_root,
            pdk=pdk,
        )

    def fabric_stitching(
        self,
        tile_marco_paths: dict[str, Path],
        fabric_path: Path,
        out_folder: Path,
        *,
        base_config_path: Path | None = None,
        config_override_path: Path | None = None,
        pdk_root: Path | None = None,
        pdk: str | None = None,
        **custom_config_overrides: dict,
    ) -> None:
        """Transform: Run fabric stitching flow to assemble tile macros.

        Parameters
        ----------
        tile_marco_paths : dict[str, Path]
            Dictionary mapping tile names to their macro output directories
        fabric_path : Path
            Path to the fabric-level Verilog file
        out_folder : Path
            Output directory for the stitched fabric
        base_config_path : Path | None, optional
            Path to base configuration YAML file
        config_override_path : Path | None, optional
            Additional configuration overrides
        pdk_root : Path | None, optional
            Path to PDK root directory
        pdk : str | None, optional
            PDK name to use
        **custom_config_overrides : dict
            Software configuration overrides

        Raises
        ------
        ValueError
            If PDK root or PDK is not specified
        """
        self._transform.run_fabric_stitching(
            tile_marco_paths,
            fabric_path,
            out_folder,
            base_config_path=base_config_path,
            config_override_path=config_override_path,
            pdk_root=pdk_root,
            pdk=pdk,
            **custom_config_overrides,
        )

    def get_most_frequent_tile(self) -> Tile:
        """Get the most frequently used tile in the fabric.

        Returns
        -------
        Tile
            The most frequently used tile in the fabric
        """
        from collections import Counter
        from itertools import chain

        counts = Counter(chain.from_iterable(row for row in self._context.fabric.tile))
        most_common_tile, _ = counts.most_common(1)[0]
        return most_common_tile

    def full_fabric_automation(
        self,
        project_dir: Path,
        out_folder: Path,
        *,
        pdk_root: Path | None = None,
        pdk: str | None = None,
        base_config_path: Path | None = None,
        config_override_path: Path | None = None,
        tile_opt_config: Path | None = None,
        **config_overrides: dict,
    ) -> None:
        """Transform: Run complete automated eFPGA macro flow."""
        self._transform.run_full_automation(
            project_dir,
            out_folder,
            pdk_root=pdk_root,
            pdk=pdk,
            base_config_path=base_config_path,
            config_override_path=config_override_path,
            tile_opt_config=tile_opt_config,
            **config_overrides,
        )

"""Fabric transformation pipeline - processes and mutates fabric state.

Similar to middleware in web frameworks, transforms modify the fabric
before export. Current transforms handle IO BEL generation and GDS flows.
Future transforms can add fabric optimizations, analysis, etc.
"""

from pathlib import Path

import yaml
from loguru import logger

from fabulous.fabric_definition.bel import Bel
from fabulous.fabric_definition.supertile import SuperTile
from fabulous.fabric_definition.tile import Tile
from fabulous.fabric_generator.code_generator.code_generator_VHDL import (
    VHDLCodeGenerator,
)
from fabulous.fabric_generator.gds_generator.flows.fabric_macro_flow import (
    FABulousFabricMacroFlow,
)
from fabulous.fabric_generator.gds_generator.flows.full_fabric_flow import (
    FABulousFabricMacroFullFlow,
)
from fabulous.fabric_generator.gds_generator.flows.tile_macro_flow import (
    FABulousTileVerilogMarcoFlow,
)
from fabulous.fabric_generator.gds_generator.gen_io_pin_config_yaml import (
    generate_IO_pin_order_config,
)
from fabulous.fabric_generator.gds_generator.steps.tile_optimisation import OptMode
from fabulous.fabric_generator.gen_fabric.fabric_automation import genIOBel
from fabulous.fabulous_settings import get_context


class Transform:
    """Fabric transformation pipeline - processes and mutates fabric state.

    Similar to middleware in web frameworks, transforms modify the fabric
    before export. Current transforms handle IO BEL generation and GDS flows.
    Future transforms can add fabric optimizations, analysis, etc.

    Parameters
    ----------
    context : Context
        The fabric processing context containing state

    Attributes
    ----------
    context : Context
        Reference to the processing context
    """

    def __init__(self, context) -> None:
        self.context = context

    def generate_io_bels_for_tile(self, tile_name: str) -> list[Bel]:
        """Transform: Generate IO BELs for a tile and update fabric state.

        Config Access Generative IOs will be a separate Bel.
        This mutates the fabric's tileDic and tile grid.

        Parameters
        ----------
        tile_name : str
            Name of the tile to generate IO BELs for

        Returns
        -------
        list[Bel]
            The BEL objects representing the generative IOs

        Raises
        ------
        ValueError
            If tile not found in fabric, invalid IO type, or config mismatch
        """
        tile = self.context.fabric.getTileByName(tile_name)
        bels: list[Bel] = []
        if not tile:
            logger.error(f"Tile {tile_name} not found in fabric.")
            raise ValueError

        suffix = (
            "vhdl" if isinstance(self.context.writer, VHDLCodeGenerator) else "v"
        )

        gios = [gio for gio in tile.gen_ios if not gio.configAccess]
        gio_config_access = [gio for gio in tile.gen_ios if gio.configAccess]

        if gios:
            bel_path = tile.tileDir.parent / f"{tile.name}_GenIO.{suffix}"
            bel = genIOBel(gios, bel_path, True)
            if bel:
                bels.append(bel)
        if gio_config_access:
            bel_path = (
                tile.tileDir.parent / f"{tile.name}_ConfigAccess_GenIO.{suffix}"
            )
            bel = genIOBel(gio_config_access, bel_path, True)
            if bel:
                bels.append(bel)

        # update fabric tileDic with generated IO BELs
        if self.context.fabric.tileDic.get(tile_name):
            self.context.fabric.tileDic[tile_name].bels += bels
        elif not self.context.fabric.unusedTileDic[tile_name].bels:
            logger.warning(
                f"Tile {tile_name} is not used in fabric, but defined in fabric.csv."
            )
            self.context.fabric.unusedTileDic[tile_name].bels += bels
        else:
            logger.error(
                f"Tile {tile_name} is not defined in fabric, please add to fabric.csv."
            )
            raise ValueError

        # update bels on all tiles in fabric.tile grid
        for row in self.context.fabric.tile:
            for tile in row:
                if tile and tile.name == tile_name:
                    tile.bels += bels

        return bels

    def generate_fabric_io_bels(self) -> None:
        """Transform: Generate IO BELs for all tiles with generative IOs."""
        for tile in self.context.fabric.tileDic.values():
            if tile.gen_ios:
                logger.info(f"Generating IO BELs for tile {tile.name}")
                self.generate_io_bels_for_tile(tile.name)

    def generate_io_pin_order_config(
        self, tile: Tile | SuperTile, outfile: Path
    ) -> None:
        """Generate IO pin order configuration YAML for a tile or super tile.

        Parameters
        ----------
        tile : Tile | SuperTile
            The fabric element for which to generate the configuration
        outfile : Path
            Output YAML path
        """
        generate_IO_pin_order_config(self.context.fabric, tile, outfile)

    def run_tile_macro_flow(
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
        """Transform: Run tile macro generation flow.

        Parameters
        ----------
        tile_dir : Path
            Directory containing tile definition
        io_pin_config : Path
            IO pin configuration file
        out_folder : Path
            Output directory for macro
        final_view : Path | None, optional
            Path to save final view snapshot
        optimisation : OptMode, optional
            Optimization mode. Default BALANCE.
        base_config_path : Path | None, optional
            Base configuration file
        config_override_path : Path | None, optional
            Override configuration file
        custom_config_overrides : dict | None, optional
            Additional configuration overrides
        pdk_root : Path | None, optional
            PDK root directory
        pdk : str | None, optional
            PDK name

        Raises
        ------
        ValueError
            If PDK not specified
        """
        if pdk_root is None:
            pdk_root = get_context().pdk_root.parent
        if pdk is None:
            pdk = get_context().pdk
            if pdk is None:
                raise ValueError("PDK must be specified either here or in settings.")

        logger.info(f"PDK root: {pdk_root}")
        logger.info(f"PDK: {pdk}")
        logger.info(f"Output folder: {out_folder.resolve()}")
        flow = FABulousTileVerilogMarcoFlow(
            self.context.fabric.getTileByName(tile_dir.name),
            io_pin_config,
            optimisation,
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
        logger.info("Marco flow completed.")

    def run_fabric_stitching(
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
        if pdk_root is None:
            pdk_root = get_context().pdk_root
        if pdk is None:
            pdk = get_context().pdk
            if pdk is None:
                raise ValueError("PDK must be specified either here or in settings.")

        logger.info(f"PDK root: {pdk_root}")
        logger.info(f"PDK: {pdk}")
        logger.info(f"Output folder: {out_folder.resolve()}")

        flow = FABulousFabricMacroFlow(
            fabric=self.context.fabric,
            fabric_verilog_paths=[fabric_path],
            tile_macro_dirs=tile_marco_paths,
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

    def run_full_automation(
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
        """Transform: Run complete automated eFPGA macro flow.

        Parameters
        ----------
        project_dir : Path
            Project directory
        out_folder : Path
            Output directory
        pdk_root : Path | None, optional
            PDK root directory
        pdk : str | None, optional
            PDK name
        base_config_path : Path | None, optional
            Base configuration file
        config_override_path : Path | None, optional
            Override configuration file
        tile_opt_config : Path | None, optional
            Tile optimization configuration
        **config_overrides : dict
            Additional configuration overrides

        Raises
        ------
        ValueError
            If PDK root or PDK not specified
        """
        if pdk_root is None:
            pdk_root = get_context().pdk_root
            if pdk_root is None:
                raise ValueError(
                    "PDK root must be specified either here or in settings."
                )
        if pdk is None:
            pdk = get_context().pdk
            if pdk is None:
                raise ValueError("PDK must be specified either here or in settings.")

        logger.info(f"PDK root: {pdk_root}")
        logger.info(f"PDK: {pdk}")
        logger.info(f"Output folder: {out_folder.resolve()}")
        final_config_args = {}
        if base_config_path is not None:
            final_config_args.update(
                yaml.safe_load(base_config_path.read_text(encoding="utf-8"))
            )
        if config_override_path is not None:
            final_config_args.update(
                yaml.safe_load(config_override_path.read_text(encoding="utf-8"))
            )
        final_config_args["FABULOUS_PROJ_DIR"] = str(project_dir.resolve())
        final_config_args["FABULOUS_FABRIC"] = self.context.fabric
        final_config_args["DESIGN_NAME"] = self.context.fabric.name
        if tile_opt_config is not None:
            final_config_args["TILE_OPT_INFO"] = str(tile_opt_config)
        if config_overrides:
            final_config_args.update(config_overrides)
        flow = FABulousFabricMacroFullFlow(
            final_config_args,
            name=self.context.fabric.name,
            design_dir=str(out_folder.resolve()),
            pdk=pdk,
            pdk_root=str((pdk_root).resolve().parent),
        )
        result = flow.start()
        logger.info(f"Saving final views for FABulous to {out_folder / 'final_views'}")
        result.save_snapshot(out_folder / "final_views")
        logger.info("Full automation flow completed.")

    # Future transforms can be added here:
    # def optimize_routing(self) -> None: ...
    # def analyze_timing(self) -> dict: ...
    # def apply_constraints(self, constraints: dict) -> None: ...

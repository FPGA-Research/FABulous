"""Fabric and tile HDL-generation commands for the FABulous REPL.

Generate config memory, switch matrices, tiles, IO, and the fabric.
"""

import csv
import pickle
from dataclasses import replace
from pathlib import Path
from typing import Annotated

from cmd2 import with_annotated, with_category
from cmd2.annotated import Argument, Option
from loguru import logger

from fabulous.custom_exception import CommandError, GDSFlowError
from fabulous.fabric_cad.gen_npnr_model import PLACEMENT_ESTIMATE_TEXT
from fabulous.fabric_definition.configmem import ConfigMem
from fabulous.fabric_definition.define import ConfigBitMode
from fabulous.fabric_definition.supertile import SuperTile
from fabulous.fabric_definition.tile import Tile
from fabulous.fabric_generator.gds_generator.flows.placement_opt_flow import (
    search_tile_from_placement,
    won_config_mapping,
)
from fabulous.fabric_generator.gen_fabric.fabric_automation import (
    generateCustomTileConfig,
)
from fabulous.fabric_generator.gen_fabric.gen_configmem import (
    generate_tile_config_mem,
)
from fabulous.fabric_generator.parser.parse_csv import (
    parseTilesCSV,
    set_config_mem_entry,
)
from fabulous.fabulous_repl.command_set_base import (
    CMD_FABRIC_FLOW,
    CMD_TOOLS,
    META_DATA_DIR,
    ReplCommandSet,
)
from fabulous.fabulous_repl.helper import (
    CommandPipeline,
)


class FabricGenCommandSet(ReplCommandSet):
    """Generate config memory, switch matrices, tiles, IO, and the fabric."""

    DEFAULT_CATEGORY = CMD_FABRIC_FLOW

    @with_annotated
    def do_gen_config_mem(
        self,
        tiles: Annotated[
            list[str],
            Argument(
                help_text="A list of tile",
                completer=lambda self: [
                    tile.name for tile in self._cmd.fabulousAPI.getTiles()
                ],
            ),
        ],
        opt_config_mapping: Annotated[
            bool,
            Option(
                "--opt-config-mapping",
                help_text=(
                    "Map each configuration bit to the frame crosspoint nearest "
                    "its placed latch, rather than taking the mapping the tile's "
                    "ConfigMem.csv already holds. The searched mapping is written "
                    "to <tile>_ConfigMem_opt.csv and the tile's CONFIGMEM entry "
                    "pointed at it. Searches the tile through the LibreLane flow, "
                    "so it needs a PDK, a DIE_AREA on the tile and a frame-based "
                    "fabric."
                ),
            ),
        ] = False,
        iterations: Annotated[
            int | None,
            Option(
                "--iterations",
                help_text="Placements to spend on the search. Defaults to 10.",
            ),
        ] = None,
        override: Annotated[
            Path | None,
            Option(
                "--override", help_text="Override config with a custom YAML config file"
            ),
        ] = None,
    ) -> None:
        """Generate configuration memory of the given tile.

        Parsing input arguments and calling `generate_tile_config_mem`. A
        FLIPFLOP_CHAIN fabric has no configuration memory, so the command
        refuses.

        With `--opt-config-mapping` the mapping is searched from the tile's own
        placement before the module is generated, so the flag changes where the
        mapping comes from rather than adding a stage. Each tile is searched in
        turn, which costs a LibreLane run apiece.

        Logs generation processes for each specified tile.
        """
        repl = self._cmd
        fabric = repl.fabulousAPI.fabric
        if fabric.configBitMode is not ConfigBitMode.FRAME_BASED:
            raise CommandError(
                f"A {fabric.configBitMode.value} fabric shifts its configuration "
                "through a daisy chain, so it has no configuration memory to "
                "generate."
            )
        logger.info(f"Generating Config Memory for {' '.join(tiles)}")
        for i in tiles:
            logger.info(f"Generating configMem for {i}")
            tile = fabric.getTileByName(i)
            if not isinstance(tile, Tile):
                if opt_config_mapping:
                    raise TypeError(
                        f"{i} is a supertile; the placement-driven mapping "
                        "searches the placement of one tile."
                    )
                repl.fabulousAPI.gen_super_tile_config_mem(i)
                logger.info(f"Generated configMem for super tile {i}")
                continue
            if opt_config_mapping and not self._map_config_from_placement(
                tile, iterations=iterations, override=override
            ):
                return
            generate_tile_config_mem(repl.fabulousAPI.writer, tile)
        if opt_config_mapping:
            logger.info("Run next: gen_bitStream_spec")
        logger.info("ConfigMem generation complete")

    def _map_config_from_placement(
        self,
        tile: Tile,
        *,
        iterations: int | None,
        override: Path | None,
    ) -> bool:
        """Search the tile's placement for its mapping and give it to the tile.

        The searched mapping is written to `<tile>_ConfigMem_opt.csv` and the
        tile's `CONFIGMEM` entry is pointed at it, so the mapping the tile was
        hardened against survives and the tile definition names the one it is
        now generated from. The tile carries the searched mapping afterwards,
        which is what makes the search the generation method.

        Parameters
        ----------
        tile : Tile
            The tile to search.
        iterations : int | None
            Placements to spend on the search.
        override : Path | None
            A YAML of further config for the flow.

        Returns
        -------
        bool
            True when a mapping was written, False when the search refused or
            no iteration reached a proposal.
        """
        repl = self._cmd
        try:
            state = search_tile_from_placement(
                tile,
                project_dir=repl.projectDir,
                fabric=repl.fabulousAPI.fabric,
                iterations=iterations,
                override=override,
            )
        except GDSFlowError as error:
            logger.error(str(error))
            return False
        won = won_config_mapping(state)
        if won is None:
            logger.error(
                f"No iteration of the {tile.name} search implemented a mapping, "
                "so there is nothing to generate from; raise --iterations"
            )
            return False
        # Named after the tile rather than after the mapping it was searched
        # from, so searching twice rewrites one file instead of growing a chain.
        destination = tile.config_mem.source.parent / f"{tile.name}_ConfigMem_opt.csv"
        fabric = repl.fabulousAPI.fabric
        tile.config_mem = replace(
            ConfigMem.from_csv(
                won,
                frame_bits_per_row=fabric.frameBitsPerRow,
                max_frames_per_col=fabric.maxFramesPerCol,
            ),
            source=destination,
        )
        tile.config_mem.to_csv()
        set_config_mem_entry(tile.tileDir, tile.name, destination)
        logger.info(
            f"Mapped {tile.name} from its placement into {destination}, which "
            f"{tile.tileDir} now names"
        )
        return True

    @with_annotated
    def do_gen_switch_matrix(
        self,
        tiles: Annotated[
            list[str],
            Argument(
                help_text="A list of tile",
                completer=lambda self: [
                    tile.name for tile in self._cmd.fabulousAPI.getTiles()
                ],
            ),
        ],
    ) -> None:
        """Generate switch matrix of given tile.

        Parsing input arguments and calling `genSwitchMatrix`.

        Also logs generation process for each specified tile.
        """
        repl = self._cmd
        fabric = repl.fabulousAPI.fabric
        logger.info(f"Generating switch matrix for {' '.join(tiles)}")
        for i in tiles:
            logger.info(f"Generating switch matrix for {i}")
            directory = fabric.getTileByName(i).directory
            repl.fabulousAPI.setWriterOutputFile(
                directory / f"{i}_switch_matrix.{repl.extension}"
            )
            repl.fabulousAPI.genSwitchMatrix(i)
        logger.info("Switch matrix generation complete")

    @with_annotated
    def do_gen_tile(
        self,
        tiles: Annotated[
            list[str],
            Argument(
                help_text="A list of tile",
                completer=lambda self: [
                    tile.name for tile in self._cmd.fabulousAPI.getTiles()
                ],
            ),
        ],
    ) -> None:
        """Generate given tile with switch matrix and configuration memory.

        Parsing input arguments, call functions such as `genSwitchMatrix` and
        `generate_tile_config_mem`. Handle both regular tiles and super tiles
        with sub-tiles.

        Also logs generation process for each specified tile and sub-tile.
        """
        repl = self._cmd
        fabric = repl.fabulousAPI.fabric
        frame_based = fabric.configBitMode is ConfigBitMode.FRAME_BASED
        logger.info(f"Generating tile {' '.join(tiles)}")
        for t in tiles:
            holder = fabric.getTileByName(t)
            if isinstance(holder, SuperTile):
                sub_tiles = [child.name for child in holder.tiles]
                logger.info(
                    f"{t} is a super tile, generating {t} with sub tiles "
                    f"{' '.join(sub_tiles)}"
                )
                for st in sub_tiles:
                    # `holder.tiles` are copies; the memory lives on the tile type.
                    sub_tile = fabric.getTileByName(st)
                    if not isinstance(sub_tile, Tile):
                        raise TypeError(
                            f"{st} under {t} resolves to a supertile; a "
                            "supertile cannot be a subtile of another."
                        )

                    # Gen switch matrix
                    logger.info(f"Generating switch matrix for tile {t}")
                    logger.info(f"Generating switch matrix for {st}")
                    repl.fabulousAPI.setWriterOutputFile(
                        sub_tile.directory / f"{st}_switch_matrix.{repl.extension}"
                    )
                    repl.fabulousAPI.genSwitchMatrix(st)
                    logger.info(f"Generated switch matrix for {st}")

                    # Gen config mem
                    if frame_based:
                        logger.info(f"Generating configMem for tile {t}")
                        logger.info(f"Generating ConfigMem for {st}")
                        generate_tile_config_mem(repl.fabulousAPI.writer, sub_tile)
                        logger.info(f"Generated configMem for {st}")

                    # Gen tile
                    logger.info(f"Generating subtile for tile {t}")
                    logger.info(f"Generating subtile {st}")
                    repl.fabulousAPI.setWriterOutputFile(
                        sub_tile.directory / f"{st}.{repl.extension}"
                    )
                    repl.fabulousAPI.genTile(st)
                    logger.info(f"Generated subtile {st}")

                # Gen supertile switch matrix (no-op if no supertile_matrix file)
                logger.info(f"Generating switch matrix for super tile {t}")
                repl.fabulousAPI.setWriterOutputFile(
                    holder.directory / f"{t}_switch_matrix.{repl.extension}"
                )
                repl.fabulousAPI.gen_super_tile_switch_matrix(t)
                logger.info(f"Generated switch matrix for super tile {t}")

                # Gen supertile ConfigMem (no-op if no ST config bits)
                if frame_based:
                    logger.info(f"Generating ConfigMem for super tile {t}")
                    repl.fabulousAPI.gen_super_tile_config_mem(t)
                    logger.info(f"Generated ConfigMem for super tile {t}")

                # Gen super tile
                logger.info(f"Generating super tile {t}")
                repl.fabulousAPI.setWriterOutputFile(
                    holder.directory / f"{t}.{repl.extension}"
                )
                repl.fabulousAPI.genSuperTile(t)
                logger.info(f"Generated super tile {t}")
                continue

            # Gen switch matrix
            repl.onecmd_plus_hooks(f"gen_switch_matrix {t}")
            if repl.exit_code != 0:
                raise CommandError(f"Switch matrix generation failed for tile {t}")

            # Gen config mem
            if frame_based:
                repl.onecmd_plus_hooks(f"gen_config_mem {t}")
                if repl.exit_code != 0:
                    raise CommandError(f"Config memory generation failed for tile {t}")

            logger.info(f"Generating tile {t}")
            # Gen tile
            repl.fabulousAPI.setWriterOutputFile(
                holder.directory / f"{t}.{repl.extension}"
            )
            repl.fabulousAPI.genTile(t)
            logger.info(f"Generated tile {t}")

        logger.info("Tile generation complete")

    def do_gen_all_tile(self, *_ignored: str) -> None:
        """Generate all tiles by calling `do_gen_tile`."""
        repl = self._cmd
        logger.info("Generating all tiles")
        repl.onecmd_plus_hooks(f"gen_tile {' '.join(repl.all_tile)}")
        if repl.exit_code != 0:
            raise CommandError("Tile generation failed")
        logger.info("All tiles generation complete")

    def do_gen_fabric(self, *_ignored: str) -> None:
        """Generate fabric based on the loaded fabric.

        Calling `gen_all_tile` and `genFabric`.

        Logs start and completion of fabric generation process.
        """
        repl = self._cmd
        logger.info(f"Generating fabric {repl.fabulousAPI.fabric.name}")
        repl.onecmd_plus_hooks("gen_all_tile")
        if repl.exit_code != 0:
            raise CommandError("Tile generation failed")
        repl.fabulousAPI.setWriterOutputFile(
            f"{repl.projectDir}/Fabric/{repl.fabulousAPI.fabric.name}.{repl.extension}"
        )
        repl.fabulousAPI.genFabric()
        logger.info("Fabric generation complete")

    @with_annotated
    def do_gen_geometry(
        self,
        padding: Annotated[
            int,
            Argument(
                help_text="Padding value for geometry generation",
                choices=range(4, 33),
                metavar="[4-32]",
            ),
        ] = 8,
    ) -> None:
        """Generate geometry of fabric for FABulator.

        Checking if fabric is loaded, and calling 'genGeometry' and passing on padding
        value. Default padding is '8'.

        Also logs geometry generation, the used padding value and any warning about
        faulty padding arguments, as well as errors if the fabric is not loaded or the
        padding is not within the valid range of 4 to 32.
        """
        repl = self._cmd
        logger.info(f"Generating geometry for {repl.fabulousAPI.fabric.name}")
        geom_file = f"{repl.projectDir}/{repl.fabulousAPI.fabric.name}_geometry.csv"
        repl.fabulousAPI.setWriterOutputFile(geom_file)

        repl.fabulousAPI.genGeometry(padding)
        logger.info("Geometry generation complete")
        logger.info(f"{geom_file} can now be imported into FABulator")

    def do_gen_bitStream_spec(self, *_ignored: str) -> None:
        """Generate bitstream specification of the fabric.

        By calling `genBitStreamSpec` and saving the specification to a binary and CSV
        file.

        Also logs the paths of the output files.
        """
        repl = self._cmd
        logger.info("Generating bitstream specification")
        spec_object = repl.fabulousAPI.genBitStreamSpec()

        logger.info(f"output file: {repl.projectDir}/{META_DATA_DIR}/bitStreamSpec.bin")
        with Path(f"{repl.projectDir}/{META_DATA_DIR}/bitStreamSpec.bin").open(
            "wb"
        ) as out_file:
            pickle.dump(spec_object, out_file)

        logger.info(f"output file: {repl.projectDir}/{META_DATA_DIR}/bitStreamSpec.csv")
        with Path(f"{repl.projectDir}/{META_DATA_DIR}/bitStreamSpec.csv").open(
            "w", encoding="utf-8", newline="\n"
        ) as f:
            w = csv.writer(f)
            for key1 in spec_object["TileSpecs"]:
                w.writerow([key1])
                for key2, val in spec_object["TileSpecs"][key1].items():
                    w.writerow([key2, val])
        logger.info("Bitstream specification generation complete")

    def do_gen_top_wrapper(self, *_ignored: str) -> None:
        """Generate top wrapper of the fabric by calling `genTopWrapper`."""
        repl = self._cmd
        logger.info("Generating top wrapper")
        repl.fabulousAPI.setWriterOutputFile(
            f"{repl.projectDir}/Fabric/{repl.fabulousAPI.fabric.name}_top.{repl.extension}"
        )
        repl.fabulousAPI.genTopWrapper()
        logger.info("Top wrapper generation complete")

    def do_run_fab(self, *_ignored: str) -> None:
        """Generate the fabric based on the CSV file.

        Create bitstream specification of the fabric, top wrapper of the fabric, Nextpnr
        model of the fabric and geometry information of the fabric.
        """
        logger.info("Running FABulous")

        success = (
            CommandPipeline(self._cmd)
            .add_step("gen_io_fabric")
            .add_step("gen_fabric", "Fabric generation failed")
            .add_step("gen_bitStream_spec", "Bitstream specification generation failed")
            .add_step("gen_top_wrapper", "Top wrapper generation failed")
            .add_step("gen_model_npnr", "Nextpnr model generation failed")
            .add_step("gen_geometry", "Geometry generation failed")
            .execute()
        )

        if success:
            logger.info("FABulous fabric flow complete")

    def do_run_FABulous_fabric(self, *_ignored: str) -> None:
        """Generate the fabric based on the CSV file.

        deprecated: Use ``run_fab`` instead.
        """
        repl = self._cmd
        logger.warning(
            "The 'run_FABulous_fabric' command is deprecated. Use 'run_fab' instead."
        )
        repl.onecmd_plus_hooks("run_fab")
        if repl.exit_code != 0:
            raise CommandError("FABulous fabric flow failed")

    def do_gen_model_npnr(self, *_ignored: str) -> None:
        """Generate Nextpnr model of fabric.

        By parsing various required files for place and route such as `pips.txt`,
        `bel.txt`, `bel.v2.txt` and `template.pcf`. Output files are written to the
        directory specified by `metaDataDir` within `projectDir`.

        Logs output file directories.
        """
        repl = self._cmd
        logger.info("Generating npnr model")
        npnr_model = repl.fabulousAPI.gen_routing_model()
        logger.info(f"output file: {repl.projectDir}/{META_DATA_DIR}/pips.txt")
        with Path(f"{repl.projectDir}/{META_DATA_DIR}/pips.txt").open("w") as f:
            f.write(npnr_model[0])

        logger.info(f"output file: {repl.projectDir}/{META_DATA_DIR}/bel.txt")
        with Path(f"{repl.projectDir}/{META_DATA_DIR}/bel.txt").open("w") as f:
            f.write(npnr_model[1])

        logger.info(f"output file: {repl.projectDir}/{META_DATA_DIR}/bel.v2.txt")
        with Path(f"{repl.projectDir}/{META_DATA_DIR}/bel.v2.txt").open("w") as f:
            f.write(npnr_model[2])

        logger.info(f"output file: {repl.projectDir}/{META_DATA_DIR}/bel.v3.txt")
        with Path(f"{repl.projectDir}/{META_DATA_DIR}/bel.v3.txt").open("w") as f:
            f.write(npnr_model[3])

        logger.info(f"output file: {repl.projectDir}/{META_DATA_DIR}/template.pcf")
        with Path(f"{repl.projectDir}/{META_DATA_DIR}/template.pcf").open("w") as f:
            f.write(npnr_model[4])

        estimate_path = Path(
            f"{repl.projectDir}/{META_DATA_DIR}/placement_estimate.txt"
        )
        logger.info(f"output file: {estimate_path}")
        estimate_path.write_text(PLACEMENT_ESTIMATE_TEXT)

        logger.info("Generated npnr model")

    @with_annotated
    def do_gen_io_tiles(
        self,
        tiles: Annotated[
            list[str],
            Argument(
                help_text="A list of tile",
                completer=lambda self: [
                    tile.name for tile in self._cmd.fabulousAPI.getTiles()
                ],
            ),
        ],
    ) -> None:
        """Generate I/O BELs for specified tiles.

        This command generates Input/Output Basic Elements of Logic (BELs) for the
        specified tiles, enabling external connectivity for the FPGA fabric.
        """
        repl = self._cmd
        for tile in tiles:
            repl.fabulousAPI.genIOBelForTile(tile)

    def do_gen_io_fabric(self, _args: str) -> None:
        """Generate I/O BELs for the entire fabric.

        This command generates Input/Output Basic Elements of Logic (BELs) for all
        applicable tiles in the fabric, providing external connectivity
        across the entire FPGA design.

        Parameters
        ----------
        _args : str
            Command arguments (unused for this command).
        """
        repl = self._cmd
        repl.fabulousAPI.genFabricIOBels()

    @with_annotated
    def do_gen_io_pin_config(
        self,
        tile: Annotated[
            str,
            Argument(
                help_text="A tile or supertile",
                completer=lambda self: self._cmd.all_tile,
            ),
        ],
        output: Annotated[
            Path | None,
            Argument(help_text="Output path for the generated IO pin config YAML"),
        ] = None,
    ) -> None:
        """Generate an IO pin configuration YAML file for a tile or supertile."""
        repl = self._cmd
        logger.info(f"Generating IO pin config for {tile}")

        tile_obj = repl.fabulousAPI.getTile(tile)
        if tile_obj is None:
            logger.error(f"Tile {tile} not found in fabric definition")
            return

        output_path = output
        if output_path is None:
            output_path = repl.projectDir / "Tile" / tile / f"{tile}_io_pin_order.yaml"

        output_path.parent.mkdir(parents=True, exist_ok=True)
        repl.fabulousAPI.gen_io_pin_order_config(tile_obj, output_path)

        logger.info(f"Generated IO pin config at {output_path}")
        logger.info("IO pin config generation complete")

    @with_category(CMD_TOOLS)
    @with_annotated
    def do_generate_custom_tile_config(
        self,
        tile_path: Annotated[
            Path, Argument(help_text="Path to the target tile directory")
        ],
        switch_matrix: Annotated[
            bool,
            Option(
                "--switch-matrix",
                "-sm",
                help_text="Generate a Tile Switch Matrix (enabled by default)",
            ),
        ] = True,
    ) -> None:
        """Generate a custom tile configuration for a given tile folder.

        Or path to bel folder. A tile `.csv` file and a switch matrix `.list` file will
        be generated.

        The provided path may contain bel files, which will be included in the generated
        tile .csv file as well as the generated switch matrix .list file.
        """
        if not tile_path.is_dir():
            logger.error(f"{tile_path} is not a directory or does not exist")
            return

        tile_csv = generateCustomTileConfig(tile_path)

        if switch_matrix:
            parseTilesCSV(tile_csv)
